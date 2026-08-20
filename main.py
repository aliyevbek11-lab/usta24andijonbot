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

import asyncpg


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
DISPATCHES_ID = os.getenv("DISPATCHES_ID")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")


if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")


if not DISPATCHES_ID:
    raise RuntimeError("DISPATCHES_ID topilmadi!")


try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID.strip())
except ValueError:
    raise RuntimeError(
        "MASTERS_GROUP_ID raqam bo‘lishi kerak!"
    )


try:
    DISPATCHES_ID = int(DISPATCHES_ID.strip())
except ValueError:
    raise RuntimeError(
        "DISPATCHES_ID raqam bo‘lishi kerak!"
    )


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# FLASK SERVER
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

db_pool = None


async def init_database():

    global db_pool

    try:

        logger.info(
            "Connecting to database..."
        )

        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=30
        )

        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (

                    id SERIAL PRIMARY KEY,

                    telegram_id BIGINT UNIQUE NOT NULL,

                    name TEXT,

                    phone TEXT,

                    username TEXT,

                    created_at TIMESTAMP DEFAULT NOW(),

                    last_order_at TIMESTAMP
                )
                """
            )


            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (

                    id SERIAL PRIMARY KEY,

                    customer_id BIGINT NOT NULL,

                    customer_name TEXT,

                    phone TEXT,

                    service TEXT,

                    address TEXT,

                    description TEXT,

                    username TEXT,

                    status TEXT NOT NULL DEFAULT 'open',

                    master_id BIGINT,

                    master_name TEXT,

                    created_at TIMESTAMP DEFAULT NOW(),

                    accepted_at TIMESTAMP,

                    started_at TIMESTAMP,

                    completed_at TIMESTAMP,

                    cancelled_at TIMESTAMP,

                    rejected_at TIMESTAMP
                )
                """
            )

        logger.info(
            "PostgreSQL muvaffaqiyatli ulandi."
        )

    except Exception as e:

        logger.exception(
            "PostgreSQL ulanishda XATO: %s",
            e
        )

        raise


# =========================================================
# DATABASE - CUSTOMER
# =========================================================

async def db_save_customer(
    telegram_id,
    name=None,
    phone=None,
    username=None
):

    if not db_pool:
        return

    try:

        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO customers (
                    telegram_id,
                    name,
                    phone,
                    username,
                    last_order_at
                )

                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    NOW()
                )

                ON CONFLICT (telegram_id)

                DO UPDATE SET

                    name =
                        COALESCE(
                            EXCLUDED.name,
                            customers.name
                        ),

                    phone =
                        COALESCE(
                            EXCLUDED.phone,
                            customers.phone
                        ),

                    username =
                        COALESCE(
                            EXCLUDED.username,
                            customers.username
                        ),

                    last_order_at =
                        NOW()
                """,

                telegram_id,
                name,
                phone,
                username
            )

    except Exception:

        logger.exception(
            "Customer saqlashda XATO!"
        )


# =========================================================
# DATABASE - GET CUSTOMER
# =========================================================

async def db_get_customer(
    telegram_id
):

    if not db_pool:
        return None

    try:

        async with db_pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *

                FROM customers

                WHERE telegram_id = $1
                """,

                telegram_id
            )

    except Exception:

        logger.exception(
            "Customer olishda XATO!"
        )

        return None


# =========================================================
# DATABASE - CREATE ORDER
# =========================================================

async def db_create_order(
    customer_id,
    customer_name,
    phone,
    service,
    address,
    description,
    username
):

    if not db_pool:
        return None

    try:

        async with db_pool.acquire() as conn:

            order_id = await conn.fetchval(
                """
                INSERT INTO orders (

                    customer_id,

                    customer_name,

                    phone,

                    service,

                    address,

                    description,

                    username,

                    status

                )

                VALUES (

                    $1,

                    $2,

                    $3,

                    $4,

                    $5,

                    $6,

                    $7,

                    'open'

                )

                RETURNING id
                """,

                customer_id,

                customer_name,

                phone,

                service,

                address,

                description,

                username
            )

            logger.info(
                "Yangi buyurtma #%s yaratildi.",
                order_id
            )

            return int(order_id)

    except Exception:

        logger.exception(
            "Buyurtma yaratishda XATO!"
        )

        return None


