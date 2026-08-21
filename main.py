# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# Python 3.11+
# python-telegram-bot==22.3
# asyncpg
# PostgreSQL
#
# OTP YO'Q
# SMS YO'Q
#
# CLIENT
# MASTER
# DISPATCHER
# ADMIN
#
# ============================================================

import os
import io
import csv
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import asyncpg

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

TZ_NAME = "Asia/Tashkent"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("usta24")

db_pool: Optional[asyncpg.Pool] = None


# ============================================================
# CONSTANTS
# ============================================================

ROLE_CLIENT = "client"
ROLE_MASTER = "master"
ROLE_ADMIN = "admin"
ROLE_DISPATCHER = "dispatcher"

STATUS_WAITING = "waiting"
STATUS_OFFERED = "offered"
STATUS_ACCEPTED = "accepted"
STATUS_ON_WAY = "on_way"
STATUS_STARTED = "started"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"

# Client conversation states
C_NAME = 100
C_PHONE = 101
C_SERVICE = 102
C_LOCATION = 103
C_ADDRESS = 104
C_DESCRIPTION = 105
C_TIME = 106
C_COUPON = 107
C_CONFIRM = 108
C_CHAT = 109
C_RATING = 110
C_REVIEW = 111

# Master states
M_ARRIVAL = 200
M_CHAT = 201

# Admin states
A_BROADCAST = 300
A_PRICE = 301


# ============================================================
# SERVICES
# ============================================================

SERVICES = {
    "sanitary": {
        "name": "🚽 Sanitariya",
        "items": {
            "toilet": ("🚽 Hojatxona o'rnatish", 80000),
            "sink": ("🚰 Rakovina o'rnatish", 70000),
            "faucet": ("🚿 Kranni almashtirish", 50000),
            "pipe": ("🔧 Quvur ta'mirlash", 80000),
        },
    },
    "furniture": {
        "name": "🪑 Mebel",
        "items": {
            "assemble": ("🪑 Mebel yig'ish", 80000),
            "wardrobe": ("🚪 Shkaf yig'ish", 120000),
            "kitchen": ("🍽 Oshxona mebeli", 150000),
            "bed": ("🛏 Karavot yig'ish", 100000),
            "table": ("🪵 Stol/stul yig'ish", 60000),
            "disassemble": ("🔧 Mebel yechish", 70000),
        },
    },
    "moving": {
        "name": "🚚 Ko'chirish",
        "items": {
            "house": ("🏠 Uy ko'chirish", 250000),
            "furniture_transport": ("🚚 Mebel tashish", 150000),
            "loading": ("📦 Yuklash/tushirish", 100000),
        },
    },
    "electric": {
        "name": "💡 Elektr",
        "items": {
            "socket": ("🔌 Rozetka o'rnatish", 50000),
            "light": ("💡 Chiroq o'rnatish", 50000),
            "wiring": ("⚡ Elektr simlari", 100000),
        },
    },
}


# ============================================================
# KEYBOARDS
# ============================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Buyurtma berish", "📋 Xizmatlar"],
            ["🔍 Buyurtmalarim", "🔄 Qayta buyurtma"],
            ["⭐ Reytinglarim", "🎁 Bonuslarim"],
            ["📞 Aloqa", "👤 Profil"],
        ],
        resize_keyboard=True,
    )


def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["📋 Yangi buyurtmalar"],
            ["🔧 Faol buyurtmalar", "📜 Tarix"],
            ["🟢 Online", "🔴 Offline"],
            ["💰 Daromadim", "⭐ Reytingim"],
            ["👤 Profil"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Ustalar", "📋 Buyurtmalar"],
            ["👥 Mijozlar", "📊 Statistika"],
            ["📄 Hisobot", "💰 Narxlar"],
            ["💬 Xabarlar", "🎟 Kuponlar"],
            ["⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📞 Telefon raqamimni yuborish",
                    request_contact=True,
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📍 Geolokatsiyani yuborish",
                    request_location=True,
                )
            ],
            ["✍️ Manzilni qo'lda yozish"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL environment variable topilmadi."
        )

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=60,
    )

    async with db_pool.acquire() as conn:

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                role TEXT NOT NULL DEFAULT 'client',
                language TEXT DEFAULT 'uz',
                is_active BOOLEAN DEFAULT TRUE,
                is_online BOOLEAN DEFAULT FALSE,
                rating NUMERIC(3,2) DEFAULT 5.00,
                rating_count INTEGER DEFAULT 0,
                bonus_points INTEGER DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,

                customer_id BIGINT NOT NULL,
                customer_name TEXT,
                customer_phone TEXT,

                service_category TEXT,
                service_code TEXT,
                service_name TEXT,

                address TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,

                description TEXT,

                requested_time TEXT DEFAULT 'now',

                base_price NUMERIC(12,2) DEFAULT 0,
                discount NUMERIC(12,2) DEFAULT 0,
                total_price NUMERIC(12,2) DEFAULT 0,

                coupon_code TEXT,

                status TEXT DEFAULT 'waiting',

                master_id BIGINT,
                master_name TEXT,
                master_phone TEXT,

                arrival_minutes INTEGER,

                started_at TIMESTAMP,
                completed_at TIMESTAMP,

                payment_method TEXT,
                payment_status TEXT DEFAULT 'unpaid',

                start_photo_file_id TEXT,
                finish_photo_file_id TEXT,

                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS order_history (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                actor_id BIGINT,
                actor_name TEXT,
                old_status TEXT,
                new_status TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT UNIQUE NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                stars INTEGER NOT NULL,
                review TEXT,
                photo_file_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id BIGSERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                discount_percent INTEGER NOT NULL,
                max_uses INTEGER DEFAULT 100,
                used_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                sender_id BIGINT NOT NULL,
                receiver_id BIGINT NOT NULL,
                message TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_customer
            ON orders(customer_id)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_master
            ON orders(master_id)
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_status
            ON orders(status)
        """)

    logger.info("PostgreSQL connected and initialized.")


# ============================================================
# USER FUNCTIONS
# ============================================================

async def get_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id=$1",
            telegram_id,
        )


async def upsert_user(tg_user):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users
            (
                telegram_id,
                username,
                full_name,
                updated_at
            )
            VALUES ($1,$2,$3,NOW())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username=EXCLUDED.username,
                full_name=EXCLUDED.full_name,
                updated_at=NOW()
        """,
            tg_user.id,
            tg_user.username,
            tg_user.full_name,
        )


async def set_user_phone(telegram_id: int, phone: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET phone=$1,
                updated_at=NOW()
            WHERE telegram_id=$2
        """, phone, telegram_id)


async def set_role(telegram_id: int, role: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET role=$1,
                updated_at=NOW()
            WHERE telegram_id=$2
        """, role, telegram_id)


async def get_or_create_user(tg_user):
    await upsert_user(tg_user)

    user = await get_user(tg_user.id)

    if not user:
        raise RuntimeError("User yaratilmadi.")

    return user


# ============================================================
# ORDER FUNCTIONS
# ============================================================

