import os
import asyncio
import logging
from datetime import datetime, timedelta
from threading import Thread
from io import BytesIO

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
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
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID.strip())
    ADMIN_ID = int(ADMIN_ID.strip())
except ValueError:
    raise RuntimeError(
        "MASTERS_GROUP_ID va ADMIN_ID raqam bo‘lishi kerak!"
    )


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("usta24")


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
    port = int(os.getenv("PORT", "10000"))

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

    if not DATABASE_URL:
        logger.warning(
            "DATABASE_URL topilmadi. Memory rejimida ishlaydi."
        )
        return

    try:
        import asyncpg

        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
        )

        async with db_pool.acquire() as conn:

            # -------------------------------------------------
            # CUSTOMERS
            # -------------------------------------------------

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    username TEXT,
                    address TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_order_at TIMESTAMP
                )
                """
            )

            # -------------------------------------------------
            # MASTERS
            # -------------------------------------------------

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS masters (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    username TEXT,
                    phone TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )

            # -------------------------------------------------
            # ORDERS
            # -------------------------------------------------

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

                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,

                    username TEXT,

                    status TEXT NOT NULL DEFAULT 'open',

                    master_id BIGINT,
                    master_name TEXT,

                    price NUMERIC DEFAULT 0,

                    created_at TIMESTAMP DEFAULT NOW(),
                    accepted_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    rejected_at TIMESTAMP
                )
                """
            )

            # -------------------------------------------------
            # RATINGS
            # -------------------------------------------------

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ratings (
                    id SERIAL PRIMARY KEY,

                    order_id INTEGER UNIQUE NOT NULL,
                    customer_id BIGINT NOT NULL,
                    master_id BIGINT,

                    rating INTEGER NOT NULL,
                    review TEXT,

                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )

            # -------------------------------------------------
            # SERVICES
            # -------------------------------------------------

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    base_price NUMERIC DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE
                )
                """
            )

            # -------------------------------------------------
            # REMINDERS
            # -------------------------------------------------

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,

                    order_id INTEGER NOT NULL,
                    customer_id BIGINT NOT NULL,

                    reminder_type TEXT,
                    sent BOOLEAN DEFAULT FALSE,

                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )

            # -------------------------------------------------
            # DEFAULT SERVICES
            # -------------------------------------------------

            default_services = [
                ("🪑 Mebel", 0),
                ("🚚 Yuk tashish / ko‘chirish", 0),
                ("🔩 Santexnika", 0),
                ("⚡ Elektr", 0),
                ("🔥 Payvandlash", 0),
                ("🔨 Boshqa xizmat", 0),
            ]

            for service_name, price in default_services:
                await conn.execute(
                    """
                    INSERT INTO services
                        (name, base_price)
                    VALUES
                        ($1, $2)
                    ON CONFLICT (name)
                    DO NOTHING
                    """,
                    service_name,
                    price,
                )

        logger.info("PostgreSQL ulandi.")

    except Exception as e:
        logger.exception(
            "PostgreSQL xatosi: %s",
            e
        )
        db_pool = None


# =========================================================
# CUSTOMER DATABASE
# =========================================================

async def db_save_customer(
    telegram_id,
    name=None,
    phone=None,
    username=None,
    address=None,
    latitude=None,
    longitude=None,
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
                    address,
                    latitude,
                    longitude,
                    last_order_at
                )
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,NOW()
                )

                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    name = COALESCE($2, customers.name),
                    phone = COALESCE($3, customers.phone),
                    username = COALESCE($4, customers.username),
                    address = COALESCE($5, customers.address),
                    latitude = COALESCE($6, customers.latitude),
                    longitude = COALESCE($7, customers.longitude),
                    last_order_at = NOW()
                """,
                telegram_id,
                name,
                phone,
                username,
                address,
                latitude,
                longitude,
            )

    except Exception:
        logger.exception(
            "Mijoz saqlashda xato."
        )


async def db_get_customer(telegram_id):
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
                telegram_id,
            )

    except Exception:
        logger.exception(
            "Mijoz olishda xato."
        )

        return None


# =========================================================
# MASTER DATABASE
# =========================================================

async def db_add_master(
    telegram_id,
    name,
    username=None,
    phone=None,
):
    if not db_pool:
        return False

    try:
        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO masters (
                    telegram_id,
                    name,
                    username,
                    phone,
                    active
                )
                VALUES ($1,$2,$3,$4,TRUE)

                ON CONFLICT (telegram_id)
                DO UPDATE SET
                    name = $2,
                    username = $3,
                    phone = $4,
                    active = TRUE
                """,
                telegram_id,
                name,
                username,
                phone,
            )

        return True

    except Exception:
        logger.exception(
            "Usta qo‘shishda xato."
        )

        return False


async def db_remove_master(telegram_id):
    if not db_pool:
        return False

    try:
        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                UPDATE masters
                SET active = FALSE
                WHERE telegram_id = $1
                """,
                telegram_id,
            )

        return True

    except Exception:
        logger.exception(
            "Ustani o‘chirishda xato."
        )

        return False


async def db_get_masters():
    if not db_pool:
        return []

    try:
        async with db_pool.acquire() as conn:

            return await conn.fetch(
                """
                SELECT *
                FROM masters
                ORDER BY id DESC
                """
            )

    except Exception:
        logger.exception(
            "Ustalarni olishda xato."
        )

        return []


async def db_get_master(telegram_id):
    if not db_pool:
        return None

    try:
        async with db_pool.acquire() as conn:

            return await conn.fetchrow(
                """
                SELECT *
                FROM masters
                WHERE telegram_id = $1
                """,
                telegram_id,
            )

    except Exception:
        return None


# =========================================================
# ORDER DATABASE
# =========================================================

