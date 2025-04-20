import sqlite3
import time
import telepot
import threading
import os
import requests
from telepot.loop import MessageLoop
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request
from io import BytesIO

# === CONFIG ===
BOT_TOKEN = '7726236368:AAEGHLdJHvjNIi4tET-ZqtATEheGJOOxddo'
DB_DIR = '/mnt/data'  # Modificato per il corretto volume di Koyeb
loading_flags = {}
cached_data = {}

# === FLASK SETUP ===
app = Flask(__name__)

# === BOT SETUP ===
bot = telepot.Bot(BOT_TOKEN)

# === COMANDI ===
def handle_command(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    if content_type != 'text':
        return

    text = msg['text']

    if text == '/start' or text == '/menu':
        bot.sendMessage(chat_id, "MENU\n├ /facebook {numero}\n├ /facebook_id {id}\n├ /file_admin (carica il database tramite file.io)")
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

    elif text.startswith('/file_admin'):
        bot.sendMessage(chat_id, "Per favore, inviami il link di file.io contenente il file .db.")
        bot.register_next_step_handler(msg, process_file)

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
        menu_msg = "MENU\n├ /facebook {numero}\n├ /facebook_id {id}\n├ /file_admin (carica il database tramite file.io)"
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

# === FILE ADMIN ===
def process_file(msg):
    chat_id = msg['chat']['id']
    if 'text' not in msg or not msg['text'].startswith("https://file.io/"):
        bot.sendMessage(chat_id, "Non è stato fornito un link valido di file.io. Riprova!")
        return

    file_url = msg['text']
    try:
        # Scarica il file dal link di file.io
        response = requests.get(file_url)
        
        # Verifica che la risposta contenga un file
        if response.status_code != 200:
            bot.sendMessage(chat_id, "Errore nel recupero del file. Assicurati che il link sia valido.")
            return

        # Estrai il nome del file e salvalo nella directory di Koyeb
        file_name = file_url.split('/')[-1] + ".db"
        file_path = os.path.join(DB_DIR, file_name)

        with open(file_path, 'wb') as f:
            f.write(response.content)

        bot.sendMessage(chat_id, f"File {file_name} caricato correttamente nella directory del bot!")
    except Exception as e:
        bot.sendMessage(chat_id, f"Errore durante il caricamento del file: {e}")

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

# === AVVIO ===
if __name__ == '__main__':
    MessageLoop(bot, {'chat': handle_command, 'callback_query': on_callback}).run_as_thread()
    app.run(host='0.0.0.0', port=5000)
