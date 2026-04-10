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
    # ========== KEYBOARDS ==========

def main_menu(user_id: int) -> InlineKeyboardMarkup:
    vip_badge = "👑 " if is_vip(user_id) else ""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(f"{vip_badge}🏠 Home", callback_data="home"),
        InlineKeyboardButton("💰 Earn Coins", callback_data="earn_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🎮 Play Games", callback_data="games_menu"),
        InlineKeyboardButton("💬 Chat/Dating", callback_data="chat_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🤖 AI Chat", callback_data="ai_menu"),
        InlineKeyboardButton("👑 VIP Upgrade", callback_data="vip_menu")
    )
    keyboard.add(
        InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        InlineKeyboardButton("📊 Profile", callback_data="profile")
    )
    keyboard.add(
        InlineKeyboardButton("🎯 Daily Tasks", callback_data="daily_tasks"),
        InlineKeyboardButton("🎡 Daily Spin", callback_data="daily_spin")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Back to Menu", callback_data="home"))
    return keyboard

def back_button() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Back to Menu", callback_data="home"))
    return kb

# ========== USER SYSTEM ==========

@bot.message_handler(commands=["start"])
def start_command(message: Message):
    user_id = message.from_user.id
    if not rate_limit(user_id):
        return bot.reply_to(message, "⏳ Slow down! Please wait a moment.")
    user = get_user(user_id)
    if not user:
        ref_id = None
        if len(message.text.split()) > 1:
            try:
                ref_id = int(message.text.split()[1])
                if ref_id == user_id:
                    ref_id = None
            except:
                pass
        create_user(user_id, message.from_user.username, message.from_user.first_name)
        if ref_id:
            users_col.update_one({"user_id": user_id}, {"$set": {"referral_id": ref_id}})
            update_coins(ref_id, 100, "Referral bonus")
            bot.send_message(ref_id, f"🎉 You got 100 coins from a new referral!")
        lang_kb = InlineKeyboardMarkup()
        lang_kb.add(InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton("🇮🇳 Hindi", callback_data="lang_hi"))
        bot.send_message(user_id, "🌍 <b>Welcome! Select your language:</b>", reply_markup=lang_kb, parse_mode="HTML")
    else:
        bot.send_message(user_id, "🏠 <b>Main Menu</b>", reply_markup=main_menu(user_id), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def set_language(call: CallbackQuery):
    lang = call.data.split("_")[1]
    users_col.update_one({"user_id": call.from_user.id}, {"$set": {"language": lang}})
    gender_kb = InlineKeyboardMarkup()
    gender_kb.add(InlineKeyboardButton("♂️ Male", callback_data="gender_male"), InlineKeyboardButton("♀️ Female", callback_data="gender_female"))
    bot.edit_message_text("👤 <b>Select your gender:</b>", call.message.chat.id, call.message.message_id, reply_markup=gender_kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("gender_"))
def set_gender(call: CallbackQuery):
    gender = call.data.split("_")[1]
    users_col.update_one({"user_id": call.from_user.id}, {"$set": {"gender": gender}})
    bot.edit_message_text("✅ Setup complete! Use /start to see main menu.", call.message.chat.id, call.message.message_id)
    bot.send_message(call.from_user.id, "🏠 <b>Main Menu</b>", reply_markup=main_menu(call.from_user.id), parse_mode="HTML")

# ========== PROFILE ==========

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def show_profile(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        bot.answer_callback_query(call.id, "Error loading profile")
        return
    vip_status = "✅ Active" if is_vip(call.from_user.id) else "❌ Inactive"
    text = f"""
📊 <b>Your Profile</b>
━━━━━━━━━━━━━━━
👤 Name: {user['name']}
🆔 ID: {user['user_id']}
💰 Coins: {user['coins']}
⭐ Level: {user['level']} (XP: {user['xp']}/{XP_PER_LEVEL*user['level']})
🏆 Wins: {user['wins']} / Losses: {user['losses']}
🎮 Games Played: {user['games_played']}
📈 Total Earnings: {user['total_earnings']}
🔥 Streak: {user['streak']} days
👑 VIP: {vip_status}
🤖 AI Usage: {user['ai_usage']} / {FREE_AI_LIMIT if not is_vip(call.from_user.id) else '∞'}
💼 Wallet: ₹{user['wallet_balance']}
    """
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")

# ========== COIN & ECONOMY ==========

@bot.callback_query_handler(func=lambda call: call.data == "earn_menu")
def earn_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus"))
    kb.add(InlineKeyboardButton("👥 Referral System", callback_data="referral"))
    kb.add(InlineKeyboardButton("📋 Daily Tasks", callback_data="daily_tasks"))
    kb.add(InlineKeyboardButton("🎡 Daily Spin", callback_data="daily_spin"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="home"))
    bot.edit_message_text("💰 <b>Earn Coins</b>\nChoose a method:", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "daily_bonus")
def daily_bonus(call: CallbackQuery):
    user = get_user(call.from_user.id)
    now = datetime.utcnow()
    last = user.get("last_daily")
    if last and (now - last).days < 1:
        remaining = timedelta(days=1) - (now - last)
        bot.answer_callback_query(call.id, f"Already claimed! Try again in {remaining.seconds//3600}h {(remaining.seconds//60)%60}m.")
        return
    bonus = VIP_DAILY_BONUS if is_vip(call.from_user.id) else DAILY_BONUS
    update_coins(call.from_user.id, bonus, "Daily bonus")
    if last and (now - last).days == 1:
        streak = user.get("streak", 0) + 1
        streak_bonus = min(streak * 10, 200)
        update_coins(call.from_user.id, streak_bonus, "Streak bonus")
        users_col.update_one({"user_id": call.from_user.id}, {"$set": {"streak": streak, "last_daily": now}})
        bot.send_message(call.from_user.id, f"🔥 Streak x{streak}! +{streak_bonus} bonus coins!")
    else:
        users_col.update_one({"user_id": call.from_user.id}, {"$set": {"streak": 1, "last_daily": now}})
    bot.answer_callback_query(call.id, f"+{bonus} coins claimed!")
    bot.edit_message_text(f"✅ Daily bonus claimed! +{bonus} coins.", call.message.chat.id, call.message.message_id, reply_markup=back_button())

@bot.callback_query_handler(func=lambda call: call.data == "referral")
def referral_info(call: CallbackQuery):
    link = f"https://t.me/{bot.get_me().username}?start={call.from_user.id}"
    text = f"👥 <b>Referral Program</b>\n\nInvite friends and earn 100 coins per referral!\n\nYour link:\n<code>{link}</code>\n\nShare this link with others."
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")
    # ========== GAMES ==========

@bot.callback_query_handler(func=lambda call: call.data == "games_menu")
def games_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎲 Dice Game", callback_data="game_dice"),
        InlineKeyboardButton("🎰 Slots", callback_data="game_slots"),
        InlineKeyboardButton("🔢 Guess Number", callback_data="game_guess"),
        InlineKeyboardButton("🪙 Coin Flip", callback_data="game_coinflip"),
        InlineKeyboardButton("💎 Jackpot", callback_data="game_jackpot"),
        InlineKeyboardButton("🏆 Game Leaderboard", callback_data="game_leaderboard")
    )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="home"))
    bot.edit_message_text("🎮 <b>Play Games & Earn Coins</b>\nSelect a game:", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

def play_game(user_id: int, game: str, bet: int) -> Tuple[bool, int]:
    user = get_user(user_id)
    if not user or user["coins"] < bet:
        return False, 0
    prob = GAME_PROBABILITIES.get(game, 0.3)
    win = random.random() < prob
    win_amount = 0
    if win:
        if game == "dice":
            win_amount = bet * 2
        elif game == "coinflip":
            win_amount = int(bet * 1.9)
        elif game == "slots":
            win_amount = bet * 3
        elif game == "guess":
            win_amount = bet * 2
        else:
            win_amount = bet * 2
        update_coins(user_id, win_amount, f"Game win {game}")
        users_col.update_one({"user_id": user_id}, {"$inc": {"wins": 1, "games_played": 1}})
        add_xp(user_id, 10)
    else:
        update_coins(user_id, -bet, f"Game loss {game}")
        users_col.update_one({"user_id": user_id}, {"$inc": {"losses": 1, "games_played": 1}})
        add_xp(user_id, 2)
    check_achievements(user_id)
    return win, win_amount

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def game_callback(call: CallbackQuery):
    game = call.data.split("_")[1]
    if game in ["dice", "slots", "guess", "coinflip"]:
        bot.answer_callback_query(call.id, "Send bet amount (min 10 coins)")
        bot.register_next_step_handler(call.message, process_game_bet, game, call.from_user.id)
    elif game == "jackpot":
        show_jackpot(call)
    elif game == "leaderboard":
        show_game_leaderboard(call)

def process_game_bet(message: Message, game: str, user_id: int):
    try:
        bet = int(message.text.strip())
        if bet < 10:
            bot.reply_to(message, "❌ Minimum bet is 10 coins.")
            return
        user = get_user(user_id)
        if user["coins"] < bet:
            bot.reply_to(message, "❌ Insufficient coins.")
            return
        win, win_amount = play_game(user_id, game, bet)
        result_text = "🎉 <b>You won!</b>" if win else "😞 <b>You lost!</b>"
        result_text += f"\nBet: {bet} coins\nWon: {win_amount} coins\nNew balance: {user['coins'] - bet + (win_amount if win else 0)}"
        bot.reply_to(message, result_text, parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "❌ Invalid amount. Send a number.")

def show_jackpot(call: CallbackQuery):
    jackpot = jackpot_col.find_one({"active": True}) or {"pool": 1000, "tickets": 0}
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"🎟️ Buy Ticket ({JACKPOT_TICKET_COST} coins)", callback_data="jackpot_buy"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="games_menu"))
    bot.edit_message_text(f"💎 <b>Jackpot</b>\nPool: {jackpot['pool']} coins\nTickets sold: {jackpot['tickets']}\nBuy a ticket for a chance to win!", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "jackpot_buy")
