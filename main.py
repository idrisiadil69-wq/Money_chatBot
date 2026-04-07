import os
import time
import random
from datetime import datetime
from flask import Flask
from threading import Thread
import telebot
from telebot import types
from pymongo import MongoClient
from deep_translator import GoogleTranslator

# --- [CORE SETTINGS] ---
API_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI') 
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# Threaded=False yahan Conflict error ko kam karne mein madad karega
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML', threaded=False)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, maxPoolSize=50, retryWrites=True)
    db = client['worldchat_master']
    users = db['users']
except Exception as e:
    print(f"DB Error: {e}")

# --- [WEB SERVER] ---
app = Flask('')
@app.route('/')
def home(): return "Grand Master Status: Online 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- [DATABASE UTILS] ---
def get_user(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, "coins": 100, "status": "idle", "partner": None,
            "gender": "Unknown", "is_vip": False, "lang": "en", "last_daily": 0
        }
        users.insert_one(user)
    return user

# --- [VIP & PAYMENT] ---
@bot.message_handler(commands=['buy_vip'])
def buy_vip_cmd(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Pay via UPI (₹99)", callback_data="pay_now"))
    bot.send_message(message.chat.id, "<b>🌟 VIP Membership</b>\n- Priority Match\n- Gender Filter\n- 5000 Coins\n\nPrice: ₹99", reply_markup=markup)

def verify_payment_step(message):
    utr = message.text
    if utr and len(utr) == 12 and utr.isdigit():
        users.update_one({"user_id": message.from_user.id}, {"$set": {"is_vip": True}, "$inc": {"coins": 5000}})
        bot.send_message(message.chat.id, "✅ <b>VIP Activated!</b>")
    else:
        bot.send_message(message.chat.id, "❌ Invalid ID. Use /buy_vip to try again.")

# --- [GENDER SETTINGS] ---
@bot.message_handler(commands=['set_gender'])
def set_gender_cmd(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Male 👦", "Female 👧")
    bot.send_message(message.chat.id, "Select your gender:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Male 👦", "Female 👧"])
def save_gender(message):
    gender = "Male" if "Male" in message.text else "Female"
    users.update_one({"user_id": message.from_user.id}, {"$set": {"gender": gender}})
    bot.send_message(message.chat.id, f"✅ Gender set to {gender}!", reply_markup=types.ReplyKeyboardRemove())

# --- [NAVIGATION] ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    u_id = message.chat.id
    get_user(u_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔍 Start Chat", callback_data="start_chat"),
        types.InlineKeyboardButton("🎁 Daily Coins", callback_data="daily_coins"),
        types.InlineKeyboardButton("📊 My Stats", callback_data="stats"),
        types.InlineKeyboardButton("❌ Stop Chat", callback_data="stop_chat")
    )
    bot.send_message(u_id, "<b>🌟 WorldChat Master 🌟</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    u_id = call.from_user.id
    user = get_user(u_id)
    bot.answer_callback_query(call.id)

    if call.data == "pay_now":
        bot.send_message(u_id, "Send ₹99 to: <code>worldchat@upi</code>\nEnter 12-digit UTR:")
        bot.register_next_step_handler(call.message, verify_payment_step)

    elif call.data == "start_chat":
        if user.get('partner'): return bot.send_message(u_id, "⚠️ Already in chat!")
        bot.send_message(u_id, "🔎 Searching...")
        
        query = {"user_id": {"$ne": u_id}, "partner": None, "status": "idle"}
        if user.get('is_vip') and user.get('gender') != "Unknown":
            query["gender"] = "Female" if user['gender'] == "Male" else "Male"

        match = users.find_one_and_update(query, {"$set": {"partner": u_id, "status": "chatting"}})
        if match:
            users.update_one({"user_id": u_id}, {"$set": {"partner": match['user_id'], "status": "chatting"}})
            bot.send_message(u_id, "✅ Connected!")
            bot.send_message(match['user_id'], "✅ Connected!")
        else:
            users.update_one({"user_id": u_id}, {"$set": {"status": "idle"}})
            bot.send_message(u_id, "⏳ Finding partner...")

    elif call.data == "daily_coins":
        if time.time() - user.get('last_daily', 0) < 86400:
            bot.send_message(u_id, "❌ Already claimed!")
        else:
            reward = random.randint(50, 150)
            users.update_one({"user_id": u_id}, {"$inc": {"coins": reward}, "$set": {"last_daily": time.time()}})
            bot.send_message(u_id, f"🎁 Got {reward} coins!")

    elif call.data == "stats":
        bot.send_message(u_id, f"💰 Coins: {user['coins']}\n⭐ VIP: {'Yes' if user['is_vip'] else 'No'}")

    elif call.data == "stop_chat":
        if user.get('partner'):
            p_id = user['partner']
            users.update_many({"user_id": {"$in": [u_id, p_id]}}, {"$set": {"partner": None, "status": "idle"}})
            bot.send_message(u_id, "❌ Chat ended.")
            bot.send_message(p_id, "❌ Partner disconnected.")

# --- [CHAT RELAY & TRANSLATE] ---
@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'voice', 'animation', 'video_note'])
def relay_handler(message):
    user = get_user(message.from_user.id)
    if not user or not user.get('partner'): return
    p_id = user['partner']
    partner = get_user(p_id)

    try:
        if message.text:
            translated = GoogleTranslator(source='auto', target=partner.get('lang', 'en')).translate(message.text)
            bot.send_message(p_id, f"💬 {translated}")
        elif message.photo: bot.send_photo(p_id, message.photo[-1].file_id, caption=message.caption)
        elif message.video: bot.send_video(p_id, message.video.file_id, caption=message.caption)
        elif message.sticker: bot.send_sticker(p_id, message.sticker.file_id)
        elif message.animation: bot.send_animation(p_id, message.animation.file_id)
        elif message.voice: bot.send_voice(p_id, message.voice.file_id)
    except:
        users.update_many({"user_id": {"$in": [message.from_user.id, p_id]}}, {"$set": {"partner": None, "status": "idle"}})

# --- [ADMIN DASHBOARD] ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    total = users.count_documents({})
    vips = users.count_documents({"is_vip": True})
    bot.send_message(message.chat.id, f"📊 <b>Admin Dash</b>\n\nUsers: {total}\nVIPs: {vips}\nIncome: ₹{vips*99}")

# --- [RUN] ---
def run_bot():
    bot.remove_webhook()
    print("Bot is starting...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    Thread(target=run_web).start()
    run_bot()
    
