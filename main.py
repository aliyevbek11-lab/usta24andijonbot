# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# Python 3.11+
# python-telegram-bot 22.3
# asyncpg 0.30.0
# Flask 3.1.1
# gunicorn 23.0.0
#
# 1 BOT = CLIENT + MASTER + ADMIN + MASTERS GROUP
# PostgreSQL
# ============================================================

import os
import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional

import asyncpg

from flask import Flask
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable topilmadi")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")

# ============================================================
# FLASK / HEALTH
# ============================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "USTA 24 ANDIJON BOT OK", 200


@flask_app.route("/health")
def health():
    return "OK", 200


def run_flask():
    port = int(os.getenv("PORT", "8080"))
    flask_app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


# ============================================================
# DATABASE
# ============================================================

db_pool: Optional[asyncpg.Pool] = None


async def init_db():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client',
                address TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                rating DOUBLE PRECISION DEFAULT 5.0,
                rating_count INTEGER DEFAULT 0,
                bonus INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # AUTO MIGRATION
        # ----------------------------------------------------

        user_columns = {
            "username": "TEXT",
            "full_name": "TEXT",
            "phone": "TEXT",
            "role": "TEXT DEFAULT 'client'",
            "address": "TEXT",
            "latitude": "DOUBLE PRECISION",
            "longitude": "DOUBLE PRECISION",
            "rating": "DOUBLE PRECISION DEFAULT 5.0",
            "rating_count": "INTEGER DEFAULT 0",
            "bonus": "INTEGER DEFAULT 0",
            "is_active": "BOOLEAN DEFAULT TRUE",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for column, definition in user_columns.items():
            try:
                await conn.execute(
                    f'ALTER TABLE users ADD COLUMN IF NOT EXISTS "{column}" {definition}'
                )
            except Exception as e:
                logger.warning("users migration %s: %s", column, e)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                customer_name TEXT,
                phone TEXT,
                service TEXT,
                description TEXT,
                address TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                order_time TEXT,
                photo_file_ids TEXT,
                status TEXT DEFAULT 'new',
                master_id BIGINT,
                master_name TEXT,
                master_rating DOUBLE PRECISION DEFAULT 5.0,
                price INTEGER DEFAULT 0,
                payment_method TEXT DEFAULT 'cash',
                urgent BOOLEAN DEFAULT FALSE,
                urgent_percent INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        order_columns = {
            "customer_id": "BIGINT",
            "customer_name": "TEXT",
            "phone": "TEXT",
            "service": "TEXT",
            "description": "TEXT",
            "address": "TEXT",
            "latitude": "DOUBLE PRECISION",
            "longitude": "DOUBLE PRECISION",
            "order_time": "TEXT",
            "photo_file_ids": "TEXT",
            "status": "TEXT DEFAULT 'new'",
            "master_id": "BIGINT",
            "master_name": "TEXT",
            "master_rating": "DOUBLE PRECISION DEFAULT 5.0",
            "price": "INTEGER DEFAULT 0",
            "payment_method": "TEXT DEFAULT 'cash'",
            "urgent": "BOOLEAN DEFAULT FALSE",
            "urgent_percent": "INTEGER DEFAULT 0",
            "started_at": "TIMESTAMP",
            "completed_at": "TIMESTAMP",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

        for column, definition in order_columns.items():
            try:
                await conn.execute(
                    f'ALTER TABLE orders ADD COLUMN IF NOT EXISTS "{column}" {definition}'
                )
            except Exception as e:
                logger.warning("orders migration %s: %s", column, e)

        # ----------------------------------------------------
        # RATINGS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                customer_id BIGINT,
                master_id BIGINT,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # SERVICES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                price INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)

        # ----------------------------------------------------
        # NOTIFICATIONS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                text TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # DEFAULT SERVICES
        # ----------------------------------------------------

        services = [
            ("🔧 Mebel yig'ish", 50000),
            ("🪑 Mebel ta'mirlash", 50000),
            ("🍳 Oshxona mebeli", 50000),
            ("🚪 Shkaf / kupe", 50000),
            ("🛏 Karavot", 50000),
            ("🪑 Stol / stul", 40000),
            ("📦 Mebel yechish", 50000),
            ("📦 Mebel yig'ish", 50000),
            ("🚚 Mebel tashish", 100000),
            ("🏠 Uy ko'chirish", 150000),
            ("⚡ Elektr", 50000),
            ("💧 Santexnika", 50000),
            ("🚪 Eshik ta'mirlash", 50000),
            ("🔨 Boshqa xizmat", 50000),
        ]

        for name, price in services:
            await conn.execute(
                """
                INSERT INTO services (name, price)
                VALUES ($1, $2)
                ON CONFLICT (name) DO NOTHING
                """,
                name,
                price,
            )

    logger.info("PostgreSQL database tayyor")


# ============================================================
# DB HELPERS
# ============================================================

async def get_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM users
            WHERE telegram_id = $1
            """,
            telegram_id,
        )


async def ensure_user(tg_user):
    telegram_id = tg_user.id
    username = tg_user.username or ""
    full_name = tg_user.full_name or ""

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                full_name
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = CURRENT_TIMESTAMP
            """,
            telegram_id,
            username,
            full_name,
        )


async def set_user_role(telegram_id: int, role: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET role = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = $2
            """,
            role,
            telegram_id,
        )


async def update_user_phone(telegram_id: int, phone: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET phone = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = $2
            """,
            phone,
            telegram_id,
        )


async def update_user_address(
    telegram_id: int,
    address: str,
    latitude=None,
    longitude=None,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET address = $1,
                latitude = $2,
                longitude = $3,
                updated_at = CURRENT_TIMESTAMP
            WHERE telegram_id = $4
            """,
            address,
            latitude,
            longitude,
            telegram_id,
        )


async def create_order(data):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO orders (
                customer_id,
                customer_name,
                phone,
                service,
                description,
                address,
                latitude,
                longitude,
                order_time,
                photo_file_ids,
                status,
                price,
                payment_method,
                urgent,
                urgent_percent
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                'new',$11,'cash',$12,$13
            )
            RETURNING id
            """,
            data["customer_id"],
            data["customer_name"],
            data["phone"],
            data["service"],
            data.get("description", ""),
            data["address"],
            data.get("latitude"),
            data.get("longitude"),
            data.get("order_time", ""),
            data.get("photo_file_ids", ""),
            data.get("price", 0),
            data.get("urgent", False),
            data.get("urgent_percent", 0),
        )

        return row["id"]


async def get_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )


async def update_order_status(order_id: int, status: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET status = $1
            WHERE id = $2
            """,
            status,
            order_id,
        )


async def accept_order(
    order_id: int,
    master_id: int,
    master_name: str,
    master_rating: float,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE orders
            SET status = 'accepted',
                master_id = $1,
                master_name = $2,
                master_rating = $3
            WHERE id = $4
              AND status = 'new'
            RETURNING *
            """,
            master_id,
            master_name,
            master_rating,
            order_id,
        )

        return row


async def start_order(order_id: int, master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE orders
            SET status = 'in_progress',
                started_at = CURRENT_TIMESTAMP
            WHERE id = $1
              AND master_id = $2
              AND status = 'accepted'
            RETURNING *
            """,
            order_id,
            master_id,
        )


async def complete_order(order_id: int, master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE orders
            SET status = 'completed',
                completed_at = CURRENT_TIMESTAMP
            WHERE id = $1
              AND master_id = $2
              AND status = 'in_progress'
            RETURNING *
            """,
            order_id,
            master_id,
        )