async def create_order(
    customer_id,
    customer_name,
    customer_phone,
    service_category,
    service_code,
    service_name,
    address,
    latitude,
    longitude,
    description,
    requested_time,
    base_price,
    discount,
    total_price,
    coupon_code=None,
):
    async with db_pool.acquire() as conn:

        order_id = await conn.fetchval("""
            INSERT INTO orders
            (
                customer_id,
                customer_name,
                customer_phone,
                service_category,
                service_code,
                service_name,
                address,
                latitude,
                longitude,
                description,
                requested_time,
                base_price,
                discount,
                total_price,
                coupon_code,
                status
            )
            VALUES
            (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                $11,$12,$13,$14,$15,$16
            )
            RETURNING id
        """,
            customer_id,
            customer_name,
            customer_phone,
            service_category,
            service_code,
            service_name,
            address,
            latitude,
            longitude,
            description,
            requested_time,
            base_price,
            discount,
            total_price,
            coupon_code,
            STATUS_WAITING,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            customer_id,
            customer_name,
            None,
            STATUS_WAITING,
            "Buyurtma yaratildi",
        )

        return order_id


async def get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM orders WHERE id=$1",
            order_id,
        )


async def update_order_status(
    order_id,
    new_status,
    actor_id=None,
    actor_name=None,
    note=None,
):
    async with db_pool.acquire() as conn:

        old = await conn.fetchval(
            "SELECT status FROM orders WHERE id=$1",
            order_id,
        )

        await conn.execute("""
            UPDATE orders
            SET status=$1,
                updated_at=NOW()
            WHERE id=$2
        """,
            new_status,
            order_id,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            actor_id,
            actor_name,
            old,
            new_status,
            note,
        )


async def get_customer_orders(customer_id, limit=20):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM orders
            WHERE customer_id=$1
            ORDER BY created_at DESC
            LIMIT $2
        """, customer_id, limit)


async def get_master_orders(master_id, limit=50):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM orders
            WHERE master_id=$1
            ORDER BY created_at DESC
            LIMIT $2
        """, master_id, limit)


async def get_waiting_orders(limit=20):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM orders
            WHERE status IN ('waiting','offered')
            ORDER BY created_at ASC
            LIMIT $1
        """, limit)


# ============================================================
# HISTORY
# ============================================================

async def get_order_history(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM order_history
            WHERE order_id=$1
            ORDER BY created_at ASC
        """, order_id)


# ============================================================
# COUPON
# ============================================================

async def check_coupon(code: str):
    code = code.strip().upper()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT *
            FROM coupons
            WHERE code=$1
              AND is_active=TRUE
              AND used_count < max_uses
        """, code)

        return row


async def use_coupon(code: str):
    if not code:
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE coupons
            SET used_count=used_count+1
            WHERE code=$1
        """, code.upper())


# ============================================================
# MASTER SEARCH
# ============================================================

async def find_available_masters(
    service_category=None,
    latitude=None,
    longitude=None,
):
    async with db_pool.acquire() as conn:

        # First: online masters
        rows = await conn.fetch("""
            SELECT *
            FROM users
            WHERE role='master'
              AND is_active=TRUE
              AND is_online=TRUE
            ORDER BY rating DESC, completed_orders ASC
            LIMIT 10
        """)

        if rows:
            return rows

        # If nobody is online — active masters
        return await conn.fetch("""
            SELECT *
            FROM users
            WHERE role='master'
              AND is_active=TRUE
            ORDER BY rating DESC, completed_orders ASC
            LIMIT 10
        """)


# ============================================================
# MASTER ASSIGN
# ============================================================

async def assign_master(order_id, master):
    async with db_pool.acquire() as conn:

        await conn.execute("""
            UPDATE orders
            SET
                master_id=$1,
                master_name=$2,
                master_phone=$3,
                status='offered',
                updated_at=NOW()
            WHERE id=$4
        """,
            master["telegram_id"],
            master["full_name"],
            master["phone"],
            order_id,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            master["telegram_id"],
            master["full_name"],
            STATUS_WAITING,
            STATUS_OFFERED,
            "Ustaga taklif yuborildi",
        )


# ============================================================
# RATING
# ============================================================

