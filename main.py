import os
import telebot
from pymongo import MongoClient
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from flask import Flask
from threading import Thread

# 1. Start a Tiny Web Server for Render
app = Flask('')
@app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# 2. Load Keys
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# 3. Setup Bot & Database
bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['my_bot_database']
users_col = db['users']

active_chats = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Welcome! Bot is working.")

@bot.message_handler(func=lambda m: m.chat.id in active_chats)
def chat_relay(message):
    uid = message.chat.id
    pid = active_chats[uid]
    if message.text:
        try:
            translated = GoogleTranslator(source='auto', target='hi').translate(message.text)
            bot.send_message(pid, f"🌐 {translated}\n---\n{message.text}")
        except:
            bot.send_message(pid, message.text)

# 4. Start both Web Server and Bot
if __name__ == "__main__":
    t = Thread(target=run_web)
    t.start()
    bot.infinity_polling()