# =========================================================
# DATABASE - GET ORDER
# =========================================================

async def db_get_order(
    order_id
):

    if not db_pool:
        return None

    try:

        async with db_pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *

                FROM orders

                WHERE id = $1
                """,

                order_id
            )

    except Exception:

        logger.exception(
            "Buyurtma olishda XATO!"
        )

        return None


# =========================================================
# DATABASE - UPDATE ORDER
# =========================================================

async def db_update_status(
    order_id,
    status,
    master_id=None,
    master_name=None
):

    if not db_pool:
        return

    timestamp_column = {

        "accepted":
            "accepted_at",

        "in_progress":
            "started_at",

        "completed":
            "completed_at",

        "cancelled":
            "cancelled_at",

        "rejected":
            "rejected_at",

    }.get(status)


    try:

        async with db_pool.acquire() as conn:

            if timestamp_column:

                query = f"""
                    UPDATE orders

                    SET

                        status = $1,

                        master_id =
                            COALESCE($2, master_id),

                        master_name =
                            COALESCE($3, master_name),

                        {timestamp_column} = NOW()

                    WHERE id = $4
                """

            else:

                query = """
                    UPDATE orders

                    SET

                        status = $1,

                        master_id =
                            COALESCE($2, master_id),

                        master_name =
                            COALESCE($3, master_name)

                    WHERE id = $4
                """


            await conn.execute(
                query,

                status,

                master_id,

                master_name,

                order_id
            )


    except Exception:

        logger.exception(
            "Order status yangilashda XATO!"
        )


# =========================================================
# DATABASE - GET ORDERS
# =========================================================

async def db_get_orders(
    status=None
):

    if not db_pool:
        return []

    try:

        async with db_pool.acquire() as conn:

            if status:

                rows = await conn.fetch(
                    """
                    SELECT *

                    FROM orders

                    WHERE status = $1

                    ORDER BY id DESC

                    LIMIT 100
                    """,

                    status
                )

            else:

                rows = await conn.fetch(
                    """
                    SELECT *

                    FROM orders

                    ORDER BY id DESC

                    LIMIT 100
                    """
                )

            return rows

    except Exception:

        logger.exception(
            "Buyurtmalarni olishda XATO!"
        )

        return []


# =========================================================
# DATABASE - STATISTICS
# =========================================================

async def db_statistics():

    result = {

        "total": 0,

        "open": 0,

        "accepted": 0,

        "in_progress": 0,

        "completed": 0,

        "cancelled": 0,

        "rejected": 0,
    }


    if not db_pool:
        return result


    try:

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT

                    status,

                    COUNT(*) AS count

                FROM orders

                GROUP BY status
                """
            )


        for row in rows:

            status = row["status"]

            count = int(
                row["count"]
            )

            if status in result:

                result[status] = count

            result["total"] += count


        return result


    except Exception:

        logger.exception(
            "Statistika olishda XATO!"
        )

        return result


# =========================================================
# CUSTOMER MENU
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
# DISPATCHER MENU
# =========================================================

def dispatcher_menu():

    keyboard = [

        ["🆕 Yangi buyurtmalar"],

        ["🟡 Qabul qilingan"],

        ["🔵 Ish jarayonida"],

        ["✅ Yakunlangan"],

        ["❌ Bekor qilingan"],

        ["🚫 Rad etilgan"],

        ["📋 Barcha buyurtmalar"],

        ["📊 Statistika"],

    ]

    return ReplyKeyboardMarkup(

        keyboard,

        resize_keyboard=True
    )


# =========================================================
# MEMORY
# =========================================================

user_orders = {}


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
# DISPATCHER
# =========================================================