async def save_rating(
    order_id,
    customer_id,
    master_id,
    stars,
    review,
    photo_file_id=None,
):
    async with db_pool.acquire() as conn:

        exists = await conn.fetchval("""
            SELECT id
            FROM ratings
            WHERE order_id=$1
        """, order_id)

        if exists:
            return False

        await conn.execute("""
            INSERT INTO ratings
            (
                order_id,
                customer_id,
                master_id,
                stars,
                review,
                photo_file_id
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            customer_id,
            master_id,
            stars,
            review,
            photo_file_id,
        )

        await conn.execute("""
            UPDATE users
            SET
                rating =
                    (
                        rating * rating_count + $1
                    )
                    /
                    (rating_count + 1),
                rating_count=rating_count+1,
                updated_at=NOW()
            WHERE telegram_id=$2
        """,
            stars,
            master_id,
        )

        await conn.execute("""
            UPDATE users
            SET
                bonus_points=bonus_points+10,
                updated_at=NOW()
            WHERE telegram_id=$1
        """,
            customer_id,
        )

        return True


# ============================================================
# FORMAT ORDER
# ============================================================

def format_order(order):
    status_map = {
        STATUS_WAITING: "⏳ Kutilmoqda",
        STATUS_OFFERED: "📨 Ustaga yuborildi",
        STATUS_ACCEPTED: "✅ Qabul qilindi",
        STATUS_ON_WAY: "🚗 Yo'lda",
        STATUS_STARTED: "🔧 Jarayonda",
        STATUS_COMPLETED: "🏁 Tugallandi",
        STATUS_CANCELLED: "❌ Bekor qilindi",
        STATUS_REJECTED: "❌ Rad etildi",
    }

    status = status_map.get(
        order["status"],
        order["status"],
    )

    text = (
        f"🆔 <b>Buyurtma #{order['id']}</b>\n"
        f"🛠 Xizmat: <b>{order['service_name']}</b>\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['customer_phone'] or '-'}\n"
        f"📍 Manzil: {order['address'] or '-'}\n"
        f"📝 Izoh: {order['description'] or '-'}\n"
        f"🕐 Vaqt: {order['requested_time']}\n"
        f"💰 Narx: <b>{float(order['total_price']):,.0f} so'm</b>\n"
        f"📌 Holat: <b>{status}</b>\n"
    )

    if order["master_name"]:
        text += (
            f"👨‍🔧 Usta: {order['master_name']}\n"
        )

    if order["arrival_minutes"]:
        text += (
            f"🚗 Yetib borish: "
            f"{order['arrival_minutes']} daqiqa\n"
        )

    return text


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_user:
        return

    user = await get_or_create_user(
        update.effective_user
    )

    if user["role"] == ROLE_ADMIN:
        await update.message.reply_text(
            "👑 <b>USTA 24 ANDIJON</b>\n\n"
            "Admin paneliga xush kelibsiz.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu(),
        )
        return

    if user["role"] == ROLE_MASTER:
        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 ANDIJON</b>\n\n"
            "Usta paneliga xush kelibsiz.",
            parse_mode=ParseMode.HTML,
            reply_markup=master_menu(),
        )
        return

    if not user["phone"]:

        await update.message.reply_text(
            "🇺🇿 <b>Assalomu alaykum!</b>\n\n"
            "USTA 24 ANDIJON xizmatiga xush kelibsiz.\n\n"
            "Davom etish uchun telefon raqamingizni yuboring.",
            parse_mode=ParseMode.HTML,
            reply_markup=phone_keyboard(),
        )
        return

    await update.message.reply_text(
        "🏠 <b>USTA 24 ANDIJON</b>\n\n"
        "Bosh menyu:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(),
    )


# ============================================================
# PHONE
# ============================================================

async def handle_contact(update, context):

    contact = update.message.contact

    if contact.user_id and contact.user_id != update.effective_user.id:
        await update.message.reply_text(
            "❌ Iltimos, o'zingizning telefon raqamingizni yuboring."
        )
        return

    phone = contact.phone_number

    await set_user_phone(
        update.effective_user.id,
        phone,
    )

    await update.message.reply_text(
        "✅ Telefon raqamingiz saqlandi.\n\n"
        "🏠 Bosh menyu:",
        reply_markup=main_menu(),
    )


# ============================================================
# SERVICES
# ============================================================

async def services_command(update, context):

    text = "🛠 <b>USTA 24 XIZMATLARI</b>\n\n"

    for category in SERVICES.values():
        text += f"<b>{category['name']}</b>\n"

        for item in category["items"].values():
            text += (
                f"• {item[0]} — "
                f"{item[1]:,} so'm dan\n"
            )

        text += "\n"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


def service_keyboard():

    buttons = []

    for key, category in SERVICES.items():
        buttons.append([
            InlineKeyboardButton(
                category["name"],
                callback_data=f"cat:{key}",
            )
        ])

    return InlineKeyboardMarkup(buttons)


# ============================================================
# NEW ORDER
# ============================================================

async def new_order(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user or not user["phone"]:
        await update.message.reply_text(
            "Avval telefon raqamingizni yuboring.",
            reply_markup=phone_keyboard(),
        )
        return

    context.user_data["order"] = {}

    await update.message.reply_text(
        "🛒 <b>Yangi buyurtma</b>\n\n"
        "Xizmat turini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=service_keyboard(),
    )


# ============================================================
# CATEGORY
# ============================================================

async def category_callback(update, context):

    query = update.callback_query
    await query.answer()

    category_key = query.data.split(":", 1)[1]

    category = SERVICES.get(category_key)

    if not category:
        return

    context.user_data["order"]["category"] = category_key

    buttons = []

    for code, item in category["items"].items():
        buttons.append([
            InlineKeyboardButton(
                f"{item[0]} — {item[1]:,} so'm",
                callback_data=f"service:{code}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "⬅️ Orqaga",
            callback_data="back:categories",
        )
    ])

    await query.edit_message_text(
        f"🛠 <b>{category['name']}</b>\n\n"
        "Xizmatni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ============================================================
# SERVICE
# ============================================================

async def service_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_data = context.user_data.get("order", {})

    category_key = order_data.get("category")

    if not category_key:
        return

    service_code = query.data.split(":", 1)[1]

    category = SERVICES[category_key]

    item = category["items"].get(service_code)

    if not item:
        return

    service_name, price = item

    order_data["service_code"] = service_code
    order_data["service_name"] = service_name
    order_data["base_price"] = price

    context.user_data["order"] = order_data

    await query.edit_message_text(
        f"✅ <b>{service_name}</b>\n"
        f"💰 Boshlang'ich narx: <b>{price:,} so'm</b>\n\n"
        "📍 Endi manzilingizni yuboring.",
        parse_mode=ParseMode.HTML,
    )

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text="📍 Geolokatsiyani yuboring:",
        reply_markup=location_keyboard(),
    )

    return C_LOCATION


# ============================================================
# LOCATION
# ============================================================

async def handle_location(update, context):

    if not update.message.location:
        return

    loc = update.message.location

    context.user_data["order"]["latitude"] = loc.latitude
    context.user_data["order"]["longitude"] = loc.longitude
    context.user_data["order"]["address"] = (
        f"📍 Geolokatsiya: "
        f"{loc.latitude:.6f}, {loc.longitude:.6f}"
    )

    await update.message.reply_text(
        "✅ Geolokatsiya qabul qilindi.\n\n"
        "📝 Buyurtma haqida izoh yozing.\n"
        "Agar izoh kerak bo'lmasa, «O'tkazib yuborish» tugmasini bosing.",
        reply_markup=ReplyKeyboardMarkup(
            [["⏭ O'tkazib yuborish"]],
            resize_keyboard=True,
        ),
    )

    return C_DESCRIPTION


# ============================================================
# MANUAL ADDRESS
# ============================================================

async def manual_address(update, context):

    if update.message.text == "✍️ Manzilni qo'lda yozish":

        await update.message.reply_text(
            "📍 Manzilingizni yozing:",
            reply_markup=ReplyKeyboardRemove(),
        )

        return C_ADDRESS


async def receive_address(update, context):

    context.user_data["order"]["address"] = (
        update.message.text.strip()
    )

    await update.message.reply_text(
        "📝 Buyurtma haqida izoh yozing.\n"
        "Kerak bo'lmasa «O'tkazib yuborish» deb yozing.",
        reply_markup=ReplyKeyboardMarkup(
            [["⏭ O'tkazib yuborish"]],
            resize_keyboard=True,
        ),
    )

    return C_DESCRIPTION


# ============================================================
# DESCRIPTION
# ============================================================

async def receive_description(update, context):

    text = update.message.text.strip()

    if text == "⏭ O'tkazib yuborish":
        text = ""

    context.user_data["order"]["description"] = text

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔴 Hozir",
                callback_data="time:now",
            ),
        ],
        [
            InlineKeyboardButton(
                "🕐 Keyinroq",
                callback_data="time:later",
            ),
        ],
    ])

    await update.message.reply_text(
        "🕐 <b>Qachon usta kerak?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    return C_TIME


# ============================================================
# TIME
# ============================================================

async def time_callback(update, context):

    query = update.callback_query
    await query.answer()

    value = query.data.split(":", 1)[1]

    if value == "now":
        requested_time = "Hozir"
    else:
        requested_time = "Keyinroq"

    context.user_data["order"]["requested_time"] = requested_time

    await query.edit_message_text(
        "🎟 Kupon kodi bormi?\n\n"
        "Bo'lmasa, «Kuponsiz» tugmasini bosing.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎟 Kupon kiritish",
                    callback_data="coupon:yes",
                ),
            ],
            [
                InlineKeyboardButton(
                    "⏭ Kuponsiz",
                    callback_data="coupon:no",
                ),
            ],
        ]),
    )

    return C_COUPON


# ============================================================
# COUPON
# ============================================================

async def coupon_callback(update, context):

    query = update.callback_query
    await query.answer()

    value = query.data.split(":", 1)[1]

    if value == "yes":

        await query.edit_message_text(
            "🎟 Kupon kodini yozing:"
        )

        return C_COUPON

    context.user_data["order"]["coupon_code"] = None
    await show_confirmation(update, context)


async def receive_coupon(update, context):

    code = update.message.text.strip().upper()

    coupon = await check_coupon(code)

    if not coupon:
        await update.message.reply_text(
            "❌ Kupon topilmadi yoki muddati tugagan.\n"
            "Boshqa kod kiriting yoki «Kuponsiz» deb yozing."
        )
        return C_COUPON

    context.user_data["order"]["coupon_code"] = code
    context.user_data["order"]["coupon_percent"] = (
        coupon["discount_percent"]
    )

    await update.message.reply_text(
        f"✅ Kupon qabul qilindi: "
        f"{coupon['discount_percent']}% chegirma."
    )

    await show_confirmation_message(
        update,
        context,
    )

    return C_CONFIRM


# ============================================================
# CONFIRMATION
# ============================================================

async def show_confirmation(update, context):
    order = context.user_data["order"]

    base = float(order["base_price"])

    percent = order.get(
        "coupon_percent",
        0,
    )

    discount = base * percent / 100
    total = base - discount

    order["discount"] = discount
    order["total_price"] = total

    text = (
        "🧾 <b>BUYURTMA TASDIG'I</b>\n\n"
        f"🛠 Xizmat: {order['service_name']}\n"
        f"📍 Manzil: {order.get('address','-')}\n"
        f"📝 Izoh: {order.get('description') or '-'}\n"
        f"🕐 Vaqt: {order.get('requested_time','Hozir')}\n\n"
        f"💰 Narx: {base:,.0f} so'm\n"
    )

    if discount:
        text += (
            f"🎟 Chegirma: -{discount:,.0f} so'm\n"
        )

    text += (
        f"💵 <b>Jami: {total:,.0f} so'm</b>\n\n"
        "Buyurtmani tasdiqlaysizmi?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Tasdiqlash",
                callback_data="order:confirm",
            ),
            InlineKeyboardButton(
                "❌ Bekor qilish",
                callback_data="order:cancel",
            ),
        ]
    ])

    if hasattr(update, "message") and update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    else:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def show_confirmation_message(update, context):
    await show_confirmation(
        update,
        context,
    )


# ============================================================
# CONFIRM ORDER
# ============================================================

async def confirm_order_callback(update, context):

    query = update.callback_query
    await query.answer()

    value = query.data.split(":", 1)[1]

    if value == "cancel":

        context.user_data.pop("order", None)

        await query.edit_message_text(
            "❌ Buyurtma bekor qilindi."
        )

        await context.bot.send_message(
            update.effective_user.id,
            "🏠 Bosh menyu:",
        )

        return

    order = context.user_data.get("order")

    if not order:
        await query.edit_message_text(
            "❌ Buyurtma ma'lumotlari topilmadi."
        )
        return

    user = await get_user(
        update.effective_user.id
    )

    order_id = await create_order(
        customer_id=update.effective_user.id,
        customer_name=user["full_name"],
        customer_phone=user["phone"],
        service_category=order["category"],
        service_code=order["service_code"],
        service_name=order["service_name"],
        address=order.get("address"),
        latitude=order.get("latitude"),
        longitude=order.get("longitude"),
        description=order.get("description"),
        requested_time=order.get("requested_time"),
        base_price=order["base_price"],
        discount=order.get("discount", 0),
        total_price=order["total_price"],
        coupon_code=order.get("coupon_code"),
    )

    if order.get("coupon_code"):
        await use_coupon(
            order["coupon_code"]
        )

    saved = await get_order(order_id)

    await query.edit_message_text(
        "✅ <b>BUYURTMA YUBORILDI!</b>\n\n"
        f"🆔 #{order_id}\n"
        "⏳ Holat: Kutilmoqda\n\n"
        "🤖 Tizim hozir usta qidirmoqda...",
        parse_mode=ParseMode.HTML,
    )

    context.user_data.pop("order", None)

    await dispatch_order(
        context,
        saved,
    )


# ============================================================
# DISPATCH ORDER
# ============================================================

async def dispatch_order(context, order):

    masters = await find_available_masters(
        order["service_category"],
        order["latitude"],
        order["longitude"],
    )

    if not masters:

        if MASTERS_GROUP_ID:
            await context.bot.send_message(
                MASTERS_GROUP_ID,
                "🚨 <b>YANGI BUYURTMA</b>\n\n"
                + format_order(order),
                parse_mode=ParseMode.HTML,
            )

        await context.bot.send_message(
            order["customer_id"],
            "⏳ Buyurtmangiz qabul qilindi.\n"
            "Hozircha bo'sh usta topilmadi.\n"
            "Dispatcher siz bilan bog'lanadi.",
        )

        return

    # Eng yaxshi birinchi usta
    master = masters[0]

    await assign_master(
        order["id"],
        master,
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Qabul qilish",
                callback_data=f"accept:{order['id']}",
            ),
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"reject:{order['id']}",
            ),
        ]
    ])

    await context.bot.send_message(
        master["telegram_id"],
        "🔔 <b>YANGI BUYURTMA!</b>\n\n"
        + format_order(order)
        + "\n"
        "Siz buyurtmani qabul qilasizmi?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    # Masters group
    if MASTERS_GROUP_ID:
        try:
            await context.bot.send_message(
                MASTERS_GROUP_ID,
                "📨 <b>Ustaga taklif yuborildi</b>\n\n"
                + format_order(order),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(
                "Masters group error: %s",
                e,
            )


# ============================================================
# MASTER ACCEPT
# ============================================================

async def master_accept_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        await query.answer(
            "Buyurtma topilmadi.",
            show_alert=True,
        )
        return

    if order["status"] not in (
        STATUS_WAITING,
        STATUS_OFFERED,
    ):
        await query.answer(
            "Bu buyurtma allaqachon qabul qilingan.",
            show_alert=True,
        )
        return

    master = await get_user(
        update.effective_user.id
    )

    if master["role"] != ROLE_MASTER:
        await query.answer(
            "Siz usta sifatida ro'yxatdan o'tmagansiz.",
            show_alert=True,
        )
        return

    async with db_pool.acquire() as conn:

        await conn.execute("""
            UPDATE orders
            SET
                master_id=$1,
                master_name=$2,
                master_phone=$3,
                status=$4,
                accepted_at=NOW(),
                updated_at=NOW()
            WHERE id=$5
        """,
            master["telegram_id"],
            master["full_name"],
            master["phone"],
            STATUS_ACCEPTED,
            order_id,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            master["telegram_id"],
            master["full_name"],
            order["status"],
            STATUS_ACCEPTED,
            "Usta buyurtmani qabul qildi",
        )

    await query.edit_message_text(
        "✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n"
        "🚗 Yetib borish vaqtini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔴 15 daqiqa",
                    callback_data=f"arrival:{order_id}:15",
                ),
                InlineKeyboardButton(
                    "🟡 30 daqiqa",
                    callback_data=f"arrival:{order_id}:30",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🟢 45 daqiqa",
                    callback_data=f"arrival:{order_id}:45",
                ),
                InlineKeyboardButton(
                    "🟢 60 daqiqa",
                    callback_data=f"arrival:{order_id}:60",
                ),
            ],
        ]),
    )

    await context.bot.send_message(
        order["customer_id"],
        f"✅ <b>Buyurtma #{order_id} qabul qilindi!</b>\n\n"
        f"👨‍🔧 Usta: {master['full_name']}\n"
        "🚗 Usta yetib borish vaqtini belgilamoqda.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# MASTER REJECT
# ============================================================

async def master_reject_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    await update_order_status(
        order_id,
        STATUS_REJECTED,
        update.effective_user.id,
        update.effective_user.full_name,
        "Usta buyurtmani rad etdi",
    )

    await query.edit_message_text(
        "❌ Buyurtma rad etildi.\n"
        "🤖 Tizim boshqa usta qidirmoqda..."
    )

    await redispatch_order(
        context,
        order_id,
    )


async def redispatch_order(context, order_id):

    order = await get_order(order_id)

    if not order:
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders
            SET status='waiting',
                master_id=NULL,
                master_name=NULL,
                master_phone=NULL,
                updated_at=NOW()
            WHERE id=$1
        """, order_id)

    await dispatch_order(
        context,
        await get_order(order_id),
    )


