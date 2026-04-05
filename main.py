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

# 1. Infrastructure
app = Flask('')
@app.route('/')
def home(): return "WorldChat Viral-God is Online 🚀🔥🔒"
def run_web(): app.run(host='0.0.0.0', port=8080)

# 2. Config
load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_URI'))
db = client['worldchat_viral_db']
users_col = db['users']

ADMIN_ID = 8186837510 

# Global state
active_pairs = {}
searching_users = []
last_msg_time = {}

# 3. Database & Referral Logic
def get_user(user_id, name="User", referrer=None):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, 
            "name": name, 
            "balance": 500, 
            "lang": "hi", 
            "vip": False,
            "last_bonus": datetime.now() - timedelta(days=1),
            "referred_by": referrer
        }
        users_col.insert_one(user)
        
        # If this is a new user from a referral, pay the referrer
        if referrer:
            users_col.update_one({"user_id": int(referrer)}, {"$inc": {"balance": 500}})
            try:
                bot.send_message(referrer, f"🎊 *Referral Success!* {name} joined. You earned 500 coins! 💰", parse_mode="Markdown")
            except: pass
    return user

# --- REFERRAL & SHARE COMMAND ---

@bot.message_handler(commands=['invite'])
def invite_friends(message):
    uid = message.from_user.id
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={uid}"
    
    markup = types.InlineKeyboardMarkup()
    # This button opens the Telegram "Forward/Share" menu
    share_url = f"https://t.me/share/url?url={referral_link}&text=Hey! Join this Anonymous Chat bot and earn coins! 👑"
    markup.add(types.InlineKeyboardButton("🔗 Share with Friends", url=share_url))
    
    text = (
        "📢 *INVITE & EARN*\n\n"
        "Share your link with friends. When they join, you get **500 coins** instantly!\n\n"
        f"Your Link: `{referral_link}`"
    )
    bot.reply_to(message, text, reply_markup=markup, parse_mode="Markdown")

