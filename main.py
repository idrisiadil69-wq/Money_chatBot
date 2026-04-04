import os
import telebot
from pymongo import MongoClient
from dotenv import load_dotenv
from googletrans import Translator

# 1. Load Keys
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

# 2. Setup
bot = telebot.TeleBot(BOT_TOKEN)
translator = Translator()
client = MongoClient(MONGO_URI)
db = client['my_bot_database']
users_col = db['users']

# This stores who is talking to who
active_chats = {} 

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "User"
    
    # Save to Database
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({"user_id": user_id, "username": username, "balance": 100, "lang": "en"})
        bot.reply_to(message, f"Welcome {username}! You have 100 coins. Use /find to chat.")
    else:
        bot.reply_to(message, f"Welcome back {username}! Balance: {user['balance']}")

# 3. AUTO-TRANSLATE LOGIC
@bot.message_handler(func=lambda m: m.chat.id in active_chats)
def chat_relay(message):
    uid = message.chat.id
    pid = active_chats[uid] # Partner's ID
    
    if message.text:
        try:
            # This detects the language and translates it for the partner
            translated = translator.translate(message.text, dest='hi').text # Example: translate to Hindi
            final_msg = f"🌐 {translated}\n---\n{message.text}"
            bot.send_message(pid, final_msg)
        except:
            bot.send_message(pid, message.text)

bot.infinity_polling()
    
