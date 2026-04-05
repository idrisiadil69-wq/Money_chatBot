import os
import telebot
from pymongo import MongoClient
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# 1. Load Keys
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# 2. Setup
bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['my_bot_database']
users_col = db['users']

active_chats = {} 

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({"user_id": user_id, "username": username, "balance": 100, "lang": "en"})
        bot.reply_to(message, f"Welcome {username}! You have 100 coins.")
    else:
        bot.reply_to(message, f"Welcome back {username}! Balance: {user['balance']}")

# 3. FIXED AUTO-TRANSLATE LOGIC
@bot.message_handler(func=lambda m: m.chat.id in active_chats)
def chat_relay(message):
    uid = message.chat.id
    pid = active_chats[uid]
    
    if message.text:
        try:
            # This uses the modern 'deep-translator' which works on Render
            translated = GoogleTranslator(source='auto', target='hi').translate(message.text)
            final_msg = f"🌐 {translated}\n---\n{message.text}"
            bot.send_message(pid, final_msg)
        except Exception as e:
            bot.send_message(pid, message.text)

bot.infinity_polling()
    
