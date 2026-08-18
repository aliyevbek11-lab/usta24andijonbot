import os
import asyncio
import logging
from threading import Thread

import psycopg2
from psycopg2.extras import RealDictCursor

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
DATABASE_URL = os.getenv("DATABASE_URL")
DISPATCHER_ID = os.getenv("DISPATCHER_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")


if not DISPATCHER_ID:
    raise RuntimeError("DISPATCHER_ID topilmadi!")


try:
    MASTERS_GROUP_ID = int(
        MASTERS_GROUP_ID.strip()
    )
except ValueError:
    raise RuntimeError(
        "MASTERS_GROUP_ID raqam bo‘lishi kerak!"
    )


try:
    DISPATCHER_ID = int(
        DISPATCHER_ID.strip()
    )
except ValueError:
    raise RuntimeError(
        "DISPATCHER_ID raqam bo‘lishi kerak!"
    )


# =========================================================
# LOG
# =========================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
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
# DATABASE
# =========================================================

def get_db():

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def init_database():

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (

                id SERIAL PRIMARY KEY,

                customer_id BIGINT NOT NULL,

                customer_username TEXT,

                customer_name TEXT,

                phone TEXT,

                service TEXT,

                address TEXT,

                description TEXT,

                status TEXT NOT NULL DEFAULT 'open',

                master_id BIGINT,

                master_name TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                accepted_at TIMESTAMP,

                started_at TIMESTAMP,

                completed_at TIMESTAMP,

                cancelled_at TIMESTAMP,

                message_id BIGINT

            );
            """
        )

        connection.commit()

        cursor.close()

        logger.info(
            "PostgreSQL database tayyor."
        )

    except Exception:

        logger.exception(
            "Database yaratishda xato!"
        )

        raise

    finally:

        if connection:
            connection.close()


# =========================================================
# DATABASE FUNCTIONS
# =========================================================

def create_order(
    customer_id,
    customer_username,
    customer_name,
    phone,
    service,
    address,
    description
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            INSERT INTO orders (
                customer_id,
                customer_username,
                customer_name,
                phone,
                service,
                address,
                description,
                status
            )

            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'open'
            )

            RETURNING id;
            """,

            (
                customer_id,
                customer_username,
                customer_name,
                phone,
                service,
                address,
                description
            )
        )

        result = cursor.fetchone()

        connection.commit()

        cursor.close()

        return result["id"]

    finally:

        if connection:
            connection.close()


def get_order(order_id):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT *
            FROM orders
            WHERE id = %s
            """,
            (order_id,)
        )

        result = cursor.fetchone()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


def update_order_message(
    order_id,
    message_id
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE orders
            SET message_id = %s
            WHERE id = %s
            """,

            (
                message_id,
                order_id
            )
        )

        connection.commit()

        cursor.close()

    finally:

        if connection:
            connection.close()


def accept_order(
    order_id,
    master_id,
    master_name
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            UPDATE orders

            SET
                status = 'accepted',
                master_id = %s,
                master_name = %s,
                accepted_at = CURRENT_TIMESTAMP

            WHERE id = %s
            AND status = 'open'

            RETURNING *;
            """,

            (
                master_id,
                master_name,
                order_id
            )
        )

        result = cursor.fetchone()

        connection.commit()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


def start_order_work(
    order_id,
    master_id
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            UPDATE orders

            SET
                status = 'in_progress',
                started_at = CURRENT_TIMESTAMP

            WHERE id = %s
            AND status = 'accepted'
            AND master_id = %s

            RETURNING *;
            """,

            (
                order_id,
                master_id
            )
        )

        result = cursor.fetchone()

        connection.commit()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