# ============================================================
# ARRIVAL
# ============================================================

async def arrival_callback(update, context):

    query = update.callback_query
    await query.answer()

    _, order_id, minutes = query.data.split(":")

    order_id = int(order_id)
    minutes = int(minutes)

    order = await get_order(order_id)

    if not order:
        return

    async with db_pool.acquire() as conn:

        await conn.execute("""
            UPDATE orders
            SET
                arrival_minutes=$1,
                status=$2,
                updated_at=NOW()
            WHERE id=$3
        """,
            minutes,
            STATUS_ON_WAY,
            order_id,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            update.effective_user.id,
            update.effective_user.full_name,
            STATUS_ACCEPTED,
            STATUS_ON_WAY,
            f"Yetib borish {minutes} daqiqa",
        )

    await query.edit_message_text(
        f"✅ <b>Qabul qilindi!</b>\n\n"
        f"🚗 Yetib borish: {minutes} daqiqa",
        parse_mode=ParseMode.HTML,
    )

    await context.bot.send_message(
        order["customer_id"],
        f"🚗 <b>Usta yo'lda!</b>\n\n"
        f"👨‍🔧 {order['master_name']}\n"
        f"⏱ Taxminan {minutes} daqiqada yetib boradi.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# MASTER START WORK
# ============================================================

async def start_work_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    if order["master_id"] != update.effective_user.id:
        await query.answer(
            "Bu buyurtma sizga tegishli emas.",
            show_alert=True,
        )
        return

    async with db_pool.acquire() as conn:

        await conn.execute("""
            UPDATE orders
            SET
                status=$1,
                started_at=NOW(),
                updated_at=NOW()
            WHERE id=$2
        """,
            STATUS_STARTED,
            order_id,
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            update.effective_user.id,
            update.effective_user.full_name,
            order["status"],
            STATUS_STARTED,
            "Usta ishni boshladi",
        )

    await query.edit_message_text(
        "🔧 <b>ISH BOSHLANDI!</b>\n\n"
        f"🆔 #{order_id}\n"
        "⏳ Holat: Jarayonda",
        parse_mode=ParseMode.HTML,
    )

    await context.bot.send_message(
        order["customer_id"],
        f"🔧 <b>Usta ishni boshladi!</b>\n\n"
        f"🆔 Buyurtma #{order_id}\n"
        f"👨‍🔧 Usta: {order['master_name']}",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# MASTER FINISH
# ============================================================

async def finish_work_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    if order["master_id"] != update.effective_user.id:
        return

    await query.edit_message_text(
        "🏁 <b>Ishni yakunlash</b>\n\n"
        f"🆔 #{order_id}\n"
        f"💰 To'lov: {float(order['total_price']):,.0f} so'm\n\n"
        "Tasdiqlaysizmi?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Yakunlash",
                    callback_data=f"finishconfirm:{order_id}",
                ),
                InlineKeyboardButton(
                    "⬅️ Bekor",
                    callback_data=f"finishcancel:{order_id}",
                ),
            ]
        ]),
    )