async def dispatcher(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return


    user = update.effective_user

    if not user:
        return


    if user.id != DISPATCHES_ID:

        await update.message.reply_text(

            "❌ Sizda dispetcher paneliga "
            "kirish huquqi yo‘q.",

            reply_markup=main_menu()
        )

        return


    await update.message.reply_text(

        "🛠 USTA 24 DISPETCHER PANELI\n\n"

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

        "☎️ Telefon: +998 77 069 00 03\n\n"

        "📍 Andijon shahri\n\n"

        "🛠 Usta chaqirish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing.",

        reply_markup=main_menu()
    )


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


    user_id = user.id


    customer = await db_get_customer(
        user_id
    )


    # =====================================================
    # OLD CUSTOMER
    # =====================================================

    if customer:

        name = customer["name"]

        phone = customer["phone"]


        if name and phone:

            user_orders[user_id] = {

                "step": "service",

                "name": name,

                "phone": phone,
            }


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

                f"👋 Salom, {name}!\n\n"

                "Sizni esladik. ✅\n"

                "Ism va telefon raqamingiz saqlangan.\n\n"

                "3️⃣ Qanday xizmat kerak?",

                reply_markup=keyboard
            )

            return


    # =====================================================
    # NEW CUSTOMER
    # =====================================================

    user_orders[user_id] = {

        "step": "name"
    }


    await update.message.reply_text(

        "📝 BUYURTMA BERISH\n\n"

        "1️⃣ Ismingizni yozing:"
    )


# =========================================================
# FORMAT ORDER
# =========================================================

def format_order(
    order,
    status_text=None
):

    if isinstance(order, dict):

        order_id = order.get(
            "id",
            "-"
        )

        name = order.get(
            "name",
            "-"
        )

        phone = order.get(
            "phone",
            "-"
        )

        service = order.get(
            "service",
            "-"
        )

        address = order.get(
            "address",
            "-"
        )

        description = order.get(
            "description",
            "-"
        )

        master = order.get(
            "master_name"
        ) or "-"

        status = order.get(
            "status",
            "-"
        )

    else:

        order_id = order["id"]

        name = (
            order["customer_name"]
            or "-"
        )

        phone = (
            order["phone"]
            or "-"
        )

        service = (
            order["service"]
            or "-"
        )

        address = (
            order["address"]
            or "-"
        )

        description = (
            order["description"]
            or "-"
        )

        master = (
            order["master_name"]
            or "-"
        )

        status = order["status"]


    status_display = (

        status_text

        if status_text

        else status
    )


    return (

        f"🔢 Buyurtma: #{order_id}\n"

        f"👤 Mijoz: {name}\n"

        f"📞 Telefon: {phone}\n"

        f"🛠 Xizmat: {service}\n"

        f"📍 Manzil: {address}\n"

        f"📝 Izoh: {description}\n"

        f"👨‍🔧 Usta: {master}\n"

        f"📌 Holat: {status_display}\n"

        "──────────────"
    )


# =========================================================
# SHOW ORDERS
# =========================================================

async def show_orders(
    update: Update,
    status=None,
    title="📋 BUYURTMALAR"
):

    if not update.message:
        return


    user = update.effective_user

    if not user:
        return


    if user.id != DISPATCHES_ID:

        await update.message.reply_text(

            "❌ Sizda ruxsat yo‘q.",

            reply_markup=main_menu()
        )

        return


    rows = await db_get_orders(
        status
    )


    if not rows:

        await update.message.reply_text(

            "📭 Hozircha buyurtmalar yo‘q.",

            reply_markup=dispatcher_menu()
        )

        return


    text = (

        f"{title}\n\n"
    )


    for order in rows:

        text += (

            format_order(order)

            + "\n\n"
        )


    # Telegram xabar limiti
    # sababli juda uzun bo‘lsa bo‘lib yuboramiz

    chunks = []

    current = ""


    for line in text.splitlines(
        keepends=True
    ):

        if len(current) + len(line) > 3800:

            chunks.append(
                current
            )

            current = ""


        current += line


    if current:

        chunks.append(
            current
        )


    for chunk in chunks:

        await update.message.reply_text(
            chunk
        )


    await update.message.reply_text(

        "⬅️ Dispetcher paneli:",

        reply_markup=dispatcher_menu()
    )


# =========================================================
# STATISTICS
# =========================================================