def buy_jackpot_ticket(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if user["coins"] < JACKPOT_TICKET_COST:
        bot.answer_callback_query(call.id, "Not enough coins!")
        return
    update_coins(call.from_user.id, -JACKPOT_TICKET_COST, "Jackpot ticket")
    jackpot = jackpot_col.find_one({"active": True})
    if not jackpot:
        jackpot = {"pool": 1000, "tickets": 0, "active": True}
        jackpot_col.insert_one(jackpot)
    jackpot_col.update_one({"_id": jackpot["_id"]}, {"$inc": {"pool": JACKPOT_TICKET_COST, "tickets": 1}})
    jackpot["tickets"] += 1
    if jackpot["tickets"] >= JACKPOT_DRAW_INTERVAL:
        winner = random.choice(list(users_col.find({"coins": {"$gt": 0}})))
        win_amount = int(jackpot["pool"] * 0.8)
        update_coins(winner["user_id"], win_amount, "Jackpot win")
        bot.send_message(winner["user_id"], f"🎉 <b>JACKPOT!</b> You won {win_amount} coins!", parse_mode="HTML")
        jackpot_col.delete_one({"_id": jackpot["_id"]})
        jackpot_col.insert_one({"pool": 1000, "tickets": 0, "active": True})
        bot.answer_callback_query(call.id, "Ticket bought! A winner was drawn.")
    else:
        bot.answer_callback_query(call.id, "Ticket bought! Good luck!")

def show_game_leaderboard(call: CallbackQuery):
    top_wins = list(users_col.find({}, {"name": 1, "wins": 1, "_id": 0}).sort("wins", -1).limit(5))
    text = "🏆 <b>Game Leaderboard (Wins)</b>\n"
    for i, u in enumerate(top_wins, 1):
        text += f"{i}. {u['name']} - {u['wins']} wins\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")