async def finish_confirm_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    async with db_pool.acquire() as conn:

        await conn.execute("""
            UPDATE orders
            SET
                status=$1,
                completed_at=NOW(),
                updated_at=NOW()
            WHERE id=$2
        """,
            STATUS_COMPLETED,
            order_id,
        )

        await conn.execute("""
            UPDATE users
            SET
                completed_orders=completed_orders+1,
                updated_at=NOW()
            WHERE telegram_id=$1
        """,
            order["master_id"],
        )

        await conn.execute("""
            INSERT INTO order_history
            (
                order_id,
                actor_id,
                actor_name,
                old_status,
                new_status,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6)
        """,
            order_id,
            update.effective_user.id,
            update.effective_user.full_name,
            order["status"],
            STATUS_COMPLETED,
            "Ish tugallandi",
        )

    await query.edit_message_text(
        "✅ <b>ISH YAKUNLANDI!</b>",
        parse_mode=ParseMode.HTML,
    )

    await context.bot.send_message(
        order["customer_id"],
        f"🏁 <b>Buyurtma #{order_id} tugallandi!</b>\n\n"
        f"👨‍🔧 Usta: {order['master_name']}\n"
        f"💰 Summa: {float(order['total_price']):,.0f} so'm\n\n"
        "⭐ Ustaga baho bering.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⭐ Reyting berish",
                    callback_data=f"rating:{order_id}",
                )
            ]
        ]),
    )


# ============================================================
# PAYMENT
# ============================================================

async def payment_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    await query.edit_message_text(
        f"💳 <b>TO'LOV</b>\n\n"
        f"🆔 #{order_id}\n"
        f"💰 {float(order['total_price']):,.0f} so'm\n\n"
        "To'lov turini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💵 Naqd",
                    callback_data=f"pay:cash:{order_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💳 Click",
                    callback_data=f"pay:click:{order_id}",
                ),
                InlineKeyboardButton(
                    "💳 Payme",
                    callback_data=f"pay:payme:{order_id}",
                ),
            ],
        ]),
    )