async def show_statistics(
    update: Update
):

    if not update.message:
        return


    user = update.effective_user

    if not user:
        return


    if user.id != DISPATCHES_ID:

        await update.message.reply_text(
            "❌ Ruxsat yo‘q."
        )

        return


    stats = await db_statistics()


    text = (

        "📊 USTA 24 STATISTIKA\n\n"

        f"📋 Jami: {stats['total']}\n\n"

        f"🆕 Yangi: {stats['open']}\n"

        f"🟡 Qabul qilingan: "
        f"{stats['accepted']}\n"

        f"🔵 Ish jarayonida: "
        f"{stats['in_progress']}\n"

        f"✅ Yakunlangan: "
        f"{stats['completed']}\n"

        f"❌ Bekor qilingan: "
        f"{stats['cancelled']}\n"

        f"🚫 Rad etilgan: "
        f"{stats['rejected']}"
    )


    await update.message.reply_text(

        text,

        reply_markup=dispatcher_menu()
    )


# =========================================================
# DISPATCHER MENU
# =========================================================

async def handle_dispatcher_menu(
    update: Update,
    text
):

    if text == "🆕 Yangi buyurtmalar":

        await show_orders(
            update,
            "open",
            "🆕 YANGI BUYURTMALAR"
        )

        return True


    if text == "🟡 Qabul qilingan":

        await show_orders(
            update,
            "accepted",
            "🟡 QABUL QILINGAN"
        )

        return True


    if text == "🔵 Ish jarayonida":

        await show_orders(
            update,
            "in_progress",
            "🔵 ISH JARAYONIDA"
        )

        return True


    if text == "✅ Yakunlangan":

        await show_orders(
            update,
            "completed",
            "✅ YAKUNLANGAN"
        )

        return True


    if text == "❌ Bekor qilingan":

        await show_orders(
            update,
            "cancelled",
            "❌ BEKOR QILINGAN"
        )

        return True


    if text == "🚫 Rad etilgan":

        await show_orders(
            update,
            "rejected",
            "🚫 RAD ETILGAN"
        )

        return True


    if text == "📋 Barcha buyurtmalar":

        await show_orders(
            update,
            None,
            "📋 BARCHA BUYURTMALAR"
        )

        return True


    if text == "📊 Statistika":

        await show_statistics(
            update
        )

        return True


    return False


