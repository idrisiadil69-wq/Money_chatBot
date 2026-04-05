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
def home(): return "WorldChat Master is Online 🚀🌐🔒"
def run_web(): app.run(host='0.0.0.0', port=8080)

# 2. Configuration & Database
load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_URI'))
db = client['worldchat_master_db']
users_col = db['users']

# !!! YOUR ADMIN ID !!!
ADMIN_ID = 8186837510 

# Global state for Pairing & Anti-Spam
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
            "lang": "en", # Default to English
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
        "🌟 *WORLDCHAT MASTER EDITION* 🌟\n\n"
        "🔍 `/find` - Match with a stranger\n"
        "🛑 `/stop` - End the chat\n"
        "📢 `/invite` - Earn 500 coins per friend\n"
        "🌐 `/setlang` - Change your language\n"
        "🎁 `/daily` - Get 100 free coins\n"
        "🎮 `/dice [amt]` | 👤 `/profile` | 🏆 `/top`\n"
        "━━━━━━━━━━━━━━\n"
        "✨ *Tip: All messages are auto-translated!*"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['invite'])
def invite(message):
    uid = message.from_user.id
    link = f"https://t.me/{bot.get_me().username}?start={uid}"
    markup = types.InlineKeyboardMarkup()
    share_url = f"https://t.me/share/url?url={link}&text=Chat with strangers globally! 🌎"
    markup.add(types.InlineKeyboardButton("🔗 Share Link", url=share_url))
    bot.reply_to(message, f"📢 *Your Referral Link:*\n`{link}`\n\nGet 500 coins for every friend!", reply_markup=markup, parse_mode="Markdown")

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

# --- CORE CHAT & TRANSLATION RELAY ---

@bot.message_handler(commands=['find'])
def find_partner(message):
    uid = message.from_user.id
    if uid in active_pairs: return bot.reply_to(message, "❌ You are already in a chat!")
    if searching_users:
        p_id = searching_users.pop(0)
        active_pairs[uid], active_pairs[p_id] = p_id, uid
        bot.send_message(uid, "✅ *Connected!* Typing will translate automatically.")
        bot.send_message(p_id, "✅ *Connected!* Typing will translate automatically.")
    else:
        searching_users.append(uid)
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
    # Anti-Spam
    now = time.time()
    if uid in last_msg_time and now - last_msg_time[uid] < 0.7: return
    last_msg_time[uid] = now

    if uid in active_pairs:
        p_id = active_pairs[uid]
        p_data = get_user(p_id)
        lang_label = "Hindi 🇮🇳" if p_data['lang'] == 'hi' else "English 🇺🇸"

        if message.content_type == 'text':
            # Translate and add the "Translation Tag"
            trans = GoogleTranslator(source='auto', target=p_data['lang']).translate(message.text)
            header = f"🌐 *Translated to {lang_label}:*\n"
            bot.send_message(p_id, f"{header}{trans}", protect_content=True, parse_mode="Markdown")
        
        # Multimedia relay with Privacy Shield
        elif message.content_type == 'voice': bot.send_voice(p_id, message.voice.file_id, protect_content=True)
        elif message.content_type == 'video_note': bot.send_video_note(p_id, message.video_note.file_id, protect_content=True)
        elif message.content_type == 'photo': bot.send_photo(p_id, message.photo[-1].file_id, protect_content=True)
        elif message.content_type == 'document': bot.send_document(p_id, message.document.file_id, protect_content=True)
        elif message.content_type == 'video': bot.send_video(p_id, message.video.file_id, protect_content=True)
    else:
        # Solo translation outside of chat
        if message.content_type == 'text':
            u_data = get_user(uid)
            trans = GoogleTranslator(source='auto', target=u_data['lang']).translate(message.text)
            bot.reply_to(message, trans)

# --- GAMES, BONUSES & ADMIN ---

@bot.message_handler(commands=['daily'])
def daily(message):
    uid = message.from_user.id
    u = get_user(uid)
    if datetime.now() - u.get('last_bonus', datetime.now() - timedelta(days=1)) >= timedelta(days=1):
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": 100}, "$set": {"last_bonus": datetime.now()}})
        bot.reply_to(message, "🎁 +100 Coins! See you tomorrow.")
    else: bot.reply_to(message, "⏳ Already claimed! Come back later.")

@bot.message_handler(commands=['dice'])
def dice(message):
    uid, u = message.from_user.id, get_user(message.from_user.id)
    try:
        amt = int(message.text.split()[1])
        if amt > u['balance'] or amt <= 0: return bot.reply_to(message, "❌ Not enough coins!")
        b, r = random.randint(1,6), random.randint(1,6)
        res = "WON! 🎉" if r > b else ("LOST! 💀" if r < b else "DRAW! 🤝")
        change = amt if r > b else (-amt if r < b else 0)
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": change}})
        bot.reply_to(message, f"🎲 You: {r} | Bot: {b}\n*{res}*", parse_mode="Markdown")
    except: bot.reply_to(message, "Usage: `/dice 100`")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace('/broadcast ', '')
    for u in users_col.find():
        try: bot.send_message(u['user_id'], f"📢 *ANNOUNCEMENT:*\n\n{text}", parse_mode="Markdown")
        except: continue

if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()

# --- ADDED COMMANDS ---

@bot.message_handler(commands=['referral'])
def referral_menu(message):
    referral_link = f"https://t.me/Worldchat_bot?start={message.chat.id}"
    bot.reply_to(message, f"🔗 *Invite friends to WorldChat!*\n\nYour personal link:\n`{referral_link}`\n\nFor every friend you bring, you earn *500 coins*! 💰", parse_mode="Markdown")

@bot.message_handler(commands=['vip'])
def vip_menu(message):
    bot.reply_to(message, "💎 *WorldChat VIP Status*\n\nComing soon! VIP members will get:\n✅ Filter partners by country\n✅ Unlimited daily coins\n✅ Ad-free experience\n\nStay tuned for updates! 🚀", parse_mode="Markdown")
    