# ========== CHAT/DATING SYSTEM ==========

chat_sessions = {}

@bot.callback_query_handler(func=lambda call: call.data == "chat_menu")
def chat_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔍 Find Match", callback_data="find_match"))
    kb.add(InlineKeyboardButton("❌ Stop Searching", callback_data="stop_search"))
    kb.add(InlineKeyboardButton("📞 My Matches", callback_data="my_matches"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="home"))
    bot.edit_message_text("💬 <b>Chat & Dating</b>\nFind random partners!", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "find_match")
def find_match(call: CallbackQuery):
    user_id = call.from_user.id
    user = get_user(user_id)
    if not user:
        return
    if not is_vip(user_id):
        last_action = user.get("last_chat_action")
        if last_action and (datetime.utcnow() - last_action).seconds < FREE_CHAT_COOLDOWN:
            bot.answer_callback_query(call.id, f"Cooldown! Wait {FREE_CHAT_COOLDOWN - (datetime.utcnow()-last_action).seconds}s")
            return
    if user_id in chat_sessions:
        bot.answer_callback_query(call.id, "You are already in a chat. Use /skip to disconnect.")
        return
    chat_queue_col.delete_one({"user_id": user_id})
    chat_queue_col.insert_one({
        "user_id": user_id,
        "gender": user["gender"],
        "language": user["language"],
        "vip": is_vip(user_id),
        "timestamp": datetime.utcnow()
    })
    match = match_users(user_id)
    if match:
        start_chat(user_id, match)
        bot.answer_callback_query(call.id, "Match found!")
    else:
        bot.answer_callback_query(call.id, "Searching for a partner... We'll notify you.", show_alert=False)
        bot.send_message(user_id, "🔍 Searching for a match... Type /stopsearch to cancel.")