async def pay_method_callback(update, context):

    query = update.callback_query
    await query.answer()

    _, method, order_id = query.data.split(":")

    order_id = int(order_id)

    if method == "cash":

        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE orders
                SET
                    payment_method='cash',
                    payment_status='pending',
                    updated_at=NOW()
                WHERE id=$1
            """, order_id)

        await query.edit_message_text(
            "💵 <b>Naqd to'lov</b>\n\n"
            "To'lovni ustaga berishingiz mumkin.\n"
            "Usta to'lovni tasdiqlaydi.",
            parse_mode=ParseMode.HTML,
        )

        order = await get_order(order_id)

        if order:
            try:
                await context.bot.send_message(
                    order["master_id"],
                    f"💵 Mijoz #{order_id} uchun "
                    "naqd to'lov tanladi."
                )
            except Exception:
                pass

        return

    # Real provider API ulanmaguncha
    # to'lov "paid" qilinmaydi.
    await query.edit_message_text(
        "💳 <b>Онлайн тўлов</b>\n\n"
        f"{method.upper()} интеграцияси ҳали API калитлари билан "
        "уланмаган.\n\n"
        "Ҳозирча тўловни устадан ёки админдан тасдиқлатиш мумкин.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# RATING
# ============================================================

async def rating_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    context.user_data["rating_order_id"] = order_id

    buttons = []

    for i in range(1, 6):
        buttons.append(
            InlineKeyboardButton(
                "⭐" * i,
                callback_data=f"stars:{order_id}:{i}",
            )
        )

    await query.edit_message_text(
        "⭐ <b>USTAGA BAHO BERING</b>\n\n"
        "Necha yulduz berasiz?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            buttons
        ]),
    )


async def stars_callback(update, context):

    query = update.callback_query
    await query.answer()

    _, order_id, stars = query.data.split(":")

    context.user_data["rating_order_id"] = int(
        order_id
    )
    context.user_data["rating_stars"] = int(
        stars
    )

    await query.edit_message_text(
        f"⭐ Siz {stars} yulduz tanladingiz.\n\n"
        "📝 Sharhingizni yozing.\n"
        "Agar sharh yozishni istamasangiz: `-`",
        parse_mode=ParseMode.MARKDOWN,
    )

    return C_REVIEW


async def receive_review(update, context):

    review = update.message.text.strip()

    if review == "-":
        review = ""

    order_id = context.user_data.get(
        "rating_order_id"
    )
    stars = context.user_data.get(
        "rating_stars"
    )

    if not order_id or not stars:
        return

    order = await get_order(order_id)

    if not order:
        return

    saved = await save_rating(
        order_id,
        update.effective_user.id,
        order["master_id"],
        stars,
        review,
    )

    if saved:
        await update.message.reply_text(
            f"✅ <b>Sharh yuborildi!</b>\n\n"
            f"⭐ Bahongiz: {stars}\n"
            "🎁 Sizga 10 bonus ball berildi.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(),
        )

        try:
            await context.bot.send_message(
                order["master_id"],
                f"⭐ Siz yangi baho oldingiz!\n\n"
                f"Buyurtma: #{order_id}\n"
                f"Bahosi: {'⭐' * stars}\n"
                f"Sharh: {review or '-'}"
            )
        except Exception:
            pass

    context.user_data.pop(
        "rating_order_id",
        None,
    )
    context.user_data.pop(
        "rating_stars",
        None,
    )


# ============================================================
# MY ORDERS
# ============================================================

async def my_orders(update, context):

    orders = await get_customer_orders(
        update.effective_user.id
    )

    if not orders:
        await update.message.reply_text(
            "📋 Sizda hali buyurtmalar yo'q."
        )
        return

    for order in orders[:10]:

        buttons = []

        if order["status"] == STATUS_COMPLETED:
            buttons.append([
                InlineKeyboardButton(
                    "💳 To'lov",
                    callback_data=f"payment:{order['id']}",
                ),
                InlineKeyboardButton(
                    "⭐ Reyting",
                    callback_data=f"rating:{order['id']}",
                ),
            ])

        if order["status"] in (
            STATUS_ACCEPTED,
            STATUS_ON_WAY,
            STATUS_STARTED,
        ):
            buttons.append([
                InlineKeyboardButton(
                    "💬 Usta bilan chat",
                    callback_data=f"chat:{order['id']}",
                )
            ])

        await update.message.reply_text(
            format_order(order),
            parse_mode=ParseMode.HTML,
            reply_markup=(
                InlineKeyboardMarkup(buttons)
                if buttons
                else None
            ),
        )


# ============================================================
# CHAT
# ============================================================

async def chat_callback(update, context):

    query = update.callback_query
    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    order = await get_order(order_id)

    if not order:
        return

    if update.effective_user.id not in (
        order["customer_id"],
        order["master_id"],
    ):
        return

    context.user_data["chat_order_id"] = order_id

    await query.message.reply_text(
        "💬 <b>Chat</b>\n\n"
        "Xabaringizni yozing.\n"
        "Xabar boshqa ishtirokchiga yuboriladi.\n\n"
        "Chiqish: /stopchat",
        parse_mode=ParseMode.HTML,
    )

    return C_CHAT


async def receive_chat(update, context):

    order_id = context.user_data.get(
        "chat_order_id"
    )

    if not order_id:
        return

    order = await get_order(order_id)

    if not order:
        return

    sender_id = update.effective_user.id

    if sender_id == order["customer_id"]:
        receiver_id = order["master_id"]
    elif sender_id == order["master_id"]:
        receiver_id = order["customer_id"]
    else:
        return

    text = update.message.text

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO messages
            (
                order_id,
                sender_id,
                receiver_id,
                message
            )
            VALUES ($1,$2,$3,$4)
        """,
            order_id,
            sender_id,
            receiver_id,
            text,
        )

    await context.bot.send_message(
        receiver_id,
        f"💬 <b>Buyurtma #{order_id}</b>\n\n"
        f"{update.effective_user.full_name}:\n"
        f"{text}",
        parse_mode=ParseMode.HTML,
    )

    await update.message.reply_text(
        "✅ Xabar yuborildi."
    )


async def stop_chat(update, context):

    context.user_data.pop(
        "chat_order_id",
        None,
    )

    await update.message.reply_text(
        "💬 Chat yopildi.",
        reply_markup=main_menu(),
    )


# ============================================================
# MASTER MENU
# ============================================================

async def master_new_orders(update, context):

    if update.effective_user.id == ADMIN_ID:
        return

    user = await get_user(
        update.effective_user.id
    )

    if not user or user["role"] != ROLE_MASTER:
        await update.message.reply_text(
            "❌ Siz usta sifatida ro'yxatdan o'tmagansiz."
        )
        return

    orders = await get_waiting_orders()

    if not orders:
        await update.message.reply_text(
            "📭 Hozircha yangi buyurtmalar yo'q."
        )
        return

    for order in orders:

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Qabul qilish",
                    callback_data=f"accept:{order['id']}",
                ),
                InlineKeyboardButton(
                    "❌ Rad etish",
                    callback_data=f"reject:{order['id']}",
                ),
            ]
        ])

        await update.message.reply_text(
            format_order(order),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def master_active_orders(update, context):

    orders = await get_master_orders(
        update.effective_user.id
    )

    active = [
        x for x in orders
        if x["status"] in (
            STATUS_ACCEPTED,
            STATUS_ON_WAY,
            STATUS_STARTED,
        )
    ]

    if not active:
        await update.message.reply_text(
            "📭 Faol buyurtmalar yo'q."
        )
        return

    for order in active:

        buttons = []

        if order["status"] in (
            STATUS_ACCEPTED,
            STATUS_ON_WAY,
        ):
            buttons.append([
                InlineKeyboardButton(
                    "🔧 Ishni boshlash",
                    callback_data=f"startwork:{order['id']}",
                )
            ])

        if order["status"] == STATUS_STARTED:
            buttons.append([
                InlineKeyboardButton(
                    "🏁 Ishni yakunlash",
                    callback_data=f"finish:{order['id']}",
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "💬 Chat",
                callback_data=f"chat:{order['id']}",
            )
        ])

        await update.message.reply_text(
            format_order(order),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                buttons
            ),
        )


async def master_history(update, context):

    orders = await get_master_orders(
        update.effective_user.id,
        30,
    )

    completed = [
        x for x in orders
        if x["status"] == STATUS_COMPLETED
    ]

    if not completed:
        await update.message.reply_text(
            "📜 Tarix bo'sh."
        )
        return

    for order in completed[:10]:
        await update.message.reply_text(
            format_order(order),
            parse_mode=ParseMode.HTML,
        )


async def master_online(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user or user["role"] != ROLE_MASTER:
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET is_online=TRUE
            WHERE telegram_id=$1
        """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        "🟢 Siz ONLINE holatdasiz.\n"
        "Yangi buyurtmalar kelishi mumkin.",
        reply_markup=master_menu(),
    )


async def master_offline(update, context):

    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET is_online=FALSE
            WHERE telegram_id=$1
        """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        "🔴 Siz OFFLINE holatdasiz.",
        reply_markup=master_menu(),
    )


async def master_income(update, context):

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow("""
            SELECT
                COUNT(*) AS orders_count,
                COALESCE(
                    SUM(total_price),
                    0
                ) AS total
            FROM orders
            WHERE master_id=$1
              AND status='completed'
        """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        "💰 <b>DAROMADIM</b>\n\n"
        f"📋 Buyurtmalar: {row['orders_count']} ta\n"
        f"💰 Jami: {float(row['total']):,.0f} so'm",
        parse_mode=ParseMode.HTML,
    )