async def db_create_order(order):

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
                    latitude,
                    longitude,
                    username,
                    status,
                    price
                )
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,'open',$10
                )
                RETURNING id
                """,
                order["customer_id"],
                order["name"],
                order["phone"],
                order["service"],
                order["address"],
                order["description"],
                order.get("latitude"),
                order.get("longitude"),
                order["username"],
                order.get("price", 0),
            )

            return int(order_id)

    except Exception:
        logger.exception(
            "Order yaratishda xato."
        )

        return None


async def db_get_order(order_id):

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
                order_id,
            )

    except Exception:
        return None


async def db_get_orders(status=None):

    if not db_pool:
        return []

    try:
        async with db_pool.acquire() as conn:

            if status:

                return await conn.fetch(
                    """
                    SELECT *
                    FROM orders
                    WHERE status = $1
                    ORDER BY id DESC
                    """,
                    status,
                )

            return await conn.fetch(
                """
                SELECT *
                FROM orders
                ORDER BY id DESC
                """
            )

    except Exception:
        logger.exception(
            "Buyurtmalarni olishda xato."
        )

        return []


async def db_update_status(
    order_id,
    status,
    master_id=None,
    master_name=None,
):

    if not db_pool:
        return

    timestamp_column = {
        "accepted": "accepted_at",
        "in_progress": "started_at",
        "completed": "completed_at",
        "cancelled": "cancelled_at",
        "rejected": "rejected_at",
    }.get(status)

    try:

        async with db_pool.acquire() as conn:

            if timestamp_column:

                await conn.execute(
                    f"""
                    UPDATE orders
                    SET
                        status = $1,
                        master_id = COALESCE($2, master_id),
                        master_name = COALESCE($3, master_name),
                        {timestamp_column} = NOW()
                    WHERE id = $4
                    """,
                    status,
                    master_id,
                    master_name,
                    order_id,
                )

            else:

                await conn.execute(
                    """
                    UPDATE orders
                    SET
                        status = $1,
                        master_id = COALESCE($2, master_id),
                        master_name = COALESCE($3, master_name)
                    WHERE id = $4
                    """,
                    status,
                    master_id,
                    master_name,
                    order_id,
                )

    except Exception:
        logger.exception(
            "Order status xatosi."
        )


async def db_update_price(
    order_id,
    price,
):

    if not db_pool:
        return

    try:

        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                UPDATE orders
                SET price = $1
                WHERE id = $2
                """,
                price,
                order_id,
            )

    except Exception:
        logger.exception(
            "Narx saqlashda xato."
        )


# =========================================================
# RATING
# =========================================================

async def db_save_rating(
    order_id,
    customer_id,
    master_id,
    rating,
    review,
):

    if not db_pool:
        return False

    try:

        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO ratings (
                    order_id,
                    customer_id,
                    master_id,
                    rating,
                    review
                )
                VALUES ($1,$2,$3,$4,$5)

                ON CONFLICT (order_id)
                DO UPDATE SET
                    rating = $4,
                    review = $5
                """,
                order_id,
                customer_id,
                master_id,
                rating,
                review,
            )

        return True

    except Exception:
        logger.exception(
            "Rating saqlashda xato."
        )

        return False


# =========================================================
# STATISTICS
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
                SELECT status, COUNT(*) AS count
                FROM orders
                GROUP BY status
                """
            )

            for row in rows:

                status = row["status"]
                count = int(row["count"])

                if status in result:
                    result[status] = count

                result["total"] += count

        return result

    except Exception:
        logger.exception(
            "Statistika xatosi."
        )

        return result


async def db_master_statistics(master_id):

    result = {
        "total": 0,
        "completed": 0,
        "cancelled": 0,
        "rating": 0,
        "rating_count": 0,
    }

    if not db_pool:
        return result

    try:

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                    ) AS completed,
                    COUNT(*) FILTER (
                        WHERE status = 'cancelled'
                    ) AS cancelled
                FROM orders
                WHERE master_id = $1
                """,
                master_id,
            )

            result["total"] = int(row["total"])
            result["completed"] = int(row["completed"])
            result["cancelled"] = int(row["cancelled"])

            rating_row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(AVG(rating),0) AS rating,
                    COUNT(*) AS count
                FROM ratings
                WHERE master_id = $1
                """,
                master_id,
            )

            result["rating"] = float(
                rating_row["rating"]
            )

            result["rating_count"] = int(
                rating_row["count"]
            )

        return result

    except Exception:
        logger.exception(
            "Usta statistikasi xatosi."
        )

        return result


# =========================================================
# MEMORY
# =========================================================

user_orders = {}
memory_orders = {}
memory_order_counter = 0


# =========================================================
# MENUS
# =========================================================

def main_menu():

    return ReplyKeyboardMarkup(
        [
            ["🛠 Usta chaqirish"],
            ["🔁 Qayta buyurtma"],
            ["📋 Xizmatlar", "📞 Aloqa"],
        ],
        resize_keyboard=True,
    )


def dispatcher_menu():

    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar"],
            ["🟡 Qabul qilingan"],
            ["🔵 Ish jarayonida"],
            ["✅ Yakunlangan"],
            ["❌ Bekor qilingan"],
            ["🚫 Rad etilgan"],
            ["📋 Barcha buyurtmalar"],
            ["👨‍🔧 Ustalar"],
            ["📊 Statistika"],
            ["📈 Hisobot"],
            ["📢 Xabar tarqatish"],
        ],
        resize_keyboard=True,
    )


def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Usta qo‘shish"],
            ["🗑 Usta o‘chirish"],
            ["👨‍🔧 Ustalar"],
            ["💰 Narxlar"],
            ["📊 Usta statistikasi"],
            ["📥 Excel"],
            ["👑 Админ панель"],
            ["⬅️ Асосий меню"],
        ],
        resize_keyboard=True,
    )


def service_menu():

    return ReplyKeyboardMarkup(
        [
            ["🪑 Mebel"],
            ["🚚 Yuk tashish / ko‘chirish"],
            ["🔩 Santexnika"],
            ["⚡ Elektr"],
            ["🔥 Payvandlash"],
            ["🔨 Boshqa xizmat"],
        ],
        resize_keyboard=True,
    )


