import os, telebot, random, time, threading
from telebot import types
from pymongo import MongoClient
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from flask import Flask
from datetime import datetime, timedelta

# 1. Infrastructure
app = Flask('')
@app.route('/')
def home(): return "WorldChat Master is Online 🚀"
def run_web(): app.run(host='0.0.0.0', port=8080)

# 2. Configuration
load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_URI'))
db = client['worldchat_master_db']
users_col = db['users']
ADMIN_ID = 8186837510 

active_pairs, searching_users, last_msg_time = {}, [], {}

def get_user(user_id, name="User", referrer=None):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {"user_id": user_id, "name": name, "balance": 500, "lang": "en", "last_bonus": datetime.now() - timedelta(days=1)}
        users_col.insert_one(user)
        if referrer:
            users_col.update_one({"user_id": int(referrer)}, {"$inc": {"balance": 500}})
            try: bot.send_message(referrer, f"🎊 *Referral!* +500 coins! 💰", parse_mode="Markdown")
            except: pass
    return user

# --- COMMANDS ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != uid else None
    get_user(uid, message.from_user.first_name, ref)
    bot.reply_to(message, "🌟 *WORLDCHAT MASTER*\n\n🔍 `/find` | 🛑 `/stop` | 👤 `/profile` | 🎲 `/dice [amt]`\n📢 `/referral` | 🌐 `/setlang` | 🎁 `/daily`", parse_mode="Markdown")

@bot.message_handler(commands=['find'])
def find_partner(message):
    uid = message.from_user.id
    if uid in active_pairs: return bot.reply_to(message, "❌ Already in chat!")
    if searching_users:
        p_id = searching_users.pop(0)
        if p_id == uid: return
        active_pairs[uid], active_pairs[p_id] = p_id, uid
        u_d, p_d = get_user(uid), get_user(p_id)
        intro = lambda d: f"👤 {d.get('name','Stranger')} ({d.get('age','??')}, {d.get('gender','Unknown')})"
        bot.send_message(uid, f"✅ *Connected!*\n{intro(p_d)}", parse_mode="Markdown")
        bot.send_message(p_id, f"✅ *Connected!*\n{intro(u_d)}", parse_mode="Markdown")
    else:
        if uid not in searching_users: searching_users.append(uid)
        bot.reply_to(message, "🔍 Searching...")

@bot.message_handler(commands=['stop'])
def stop_chat(message):
    if message.from_user.id in active_pairs:
        p_id = active_pairs.pop(message.from_user.id)
        active_pairs.pop(p_id, None)
        bot.send_message(message.from_user.id, "🛑 Ended.")
        bot.send_message(p_id, "🛑 Partner left.")

# --- GAMING SYSTEM ---
@bot.message_handler(commands=['dice'])
def dice_game(message):
    uid, u = message.from_user.id, get_user(message.from_user.id)
    try:
        amt = int(message.text.split()[1])
        if amt > u['balance'] or amt <= 0: return bot.reply_to(message, "❌ Not enough coins!")
        b, r = random.randint(1,6), random.randint(1,6)
        res = "WON! 🎉" if r > b else ("LOST! 💀" if r < b else "DRAW! 🤝")
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt if r > b else (-amt if r < b else 0)}})
        bot.reply_to(message, f"🎲 You: {r} | Bot: {b}\n*{res}*", parse_mode="Markdown")
    except: bot.reply_to(message, "Usage: `/dice 100`")

# --- TRANSLATION RELAY ---
@bot.message_handler(content_types=['text', 'photo', 'video', 'voice'])
def relay(message):
    uid = message.from_user.id
    if uid in active_pairs:
        p_id = active_pairs[uid]
        p_lang = get_user(p_id)['lang']
        if message.content_type == 'text':
            t = GoogleTranslator(source='auto', target=p_lang).translate(message.text)
            bot.send_message(p_id, f"🌐 {t}")
        elif message.content_type == 'photo': bot.send_photo(p_id, message.photo[-1].file_id)
        elif message.content_type == 'video': bot.send_video(p_id, message.video.file_id)
        elif message.content_type == 'voice': bot.send_voice(p_id, message.voice.file_id)

# --- PROFILE SETUP ---
@bot.message_handler(commands=['profile'])
def profile(m):
    msg = bot.send_message(m.chat.id, "👤 Name?")
    bot.register_next_step_handler(msg, lambda m: bot.register_next_step_handler(bot.send_message(m.chat.id, f"Age?"), save_prof, m.text))

def save_prof(m, name):
    users_col.update_one({"user_id": m.from_user.id}, {"$set": {"name": name, "age": m.text}}, upsert=True)
    bot.send_message(m.chat.id, "✅ Saved!")

@bot.message_handler(commands=['daily'])
def daily(m):
    u = get_user(m.from_user.id)
    if datetime.now() - u.get('last_bonus', datetime.now()) >= timedelta(days=1):
        users_col.update_one({"user_id": m.from_user.id}, {"$inc": {"balance": 100}, "$set": {"last_bonus": datetime.now()}})
        bot.reply_to(m, "🎁 +100 Coins!")
    else: bot.reply_to(m, "⏳ Come back tomorrow!")

@bot.message_handler(commands=['referral'])
def ref(m):
    bot.reply_to(m, f"🔗 `https://t.me/{bot.get_me().username}?start={m.from_user.id}`\nEarn 500 coins!", parse_mode="Markdown")

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
