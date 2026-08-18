import os
import asyncio
import logging
from threading import Thread

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)


# =========================================================
# SOZLAMALAR
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")

try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID.strip())
except ValueError:
    raise RuntimeError(
        "MASTERS_GROUP_ID raqam bo‘lishi kerak!"
    )


# =========================================================
# LOG
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI!"


@app.route("/health")
def health():
    return "OK"


def run_flask():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# =========================================================
# MENU
# =========================================================

def main_menu():

    keyboard = [
        ["🛠 Usta chaqirish"],
        ["📋 Xizmatlar", "📞 Aloqa"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# =========================================================
# BUYURTMALAR
# =========================================================

user_orders = {}

orders = {}

order_counter = 0


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "🏠 USTA 24 xizmatiga xush kelibsiz!\n\n"
        "🔧 Uy va ofis uchun ustalar xizmatlari.\n"
        "📍 Andijon shahri\n\n"
        "Kerakli xizmatni tanlang:",
        reply_markup=main_menu()
    )


# =========================================================
# CHAT ID
# =========================================================

async def chat_id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    chat = update.effective_chat

    if not chat:
        return

    await update.message.reply_text(
        f"🆔 Chat ID: {chat.id}\n\n"
        f"📌 Chat turi: {chat.type}\n"
        f"📌 Nomi: {chat.title or '-'}"
    )


# =========================================================
# XIZMATLAR
# =========================================================

async def services(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "🛠 USTA 24 XIZMATLARI\n\n"

        "🪑 Mebel yig‘ish\n"
        "🔧 Mebel ta’mirlash\n"
        "🍽 Oshxona mebellari\n"
        "🚪 Shkaf yig‘ish va ta’mirlash\n"
        "🛏 Krovat yig‘ish\n"
        "🪑 Stol va stul yig‘ish\n"
        "📦 Mebelni qismlarga ajratish va yig‘ish\n"
        "🚚 Mebel tashish\n"
        "🏠 Uy ko‘chirish\n"
        "🚛 Yuk tashish\n"
        "🔩 Santexnika ishlari\n"
        "⚡ Elektr ishlari\n"
        "🔥 Payvandlash ishlari\n"
        "🔨 Boshqa xizmat\n\n"

        "📞 Buyurtma berish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing.",
        reply_markup=main_menu()
    )


# =========================================================
# ALOQA
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "☎️ Telefon: +998 77 069 00 03\n\n"
        "📍 Andijon shahri\n\n"
        "🛠 Usta chaqirish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing.",
        reply_markup=main_menu()
    )


# =========================================================
# USTA CHAQIRISH
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_id = update.effective_user.id

    user_orders[user_id] = {
        "step": "name"
    }

    await update.message.reply_text(
        "📝 Буюртма бериш\n\n"
        "1️⃣ Мижоз исмингизни ёзинг:"
    )


# =========================================================
# ASOSIY XABAR HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    user_id = user.id

    text = (
        update.message.text or ""
    ).strip()


    # =====================================================
    # MENU
    # =====================================================

    if text == "🛠 Usta chaqirish":

        await start_order(
            update,
            context
        )

        return


    if text == "📋 Xizmatlar":

        await services(
            update,
            context
        )

        return


    if text == "📞 Aloqa":

        await contact(
            update,
            context
        )

        return


    # =====================================================
    # BUYURTMA YO‘Q
    # =====================================================

    if user_id not in user_orders:

        await update.message.reply_text(
            "Iltimos, menyudan kerakli xizmatni tanlang.",
            reply_markup=main_menu()
        )

        return


    order = user_orders[user_id]

    step = order.get("step")


    # =====================================================
    # 1. ISM
    # =====================================================

    if step == "name":

        if not text:

            await update.message.reply_text(
                "📝 Iltimos, ismingizni yozing:"
            )

            return

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


    # =====================================================
    # 2. TELEFON
    # =====================================================

    if step == "phone":

        if update.message.contact:

            phone = update.message.contact.phone_number

        else:

            phone = text


        if not phone:

            await update.message.reply_text(
                "📱 Iltimos, telefon raqamingizni yuboring."
            )

            return


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


    # =====================================================
    # 3. XIZMAT
    # =====================================================

    if step == "service":

        if not text:

            await update.message.reply_text(
                "Iltimos, xizmat turini tanlang."
            )

            return


        order["service"] = text
        order["step"] = "address"


        await update.message.reply_text(
            "4️⃣ Манзилингизни ёзинг:\n\n"
            "Масалан:\n"
            "Андижон шаҳар, Бобуршоҳ кўчаси, 15-уй"
        )

        return


    # =====================================================
    # 4. MANZIL
    # =====================================================

    if step == "address":

        if not text:

            await update.message.reply_text(
                "📍 Iltimos, manzilingizni yozing."
            )

            return


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


    # =====================================================
    # 5. IZOH
    # =====================================================

    if step == "description":

        if not text:

            await update.message.reply_text(
                "📝 Iltimos, buyurtma haqida "
                "qisqacha ma'lumot yozing."
            )

            return


        order["description"] = text


        try:

            order_id = await send_order_to_masters(
                update,
                context,
                order
            )

        except Exception:

            logger.exception(
                "USTALAR GURUHIGA YUBORISHDA XATO"
            )

            await update.message.reply_text(
                "❌ Буюртмани усталар гуруҳига "
                "юборишда хатолик юз берди.\n\n"
                "☎️ +998 77 069 00 03"
            )

            return


        del user_orders[user_id]


        await update.message.reply_text(
            f"✅ Буюртмангиз қабул қилинди!\n\n"
            f"🔢 Буюртма №{order_id}\n\n"
            "👨‍🔧 Буюртма усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            "☎️ USTA 24: +998 77 069 00 03",
            reply_markup=main_menu()
        )

        return