def finish_order(
    order_id,
    master_id
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            UPDATE orders

            SET
                status = 'completed',
                completed_at = CURRENT_TIMESTAMP

            WHERE id = %s
            AND status = 'in_progress'
            AND master_id = %s

            RETURNING *;
            """,

            (
                order_id,
                master_id
            )
        )

        result = cursor.fetchone()

        connection.commit()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


def cancel_order(
    order_id,
    master_id
):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            UPDATE orders

            SET
                status = 'cancelled',
                cancelled_at = CURRENT_TIMESTAMP

            WHERE id = %s
            AND master_id = %s
            AND status IN (
                'accepted',
                'in_progress'
            )

            RETURNING *;
            """,

            (
                order_id,
                master_id
            )
        )

        result = cursor.fetchone()

        connection.commit()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


def reject_order(order_id):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE orders

            SET status = 'rejected'

            WHERE id = %s
            AND status = 'open'
            """,

            (order_id,)
        )

        connection.commit()

        cursor.close()

    finally:

        if connection:
            connection.close()


# =========================================================
# DISPATCHER DATABASE
# =========================================================

def get_orders_by_status(status):

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT *
            FROM orders
            WHERE status = %s
            ORDER BY id DESC
            LIMIT 50
            """,

            (status,)
        )

        results = cursor.fetchall()

        cursor.close()

        return results

    finally:

        if connection:
            connection.close()


def get_all_orders():

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT *
            FROM orders
            ORDER BY id DESC
            LIMIT 50
            """
        )

        results = cursor.fetchall()

        cursor.close()

        return results

    finally:

        if connection:
            connection.close()


def get_statistics():

    connection = None

    try:

        connection = get_db()

        cursor = connection.cursor(
            cursor_factory=RealDictCursor
        )

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,

                COUNT(*) FILTER (
                    WHERE status = 'open'
                ) AS open_count,

                COUNT(*) FILTER (
                    WHERE status = 'accepted'
                ) AS accepted_count,

                COUNT(*) FILTER (
                    WHERE status = 'in_progress'
                ) AS progress_count,

                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed_count,

                COUNT(*) FILTER (
                    WHERE status = 'cancelled'
                ) AS cancelled_count,

                COUNT(*) FILTER (
                    WHERE status = 'rejected'
                ) AS rejected_count

            FROM orders
            """
        )

        result = cursor.fetchone()

        cursor.close()

        return result

    finally:

        if connection:
            connection.close()


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