async def add_rating(
    order_id: int,
    customer_id: int,
    master_id: int,
    rating: int,
    comment: str,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ratings (
                order_id,
                customer_id,
                master_id,
                rating,
                comment
            )
            VALUES ($1,$2,$3,$4,$5)
            """,
            order_id,
            customer_id,
            master_id,
            rating,
            comment,
        )

        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS cnt,
                COALESCE(AVG(rating), 5.0) AS avg_rating
            FROM ratings
            WHERE master_id = $1
            """,
            master_id,
        )

        await conn.execute(
            """
            UPDATE users
            SET rating = $1,
                rating_count = $2
            WHERE telegram_id = $3
            """,
            float(stats["avg_rating"]),
            int(stats["cnt"]),
            master_id,
        )


# ============================================================
# KEYBOARDS
# ============================================================

def client_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Buyurtma berish", "📋 Mening buyurtmalarim"],
            ["🔍 Buyurtma holati", "❌ Bekor qilish"],
            ["🔁 Qayta buyurtma", "👨‍🔧 Mening ustalarim"],
            ["⭐ Reytingim", "📝 Sharh qoldirish"],
            ["📌 Eslatmalarim", "🗺️ Yaqin atrofdagi ustalar"],
            ["📅 Yozilma (bron)", "🎁 Loyallik va bonuslar"],
            ["🤖 AI yordamchi", "⚙️ Sozlamalar"],
            ["📊 Mening statistika", "🏷️ Chegirmalar va aksiyalar"],
            ["📞 Tez yordam", "🔔 Bildirishnomalar"],
            ["📁 Mening hujjatlarim", "🕊️ Do'stga tavsiya qilish"],
            ["📞 Dispetcherga qo'ng'iroq", "🚨 24/7 Shosilinch rejim"],
            ["👨‍🔧 Usta rejimi"],
        ],
        resize_keyboard=True,
    )


def master_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📋 Yangi buyurtmalar", "✅ Mening faol buyurtmalarim"],
            ["⏳ Tarix", "💰 Ish haqi va hisobot"],
            ["⭐ Reytingim va sharhlar", "📅 Kunlik ish jadvalim"],
            ["🔔 Mijozlar bilan bog'lanish", "📸 Galereya"],
            ["🛠 Xizmatlarni boshqarish", "📊 Ish statistikasi"],
            ["🏷️ Mening narxlarim", "📍 Ish hududim"],
            ["📅 Dam olish kunlari", "🔔 Bildirishnoma sozlamalari"],
            ["📝 Reytingni oshirish", "🎁 Usta bonuslari"],
            ["🤖 AI yordamchi", "📞 Texnik yordam"],
            ["📢 E'lonlar va yangiliklar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcherga qo'ng'iroq", "🚨 24/7 Shosilinch rejim"],
            ["👤 Mijoz rejimi"],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "🛠 Buyurtmalar"],
            ["👨‍🔧 Ustalar", "⭐ Reyting va sharhlar"],
            ["🎁 Loyallik va bonuslar", "💰 To'lovlar"],
            ["🏷️ Chegirmalar va aksiyalar", "🛠 Xizmat turlari"],
            ["📊 Statistika va hisobot", "📢 E'lonlar va yangiliklar"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
            ["📸 Rasm galereyasi", "📱 Botni boshqarish"],
            ["📞 Qo'llab-quvvatlash", "🚨 24/7 Shosilinch rejim"],
            ["👤 Mijoz rejimi"],
        ],
        resize_keyboard=True,
    )


def service_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🔧 Mebel yig'ish", "🪑 Mebel ta'mirlash"],
            ["🍳 Oshxona mebeli", "🚪 Shkaf / kupe"],
            ["🛏 Karavot", "🪑 Stol / stul"],
            ["📦 Mebel yechish", "📦 Mebel yig'ish"],
            ["🚚 Mebel tashish", "🏠 Uy ko'chirish"],
            ["⚡ Elektr", "💧 Santexnika"],
            ["🚪 Eshik ta'mirlash", "🔨 Boshqa xizmat"],
            ["⬅️ Orqaga"],
        ],
        resize_keyboard=True,
    )


def urgent_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🔴 HOZIR — 20% ustama"],
            ["🟡 YARIM SOATDA — 10% ustama"],
            ["🟢 1 SOATDA — oddiy narx"],
            ["⬅️ Orqaga"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# HELPERS
# ============================================================

def get_role(user_id: int):
    if user_id == ADMIN_ID:
        return "admin"
    return None


async def role_of(user_id: int):
    if user_id == ADMIN_ID:
        return "admin"

    user = await get_user(user_id)

    if not user:
        return "client"

    return user["role"] or "client"


async def safe_send(
    bot,
    chat_id,
    text,
    **kwargs,
):
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            **kwargs,
        )
    except Exception as e:
        logger.warning(
            "Xabar yuborilmadi chat=%s error=%s",
            chat_id,
            e,
        )
        return None


async def notify_admin(bot, text):
    if ADMIN_ID:
        await safe_send(bot, ADMIN_ID, text)


async def notify_customer(bot, customer_id, text):
    await safe_send(bot, customer_id, text)


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not user:
        return

    await ensure_user(user)

    context.user_data.clear()

    role = await role_of(user.id)

    if role == "admin":
        await update.message.reply_text(
            "👨‍💼 <b>USTA 24 ANDIJON — ADMIN</b>\n\n"
            "Тизимга хуш келибсиз!",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_keyboard(),
        )
        return

    if role == "master":
        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 ANDIJON — USTA</b>\n\n"
            "Хуш келибсиз, уста!",
            parse_mode=ParseMode.HTML,
            reply_markup=master_keyboard(),
        )
        return

    await update.message.reply_text(
        "👋 <b>USTA 24 ANDIJON</b>\n\n"
        "🏠 Уйга хизмат кўрсатиш хизмати.\n"
        "🕐 24/7 ишлаймиз.\n"
        "💵 Тўлов — фақат ишдан кейин нақд.\n\n"
        "Керакли хизматни танланг:",
        parse_mode=ParseMode.HTML,
        reply_markup=client_keyboard(),
    )


