import os
import telebot
from pymongo import MongoClient

# Load variables from Koyeb settings
BOT_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')

client = MongoClient(MONGO_URI)
db = client['my_bot_db']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user = users_col.find_one({"user_id": user_id})
    if not user:
        users_col.insert_one({"user_id": user_id, "balance": 100})
        bot.reply_to(message, "Welcome! You've been given 100 coins.")
    else:
        bot.reply_to(message, f"Welcome back! Your balance is {user['balance']} coins.")

bot.infinity_polling()
