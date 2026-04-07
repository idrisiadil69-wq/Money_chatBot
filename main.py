import os
import time
import random
from flask import Flask
from threading import Thread
import telebot
from telebot import types
from pymongo import MongoClient
from deep_translator import GoogleTranslator

# --- [1. CONFIG] ---
API_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI') 
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

# Threaded=False buttons ki reliability ke liye best hai
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML', threaded=False)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000, maxPoolSize=50, retryWrites=True)
    db = client['worldchat_master']
    users = db['users']
except Exception as e:
    print(f"DB Error: {e}")

# --- [2. KEEP-ALIVE SERVER] ---
app = Flask('')
@app.route('/')
def home(): return "Grand Master Status: Active 🚀"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- [3. DATABASE UTILS] ---
def get_user(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, "coins": 100, "status": "idle", "partner": None,
            "gender": "Unknown", "is_vip": False, "lang": "en", "last_daily": 0
        }
        users.insert_one(user)
    return user

# --- [4. START COMMAND] ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    u_id = message.chat.id
    get_user(u_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    # Buttons definition
    btn_start = types.InlineKeyboardButton("🔍 Start Chat", callback_data="start_chat")
    btn_daily = types.InlineKeyboardButton("🎁 Daily Coins", callback_data="daily_coins")
    btn_stats = types.InlineKeyboardButton("📊 My Stats", callback_data="stats")
    btn_stop = types.InlineKeyboardButton("❌ Stop Chat", callback_data="stop_chat")
    btn_vip = types.InlineKeyboardButton("🌟 Buy VIP", callback_data="buy_vip_menu")
    
    markup.add(btn_start, btn_daily, btn_stats, btn_stop, btn_vip)
    bot.send_message(u_id, "<b>🌟 WorldChat Master 🌟</b>\nSelect an option to begin:", reply_markup=markup)

# --- [5. BUTTONS (CALLBACK) HANDLER - FIXED] ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    u_id = call.from_user.id
    user = get_user(u_id)
    
    # CRITICAL: Har button click ko "Acknowledge" karna zaroori hai
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    if call.data == "start_chat":
        if user.get('partner'):
            bot.send_message(u_id, "⚠️ You are already in a chat!")
            return
            
        bot.send_message(u_id, "🔎 Searching for a partner...")
        query = {"user_id": {"$ne": u_id}, "partner": None, "status": "idle"}
        
        # VIP Gender Filter
        if user.get('is_vip') and user.get('gender') != "Unknown":
            query["gender"] = "Female" if user['gender'] == "Male" else "Male"

        match = users.find_one_and_update(query, {"$set": {"partner": u_id, "status": "chatting"}})
        if match:
            users.update_one({"user_id": u_id}, {"$set": {"partner": match['user_id'], "status": "chatting"}})
            bot.send_message(u_id, "✅ <b>Connected!</b> Say Hi.")
            bot.send_message(match['user_id'], "✅ <b>Connected!</b> Say Hi.")
        else:
            users.update_one({"user_id": u_id}, {"$set": {"status": "idle"}})
            bot.send_message(u_id, "⏳ Finding someone... Please wait.")

    elif call.data == "daily_coins":
        now = time.time()
        if now - user.get('last_daily', 0) < 86400:
            bot.send_message(u_id, "❌ Already claimed today!")
        else:
            reward = random.randint(50, 150)
            users.update_one({"user_id": u_id}, {"$inc": {"coins": reward}, "$set": {"last_daily": now}})
            bot.send_message(u_id, f"🎁 You received {reward} coins!")

    elif call.data == "stats":
        vip = "Yes ⭐" if user.get('is_vip') else "No"
        bot.send_message(u_id, f"📊 <b>Your Stats</b>\n\n💰 Coins: {user['coins']}\n⭐ VIP: {vip}\n🆔 ID: <code>{u_id}</code>")

    elif call.data == "buy_vip_menu":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Pay via UPI (₹99)", callback_data="pay_now"))
        bot.send_message(u_id, "<b>🌟 VIP Membership</b>\n- Unlocks Gender Filter\n- 5000 Bonus Coins\n\nPrice: ₹99", reply_markup=markup)

    elif call.data == "pay_now":
        bot.send_message(u_id, "Send ₹99 to: <code>worldchat@upi</code>\nEnter 12-digit UTR ID:")
        bot.register_next_step_handler_by_chat_id(u_id, verify_payment)

    elif call.data == "stop_chat":
        if user.get('partner'):
            p_id = user['partner']
            users.update_many({"user_id": {"$in": [u_id, p_id]}}, {"$set": {"partner": None, "status": "idle"}})
            bot.send_message(u_id, "❌ Chat ended.")
            bot.send_message(p_id, "❌ Partner disconnected.")
        else:
            bot.send_message(u_id, "You are not in a chat.")

def verify_payment(message):
    utr = message.text
    if utr and len(utr) == 12 and utr.isdigit():
        users.update_one({"user_id": message.from_user.id}, {"$set": {"is_vip": True}, "$inc": {"coins": 5000}})
        bot.send_message(message.chat.id, "✅ <b>VIP Activated!</b> Enjoy your perks.")
    else:
        bot.send_message(message.chat.id, "❌ Invalid UTR. Use /buy_vip to try again.")

# --- [6. CHAT RELAY & TRANSLATE] ---
@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'voice', 'animation'])
def relay_handler(message):
    user = get_user(message.from_user.id)
    if not user.get('partner'): return
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

# --- [7. ADMIN DASH] ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    total = users.count_documents({})
    vips = users.count_documents({"is_vip": True})
    bot.send_message(message.chat.id, f"📊 <b>Admin Dashboard</b>\n\nTotal Users: {total}\nVIP Members: {vips}\nIncome: ₹{vips*99}")

# --- [8. RUN BOT] ---
def run_bot():
    bot.remove_webhook()
    print("Bot is starting... 🚀")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    Thread(target=run_web).start()
    run_bot()
    
