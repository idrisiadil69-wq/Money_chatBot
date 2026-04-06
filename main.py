import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from googletrans import Translator
import time, threading
import os

# ===== LOAD SECRETS =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
UPI_ID = os.environ.get("UPI_ID")
VIP_PRICE = int(os.environ.get("VIP_PRICE"))

COIN_COST_PER_CHAT = 1
REFERRAL_REWARD = 5
DAILY_COINS = 5
VIP_DURATION_DAYS = 30

bot = telebot.TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URL)
db = client["dating_bot"]
users = db["users"]
earnings = db["earnings"]
translator = Translator()

# Persistent queues & active chats
waiting_males = db["waiting_males"]
waiting_females = db["waiting_females"]
active_chats = db["active_chats"]

# Rate-limiting & daily claim tracking
user_last_msg_time = {}
daily_claims = {}

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
            "banned": False
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
        InlineKeyboardButton("🎮 Stats / Game", callback_data="stats")
    )
    return m

def vip_admin_menu(uid):
    m = InlineKeyboardMarkup()
    m.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"vip_approve_{uid}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"vip_reject_{uid}")
    )
    return m

def language_menu():
    m = InlineKeyboardMarkup(row_width=2)
    langs = [("English","en"),("Hindi","hi"),("Spanish","es"),("French","fr"),("German","de")]
    for name, code in langs:
        m.add(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
    return m

# ===== START / BIO =====
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.from_user.id
    user = get_user(uid)
    args = msg.text.split()

    # Referral system
    if len(args) > 1:
        try:
            ref_id = int(args[1])
            if ref_id != uid and not users.find_one({"id": uid, "ref_claimed": True}):
                increment_user(ref_id, "coins", REFERRAL_REWARD)
                increment_user(ref_id, "referrals", 1)
                update_user(uid, {"ref_claimed": True})
                bot.send_message(ref_id, f"🎁 Referral bonus! +{REFERRAL_REWARD} coins.")
        except: pass

    if not user["gender"]:
        bot.send_message(uid, "👋 Welcome! Select your gender:", reply_markup=gender_menu())
    else:
        bot.send_message(uid, "🔥 Main Menu", reply_markup=main_menu(uid))

@bot.message_handler(commands=["bio"])
def set_bio(msg):
    uid = msg.from_user.id
    new_bio = msg.text.replace("/bio ", "").strip()
    if not 1 <= len(new_bio) <= 100:
        return bot.send_message(uid, "⚠️ Bio must be 1-100 characters.")
    update_user(uid, {"bio": new_bio})
    bot.send_message(uid, f"✅ Bio updated:\n_{new_bio}_", parse_mode="Markdown")

# ===== CHAT SYSTEM =====
def start_chat(uid):
    user = get_user(uid)
    if user["banned"]:
        return bot.send_message(uid, "🚫 You are banned.")
    if str(uid) in active_chats:
        return bot.send_message(uid, "⚠️ Already in chat!")
    if not user["is_vip"] and user["coins"] < COIN_COST_PER_CHAT:
        return bot.send_message(uid, "❌ Not enough coins!")

    # Queues
    gender = user["gender"]
    target_list = waiting_females.find_one({"queue": []})["queue"] if gender=="M" else waiting_males.find_one({"queue": []})["queue"]
    my_list = waiting_males.find_one({"queue": []})["queue"] if gender=="M" else waiting_females.find_one({"queue": []})["queue"]

    # Searching
    if uid in my_list: return bot.send_message(uid, "⏳ Still searching...")
    if target_list:
        partner_id = target_list.pop(0)
        # Update active chats
        active_chats[str(uid)] = partner_id
        active_chats[str(partner_id)] = uid
        # Deduct coins
        if not user["is_vip"]: increment_user(uid, "coins", -COIN_COST_PER_CHAT)
        partner_user = get_user(partner_id)
        bot.send_message(uid, f"💘 Matched!\nBio: {partner_user['bio']}", parse_mode="Markdown")
        bot.send_message(partner_id, f"💘 Matched!\nBio: {user['bio']}", parse_mode="Markdown")
    else:
        my_list.append(uid)
        bot.send_message(uid, "🔎 Searching for a partner...")

# ===== CALLBACK HANDLER =====
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    uid = call.from_user.id
    data = call.data
    user = get_user(uid)

    # Gender selection
    if data.startswith("set_"):
        update_user(uid, {"gender": data.split("_")[1]})
        bot.send_message(uid, "✅ Gender set!", reply_markup=main_menu(uid))

    # Chat control
    elif data=="chat": start_chat(uid)
    elif data=="next":
        if str(uid) in active_chats:
            pid = active_chats[str(uid)]
            del active_chats[str(uid)], active_chats[str(pid)]
            bot.send_message(pid, "❌ Partner skipped.")
        start_chat(uid)
    elif data=="stop":
        if str(uid) in active_chats:
            pid = active_chats[str(uid)]
            del active_chats[str(uid)], active_chats[str(pid)]
            bot.send_message(uid, "❌ Chat ended.")
            bot.send_message(pid, "❌ Chat ended.")

    # Daily coins
    elif data=="daily":
        today = int(time.time()//86400)
        last_claim = users.find_one({"id": uid}).get("last_daily", 0)
        if last_claim==today: bot.answer_callback_query(call.id, "❌ Already claimed today!")
        else:
            increment_user(uid, "coins", DAILY_COINS)
            update_user(uid, {"last_daily": today})
            bot.send_message(uid, f"✅ {DAILY_COINS} coins added!")

    # Referral
    elif data=="refer":
        link = f"https://t.me/{bot.get_me().username}?start={uid}"
        bot.send_message(uid, f"🎁 Invite friends and get {REFERRAL_REWARD} coins!\n`{link}`", parse_mode="Markdown")

    # Translate toggle
    elif data=="translate":
        update_user(uid, {"translate": not user["translate"]})
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=main_menu(uid))

    # VIP
    elif data=="vip":
        bot.send_message(uid, f"💎 Upgrade to VIP:\n• Unlimited chats\n• No coin deduction\n\nPay ₹{VIP_PRICE} to `{UPI_ID}`\nSend screenshot with caption 'VIP'", parse_mode="Markdown")

    # Language selection
    elif data=="language": bot.send_message(uid, "Select your language:", reply_markup=language_menu())
    elif data.startswith("lang_"):
        code = data.split("_")[1]
        update_user(uid, {"lang": code})
        bot.send_message(uid, f"🌐 Language set to {code.upper()}", reply_markup=main_menu(uid))

    # Admin VIP approval
    elif data.startswith("vip_approve_") and uid==ADMIN_ID:
        target = int(data.split("_")[2])
        expiry = int(time.time() + VIP_DURATION_DAYS*86400)
        update_user(target, {"is_vip": True, "vip_expiry": expiry})
        bot.send_message(target, "✅ VIP Activated!")
        bot.edit_message_text("VIP approved", ADMIN_ID, call.message.message_id)
    elif data.startswith("vip_reject_") and uid==ADMIN_ID:
        target = int(data.split("_")[2])
        bot.send_message(target, "❌ VIP Rejected")
        bot.edit_message_text("VIP rejected", ADMIN_ID, call.message.message_id)

    # Report system
    elif data=="report":
        if str(uid) in active_chats:
            pid = active_chats[str(uid)]
            bot.send_message(ADMIN_ID, f"🚨 Report\nReporter: {uid}\nReported: {pid}")
            bot.send_message(uid, "✅ Report sent!")
        else: bot.send_message(uid, "❌ You must be in chat to report.")

    # Game stats
    elif data=="stats":
        u = get_user(uid)
        vip_status = "Active ✅" if u["is_vip"] else "Inactive ❌"
        msg = f"🎮 Your Stats:\n🪙 Coins: {u['coins']}\n💎 VIP: {vip_status}\n🎁 Referrals: {u['referrals']}"
        bot.send_message(uid, msg, reply_markup=main_menu(uid))

# ===== MESSAGE RELAY =====
@bot.message_handler(content_types=['text','photo','video','voice','sticker'])
def relay(msg):
    uid = msg.from_user.id
    now = time.time()
    if uid in user_last_msg_time and now - user_last_msg_time[uid]<1: return
    user_last_msg_time[uid] = now

    user = get_user(uid)
    if user.get("banned"): return

    # VIP screenshot
    if msg.content_type=='photo' and str(uid) not in active_chats:
        caption = (msg.caption or "").lower()
        if "vip" in caption:
            bot.forward_message(ADMIN_ID, uid, msg.message_id)
            bot.send_message(ADMIN_ID, f"VIP Payment from {uid}", reply_markup=vip_admin_menu(uid))
            bot.send_message(uid, "⏳ Payment received. Admin will verify.")
            return

    # Relay messages
    if str(uid) in active_chats:
        pid = active_chats[str(uid)]
        partner = get_user(pid)
        # Text
        if msg.text:
            text_to_send = msg.text
            if partner["translate"]:
                try:
                    translated = translator.translate(msg.text, dest=partner["lang"])
                    text_to_send = f"{translated.text}\n\n—\n_Original: {msg.text}_"
                except: pass
            bot.send_message(pid, text_to_send, parse_mode="Markdown")
        # Photo
        elif msg.content_type=='photo': bot.send_photo(pid, msg.photo[-1].file_id, caption=msg.caption)
        # Video
        elif msg.content_type=='video': bot.send_video(pid, msg.video.file_id, caption=msg.caption)
        # Voice
        elif msg.content_type=='voice': bot.send_voice(pid, msg.voice.file_id)
        # Sticker
        elif msg.content_type=='sticker': bot.send_sticker(pid, msg.sticker.file_id)
    else:
        bot.send_message(uid, "❌ You are not in chat.", reply_markup=main_menu(uid))

# ===== VIP EXPIRY CHECK =====
def vip_expiry_checker():
    while True:
        now = int(time.time())
        users.update_many({"is_vip": True, "vip_expiry": {"$lt": now}}, {"$set": {"is_vip": False}})
        time.sleep(3600)

threading.Thread(target=vip_expiry_checker, daemon=True).start()

print("Bot is running...")
bot.infinity_polling()