# =========================================================
# MAIN MESSAGE HANDLER
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

        update.message.text

        or ""
    ).strip()


    # =====================================================
    # DISPATCHER BUTTONS
    # =====================================================

    dispatcher_buttons = [

        "🆕 Yangi buyurtmalar",

        "🟡 Qabul qilingan",

        "🔵 Ish jarayonida",

        "✅ Yakunlangan",

        "❌ Bekor qilingan",

        "🚫 Rad etilgan",

        "📋 Barcha buyurtmalar",

        "📊 Statistika",
    ]


    if text in dispatcher_buttons:

        if user_id != DISPATCHES_ID:

            await update.message.reply_text(

                "❌ Sizda dispetcher paneliga "
                "kirish huquqi yo‘q.",

                reply_markup=main_menu()
            )

            return


        await handle_dispatcher_menu(
            update,
            text
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
    # DISPATCHER COMMAND BUTTON
    # =====================================================

    if text == "🛠 Dispetcher":

        if user_id == DISPATCHES_ID:

            await dispatcher(
                update,
                context
            )

        return


    # =====================================================
    # NO ACTIVE ORDER
    # =====================================================

    if user_id not in user_orders:

        if user_id == DISPATCHES_ID:

            await update.message.reply_text(

                "🛠 Dispetcher paneliga kirish "
                "uchun /dispatcher buyrug‘ini bosing.",

                reply_markup=dispatcher_menu()
            )

        else:

            await update.message.reply_text(

                "Iltimos, menyudan kerakli "
                "xizmatni tanlang.",

                reply_markup=main_menu()
            )

        return


    order = user_orders[user_id]

    step = order.get(
        "step"
    )


    # =====================================================
    # NAME
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
    # PHONE
    # =====================================================

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
    # SERVICE
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

            "4️⃣ Manzilingizni yozing:\n\n"

            "Masalan:\n"

            "Andijon shahar, "
            "Boburshoh ko‘chasi, 15-uy"
        )

        return


    # =====================================================
    # ADDRESS
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

            "5️⃣ Buyurtma haqida qisqacha "
            "ma’lumot yozing:\n\n"

            "Masalan:\n"

            "Shkaf yig‘ish kerak.\n\n"

            "Yoki:\n"

            "Uy ko‘chirish kerak, 3-qavat."
        )

        return


    # =====================================================
    # DESCRIPTION
    # =====================================================

    if step == "description":

        if not text:

            await update.message.reply_text(

                "📝 Iltimos, buyurtma haqida "
                "qisqacha ma’lumot yozing."
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
                "Buyurtmani yuborishda XATO!"
            )


            await update.message.reply_text(

                "❌ Buyurtmani yuborishda "
                "xatolik yuz berdi.\n\n"

                "☎️ +998 77 069 00 03",

                reply_markup=main_menu()
            )

            return


        del user_orders[user_id]


        await update.message.reply_text(

            f"✅ Buyurtmangiz qabul qilindi!\n\n"

            f"🔢 Buyurtma №{order_id}\n\n"

            "👨‍🔧 Buyurtma ustalar guruhiga "
            "va dispetcherga yuborildi.\n\n"

            "📞 Tez orada siz bilan "
            "bog‘lanishadi.\n\n"

            "☎️ USTA 24: "
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
            "Telegram user topilmadi!"
        )


    if user.username:

        username = (
            f"@{user.username}"
        )

    else:

        username = "username yo‘q"


    # =====================================================
    # SAVE CUSTOMER
    # =====================================================

    await db_save_customer(

        telegram_id=user.id,

        name=order.get("name"),

        phone=order.get("phone"),

        username=username
    )


    # =====================================================
    # CREATE ORDER
    # =====================================================

    order_id = await db_create_order(

        customer_id=user.id,

        customer_name=order.get("name"),

        phone=order.get("phone"),

        service=order.get("service"),

        address=order.get("address"),

        description=order.get("description"),

        username=username
    )


    if not order_id:

        raise RuntimeError(
            "Buyurtma bazaga saqlanmadi!"
        )


    # =====================================================
    # MESSAGE
    # =====================================================

    message = (

        "🆕 YANGI BUYURTMA\n\n"

        f"🔢 Buyurtma: #{order_id}\n\n"

        f"👤 Mijoz: "
        f"{order.get('name', '-')}\n"

        f"📞 Telefon: "
        f"{order.get('phone', '-')}\n"

        f"🛠 Xizmat: "
        f"{order.get('service', '-')}\n"

        f"📍 Manzil: "
        f"{order.get('address', '-')}\n"

        f"📝 Izoh: "
        f"{order.get('description', '-')}\n\n"

        f"👤 Telegram: {username}\n"

        f"🆔 User ID: {user.id}\n\n"

        "🚨 Usta buyurtmani qabul qilish "
        "uchun tugmani bosing."
    )


    keyboard = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton(

                    "✅ Qabul qilish",

                    callback_data=
                    f"accept:{order_id}"
                ),

                InlineKeyboardButton(

                    "❌ Rad etish",

                    callback_data=
                    f"reject:{order_id}"
                ),

            ]

        ]
    )


    # =====================================================
    # SEND TO MASTERS
    # =====================================================

    sent_message = await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=message,

        reply_markup=keyboard
    )


    logger.info(

        "✅ Buyurtma #%s ustalar guruhiga yuborildi.",

        order_id
    )


    # =====================================================
    # SEND TO DISPATCHER
    # =====================================================

    dispatcher_text = (

        "📢 YANGI BUYURTMA\n\n"

        f"🔢 Buyurtma: #{order_id}\n\n"

        f"👤 Mijoz: "
        f"{order.get('name', '-')}\n"

        f"📞 Telefon: "
        f"{order.get('phone', '-')}\n"

        f"🛠 Xizmat: "
        f"{order.get('service', '-')}\n"

        f"📍 Manzil: "
        f"{order.get('address', '-')}\n"

        f"📝 Izoh: "
        f"{order.get('description', '-')}\n\n"

        f"👤 Telegram: {username}\n"

        f"🆔 User ID: {user.id}\n\n"

        "🆕 Holat: Yangi"
    )


    try:

        await context.bot.send_message(

            chat_id=DISPATCHES_ID,

            text=dispatcher_text
        )

        logger.info(
            "✅ Buyurtma #%s dispetcherga yuborildi.",
            order_id
        )

    except Exception:

        logger.exception(
            "Dispetcherga xabar yuborishda XATO!"
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


    await query.answer()


    data = (
        query.data
        or ""
    )


    if ":" not in data:
        return


    action, order_id_text = data.split(
        ":",
        1
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


    row = await db_get_order(
        order_id
    )


    if not row:

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

        master_name = (
            master.full_name
        )


    status = row["status"]


    # =====================================================
    # ACCEPT
    # =====================================================

    if action == "accept":

        if status != "open":

            await query.answer(

                "⚠️ Bu buyurtmani boshqa "
                "usta qabul qilgan.",

                show_alert=True
            )

            return


        await db_update_status(

            order_id,

            "accepted",

            master.id,

            master_name
        )


        group_text = (

            "🟡 BUYURTMA QABUL QILINDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Telefon: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Xizmat: "
            f"{row['service'] or '-'}\n"

            f"📍 Manzil: "
            f"{row['address'] or '-'}\n"

            f"📝 Izoh: "
            f"{row['description'] or '-'}\n\n"

            f"👨‍🔧 Qabul qilgan usta: "
            f"{master_name}\n\n"

            "🔵 Ishni boshlash uchun tugmani bosing."
        )


        keyboard = InlineKeyboardMarkup(

            [

                [

                    InlineKeyboardButton(

                        "🔵 Ishni boshlash",

                        callback_data=
                        f"startjob:{order_id}"
                    ),

                    InlineKeyboardButton(

                        "❌ Bekor qilish",

                        callback_data=
                        f"cancel:{order_id}"
                    ),

                ]

            ]
        )


        try:

            await query.edit_message_text(

                text=group_text,

                reply_markup=keyboard
            )

        except Exception:

            logger.exception(
                "Guruh xabarini yangilashda XATO!"
            )


        # MASTER MESSAGE

        try:

            await context.bot.send_message(

                chat_id=master.id,

                text=(

                    "🟡 BUYURTMA SIZGA BIRIKTIRILDI\n\n"

                    f"🔢 Buyurtma: #{order_id}\n\n"

                    f"👤 Mijoz: "
                    f"{row['customer_name'] or '-'}\n"

                    f"📞 Telefon: "
                    f"{row['phone'] or '-'}\n"

                    f"🛠 Xizmat: "
                    f"{row['service'] or '-'}\n"

                    f"📍 Manzil: "
                    f"{row['address'] or '-'}\n\n"

                    f"📝 Izoh:\n"
                    f"{row['description'] or '-'}\n\n"

                    "🔵 Ishni boshlash учун "
                    "tugmani bosing."
                )
            )

        except Exception:

            logger.warning(
                "Ustaga shaxsiy xabar yuborilmadi.",
                exc_info=True
            )


        # CUSTOMER

        try:

            await context.bot.send_message(

                chat_id=row["customer_id"],

                text=(

                    f"🟡 Buyurtmangiz №{order_id} "
                    "qabul qilindi.\n\n"

                    f"👨‍🔧 Usta: {master_name}\n\n"

                    "Tez orada usta ishni boshlaydi.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga qabul xabari yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "✅ Buyurtma sizga biriktirildi!"
        )

        return


    # =====================================================
    # START JOB
    # =====================================================

    if action == "startjob":

        if status != "accepted":

            await query.answer(

                "⚠️ Buyurtma ish boshlash "
                "holatida emas.",

                show_alert=True
            )

            return


        if row["master_id"] != master.id:

            await query.answer(

                "❌ Bu buyurtma sizga "
                "biriktirilmagan.",

                show_alert=True
            )

            return


        await db_update_status(

            order_id,

            "in_progress"
        )


        text = (

            "🔵 ISH JARAYONIDA\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Telefon: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Xizmat: "
            f"{row['service'] or '-'}\n"

            f"📍 Manzil: "
            f"{row['address'] or '-'}\n"

            f"📝 Izoh: "
            f"{row['description'] or '-'}\n\n"

            f"👨‍🔧 Usta: {master_name}\n\n"

            "Ish tugagach, "
            "«✅ Ishni yakunlash» tugmasini bosing."
        )


        keyboard = InlineKeyboardMarkup(

            [

                [

                    InlineKeyboardButton(

                        "✅ Ishni yakunlash",

                        callback_data=
                        f"complete:{order_id}"
                    ),

                    InlineKeyboardButton(

                        "❌ Bekor qilish",

                        callback_data=
                        f"cancel:{order_id}"
                    ),

                ]

            ]
        )


        try:

            await query.edit_message_text(

                text=text,

                reply_markup=keyboard
            )

        except Exception:

            logger.exception(
                "Ish jarayoni xabarini yangilashda XATO!"
            )


        try:

            await context.bot.send_message(

                chat_id=row["customer_id"],

                text=(

                    f"🔵 Buyurtmangiz №{order_id} "
                    "bo‘yicha ish boshlandi.\n\n"

                    f"👨‍🔧 Usta: {master_name}\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga ish boshlandi xabari yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "🔵 Ish boshlandi!"
        )

        return


    # =====================================================
    # COMPLETE
    # =====================================================

    if action == "complete":

        if status != "in_progress":

            await query.answer(

                "⚠️ Buyurtma ish "
                "jarayonida emas.",

                show_alert=True
            )

            return


        if row["master_id"] != master.id:

            await query.answer(

                "❌ Bu buyurtma sizga "
                "biriktirilmagan.",

                show_alert=True
            )

            return


        await db_update_status(

            order_id,

            "completed"
        )


        text = (

            "✅ ISH YAKUNLANDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Telefon: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Xizmat: "
            f"{row['service'] or '-'}\n"

            f"📍 Manzil: "
            f"{row['address'] or '-'}\n"

            f"📝 Izoh: "
            f"{row['description'] or '-'}\n\n"

            f"👨‍🔧 Usta: {master_name}\n\n"

            "📌 Holat: Yakunlandi\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        try:

            await query.edit_message_text(
                text=text
            )

        except Exception:

            logger.exception(
                "Yakunlangan xabarini yangilashda XATO!"
            )


        try:

            await context.bot.send_message(

                chat_id=row["customer_id"],

                text=(

                    f"✅ Buyurtmangiz №{order_id} "
                    "yakunlandi.\n\n"

                    f"👨‍🔧 Usta: {master_name}\n\n"

                    "Xizmat ko‘rsatish ishlari yakunlandi.\n\n"

                    "Rahmat! USTA 24 xizmatidan "
                    "foydalanganingiz uchun.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga yakun xabari yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "✅ Buyurtma yakunlandi!"
        )

        return


    # =====================================================
    # CANCEL
    # =====================================================

    if action == "cancel":

        if status not in [

            "accepted",

            "in_progress"

        ]:

            await query.answer(

                "⚠️ Bu buyurtmani hozir "
                "bekor qilib bo‘lmaydi.",

                show_alert=True
            )

            return


        if row["master_id"] != master.id:

            await query.answer(

                "❌ Bu buyurtma sizga "
                "biriktirilmagan.",

                show_alert=True
            )

            return


        await db_update_status(

            order_id,

            "cancelled"
        )


        text = (

            "❌ BUYURTMA BEKOR QILINDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Telefon: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Xizmat: "
            f"{row['service'] or '-'}\n"

            f"📍 Manzil: "
            f"{row['address'] or '-'}\n"

            f"📝 Izoh: "
            f"{row['description'] or '-'}\n\n"

            f"👨‍🔧 Usta: {master_name}\n\n"

            "📌 Holat: Bekor qilindi"
        )


        try:

            await query.edit_message_text(
                text=text
            )

        except Exception:

            logger.exception(
                "Bekor qilingan xabarini yangilashda XATO!"
            )


        try:

            await context.bot.send_message(

                chat_id=row["customer_id"],

                text=(

                    f"❌ Buyurtmangiz №{order_id} "
                    "bekor qilindi.\n\n"

                    f"👨‍🔧 Usta: {master_name}\n\n"

                    "Yangi buyurtma berishingiz mumkin.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga bekor xabari yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "❌ Buyurtma bekor qilindi!"
        )

        return


    # =====================================================
    # REJECT
    # =====================================================

    if action == "reject":

        if status != "open":

            await query.answer(

                "⚠️ Bu buyurtma allaqachon "
                "o‘zgargan.",

                show_alert=True
            )

            return


        await db_update_status(

            order_id,

            "rejected",

            master.id,

            master_name
        )


        text = (

            "🚫 BUYURTMA RAD ETILDI\n\n"

            f"🔢 Buyurtma: #{order_id}\n\n"

            f"👤 Mijoz: "
            f"{row['customer_name'] or '-'}\n"

            f"📞 Telefon: "
            f"{row['phone'] or '-'}\n"

            f"🛠 Xizmat: "
            f"{row['service'] or '-'}\n"

            f"📍 Manzil: "
            f"{row['address'] or '-'}\n"

            f"📝 Izoh: "
            f"{row['description'] or '-'}\n\n"

            f"🚫 Rad etgan usta: "
            f"{master_name}"
        )


        try:

            await query.edit_message_text(
                text=text
            )

        except Exception:

            logger.exception(
                "Rad xabarini yangilashda XATO!"
            )


        try:

            await context.bot.send_message(

                chat_id=row["customer_id"],

                text=(

                    f"⚠️ Buyurtmangiz №{order_id} "
                    "tanlangan usta tomonidan "
                    "qabul qilinmadi.\n\n"

                    "Dispetcher boshqa usta topishga "
                    "harakat qiladi.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                )
            )

        except Exception:

            logger.warning(
                "Mijozga rad xabari yuborilmadi.",
                exc_info=True
            )


        await query.answer(
            "🚫 Buyurtma rad etildi."
        )

        return


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "❌ BOT XATOSI: %s",
        context.error,
        exc_info=context.error
    )


# =========================================================
# RUN BOT
# =========================================================

async def run_bot(
    application: Application
):

    await application.initialize()

    await init_database()

    await application.start()

    try:

        await application.updater.start_polling(

            allowed_updates=Update.ALL_TYPES,

            drop_pending_updates=True
        )


        logger.info(
            "✅ Telegram polling ishga tushdi."
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
        "========================================"
    )

    logger.info(
        "USTA 24 BOT START"
    )

    logger.info(
        "MASTERS_GROUP_ID = %s",
        MASTERS_GROUP_ID
    )

    logger.info(
        "DISPATCHES_ID = %s",
        DISPATCHES_ID
    )

    logger.info(
        "DATABASE_URL mavjud: %s",
        bool(DATABASE_URL)
    )

    logger.info(
        "========================================"
    )


    application = (

        Application.builder()

        .token(BOT_TOKEN)

        .build()
    )


    # =====================================================
    # COMMANDS
    # =====================================================

    application.add_handler(

        CommandHandler(
            "start",
            start
        )
    )


    application.add_handler(

        CommandHandler(
            "dispatcher",
            dispatcher
        )
    )


    application.add_handler(

        CommandHandler(
            "id",
            chat_id_command
        )
    )


    # =====================================================
    # CALLBACK
    # =====================================================

    application.add_handler(

        CallbackQueryHandler(
            order_callback
        )
    )


    # =====================================================
    # CONTACT
    # =====================================================

    application.add_handler(

        MessageHandler(
            filters.CONTACT,
            handle_message
        )
    )


    # =====================================================
    # TEXT
    # =====================================================

    application.add_handler(

        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )


    # =====================================================
    # ERROR
    # =====================================================

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


    # =====================================================
    # BOT
    # =====================================================

    asyncio.run(
        run_bot(
            application
        )
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