# ============================================================
# ORDER START
# ============================================================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "order"
    context.user_data["step"] = "phone"

    await update.message.reply_text(
        "🛒 <b>ЯНГИ БУЮРТМА</b>\n\n"
        "Аввало телефон рақамингизни юборинг:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📞 Телефон рақамимни юбориш",
                        request_contact=True,
                    )
                ],
                ["⬅️ Орқага"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact

    if contact.user_id and contact.user_id != update.effective_user.id:
        await update.message.reply_text(
            "❌ Илтимос, ўз телефон рақамингизни юборинг."
        )
        return

    phone = contact.phone_number

    await update_user_phone(
        update.effective_user.id,
        phone,
    )

    if context.user_data.get("flow") == "order":
        context.user_data["phone"] = phone
        context.user_data["step"] = "service"

        await update.message.reply_text(
            "🛠 <b>Хизмат турини танланг:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=service_keyboard(),
        )
    else:
        await update.message.reply_text(
            "✅ Телефон рақамингиз сақланди.",
            reply_markup=client_keyboard(),
        )


# ============================================================
# ORDER SERVICE
# ============================================================

async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "⬅️ Orqaga" or text == "⬅️ Орқага":
        context.user_data.clear()
        await update.message.reply_text(
            "Асосий меню:",
            reply_markup=client_keyboard(),
        )
        return

    services = [
        "🔧 Mebel yig'ish",
        "🪑 Mebel ta'mirlash",
        "🍳 Oshxona mebeli",
        "🚪 Shkaf / kupe",
        "🛏 Karavot",
        "🪑 Stol / stul",
        "📦 Mebel yechish",
        "📦 Mebel yig'ish",
        "🚚 Mebel tashish",
        "🏠 Uy ko'chirish",
        "⚡ Elektr",
        "💧 Santexnika",
        "🚪 Eshik ta'mirlash",
        "🔨 Boshqa xizmat",
    ]

    if text not in services:
        await update.message.reply_text(
            "❗ Илтимос, хизматни кнопкадан танланг."
        )
        return

    context.user_data["service"] = text
    context.user_data["step"] = "description"

    await update.message.reply_text(
        "📝 <b>Муаммони қисқача ёзинг:</b>\n\n"
        "Масалан:\n"
        "«Розетка ишламаяпти»\n"
        "«Шкафни йиғиш керак»\n"
        "«Крандан сув оқяпти»",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                ["📸 Рasm yuborish"],
                ["⏭ Rasmsiz davom etish"],
                ["⬅️ Orqaga"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# ORDER PHOTO / DESCRIPTION
# ============================================================

async def handle_order_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("flow") != "order":
        return

    photo = update.message.photo[-1]

    ids = context.user_data.get("problem_photos", [])
    ids.append(photo.file_id)

    context.user_data["problem_photos"] = ids

    context.user_data["step"] = "address"

    await update.message.reply_text(
        "📸 Расм қабул қилинди.\n\n"
        "📍 Энди манзилингизни ёзинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📍 Геолокация юбориш",
                        request_location=True,
                    )
                ],
                ["⬅️ Orqaga"],
            ],
            resize_keyboard=True,
        ),
    )


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("flow") != "order":
        return

    context.user_data["step"] = "address"

    await update.message.reply_text(
        "📍 Манзилингизни ёзинг ёки геолокация юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📍 Геолокация юбориш",
                        request_location=True,
                    )
                ],
                ["⬅️ Orqaga"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# LOCATION
# ============================================================

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location

    lat = location.latitude
    lon = location.longitude

    context.user_data["latitude"] = lat
    context.user_data["longitude"] = lon

    context.user_data["address"] = (
        f"📍 Геолокация: {lat:.6f}, {lon:.6f}"
    )

    await update_user_address(
        update.effective_user.id,
        context.user_data["address"],
        lat,
        lon,
    )

    context.user_data["step"] = "time"

    await update.message.reply_text(
        "🕐 <b>Қачон уста керак?</b>\n\n"
        "Вақтни ёзинг.\n"
        "Масалан: <b>10:30</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                ["🚨 24/7 Шошилинч"],
                ["⬅️ Orqaga"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# ORDER CONFIRMATION
# ============================================================

async def create_order_from_context(update, context):
    user = update.effective_user

    phone = context.user_data.get("phone", "")
    if not phone:
        db_user = await get_user(user.id)
        if db_user:
            phone = db_user["phone"] or ""

    if not phone:
        await update.message.reply_text(
            "❗ Аввало телефон рақамингизни юборинг."
        )
        return

    service = context.user_data.get("service", "Boshqa xizmat")
    address = context.user_data.get("address", "")
    description = context.user_data.get("description", "")
    order_time = context.user_data.get("order_time", "")

    urgent = context.user_data.get("urgent", False)
    urgent_percent = context.user_data.get("urgent_percent", 0)

    # Базавий нарх
    price = 50000

    if urgent_percent:
        price = int(price * (100 + urgent_percent) / 100)

    photos = context.user_data.get("problem_photos", [])

    order_id = await create_order(
        {
            "customer_id": user.id,
            "customer_name": user.full_name,
            "phone": phone,
            "service": service,
            "description": description,
            "address": address,
            "latitude": context.user_data.get("latitude"),
            "longitude": context.user_data.get("longitude"),
            "order_time": order_time,
            "photo_file_ids": ",".join(photos),
            "price": price,
            "urgent": urgent,
            "urgent_percent": urgent_percent,
        }
    )

    order = await get_order(order_id)

    await send_order_to_group(
        context.bot,
        order,
    )

    await notify_admin(
        context.bot,
        f"🆕 <b>ЯНГИ БУЮРТМА #{order_id}</b>\n\n"
        f"👤 Мижоз: {user.full_name}\n"
        f"📞 Телефон: {phone}\n"
        f"🛠 Хизмат: {service}\n"
        f"📍 Манзил: {address}\n"
        f"💰 Бошланғич нарх: {price:,} сўм\n"
        f"💵 Тўлов: нақд, ишдан кейин",
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ <b>Буюртмангиз қабул қилинди!</b>\n\n"
        f"🆔 Заказ: <b>#{order_id}</b>\n"
        f"🛠 Хизмат: {service}\n"
        f"📍 Манзил: {address}\n"
        f"🕐 Вақт: {order_time}\n\n"
        f"👨‍🔧 Ҳозир усталарга юборилди.\n"
        f"⏳ Уста қабул қилганда сизга хабар берамиз.\n\n"
        f"💵 Тўлов: <b>фақат нақд, ишдан кейин</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=client_keyboard(),
    )


async def send_order_to_group(bot, order):
    if not MASTERS_GROUP_ID:
        logger.warning("MASTERS_GROUP_ID berilmagan")
        return

    urgent_text = ""

    if order["urgent"]:
        urgent_text = (
            f"\n🚨 <b>24/7 ШОШИЛИНЧ</b>"
            f"\n📈 Устама: {order['urgent_percent']}%"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ QABUL QILISH",
                    callback_data=f"accept:{order['id']}",
                ),
                InlineKeyboardButton(
                    "❌ RAD ETISH",
                    callback_data=f"reject:{order['id']}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📸 RASMNI KO'RISH",
                    callback_data=f"photos:{order['id']}",
                )
            ],
        ]
    )

    text = (
        f"🆕 <b>YANGI BUYURTMA #{order['id']}</b>\n\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['phone']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"📝 Muammo: {order['description'] or 'Ko‘rsatilmagan'}\n"
        f"🕐 Vaqt: {order['order_time']}\n"
        f"💰 Narx: {order['price']:,} so'm\n"
        f"💵 To'lov: NAQD / ISHDAN KEYIN"
        f"{urgent_text}"
    )

    await safe_send(
        bot,
        MASTERS_GROUP_ID,
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )

    # Фото бўлса группада ҳам кўрсатиш
    photo_ids = (order["photo_file_ids"] or "").split(",")

    for file_id in photo_ids:
        if file_id:
            try:
                await bot.send_photo(
                    chat_id=MASTERS_GROUP_ID,
                    photo=file_id,
                    caption=f"📸 Muammo rasmi — buyurtma #{order['id']}",
                )
            except Exception as e:
                logger.warning("Photo groupga yuborilmadi: %s", e)


# ============================================================
# MASTER ACCEPT
# ============================================================

async def callback_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    master = query.from_user
    order_id = int(query.data.split(":")[1])

    await ensure_user(master)

    user = await get_user(master.id)

    # Группадаги ҳар қандай Telegram user'ни автоматик master қилмаймиз,
    # лекин қабул қилиш босилса мастер сифатида белгиланади.
    if user["role"] not in ("master", "admin"):
        await set_user_role(master.id, "master")
        rating = 5.0
    else:
        rating = float(user["rating"] or 5.0)

    master_name = master.full_name

    order = await accept_order(
        order_id,
        master.id,
        master_name,
        rating,
    )

    if not order:
        await query.answer(
            "❌ Бу буюртма аллақачон қабул қилинган.",
            show_alert=True,
        )
        return

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.message.reply_text(
        f"✅ <b>BUYURTMA #{order_id} QABUL QILINDI</b>\n\n"
        f"👨‍🔧 Usta: {master_name}\n"
        f"⭐ Reyting: {rating:.1f}\n\n"
        f"🔧 Ишни бошлаш учун:\n"
        f"<b>🔧 Ishni boshlash</b> тугмасини босинг.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔧 ISHNI BOSHLASH",
                        callback_data=f"startjob:{order_id}",
                    )
                ]
            ]
        ),
    )

    await notify_customer(
        context.bot,
        order["customer_id"],
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"🆔 #{order_id}\n"
        f"👨‍🔧 Usta: <b>{master_name}</b>\n"
        f"⭐ Reyting: {rating:.1f}\n\n"
        f"⏳ Уста белгиланган вақтда ишни бошлайди.",
    )


