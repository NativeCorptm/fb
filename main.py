import sqlite3
import time
import telepot
import threading
import os
import requests
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request

BOT_TOKEN = '7726236368:AAEGHLdJHvjNIi4tET-ZqtATEheGJOOxddo'
DB_DIR = '/mnt/data'
loading_flags = {}
cached_data = {}

app = Flask(__name__)
bot = telepot.Bot(BOT_TOKEN)

def handle_command(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    if content_type not in ['text', 'document']:
        return

    if content_type == 'document' and chat_id in file_admin_listening:
        file_id = msg['document']['file_id']
        file_name = msg['document']['file_name']
        dest_path = os.path.join(DB_DIR, file_name)
        bot.download_file(file_id, dest_path)
        bot.sendMessage(chat_id, f"✅ File salvato in:\n{dest_path}")
        file_admin_listening.remove(chat_id)
        return

    text = msg['text']

    if text in ['/start', '/menu']:
        bot.sendMessage(chat_id, "MENU\n├ /facebook {numero}\n├ /facebook_id {id}")
        return

    if text.startswith('/facebook '):
        numero = text.split(maxsplit=1)[1].replace(" ", "").replace("+", "")
        if numero.startswith("3") and len(numero) == 10:
            numero = "39" + numero

        status_msg = bot.sendMessage(chat_id, "🔎")
        msg_id = status_msg['message_id']
        loading_flags[chat_id] = True
        threading.Thread(target=loading_animation, args=(chat_id, msg_id)).start()

        try:
            db_file = None
            result = None
            for file in os.listdir(DB_DIR):
                if file.endswith(".db"):
                    conn = sqlite3.connect(os.path.join(DB_DIR, file))
                    cursor = conn.cursor()
                    cursor.execute("SELECT numero, id, nome, cognome, sesso FROM utenti WHERE numero=?", (numero,))
                    row = cursor.fetchone()
                    conn.close()
                    if row:
                        db_file = file
                        result = row
                        break

            if not db_file:
                loading_flags[chat_id] = False
                bot.editMessageText((chat_id, msg_id), "❌ Numero non trovato.")
                return

            cached_data[chat_id] = {'numero': numero, 'db_file': db_file, 'result': result}
        except Exception as e:
            loading_flags[chat_id] = False
            bot.editMessageText((chat_id, msg_id), f"Errore: {e}")
            return

        loading_flags[chat_id] = False
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='BACK ◀️', callback_data='back'),
             InlineKeyboardButton(text='SEARCH 🔎', callback_data='search')]
        ])
        bot.editMessageText((chat_id, msg_id), "• Numero trovato.", reply_markup=keyboard)

    elif text.startswith('/facebook_id '):
        id_value = text.split(maxsplit=1)[1]
        status_msg = bot.sendMessage(chat_id, "🔎")
        msg_id = status_msg['message_id']
        loading_flags[chat_id] = True
        threading.Thread(target=loading_animation, args=(chat_id, msg_id)).start()

        try:
            matches = []
            for file in os.listdir(DB_DIR):
                if file.endswith(".db"):
                    conn = sqlite3.connect(os.path.join(DB_DIR, file))
                    cursor = conn.cursor()
                    cursor.execute("SELECT numero, id, nome, cognome, sesso FROM utenti WHERE id=?", (id_value,))
                    rows = cursor.fetchall()
                    if rows:
                        matches.extend(rows)
                    conn.close()
        except Exception as e:
            loading_flags[chat_id] = False
            bot.editMessageText((chat_id, msg_id), f"Errore: {e}")
            return

        loading_flags[chat_id] = False

        if not matches:
            bot.editMessageText((chat_id, msg_id), "❌ ID non trovato.")
            return

        cached_data[chat_id] = {'numero': matches[0][0], 'db_file': '', 'result': matches[0]}
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='BACK ◀️', callback_data='back'),
             InlineKeyboardButton(text='SEARCH 🔎', callback_data='search')]
        ])
        bot.editMessageText((chat_id, msg_id), "• ID trovato.", reply_markup=keyboard)

    elif text.startswith('/carica_link '):
        args = text.split(maxsplit=1)
        if len(args) != 2:
            bot.sendMessage(chat_id, "❌ Usa: /carica_link <url>")
            return

        url = args[1]
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".db"):
            filename += ".db"
        dest_path = os.path.join(DB_DIR, filename)
        bot.sendMessage(chat_id, f"⬇️ Scarico da:\n{url}")

        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            with requests.get(url, stream=True, headers=headers, allow_redirects=True, timeout=30) as r:
                r.raise_for_status()
                with open(dest_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            bot.sendMessage(chat_id, f"✅ File salvato:\n{dest_path}")
        except Exception as e:
            bot.sendMessage(chat_id, f"❌ Errore nel download:\n{e}")

    elif text == '/file_admin':
        file_admin_listening.add(chat_id)
        bot.sendMessage(chat_id, "📎 Inviami ora il file `.db` come documento.")

def on_callback(msg):
    query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')
    chat_id = msg['message']['chat']['id']
    message_id = msg['message']['message_id']

    if query_data == "search":
        data = cached_data.get(chat_id)
        if not data:
            bot.editMessageText((chat_id, message_id), "❌ Dati non trovati.")
            return
        result = data['result']
        messaggio = (
            "Facebook\n"
            f"├ 📞Numero: {result[0]}\n"
            f"├ 🖇️Facebook: facebook.com/{result[1]}\n"
            f"├ 👤Nome: {result[2]}\n"
            f"└ 👤Cognome: {result[3]}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='BACK ◀️', callback_data='back_to_menu')]
        ])
        bot.editMessageText((chat_id, message_id), messaggio, reply_markup=keyboard, disable_web_page_preview=True)
        cached_data.pop(chat_id, None)
        loading_flags[chat_id] = False

    elif query_data == "back":
        bot.editMessageText((chat_id, message_id), "❌ Operazione annullata.")
        cached_data.pop(chat_id, None)
        loading_flags[chat_id] = False

    elif query_data == "back_to_menu":
        bot.editMessageText((chat_id, message_id), "MENU\n├ /facebook {numero}\n├ /facebook_id {id}")

def loading_animation(chat_id, message_id):
    dots = ["🔎", "🔎.", "🔎..", "🔎..."]
    i = 0
    last_text = ""
    while loading_flags.get(chat_id, False):
        text = dots[i % 4]
        if text != last_text:
            try:
                bot.editMessageText((chat_id, message_id), text)
                last_text = text
            except:
                pass
        i += 1
        time.sleep(0.5)

@app.route('/')
def index():
    return "Bot is running"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        json_data = request.get_json()
        bot.handle(json_data)
        return 'ok', 200

def keep_alive():
    while True:
        print("Bot attivo...")
        time.sleep(2000)

file_admin_listening = set()

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    MessageLoop(bot, {'chat': handle_command, 'callback_query': on_callback}).run_as_thread()
    app.run(host='0.0.0.0', port=5000)
