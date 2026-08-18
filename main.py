import os
import logging
from flask import Flask
from threading import Thread

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# SOZLAMALAR
# =========================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")

try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)
except ValueError:
    raise RuntimeError("MASTERS_GROUP_ID raqam bo‘lishi kerak!")

# =========================
# LOG
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# =========================
# FLASK
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# =========================
# MENU
# =========================

def main_menu():
    keyboard = [
        ["🛠 Usta chaqirish"],
        ["📋 Xizmatlar", "📞 Aloqa"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# =========================
# BUYURTMA HOLATI
# =========================

user_orders = {}


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    text = (
        "👋 Assalomu alaykum!\n\n"
        "🏠 USTA 24 xizmatiga xush kelibsiz!\n\n"
        "🔧 Uy va ofis uchun ustalar xizmatlari.\n"
        "📍 Andijon shahri\n\n"
        "Kerakli xizmatni tanlang:"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# XIZMATLAR
# =========================

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "🛠 USTA 24 XIZMATLARI\n\n"

        "🪑 Mebel yig‘ish\n"
        "🔧 Mebel ta’mirlash\n"
        "🍽 Oshxona mebellari\n"
        "🚪 Shkaf yig‘ish va ta’mirlash\n"
        "🛏 Krovать yig‘ish\n"
        "🪑 Stol va stul yig‘ish\n"
        "📦 Mebelni qismlarga ajratish va yig‘ish\n"
        "🚚 Mebel tashish\n"
        "🏠 Uy ko‘chirish\n"
        "🚛 Yuk tashish\n"
        "🔩 Santexnika ishlari\n"
        "⚡ Elektr ishlari\n"
        "🔥 Payvandlash ishlari\n"
        "🔨 Boshqa uy xizmatlari\n\n"

        "📞 Buyurtma berish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# ALOQA
# =========================

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "📞 USTA 24\n\n"
        "☎️ Telefon: +998 77 069 00 03\n\n"
        "📍 Andijon shahri\n\n"
        "🛠 Usta chaqirish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing."
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu()
    )


# =========================
# USTA CHAQIRISH
# =========================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    user_orders[user_id] = {
        "step": "name"
    }

    await update.message.reply_text(
        "📝 Буюртма бериш\n\n"
        "1️⃣ Мижоз исмингизни ёзинг:"
    )


# =========================
# BUYURTMA QABUL QILISH
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    # MENU TUGMALARI
    if text == "🛠 Usta chaqirish":
        await start_order(update, context)
        return

    if text == "📋 Xizmatlar":
        await services(update, context)
        return

    if text == "📞 Aloqa":
        await contact(update, context)
        return

    # BUYURTMA YO‘Q BO‘LSA
    if user_id not in user_orders:
        await update.message.reply_text(
            "Iltimos, menyudan kerakli xizmatni tanlang.",
            reply_markup=main_menu()
        )
        return

    order = user_orders[user_id]
    step = order.get("step")

    # =====================
    # ISM
    # =====================

    if step == "name":

        order["name"] = text
        order["step"] = "phone"

        phone_button = KeyboardButton(
            "📱 Telefon raqamimni yuborish",
            request_contact=True
        )

        keyboard = ReplyKeyboardMarkup(
            [[phone_button]],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await update.message.reply_text(
            "2️⃣ Telefon raqamingizni yuboring:",
            reply_markup=keyboard
        )

        return

    # =====================
    # TELEFON
    # =====================

    if step == "phone":

        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = text

        order["phone"] = phone
        order["step"] = "service"

        keyboard = ReplyKeyboardMarkup(
            [
                ["🪑 Mebel"],
                ["🚚 Yuk tashish / ko‘chirish"],
                ["🔩 Santexnika"],
                ["⚡ Elektr"],
                ["🔥 Payvandlash"],
                ["🔨 Boshqa xizmat"],
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            "3️⃣ Qanday xizmat kerak?",
            reply_markup=keyboard
        )

        return

    # =====================
    # XIZMAT
    # =====================

    if step == "service":

        order["service"] = text
        order["step"] = "address"

        await update.message.reply_text(
            "4️⃣ Манзилингизни ёзинг:\n\n"
            "Масалан:\n"
            "Андижон шаҳар, Бобуршоҳ кўчаси, 15-уй"
        )

        return

    # =====================
    # MANZIL
    # =====================

    if step == "address":

        order["address"] = text
        order["step"] = "description"

        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:\n\n"
            "Масалан:\n"
            "Шкаф йиғиш керак.\n"
            "Ёки:\n"
            "Уй кўчириш керак, 3-қават."
        )

        return

    # =====================
    # IZOH
    # =====================

    if step == "description":

        order["description"] = text

        await send_order_to_masters(
            update,
            context,
            order
        )

        del user_orders[user_id]

        await update.message.reply_text(
            "✅ Буюртмангиз қабул қилинди!\n\n"
            "👨‍🔧 Буюртма усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            "☎️ USTA 24: +998 77 069 00 03",
            reply_markup=main_menu()
        )

        return


# =========================
# USTALAR GURUHIGA YUBORISH
# =========================

async def send_order_to_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: dict
):

    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else "username yo‘q"
    )

    message = (
        "🆕 YANGI BUYURTMA\n\n"

        f"🔢 Буюртма: #{user.id}\n\n"

        f"👤 Мижоз: {order.get('name', '-')}\n"
        f"📞 Телефон: {order.get('phone', '-')}\n"
        f"🛠 Хизмат: {order.get('service', '-')}\n"
        f"📍 Манзил: {order.get('address', '-')}\n"
        f"📝 Изоҳ: {order.get('description', '-')}\n\n"

        f"👤 Telegram: {username}\n"
        f"🆔 User ID: {user.id}\n\n"

        "🚨 Уста буюртмани қабул қилиш учун "
        "диспетчер билан боғлансин.\n\n"

        "☎️ USTA 24\n"
        "+998 77 069 00 03"
    )

    await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=message
    )

async def show_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat:
        print(
            f"CHAT ID: {update.effective_chat.id} | "
            f"CHAT TYPE: {update.effective_chat.type} | "
            f"CHAT TITLE: {update.effective_chat.title}"
        )
# =========================
# ERROR
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Xatolik:",
        exc_info=context.error
    )


# =========================
# BOT ISHGA TUSHIRISH
# =========================

def main():

    logger.info("USTA 24 BOT ishga tushmoqda...")

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )
application.add_handler(
    MessageHandler(
        filters.ALL,
        show_chat_id
    )
) application.add_handler(
    MessageHandler(
        filters.ALL,
        show_chat_id
    )
)
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            handle_message
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    application.add_error_handler(
        error_handler
    )

    # Flask serverni alohida ishga tushirish
    flask_thread = Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    logger.info("Flask server ishga tushdi.")
    logger.info("Telegram bot ishga tushdi.")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================
# START
# =========================

if __name__ == 
