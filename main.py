import sqlite3
import time
import telepot
import threading
import os
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request

# === CONFIG ===
BOT_TOKEN = '7726236368:AAEGHLdJHvjNIi4tET-ZqtATEheGJOOxddo'
DB_DIR = '/mnt/data'
loading_flags = {}
cached_data = {}
uploading_flags = {}

# === FLASK SETUP ===
app = Flask(__name__)

# === BOT SETUP ===
bot = telepot.Bot(BOT_TOKEN)

# === COMANDI ===
def handle_command(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)

    if content_type == 'text':
        text = msg['text']

        if text == '/start' or text == '/menu':
            bot.sendMessage(chat_id, "MENU\n├ /facebook {numero}\n├ /facebook_id {id}\n├ /file_admin")
            return

        if text.startswith('/facebook '):
            args = text.split(maxsplit=1)
            if len(args) != 2:
                return

            numero = args[1]
            numero = numero.replace(" ", "").replace("+", "")
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
                    bot.editMessageText((chat_id, msg_id), "❌ Numero non trovato nei database.")
                    return

                cached_data[chat_id] = {
                    'numero': numero,
                    'db_file': db_file,
                    'result': result
                }

            except Exception as e:
                loading_flags[chat_id] = False
                bot.editMessageText((chat_id, msg_id), f"Errore: {e}")
                return

            loading_flags[chat_id] = False
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text='BACK ◀️', callback_data='back'),
                    InlineKeyboardButton(text='SEARCH 🔎', callback_data='search')
                ]
            ])
            bot.editMessageText((chat_id, msg_id), "• Numero trovato.", reply_markup=keyboard)

        elif text.startswith('/facebook_id '):
            args = text.split()
            if len(args) != 2:
                return

            id_value = args[1]
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

            info = matches[0]
            cached_data[chat_id] = {
                'numero': info[0],
                'db_file': '',
                'result': info
            }

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text='BACK ◀️', callback_data='back'),
                    InlineKeyboardButton(text='SEARCH 🔎', callback_data='search')
                ]
            ])
            bot.editMessageText((chat_id, msg_id), "• ID trovato.", reply_markup=keyboard)

        elif text == '/file_admin':
            bot.sendMessage(chat_id, "Invia ora il file `.db` da caricare nel volume.")
            uploading_flags[chat_id] = True

    elif content_type == 'document':
        if uploading_flags.get(chat_id):
            file_id = msg['document']['file_id']
            file_name = msg['document']['file_name']
            file_info = bot.getFile(file_id)
            file_path = file_info['file_path']

            download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            local_path = os.path.join(DB_DIR, file_name)

            def download_file():
                import requests
                response = requests.get(download_url, stream=True)
                total_length = int(response.headers.get('content-length', 0))
                downloaded = 0
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            percent = int((downloaded / total_length) * 100)
                            bot.sendMessage(chat_id, f"Caricamento: {percent}%")
                bot.sendMessage(chat_id, f"✅ File '{file_name}' salvato in {DB_DIR}.")
                uploading_flags.pop(chat_id, None)

            threading.Thread(target=download_file).start()

# === CALLBACK ===
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
        if result:
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
        else:
            bot.editMessageText((chat_id, message_id), "❌ Dato non trovato nel DB.")

        cached_data.pop(chat_id, None)
        loading_flags[chat_id] = False

    elif query_data == "back":
        bot.editMessageText((chat_id, message_id), "❌ Operazione annullata.")
        cached_data.pop(chat_id, None)
        loading_flags[chat_id] = False

    elif query_data == "back_to_menu":
        menu_msg = "MENU\n├ /facebook {numero}\n├ /facebook_id {id}\n├ /file_admin"
        bot.editMessageText((chat_id, message_id), menu_msg)

# === ANIMAZIONE ===
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

# === FLASK ROUTES ===
@app.route('/')
def index():
    return "Bot is running"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        json_data = request.get_json()
        bot.handle(json_data)
        return 'ok', 200

# === KEEP-ALIVE TERMINALE ===
def keep_alive():
    while True:
        print("Bot attivo - ping interno")
        time.sleep(2000)

# === AVVIO ===
if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    MessageLoop(bot, {'chat': handle_command, 'callback_query': on_callback}).run_as_thread()
    app.run(host='0.0.0.0', port=5000)