def location_menu():

    button = KeyboardButton(
        "📍 Геолокациямни юбориш",
        request_location=True,
    )

    return ReplyKeyboardMarkup(
        [
            [button],
            ["✍️ Манзилни қўлда ёзиш"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 хизматларига хуш келибсиз!\n\n"
        "🔧 Уй ва офис учун профессионал усталар.\n"
        "📍 Андижон шаҳри\n\n"
        "Керакли хизматни танланг:",
        reply_markup=main_menu(),
    )


# =========================================================
# DISPATCHER
# =========================================================

async def dispatcher(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сизда диспетчер панелига кириш ҳуқуқи йўқ."
        )

        return

    await update.message.reply_text(
        "👑 USTA 24 ДИСПЕТЧЕР ПАНЕЛИ\n\n"
        "Керакли бўлимни танланг:",
        reply_markup=dispatcher_menu(),
    )


# =========================================================
# ADMIN
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Фақат админ."
        )

        return

    await update.message.reply_text(
        "👑 USTA 24 АДМИН БОШҚАРУВИ",
        reply_markup=admin_menu(),
    )


# =========================================================
# CHAT ID
# =========================================================

async def chat_id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "🛠 USTA 24 ХИЗМАТЛАРИ\n\n"

        "🪑 Мебель:\n"
        "• Мебель йиғиш\n"
        "• Мебель таъмирлаш\n"
        "• Ошхона мебели\n"
        "• Шкаф\n"
        "• Кровать\n"
        "• Стол ва стул\n"
        "• Мебельни ажратиш/йиғиш\n"
        "• Мебель ташиш\n\n"

        "🚚 Юк ташиш / уй кўчириш\n"
        "🔩 Сантехника\n"
        "⚡ Электр\n"
        "🔥 Пайвандлаш\n"
        "🔨 Бошқа хизматлар",
        reply_markup=main_menu(),
    )


# =========================================================
# CONTACT
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "☎️ +998 77 069 00 03\n"
        "📍 Андижон шаҳри\n\n"
        "🛠 Уста чақириш учун "
        "«🛠 Usta chaqirish» тугмасини босинг.",
        reply_markup=main_menu(),
    )


# =========================================================
# START ORDER
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    customer = await db_get_customer(user.id)

    if (
        customer
        and customer["name"]
        and customer["phone"]
    ):

        user_orders[user.id] = {
            "step": "service",

            "name": customer["name"],
            "phone": customer["phone"],

            "address": customer["address"],
            "latitude": customer["latitude"],
            "longitude": customer["longitude"],
        }

        await update.message.reply_text(
            f"👋 Салом, {customer['name']}!\n\n"
            "Сизни эсладик. ✅\n\n"
            "🛠 Қандай хизмат керак?",
            reply_markup=service_menu(),
        )

        return

    user_orders[user.id] = {
        "step": "name"
    }

    await update.message.reply_text(
        "📝 БУЮРТМА БЕРИШ\n\n"
        "1️⃣ Мижоз исмингизни ёзинг:"
    )


# =========================================================
# REPEAT ORDER
# =========================================================

async def repeat_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    customer = await db_get_customer(user.id)

    if not customer:

        await update.message.reply_text(
            "📭 Сизда аввалги буюртма топилмади.\n\n"
            "🛠 Янги буюртма беринг.",
            reply_markup=main_menu(),
        )

        return

    user_orders[user.id] = {
        "step": "service",

        "name": customer["name"],
        "phone": customer["phone"],

        "address": customer["address"],
        "latitude": customer["latitude"],
        "longitude": customer["longitude"],
    }

    await update.message.reply_text(
        "🔁 ҚАЙТА БУЮРТМА\n\n"
        "🛠 Қайси хизмат керак?",
        reply_markup=service_menu(),
    )


# =========================================================
# FORMAT ORDER
# =========================================================

def format_order(order):

    if isinstance(order, dict):

        order_id = order.get("id", "-")
        name = order.get("name", "-")
        phone = order.get("phone", "-")
        service = order.get("service", "-")
        address = order.get("address", "-")
        description = order.get("description", "-")
        master = order.get("master_name") or "-"
        status = order.get("status", "-")
        price = order.get("price", 0)

    else:

        order_id = order["id"]
        name = order["customer_name"] or "-"
        phone = order["phone"] or "-"
        service = order["service"] or "-"
        address = order["address"] or "-"
        description = order["description"] or "-"
        master = order["master_name"] or "-"
        status = order["status"]
        price = order["price"] or 0

    return (
        f"🔢 Буюртма: #{order_id}\n"
        f"👤 Мижоз: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"🛠 Хизмат: {service}\n"
        f"📍 Манзил: {address}\n"
        f"📝 Изоҳ: {description}\n"
        f"👨‍🔧 Уста: {master}\n"
        f"💰 Нарх: {price}\n"
        f"📌 Ҳолат: {status}\n"
        "──────────────"
    )


# =========================================================
# SEND ORDER TO MASTERS
# =========================================================