async def master_rating(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user:
        return

    await update.message.reply_text(
        "⭐ <b>REYTINGIM</b>\n\n"
        f"⭐ Reyting: {float(user['rating']):.2f}\n"
        f"📊 Baholar: {user['rating_count']} ta\n"
        f"📋 Tugallangan: {user['completed_orders']} ta",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(user_id):
    return user_id == ADMIN_ID


# ============================================================
# ADMIN STATISTICS
# ============================================================

async def admin_statistics(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        users = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        clients = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE role='client'
        """)

        masters = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE role='master'
        """)

        orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        completed = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE status='completed'
        """)

        revenue = await conn.fetchval("""
            SELECT COALESCE(SUM(total_price),0)
            FROM orders
            WHERE status='completed'
        """)

        rating = await conn.fetchval("""
            SELECT COALESCE(AVG(rating),0)
            FROM users
            WHERE role='master'
              AND rating_count > 0
        """)

        today_orders = await conn.fetchval("""
            SELECT COUNT(*)
            FROM orders
            WHERE created_at::date=CURRENT_DATE
        """)

        today_revenue = await conn.fetchval("""
            SELECT COALESCE(SUM(total_price),0)
            FROM orders
            WHERE status='completed'
              AND completed_at::date=CURRENT_DATE
        """)

    await update.message.reply_text(
        "📊 <b>USTA 24 ANDIJON</b>\n"
        "📊 <b>STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"👤 Mijozlar: {clients}\n"
        f"👨‍🔧 Ustalar: {masters}\n"
        f"📋 Buyurtmalar: {orders}\n"
        f"✅ Tugallangan: {completed}\n"
        f"💰 Daromad: {float(revenue):,.0f} so'm\n"
        f"⭐ O'rtacha reyting: {float(rating):.2f}\n\n"
        f"📅 Bugun: {today_orders} ta buyurtma\n"
        f"💰 Bugungi daromad: "
        f"{float(today_revenue):,.0f} so'm",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ADMIN USERS
# ============================================================

async def admin_masters(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT *
            FROM users
            WHERE role='master'
            ORDER BY rating DESC
        """)

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Ustalar yo'q."
        )
        return

    text = "👨‍🔧 <b>USTALAR</b>\n\n"

    for i, row in enumerate(rows, 1):
        online = "🟢" if row["is_online"] else "🔴"

        text += (
            f"{i}. {online} "
            f"<b>{row['full_name']}</b>\n"
            f"   ID: {row['telegram_id']}\n"
            f"   ⭐ {float(row['rating']):.2f}\n"
            f"   📋 {row['completed_orders']} ta\n\n"
        )

    await update.message.reply_text(
        text[:4000],
        parse_mode=ParseMode.HTML,
    )


async def admin_clients(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT *
            FROM users
            WHERE role='client'
            ORDER BY created_at DESC
            LIMIT 50
        """)

    text = "👥 <b>MIJOZLAR</b>\n\n"

    for row in rows:
        text += (
            f"👤 {row['full_name']}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🆔 {row['telegram_id']}\n"
            f"📋 {row['completed_orders']}\n"
            f"🎁 {row['bonus_points']} 🪙\n\n"
        )

    await update.message.reply_text(
        text[:4000],
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ADMIN ORDERS
# ============================================================

async def admin_orders(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT *
            FROM orders
            ORDER BY created_at DESC
            LIMIT 20
        """)

    if not rows:
        await update.message.reply_text(
            "📋 Buyurtmalar yo'q."
        )
        return

    for order in rows:
        await update.message.reply_text(
            format_order(order),
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# ADMIN BROADCAST
# ============================================================

async def admin_broadcast_start(update, context):

    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "📢 Yuboriladigan xabarni yozing:"
    )

    return A_BROADCAST


async def admin_broadcast_send(update, context):

    if not is_admin(update.effective_user.id):
        return

    text = update.message.text

    async with db_pool.acquire() as conn:
        users = await conn.fetch("""
            SELECT telegram_id
            FROM users
            WHERE is_active=TRUE
        """)

    sent = 0
    failed = 0

    for row in users:

        try:
            await context.bot.send_message(
                row["telegram_id"],
                "📢 <b>USTA 24 ANDIJON</b>\n\n"
                + text,
                parse_mode=ParseMode.HTML,
            )

            sent += 1

            await asyncio.sleep(0.05)

        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📢 <b>Рассылка tugadi</b>\n\n"
        f"✅ Yuborildi: {sent}\n"
        f"❌ Xato: {failed}",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN REPORT CSV
# ============================================================

async def admin_report(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        rows = await conn.fetch("""
            SELECT
                id,
                customer_name,
                customer_phone,
                service_name,
                address,
                total_price,
                status,
                master_name,
                payment_status,
                created_at
            FROM orders
            ORDER BY created_at DESC
        """)

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "ID",
        "Customer",
        "Phone",
        "Service",
        "Address",
        "Total",
        "Status",
        "Master",
        "Payment",
        "Created",
    ])

    for row in rows:
        writer.writerow([
            row["id"],
            row["customer_name"],
            row["customer_phone"],
            row["service_name"],
            row["address"],
            float(row["total_price"]),
            row["status"],
            row["master_name"],
            row["payment_status"],
            row["created_at"],
        ])

    data = io.BytesIO(
        output.getvalue().encode("utf-8-sig")
    )

    data.name = "usta24_report.csv"

    await update.message.reply_document(
        document=data,
        caption="📄 USTA 24 buyurtmalar hisoboti",
    )


# ============================================================
# PROFILE
# ============================================================

