import os, telebot, threading
from telebot import types
from pymongo import MongoClient
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from flask import Flask
from datetime import datetime, timedelta

# ------------------ KEEP ALIVE ------------------
app = Flask('')
@app.route('/')
def home():
    return "WorldChat Ultimate Live 🚀"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# ------------------ CONFIG ------------------
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MONGO = os.getenv("MONGO_URI")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing")

bot = telebot.TeleBot(TOKEN)
client = MongoClient(MONGO)
db = client["worldchat_ultimate"]

users = db["users"]
likes = db["likes"]

users.create_index("user_id", unique=True)

ADMIN_ID = 8186837510  # 🔴 PUT YOUR TELEGRAM ID

# ------------------ GLOBAL ------------------
active_pairs = {}
searching = []

# ------------------ MENU ------------------
def menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("💬 Start", callback_data="start"),
        types.InlineKeyboardButton("🔄 Next", callback_data="next"),
        types.InlineKeyboardButton("🪙 Coins", callback_data="coins"),
        types.InlineKeyboardButton("❤️ Match", callback_data="match"),
        types.InlineKeyboardButton("🎁 Refer", callback_data="refer"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("🛑 Stop", callback_data="stop")
    )
    return m

# ------------------ FAKE USERS ------------------
def add_fake_users():
    fake = [
        {"user_id": 9001, "name": "Riya", "age": "19", "gender": "Girl"},
        {"user_id": 9002, "name": "Anjali", "age": "21", "gender": "Girl"},
        {"user_id": 9003, "name": "Priya", "age": "20", "gender": "Girl"}
    ]
    for f in fake:
        if not users.find_one({"user_id": f["user_id"]}):
            users.insert_one({
                "user_id": f["user_id"],
                "name": f["name"],
                "age": f["age"],
                "gender": f["gender"],
                "balance": 1000,
                "lang": "en",
                "premium": False,
                "last_bonus": datetime.now() - timedelta(days=1)
            })

add_fake_users()

# ------------------ USER ------------------
def get_user(uid, name="User", ref=None):
    user = users.find_one({"user_id": uid})
    if not user:
        user = {
            "user_id": uid,
            "name": name,
            "age": "??",
            "gender": "Not Set",
            "balance": 1000,
            "lang": "en",
            "premium": False,
            "free_chats": 0,
            "last_bonus": datetime.now() - timedelta(days=1)
        }
        users.insert_one(user)

        if ref and str(ref).isdigit() and int(ref) != uid:
            users.update_one({"user_id": int(ref)}, {"$inc": {"balance": 500}})
            try:
                bot.send_message(ref, "🎉 Referral Bonus +500 coins")
            except:
                pass
    return user

# ------------------ START ------------------
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.from_user.id
    args = msg.text.split()
    ref = args[1] if len(args) > 1 else None

    get_user(uid, msg.from_user.first_name, ref)

    bot.send_message(uid,
        "🔥 *Welcome to Secret Chat*\n\n"
        "😈 Talk to strangers privately\n"
        "❤️ Find girlfriend/boyfriend\n"
        "💬 Unlimited anonymous chat\n\n"
        "🚀 Press START below",
        parse_mode="Markdown",
        reply_markup=menu()
    )

# ------------------ MATCHMAKING ------------------
def find_partner(uid):
    u = get_user(uid)

    if not u.get("premium"):
        if u.get("free_chats", 0) >= 3:
            bot.send_message(uid, "🚫 Free limit reached! Buy Premium 💎")
            return

    if uid in active_pairs:
        bot.send_message(uid, "❌ Already chatting")
        return

    if searching:
        p = searching.pop(0)
        if p == uid:
            return

        active_pairs[uid] = p
        active_pairs[p] = uid

        users.update_one({"user_id": uid}, {"$inc": {"free_chats": 1}})

        bot.send_message(uid, "✅ Connected!")
        bot.send_message(p, "✅ Connected!")

        bot.send_message(uid, "🔥 Many girls are online now!\nUpgrade to Premium for faster matches 💎")

    else:
        searching.append(uid)
        bot.send_message(uid, "🔍 Searching...")

