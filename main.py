import os
import telebot
import random
import time
from telebot import types
from pymongo import MongoClient, DESCENDING
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# 1. Infrastructure (Render Keep-Alive)
app = Flask('')
@app.route('/')
def home(): return "WorldChat Master is Online 🚀"
def run_web(): app.run(host='0.0.0.0', port=8080)

# 2. Configuration & Database
load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_URI'))
db = client['worldchat_master_db']
users_col = db['users']

ADMIN_ID = 8186837510 

# Global state
active_pairs = {}
searching_users = []
last_msg_time = {}

def get_user(user_id, name="User", referrer=None):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, 
            "name": name, 
            "balance": 500, 
            "lang": "en",
            "vip": False,
            "last_bonus": datetime.now() - timedelta(days=1),
            "referred_by": referrer
        }
        users_col.insert_one(user)
        if referrer:
            users_col.update_one({"user_id": int(referrer)}, {"$inc": {"balance": 500}})
            try: bot.send_message(referrer, f"🎊 *Referral!* {name} joined. +500 coins! 💰", parse_mode="Markdown")
            except: pass
    return user

# --- COMMANDS ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    referrer = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
    get_user(uid, message.from_user.first_name, referrer)
    msg = (
        "🌟 *WORLDCHAT MASTER* 🌟\n\n"
        "🔍 `/find` - Match with a stranger\n"
        "🛑 `/stop` - End the chat\n"
        "👤 `/profile` - Set Name/Age/Gender\n"
        "📢 `/referral` - Earn 500 coins\n"
        "🌐 `/setlang` - Change language\n"
        "🎁 `/daily` - Free coins\n"
        "━━━━━━━━━━━━━━\n"
        "✨ *Messages translate automatically!*"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setlang'])
def set_lang(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"),
               types.InlineKeyboardButton("Hindi 🇮🇳", callback_data="lang_hi"))
    bot.reply_to(message, "🌐 *Select your language:*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def lang_call(call):
    new_lang = call.data.split("_")[1]
    users_col.update_one({"user_id": call.from_user.id}, {"$set": {"lang": new_lang}})
    bot.answer_callback_query(call.id, f"Language set to {new_lang.upper()}")
    bot.edit_message_text(f"✅ Your language is now: *{new_lang.upper()}*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- CORE CHAT LOGIC ---

@bot.message_handler(commands=['find'])
def find_partner(message):
    uid = message.from_user.id
    if uid in active_pairs: return bot.reply_to(message, "❌ Already in a chat!")
    
    if searching_users:
        p_id = searching_users.pop(0)
        if p_id == uid: return # Don't match with self
        active_pairs[uid], active_pairs[p_id] = p_id, uid
        
        u_data, p_data = get_user(uid), get_user(p_id)
        
        def get_intro(d):
            return f"👤 {d.get('name','Stranger')} ({d.get('age','??')}, {d.get('gender','Unknown')})"

        bot.send_message(uid, f"✅ *Connected!*\nTalking to: {get_intro(p_data)}\n\nType to chat (Auto-translated) 🌐", parse_mode="Markdown")
        bot.send_message(p_id, f"✅ *Connected!*\nTalking to: {get_intro(u_data)}\n\nType to chat (Auto-translated) 🌐", parse_mode="Markdown")
    else:
        if uid not in searching_users: searching_users.append(uid)
        bot.reply_to(message, "🔍 Searching for a partner...")

@bot.message_handler(commands=['stop'])
def stop_chat(message):
    uid = message.from_user.id
    if uid in active_pairs:
        p_id = active_pairs.pop(uid)
        active_pairs.pop(p_id, None)
        bot.send_message(uid, "🛑 Chat ended.")
        bot.send_message(p_id, "🛑 Partner left the chat.")
    else: bot.reply_to(message, "You aren't in a chat.")

@bot.message_handler(content_types=['text', 'voice', 'video_note', 'photo', 'document', 'video', 'audio'])
def master_relay(message):
    uid = message.from_user.id
    now = time.time()
    if uid in last_msg_time and now - last_msg_time[uid] < 0.7: return
    last_msg_time[uid] = now

    if uid in active_pairs:
        p_id = active_pairs[uid]
        p_data = get_user(p_id)
        if message.content_type == 'text':
            trans = GoogleTranslator(source='auto', target=p_data['lang']).translate(message.text)
            bot.send_message(p_id, f"🌐 {trans}", protect_content=True)
        elif message.content_type == 'voice': bot.send_voice(p_id, message.voice.file_id, protect_content=True)
        elif message.content_type == 'photo': bot.send_photo(p_id, message.photo[-1].file_id, protect_content=True)
        elif message.content_type == 'video': bot.send_video(p_id, message.video.file_id, protect_content=True)
    else:
        if message.content_type == 'text':
            u_data = get_user(uid)
            trans = GoogleTranslator(source='auto', target=u_data['lang']).translate(message.text)
            bot.reply_to(message, trans)

# --- PROFILE SETUP ---

@bot.message_handler(commands=['profile'])
def start_profile(message):
    msg = bot.send_message(message.chat.id, "👤 What is your **Name**?")
    bot.register_next_step_handler(msg, get_name)

def get_name(message):
    name = message.text
    msg = bot.send_message(message.chat.id, f"Nice to meet you, {name}! How **old** are you?")
    bot.register_next_step_handler(msg, get_age, name)

def get_age(message, name):
    age = message.text
    if not age.isdigit():
        msg = bot.send_message(message.chat.id, "Enter a number for age:")
        bot.register_next_step_handler(msg, get_age, name)
        return
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('Male', 'Female', 'Other')
    msg = bot.send_message(message.chat.id, "What is your **Gender**?", reply_markup=markup)
    bot.register_next_step_handler(msg, save_profile, name, age)

def save_profile(message, name, age):
    gender = message.text
    users_col.update_one({"user_id": message.from_user.id}, {"$set": {"name": name, "age": int(age), "gender": gender}}, upsert=True)
    bot.send_message(message.chat.id, f"✅ **Profile Saved!**", reply_markup=types.ReplyKeyboardRemove())

# --- EXTRA COMMANDS ---

@bot.message_handler(commands=['referral'])
def referral_menu(message):
    link = f"https://t.me/{bot.get_me().username}?start={message.from_user.id}"
    bot.reply_to(message, f"🔗 *Invite Link:*\n`{link}`\n\nEarn 500 coins per friend!", parse_mode="Markdown")

@bot.message_handler(commands=['vip'])
def vip_menu(message):
    bot.reply_to(message, "💎 *VIP Status*\n\n✅ Filter by Gender\n✅ Filter by Country\n\nPrice: 500 Stars", parse_mode="Markdown")

@bot.message_handler(commands=['daily'])
def daily(message):
    uid = message.from_user.id
    u = get_user(uid)
    if datetime.now() - u.get('last_bonus', datetime.now() - timedelta(days=1)) >= timedelta(days=1):
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": 100}, "$set": {"last_bonus": datetime.now()}})
        bot.reply_to(message, "🎁 +100 Coins!")
    else: bot.reply_to(message, "⏳ Already claimed today.")

# --- START BOT ---
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
            