# =========================================================
# GURUHGA BUYURTMA YUBORISH
# =========================================================

async def send_order_to_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: dict
):

    global order_counter

    order_counter += 1

    order_id = order_counter

    user = update.effective_user

    if user.username:

        username = f"@{user.username}"

    else:

        username = "username yo‘q"


    orders[order_id] = {
        "customer_id": user.id,
        "status": "open",
        "master_id": None,
        "master_name": None,
        "order": order,
    }


    message = (
        "🆕 YANGI BUYURTMA\n\n"

        f"🔢 Буюртма: #{order_id}\n\n"

        f"👤 Мижоз: "
        f"{order.get('name', '-')}\n"

        f"📞 Телефон: "
        f"{order.get('phone', '-')}\n"

        f"🛠 Хизмат: "
        f"{order.get('service', '-')}\n"

        f"📍 Манзил: "
        f"{order.get('address', '-')}\n"

        f"📝 Изоҳ: "
        f"{order.get('description', '-')}\n\n"

        f"👤 Telegram: {username}\n"

        f"🆔 User ID: {user.id}\n\n"

        "🚨 Уста буюртмани қабул қилиш учун "
        "қуйидаги тугмани босинг."
    )


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Қабул қилиш",
                    callback_data=f"accept:{order_id}"
                ),

                InlineKeyboardButton(
                    "❌ Рад этиш",
                    callback_data=f"reject:{order_id}"
                ),
            ]
        ]
    )


    sent_message = await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=message,
        reply_markup=keyboard
    )


    orders[order_id]["message_id"] = (
        sent_message.message_id
    )


    logger.info(
        "Buyurtma #%s guruhga yuborildi.",
        order_id
    )


    return order_id


# =========================================================
# QABUL QILISH / RAD ETISH
# =========================================================

