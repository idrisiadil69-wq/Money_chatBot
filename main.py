import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

waiting_users = []
active_chats = {}

def menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💬 Start Chat", callback_data="start"),
        InlineKeyboardButton("🔄 Next", callback_data="next"),
        InlineKeyboardButton("🛑 Stop", callback_data="stop"),
        InlineKeyboardButton("💎 Premium", callback_data="premium")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(msg.chat.id,
        "🔥 Welcome to DarkX Chat\n\nClick below to start chatting!",
        reply_markup=menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    uid = call.message.chat.id

    if call.data == "start":
        if uid in waiting_users:
            bot.send_message(uid, "⏳ Already waiting...")
            return

        if waiting_users:
            partner = waiting_users.pop(0)
            active_chats[uid] = partner
            active_chats[partner] = uid

            bot.send_message(uid, "✅ Connected!")
            bot.send_message(partner, "✅ Connected!")
        else:
            waiting_users.append(uid)
            bot.send_message(uid, "⏳ Waiting for partner...")

    elif call.data == "next":
        if uid in active_chats:
            partner = active_chats.pop(uid)
            active_chats.pop(partner, None)
            bot.send_message(partner, "❌ Partner left")
        bot.send_message(uid, "🔄 Finding new partner...")
        handle(call)  # restart matching

    elif call.data == "stop":
        if uid in active_chats:
            partner = active_chats.pop(uid)
            active_chats.pop(partner, None)
            bot.send_message(partner, "❌ Chat ended")
        bot.send_message(uid, "🛑 Chat stopped")

    elif call.data == "premium":
        bot.send_message(uid,
            "💎 Premium\n\nUnlimited chat + fast match\n\nUPI: yourupi@upi"
        )

@bot.message_handler(func=lambda msg: True)
def forward(msg):
    uid = msg.chat.id
    if uid in active_chats:
        bot.send_message(active_chats[uid], msg.text)

print("Bot running...")
bot.infinity_polling()