# ============================================================
# MASTER REJECT
# ============================================================

async def callback_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    order = await get_order(order_id)

    if not order:
        return

    if order["status"] != "new":
        await query.answer(
            "Бу заказ энди очиқ эмас.",
            show_alert=True,
        )
        return

    await query.message.reply_text(
        f"❌ Usta заказ #{order_id} ни рад этди.\n"
        f"🔄 Бошқа усталар кўриб чиқсин."
    )

    await notify_customer(
        context.bot,
        order["customer_id"],
        f"❌ <b>Buyurtma #{order_id}</b>\n\n"
        f"Бир уста буюртмани қабул қила олмади.\n"
        f"🔄 Бошқа усталарни қидиряпмиз.",
    )

    await query.answer("Rad etildi")


# ============================================================
# MASTER START JOB
# ============================================================

async def callback_start_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    master_id = query.from_user.id
    order_id = int(query.data.split(":")[1])

    order = await start_order(
        order_id,
        master_id,
    )

    if not order:
        await query.answer(
            "❌ Заказ ҳолати нотўғри.",
            show_alert=True,
        )
        return

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📸 ISHNI YAKUNLASH",
                        callback_data=f"complete:{order_id}",
                    )
                ]
            ]
        )
    )

    await query.message.reply_text(
        f"🔧 <b>#{order_id} иш бошланди!</b>\n\n"
        f"👨‍🔧 Usta: {order['master_name']}\n"
        f"📸 Иш тугагач натижа расмини юборинг.",
        parse_mode=ParseMode.HTML,
    )

    await notify_customer(
        context.bot,
        order["customer_id"],
        f"🔧 <b>Иш бошланди!</b>\n\n"
        f"🆔 #{order_id}\n"
        f"👨‍🔧 Usta: {order['master_name']}\n\n"
        f"Иш якунлангач натижа расми юборилади.",
    )


# ============================================================
# COMPLETE
# ============================================================

async def callback_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    context.user_data["complete_order_id"] = order_id
    context.user_data["flow"] = "complete_photo"

    await query.message.reply_text(
        f"📸 <b>#{order_id} ишини якунлаш</b>\n\n"
        f"Иш натижасининг расмини юборинг.\n"
        f"<b>Расм мажбурий.</b>",
        parse_mode=ParseMode.HTML,
    )


async def handle_complete_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("flow") != "complete_photo":
        return

    order_id = context.user_data.get("complete_order_id")

    if not order_id:
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    order = await get_order(order_id)

    if not order:
        await update.message.reply_text("❌ Заказ топилмади.")
        context.user_data.clear()
        return

    completed = await complete_order(
        order_id,
        update.effective_user.id,
    )

    if not completed:
        await update.message.reply_text(
            "❌ Бу заказни якунлаш мумкин эмас."
        )
        context.user_data.clear()
        return

    # Натижа расмини customer'га юбориш
    try:
        await context.bot.send_photo(
            chat_id=order["customer_id"],
            photo=file_id,
            caption=(
                f"✅ <b>Иш якунланди!</b>\n\n"
                f"🆔 #{order_id}\n"
                f"👨‍🔧 Usta: {order['master_name']}\n"
                f"💰 Сумма: {order['price']:,} сўм\n\n"
                f"💵 Тўлов: <b>ФАҚАТ НАҚД</b>\n"
                f"⏳ Тўлов — ишдан кейин."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("Customerga result photo yuborilmadi: %s", e)

    # Group
    await safe_send(
        context.bot,
        MASTERS_GROUP_ID,
        f"✅ <b>#{order_id} BUYURTMA YAKUNLANDI!</b>\n\n"
        f"👨‍🔧 Usta: {order['master_name']}\n"
        f"⭐ Usta reytingi: {float(order['master_rating'] or 5):.1f}\n"
        f"💰 Summa: {order['price']:,} so'm\n"
        f"📸 Natija rasmi yuborildi.",
        parse_mode=ParseMode.HTML,
    )

    # Admin
    await notify_admin(
        context.bot,
        f"✅ <b>ISH YAKUNLANDI</b>\n\n"
        f"🆔 #{order_id}\n"
        f"👨‍🔧 Usta: {order['master_name']}\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"💰 Summa: {order['price']:,} so'm\n"
        f"💵 To'lov: NAQD",
        parse_mode=ParseMode.HTML,
    )

    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=f"📸 #{order_id} натижа расми",
        )
    except Exception:
        pass

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ <b>#{order_id} иши якунланди!</b>\n\n"
        f"📸 Натижа расми сақланди.\n"
        f"💵 Мijoz нақд тўлайди.",
        parse_mode=ParseMode.HTML,
        reply_markup=master_keyboard(),
    )


# ============================================================
# MASTER MENUS
# ============================================================

async def master_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "👤 Mijoz rejimi":
        await set_user_role(user_id, "client")
        await update.message.reply_text(
            "👤 Мижоз режими ёқилди.",
            reply_markup=client_keyboard(),
        )
        return

    if text == "📋 Yangi buyurtmalar":
        await show_new_orders(update, context)
        return

    if text == "✅ Mening faol buyurtmalarim":
        await show_master_active(update, context)
        return

    if text == "⏳ Tarix":
        await show_master_history(update, context)
        return

    if text == "💰 Ish haqi va hisobot":
        await show_master_salary(update, context)
        return

    if text == "⭐ Reytingim va sharhlar":
        await show_my_rating(update, context)
        return

    if text == "📊 Ish statistikasi":
        await show_master_statistics(update, context)
        return

    if text == "🏆 Ustalar reytingi":
        await show_top_masters(update, context)
        return

    if text == "📞 Dispetcherga qo'ng'iroq":
        await dispatcher(update, context)
        return

    if text == "🚨 24/7 Shosilinch rejim":
        await urgent_info(update, context)
        return

    await generic_master_button(update, context)