async def profile(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user:
        return

    await update.message.reply_text(
        "👤 <b>PROFIL</b>\n\n"
        f"👤 Ism: {user['full_name']}\n"
        f"📞 Telefon: {user['phone'] or '-'}\n"
        f"📋 Buyurtmalar: {user['completed_orders']}\n"
        f"🎁 Bonus: {user['bonus_points']} 🪙\n"
        f"⭐ Reyting: {float(user['rating']):.2f}",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# BONUS
# ============================================================

async def bonuses(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user:
        return

    points = user["bonus_points"]

    if points >= 1000:
        level = "🥇 Oltin"
    elif points >= 500:
        level = "🥈 Kumush"
    else:
        level = "🥉 Bronza"

    await update.message.reply_text(
        "🎁 <b>LOYALLIK</b>\n\n"
        f"🏅 Daraja: {level}\n"
        f"🪙 Bonus: {points}\n"
        f"💰 100 🪙 = 1,000 so'm chegirma",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# CONTACT
# ============================================================

async def contact(update, context):

    await update.message.reply_text(
        "📞 <b>USTA 24 ANDIJON</b>\n\n"
        "☎️ Aloqa: +998 XX XXX XX XX\n"
        "📍 Andijon shahri\n\n"
        "Operator bilan bog'lanish uchun xabar qoldiring.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ROLE ASSIGN
# ============================================================

async def admin_make_master(update, context):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Foydalanish:\n"
            "/master TELEGRAM_ID"
        )
        return

    try:
        user_id = int(
            context.args[0]
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Telegram ID noto'g'ri."
        )
        return

    await upsert_user(
        await context.bot.get_chat(user_id)
    )

    await set_role(
        user_id,
        ROLE_MASTER,
    )

    await update.message.reply_text(
        f"✅ {user_id} endi USTA."
    )

    try:
        await context.bot.send_message(
            user_id,
            "👨‍🔧 Siz USTA 24 tizimiga usta sifatida qo'shildingiz.\n\n"
            "Botni qayta oching: /start",
        )
    except Exception:
        pass


# ============================================================
# ADMIN COMMAND
# ============================================================

async def admin_command(update, context):

    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )
        return

    await update.message.reply_text(
        "👑 <b>ADMIN PANEL</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_menu(),
    )


# ============================================================
# MASTER COMMAND
# ============================================================

async def master_command(update, context):

    user = await get_user(
        update.effective_user.id
    )

    if not user or user["role"] != ROLE_MASTER:
        await update.message.reply_text(
            "❌ Siz usta sifatida ro'yxatdan o'tmagansiz."
        )
        return

    await update.message.reply_text(
        "👨‍🔧 <b>USTA PANELI</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=master_menu(),
    )


# ============================================================
# AUTOMATIC REMINDERS
# ============================================================

async def reminder_worker(app):

    while True:

        try:

            # 1. Accepted but not started
            async with db_pool.acquire() as conn:

                rows = await conn.fetch("""
                    SELECT *
                    FROM orders
                    WHERE status IN ('accepted','on_way')
                      AND accepted_at IS NOT NULL
                      AND accepted_at <
                          NOW() - INTERVAL '2 hours'
                """)

            for order in rows:

                try:
                    await app.bot.send_message(
                        order["master_id"],
                        f"🔔 Eslatma\n\n"
                        f"Buyurtma #{order['id']} hali "
                        "boshlanmagan.",
                    )
                except Exception:
                    pass

            # 2. Started but not completed
            async with db_pool.acquire() as conn:

                rows = await conn.fetch("""
                    SELECT *
                    FROM orders
                    WHERE status='started'
                      AND started_at IS NOT NULL
                      AND started_at <
                          NOW() - INTERVAL '6 hours'
                """)

            for order in rows:

                try:
                    await app.bot.send_message(
                        order["master_id"],
                        f"🔔 Eslatma\n\n"
                        f"Buyurtma #{order['id']} "
                        "6 soatdan beri jarayonda.",
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(
                "Reminder worker error: %s",
                e,
            )

        await asyncio.sleep(300)


# ============================================================
# TEXT ROUTER
# ============================================================

async def text_router(update, context):

    if not update.message:
        return

    text = update.message.text

    user = await get_user(
        update.effective_user.id
    )

    if not user:
        await upsert_user(
            update.effective_user
        )
        user = await get_user(
            update.effective_user.id
        )

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if is_admin(update.effective_user.id):

        if text == "👨‍🔧 Ustalar":
            await admin_masters(update, context)
            return

        if text == "📋 Buyurtmalar":
            await admin_orders(update, context)
            return

        if text == "👥 Mijozlar":
            await admin_clients(update, context)
            return

        if text == "📊 Statistika":
            await admin_statistics(update, context)
            return

        if text == "📄 Hisobot":
            await admin_report(update, context)
            return

        if text == "💬 Xabarlar":
            await admin_broadcast_start(
                update,
                context,
            )
            return

        if text == "💰 Narxlar":
            await services_command(update, context)
            return

        if text == "🎟 Kuponlar":
            await update.message.reply_text(
                "🎟 Kupon boshqaruvi:\n\n"
                "Hozircha PostgreSQL orqali boshqariladi."
            )
            return

        if text == "⚙️ Sozlamalar":
            await update.message.reply_text(
                "⚙️ Sozlamalar\n\n"
                "Bot konfiguratsiyasi .env orqali boshqariladi."
            )
            return

    # --------------------------------------------------------
    # MASTER
    # --------------------------------------------------------

    if user["role"] == ROLE_MASTER:

        if text == "📋 Yangi buyurtmalar":
            await master_new_orders(
                update,
                context,
            )
            return

        if text == "🔧 Faol buyurtmalar":
            await master_active_orders(
                update,
                context,
            )
            return

        if text == "📜 Tarix":
            await master_history(
                update,
                context,
            )
            return

        if text == "🟢 Online":
            await master_online(
                update,
                context,
            )
            return

        if text == "🔴 Offline":
            await master_offline(
                update,
                context,
            )
            return

        if text == "💰 Daromadim":
            await master_income(
                update,
                context,
            )
            return

        if text == "⭐ Reytingim":
            await master_rating(
                update,
                context,
            )
            return

        if text == "👤 Profil":
            await profile(
                update,
                context,
            )
            return

    # --------------------------------------------------------
    # CLIENT
    # --------------------------------------------------------

    if text == "🛠 Buyurtma berish":
        await new_order(
            update,
            context,
        )
        return

    if text == "📋 Xizmatlar":
        await services_command(
            update,
            context,
        )
        return

    if text == "🔍 Buyurtmalarim":
        await my_orders(
            update,
            context,
        )
        return

    if text == "🔄 Qayta buyurtma":
        await update.message.reply_text(
            "🔄 Qayta buyurtma qilish uchun "
            "yangi xizmat tanlang."
        )
        await new_order(
            update,
            context,
        )
        return

    if text == "⭐ Reytinglarim":
        await update.message.reply_text(
            "⭐ Sizning reytinglaringiz "
            "tugallangan buyurtmalar orqali saqlanadi."
        )
        return

    if text == "🎁 Bonuslarim":
        await bonuses(
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

    if text == "👤 Profil":
        await profile(
            update,
            context,
        )
        return

    if text == "✍️ Manzilni qo'lda yozish":
        await manual_address(
            update,
            context,
        )
        return

    # If user is waiting for address
    if context.user_data.get("waiting_address"):
        await receive_address(
            update,
            context,
        )
        return

    await update.message.reply_text(
        "🏠 Menyu:",
        reply_markup=(
            admin_menu()
            if is_admin(update.effective_user.id)
            else master_menu()
            if user["role"] == ROLE_MASTER
            else main_menu()
        ),
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    logger.exception(
        "Unhandled exception:",
        exc_info=context.error,
    )

    try:

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Тизимда вақтинчалик хато юз берди.\n"
                "Илтимос, қайта уриниб кўринг."
            )

    except Exception:
        pass


# ============================================================
# POST INIT
# ============================================================

async def post_init(application):

    await init_db()

    application.create_task(
        reminder_worker(application)
    )

    logger.info(
        "USTA 24 ANDIJON started."
    )


# ============================================================
# POST SHUTDOWN
# ============================================================

async def post_shutdown(application):

    global db_pool

    if db_pool:
        await db_pool.close()

    logger.info(
        "PostgreSQL connection closed."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi."
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL topilmadi."
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
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
            "master",
            master_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "services",
            services_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "stopchat",
            stop_chat,
        )
    )

    application.add_handler(
        CommandHandler(
            "report",
            admin_report,
        )
    )

    application.add_handler(
        CommandHandler(
            "make_master",
            admin_make_master,
        )
    )

    # --------------------------------------------------------
    # CONTACT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            handle_contact,
        )
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.LOCATION,
            handle_location,
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            category_callback,
            pattern=r"^cat:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            service_callback,
            pattern=r"^service:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            time_callback,
            pattern=r"^time:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            coupon_callback,
            pattern=r"^coupon:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_order_callback,
            pattern=r"^order:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            master_accept_callback,
            pattern=r"^accept:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            master_reject_callback,
            pattern=r"^reject:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            arrival_callback,
            pattern=r"^arrival:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            start_work_callback,
            pattern=r"^startwork:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            finish_work_callback,
            pattern=r"^finish:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            finish_confirm_callback,
            pattern=r"^finishconfirm:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            payment_callback,
            pattern=r"^payment:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            pay_method_callback,
            pattern=r"^pay:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            rating_callback,
            pattern=r"^rating:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            stars_callback,
            pattern=r"^stars:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            chat_callback,
            pattern=r"^chat:",
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_review,
            block=False,
        )
    )

    # Main router after specialized handlers
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router,
            block=False,
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    logger.info(
        "Starting Telegram polling..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
