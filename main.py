import os
import time
import random
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import telebot
from telebot import types
from pymongo import MongoClient
from deep_translator import GoogleTranslator

# --- INITIALIZATION ---
API_TOKEN = os.getenv('BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
LOG_GROUP_ID = int(os.getenv('LOG_GROUP_ID', 0))

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
client = MongoClient(MONGO_URI)
db = client['worldchat_master']
users = db['users']

# --- FLASK KEEP-ALIVE ---
app = Flask('')
@app.route('/')
def home(): return "WorldChat Master is Live 🚀"
def run_web(): app.run(host='0.0.0.0', port=8080)

# --- DATABASE & UTILITY LOGIC ---
def get_user(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, "name": "Guest", "age": 18, "gender": "Unknown",
            "coins": 100, "is_vip": False, "lang": "en", "partner": None,
            "referred_by": None, "daily_msgs": 0, "daily_photos": 0,
            "last_reset": datetime.now(), "reports": 0, "last_daily": 0, "bio": ""
        }
        users.insert_one(user)
    
    # Daily Limit Reset Logic
    if (datetime.now() - user.get('last_reset', datetime.now())).days >= 1:
        users.update_one({"user_id": user_id}, {"$set": {"daily_msgs": 0, "daily_photos": 0, "last_reset": datetime.now()}})
        user['daily_msgs'], user['daily_photos'] = 0, 0
        
    return user

def translate_msg(text, target):
    try: return GoogleTranslator(source='auto', target=target).translate(text)
    except: return text

# --- CORE MATCHMAKING ---
@bot.message_handler(func=lambda m: m.text == "🔍 Find Partner")
def start_search(message):
    u_id = message.from_user.id
    user = get_user(u_id)
    
    if user['partner']: return bot.send_message(u_id, "❌ You are already in a chat!")

    # 40-Second Penalty for Low Rating/Reported Users
    if user['reports'] > 3:
        bot.send_message(u_id, "⚠️ <b>System Penalty:</b> Due to reports, your search will take 40 seconds...")
        time.sleep(40)

    bot.send_message(u_id, "🔎 Searching for a partner...")
    
    # Matchmaking Logic
    match = users.find_one({
        "user_id": {"$ne": u_id},
        "partner": None,
        "gender": {"$ne": "Unknown"} # Basic filter
    })

    if match:
        # Accept/Decline Logic
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Accept ✅", callback_data=f"acc_{match['user_id']}"),
                   types.InlineKeyboardButton("Decline ❌", callback_data=f"dec_{match['user_id']}"))
        bot.send_message(u_id, f"Match Found! <b>{match['name']}</b> ({match['age']}). Accept?", reply_markup=markup)
    else:
        bot.send_message(u_id, "No one found yet. Stay in the queue!")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('acc_', 'dec_')))
def handle_request(call):
    u_id = call.from_user.id
    target_id = int(call.data.split('_')[1])
    
    if "acc" in call.data:
        users.update_one({"user_id": u_id}, {"$set": {"partner": target_id}})
        users.update_one({"user_id": target_id}, {"$set": {"partner": u_id}})
        bot.send_message(u_id, "✅ Connected! Use /stop to end.")
        bot.send_message(target_id, "✅ Connected! Use /stop to end.")
    else:
        bot.send_message(u_id, "❌ Match declined.")

# --- 3D GAMES ---
@bot.message_handler(commands=['dice', 'basketball', 'slots'])
def play_game(message):
    user = get_user(message.from_user.id)
    if user['coins'] < 20: return bot.send_message(message.chat.id, "Need 20 coins!")
    
    users.update_one({"user_id": user['user_id']}, {"$inc": {"coins": -20}})
    
    emoji_map = {'dice': '🎲', 'basketball': '🏀', 'slots': '🎰'}
    game = message.text.replace('/', '')
    res = bot.send_dice(message.chat.id, emoji=emoji_map.get(game, '🎲'))
    
    # Winning Logic
    if res.dice.value >= 4:
        users.update_one({"user_id": user['user_id']}, {"$inc": {"coins": 60}})
        bot.reply_to(message, "🔥 <b>YOU WON!</b> +60 Coins.")
    else:
        bot.reply_to(message, "💀 You lost 20 coins.")

# --- CHAT & LIMITS ---
@bot.message_handler(content_types=['text', 'photo'])
def chat_handler(message):
    user = get_user(message.from_user.id)
    if not user['partner']: return
    
    partner = get_user(user['partner'])

    # Non-VIP Limits
    if not user['is_vip']:
        if message.text and user['daily_msgs'] >= 50:
            return bot.send_message(user['user_id'], "🚫 Daily limit of 50 messages reached! Upgrade to VIP.")
        if message.photo and user['daily_photos'] >= 5:
            return bot.send_message(user['user_id'], "🚫 Daily limit of 5 photos reached!")

    # Message Routing
    if message.text:
        translated = translate_msg(message.text, partner['lang'])
        bot.send_message(partner['user_id'], f"💬 {translated}")
        users.update_one({"user_id": user['user_id']}, {"$inc": {"daily_msgs": 1}})
        
    elif message.photo:
        bot.send_photo(partner['user_id'], message.photo[-1].file_id, caption="📸 New Photo")
        users.update_one({"user_id": user['user_id']}, {"$inc": {"daily_photos": 1}})

# --- REFERRAL & DAILY ---
@bot.message_handler(commands=['daily'])
def daily_bonus(message):
    user = get_user(message.from_user.id)
    now = time.time()
    if now - user['last_daily'] < 86400: return bot.reply_to(message, "Come back tomorrow!")
    
    reward = random.randint(100, 200)
    users.update_one({"user_id": user['user_id']}, {"$inc": {"coins": reward}, "$set": {"last_daily": now}})
    bot.reply_to(message, f"🎁 You claimed {reward} coins!")

@bot.message_handler(commands=['referral'])
def ref_link(message):
    link = f"https://t.me/{(bot.get_me()).username}?start={message.from_user.id}"
    bot.send_message(message.chat.id, f"🔗 Invite friends and get 500 coins!\nYour link: {link}")

# --- ADMIN TOOLS ---
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    msg_text = message.text.replace('/broadcast ', '')
    for u in users.find():
        try: bot.send_message(u['user_id'], f"📢 <b>Announcement:</b>\n\n{msg_text}")
        except: pass

# --- START THREADS ---
def run_bot():
    while True:
        try: bot.polling(none_stop=True)
        except Exception: time.sleep(5)

if __name__ == "__main__":
    Thread(target=run_web).start()
    run_bot()