async def send_order_to_masters(
    update,
    context,
    order,
):

    global memory_order_counter

    user = update.effective_user

    if not user:
        raise RuntimeError(
            "Telegram user topilmadi!"
        )

    username = (
        f"@{user.username}"
        if user.username
        else "username yo‘q"
    )

    order["customer_id"] = user.id
    order["username"] = username

    await db_save_customer(
        user.id,
        order.get("name"),
        order.get("phone"),
        username,
        order.get("address"),
        order.get("latitude"),
        order.get("longitude"),
    )

    db_order_id = await db_create_order(order)

    if db_order_id:

        order_id = db_order_id

    else:

        memory_order_counter += 1
        order_id = memory_order_counter

    memory_orders[order_id] = {
        "customer_id": user.id,
        "status": "open",
        "master_id": None,
        "master_name": None,
        "order": order.copy(),
    }

    location_text = ""

    if (
        order.get("latitude")
        and order.get("longitude")
    ):

        location_text = (
            f"\n📍 Геолокация:\n"
            f"https://maps.google.com/?q="
            f"{order['latitude']},{order['longitude']}\n"
        )

    message = (
        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 Буюртма: #{order_id}\n\n"

        f"👤 Мижоз: {order.get('name', '-')}\n"
        f"📞 Телефон: {order.get('phone', '-')}\n"
        f"🛠 Хизмат: {order.get('service', '-')}\n"
        f"📍 Манзил: {order.get('address', '-')}\n"
        f"📝 Изоҳ: {order.get('description', '-')}\n"
        f"💰 Нарх асоси: {order.get('price', 0)}\n"

        f"{location_text}\n"

        f"👤 Telegram: {username}\n"
        f"🆔 User ID: {user.id}\n\n"

        "🚨 Уста буюртмани қабул қилиши мумкин."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Қабул қилиш",
                    callback_data=f"accept:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ Рад этиш",
                    callback_data=f"reject:{order_id}",
                ),
            ]
        ]
    )

    sent = await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=message,
        reply_markup=keyboard,
    )

    memory_orders[order_id]["message_id"] = (
        sent.message_id
    )

    logger.info(
        "Buyurtma #%s ustalar guruhiga yuborildi.",
        order_id,
    )

    return order_id


# =========================================================
# CALLBACK
# =========================================================

