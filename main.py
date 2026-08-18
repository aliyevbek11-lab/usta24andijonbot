import os
import threading

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-3771002872"))

app = Flask(__name__)

orders = {}
user_states = {}


@app.get("/")
def home():
    return "USTA 24 Dispatcher Bot is running!"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🤖 USTA 24 Диспетчер боти\n\n"
        "Янги буюртма киритиш учун /new ни босинг."
    )


async def new_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_states[update.effective_user.id] = {
        "step": "name"
    }

    await update.message.reply_text(
        "🆕 Янги буюртма\n\n"
        "1️⃣ Мижоз исмини киритинг:"
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_states:
        return

    state = user_states[user_id]
    step = state["step"]

    if step == "name":
        state["name"] = text
        state["step"] = "phone"

        await update.message.reply_text(
            "📞 Мижоз телефон рақамини киритинг:"
        )

    elif step == "phone":
        state["phone"] = text
        state["step"] = "address"

        await update.message.reply_text(
            "📍 Манзилни киритинг:"
        )

    elif step == "address":
        state["address"] = text
        state["step"] = "work"

        await update.message.reply_text(
            "🔧 Қандай иш кераклигини ёзинг:"
        )

    elif step == "work":
        state["work"] = text
        state["step"] = "time"

        await update.message.reply_text(
            "⏰ Бориш вақтини киритинг:"
        )

    elif step == "time":
        state["time"] = text

        order_id = len(orders) + 1
        orders[order_id] = state.copy()

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🟢 БУЮРТМАНИ ОЛИШ",
                    callback_data=f"take_{order_id}"
                )
            ]
        ])

        message = (
            f"🔔 ЯНГИ БУЮРТМА №{order_id}\n\n"
            f"👤 Мижоз: {state['name']}\n"
            f"📞 Телефон: {state['phone']}\n"
            f"📍 Манзил: {state['address']}\n"
            f"🔧 Иш: {state['work']}\n"
            f"⏰ Вақт: {state['time']}\n\n"
            f"👷 Буюртмани олиш учун тугмани босинг."
        )

        try:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=message,
                reply_markup=keyboard
            )

            await update.message.reply_text(
                f"✅ Буюртма №{order_id} усталар гуруҳига юборилди."
            )

        except Exception as e:
            print("GROUP SEND ERROR:", repr(e))

            await update.message.reply_text(
                "❌ Буюртмани гуруҳга юборишда хато юз берди."
            )

        del user_states[user_id]


async def take_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split("_")[1])

    order = orders.get(order_id)

    if not order:
        await query.answer(
            "Буюртма топилмади.",
            show_alert=True
        )
        return

    master = query.from_user

    await query.edit_message_text(
        f"🟢 БУЮРТМА №{order_id} ОЛИНДИ!\n\n"
        f"👷 Уста: {master.full_name}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"🔧 Иш: {order['work']}\n"
        f"⏰ Вақт: {order['time']}"
    )


def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000"))
    )


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi")

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("new", new_order)
    )

    application.add_handler(
        CallbackQueryHandler(
            take_order,
            pattern=r"^take_\d+$"
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            message_handler
        )
    )

    threading.Thread(
        target=run_flask,
        daemon=True
    ).start()

    application.run_polling()


if __name__ == 