# --- CORE LOGIC ---

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    args = message.text.split()
    referrer = None
    
    # Check if user clicked a referral link
    if len(args) > 1 and args[1].isdigit():
        if int(args[1]) != uid: # Prevent self-referral
            referrer = int(args[1])

    get_user(uid, message.from_user.first_name, referrer)
    
    msg = (
        "🌟 *WORLDCHAT VIRAL EDITION* 🌟\n\n"
        "🎮 `/dice` | 🎁 `/daily` | 📢 `/invite`\n"
        "🔍 `/find` | 🛑 `/stop` | 🌐 `/setlang`\n"
        "👑 `/buy` | 👤 `/profile` | 🏆 `/top`\n"
        "━━━━━━━━━━━━━━\n"
        "💰 *EARN 500 COINS* for every friend you invite!"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

# --- SHOP, GAMES & ADMIN (REMAINS SAME) ---

@bot.message_handler(commands=['buy'])
def buy_menu(message):
    bot.send_invoice(message.chat.id, "💰 5k Coins", "Refill", "coins_pack", "", "XTR", [types.LabeledPrice(label="5k Coins", amount=50)])
    bot.send_invoice(message.chat.id, "👑 VIP Crown", "Badge", "vip_pack", "", "XTR", [types.LabeledPrice(label="VIP Crown", amount=150)])

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    uid = message.from_user.id
    payload = message.successful_payment.invoice_payload
    if payload == "coins_pack":
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": 5000}})
        bot.send_message(uid, "✅ 5,000 coins added!")
    elif payload == "vip_pack":
        users_col.update_one({"user_id": uid}, {"$set": {"vip": True}})
        bot.send_message(uid, "🎊 You are now a VIP 👑!")

@bot.message_handler(commands=['daily'])
def daily_bonus(message):
    uid = message.from_user.id
    user = get_user(uid)
    now = datetime.now()
    if now - user.get('last_bonus', now - timedelta(days=1)) >= timedelta(days=1):
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": 100}, "$set": {"last_bonus": now}})
        bot.reply_to(message, "🎁 +100 Coins Daily Bonus!")
    else: bot.reply_to(message, "⏳ Come back tomorrow!")

@bot.message_handler(commands=['setlang'])
def set_lang(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"),
               types.InlineKeyboardButton("Hindi 🇮🇳", callback_data="lang_hi"))
    bot.reply_to(message, "Select Language:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def lang_call(call):
    new_lang = call.data.split("_")[1]
    users_col.update_one({"user_id": call.from_user.id}, {"$set": {"lang": new_lang}})
    bot.answer_callback_query(call.id, f"Set to {new_lang}")

# --- PRIVACY CHAT RELAY ---

@bot.message_handler(commands=['find'])
def find_partner(message):
    uid = message.from_user.id
    if uid in active_pairs:
        bot.reply_to(message, "❌ Use /stop first.")
        return
    if searching_users:
        p_id = searching_users.pop(0)
        active_pairs[uid], active_pairs[p_id] = p_id, uid
        bot.send_message(uid, "✅ *Connected!* Privacy Shield On.")
        bot.send_message(p_id, "✅ *Connected!* Privacy Shield On.")
    else:
        searching_users.append(uid)
        bot.reply_to(message, "🔍 Searching...")

@bot.message_handler(commands=['stop'])
def stop_chat(message):
    uid = message.from_user.id
    if uid in active_pairs:
        p_id = active_pairs.pop(uid)
        active_pairs.pop(p_id, None)
        bot.send_message(uid, "🛑 Chat ended.")
        bot.send_message(p_id, "🛑 Chat ended.")

@bot.message_handler(content_types=['text', 'voice', 'video_note', 'photo', 'document', 'video', 'audio'])
def handle_relay(message):
    uid = message.from_user.id
    # Anti-Spam
    cur = time.time()
    if uid in last_msg_time and cur - last_msg_time[uid] < 0.7: return
    last_msg_time[uid] = cur

    if uid in active_pairs:
        p_id = active_pairs[uid]
        p_data = get_user(p_id)
        if message.content_type == 'text':
            trans = GoogleTranslator(source='auto', target=p_data['lang']).translate(message.text)
            bot.send_message(p_id, f"💬: {trans}", protect_content=True)
        elif message.content_type == 'voice': bot.send_voice(p_id, message.voice.file_id, protect_content=True)
        elif message.content_type == 'video_note': bot.send_video_note(p_id, message.video_note.file_id, protect_content=True)
        elif message.content_type == 'photo': bot.send_photo(p_id, message.photo[-1].file_id, protect_content=True)
        elif message.content_type == 'document': bot.send_document(p_id, message.document.file_id, protect_content=True)
        elif message.content_type == 'video': bot.send_video(p_id, message.video.file_id, protect_content=True)
    else:
        if message.content_type == 'text':
            u_data = get_user(uid)
            trans = GoogleTranslator(source='auto', target=u_data['lang']).translate(message.text)
            bot.reply_to(message, trans)

# --- GAMES & ADMIN ---

@bot.message_handler(commands=['dice'])
def dice(message):
    uid = message.from_user.id
    u = get_user(uid)
    try:
        amt = int(message.text.split()[1])
        if amt > u['balance'] or amt <= 0: return
        b, r = random.randint(1,6), random.randint(1,6)
        if r > b: users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        elif r < b: users_col.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})
        bot.reply_to(message, f"🎲 {r} vs {b}")
    except: pass

@bot.message_handler(commands=['top'])
def top(message):
    top_u = users_col.find().sort("balance", DESCENDING).limit(10)
    t = "🏆 *LEADERBOARD*\n"
    for i, x in enumerate(top_u, 1):
        icon = "👑" if x.get('vip') else "👤"
        t += f"{i}. {icon} {x.get('name')} - {x['balance']}\n"
    bot.reply_to(message, t, parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def bdc(message):
    if message.from_user.id != ADMIN_ID: return
    txt = message.text.replace('/broadcast ', '')
    for u in users_col.find():
        try: bot.send_message(u['user_id'], f"📢 {txt}")
        except: continue

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