def services_keyboard():

    keyboard = [

        ["🪑 Mebel"],

        ["🚚 Yuk tashish / ko‘chirish"],

        ["🔩 Santexnika"],

        ["⚡ Elektr"],

        ["🔥 Payvandlash"],

        ["🔨 Boshqa xizmat"],

    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


def dispatcher_menu():

    keyboard = [

        ["🆕 Yangi buyurtmalar"],

        ["🟡 Qabul qilingan"],

        ["🔵 Ish jarayonida"],

        ["✅ Yakunlangan"],

        ["❌ Bekor qilingan"],

        ["📋 Barcha buyurtmalar"],

        ["📊 Statistika"],

    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


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
# DISPATCHER COMMAND
# =========================================================

async def dispatcher_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    if user.id != DISPATCHER_ID:

        await update.message.reply_text(
            "❌ Sizda диспетчер ҳуқуқи йўқ."
        )

        return

    await update.message.reply_text(

        "👨‍💼 USTA 24 DİSPETCHER PANELI\n\n"
        "Kerakli bo‘limni tanlang:",

        reply_markup=dispatcher_menu()
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
# SERVICES
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
# CONTACT
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(

        "📞 USTA 24\n\n"

        "☎️ Telefon:\n"
        "+998 77 069 00 03\n\n"

        "📍 Andijon shahri\n\n"

        "🛠 Usta chaqirish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing.",

        reply_markup=main_menu()
    )


# =========================================================
# USER ORDERS
# =========================================================

user_orders = {}


# =========================================================
# START ORDER
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    user_orders[user.id] = {
        "step": "name"
    }

    await update.message.reply_text(

        "📝 Буюртма бериш\n\n"

        "1️⃣ Мижоз исмингизни ёзинг:"
    )


# =========================================================
# DISPATCHER SHOW ORDERS
# =========================================================

async def show_dispatcher_orders(
    update: Update,
    status,
    title
):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != DISPATCHER_ID:
        return

    rows = get_orders_by_status(
        status
    )

    if not rows:

        await update.message.reply_text(
            f"{title}\n\n"
            "📭 Ҳозирча буюртмалар йўқ.",
            reply_markup=dispatcher_menu()
        )

        return


    messages = []

    for row in rows:

        text = (

            f"🔢 Буюртма: #{row['id']}\n"

            f"👤 Мижоз: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Телефон: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Хизмат: "
            f"{row['service'] or '-'}\n"

            f"📍 Манзил: "
            f"{row['address'] or '-'}\n"

            f"📝 Изоҳ: "
            f"{row['description'] or '-'}\n"

            f"👨‍🔧 Уста: "
            f"{row['master_name'] or '-'}\n"

            f"📌 Ҳолат: "
            f"{row['status']}\n"

            "──────────────"
        )

        messages.append(text)


    result = "\n".join(
        messages
    )


    if len(result) > 3900:

        result = result[:3900]

        result += "\n\n..."

    await update.message.reply_text(

        f"{title}\n\n"
        f"{result}",

        reply_markup=dispatcher_menu()
    )


# =========================================================
# DISPATCHER STATISTICS
# =========================================================

async def show_statistics(
    update: Update
):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != DISPATCHER_ID:
        return


    stats = get_statistics()


    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: "
        f"{stats['total']}\n\n"

        f"🆕 Янги: "
        f"{stats['open_count']}\n"

        f"🟡 Қабул қилинган: "
        f"{stats['accepted_count']}\n"

        f"🔵 Иш жараёнида: "
        f"{stats['progress_count']}\n"

        f"✅ Якунланган: "
        f"{stats['completed_count']}\n"

        f"❌ Бекор қилинган: "
        f"{stats['cancelled_count']}\n"

        f"🚫 Рад этилган: "
        f"{stats['rejected_count']}",

        reply_markup=dispatcher_menu()
    )


# =========================================================
# HANDLE MESSAGE
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
    # DISPATCHER
    # =====================================================

    if user_id == DISPATCHER_ID:

        if text == "🆕 Yangi buyurtmalar":

            await show_dispatcher_orders(
                update,
                "open",
                "🆕 YANGI BUYURTMALAR"
            )

            return


        if text == "🟡 Qabul qilingan":

            await show_dispatcher_orders(
                update,
                "accepted",
                "🟡 QABUL QILINGAN"
            )

            return


        if text == "🔵 Ish jarayonida":

            await show_dispatcher_orders(
                update,
                "in_progress",
                "🔵 ISH JARAYONIDA"
            )

            return


        if text == "✅ Yakunlangan":

            await show_dispatcher_orders(
                update,
                "completed",
                "✅ YAKUNLANGAN"
            )

            return


        if text == "❌ Bekor qilingan":

            await show_dispatcher_orders(
                update,
                "cancelled",
                "❌ BEKOR QILINGAN"
            )

            return


        if text == "📋 Barcha buyurtmalar":

            rows = get_all_orders()

            if not rows:

                await update.message.reply_text(
                    "📭 Ҳозирча буюртмалар йўқ.",
                    reply_markup=dispatcher_menu()
                )

                return


            messages = []

            for row in rows:

                messages.append(

                    f"🔢 #{row['id']} | "
                    f"{row['customer_name'] or '-'} | "
                    f"{row['status']}"
                )


            result = "\n".join(
                messages
            )


            await update.message.reply_text(

                "📋 БАРЧА БУЮРТМАЛАР\n\n"
                + result,

                reply_markup=dispatcher_menu()
            )

            return


        if text == "📊 Statistika":

            await show_statistics(
                update
            )

            return


    # =====================================================
    # MAIN MENU
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
    # ORDER
    # =====================================================

    if user_id not in user_orders:

        await update.message.reply_text(

            "Iltimos, menyudan kerakli "
            "xizmatni tanlang.",

            reply_markup=main_menu()
        )

        return


    order = user_orders[user_id]

    step = order.get("step")


    # NAME

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


    # PHONE

    if step == "phone":

        if update.message.contact:

            phone = (
                update.message.contact.phone_number
            )

        else:

            phone = text


        if not phone:

            await update.message.reply_text(

                "📱 Iltimos, telefon "
                "raqamingizni yuboring."
            )

            return


        order["phone"] = phone

        order["step"] = "service"


        await update.message.reply_text(

            "3️⃣ Qanday xizmat kerak?",

            reply_markup=services_keyboard()
        )

        return


    # SERVICE

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

            "Андижон шаҳар, "
            "Бобуршоҳ кўчаси, 15-уй"
        )

        return


    # ADDRESS

    if step == "address":

        if not text:

            await update.message.reply_text(
                "📍 Iltimos, manzilingizni yozing."
            )

            return


        order["address"] = text

        order["step"] = "description"


        await update.message.reply_text(

            "5️⃣ Буюртма ҳақида қисқача "
            "маълумот ёзинг:\n\n"

            "Масалан:\n"
            "Шкаф йиғиш керак.\n\n"

            "Ёки:\n"
            "Уй кўчириш керак, 3-қават."
        )

        return


    # DESCRIPTION

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
                "Buyurtmani yuborishda xato!"
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

            "👨‍🔧 Буюртма усталар "
            "гуруҳига юборилди.\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03",

            reply_markup=main_menu()
        )

        return