async def order_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    if ":" not in data:
        await query.answer()
        return

    action, order_id_text = data.split(":", 1)

    try:
        order_id = int(order_id_text)
    except ValueError:
        await query.answer(
            "❌ Буюртма рақами нотўғри.",
            show_alert=True,
        )
        return

    order_data = memory_orders.get(order_id)

    if not order_data:

        row = await db_get_order(order_id)

        if row:

            order_data = {
                "customer_id": row["customer_id"],
                "status": row["status"],
                "master_id": row["master_id"],
                "master_name": row["master_name"],

                "order": {
                    "name": row["customer_name"],
                    "phone": row["phone"],
                    "service": row["service"],
                    "address": row["address"],
                    "description": row["description"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "price": row["price"],
                },
            }

            memory_orders[order_id] = order_data

    if not order_data:

        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True,
        )

        return

    master = query.from_user

    master_name = (
        f"@{master.username}"
        if master.username
        else master.full_name
    )

    order_info = order_data["order"]

    # =====================================================
    # ACCEPT
    # =====================================================

    if action == "accept":

        await query.answer()

        if order_data["status"] != "open":

            await query.answer(
                "⚠️ Бу буюртмани бошқа уста қабул қилган.",
                show_alert=True,
            )

            return

        # Фақат фаол уста қабул қила олади
        master_record = await db_get_master(master.id)

        if db_pool and (
            not master_record
            or not master_record["active"]
        ):

            await query.answer(
                "❌ Сиз уста сифатида рўйхатдан ўтмагансиз.",
                show_alert=True,
            )

            return

        order_data["status"] = "accepted"
        order_data["master_id"] = master.id
        order_data["master_name"] = master_name

        await db_update_status(
            order_id,
            "accepted",
            master.id,
            master_name,
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔵 Ишни бошлаш",
                        callback_data=f"startjob:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "🔄 Бошқа устага бериш",
                        callback_data=f"reassign:{order_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel:{order_id}",
                    ),
                ],
            ]
        )

        await query.edit_message_text(
            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
            + format_order(
                {
                    "id": order_id,
                    "name": order_info.get("name"),
                    "phone": order_info.get("phone"),
                    "service": order_info.get("service"),
                    "address": order_info.get("address"),
                    "description": order_info.get("description"),
                    "master_name": master_name,
                    "price": order_info.get("price", 0),
                    "status": "accepted",
                }
            ),
            reply_markup=keyboard,
        )

        # Устага
        try:

            await context.bot.send_message(
                chat_id=master.id,
                text=(
                    "🟡 БУЮРТМА СИЗГА БИРИКТИРИЛДИ\n\n"
                    f"🔢 Буюртма: #{order_id}\n"
                    f"👤 Мижоз: {order_info.get('name', '-')}\n"
                    f"📞 Телефон: {order_info.get('phone', '-')}\n"
                    f"🛠 Хизмат: {order_info.get('service', '-')}\n"
                    f"📍 Манзил: {order_info.get('address', '-')}\n"
                    f"📝 Изоҳ: {order_info.get('description', '-')}\n\n"
                    "🔵 Ишни бошлаш тугмаси гуруҳда."
                ),
            )

        except Exception:
            logger.warning(
                "Ustaga shaxsiy xabar yuborilmadi.",
                exc_info=True,
            )

        # Мижозга
        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "Тез орада иш бошланади.\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )

        except Exception:
            logger.warning(
                "Mijozga xabar yuborilmadi.",
                exc_info=True,
            )

        return

    # =====================================================
    # REASSIGN
    # =====================================================

    if action == "reassign":

        await query.answer(
            "🔄 Буюртма қайта тақсимлаш учун белгиланди."
        )

        if order_data["status"] != "accepted":

            return

        # Очиқ ҳолатга қайтариш
        order_data["status"] = "open"
        order_data["master_id"] = None
        order_data["master_name"] = None

        await db_update_status(
            order_id,
            "open",
            None,
            None,
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Қабул қилиш",
                        callback_data=f"accept:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Рад этиш",
                        callback_data=f"reject:{order_id}",
                    ),
                ]
            ]
        )

        await query.edit_message_reply_markup(
            reply_markup=keyboard
        )

        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"🔄 Буюртма №{order_id} бошқа устага "
                    "берилмоқда.\n\n"
                    "Яқин орада янги уста бириктирилади."
                ),
            )

        except Exception:
            pass

        return

    # =====================================================
    # START JOB
    # =====================================================

    if action == "startjob":

        await query.answer()

        if order_data["status"] != "accepted":

            await query.answer(
                "⚠️ Буюртма иш бошлаш ҳолатида эмас.",
                show_alert=True,
            )

            return

        if order_data.get("master_id") != master.id:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )

            return

        order_data["status"] = "in_progress"

        await db_update_status(
            order_id,
            "in_progress",
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ишни якунлаш",
                        callback_data=f"complete:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel:{order_id}",
                    ),
                ]
            ]
        )

        await query.edit_message_text(
            "🔵 ИШ ЖАРАЁНИДА\n\n"
            + format_order(
                {
                    "id": order_id,
                    "name": order_info.get("name"),
                    "phone": order_info.get("phone"),
                    "service": order_info.get("service"),
                    "address": order_info.get("address"),
                    "description": order_info.get("description"),
                    "master_name": master_name,
                    "price": order_info.get("price", 0),
                    "status": "in_progress",
                }
            ),
            reply_markup=keyboard,
        )

        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"🔵 Буюртмангиз №{order_id} бўйича "
                    "иш бошланди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )

        except Exception:
            pass

        return

    # =====================================================
    # COMPLETE
    # =====================================================

    if action == "complete":

        await query.answer()

        if order_data["status"] != "in_progress":

            await query.answer(
                "⚠️ Буюртма иш жараёнида эмас.",
                show_alert=True,
            )

            return

        if order_data.get("master_id") != master.id:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )

            return

        order_data["status"] = "completed"

        await db_update_status(
            order_id,
            "completed",
        )

        await query.edit_message_text(
            "✅ ИШ ЯКУНЛАНДИ\n\n"
            + format_order(
                {
                    "id": order_id,
                    "name": order_info.get("name"),
                    "phone": order_info.get("phone"),
                    "service": order_info.get("service"),
                    "address": order_info.get("address"),
                    "description": order_info.get("description"),
                    "master_name": master_name,
                    "price": order_info.get("price", 0),
                    "status": "completed",
                }
            )
        )

        # Мижозга рейтинг
        rating_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐",
                        callback_data=f"rate:{order_id}:1",
                    ),
                    InlineKeyboardButton(
                        "⭐⭐",
                        callback_data=f"rate:{order_id}:2",
                    ),
                    InlineKeyboardButton(
                        "⭐⭐⭐",
                        callback_data=f"rate:{order_id}:3",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⭐⭐⭐⭐",
                        callback_data=f"rate:{order_id}:4",
                    ),
                    InlineKeyboardButton(
                        "⭐⭐⭐⭐⭐",
                        callback_data=f"rate:{order_id}:5",
                    ),
                ],
            ]
        )

        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"✅ Буюртмангиз №{order_id} якунланди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "⭐ Илтимос, хизматни баҳоланг:"
                ),
                reply_markup=rating_keyboard,
            )

        except Exception:
            pass

        return

    # =====================================================
    # CANCEL
    # =====================================================

    if action == "cancel":

        await query.answer()

        if order_data["status"] not in (
            "accepted",
            "in_progress",
        ):

            await query.answer(
                "⚠️ Бу буюртмани бекор қилиб бўлмайди.",
                show_alert=True,
            )

            return

        if order_data.get("master_id") != master.id:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )

            return

        order_data["status"] = "cancelled"

        await db_update_status(
            order_id,
            "cancelled",
        )

        await query.edit_message_text(
            "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"
            + format_order(
                {
                    "id": order_id,
                    "name": order_info.get("name"),
                    "phone": order_info.get("phone"),
                    "service": order_info.get("service"),
                    "address": order_info.get("address"),
                    "description": order_info.get("description"),
                    "master_name": master_name,
                    "price": order_info.get("price", 0),
                    "status": "cancelled",
                }
            )
        )

        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"❌ Буюртмангиз №{order_id} бекор қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "Янги буюртма беришингиз мумкин.\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )

        except Exception:
            pass

        return

    # =====================================================
    # REJECT
    # =====================================================

    if action == "reject":

        await query.answer()

        if order_data["status"] != "open":

            await query.answer(
                "⚠️ Бу буюртма аллақачон ўзгарган.",
                show_alert=True,
            )

            return

        order_data["status"] = "rejected"
        order_data["master_id"] = master.id
        order_data["master_name"] = master_name

        await db_update_status(
            order_id,
            "rejected",
            master.id,
            master_name,
        )

        await query.edit_message_text(
            "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
            + format_order(
                {
                    "id": order_id,
                    "name": order_info.get("name"),
                    "phone": order_info.get("phone"),
                    "service": order_info.get("service"),
                    "address": order_info.get("address"),
                    "description": order_info.get("description"),
                    "master_name": master_name,
                    "price": order_info.get("price", 0),
                    "status": "rejected",
                }
            )
        )

        try:

            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"⚠️ Буюртмангиз №{order_id} "
                    "ушбу уста томонидан қабул қилинмади.\n\n"
                    "Бошқа уста топиш учун диспетчер "
                    "буюртмани қайта тақсимлайди.\n\n"
                    "☎️ +998 77 069 00 03"
                ),
            )

        except Exception:
            pass

        return

    # =====================================================
    # RATING
    # =====================================================

    if action == "rate":

        parts = data.split(":")

        if len(parts) != 3:
            return

        try:
            rating = int(parts[2])
        except ValueError:
            return

        customer = query.from_user

        if customer.id != order_data["customer_id"]:

            await query.answer(
                "❌ Бу рейтинг сиз учун эмас.",
                show_alert=True,
            )

            return

        await db_save_rating(
            order_id,
            customer.id,
            order_data.get("master_id"),
            rating,
            None,
        )

        user_orders[customer.id] = {
            "step": "review",
            "review_order_id": order_id,
            "review_rating": rating,
        }

        await query.answer(
            "⭐ Рейтинг сақланди."
        )

        await context.bot.send_message(
            chat_id=customer.id,
            text=(
                f"⭐ Сиз {rating}/5 баҳо бердингиз.\n\n"
                "💬 Энди хизмат ҳақида қисқача фикрингизни "
                "ёзинг.\n\n"
                "Агар изоҳ қолдиришни истамасангиз: - "
            ),
        )

        return


# =========================================================
# SHOW ORDERS
# =========================================================