def match_users(user_id: int) -> Optional[int]:
    my_data = chat_queue_col.find_one({"user_id": user_id})
    if not my_data:
        return None
    query = {"user_id": {"$ne": user_id}}
    candidates = list(chat_queue_col.find(query).sort("vip", -1).limit(10))
    for c in candidates:
        if c["user_id"] not in chat_sessions:
            return c["user_id"]
    return None

def start_chat(user1: int, user2: int):
    chat_queue_col.delete_many({"user_id": {"$in": [user1, user2]}})
    chat_sessions[user1] = user2
    chat_sessions[user2] = user1
    match_data = {"user_id": user1, "matched_user": user2, "started": datetime.utcnow(), "ended": False}
    matches_col.insert_one(match_data)
    match_data2 = {"user_id": user2, "matched_user": user1, "started": datetime.utcnow(), "ended": False}
    matches_col.insert_one(match_data2)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✉️ Send Message", callback_data="send_msg"), InlineKeyboardButton("⏩ Skip", callback_data="skip_chat"))
    kb.add(InlineKeyboardButton("🚫 Disconnect", callback_data="disconnect_chat"))
    for uid in [user1, user2]:
        bot.send_message(uid, "💞 <b>You are now connected!</b>\nStart chatting! Type your message.", reply_markup=kb, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.chat.id in chat_sessions and not m.text.startswith("/"))
def relay_message(message: Message):
    user_id = message.chat.id
    if user_id not in chat_sessions:
        return
    partner = chat_sessions[user_id]
    bot.send_message(partner, f"👤 <b>Stranger says:</b>\n{message.text}", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data in ["skip_chat", "disconnect_chat"])
def handle_chat_action(call: CallbackQuery):
    user_id = call.from_user.id
    if user_id not in chat_sessions:
        bot.answer_callback_query(call.id, "No active chat.")
        return
    partner = chat_sessions[user_id]
    del chat_sessions[user_id]
    if partner in chat_sessions:
        del chat_sessions[partner]
    matches_col.update_many({"user_id": {"$in": [user_id, partner]}, "ended": False}, {"$set": {"ended": True, "ended_at": datetime.utcnow()}})
    bot.send_message(partner, "👋 The user has left the chat.")
    bot.answer_callback_query(call.id, "Disconnected.")
    bot.send_message(user_id, "Disconnected. Use /chat to find a new match.")

@bot.callback_query_handler(func=lambda call: call.data == "stop_search")
def stop_search(call: CallbackQuery):
    chat_queue_col.delete_one({"user_id": call.from_user.id})
    bot.answer_callback_query(call.id, "Search stopped.")
    bot.edit_message_text("Search stopped.", call.message.chat.id, call.message.message_id, reply_markup=main_menu(call.from_user.id))

# ========== AI SYSTEM ==========

ai_sessions = {}