def stop_chat(uid):
    if uid in active_pairs:
        p = active_pairs.pop(uid)
        active_pairs.pop(p, None)

        bot.send_message(uid, "🛑 Chat ended")
        bot.send_message(p, "❌ Partner left")

# ------------------ TINDER MATCH ------------------
def show_profile(uid):
    other = users.find_one({"user_id": {"$ne": uid}})
    if not other:
        bot.send_message(uid, "❌ No users found")
        return

    m = types.InlineKeyboardMarkup()
    m.add(
        types.InlineKeyboardButton("❤️ Like", callback_data=f"like_{other['user_id']}"),
        types.InlineKeyboardButton("❌ Skip", callback_data="skip")
    )

    bot.send_message(uid, f"👤 {other['name']} ({other['age']})", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith("like_"))
def like_user(call):
    uid = call.from_user.id
    target = int(call.data.split("_")[1])

    likes.insert_one({"from": uid, "to": target})

    if likes.find_one({"from": target, "to": uid}):
        active_pairs[uid] = target
        active_pairs[target] = uid

        bot.send_message(uid, "❤️ MATCH! Start chatting!")
        bot.send_message(target, "❤️ MATCH! Start chatting!")
    else:
        bot.send_message(uid, "👍 Liked!")

# ------------------ BUTTONS ------------------
@bot.callback_query_handler(func=lambda c: True)
def buttons(call):
    uid = call.from_user.id

    if call.data == "start":
        find_partner(uid)

    elif call.data == "next":
        stop_chat(uid)
        find_partner(uid)

    elif call.data == "stop":
        stop_chat(uid)

    elif call.data == "coins":
        u = get_user(uid)
        bot.send_message(uid, f"🪙 Coins: {u['balance']}")

    elif call.data == "refer":
        link = f"https://t.me/{bot.get_me().username}?start={uid}"
        bot.send_message(uid, f"🔗 Invite:\n{link}")

    elif call.data == "premium":
        bot.send_message(uid,
            "💎 *Premium Benefits*\n\n"
            "🔥 Chat with girls first\n"
            "🚀 Faster matching\n"
            "💬 No waiting\n"
            "❤️ Unlimited matches\n\n"
            "💰 Price: ₹49 only\n\n"
            "UPI: yourupi@upi\nSend screenshot after payment",
            parse_mode="Markdown"
        )

    elif call.data == "match":
        show_profile(uid)

# ------------------ PAYMENT ------------------
@bot.message_handler(content_types=['photo'])
def payment(msg):
    users.update_one({"user_id": msg.from_user.id},
                     {"$set": {"payment_pending": True}})

    bot.send_message(ADMIN_ID, f"💰 Payment request from {msg.from_user.id}")

@bot.message_handler(commands=['approve'])
def approve(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    uid = int(msg.text.split()[1])

    users.update_one({"user_id": uid},
                     {"$set": {"premium": True, "payment_pending": False}})

    bot.send_message(uid, "💎 Premium Activated!")

# ------------------ DAILY ------------------
@bot.message_handler(commands=['daily'])
def daily(msg):
    u = get_user(msg.from_user.id)

    if datetime.now() - u['last_bonus'] >= timedelta(days=1):
        users.update_one({"user_id": msg.from_user.id},
                         {"$inc": {"balance": 200},
                          "$set": {"last_bonus": datetime.now()}})
        bot.reply_to(msg, "🎁 +200 coins added")
    else:
        bot.reply_to(msg, "⏳ Come tomorrow")

# ------------------ LEADERBOARD ------------------
@bot.message_handler(commands=['top'])
def top(msg):
    top_users = users.find().sort("balance", -1).limit(5)

    text = "🏆 Top Users:\n"
    for i, u in enumerate(top_users, 1):
        text += f"{i}. {u['name']} - {u['balance']}\n"

    bot.send_message(msg.chat.id, text)

# ------------------ CHAT ------------------
@bot.message_handler(content_types=['text'])
def chat(msg):
    uid = msg.from_user.id

    if uid in active_pairs:
        p = active_pairs[uid]
        lang = get_user(p).get("lang", "en")

        try:
            t = GoogleTranslator(source='auto', target=lang).translate(msg.text)
        except:
            t = msg.text

        bot.send_message(p, f"🌐 {t}")

# ------------------ RUN ------------------
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    print("Bot running...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