async def show_orders(
    update,
    status=None,
    title="📋 БУЮРТМАЛАР",
):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Бу бўлим фақат админ учун."
        )

        return

    orders = await db_get_orders(status)

    if not orders:

        await update.message.reply_text(
            "📭 Ҳозирча буюртмалар йўқ.",
            reply_markup=dispatcher_menu(),
        )

        return

    text = f"{title}\n\n"

    for order in orders[:30]:

        text += (
            format_order(order)
            + "\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=dispatcher_menu(),
    )


# =========================================================
# STATISTICS
# =========================================================

async def show_statistics(update):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Фақат админ."
        )

        return

    stats = await db_statistics()

    await update.message.reply_text(
        "📊 USTA 24 ТЎЛИҚ СТАТИСТИКА\n\n"

        f"📋 Жами: {stats['total']}\n\n"

        f"🆕 Янги: {stats['open']}\n"
        f"🟡 Қабул қилинган: {stats['accepted']}\n"
        f"🔵 Иш жараёнида: {stats['in_progress']}\n"
        f"✅ Якунланган: {stats['completed']}\n"
        f"❌ Бекор қилинган: {stats['cancelled']}\n"
        f"🚫 Рад этилган: {stats['rejected']}",
        reply_markup=dispatcher_menu(),
    )


# =========================================================
# MASTER LIST
# =========================================================