@bot.callback_query_handler(func=lambda call: call.data == "ai_menu")
def ai_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🤖 Normal AI", callback_data="ai_normal"),
        InlineKeyboardButton("😂 Funny AI", callback_data="ai_funny"),
        InlineKeyboardButton("💕 Romantic AI", callback_data="ai_romantic"),
        InlineKeyboardButton("👩‍❤️‍👨 AI Girlfriend", callback_data="ai_gf")
    )
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="home"))
    bot.edit_message_text("🤖 <b>AI Chat</b>\nSelect mode:", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("ai_"))
def set_ai_mode(call: CallbackQuery):
    mode = call.data.split("_")[1]
    if mode == "gf":
        mode = "girlfriend"
    user_id = call.from_user.id
    ai_sessions[user_id] = {"mode": mode, "conversation": []}
    bot.edit_message_text(f"✅ AI mode set to {mode}. Start chatting! (Type /stopai to end)", call.message.chat.id, call.message.message_id, reply_markup=back_button())
    bot.send_message(user_id, "💬 Send any message to chat with AI.")

@bot.message_handler(commands=["stopai"])
def stop_ai(message: Message):
    if message.chat.id in ai_sessions:
        del ai_sessions[message.chat.id]
        bot.reply_to(message, "AI session ended.")

@bot.message_handler(func=lambda m: m.chat.id in ai_sessions and not m.text.startswith("/"))
def handle_ai(message: Message):
    user_id = message.chat.id
    user = get_user(user_id)
    if not user:
        return
    today = datetime.utcnow().date()
    if user["ai_usage_date"] != today:
        users_col.update_one({"user_id": user_id}, {"$set": {"ai_usage": 0, "ai_usage_date": today}})
        user["ai_usage"] = 0
    if not is_vip(user_id) and user["ai_usage"] >= FREE_AI_LIMIT:
        bot.reply_to(message, "❌ Daily AI limit reached. Upgrade to VIP for unlimited AI!")
        return
    if GEMINI_AVAILABLE and GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-pro")
        prompt = f"You are a {ai_sessions[user_id]['mode']} AI assistant. Respond naturally: {message.text}"
        try:
            response = model.generate_content(prompt)
            reply = response.text
        except Exception as e:
            reply = "Sorry, AI is busy. Try again later."
    else:
        reply = "🤖 AI service not configured. Contact admin."
    bot.reply_to(message, reply)
    users_col.update_one({"user_id": user_id}, {"$inc": {"ai_usage": 1}})
    # ========== VIP SYSTEM ==========

@bot.callback_query_handler(func=lambda call: call.data == "vip_menu")
def vip_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💎 Upgrade to VIP (₹199/month)", callback_data="vip_upgrade"))
    kb.add(InlineKeyboardButton("🔍 Check VIP Status", callback_data="vip_status"))
    kb.add(InlineKeyboardButton("⬅️ Back", callback_data="home"))
    bot.edit_message_text("👑 <b>VIP Membership</b>\nBenefits:\n- Unlimited AI\n- Priority chat matching\n- Double daily bonus\n- No cooldowns\n- Exclusive badge", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "vip_upgrade")
def vip_upgrade(call: CallbackQuery):
    bot.edit_message_text(f"💳 <b>Payment Instructions</b>\nSend ₹199 to UPI: {UPI_ID}\nAfter payment, send screenshot via /paymentsubmit", call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "vip_status")
def vip_status(call: CallbackQuery):
    active = is_vip(call.from_user.id)
    status = "✅ Active" if active else "❌ Not active"
    bot.answer_callback_query(call.id, status)

# ========== PAYMENT SYSTEM ==========

@bot.message_handler(commands=["paymentsubmit"])
def payment_submit(message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "Please reply to a screenshot with your transaction ID.")
        return
    photo_id = message.reply_to_message.photo[-1].file_id
    tx_id = message.text.split()[1] if len(message.text.split()) > 1 else "N/A"
    payments_col.insert_one({
        "user_id": message.from_user.id,
        "amount": 199,
        "tx_id": tx_id,
        "screenshot": photo_id,
        "status": "pending",
        "timestamp": datetime.utcnow()
    })
    bot.reply_to(message, "Payment submitted for admin approval.")
    bot.send_message(ADMIN_ID, f"💰 New payment from {message.from_user.id}\nTXID: {tx_id}")