async def order_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return


    data = query.data or ""


    if ":" not in data:

        await query.answer(
            "❌ Noto‘g‘ri buyurtma.",
            show_alert=True
        )

        return


    action, order_id_text = data.split(
        ":",
        1
    )


    try:

        order_id = int(order_id_text)

    except ValueError:

        await query.answer(
            "❌ Buyurtma raqami noto‘g‘ri.",
            show_alert=True
        )

        return


    if order_id not in orders:

        await query.answer(
            "❌ Buyurtma topilmadi.",
            show_alert=True
        )

        return


    order_data = orders[order_id]

    master = query.from_user

    if master.username:

        master_name = f"@{master.username}"

    else:

        master_name = master.full_name


    order_info = order_data["order"]


    # =====================================================
    # QABUL QILISH
    # =====================================================

    if action == "accept":

        if order_data["status"] != "open":

            await query.answer(
                "⚠️ Bu buyurtmani boshqa usta qabul qilgan.",
                show_alert=True
            )

            return


        order_data["status"] = "accepted"

        order_data["master_id"] = master.id

        order_data["master_name"] = master_name


        # =================================================
        # GURUHDA KO‘RSATISH
        # =================================================

        group_text = (
            "✅ BUYURTMA QABUL QILINDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{order_info.get('name', '-')}\n"

            f"📞 Telefon: "
            f"{order_info.get('phone', '-')}\n"

            f"🛠 Xizmat: "
            f"{order_info.get('service', '-')}\n"

            f"📍 Manzil: "
            f"{order_info.get('address', '-')}\n"

            f"📝 Izoh: "
            f"{order_info.get('description', '-')}\n\n"

            f"👨‍🔧 Qabul qilgan usta: "
            f"{master_name}\n"

            f"🆔 Usta ID: {master.id}\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        try:

            await query.edit_message_text(
                text=group_text
            )

        except Exception:

            logger.exception(
                "Guruh xabarini o‘zgartirishda xato"
            )


        # =================================================
        # USTAGA SHAXSIY XABAR
        # =================================================

        master_text = (
            "✅ BUYURTMA SIZGA BIRIKTIRILDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{order_info.get('name', '-')}\n"

            f"📞 Telefon: "
            f"{order_info.get('phone', '-')}\n\n"

            f"🛠 Xizmat: "
            f"{order_info.get('service', '-')}\n"

            f"📍 Manzil: "
            f"{order_info.get('address', '-')}\n\n"

            f"📝 Izoh:\n"
            f"{order_info.get('description', '-')}\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        try:

            await context.bot.send_message(
                chat_id=master.id,
                text=master_text
            )

        except Exception:

            logger.warning(
                "Ustaga shaxsiy xabar yuborilmadi.",
                exc_info=True
            )


        # =================================================
        # MIJOZGA XABAR
        # =================================================

        customer_text = (
            f"✅ Буюртмангиз №{order_id} қабул қилинди.\n\n"

            f"👨‍🔧 Уста: {master_name}\n\n"

            "Тез орада уста сиз билан боғланади.\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=customer_text
            )

        except Exception:

            logger.warning(
                "Mijozga xabar yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "✅ Buyurtma sizga biriktirildi!"
        )

        return


    # =====================================================
    # RAD ETISH
    # =====================================================

    if action == "reject":

        if order_data["status"] != "open":

            await query.answer(
                "⚠️ Bu buyurtma allaqachon qabul qilingan.",
                show_alert=True
            )

            return


        await query.answer(
            "❌ Buyurtma rad etildi."
        )


        try:

            await context.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=(
                    f"❌ Buyurtma #{order_id} "
                    f"{master_name} tomonidan rad etildi."
                )
            )

        except Exception:

            logger.warning(
                "Rad etish xabarida xato.",
                exc_info=True
            )

        return


# =========================================================
# ERROR
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "BOT XATOSI:",
        exc_info=context.error
    )


# =========================================================
# BOT ISHGA TUSHIRISH
# =========================================================

async def run_bot(
    application: Application
):

    await application.initialize()

    await application.start()

    try:

        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES
        )

        logger.info(
            "Telegram polling ishga tushdi."
        )


        while True:

            await asyncio.sleep(
                3600
            )


    finally:

        try:

            await application.updater.stop()

        except Exception:

            logger.exception(
                "Updater stop xatosi"
            )


        try:

            await application.stop()

        except Exception:

            logger.exception(
                "Application stop xatosi"
            )


        try:

            await application.shutdown()

        except Exception:

            logger.exception(
                "Application shutdown xatosi"
            )


# =========================================================
# MAIN
# =========================================================

def main():

    logger.info(
        "USTA 24 BOT ishga tushmoqda..."
    )


    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )


    # /start

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    # /id

    application.add_handler(
        CommandHandler(
            "id",
            chat_id_command
        )
    )


    # ✅ / ❌ tugmalar

    application.add_handler(
        CallbackQueryHandler(
            order_callback
        )
    )


    # Telefon

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            handle_message
        )
    )


    # Oddiy matn

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )


    # Xatolar

    application.add_error_handler(
        error_handler
    )


    # =====================================================
    # FLASK
    # =====================================================

    flask_thread = Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()


    logger.info(
        "Flask server ishga tushdi."
    )


    logger.info(
        "Telegram bot ishga tushdi."
    )


    # =====================================================
    # TELEGRAM
    # =====================================================

    asyncio.run(
        run_bot(application)
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
