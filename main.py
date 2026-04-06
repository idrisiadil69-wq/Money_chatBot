import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from googletrans import Translator
import time, threading
import os

# ===== LOAD SECRETS =====
# Use .get() with defaults to prevent immediate crashing
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
UPI_ID = os.environ.get("UPI_ID", "your_upi@id")
VIP_PRICE = int(os.environ.get("VIP_PRICE", 100))

COIN_COST_PER_CHAT = 1
REFERRAL_REWARD = 5
DAILY_COINS = 5
VIP_DURATION_DAYS = 30

bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URL)
db = client["dating_bot"]
users = db["users"]

# We use a single document to manage queues to avoid "NoneType" errors
queues = db["queues"]

# Initialize queues if they don't exist
if not queues.find_one({"type": "global"}):
    queues.insert_one({"type": "global", "males": [], "females": []})

# In-memory active chats (For a production bot, move this to MongoDB)
active_chats = {} 
user_last_msg_time = {}

translator = Translator()

# ===== DATABASE FUNCTIONS =====
def get_user(uid):
    user = users.find_one({"id": uid})
    if not user:
        user = {
            "id": uid,
            "gender": None,
            "bio": "No bio set",
            "coins": 10,
            "referrals": 0,
            "is_vip": False,
            "vip_expiry": 0,
            "lang": "en",
            "translate": True,
            "banned": False,
            "last_daily": 0
        }
        users.insert_one(user)
    return user

def update_user(uid, data):
    users.update_one({"id": uid}, {"$set": data})

def increment_user(uid, field, amount):
    users.update_one({"id": uid}, {"$inc": {field: amount}})

# ===== KEYBOARDS =====
def gender_menu():
    m = InlineKeyboardMarkup()
    m.add(
        InlineKeyboardButton("👨 Male", callback_data="set_M"),
        InlineKeyboardButton("👩 Female", callback_data="set_F")
    )
    return m

def main_menu(uid):
    u = get_user(uid)
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("💬 Start Chat", callback_data="chat"),
        InlineKeyboardButton("🔄 Next", callback_data="next"),
        InlineKeyboardButton(f"🪙 Coins: {u['coins']}", callback_data="coins"),
        InlineKeyboardButton("🎁 Daily Coins", callback_data="daily"),
        InlineKeyboardButton("🎁 Refer", callback_data="refer"),
        InlineKeyboardButton(f"🌍 Translate: {'ON' if u['translate'] else 'OFF'}", callback_data="translate"),
        InlineKeyboardButton("💎 VIP", callback_data="vip"),
        InlineKeyboardButton("🛑 Stop", callback_data="stop"),
        InlineKeyboardButton("🌐 Language", callback_data="language"),
        InlineKeyboardButton("🚨 Report", callback_data="report"),
        InlineKeyboardButton("🎮 Stats", callback_data="stats")
    )
    return m

# ===== CHAT LOGIC (FIXED) =====
def start_chat(uid):
    user = get_user(uid)
    if user["banned"]:
        return bot.send_message(uid, "🚫 You are banned.")
    if str(uid) in active_chats:
        return bot.send_message(uid, "⚠️ Already in chat!")
    if not user["is_vip"] and user["coins"] < COIN_COST_PER_CHAT:
        return bot.send_message(uid, "❌ Not enough coins! Use /refer or /daily.")

    gender = user["gender"]
    q_doc = queues.find_one({"type": "global"})
    males = q_doc["males"]
    females = q_doc["females"]

    # Prevent double-queueing
    if uid in males or uid in females:
        return bot.send_message(uid, "🔎 Still searching for a partner...")

    target_queue = females if gender == "M" else males
    my_queue_name = "males" if gender == "M" else "females"

    if target_queue:
        partner_id = target_queue.pop(0)
        # Update DB Queues
        queues.update_one({"type": "global"}, {"$set": {"males": males, "females": females}})
        
        # Link them
        active_chats[str(uid)] = partner_id
        active_chats[str(partner_id)] = uid
        
        if not user["is_vip"]: increment_user(uid, "coins", -COIN_COST_PER_CHAT)
        
        p_user = get_user(partner_id)
        bot.send_message(uid, f"💘 Matched!\nBio: {p_user['bio']}", reply_markup=main_menu(uid))
        bot.send_message(partner_id, f"💘 Matched!\nBio: {user['bio']}", reply_markup=main_menu(partner_id))
    else:
        queues.update_one({"type": "global"}, {"$push": {my_queue_name: uid}})
        bot.send_message(uid, "🔎 Searching for a partner... please wait.")

# ===== HANDLERS =====
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.from_user.id
    user = get_user(uid)
    
    # Simple referral check
    if " " in msg.text:
        ref_id = msg.text.split()[1]
        if ref_id.isdigit() and int(ref_id) != uid and not user.get("ref_claimed"):
            increment_user(int(ref_id), "coins", REFERRAL_REWARD)
            update_user(uid, {"ref_claimed": True})
            bot.send_message(int(ref_id), "🎁 Someone joined via your link! +5 coins.")

    if not user["gender"]:
        bot.send_message(uid, "👋 Welcome! Select your gender:", reply_markup=gender_menu())
    else:
        bot.send_message(uid, "🔥 Welcome Back!", reply_markup=main_menu(uid))

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.from_user.id
    if call.data.startswith("set_"):
        g = call.data.split("_")[1]
        update_user(uid, {"gender": g})
        bot.edit_message_text("✅ Gender saved!", call.message.chat.id, call.message.message_id, reply_markup=main_menu(uid))
    
    elif call.data == "chat":
        start_chat(uid)
    
    elif call.data == "stop":
        if str(uid) in active_chats:
            pid = active_chats.pop(str(uid))
            active_chats.pop(str(pid), None)
            bot.send_message(uid, "🛑 Chat ended.", reply_markup=main_menu(uid))
            bot.send_message(pid, "🛑 Your partner ended the chat.", reply_markup=main_menu(pid))
        else:
            bot.answer_callback_query(call.id, "You aren't in a chat.")

@bot.message_handler(content_types=['text', 'photo'])
def handle_relay(msg):
    uid = msg.from_user.id
    if str(uid) in active_chats:
        pid = active_chats[str(uid)]
        if msg.text:
            # Simple relay without translation first to ensure it works
            bot.send_message(pid, f"💬: {msg.text}")
        elif msg.photo:
            bot.send_photo(pid, msg.photo[-1].file_id, caption=msg.caption)
    else:
        bot.send_message(uid, "❌ Not in a chat. Click 'Start Chat'", reply_markup=main_menu(uid))

# Start the bot
print("Bot Started...")
bot.infinity_polling()