# ========== ADMIN PANEL ==========

@bot.message_handler(commands=["admin"])
def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return bot.reply_to(message, "Unauthorized.")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("💰 Pending Payments", callback_data="admin_payments"),
        InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
        InlineKeyboardButton("🔨 Manage User", callback_data="admin_manage"),
        InlineKeyboardButton("📜 Logs", callback_data="admin_logs")
    )
    bot.send_message(message.chat.id, "🔧 Admin Panel", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_actions(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Unauthorized")
        return
    action = call.data.split("_")[1]
    if action == "stats":
        total_users = users_col.count_documents({})
        total_coins = sum([u["coins"] for u in users_col.find({}, {"coins": 1})])
        bot.edit_message_text(f"📊 Stats\nUsers: {total_users}\nTotal coins: {total_coins}", call.message.chat.id, call.message.message_id)
    elif action == "payments":
        pending = list(payments_col.find({"status": "pending"}))
        for p in pending:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("✅ Approve", callback_data=f"approve_{p['_id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{p['_id']}"))
            bot.send_photo(call.message.chat.id, p["screenshot"], caption=f"User: {p['user_id']}\nTXID: {p['tx_id']}", reply_markup=kb)
        bot.edit_message_text("Process payments.", call.message.chat.id, call.message.message_id)
    elif action == "broadcast":
        bot.send_message(call.message.chat.id, "Send the message to broadcast:")
        bot.register_next_step_handler(call.message, broadcast_message)

def broadcast_message(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    for user in users_col.find({}, {"user_id": 1}):
        try:
            bot.send_message(user["user_id"], message.text)
        except:
            pass
    bot.reply_to(message, "Broadcast sent.")

# ========== DAILY TASKS & SPIN ==========

@bot.callback_query_handler(func=lambda call: call.data == "daily_tasks")
def daily_tasks(call: CallbackQuery):
    tasks = [
        "🎲 Play 3 games → +50 coins",
        "💬 Send 5 chat messages → +30 coins",
        "🤖 Ask AI 2 questions → +20 coins"
    ]
    text = "🎯 <b>Daily Tasks</b>\n" + "\n".join(tasks)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "daily_spin")
def daily_spin(call: CallbackQuery):
    user = get_user(call.from_user.id)
    last_spin = user.get("last_spin")
    if last_spin and (datetime.utcnow() - last_spin).days < 1:
        bot.answer_callback_query(call.id, "Already spun today!")
        return
    rewards = [100, 200, 500, 1000, 50, 150]
    win = random.choice(rewards)
    update_coins(call.from_user.id, win, "Daily spin")
    users_col.update_one({"user_id": call.from_user.id}, {"$set": {"last_spin": datetime.utcnow()}})
    bot.answer_callback_query(call.id, f"🎡 You won {win} coins!")

# ========== LEADERBOARD ==========

@bot.callback_query_handler(func=lambda call: call.data == "leaderboard")
def leaderboard(call: CallbackQuery):
    top_coins = list(users_col.find({}, {"name": 1, "coins": 1, "_id": 0}).sort("coins", -1).limit(5))
    text = "🏆 <b>Coin Leaderboard</b>\n"
    for i, u in enumerate(top_coins, 1):
        text += f"{i}. {u['name']} - {u['coins']} coins\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=back_button(), parse_mode="HTML")

# ========== PROMO CODE SYSTEM ==========

@bot.message_handler(commands=["redeem"])
def redeem_promo(message: Message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /redeem <code>")
        return
    code = parts[1].upper()
    promo = promo_col.find_one({"code": code, "used": False})
    if not promo:
        bot.reply_to(message, "Invalid or expired code.")
        return
    update_coins(message.from_user.id, promo["reward"], "Promo code")
    promo_col.update_one({"_id": promo["_id"]}, {"$set": {"used": True, "used_by": message.from_user.id}})
    bot.reply_to(message, f"✅ Redeemed {promo['reward']} coins!")

# ========== MAIN LOOP ==========

if __name__ == "__main__":
    logger.info("Bot started...")
    if ADMIN_ID:
        create_user(ADMIN_ID, "admin", "Admin")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