async def show_masters(update):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Фақат админ."
        )

        return

    masters = await db_get_masters()

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Ҳозирча усталар базаси бўш.",
            reply_markup=admin_menu(),
        )

        return

    text = "👨‍🔧 УСТАЛАР\n\n"

    for master in masters:

        status = (
            "🟢 Фаол"
            if master["active"]
            else "🔴 Нофаол"
        )

        username = (
            f"@{master['username']}"
            if master["username"]
            else "-"
        )

        text += (
            f"👨‍🔧 {master['name']}\n"
            f"🆔 {master['telegram_id']}\n"
            f"👤 {username}\n"
            f"📞 {master['phone'] or '-'}\n"
            f"{status}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# MASTER STATISTICS
# =========================================================

async def show_master_statistics(update):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Фақат админ."
        )
        return

    masters = await db_get_masters()

    if not masters:

        await update.message.reply_text(
            "📭 Усталар йўқ."
        )

        return

    text = "👨‍🔧 УСТАЛАР СТАТИСТИКАСИ\n\n"

    for master in masters:

        stats = await db_master_statistics(
            master["telegram_id"]
        )

        text += (
            f"👨‍🔧 {master['name']}\n"
            f"📋 Буюртмалар: {stats['total']}\n"
            f"✅ Якунланган: {stats['completed']}\n"
            f"❌ Бекор қилинган: {stats['cancelled']}\n"
            f"⭐ Рейтинг: "
            f"{stats['rating']:.1f}/5 "
            f"({stats['rating_count']} та)\n"
            "──────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# EXCEL
# =========================================================

async def export_excel(update):

    if not update.message:
        return

    user = update.effective_user

    if not user or user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Фақат админ."
        )

        return

    try:

        from openpyxl import Workbook

        orders = await db_get_orders()

        workbook = Workbook()

        sheet = workbook.active
        sheet.title = "USTA24 Orders"

        headers = [
            "ID",
            "Mijoz",
            "Telefon",
            "Xizmat",
            "Manzil",
            "Izoh",
            "Usta",
            "Holat",
            "Narx",
            "Sana",
        ]

        sheet.append(headers)

        for order in orders:

            sheet.append(
                [
                    order["id"],
                    order["customer_name"],
                    order["phone"],
                    order["service"],
                    order["address"],
                    order["description"],
                    order["master_name"],
                    order["status"],
                    float(order["price"] or 0),
                    str(order["created_at"]),
                ]
            )

        file = BytesIO()

        workbook.save(file)

        file.seek(0)

        file.name = "usta24_report.xlsx"

        await update.message.reply_document(
            document=file,
            caption="📥 USTA 24 Excel ҳисобот",
        )

    except Exception:

        logger.exception(
            "Excel export xatosi."
        )

        await update.message.reply_text(
            "❌ Excel тайёрлашда хатолик.\n\n"
            "openpyxl ўрнатилганини текширинг."
        )


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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
    # LOCATION
    # =====================================================

    if update.message.location:

        if user_id not in user_orders:
            return

        order = user_orders[user_id]

        location = update.message.location

        order["latitude"] = location.latitude
        order["longitude"] = location.longitude

        order["address"] = (
            f"Геолокация: "
            f"{location.latitude}, "
            f"{location.longitude}"
        )

        order["step"] = "description"

        await update.message.reply_text(
            "📍 Геолокация қабул қилинди. ✅\n\n"
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
        )

        return

    # =====================================================
    # DISPATCHER BUTTONS
    # =====================================================

    dispatcher_buttons = {
        "🆕 Yangi buyurtmalar",
        "🟡 Qabul qilingan",
        "🔵 Ish jarayonida",
        "✅ Yakunlangan",
        "❌ Bekor qilingan",
        "🚫 Rad etilgan",
        "📋 Barcha buyurtmalar",
        "📊 Statistika",
        "👨‍🔧 Ustalar",
        "📈 Hisobot",
        "📢 Xabar tarqatish",
    }

    if text in dispatcher_buttons:

        if user_id != ADMIN_ID:

            await update.message.reply_text(
                "❌ Фақат админ."
            )

            return

        mapping = {
            "🆕 Yangi buyurtmalar": (
                "open",
                "🆕 ЯНГИ БУЮРТМАЛАР"
            ),
            "🟡 Qabul qilingan": (
                "accepted",
                "🟡 ҚАБУЛ ҚИЛИНГАН"
            ),
            "🔵 Ish jarayonida": (
                "in_progress",
                "🔵 ИШ ЖАРАЁНИДА"
            ),
            "✅ Yakunlangan": (
                "completed",
                "✅ ЯКУНЛАНГАН"
            ),
            "❌ Bekor qilingan": (
                "cancelled",
                "❌ БЕКОР ҚИЛИНГАН"
            ),
            "🚫 Rad etilgan": (
                "rejected",
                "🚫 РАД ЭТИЛГАН"
            ),
            "📋 Barcha buyurtmalar": (
                None,
                "📋 БАРЧА БУЮРТМАЛАР"
            ),
        }

        if text == "📊 Statistika":
            await show_statistics(update)
            return

        if text == "👨‍🔧 Ustalar":
            await show_masters(update)
            return

        if text == "📈 Hisobot":
            await show_statistics(update)
            return

        if text == "📢 Xabar tarqatish":

            user_orders[user_id] = {
                "step": "broadcast"
            }

            await update.message.reply_text(
                "📢 ХАБАР ТАРҚАТИШ\n\n"
                "Мижозларга юбориладиган хабарни ёзинг.\n\n"
                "❌ Бекор қилиш учун: /cancel"
            )

            return

        status, title = mapping[text]

        await show_orders(
            update,
            status,
            title,
        )

        return

    # =====================================================
    # ADMIN MENU
    # =====================================================

    if text == "👑 Админ панель":

        if user_id != ADMIN_ID:
            return

        await update.message.reply_text(
            "👑 АДМИН БОШҚАРУВИ",
            reply_markup=admin_menu(),
        )

        return

    if text == "👨‍🔧 Усталар":

        if user_id != ADMIN_ID:
            return

        await show_masters(update)
        return

    if text == "📊 Уста статистикаси":

        if user_id != ADMIN_ID:
            return

        await show_master_statistics(update)
        return

    if text == "📥 Excel":

        if user_id != ADMIN_ID:
            return

        await export_excel(update)
        return

    if text == "👨‍🔧 Usta qo‘shish":

        if user_id != ADMIN_ID:
            return

        user_orders[user_id] = {
            "step": "add_master"
        }

        await update.message.reply_text(
            "👨‍🔧 УСТА ҚЎШИШ\n\n"
            "Устанинг Telegram ID рақамини ёзинг:"
        )

        return

    if text == "🗑 Usta o‘chirish":

        if user_id != ADMIN_ID:
            return

        user_orders[user_id] = {
            "step": "remove_master"
        }

        await update.message.reply_text(
            "🗑 УСТАНИ ЎЧИРИШ\n\n"
            "Устанинг Telegram ID рақамини ёзинг:"
        )

        return

    if text == "⬅️ Асосий меню":

        await update.message.reply_text(
            "Асосий меню:",
            reply_markup=main_menu(),
        )

        return

    # =====================================================
    # MAIN MENU
    # =====================================================

    if text == "🛠 Usta chaqirish":

        await start_order(
            update,
            context,
        )

        return

    if text == "🔁 Qayta buyurtma":

        await repeat_order(
            update,
            context,
        )

        return

    if text == "📋 Xizmatlar":

        await services(
            update,
            context,
        )

        return

    if text == "📞 Aloqa":

        await contact(
            update,
            context,
        )

        return

    # =====================================================
    # BROADCAST
    # =====================================================

    if user_id in user_orders:

        order = user_orders[user_id]

        if order.get("step") == "broadcast":

            if user_id != ADMIN_ID:
                return

            if text == "/cancel":

                del user_orders[user_id]

                await update.message.reply_text(
                    "❌ Хабар тарқатиш бекор қилинди.",
                    reply_markup=dispatcher_menu(),
                )

                return

            if not db_pool:

                await update.message.reply_text(
                    "❌ База уланмаган."
                )

                return

            try:

                async with db_pool.acquire() as conn:

                    customers = await conn.fetch(
                        """
                        SELECT telegram_id
                        FROM customers
                        """
                    )

                sent = 0
                failed = 0

                for customer in customers:

                    try:

                        await context.bot.send_message(
                            chat_id=customer["telegram_id"],
                            text=text,
                        )

                        sent += 1

                        await asyncio.sleep(0.05)

                    except Exception:

                        failed += 1

                del user_orders[user_id]

                await update.message.reply_text(
                    "📢 ХАБАР ТАРҚАТИЛДИ\n\n"
                    f"✅ Юборилди: {sent}\n"
                    f"❌ Юборилмади: {failed}",
                    reply_markup=dispatcher_menu(),
                )

            except Exception:

                logger.exception(
                    "Broadcast xatosi."
                )

                await update.message.reply_text(
                    "❌ Хабар тарқатишда хатолик."
                )

            return

        # =================================================
        # ADD MASTER
        # =================================================

        if order.get("step") == "add_master":

            if user_id != ADMIN_ID:
                return

            try:

                master_id = int(text)

            except ValueError:

                await update.message.reply_text(
                    "❌ Telegram ID фақат рақам бўлиши керак."
                )

                return

            user_orders[user_id] = {
                "step": "add_master_name",
                "master_id": master_id,
            }

            await update.message.reply_text(
                "👤 Энди устанинг исмини ёзинг:"
            )

            return

        if order.get("step") == "add_master_name":

            master_id = order["master_id"]

            name = text

            await db_add_master(
                master_id,
                name,
            )

            del user_orders[user_id]

            await update.message.reply_text(
                "✅ Уста қўшилди.\n\n"
                f"👨‍🔧 {name}\n"
                f"🆔 {master_id}",
                reply_markup=admin_menu(),
            )

            return

        # =================================================
        # REMOVE MASTER
        # =================================================

        if order.get("step") == "remove_master":

            if user_id != ADMIN_ID:
                return

            try:

                master_id = int(text)

            except ValueError:

                await update.message.reply_text(
                    "❌ Telegram ID нотўғри."
                )

                return

            await db_remove_master(
                master_id
            )

            del user_orders[user_id]

            await update.message.reply_text(
                "🗑 Уста нофаол қилинди.",
                reply_markup=admin_menu(),
            )

            return

    # =====================================================
    # ORDER FLOW
    # =====================================================

    if user_id not in user_orders:

        await update.message.reply_text(
            "Илтимос, менюдан керакли хизматни танланг.",
            reply_markup=main_menu(),
        )

        return

    order = user_orders[user_id]

    step = order.get("step")

    # =====================================================
    # REVIEW
    # =====================================================

    if step == "review":

        review = text

        if review == "-":
            review = None

        await db_save_rating(
            order["review_order_id"],
            user_id,
            None,
            order["review_rating"],
            review,
        )

        del user_orders[user_id]

        await update.message.reply_text(
            "🙏 Раҳмат!\n\n"
            "⭐ Баҳонгиз ва 💬 фикрингиз сақланди.\n\n"
            "USTA 24 сизга яна хизмат кўрсатишдан мамнун.",
            reply_markup=main_menu(),
        )

        return

    # =====================================================
    # NAME
    # =====================================================

    if step == "name":

        if not text:

            await update.message.reply_text(
                "📝 Илтимос, исмингизни ёзинг:"
            )

            return

        order["name"] = text
        order["step"] = "phone"

        phone_button = KeyboardButton(
            "📱 Телефон рақамимни юбориш",
            request_contact=True,
        )

        keyboard = ReplyKeyboardMarkup(
            [[phone_button]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await update.message.reply_text(
            "2️⃣ Телефон рақамингизни юборинг:",
            reply_markup=keyboard,
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
                "📱 Илтимос, телефон рақамингизни юборинг."
            )

            return

        order["phone"] = phone
        order["step"] = "service"

        await update.message.reply_text(
            "3️⃣ Қандай хизмат керак?",
            reply_markup=service_menu(),
        )

        return

    # =====================================================
    # SERVICE
    # =====================================================

    if step == "service":

        if not text:

            await update.message.reply_text(
                "Илтимос, хизмат турини танланг."
            )

            return

        order["service"] = text
        order["step"] = "location"

        await update.message.reply_text(
            "4️⃣ Манзилни танланг:\n\n"
            "📍 Геолокация юборсангиз, устанинг "
            "бориши осонлашади.",
            reply_markup=location_menu(),
        )

        return

    # =====================================================
    # LOCATION MANUAL
    # =====================================================

    if step == "location":

        if text == "✍️ Манзилни қўлда ёзиш":

            order["step"] = "address"

            await update.message.reply_text(
                "📍 Манзилингизни ёзинг:\n\n"
                "Масалан:\n"
                "Андижон шаҳар, Бобуршоҳ кўчаси, 15-уй",
                reply_markup=ReplyKeyboardRemove(),
            )

            return

        if text == "📍 Геолокациямни юбориш":

            await update.message.reply_text(
                "📍 Пастдаги тугма орқали "
                "геолокацияни юборинг.",
                reply_markup=location_menu(),
            )

            return

        await update.message.reply_text(
            "📍 Геолокация юборинг ёки "
            "«✍️ Манзилни қўлда ёзиш»ни танланг."
        )

        return

    # =====================================================
    # ADDRESS
    # =====================================================

    if step == "address":

        if not text:

            await update.message.reply_text(
                "📍 Илтимос, манзилни ёзинг."
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
    # DESCRIPTION
    # =====================================================

    if step == "description":

        if not text:

            await update.message.reply_text(
                "📝 Илтимос, буюртма ҳақида маълумот ёзинг."
            )

            return

        order["description"] = text

        # Нарх ҳозирча диспетчер томонидан белгиланади
        order["price"] = 0

        try:

            order_id = await send_order_to_masters(
                update,
                context,
                order,
            )

        except Exception:

            logger.exception(
                "USTALAR GURUHIGA YUBORISH XATOSI"
            )

            await update.message.reply_text(
                "❌ Буюртмани усталар гуруҳига "
                "юборишда хатолик юз берди.\n\n"
                "☎️ +998 77 069 00 03",
                reply_markup=main_menu(),
            )

            return

        del user_orders[user_id]

        await update.message.reply_text(
            f"✅ БУЮРТМАНГИЗ ҚАБУЛ ҚИЛИНДИ!\n\n"
            f"🔢 Буюртма №{order_id}\n\n"
            "👨‍🔧 Буюртма усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            "☎️ USTA 24\n"
            "+998 77 069 00 03",
            reply_markup=main_menu(),
        )

        return


# =========================================================
# ERROR
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "BOT XATOSI:",
        exc_info=context.error,
    )


# =========================================================
# RUN BOT
# =========================================================

async def run_bot(application):

    await application.initialize()

    await init_database()

    await application.start()

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    logger.info(
        "✅ Telegram polling ishga tushdi."
    )

    try:

        while True:

            await asyncio.sleep(3600)

    finally:

        await application.updater.stop()
        await application.stop()
        await application.shutdown()


# =========================================================
# MAIN
# =========================================================

def main():

    logger.info(
        "=============================="
    )

    logger.info(
        "USTA 24 BOT START"
    )

    logger.info(
        "MASTERS_GROUP_ID = %s",
        MASTERS_GROUP_ID,
    )

    logger.info(
        "ADMIN_ID = %s",
        ADMIN_ID,
    )

    logger.info(
        "DATABASE_URL mavjud: %s",
        bool(DATABASE_URL),
    )

    logger.info(
        "=============================="
    )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # COMMANDS
    # -----------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "dispatcher",
            dispatcher,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "id",
            chat_id_command,
        )
    )

    # -----------------------------------------------------
    # CALLBACK
    # -----------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            order_callback,
        )
    )

    # -----------------------------------------------------
    # CONTACT
    # -----------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            handle_message,
        )
    )

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.LOCATION,
            handle_message,
        )
    )

    # -----------------------------------------------------
    # TEXT
    # -----------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    application.add_error_handler(
        error_handler
    )

    # -----------------------------------------------------
    # FLASK
    # -----------------------------------------------------

    flask_thread = Thread(
        target=run_flask,
        daemon=True,
    )

    flask_thread.start()

    logger.info(
        "Flask server ishga tushdi."
    )

    # -----------------------------------------------------
    # BOT
    # -----------------------------------------------------

    asyncio.run(
        run_bot(application)
    )


if __name__ == "__main__":
    main()
