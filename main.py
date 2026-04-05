import os
import telebot
import random
from telebot import types
from pymongo import MongoClient, DESCENDING
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from flask import Flask
from threading import Thread
from datetime import datetime

# 1. Infrastructure Setup (Keeps bot alive on Render)
app = Flask('')
@app.route('/')
def home(): return "WorldChat Ultimate Royal is Online 🚀👑"
def run_web(): app.run(host='0.0.0.0', port=8080)

# 2. Configuration & Database
load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
client = MongoClient(os.getenv('MONGO_URI'))
db = client['worldchat_final_db']
users_col = db['users']

# !!! IMPORTANT: REPLACE 123456789 WITH YOUR REAL TELEGRAM ID !!!
ADMIN_ID = 8186837510 

# Global state for Anonymous Chat pairing
active_pairs = {}
searching_users = []

# 3. Database Helper
def get_user(user_id, name="User"):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id, 
            "name": name, 
            "balance": 500, 
            "lang": "hi", 
            "vip": False,
            "joined": datetime.now().strftime("%Y-%m-%d")
        }
        users_col.insert_one(user)
    return user

# --- COMMANDS ---

@bot.message_handler(commands=['start'])
def start(message):
    get_user(message.from_user.id, message.from_user.first_name)
    msg = (
        "🌟 *WELCOME TO WORLDCHAT ULTIMATE* 🌟\n\n"
        "🎮 `/dice [amount]` - Bet coins on a roll\n"
        "🔍 `/find` - Chat with a random stranger\n"
        "🛑 `/stop` - End the random chat\n"
        "👑 `/buy` - Purchase Coins or VIP Crown\n"
        "👤 `/profile` - See your stats & coins\n"
        "🏆 `/top` - Global Leaderboard\n"
        "━━━━━━━━━━━━━━\n"
        "💬 *Send any text to translate it!*"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

# --- VIP & SHOP (AUTO-PAYMENT VIA TELEGRAM STARS) ---

@bot.message_handler(commands=['buy'])
def buy_menu(message):
    # Invoice for Coins
    bot.send_invoice(
        message.chat.id, "💰 5,000 WorldCoins", "Refill your balance to play games!", 
        "coins_pack", "", "XTR", [types.LabeledPrice(label="5,000 Coins", amount=50)]
    )
    # Invoice for VIP Crown
    bot.send_invoice(
        message.chat.id, "👑 VIP Crown Status", "Get a permanent Crown icon & Badge!", 
        "vip_pack", "", "XTR", [types.LabeledPrice(label="VIP Crown 👑", amount=150)]
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def payment_success(message):
    uid = message.from_user.id
    payload = message.successful_payment.invoice_payload
    if payload == "coins_pack":
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": 5000}})
        bot.send_message(uid, "✅ *Payment Success!* 5,000 coins added to your wallet. 💰", parse_mode="Markdown")
    elif payload == "vip_pack":
        users_col.update_one({"user_id": uid}, {"$set": {"vip": True}})
        bot.send_message(uid, "🎊 *CONGRATULATIONS!* You are now a VIP with a 👑 Crown!", parse_mode="Markdown")

# --- ADMIN POWER COMMANDS ---

@bot.message_handler(commands=['makevip'])
def manual_vip(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        users_col.update_one({"user_id": target_id}, {"$set": {"vip": True}})
        bot.reply_to(message, f"✅ User {target_id} is now a VIP! 👑")
        bot.send_message(target_id, "👑 *The Admin has granted you VIP status!*", parse_mode="Markdown")
    except: bot.reply_to(message, "Usage: `/makevip [User_ID]`")

@bot.message_handler(commands=['unvip'])
def remove_vip(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        users_col.update_one({"user_id": target_id}, {"$set": {"vip": False}})
        bot.reply_to(message, f"❌ VIP removed from {target_id}")
    except: bot.reply_to(message, "Usage: `/unvip [User_ID]`")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace('/broadcast ', '')
    all_users = users_col.find()
    count = 0
    for u in all_users:
        try:
            bot.send_message(u['user_id'], f"📢 *ANNOUNCEMENT:*\n\n{text}", parse_mode="Markdown")
            count += 1
        except: continue
    bot.reply_to(message, f"✅ Sent to {count} users.")

# --- SOCIAL & LEADERBOARD ---

@bot.message_handler(commands=['top'])
def leaderboard(message):
    top_users = users_col.find().sort("balance", DESCENDING).limit(10)
    text = "🏆 *WORLD LEADERBOARD*\n━━━━━━━━━━━━━━\n"
    for i, u in enumerate(top_users, 1):
        icon = "👑" if u.get('vip') else "👤"
        text += f"{i}. {icon} {u.get('name', 'User')} - {u['balance']} 💰\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['profile'])
def profile(message):
    u = get_user(message.from_user.id)
    badge = "👑 VIP MEMBER" if u.get('vip') else "🆓 FREE USER"
    bot.reply_to(message, f"👤 *{u.get('name')}*\n✨ {badge}\n💰 Wallet: {u['balance']} coins", parse_mode="Markdown")

# --- ANONYMOUS CHAT LOGIC ---

@bot.message_handler(commands=['find'])
def find_partner(message):
    uid = message.from_user.id
    if uid in active_pairs:
        bot.reply_to(message, "❌ Already in chat! Use /stop.")
        return
    if searching_users:
        partner_id = searching_users.pop(0)
        active_pairs[uid] = partner_id
        active_pairs[partner_id] = uid
        bot.send_message(uid, "✅ *Connected!* Messages are translated. Say hello!")
        bot.send_message(partner_id, "✅ *Connected!* Messages are translated. Say hello!")
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
        bot.send_message(p_id, "🛑 Your partner ended the chat.")
    else: bot.reply_to(message, "You are not in a chat.")

# --- DICE GAMBLING ---

@bot.message_handler(commands=['dice'])
def play_dice(message):
    uid = message.from_user.id
    user = get_user(uid)
    try:
        amt = int(message.text.split()[1])
        if amt > user['balance'] or amt <= 0:
            bot.reply_to(message, "❌ Insufficient coins!")
            return
        b_roll, u_roll = random.randint(1, 6), random.randint(1, 6)
        if u_roll > b_roll:
            users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
            bot.reply_to(message, f"🎲 Me: {b_roll} | You: {u_roll}\n🎉 *YOU WON {amt} COINS!*")
        elif u_roll < b_roll:
            users_col.update_one({"user_id": uid}, {"$inc": {"balance": -amt}})
            bot.reply_to(message, f"🎲 Me: {b_roll} | You: {u_roll}\n💀 *YOU LOST {amt} COINS!*")
        else: bot.reply_to(message, "🤝 Draw! No coins lost.")
    except: bot.reply_to(message, "Usage: `/dice 100`")

# --- AUTO-TRANSLATION & RELAY ---

@bot.message_handler(func=lambda m: True)
def relay_text(message):
    uid = message.from_user.id
    # If in anonymous chat, relay with translation
    if uid in active_pairs:
        p_id = active_pairs[uid]
        p_data = get_user(p_id)
        target = p_data.get('lang', 'hi')
        trans = GoogleTranslator(source='auto', target=target).translate(message.text)
        bot.send_message(p_id, f"💬: {trans}")
    else:
        # Default solo translation
        u_data = get_user(uid)
        trans = GoogleTranslator(source='auto', target=u_data.get('lang', 'hi')).translate(message.text)
        bot.reply_to(message, trans)

# 5. Boot System
if __name__ == "__main__":
    Thread(target=run_web).start()
    bot.infinity_polling()