async def show_new_orders(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE status = 'new'
            ORDER BY created_at DESC
            LIMIT 20
            """
        )

    if not rows:
        await update.message.reply_text(
            "📭 Ҳозирча янги буюртмалар йўқ.",
            reply_markup=master_keyboard(),
        )
        return

    for order in rows:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ QABUL",
                        callback_data=f"accept:{order['id']}",
                    ),
                    InlineKeyboardButton(
                        "❌ RAD",
                        callback_data=f"reject:{order['id']}",
                    ),
                ]
            ]
        )

        await update.message.reply_text(
            f"🆕 <b>#{order['id']}</b>\n"
            f"🛠 {order['service']}\n"
            f"👤 {order['customer_name']}\n"
            f"📞 {order['phone']}\n"
            f"📍 {order['address']}\n"
            f"💰 {order['price']:,} сўм",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def show_master_active(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id = $1
              AND status IN ('accepted','in_progress')
            ORDER BY created_at DESC
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "📭 Фаол буюртмаларингиз йўқ."
        )
        return

    for order in rows:
        await update.message.reply_text(
            f"📋 <b>#{order['id']}</b>\n\n"
            f"🛠 {order['service']}\n"
            f"👤 {order['customer_name']}\n"
            f"📞 {order['phone']}\n"
            f"📍 {order['address']}\n"
            f"📌 Ҳолат: {order['status']}",
            parse_mode=ParseMode.HTML,
        )


async def show_master_history(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id = $1
              AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 30
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "📭 Ҳали якунланган буюртмалар йўқ."
        )
        return

    text = "⏳ <b>ЯКУНЛАНГАН БУЮРТМАЛАР</b>\n\n"

    for order in rows:
        text += (
            f"#{order['id']} — {order['service']} — "
            f"{order['price']:,} сўм\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


async def show_master_salary(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS cnt,
                COALESCE(SUM(price), 0) AS total
            FROM orders
            WHERE master_id = $1
              AND status = 'completed'
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"💰 <b>ИШ ҲАҚИ ВА ҲИСОБОТ</b>\n\n"
        f"📋 Якунланган ишлар: {row['cnt']}\n"
        f"💵 Жами: {int(row['total']):,} сўм\n\n"
        f"Тўлов тури: 💵 нақд",
        parse_mode=ParseMode.HTML,
    )


async def show_my_rating(update, context):
    user = await get_user(update.effective_user.id)

    rating = float(user["rating"] or 5)
    count = int(user["rating_count"] or 0)

    await update.message.reply_text(
        f"⭐ <b>РЕЙТИНГИМ</b>\n\n"
        f"⭐ Рейтинг: <b>{rating:.1f}</b>\n"
        f"📝 Баҳо сони: {count}",
        parse_mode=ParseMode.HTML,
    )


async def show_master_statistics(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='in_progress') AS active,
                COALESCE(SUM(price) FILTER (WHERE status='completed'),0) AS income
            FROM orders
            WHERE master_id = $1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"📊 <b>ИШ СТАТИСТИКАСИ</b>\n\n"
        f"✅ Якунланган: {row['completed']}\n"
        f"🔧 Жараёнда: {row['active']}\n"
        f"💰 Даромад: {int(row['income']):,} сўм",
        parse_mode=ParseMode.HTML,
    )


async def show_top_masters(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT full_name, rating, rating_count
            FROM users
            WHERE role = 'master'
              AND is_active = TRUE
            ORDER BY rating DESC, rating_count DESC
            LIMIT 10
            """
        )

    if not rows:
        await update.message.reply_text(
            "🏆 Ҳали усталар рейтинги шаклланмаган."
        )
        return

    text = "🏆 <b>TOP 10 USTALAR</b>\n\n"

    for i, row in enumerate(rows, 1):
        text += (
            f"{i}. 👨‍🔧 {row['full_name'] or 'Usta'} — "
            f"⭐ {float(row['rating'] or 5):.1f}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


async def generic_master_button(update, context):
    await update.message.reply_text(
        "ℹ️ Бу бўлим кейинги версияларда кенгайтирилади.\n\n"
        "Ҳозир заказ қабул қилиш, иш бошлаш ва якунлаш тизими ишлайди.",
        reply_markup=master_keyboard(),
    )


# ============================================================
# CLIENT MENUS
# ============================================================

async def client_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "👨‍🔧 Usta rejimi":
        user = await get_user(update.effective_user.id)

        # ADMIN устасига айланмайди
        if update.effective_user.id != ADMIN_ID:
            await set_user_role(
                update.effective_user.id,
                "master",
            )

        await update.message.reply_text(
            "👨‍🔧 <b>УСТА РЕЖИМИ</b>\n\n"
            "Хуш келибсиз!",
            parse_mode=ParseMode.HTML,
            reply_markup=master_keyboard(),
        )
        return

    if text == "🛒 Buyurtma berish":
        await start_order(update, context)
        return

    if text == "📋 Mening buyurtmalarim":
        await my_orders(update, context)
        return

    if text == "🔍 Buyurtma holati":
        await order_status_menu(update, context)
        return

    if text == "❌ Bekor qilish":
        await cancel_order_menu(update, context)
        return

    if text == "🔁 Qayta buyurtma":
        await repeat_order(update, context)
        return

    if text == "👨‍🔧 Mening ustalarim":
        await my_masters(update, context)
        return

    if text == "⭐ Reytingim":
        await my_rating(update, context)
        return

    if text == "📝 Sharh qoldirish":
        await review_menu(update, context)
        return

    if text == "🎁 Loyallik va bonuslar":
        await loyalty(update, context)
        return

    if text == "📊 Mening statistika":
        await client_statistics(update, context)
        return

    if text == "🏷️ Chegirmalar va aksiyalar":
        await discounts(update, context)
        return

    if text == "📞 Dispetcherga qo'ng'iroq":
        await dispatcher(update, context)
        return

    if text == "📞 Tez yordam":
        await dispatcher(update, context)
        return

    if text == "🚨 24/7 Shosilinch rejim":
        await urgent_info(update, context)
        return

    if text == "⚙️ Sozlamalar":
        await settings(update, context)
        return

    if text == "🤖 AI yordamchi":
        await update.message.reply_text(
            "🤖 AI ёрдамчи:\n\n"
            "Хизмат, таъмир ёки буюртма бўйича саволингизни ёзинг."
        )
        context.user_data["ai_mode"] = True
        return

    if text == "📌 Eslatmalarim":
        await update.message.reply_text(
            "📌 Ҳозирча эслатмаларингиз йўқ."
        )
        return

    if text == "🗺️ Yaqin atrofdagi ustalar":
        await update.message.reply_text(
            "🗺️ Яқин усталарни аниқлаш учун буюртмада геолокация юборинг."
        )
        return

    if text == "📅 Yozilma (bron)":
        await update.message.reply_text(
            "📅 Брон қилиш буюртма бериш жараёнида амалга оширилади."
        )
        return

    if text == "🔔 Bildirishnomalar":
        await update.message.reply_text(
            "🔔 Билдиришномалар ёқилган."
        )
        return

    if text == "📁 Mening hujjatlarim":
        await update.message.reply_text(
            "📁 Ҳужжатларингиз ҳозирча йўқ."
        )
        return

    if text == "🕊️ Do'stga tavsiya qilish":
        await update.message.reply_text(
            "🕊️ USTA 24 ANDIJON'ни дўстларингизга тавсия қилинг!\n\n"
            "https://t.me/usta24_bot"
        )
        return

    await update.message.reply_text(
        "Асосий меню:",
        reply_markup=client_keyboard(),
    )


# ============================================================
# CLIENT ORDER LIST
# ============================================================

async def my_orders(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE customer_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "📭 Ҳали буюртмаларингиз йўқ."
        )
        return

    for order in rows:
        await update.message.reply_text(
            f"📋 <b>#{order['id']}</b>\n\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n"
            f"📌 Ҳолат: <b>{order['status']}</b>\n"
            f"💰 Сумма: {order['price']:,} сўм",
            parse_mode=ParseMode.HTML,
        )


async def order_status_menu(update, context):
    await my_orders(update, context)


async def cancel_order_menu(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, service, status
            FROM orders
            WHERE customer_id = $1
              AND status IN ('new','accepted')
            ORDER BY created_at DESC
            LIMIT 10
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "❌ Бекор қилиш мумкин бўлган заказ йўқ."
        )
        return

    buttons = []

    for row in rows:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"❌ #{row['id']} — {row['service']}",
                    callback_data=f"cancel:{row['id']}",
                )
            ]
        )

    await update.message.reply_text(
        "❌ Бекор қилмоқчи бўлган заказни танланг:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_cancel(update, context):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    order = await get_order(order_id)

    if not order:
        return

    if order["customer_id"] != query.from_user.id:
        await query.answer("❌ Бу сизга тегишли эмас.", show_alert=True)
        return

    if order["status"] not in ("new", "accepted"):
        await query.answer(
            "❌ Бу заказни бекор қилиб бўлмайди.",
            show_alert=True,
        )
        return

    await update_order_status(
        order_id,
        "cancelled",
    )

    await query.edit_message_text(
        f"✅ Buyurtma #{order_id} бекор қилинди."
    )

    await notify_admin(
        context.bot,
        f"❌ Buyurtma #{order_id} мижоз томонидан бекор қилинди."
    )


async def repeat_order(update, context):
    await update.message.reply_text(
        "🔁 Қайта буюртма бериш:",
        reply_markup=service_keyboard(),
    )

    context.user_data.clear()
    context.user_data["flow"] = "order"
    context.user_data["step"] = "service_repeat"


async def my_masters(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT master_id, master_name, master_rating
            FROM orders
            WHERE customer_id = $1
              AND master_id IS NOT NULL
            ORDER BY master_rating DESC
            LIMIT 10
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Ҳали сизга хизмат кўрсатган уста йўқ."
        )
        return

    text = "👨‍🔧 <b>МЕНИНГ УСТАЛАРИМ</b>\n\n"

    for row in rows:
        text += (
            f"👨‍🔧 {row['master_name']}\n"
            f"⭐ {float(row['master_rating'] or 5):.1f}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


async def my_rating(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS cnt,
                COALESCE(AVG(r.rating),0) AS avg_rating
            FROM ratings r
            WHERE r.customer_id = $1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"⭐ <b>МЕНИНГ РЕЙТИНГИМ</b>\n\n"
        f"📝 Қолдирган баҳолар: {row['cnt']}\n"
        f"⭐ Ўртача: {float(row['avg_rating'] or 0):.1f}",
        parse_mode=ParseMode.HTML,
    )


async def review_menu(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE customer_id = $1
              AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 10
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "📝 Баҳо қолдириш учун якунланган заказингиз бўлиши керак."
        )
        return

    buttons = []

    for row in rows:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"⭐ #{row['id']} — {row['master_name'] or 'Usta'}",
                    callback_data=f"rate:{row['id']}",
                )
            ]
        )

    await update.message.reply_text(
        "⭐ Баҳо қолдириш учун заказни танланг:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_rate(update, context):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    context.user_data["rating_order_id"] = order_id
    context.user_data["flow"] = "rating"

    buttons = [
        [
            InlineKeyboardButton("⭐ 1", callback_data="rating:1"),
            InlineKeyboardButton("⭐ 2", callback_data="rating:2"),
            InlineKeyboardButton("⭐ 3", callback_data="rating:3"),
        ],
        [
            InlineKeyboardButton("⭐ 4", callback_data="rating:4"),
            InlineKeyboardButton("⭐ 5", callback_data="rating:5"),
        ],
    ]

    await query.message.reply_text(
        "⭐ Устага неча баҳо берасиз?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def callback_rating_value(update, context):
    query = update.callback_query
    await query.answer()

    rating = int(query.data.split(":")[1])
    order_id = context.user_data.get("rating_order_id")

    if not order_id:
        return

    order = await get_order(order_id)

    if not order:
        return

    if order["customer_id"] != query.from_user.id:
        return

    await add_rating(
        order_id,
        query.from_user.id,
        order["master_id"],
        rating,
        "",
    )

    await query.message.reply_text(
        f"⭐ Раҳмат! Сиз {rating}⭐ баҳо бердингиз."
    )

    await notify_customer(
        context.bot,
        order["master_id"],
        f"⭐ <b>ЯНГИ БАҲО!</b>\n\n"
        f"Мижоз сизга <b>{rating}⭐</b> баҳо қолдирди.\n"
        f"🆔 Заказ #{order_id}",
        parse_mode=ParseMode.HTML,
    )

    context.user_data.clear()


async def loyalty(update, context):
    user = await get_user(update.effective_user.id)

    await update.message.reply_text(
        f"🎁 <b>LOYALLIK VA BONUSLAR</b>\n\n"
        f"💎 Баланс: <b>{int(user['bonus'] or 0)}</b> бонус\n\n"
        f"Кейинчалик бонуслар тизими кенгайтирилади.",
        parse_mode=ParseMode.HTML,
    )


async def client_statistics(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
            FROM orders
            WHERE customer_id = $1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"📊 <b>МЕНИНГ СТАТИСТИКАМ</b>\n\n"
        f"📋 Жами заказ: {row['total']}\n"
        f"✅ Якунланган: {row['completed']}\n"
        f"❌ Бекор қилинган: {row['cancelled']}",
        parse_mode=ParseMode.HTML,
    )


async def discounts(update, context):
    await update.message.reply_text(
        "🏷️ <b>ЧЕГИРМАЛАР ВА АКЦИЯЛАР</b>\n\n"
        "🎁 Ҳозирча махсус акция йўқ.\n"
        "Янги акциялар шу ерда чиқади.",
        parse_mode=ParseMode.HTML,
    )


async def settings(update, context):
    await update.message.reply_text(
        "⚙️ <b>СОЗЛАМАЛАР</b>\n\n"
        "🔔 Билдиришномалар: ON\n"
        "📍 Геолокация: буюртма вақтида\n"
        "💵 Тўлов: нақд",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# URGENT 24/7
# ============================================================

async def urgent_info(update, context):
    await update.message.reply_text(
        "🚨 <b>24/7 ШОШИЛИНЧ РЕЖИМ</b>\n\n"
        "🚨 ДАРҲОЛ ЁРДАМ КЕРАКМИ?\n"
        "💨 24/7 ишлаймиз!\n\n"
        "🔹 Долзарб ҳолатлар:\n"
        "💧 Сув\n"
        "⚡ Электр\n"
        "🔥 Газ\n"
        "🚪 Эшик\n"
        "🚰 Қувур\n\n"
        "🔴 ҲОЗИР — 10-15 дақиқа — <b>20% устама</b>\n"
        "🟡 ЯРИМ СОАТДА — <b>10% устама</b>\n"
        "🟢 1 СОАТДА — <b>оддий нарх</b>\n\n"
        "💵 Тўлов: <b>ФАҚАТ НАҚД + ИШДАН КЕЙИН</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=urgent_keyboard(),
    )

    context.user_data["urgent_select"] = True


async def handle_urgent_selection(update, context):
    text = update.message.text

    if text == "🔴 HOZIR — 20% ustama":
        context.user_data["urgent"] = True
        context.user_data["urgent_percent"] = 20

    elif text == "🟡 YARIM SOATDA — 10% ustama":
        context.user_data["urgent"] = True
        context.user_data["urgent_percent"] = 10

    elif text == "🟢 1 SOATDA — oddiy narx":
        context.user_data["urgent"] = False
        context.user_data["urgent_percent"] = 0

    else:
        return

    context.user_data["flow"] = "order"
    context.user_data["step"] = "phone"

    await update.message.reply_text(
        "🚨 Шошилинч буюртма бошланди.\n\n"
        "📞 Телефон рақамингизни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📞 Телефон рақамимни юбориш",
                        request_contact=True,
                    )
                ]
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# DISPATCHER
# ============================================================

async def dispatcher(update, context):
    await update.message.reply_text(
        f"📞 <b>ДИСПЕТЧЕР</b>\n\n"
        f"📞 Телефон: <b>{DISPATCHER_PHONE}</b>\n"
        f"🕐 Иш вақти: <b>24/7</b>\n"
        f"📍 Манзил: Andijon shahar\n\n"
        f"🚨 Шошилинч ҳолатларда дарҳол қўнғироқ қилинг.",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ADMIN
# ============================================================

async def admin_menu(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Сиз админ эмассиз.")
        return

    text = update.message.text

    if text == "👤 Mijoz rejimi":
        await update.message.reply_text(
            "👤 Мижоз режими:",
            reply_markup=client_keyboard(),
        )
        return

    if text == "👥 Foydalanuvchilar":
        await admin_users(update, context)
        return

    if text == "🛠 Buyurtmalar":
        await admin_orders(update, context)
        return

    if text == "👨‍🔧 Ustalar":
        await admin_masters(update, context)
        return

    if text == "⭐ Reyting va sharhlar":
        await admin_ratings(update, context)
        return

    if text == "💰 To'lovlar":
        await admin_payments(update, context)
        return

    if text == "🛠 Xizmat turlari":
        await admin_services(update, context)
        return

    if text == "📊 Statistika va hisobot":
        await admin_statistics(update, context)
        return

    if text == "📞 Dispetcher":
        await dispatcher(update, context)
        return

    if text == "🚨 24/7 Shosilinch rejim":
        await urgent_info(update, context)
        return

    if text == "📢 E'lonlar va yangiliklar":
        await update.message.reply_text(
            "📢 Эълон функцияси тайёр. Кейинги қадамда broadcast қўшилади."
        )
        return

    if text == "📸 Rasm galereyasi":
        await update.message.reply_text(
            "📸 Галерея заказлар натижа расмларидан ташкил топади."
        )
        return

    await update.message.reply_text(
        "⚙️ Admin bo'limi:",
        reply_markup=admin_keyboard(),
    )


async def admin_users(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE role='client') AS clients,
                COUNT(*) FILTER (WHERE role='master') AS masters,
                COUNT(*) FILTER (WHERE role='admin') AS admins
            FROM users
            """
        )

    await update.message.reply_text(
        f"👥 <b>FOYDALANUVCHILAR</b>\n\n"
        f"👤 Мижозлар: {row['clients']}\n"
        f"👨‍🔧 Усталар: {row['masters']}\n"
        f"👨‍💼 Админлар: {row['admins']}\n"
        f"📊 Жами: {row['total']}",
        parse_mode=ParseMode.HTML,
    )


async def admin_orders(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status='new') AS new,
                COUNT(*) FILTER (WHERE status='accepted') AS accepted,
                COUNT(*) FILTER (WHERE status='in_progress') AS active,
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
            FROM orders
            """
        )

    await update.message.reply_text(
        f"🛠 <b>BUYURTMALAR</b>\n\n"
        f"📋 Жами: {row['total']}\n"
        f"🆕 Янги: {row['new']}\n"
        f"✅ Қабул қилинган: {row['accepted']}\n"
        f"🔧 Жараёнда: {row['active']}\n"
        f"🏁 Якунланган: {row['completed']}\n"
        f"❌ Бекор қилинган: {row['cancelled']}",
        parse_mode=ParseMode.HTML,
    )


async def admin_masters(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT telegram_id, full_name, phone, rating, rating_count
            FROM users
            WHERE role='master'
            ORDER BY rating DESC
            LIMIT 30
            """
        )

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Усталар ҳали йўқ."
        )
        return

    text = "👨‍🔧 <b>USTALAR</b>\n\n"

    for row in rows:
        text += (
            f"👨‍🔧 {row['full_name'] or 'Usta'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"⭐ {float(row['rating'] or 5):.1f}\n"
            f"📝 {row['rating_count'] or 0} баҳо\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


async def admin_ratings(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(AVG(rating),0) AS avg_rating
            FROM ratings
            """
        )

    await update.message.reply_text(
        f"⭐ <b>РЕЙТИНГ ВА ШАРҲЛАР</b>\n\n"
        f"📝 Жами баҳолар: {row['total']}\n"
        f"⭐ Ўртача: {float(row['avg_rating'] or 0):.2f}",
        parse_mode=ParseMode.HTML,
    )


async def admin_payments(update, context):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status='completed') AS cnt,
                COALESCE(
                    SUM(price) FILTER (WHERE status='completed'),
                    0
                ) AS total
            FROM orders
            """
        )

    await update.message.reply_text(
        f"💰 <b>ТЎЛОВЛАР</b>\n\n"
        f"💵 Тўлов тури: НАҚД\n"
        f"📋 Якунланган ишлар: {row['cnt']}\n"
        f"💰 Жами: {int(row['total']):,} сўм\n\n"
        f"❌ Click / Payme / Uzcard / Visa / Mastercard:\n"
        f"қабул қилинмайди.",
        parse_mode=ParseMode.HTML,
    )


async def admin_services(update, context):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name, price, is_active
            FROM services
            ORDER BY id
            """
        )

    text = "🛠 <b>ХИЗМАТ ТУРЛАРИ</b>\n\n"

    for row in rows:
        status = "✅" if row["is_active"] else "❌"

        text += (
            f"{status} {row['name']} — "
            f"{row['price']:,} сўм\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
    )


async def admin_statistics(update, context):
    async with db_pool.acquire() as conn:
        users = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='completed'
            """
        )

        income = await conn.fetchval(
            """
            SELECT COALESCE(SUM(price),0)
            FROM orders
            WHERE status='completed'
            """
        )

    await update.message.reply_text(
        f"📊 <b>USTA 24 STATISTIKA</b>\n\n"
        f"👥 Фойдаланувчилар: {users}\n"
        f"📋 Заказлар: {orders}\n"
        f"✅ Якунланган: {completed}\n"
        f"💰 Тушум: {int(income):,} сўм",
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ORDER TEXT FLOW
# ============================================================

async def handle_text_flow(update, context):
    text = update.message.text
    user_id = update.effective_user.id

    # --------------------------------------------------------
    # URGENT
    # --------------------------------------------------------

    if context.user_data.get("urgent_select"):
        await handle_urgent_selection(update, context)
        context.user_data.pop("urgent_select", None)
        return

    # --------------------------------------------------------
    # ORDER FLOW
    # --------------------------------------------------------

    if context.user_data.get("flow") == "order":

        step = context.user_data.get("step")

        if step == "service":
            await handle_service(update, context)
            return

        if step == "service_repeat":
            await handle_service(update, context)
            context.user_data["step"] = "description"
            return

        if step == "description":

            if text == "📸 Rasm yuborish":
                await update.message.reply_text(
                    "📸 Муаммо расмини юборинг."
                )
                context.user_data["step"] = "photo"
                return

            if text == "⏭ Rasmsiz davom etish":
                context.user_data["step"] = "address"

                await update.message.reply_text(
                    "📍 Манзилингизни ёзинг ёки геолокация юборинг:",
                    reply_markup=ReplyKeyboardMarkup(
                        [
                            [
                                KeyboardButton(
                                    "📍 Геолокация юбориш",
                                    request_location=True,
                                )
                            ]
                        ],
                        resize_keyboard=True,
                    ),
                )
                return

            context.user_data["description"] = text
            context.user_data["step"] = "address"

            await update.message.reply_text(
                "📍 Энди манзилингизни ёзинг ёки геолокация юборинг:",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [
                            KeyboardButton(
                                "📍 Геолокация юбориш",
                                request_location=True,
                            )
                        ]
                    ],
                    resize_keyboard=True,
                ),
            )
            return

        if step == "address":

            if text == "📍 Геолокация юбориш":
                await update.message.reply_text(
                    "📍 Telegram орқали геолокацияни юборинг."
                )
                return

            context.user_data["address"] = text

            await update_user_address(
                user_id,
                text,
            )

            context.user_data["step"] = "time"

            await update.message.reply_text(
                "🕐 Қайси вақтда уста керак?\n\n"
                "Масалан: <b>10:30</b>",
                parse_mode=ParseMode.HTML,
            )
            return

        if step == "time":

            if text == "🚨 24/7 Шошилинч":
                context.user_data["urgent"] = True
                context.user_data["urgent_percent"] = 20

            else:
                context.user_data["order_time"] = text

            if context.user_data.get("urgent"):
                await update.message.reply_text(
                    "🚨 Шошилинч буюртма.\n"
                    "Қачон келишини танланг:",
                    reply_markup=urgent_keyboard(),
                )

                context.user_data["urgent_select"] = True
                context.user_data["flow"] = "urgent_confirmation"
                return

            await show_order_confirmation(update, context)
            return

    # --------------------------------------------------------
    # URGENT CONFIRMATION
    # --------------------------------------------------------

    if context.user_data.get("flow") == "urgent_confirmation":

        if text in (
            "🔴 HOZIR — 20% ustama",
            "🟡 YARIM SOATDA — 10% ustama",
            "🟢 1 SOATDA — oddiy narx",
        ):

            if "20%" in text:
                context.user_data["urgent_percent"] = 20
                context.user_data["order_time"] = "ҲОЗИР"

            elif "10%" in text:
                context.user_data["urgent_percent"] = 10
                context.user_data["order_time"] = "30 дақиқада"

            else:
                context.user_data["urgent_percent"] = 0
                context.user_data["order_time"] = "1 соатда"

            context.user_data["urgent"] = True
            context.user_data["flow"] = "order"
            context.user_data["step"] = "confirm"

            await show_order_confirmation(update, context)
            return

    # --------------------------------------------------------
    # CONFIRM
    # --------------------------------------------------------

    if context.user_data.get("step") == "confirm":

        if text == "✅ Tasdiqlash":

            await create_order_from_context(
                update,
                context,
            )
            return

        if text == "❌ Bekor qilish":

            context.user_data.clear()

            await update.message.reply_text(
                "❌ Буюртма бекор қилинди.",
                reply_markup=client_keyboard(),
            )
            return

    # --------------------------------------------------------
    # RATING COMMENT
    # --------------------------------------------------------

    if context.user_data.get("flow") == "rating":
        await update.message.reply_text(
            "⭐ Аввало рейтингни кнопка орқали танланг."
        )
        return

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    if context.user_data.get("ai_mode"):
        await update.message.reply_text(
            "🤖 AI ёрдамчи:\n\n"
            "Саволингизни қабул қилдим.\n"
            "Керакли хизматни танлаб, буюртма беришингиз мумкин.",
            reply_markup=client_keyboard(),
        )
        context.user_data.pop("ai_mode", None)
        return


async def show_order_confirmation(update, context):
    service = context.user_data.get("service", "")
    description = context.user_data.get("description", "")
    address = context.user_data.get("address", "")
    order_time = context.user_data.get("order_time", "")
    urgent_percent = context.user_data.get("urgent_percent", 0)

    base_price = 50000
    price = int(
        base_price * (100 + urgent_percent) / 100
    )

    context.user_data["price"] = price
    context.user_data["step"] = "confirm"
    context.user_data["flow"] = "order"

    await update.message.reply_text(
        f"📋 <b>БУЮРТМА ТЕКШИРУВИ</b>\n\n"
        f"🛠 Хизмат: {service}\n"
        f"📝 Муаммо: {description or '-'}\n"
        f"📍 Манзил: {address}\n"
        f"🕐 Вақт: {order_time}\n"
        f"💰 Бошланғич нарх: {price:,} сўм\n"
        f"💵 Тўлов: НАҚД, ИШДАН КЕЙИН\n"
        f"📈 Шошилинч устама: {urgent_percent}%\n\n"
        f"Тасдиқлайсизми?",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ Tasdiqlash"],
                ["❌ Bekor qilish"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# GENERIC MESSAGE ROUTER
# ============================================================

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user

    if user:
        await ensure_user(user)

    text = update.message.text or ""

    # Contact
    if update.message.contact:
        await handle_contact(update, context)
        return

    # Location
    if update.message.location:
        await handle_location(update, context)
        return

    # Photo
    if update.message.photo:
        if context.user_data.get("flow") == "complete_photo":
            await handle_complete_photo(update, context)
            return

        if context.user_data.get("flow") == "order":
            step = context.user_data.get("step")

            if step in ("photo", "description"):
                await handle_order_photo(update, context)
                return

        await update.message.reply_text(
            "📸 Расм қабул қилинди."
        )
        return

    # --------------------------------------------------------
    # ROLE
    # --------------------------------------------------------

    role = await role_of(user.id)

    # Admin
    if role == "admin":
        await admin_menu(update, context)

        # Агар махсус order flow бошланган бўлса, flow устувор
        if context.user_data.get("flow") == "order":
            await handle_text_flow(update, context)

        return

    # Master
    if role == "master":
        if (
            context.user_data.get("flow")
            in ("order", "urgent_confirmation")
            or context.user_data.get("step") in (
                "confirm",
                "description",
                "address",
                "time",
            )
        ):
            await handle_text_flow(update, context)
            return

        await master_menu(update, context)
        return

    # Client
    if (
        context.user_data.get("flow")
        in ("order", "urgent_confirmation")
        or context.user_data.get("step") in (
            "confirm",
            "description",
            "address",
            "time",
        )
    ):
        await handle_text_flow(update, context)
        return

    await client_menu(update, context)


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    if data.startswith("accept:"):
        await callback_accept(update, context)
        return

    if data.startswith("reject:"):
        await callback_reject(update, context)
        return

    if data.startswith("startjob:"):
        await callback_start_job(update, context)
        return

    if data.startswith("complete:"):
        await callback_complete(update, context)
        return

    if data.startswith("cancel:"):
        await callback_cancel(update, context)
        return

    if data.startswith("rate:"):
        await callback_rate(update, context)
        return

    if data.startswith("rating:"):
        await callback_rating_value(update, context)
        return

    if data.startswith("photos:"):
        await callback_photos(update, context)
        return

    await query.answer()


# ============================================================
# PHOTOS
# ============================================================

async def callback_photos(update, context):
    query = update.callback_query
    await query.answer()

    order_id = int(query.data.split(":")[1])

    order = await get_order(order_id)

    if not order:
        return

    photos = (order["photo_file_ids"] or "").split(",")

    sent = False

    for file_id in photos:
        if not file_id:
            continue

        try:
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=file_id,
                caption=f"📸 Buyurtma #{order_id} муаммо расми",
            )
            sent = True
        except Exception:
            pass

    if not sent:
        await query.message.reply_text(
            "📸 Бу заказда муаммо расми йўқ."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(
        "Unhandled exception:",
        exc_info=context.error,
    )


# ============================================================
# POST INIT
# ============================================================

async def post_init(application: Application):
    await init_db()

    logger.info("USTA 24 database initialized")

    # Bot commands
    try:
        await application.bot.set_my_commands(
            [
                ("start", "Ботни бошлаш"),
            ]
        )
    except Exception as e:
        logger.warning("Commands set error: %s", e)


# ============================================================
# MAIN
# ============================================================

def main():
    logger.info("====================================")
    logger.info("USTA 24 ANDIJON STARTING")
    logger.info("====================================")

    # Flask
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True,
    )

    flask_thread.start()

    # Telegram Application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    # Callback
    application.add_handler(
        CallbackQueryHandler(callback_router)
    )

    # Contact / location / photo / text
    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            message_router,
        )
    )

    # Error
    application.add_error_handler(error_handler)

    logger.info("Bot polling started")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