# =========================================================
# SEND ORDER
# =========================================================

async def send_order_to_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order: dict
):

    user = update.effective_user

    if not user:
        raise RuntimeError(
            "Foydalanuvchi topilmadi!"
        )


    if user.username:

        username = (
            f"@{user.username}"
        )

    else:

        username = "username yo‘q"


    order_id = create_order(

        customer_id=user.id,

        customer_username=username,

        customer_name=order.get(
            "name",
            "-"
        ),

        phone=order.get(
            "phone",
            "-"
        ),

        service=order.get(
            "service",
            "-"
        ),

        address=order.get(
            "address",
            "-"
        ),

        description=order.get(
            "description",
            "-"
        )
    )


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

        "🚨 Уста буюртмани қабул қилиш "
        "учун қуйидаги тугмани босинг."
    )


    keyboard = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton(

                    "✅ Қабул қилиш",

                    callback_data=(
                        f"accept:{order_id}"
                    )
                ),

                InlineKeyboardButton(

                    "❌ Рад этиш",

                    callback_data=(
                        f"reject:{order_id}"
                    )
                ),

            ]

        ]
    )


    sent_message = await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=message,

        reply_markup=keyboard
    )


    update_order_message(

        order_id,

        sent_message.message_id
    )


    return order_id


# =========================================================
# CALLBACK
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


    action, order_id_text = (
        data.split(":", 1)
    )


    try:

        order_id = int(
            order_id_text
        )

    except ValueError:

        await query.answer(
            "❌ Buyurtma raqami noto‘g‘ri.",
            show_alert=True
        )

        return


    order_data = get_order(
        order_id
    )


    if not order_data:

        await query.answer(
            "❌ Buyurtma topilmadi.",
            show_alert=True
        )

        return


    master = query.from_user


    if master.username:

        master_name = (
            f"@{master.username}"
        )

    else:

        master_name = master.full_name


    # ACCEPT

    if action == "accept":

        result = accept_order(

            order_id,

            master.id,

            master_name
        )


        if not result:

            await query.answer(

                "⚠️ Бу буюртмани бошқа "
                "уста қабул қилган.",

                show_alert=True
            )

            return


        order_data = result


        group_text = (

            "✅ BUYURTMA QABUL QILINDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{order_data['customer_name']}\n"

            f"📞 Telefon: "
            f"{order_data['phone']}\n"

            f"🛠 Xizmat: "
            f"{order_data['service']}\n"

            f"📍 Manzil: "
            f"{order_data['address']}\n"

            f"📝 Izoh: "
            f"{order_data['description']}\n\n"

            f"👨‍🔧 Qabul qilgan usta: "
            f"{master_name}\n"

            f"🆔 Usta ID: {master.id}\n\n"

            "🟡 Holat: Qabul qilindi\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        keyboard = InlineKeyboardMarkup(

            [

                [

                    InlineKeyboardButton(

                        "🔵 Ishni boshlash",

                        callback_data=(
                            f"startwork:{order_id}"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(

                        "❌ Bekor qilish",

                        callback_data=(
                            f"cancel:{order_id}"
                        )
                    )

                ]

            ]
        )


        await query.edit_message_text(

            text=group_text,

            reply_markup=keyboard
        )


        try:

            await context.bot.send_message(

                chat_id=master.id,

                text=(

                    "✅ BUYURTMA SIZGA "
                    "BIRIKTIRILDI\n\n"

                    f"🔢 Buyurtma: #{order_id}\n\n"

                    f"👤 Mijoz: "
                    f"{order_data['customer_name']}\n"

                    f"📞 Telefon: "
                    f"{order_data['phone']}\n\n"

                    f"🛠 Xizmat: "
                    f"{order_data['service']}\n"

                    f"📍 Manzil: "
                    f"{order_data['address']}\n\n"

                    f"📝 Izoh:\n"
                    f"{order_data['description']}\n\n"

                    "🟡 Holat: Qabul qilindi\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Ustaga xabar yuborilmadi.",
                exc_info=True
            )


        try:

            await context.bot.send_message(

                chat_id=(
                    order_data["customer_id"]
                ),

                text=(

                    f"✅ Буюртмангиз №{order_id} "
                    "қабул қилинди.\n\n"

                    f"👨‍🔧 Уста: {master_name}\n\n"

                    "Уста буюртмани қабул қилди.\n\n"

                    "🟡 Ҳолат: Қабул қилинди.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
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


    # START WORK

    if action == "startwork":

        result = start_order_work(

            order_id,

            master.id
        )


        if not result:

            await query.answer(

                "❌ Bu buyurtma sizga "
                "biriktirilmagan.",

                show_alert=True
            )

            return


        order_data = result


        group_text = (

            "🔵 ISH BOSHLANDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{order_data['customer_name']}\n"

            f"📞 Telefon: "
            f"{order_data['phone']}\n"

            f"🛠 Xizmat: "
            f"{order_data['service']}\n"

            f"📍 Manzil: "
            f"{order_data['address']}\n"

            f"📝 Изоҳ: "
            f"{order_data['description']}\n\n"

            f"👨‍🔧 Уста: {master_name}\n"

            "🔵 Holat: Ish jarayonida\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        keyboard = InlineKeyboardMarkup(

            [

                [

                    InlineKeyboardButton(

                        "✅ Ishni yakunlash",

                        callback_data=(
                            f"finish:{order_id}"
                        )
                    )

                ]

            ]
        )


        await query.edit_message_text(

            text=group_text,

            reply_markup=keyboard
        )


        try:

            await context.bot.send_message(

                chat_id=(
                    order_data["customer_id"]
                ),

                text=(

                    f"🔵 Буюртмангиз №{order_id}\n\n"

                    f"👨‍🔧 Уста: {master_name}\n\n"

                    "Уста ишни бошлади.\n\n"

                    "🔵 Ҳолат: Иш жараёнида.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga ish boshlangan "
                "xabar yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "🔵 Ish boshlandi!"
        )

        return


    # FINISH

    if action == "finish":

        result = finish_order(

            order_id,

            master.id
        )


        if not result:

            await query.answer(

                "❌ Bu buyurtma sizga "
                "biriktirilmagan.",

                show_alert=True
            )

            return


        order_data = result


        group_text = (

            "✅ ISH YAKUNLANDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{order_data['customer_name']}\n"

            f"📞 Telefon: "
            f"{order_data['phone']}\n"

            f"🛠 Xizmat: "
            f"{order_data['service']}\n"

            f"📍 Manzil: "
            f"{order_data['address']}\n"

            f"📝 Изоҳ: "
            f"{order_data['description']}\n\n"

            f"👨‍🔧 Уста: {master_name}\n"

            "✅ Holat: Yakunlandi\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        await query.edit_message_text(
            text=group_text
        )


        try:

            await context.bot.send_message(

                chat_id=(
                    order_data["customer_id"]
                ),

                text=(

                    f"✅ Буюртмангиз №{order_id} "
                    "якунланди.\n\n"

                    f"👨‍🔧 Уста: {master_name}\n\n"

                    "Хизмат кўрсатиш ишлари "
                    "якунланди.\n\n"

                    "Раҳмат! USTA 24 хизматидан "
                    "фойдаланганингиз учун.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga yakunlangan "
                "xabar yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "✅ Buyurtma yakunlandi!"
        )

        return


    # CANCEL

    if action == "cancel":

        result = cancel_order(

            order_id,

            master.id
        )


        if not result:

            await query.answer(

                "❌ Bu buyurtmani "
                "bekor qilib bo‘lmaydi.",

                show_alert=True
            )

            return


        order_data = result


        await query.edit_message_text(

            text=(

                "❌ BUYURTMA BEKOR QILINDI\n\n"

                f"🔢 Buyurtma: #{order_id}\n\n"

                f"👤 Mijoz: "
                f"{order_data['customer_name']}\n"

                f"📞 Telefon: "
                f"{order_data['phone']}\n"

                f"🛠 Xizmat: "
                f"{order_data['service']}\n"

                f"📍 Манзил: "
                f"{order_data['address']}\n\n"

                f"👨‍🔧 Уста: {master_name}\n\n"

                "❌ Holat: Bekor qilindi\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )


        try:

            await context.bot.send_message(

                chat_id=(
                    order_data["customer_id"]
                ),

                text=(

                    f"❌ Буюртмангиз №{order_id} "
                    "бекор қилинди.\n\n"

                    f"👨‍🔧 Уста: {master_name}\n\n"

                    "Илтимос, диспетчер билан "
                    "боғланинг.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga bekor qilingan "
                "xabar yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "❌ Buyurtma bekor qilindi."
        )

        return


    # REJECT

    if action == "reject":

        reject_order(
            order_id
        )


        await query.answer(
            "❌ Buyurtma rad etildi."
        )


        try:

            await query.edit_message_text(

                text=(

                    "❌ BUYURTMA RAD ETILDI\n\n"

                    f"🔢 Buyurtma: #{order_id}\n\n"

                    f"👤 Мижоз: "
                    f"{order_data['customer_name']}\n"

                    f"🛠 Хизмат: "
                    f"{order_data['service']}\n"

                    f"📍 Манзил: "
                    f"{order_data['address']}\n\n"

                    f"👨‍🔧 Рад этган уста: "
                    f"{master_name}\n\n"

                    "❌ Holat: Rad etildi\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.exception(
                "Rad etishda xato."
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
# RUN BOT
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
                "Updater stop xatosi."
            )


        try:

            await application.stop()

        except Exception:

            logger.exception(
                "Application stop xatosi."
            )


        try:

            await application.shutdown()

        except Exception:

            logger.exception(
                "Application shutdown xatosi."
            )


# =========================================================
# MAIN
# =========================================================

def main():

    logger.info(
        "USTA 24 BOT ishga tushmoqda..."
    )


    init_database()


    application = (

        Application.builder()

        .token(TOKEN)

        .build()
    )


    # START

    application.add_handler(

        CommandHandler(
            "start",
            start
        )
    )


    # DISPATCHER

    application.add_handler(

        CommandHandler(
            "dispatcher",
            dispatcher_command
        )
    )


    # ID

    application.add_handler(

        CommandHandler(
            "id",
            chat_id_command
        )
    )


    # CALLBACK

    application.add_handler(

        CallbackQueryHandler(
            order_callback
        )
    )


    # CONTACT

    application.add_handler(

        MessageHandler(
            filters.CONTACT,
            handle_message
        )
    )


    # TEXT

    application.add_handler(

        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )


    # ERROR

    application.add_error_handler(
        error_handler
    )


    # FLASK

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


    asyncio.run(
        run_bot(application)
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
