#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA 24 ANDIJON
🏗️ ONE BOT = CLIENT + MASTER + ADMIN + MASTERS GROUP
🐘 PostgreSQL with asyncpg
📦 python-telegram-bot 22.3

🔧 ENV:
    BOT_TOKEN
    DATABASE_URL
    ADMIN_ID
    DISPATCHER_ID (optional)
    MASTERS_GROUP_ID (optional)
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import asyncpg

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

DISPATCHER_PHONE = "+9987706900003"

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL topilmadi!")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")

db_pool = None

# ============================================================
# STATES
# ============================================================

(
    ORDER_SERVICE,
    ORDER_DESCRIPTION,
    ORDER_PHOTO,
    ORDER_ADDRESS,
    ORDER_TIME,
    ORDER_CONFIRM,
    MASTER_NAME,
    MASTER_PHONE,
    REVIEW_MASTER,
    REVIEW_RATING,
    REVIEW_COMMENT,
) = range(11)

# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "🔧 Santexnika",
    "⚡ Elektrika",
    "🪑 Mebel yig'ish",
    "🛠 Mebel ta'mirlash",
    "🚚 Ko'chirish",
    "🚪 Eshik / qulf",
    "🎨 Ta'mirlash / bo'yoq",
    "❄️ Konditsioner",
    "🔥 Gaz xizmati",
    "🧰 Boshqa xizmat",
]

SERVICE_SUB = {
    "🔧 Santexnika": ["🚽 Hojatxona", "🚿 Lavabo", "🔧 Quvur", "🧹 Kanalizatsiya", "📋 Boshqa"],
    "⚡ Elektrika": ["💡 Chiroq", "🔌 Rozetka", "🔧 Sim", "⚡ Avtomat", "📋 Boshqa"],
    "🪑 Mebel yig'ish": ["🪑 Stul", "🛋 Divan", "🪑 Stol", "📋 Boshqa"],
    "🛠 Mebel ta'mirlash": ["🚪 Eshik", "🪟 Deraza", "🪑 Mebel", "📋 Boshqa"],
    "🚚 Ko'chirish": ["📦 Kichik", "📦 O'rta", "📦 Katta", "📋 Boshqa"],
    "🚪 Eshik / qulf": ["🚪 Eshik", "🔐 Qulf", "📋 Boshqa"],
    "🎨 Ta'mirlash / bo'yoq": ["🎨 Devor", "🪟 Deraza", "🚪 Eshik", "📋 Boshqa"],
    "❄️ Konditsioner": ["❄️ O'rnatish", "🧹 Tozalash", "🔧 Ta'mirlash", "📋 Boshqa"],
    "🔥 Gaz xizmati": ["🔥 O'rnatish", "🔧 Ta'mirlash", "📋 Boshqa"],
    "🧰 Boshqa xizmat": ["📋 Boshqa"],
}

# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    logger.info("🐘 PostgreSQL ulanish...")

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
            CREATE TABLE IF NOT EXISTS u24_users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'client',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_orders (
                id BIGSERIAL PRIMARY KEY,
                order_num TEXT UNIQUE,
                customer_id BIGINT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL DEFAULT '',
                sub_service TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                order_time TEXT NOT NULL DEFAULT '',
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                status TEXT NOT NULL DEFAULT 'new',
                master_id BIGINT,
                master_name TEXT NOT NULL DEFAULT '',
                master_phone TEXT NOT NULL DEFAULT '',
                price NUMERIC(12,2) NOT NULL DEFAULT 0,
                duration INTEGER NOT NULL DEFAULT 0,
                emergency BOOLEAN NOT NULL DEFAULT FALSE,
                emergency_percent INTEGER NOT NULL DEFAULT 0,
                result_photo TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """)

        # ----------------------------------------------------
        # PHOTOS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_order_photos (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                photo_type TEXT NOT NULL DEFAULT 'problem',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # RATINGS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT u24_rating_value CHECK (rating >= 1 AND rating <= 5)
            )
        """)

        # ----------------------------------------------------
        # SERVICES
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_services (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        for service in SERVICES:
            await conn.execute(
                """
                INSERT INTO u24_services(name)
                VALUES($1)
                ON CONFLICT(name) DO NOTHING
                """,
                service,
            )

        # ----------------------------------------------------
        # BONUSES
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_bonuses (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                order_id BIGINT,
                amount INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL DEFAULT 'order',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # REMINDERS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_reminders (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT NOT NULL,
                remind_at TIMESTAMPTZ NOT NULL,
                is_done BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # URGENT REQUESTS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_urgent_requests (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                issue_type TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                status TEXT NOT NULL DEFAULT 'kutilmoqda',
                master_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    logger.info("✅ PostgreSQL tayyor!")


async def get_db():
    return db_pool


# ============================================================
# USER FUNCTIONS
# ============================================================

async def ensure_user(tg_user):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_users (telegram_id, full_name, username)
            VALUES($1, $2, $3)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                updated_at = NOW()
            """,
            tg_user.id,
            tg_user.full_name or "",
            tg_user.username or "",
        )


async def get_user(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM u24_users WHERE telegram_id = $1",
            user_id,
        )


async def set_role(user_id, role):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_users
            SET role = $1, updated_at = NOW()
            WHERE telegram_id = $2
            """,
            role,
            user_id,
        )


async def save_phone(user_id, phone):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_users
            SET phone = $1, updated_at = NOW()
            WHERE telegram_id = $2
            """,
            phone,
            user_id,
        )


# ============================================================
# ORDER FUNCTIONS
# ============================================================

async def create_order(
    customer_id,
    customer_name,
    customer_phone,
    service,
    sub_service,
    description,
    address,
    order_time,
    emergency=False,
    emergency_percent=0,
    latitude=None,
    longitude=None,
):
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM u24_orders")
        order_num = f"#{1000 + count + 1}"

        row = await conn.fetchrow(
            """
            INSERT INTO u24_orders (
                order_num, customer_id, customer_name, customer_phone,
                service, sub_service, description, address, order_time,
                emergency, emergency_percent, latitude, longitude
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            RETURNING id
            """,
            order_num,
            customer_id,
            customer_name,
            customer_phone,
            service,
            sub_service,
            description,
            address,
            order_time,
            emergency,
            emergency_percent,
            latitude,
            longitude,
        )

        return row["id"], order_num


async def add_photo(order_id, file_id, photo_type="problem"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_order_photos (order_id, file_id, photo_type)
            VALUES($1,$2,$3)
            """,
            order_id,
            file_id,
            photo_type,
        )


async def get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM u24_orders WHERE id = $1",
            order_id,
        )


async def get_order_by_num(order_num):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM u24_orders WHERE order_num = $1",
            order_num,
        )


async def update_order_status(order_id, status):
    async with db_pool.acquire() as conn:
        if status == "accepted":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1, accepted_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )
        elif status == "started":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1, started_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )
        elif status == "completed":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1, completed_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )
        else:
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1
                WHERE id = $2
                """,
                status,
                order_id,
            )


async def assign_master(order_id, master_id, master_name, master_phone):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_orders
            SET master_id = $1,
                master_name = $2,
                master_phone = $3,
                status = 'accepted',
                accepted_at = NOW()
            WHERE id = $4
            """,
            master_id,
            master_name,
            master_phone,
            order_id,
        )


async def get_user_orders(user_id, status=None):
    async with db_pool.acquire() as conn:
        if status:
            return await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE customer_id = $1 AND status = $2
                ORDER BY id DESC
                """,
                user_id,
                status,
            )
        return await conn.fetch(
            """
            SELECT * FROM u24_orders
            WHERE customer_id = $1
            ORDER BY id DESC
            """,
            user_id,
        )


async def get_master_orders(master_id, status=None):
    async with db_pool.acquire() as conn:
        if status:
            return await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE master_id = $1 AND status = $2
                ORDER BY id DESC
                """,
                master_id,
                status,
            )
        return await conn.fetch(
            """
            SELECT * FROM u24_orders
            WHERE master_id = $1
            ORDER BY id DESC
            """,
            master_id,
        )


async def get_order_stats():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status='new') as new,
                COUNT(*) FILTER (WHERE status='accepted') as accepted,
                COUNT(*) FILTER (WHERE status='started') as started,
                COUNT(*) FILTER (WHERE status='completed') as completed,
                COUNT(*) FILTER (WHERE status='cancelled') as cancelled,
                COALESCE(SUM(price), 0) as total_price
            FROM u24_orders
            """
        )


# ============================================================
# RATING FUNCTIONS
# ============================================================

async def add_rating(order_id, customer_id, master_id, rating, comment):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_ratings (order_id, customer_id, master_id, rating, comment)
            VALUES($1,$2,$3,$4,$5)
            """,
            order_id,
            customer_id,
            master_id,
            rating,
            comment,
        )


async def get_master_rating(master_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total,
                COALESCE(AVG(rating), 0) as avg
            FROM u24_ratings
            WHERE master_id = $1
            """,
            master_id,
        )


# ============================================================
# BONUS FUNCTIONS
# ============================================================

async def add_bonus(user_id, order_id, amount, bonus_type="order"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_bonuses (user_id, order_id, amount, type)
            VALUES($1,$2,$3,$4)
            """,
            user_id,
            order_id,
            amount,
            bonus_type,
        )


async def get_user_bonus(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM u24_bonuses WHERE user_id = $1",
            user_id,
        )


# ============================================================
# KEYBOARDS
# ============================================================

def client_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Buyurtma berish", "📋 Mening buyurtmalarim"],
            ["🔍 Buyurtma holati", "❌ Bekor qilish"],
            ["🔁 Qayta buyurtma", "👨‍🔧 Mening ustalarim"],
            ["⭐ Reytingim", "📝 Sharh qoldirish"],
            ["📌 Eslatmalarim", "🗺 Yaqin atrofdagi ustalar"],
            ["📅 Yozilma", "🎁 Loyallik va bonuslar"],
            ["🤖 AI yordamchi", "⚙️ Sozlamalar"],
            ["📊 Mening statistikam", "🏷 Chegirmalar"],
            ["📞 Tez yordam", "🔔 Bildirishnomalar"],
            ["📁 Mening hujjatlarim", "🕊 Do'stga tavsiya"],
            ["📞 Dispetcher", "🚨 24/7 Shoshilinch"],
        ],
        resize_keyboard=True,
    )


def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["📋 Yangi buyurtmalar", "✅ Mening faol"],
            ["⏳ Tarix", "💰 Ish haqi"],
            ["⭐ Reytingim", "📅 Kunlik jadval"],
            ["🔔 Mijozlar bilan bog'lanish", "📸 Galereya"],
            ["🛠 Xizmatlarim", "📊 Ish statistikasi"],
            ["🏷 Mening narxlarim", "📍 Ish hududim"],
            ["📅 Dam olish kunlari", "🔔 Bildirishnoma"],
            ["📝 Reytingni oshirish", "🎁 Usta bonuslari"],
            ["🤖 AI yordamchi", "📞 Texnik yordam"],
            ["📢 E'lonlar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcher", "🚨 24/7 Shoshilinch"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "🛠 Buyurtmalar"],
            ["👨‍🔧 Ustalar", "⭐ Reytinglar"],
            ["🎁 Bonuslar", "💰 To'lovlar"],
            ["🏷 Chegirmalar", "🛠 Xizmat turlari"],
            ["📊 Statistika", "📢 E'lonlar"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
            ["📸 Galereya", "📱 Botni boshqarish"],
            ["📞 Qo'llab-quvvatlash", "🚨 24/7 Rejim"],
        ],
        resize_keyboard=True,
    )


def services_keyboard():
    buttons = []
    for service in SERVICES:
        buttons.append([KeyboardButton(service)])
    buttons.append([KeyboardButton("⬅️ Orqaga")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def sub_services_keyboard(service):
    buttons = []
    for sub in SERVICE_SUB.get(service, ["📋 Boshqa"]):
        buttons.append([KeyboardButton(sub)])
    buttons.append([KeyboardButton("⬅️ Orqaga")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


def phone_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📱 Telefon raqamni yuborish",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def time_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🔴 Hozir", "🟡 Bugun kechqurun"],
            ["🟢 Ertaga ertalab", "📆 Boshqa vaqt"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def rating_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⭐", callback_data="rating_1"),
                InlineKeyboardButton("⭐⭐", callback_data="rating_2"),
                InlineKeyboardButton("⭐⭐⭐", callback_data="rating_3"),
                InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rating_4"),
                InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rating_5"),
            ]
        ]
    )


# ============================================================
# START HANDLER
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        await ensure_user(user)

        if ADMIN_ID and user.id == ADMIN_ID:
            await set_role(user.id, "admin")
            await update.message.reply_text(
                "👑 USTA 24 ANDIJON\n\nАдмин панелига хуш келибсиз!",
                reply_markup=admin_menu(),
            )
            return

        db_user = await get_user(user.id)

        if db_user and db_user["role"] == "master":
            await update.message.reply_text(
                "👨‍🔧 USTA 24 ANDIJON\n\nUsta paneliga xush kelibsiz!",
                reply_markup=master_menu(),
            )
            return

        await set_role(user.id, "client")
        await update.message.reply_text(
            "🏠 USTA 24 ANDIJON\n\n"
            "Assalomu alaykum!\n"
            "Siz mijoz sifatida kirdingiz.\n\n"
            "🛠 Uyga usta chaqiring.\n"
            "⚡ Tez va qulay xizmat.",
            reply_markup=client_menu(),
        )

    except Exception as e:
        logger.exception("START ERROR")
        await update.message.reply_text("⚠️ Texnik xatolik yuz berdi.")


# ============================================================
# MASTER REGISTRATION
# ============================================================

async def master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)

    await update.message.reply_text(
        "👨‍🔧 USTA RO'YXATDAN O'TISH\n\nIsmingizni yozing:"
    )
    context.user_data["master_register"] = "name"
    return


async def master_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("master_register")
    if not state:
        return False

    user = update.effective_user

    if state == "name":
        context.user_data["master_name"] = update.message.text
        context.user_data["master_register"] = "phone"
        await update.message.reply_text(
            "📞 Telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard(),
        )
        return True

    if state == "phone":
        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = update.message.text

        await save_phone(user.id, phone)
        await set_role(user.id, "master")
        context.user_data.clear()

        await update.message.reply_text(
            "✅ Siz USTA sifatida ro'yxatdan o'tdingiz!\n\n"
            "Endi guruhdagi buyurtmalarni qabul qilishingiz mumkin.",
            reply_markup=master_menu(),
        )
        return True

    return False


# ============================================================
# ORDER START
# ============================================================

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = await get_user(user.id)

    if not db_user or not db_user["phone"]:
        context.user_data["waiting_phone"] = True
        await update.message.reply_text(
            "📱 Buyurtma berish uchun telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard(),
        )
        return

    context.user_data["order_phone"] = db_user["phone"]

    await update.message.reply_text(
        "🛠 Xizmat turini tanlang:",
        reply_markup=services_keyboard(),
    )

    context.user_data["order_step"] = "service"


# ============================================================
# ORDER TEXT FLOW
# ============================================================

async def handle_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if await master_register_handler(update, context):
        return

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------
    if context.user_data.get("waiting_phone"):
        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = text.strip()

        await save_phone(user.id, phone)
        context.user_data["order_phone"] = phone
        context.user_data["waiting_phone"] = False
        context.user_data["order_step"] = "service"

        await update.message.reply_text(
            "✅ Telefon saqlandi.\n\n🛠 Xizmat turini tanlang:",
            reply_markup=services_keyboard(),
        )
        return

    # --------------------------------------------------------
    # SERVICE
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "service":
        if text == "⬅️ Orqaga":
            context.user_data.clear()
            await update.message.reply_text("Bosh menyu:", reply_markup=client_menu())
            return

        if text in SERVICES:
            context.user_data["service"] = text
            context.user_data["order_step"] = "sub_service"
            await update.message.reply_text(
                f"📋 {text} xizmatidan birini tanlang:",
                reply_markup=sub_services_keyboard(text),
            )
        else:
            await update.message.reply_text(
                "❌ Iltimos, xizmatlar ro'yxatidan tanlang:",
                reply_markup=services_keyboard(),
            )
        return

    # --------------------------------------------------------
    # SUB SERVICE
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "sub_service":
        if text == "⬅️ Orqaga":
            context.user_data["order_step"] = "service"
            await update.message.reply_text(
                "🛠 Xizmat turini tanlang:",
                reply_markup=services_keyboard(),
            )
            return

        context.user_data["sub_service"] = text
        context.user_data["order_step"] = "description"

        await update.message.reply_text(
            "📝 Muammo haqida qisqacha yozing:\n\nMasalan: «Rozetka ishlamayapti»"
        )
        return

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "description":
        context.user_data["description"] = text
        context.user_data["order_step"] = "photo"

        await update.message.reply_text(
            "📸 Muammo rasmini yuboring.\n\nAgar rasm bo'lmasa, «⏭ O'tkazib yuborish» deb yozing."
        )
        return

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "photo":
        if text.lower() in ["⏭ o'tkazib yuborish", "otkazib yuborish", "skip"]:
            context.user_data["problem_photo"] = ""
            context.user_data["order_step"] = "address"
            await update.message.reply_text(
                "📍 Manzilingizni yozing:"
            )
            return

        await update.message.reply_text(
            "📸 Iltimos, rasm yuboring yoki «⏭ O'tkazib yuborish» deb yozing."
        )
        return

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "address":
        context.user_data["address"] = text
        context.user_data["order_step"] = "time"

        await update.message.reply_text(
            "🕐 Qachon usta kerak?",
            reply_markup=time_keyboard(),
        )
        return

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "time":
        if text == "⬅️ Orqaga":
            context.user_data["order_step"] = "address"
            await update.message.reply_text("📍 Manzilingizni yozing:")
            return

        context.user_data["order_time"] = text
        context.user_data["order_step"] = "confirm"

        service = context.user_data.get("service", "")
        sub_service = context.user_data.get("sub_service", "")
        description = context.user_data.get("description", "")
        address = context.user_data.get("address", "")

        await update.message.reply_text(
            f"📋 BUYURTMA\n\n"
            f"🛠 Xizmat: {service}\n"
            f"📋 Turi: {sub_service}\n"
            f"📝 Muammo: {description}\n"
            f"📍 Manzil: {address}\n"
            f"🕐 Vaqt: {text}\n\n"
            "Buyurtmani tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ TASDIQLASH", callback_data="order_confirm")],
                    [InlineKeyboardButton("❌ BEKOR QILISH", callback_data="order_cancel")],
                ]
            ),
        )
        return

    # --------------------------------------------------------
    # CHECK ORDER STATUS
    # --------------------------------------------------------
    if context.user_data.get("checking_order"):
        try:
            order_num = text.strip()
            if not order_num.startswith("#"):
                order_num = f"#{order_num}"

            order = await get_order_by_num(order_num)
            if not order:
                await update.message.reply_text("❌ Buyurtma topilmadi.")
                return

            await update.message.reply_text(
                f"🔍 BUYURTMA {order['order_num']}\n\n"
                f"🛠 Xizmat: {order['service']} – {order['sub_service']}\n"
                f"📍 Manzil: {order['address']}\n"
                f"🕐 Vaqt: {order['order_time']}\n"
                f"📌 Holat: {order['status']}\n"
                f"👨‍🔧 Usta: {order['master_name'] or 'Hali biriktirilmagan'}"
            )
            context.user_data["checking_order"] = False
            return
        except:
            await update.message.reply_text("❌ Noto'g'ri format. Masalan: 1245")
            return

    # --------------------------------------------------------
    # CANCEL ORDER
    # --------------------------------------------------------
    if context.user_data.get("cancel_order"):
        try:
            order_num = text.strip()
            if not order_num.startswith("#"):
                order_num = f"#{order_num}"

            order = await get_order_by_num(order_num)
            if not order:
                await update.message.reply_text("❌ Buyurtma topilmadi.")
                return

            if order["customer_id"] != user.id:
                await update.message.reply_text("❌ Bu sizning buyurtmangiz emas.")
                return

            if order["status"] not in ["new", "accepted"]:
                await update.message.reply_text("❌ Bu buyurtmani bekor qilib bo'lmaydi.")
                return

            await update_order_status(order["id"], "cancelled")
            await update.message.reply_text(
                f"❌ {order['order_num']} buyurtma bekor qilindi.",
                reply_markup=client_menu(),
            )
            context.user_data["cancel_order"] = False
            return
        except:
            await update.message.reply_text("❌ Noto'g'ri format. Masalan: 1245")
            return

    # --------------------------------------------------------
    # REVIEW - SELECT MASTER
    # --------------------------------------------------------
    if context.user_data.get("review_step") == "select_master":
        try:
            order_id = int(text)
            order = await get_order(order_id)

            if not order or order["customer_id"] != user.id:
                await update.message.reply_text("❌ Buyurtma topilmadi.")
                return

            if not order["master_id"]:
                await update.message.reply_text("❌ Bu buyurtmaga usta biriktirilmagan.")
                return

            context.user_data["review_order_id"] = order_id
            context.user_data["review_master_id"] = order["master_id"]
            context.user_data["review_step"] = "rating"

            await update.message.reply_text(
                "⭐ Ustaga baho bering:",
                reply_markup=rating_keyboard(),
            )
            return
        except:
            await update.message.reply_text("❌ Noto'g'ri format. Buyurtma raqamini yozing.")
            return

    # ========================================================
    # MASTER MENU
    # ========================================================
    db_user = await get_user(user.id)

    if db_user and db_user["role"] == "master":
        await master_text(update, context)
        return

    # ========================================================
    # ADMIN MENU
    # ========================================================
    if ADMIN_ID and user.id == ADMIN_ID:
        await admin_text(update, context)
        return

    # ========================================================
    # CLIENT MENU
    # ========================================================
    await client_text(update, context)


# ============================================================
# PHOTO HANDLER
# ============================================================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("order_step") == "photo":
        photo = update.message.photo[-1]
        context.user_data["problem_photo"] = photo.file_id
        context.user_data["order_step"] = "address"

        await update.message.reply_text(
            "✅ Rasm qabul qilindi.\n\n📍 Endi manzilingizni yozing:"
        )
        return

    if context.user_data.get("complete_order"):
        photo = update.message.photo[-1]
        order_id = context.user_data["complete_order"]

        await add_photo(order_id, photo.file_id, "result")

        await update.message.reply_text(
            "✅ Natija rasmi qabul qilindi!\n\n"
            "💰 Ish narxini yozing (so'mda):\nMasalan: 150000"
        )
        context.user_data["complete_step"] = "price"
        return


# ============================================================
# ORDER CALLBACKS
# ============================================================

async def order_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user

    try:
        db_user = await get_user(user.id)

        order_id, order_num = await create_order(
            customer_id=user.id,
            customer_name=user.full_name or "Mijoz",
            customer_phone=db_user["phone"] or context.user_data.get("order_phone", ""),
            service=context.user_data.get("service", ""),
            sub_service=context.user_data.get("sub_service", ""),
            description=context.user_data.get("description", ""),
            address=context.user_data.get("address", ""),
            order_time=context.user_data.get("order_time", ""),
        )

        photo_id = context.user_data.get("problem_photo")
        if photo_id:
            await add_photo(order_id, photo_id, "problem")

        await query.edit_message_text(
            f"✅ BUYURTMA QABUL QILINDI!\n\n"
            f"🆔 {order_num}\n"
            f"🛠 {context.user_data.get('service', '')}\n"
            f"📍 {context.user_data.get('address', '')}\n"
            f"🕐 {context.user_data.get('order_time', '')}\n\n"
            "👨‍🔧 Ustalar qidirilmoqda..."
        )

        if MASTERS_GROUP_ID:
            try:
                await send_order_to_group(context.bot, order_id)
            except Exception as e:
                logger.error(f"Group send error: {e}")

        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🆕 YANGI BUYURTMA!\n\n"
                    f"🆔 {order_num}\n"
                    f"👤 {user.full_name}\n"
                    f"🛠 {context.user_data.get('service', '')}\n"
                    f"📍 {context.user_data.get('address', '')}"
                )
            except Exception:
                pass

        context.user_data.clear()

    except Exception as e:
        logger.exception("ORDER CREATE ERROR")
        await query.message.reply_text("⚠️ Texnik xatolik yuz berdi.")


async def order_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    await query.edit_message_text("❌ Buyurtma bekor qilindi.")
    await query.message.reply_text("Bosh menyu:", reply_markup=client_menu())


# ============================================================
# SEND ORDER TO GROUP
# ============================================================

async def send_order_to_group(bot, order_id):
    order = await get_order(order_id)
    if not order:
        return

    text = (
        f"🆕 YANGI BUYURTMA!\n\n"
        f"🆔 {order['order_num']}\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['customer_phone']}\n"
        f"🛠 Xizmat: {order['service']} – {order['sub_service']}\n"
        f"📝 Muammo: {order['description']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"🕐 Vaqt: {order['order_time']}\n"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ QABUL QILISH", callback_data=f"accept:{order['id']}"),
                InlineKeyboardButton("❌ RAD ETISH", callback_data=f"reject:{order['id']}"),
            ],
            [
                InlineKeyboardButton("🔧 Ishni boshlash", callback_data=f"startwork:{order['id']}"),
            ],
            [
                InlineKeyboardButton("✅ Ishni yakunlash", callback_data=f"complete:{order['id']}"),
            ],
            [
                InlineKeyboardButton("📸 Rasmlarni ko'rish", callback_data=f"viewphotos:{order['id']}"),
            ],
        ]
    )

    await bot.send_message(
        MASTERS_GROUP_ID,
        text,
        reply_markup=keyboard,
    )


# ============================================================
# MASTER CALLBACK
# ============================================================

async def master_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await get_user(user.id)

    if not db_user or db_user["role"] != "master":
        await query.answer("❌ Siz usta sifatida ro'yxatdan o'tmagansiz.", show_alert=True)
        return

    data = query.data

    try:
        action, order_id_text = data.split(":", 1)
        order_id = int(order_id_text)
        order = await get_order(order_id)

        if not order:
            await query.answer("Buyurtma topilmadi.", show_alert=True)
            return

        if action == "accept":
            if order["status"] != "new":
                await query.answer("Bu buyurtmani boshqa usta olgan.", show_alert=True)
                return

            await assign_master(order_id, user.id, user.full_name, db_user["phone"] or "")

            await query.edit_message_text(
                f"✅ BUYURTMA QABUL QILINDI\n\n"
                f"🆔 {order['order_num']}\n"
                f"👨‍🔧 Usta: {user.full_name}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}"
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"✅ Buyurtmangiz qabul qilindi!\n\n"
                    f"🆔 {order['order_num']}\n"
                    f"👨‍🔧 Usta: {user.full_name}\n"
                    f"📞 {db_user['phone']}\n\n"
                    "Usta tez orada bog'lanadi.",
                )
            except Exception:
                pass

            return

        if action == "reject":
            await update_order_status(order_id, "rejected")

            await query.edit_message_text(
                f"❌ {order['order_num']} rad etildi.\n🔄 Boshqa usta ko'rib chiqishi mumkin."
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"❌ {order['order_num']} buyurtmangizni ushbu usta qabul qilmadi.\n\n🔄 Boshqa usta qidirilmoqda.",
                )
            except Exception:
                pass

            return

        if action == "startwork":
            if order["master_id"] != user.id:
                await query.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
                return

            await update_order_status(order_id, "started")

            await query.message.reply_text(
                f"🔧 {order['order_num']} ish boshlandi!\n👨‍🔧 Usta: {user.full_name}"
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"🔧 Ish boshlandi!\n\n🆔 {order['order_num']}\n👨‍🔧 Usta: {user.full_name}",
                )
            except Exception:
                pass

            return

        if action == "complete":
            if order["master_id"] != user.id:
                await query.answer("Bu buyurtma sizga tegishli emas.", show_alert=True)
                return

            await query.message.reply_text(
                f"📸 {order['order_num']} buyurtma uchun natija rasmini yuboring.\n\n"
                "📸 Rasm yuboring (majburiy!)"
            )

            context.user_data["complete_order"] = order_id
            return

        if action == "viewphotos":
            async with db_pool.acquire() as conn:
                photos = await conn.fetch(
                    "SELECT * FROM u24_order_photos WHERE order_id = $1",
                    order_id,
                )

            if not photos:
                await query.answer("Bu buyurtmada rasmlar yo'q.")
                return

            for photo in photos:
                await query.message.reply_photo(photo["file_id"])

            return

    except Exception as e:
        logger.exception("MASTER CALLBACK ERROR")
        await query.message.reply_text("⚠️ Texnik xatolik yuz berdi.")


# ============================================================
# REVIEW CALLBACK
# ============================================================

async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if data.startswith("rating_"):
        rating = int(data.split("_")[1])
        context.user_data["review_rating"] = rating
        context.user_data["review_step"] = "comment"

        await query.message.edit_text(
            f"⭐ Baho: {rating} yulduz\n\n📝 Sharhingizni yozing:"
        )
        return


# ============================================================
# CLIENT TEXT HANDLER
# ============================================================

async def client_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🛒 Buyurtma berish":
        await order_start(update, context)
        return

    if text == "📋 Mening buyurtmalarim":
        orders = await get_user_orders(user.id)

        if not orders:
            await update.message.reply_text("📋 Sizda hali buyurtmalar yo'q.")
            return

        out = "📋 MENING BUYURTMALARIM\n\n"
        for order in orders[:10]:
            out += (
                f"🆔 {order['order_num']}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}\n"
                f"📌 Holat: {order['status']}\n"
                f"📅 {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "🔍 Buyurtma holati":
        await update.message.reply_text(
            "🔍 Buyurtma raqamini yozing.\n\nMasalan: 1245"
        )
        context.user_data["checking_order"] = True
        return

    if text == "❌ Bekor qilish":
        await update.message.reply_text(
            "❌ Bekor qilmoqchi bo'lgan buyurtma raqamini yozing.\n\nMasalan: 1245"
        )
        context.user_data["cancel_order"] = True
        return

    if text == "🔁 Qayta buyurtma":
        await update.message.reply_text("🔁 Yangi buyurtma berishni boshlaymiz.")
        await order_start(update, context)
        return

    if text == "👨‍🔧 Mening ustalarim":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT master_id, master_name, master_phone
                FROM u24_orders
                WHERE customer_id = $1 AND master_id IS NOT NULL
                ORDER BY master_name
                """,
                user.id,
            )

        if not rows:
            await update.message.reply_text("👨‍🔧 Hali sizga usta biriktirilmagan.")
            return

        out = "👨‍🔧 MENING USTALARIM\n\n"
        for row in rows:
            out += f"👨‍🔧 {row['master_name']}\n📞 {row['master_phone']}\n\n"

        await update.message.reply_text(out)
        return

    if text == "⭐ Reytingim":
        rating = await get_master_rating(user.id)
        bonuses = await get_user_bonus(user.id)

        await update.message.reply_text(
            f"⭐ REYTINGINGIZ\n\n"
            f"⭐ O'rtacha: {float(rating['avg']):.2f}\n"
            f"📝 Sharhlar: {rating['total']}\n\n"
            f"🎁 Bonuslar: {bonuses:,} ball\n"
            f"💰 1 ball = 100 so'm\n"
            f"💵 Jami: {bonuses * 100:,} so'm"
        )
        return

    if text == "📝 Sharh qoldirish":
        orders = await get_user_orders(user.id, "completed")

        if not orders:
            await update.message.reply_text(
                "📝 Sizda yakunlangan buyurtmalar yo'q.\n"
                "Avval buyurtma bering va ish yakunlansin."
            )
            return

        out = "📝 SHARH QOLDIRISH\n\n"
        out += "Qaysi buyurtma uchun sharh qoldirmoqchisiz?\n"
        out += "Buyurtma raqamini yozing:\n\n"

        for order in orders[:5]:
            out += f"🆔 {order['order_num']} – {order['service']}\n"

        await update.message.reply_text(out)
        context.user_data["review_step"] = "select_master"
        return

    if text == "📌 Eslatmalarim":
        await update.message.reply_text("📌 Hozircha eslatmalar mavjud emas.")
        return

    if text == "🗺 Yaqin atrofdagi ustalar":
        await update.message.reply_text(
            "🗺 Yaqin atrofdagi ustalarni aniqlash uchun geolokatsiya funksiyasi ishlatiladi.\n\n"
            "📍 Joylashuvingizni yuboring:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📍 Geolokatsiya yuborish", request_location=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return

    if text == "📅 Yozilma":
        await update.message.reply_text(
            "📅 Bron qilish: buyurtma berishda kerakli vaqtni ko'rsating."
        )
        return

    if text == "🎁 Loyallik va bonuslar":
        bonuses = await get_user_bonus(user.id)

        if bonuses < 500:
            level = "🥉 Mis"
        elif bonuses < 1000:
            level = "🥈 Kumush"
        elif bonuses < 3000:
            level = "🥇 Oltin"
        elif bonuses < 5000:
            level = "💎 Platina"
        else:
            level = "👑 Olmos"

        await update.message.reply_text(
            f"🎁 LOYALLIK VA BONUSLAR\n\n"
            f"💰 Bonus ball: {bonuses:,}\n"
            f"💵 1 ball = 100 so'm\n"
            f"💵 Jami: {bonuses * 100:,} so'm\n\n"
            f"🏆 Darajangiz: {level}\n\n"
            f"📋 Darajalar:\n"
            f"├── 🥉 Mis: 0-500 ball\n"
            f"├── 🥈 Kumush: 501-1000 ball\n"
            f"├── 🥇 Oltin: 1001-3000 ball\n"
            f"├── 💎 Platina: 3001-5000 ball\n"
            f"└── 👑 Olmos: 5000+ ball"
        )
        return

    if text == "🤖 AI yordamchi":
        await update.message.reply_text(
            "🤖 AI YORDAMCHI\n\n"
            "1️⃣ 💬 Savol-javob\n"
            "2️⃣ 📝 Buyurtma tavsiyasi\n"
            "3️⃣ 💰 Narx hisoblash\n"
            "4️⃣ 📅 Vaqt rejalash\n"
            "5️⃣ 📸 Rasm tahlili\n\n"
            "Savolingizni yozing, AI yordamchi javob beradi."
        )
        return

    if text == "⚙️ Sozlamalar":
        db_user = await get_user(user.id)
        await update.message.reply_text(
            f"⚙️ SOZLAMALAR\n\n"
            f"👤 Ism: {db_user['full_name']}\n"
            f"📞 Telefon: {db_user['phone']}\n"
            f"🎭 Rol: {db_user['role']}\n"
            f"🌐 Til: 🇺🇿 O'zbek\n\n"
            f"🔔 Bildirishnomalar: ✅ Yoqilgan\n\n"
            f"📞 Dispetcher: {DISPATCHER_PHONE}"
        )
        return

    if text == "📊 Mening statistikam":
        orders = await get_user_orders(user.id)
        total = len(orders)
        completed = len([o for o in orders if o["status"] == "completed"])
        cancelled = len([o for o in orders if o["status"] == "cancelled"])
        bonuses = await get_user_bonus(user.id)

        await update.message.reply_text(
            f"📊 MENING STATISTIKAM\n\n"
            f"📋 Jami buyurtmalar: {total}\n"
            f"✅ Tugallangan: {completed}\n"
            f"❌ Bekor qilingan: {cancelled}\n"
            f"📌 Jarayonda: {total - completed - cancelled}\n\n"
            f"🎁 Bonuslar: {bonuses:,} ball"
        )
        return

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 CHEGIRMALAR VA AKSIYALAR\n\n"
            "Hozircha faol chegirmalar yo'q.\n\n"
            "🔔 Yangiliklar uchun bildirishnomalarni yoqing!"
        )
        return

    if text == "📞 Tez yordam":
        await update.message.reply_text(
            f"📞 TEZ YORDAM\n\n"
            f"1️⃣ 📞 Dispetcher: {DISPATCHER_PHONE}\n"
            f"2️⃣ 💬 Bot orqali yozing: @usta24_bot\n\n"
            f"❓ Ko'p so'raladigan savollar:\n\n"
            f"Q: Qanday buyurtma berish mumkin?\n"
            f"A: '🛒 Buyurtma berish' tugmasini bosing!\n\n"
            f"Q: Narx qanday hisoblanadi?\n"
            f"A: Xizmat turiga qarab 40,000-80,000 so'm/soat\n\n"
            f"Q: To'lov qanday amalga oshiriladi?\n"
            f"A: Faqat naqd pul! Ishdan keyin to'lov!\n\n"
            f"Q: 24/7 rejim qanday ishlaydi?\n"
            f"A: Shosilingch holatda 10-15 daqiqada yetib boramiz!"
        )
        return

    if text == "🔔 Bildirishnomalar":
        await update.message.reply_text(
            "🔔 BILDIRISHNOMALAR\n\n"
            "✅ Yangi buyurtma\n"
            "✅ Buyurtma holati o'zgarishi\n"
            "✅ Usta xabarlari\n"
            "❌ Reklama xabarlari\n\n"
            "🔊 Ovoz: ✅ Yoqilgan"
        )
        return

    if text == "📁 Mening hujjatlarim":
        await update.message.reply_text(
            "📁 MENING HUJJATLARIM\n\n"
            "1️⃣ 📄 Cheklar (0 ta)\n"
            "2️⃣ 📄 Shartnomalar (0 ta)\n"
            "3️⃣ 📄 Hisobotlar (0 ta)\n\n"
            "📤 Hujjatlar tez orada qo'shiladi."
        )
        return

    if text == "🕊 Do'stga tavsiya":
        await update.message.reply_text(
            "🕊 DO'STGA TAVSIYA QILISH\n\n"
            "1️⃣ 📤 Telegram orqali ulashish\n"
            "2️⃣ 🔗 Havola: https://t.me/usta24_bot\n"
            "3️⃣ 📱 QR kod\n\n"
            "🎁 Har bir do'stingiz uchun 50,000 so'm bonus!"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7 – KUTISH YO'Q!\n"
            f"📍 Andijon shahar\n\n"
            f"📋 Vazifalar:\n"
            f"├── 📞 Mijoz va ustalarni bog'lash\n"
            f"├── 🚨 24/7 shosilingch holatlarni boshqarish\n"
            f"├── 📋 Zakazlarni nazorat qilish\n"
            f"└── 👨‍🔧 Yangi ustalarni qabul qilish"
        )
        return

    if text == "🚨 24/7 Shoshilinch":
        await update.message.reply_text(
            "🚨 24/7 SHOSHILINCH REJIM\n\n"
            "⚡ DOLZARB HOLATLAR:\n"
            "├── 💧 Suv tўхtab qoldi\n"
            "├── ⚡ Elektr ўчиб қолди\n"
            "├── 🔥 Газ оқаётган\n"
            "├── 🚪 Эшик синиб қолди\n"
            "└── 🚰 Қувур ёрилган\n\n"
            "🕐 24/7 USTA KERAK:\n"
            "├── 🔴 HOZIR (10-15 daqiqa) – 20% ustama\n"
            "├── 🟡 30 daqiqada – 10% ustama\n"
            "└── 🟢 1 soatda – oddiy narx\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "💵 TO'LOV: Faqat naqd! Ishdan keyin!\n"
            "📸 Natija rasmi majburiy!"
        )
        return

    await update.message.reply_text(
        "❓ Tushunarsiz buyruq.\n"
        "Iltimos, menyudan tanlang:",
        reply_markup=client_menu(),
    )


# ============================================================
# MASTER TEXT HANDLER
# ============================================================

async def master_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "📋 Yangi buyurtmalar":
        if not MASTERS_GROUP_ID:
            await update.message.reply_text("⚠️ MASTERS_GROUP_ID sozlanmagan.")
            return

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE status = 'new'
                ORDER BY id DESC
                LIMIT 10
                """
            )

        if not rows:
            await update.message.reply_text("📋 Hozircha yangi buyurtmalar yo'q.")
            return

        out = "📋 YANGI BUYURTMALAR\n\n"
        for row in rows:
            out += (
                f"🆔 {row['order_num']}\n"
                f"🛠 {row['service']} – {row['sub_service']}\n"
                f"📍 {row['address']}\n"
                f"🕐 {row['order_time']}\n"
                f"📌 {row['status']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "✅ Mening faol":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE master_id = $1 AND status IN ('accepted', 'started')
                ORDER BY id DESC
                """,
                user.id,
            )

        if not rows:
            await update.message.reply_text("✅ Faol buyurtmalar yo'q.")
            return

        out = "✅ FAOL BUYURTMALAR\n\n"
        for row in rows:
            out += (
                f"🆔 {row['order_num']}\n"
                f"🛠 {row['service']}\n"
                f"📍 {row['address']}\n"
                f"📌 {row['status']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "⏳ Tarix":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE master_id = $1 AND status = 'completed'
                ORDER BY id DESC
                LIMIT 30
                """,
                user.id,
            )

        if not rows:
            await update.message.reply_text("⏳ Tugallangan ishlar yo'q.")
            return

        out = "⏳ ISH TARIXI\n\n"
        for row in rows:
            out += (
                f"🆔 {row['order_num']}\n"
                f"🛠 {row['service']}\n"
                f"💰 {row['price']} so'm\n"
                f"📅 {row['completed_at'].strftime('%d.%m.%Y %H:%M') if row['completed_at'] else ''}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "💰 Ish haqi":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(price), 0) AS money
                FROM u24_orders
                WHERE master_id = $1 AND status = 'completed'
                """,
                user.id,
            )

        await update.message.reply_text(
            f"💰 ISH HAQI\n\n"
            f"📋 Ishlar: {row['total']}\n"
            f"💵 Jami: {row['money']:,} so'm"
        )
        return

    if text == "⭐ Reytingim":
        rating = await get_master_rating(user.id)

        await update.message.reply_text(
            f"⭐ USTA REYTINGI\n\n"
            f"⭐ {float(rating['avg']):.2f}\n"
            f"📝 {rating['total']} ta baho\n\n"
            f"📊 O'z o'rningizni bilish uchun yaxshi ishlang!"
        )
        return

    if text == "📊 Ish statistikasi":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status='completed') AS completed,
                    COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
                FROM u24_orders
                WHERE master_id = $1
                """,
                user.id,
            )

        await update.message.reply_text(
            f"📊 ISH STATISTIKASI\n\n"
            f"📋 Jami: {row['total']}\n"
            f"✅ Tugallangan: {row['completed']}\n"
            f"❌ Bekor qilingan: {row['cancelled']}\n"
            f"📌 Jarayonda: {row['total'] - row['completed'] - row['cancelled']}"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7"
        )
        return

    if text == "🚨 24/7 Shoshilinch":
        await update.message.reply_text(
            f"🚨 24/7 SHOSHILINCH\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "🔴 HOZIR: +20%\n"
            "🟡 30 daqiqa: +10%\n"
            "🟢 1 soat: oddiy narx\n\n"
            "💰 To'lov: Faqat naqd! Ishdan keyin!"
        )
        return

    if text == "📅 Kunlik jadval":
        await update.message.reply_text(
            "📅 KUNLIK JADVAL\n\n"
            "Bugun 12.01.2026\n\n"
            "08:00 – 09:00 ⬜ Bo'sh\n"
            "09:00 – 10:00 ⬜ Bo'sh\n"
            "10:00 – 11:00 🔴 Band\n"
            "11:00 – 12:00 🔴 Band\n"
            "12:00 – 13:00 ⬜ Bo'sh\n"
            "13:00 – 14:00 🟡 Tushlik\n"
            "14:00 – 15:00 ⬜ Bo'sh\n"
            "15:00 – 16:00 ⬜ Bo'sh"
        )
        return

    if text == "🔔 Mijozlar bilan bog'lanish":
        await update.message.reply_text(
            "🔔 MIJOZLAR BILAN BOG'LANISH\n\n"
            "1️⃣ 📞 Qo'ng'iroq qilish\n"
            "2️⃣ 💬 Xabar yozish\n"
            "3️⃣ 📨 Shablon xabarlar\n\n"
            "📋 Faol mijozlar ro'yxati..."
        )
        return

    if text == "📸 Galereya":
        await update.message.reply_text(
            "📸 GALEREYA\n\n"
            "Sizning ish natijasi rasmlaringiz:\n"
            "📸 18 ta rasm\n\n"
            "[📤 Yuklab olish]  [🗑 O'chirish]"
        )
        return

    if text == "🛠 Xizmatlarim":
        await update.message.reply_text(
            "🛠 XIZMATLARIM\n\n"
            "1️⃣ ⚡ Elektr – 50,000 so'm/soat\n"
            "2️⃣ ⚡ Elektr – 40,000 so'm/soat\n"
            "3️⃣ 🛠 Santexnika – 80,000 so'm/soat\n\n"
            "[➕ Yangi xizmat]  [✏️ Tahrirlash]"
        )
        return

    if text == "🏷 Mening narxlarim":
        await update.message.reply_text(
            "🏷 MENING NARXLARIM\n\n"
            "⚡ Elektr: 50,000 so'm/soat\n"
            "🛠 Santexnika: 80,000 so'm/soat\n"
            "🔧 Mexanik: 60,000 so'm/soat\n\n"
            "🚗 Yetib borish: 10,000 so'm\n"
            "📦 Material: 5,000-30,000 so'm"
        )
        return

    if text == "📍 Ish hududim":
        await update.message.reply_text(
            "📍 ISH HUDUDIM\n\n"
            "📍 Asosiy joy: Andijon shahar\n"
            "📏 Masofa: 10 km\n\n"
            "🏙 Hududlar:\n"
            "├── Andijon shahar\n"
            "├── Andijon tumani\n"
            "├── Asaka\n"
            "└── Xo'jaobod"
        )
        return

    if text == "📅 Dam olish kunlari":
        await update.message.reply_text(
            "📅 DAM OLISH KUNLARI\n\n"
            "Doimiy dam olish:\n"
            "├── Yakshanba\n"
            "└── Dushanba\n\n"
            "Maxsus dam olish:\n"
            "├── 15.01.2026\n"
            "└── 20.01.2026"
        )
        return

    if text == "🔔 Bildirishnoma":
        await update.message.reply_text(
            "🔔 BILDIRISHNOMA SOZLAMALARI\n\n"
            "✅ Yangi buyurtma\n"
            "✅ Buyurtma holati o'zgarishi\n"
            "✅ Mijoz xabarlari\n"
            "❌ Reklama xabarlari\n"
            "✅ Reyting va sharhlar\n\n"
            "🔊 Ovoz: ✅ Yoqilgan"
        )
        return

    if text == "📝 Reytingni oshirish":
        await update.message.reply_text(
            "📝 REYTINGNI OSHIRISH\n\n"
            "1️⃣ 📸 Ish natijasi rasmini yuboring!\n"
            "2️⃣ ⏰ O'z vaqtida boring!\n"
            "3️⃣ 💬 Mijoz bilan samimiy muloqot qiling!\n"
            "4️⃣ 🛠 Sifatli ish bajaring!\n"
            "5️⃣ 📝 Mijozdan sharh so'rang!\n\n"
            f"⭐ Hozirgi: 4.8\n"
            f"🎯 Maqsad: 5.0"
        )
        return

    if text == "🎁 Usta bonuslari":
        await update.message.reply_text(
            "🎁 USTA BONUSLARI\n\n"
            "💰 Bonus ball: 3,200\n"
            "💵 1 ball = 100 so'm\n"
            "💵 Jami: 320,000 so'm\n\n"
            "🏆 Daraja: OLTIN\n\n"
            "[💳 Yechib olish]  [📋 Qoidalar]"
        )
        return

    if text == "🤖 AI yordamchi":
        await update.message.reply_text(
            "🤖 AI YORDAMCHI (USTALAR)\n\n"
            "1️⃣ 💬 Savol-javob\n"
            "2️⃣ 📝 Buyurtma tavsiyasi\n"
            "3️⃣ 💰 Narx hisoblash\n"
            "4️⃣ 📅 Vaqt rejalash\n"
            "5️⃣ 📸 Rasm tahlili\n"
            "6️⃣ ⭐ Reytingni oshirish maslahati"
        )
        return

    if text == "📞 Texnik yordam":
        await update.message.reply_text(
            f"📞 TEXNIK YORDAM\n\n"
            f"1️⃣ 📞 Dispetcher: {DISPATCHER_PHONE}\n"
            f"2️⃣ 💬 Bot orqali: @usta24_bot\n\n"
            f"❓ FAQ:\n"
            f"Q: Qanday buyurtma qabul qilish mumkin?\n"
            f"A: Guruhdagi buyurtmalarni ko'rib, QABUL QILISH tugmasini bosing!"
        )
        return

    if text == "📢 E'lonlar":
        await update.message.reply_text(
            "📢 E'LONLAR\n\n"
            "1️⃣ 🔥 Yangi yil aksiyasi – 20%\n"
            "2️⃣ 🎁 Do'stingizni taklif qiling – 50,000 so'm\n"
            "3️⃣ 📱 Telegram orqali – 10% chegirma\n"
            "4️⃣ 🏆 TOP 10 ustalar e'loni\n"
            "5️⃣ 🛠 'Aqlli uy' xizmati qo'shildi"
        )
        return

    if text == "🏆 Ustalar reytingi":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    u24_users.full_name,
                    COALESCE(AVG(u24_ratings.rating), 0) as avg_rating,
                    COUNT(u24_ratings.id) as total_ratings
                FROM u24_users
                LEFT JOIN u24_ratings ON u24_users.telegram_id = u24_ratings.master_id
                WHERE u24_users.role = 'master'
                GROUP BY u24_users.telegram_id, u24_users.full_name
                ORDER BY avg_rating DESC
                LIMIT 10
                """
            )

        if not rows:
            await update.message.reply_text("🏆 Hali reytinglar mavjud emas.")
            return

        out = "🏆 TOP 10 USTALAR\n\n"
        medals = ["👑", "🥇", "🥈", "🥉"]
        for i, row in enumerate(rows, 1):
            medal = medals[i-1] if i <= 4 else f"{i}."
            out += f"{medal} {row['full_name']} – ⭐{float(row['avg_rating']):.2f} ({row['total_ratings']})\n"

        await update.message.reply_text(out)
        return

    await update.message.reply_text(
        "👨‍🔧 Usta menyusi:",
        reply_markup=master_menu(),
    )


# ============================================================
# ADMIN TEXT HANDLER
# ============================================================

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "👥 Foydalanuvchilar":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE role='client') AS clients,
                    COUNT(*) FILTER (WHERE role='master') AS masters,
                    COUNT(*) FILTER (WHERE role='admin') AS admins
                FROM u24_users
                """
            )

        await update.message.reply_text(
            f"👥 FOYDALANUVCHILAR\n\n"
            f"👤 Jami: {row['total']}\n"
            f"🛒 Mijozlar: {row['clients']}\n"
            f"👨‍🔧 Ustalar: {row['masters']}\n"
            f"👑 Adminlar: {row['admins']}"
        )
        return

    if text == "🛠 Buyurtmalar":
        stats = await get_order_stats()

        await update.message.reply_text(
            f"🛠 BUYURTMALAR\n\n"
            f"📋 Jami: {stats['total']}\n"
            f"🆕 Yangi: {stats['new']}\n"
            f"✅ Qabul qilingan: {stats['accepted']}\n"
            f"🔧 Jarayonda: {stats['started']}\n"
            f"🏁 Tugagan: {stats['completed']}\n"
            f"❌ Bekor: {stats['cancelled']}\n\n"
            f"💰 Jami: {stats['total_price']:,} so'm"
        )
        return

    if text == "👨‍🔧 Ustalar":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT telegram_id, full_name, phone
                FROM u24_users
                WHERE role = 'master'
                ORDER BY full_name
                """
            )

        if not rows:
            await update.message.reply_text("👨‍🔧 Hali ustalar yo'q.")
            return

        out = "👨‍🔧 USTALAR\n\n"
        for row in rows:
            out += f"👨‍🔧 {row['full_name']}\n🆔 {row['telegram_id']}\n📞 {row['phone']}\n\n"

        await update.message.reply_text(out)
        return

    if text == "⭐ Reytinglar":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    master_id,
                    COUNT(*) AS total,
                    AVG(rating) AS avg
                FROM u24_ratings
                GROUP BY master_id
                ORDER BY avg DESC
                LIMIT 10
                """
            )

        if not rows:
            await update.message.reply_text("⭐ Hali reytinglar yo'q.")
            return

        out = "⭐ TOP USTALAR\n\n"
        for i, row in enumerate(rows, 1):
            out += f"{i}. 👨‍🔧 ID:{row['master_id']} ⭐{float(row['avg']):.2f} ({row['total']})\n"

        await update.message.reply_text(out)
        return

    if text == "🎁 Bonuslar":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM u24_bonuses")
            count = await conn.fetchval("SELECT COUNT(*) FROM u24_bonuses")

        await update.message.reply_text(
            f"🎁 BONUSLAR\n\n"
            f"💰 Jami bonus: {total:,} ball\n"
            f"📋 Transaktsiyalar: {count} ta"
        )
        return

    if text == "💰 To'lovlar":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COALESCE(SUM(price), 0) FROM u24_orders WHERE status='completed'"
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM u24_orders WHERE status='completed'"
            )

        await update.message.reply_text(
            f"💰 TO'LOVLAR\n\n"
            f"💵 Jami: {total:,} so'm\n"
            f"📋 Tugallangan: {count} ta buyurtma\n\n"
            f"📊 O'rtacha: {total // count if count else 0:,} so'm"
        )
        return

    if text == "📊 Statistika":
        async with db_pool.acquire() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM u24_users")
            orders = await conn.fetchval("SELECT COUNT(*) FROM u24_orders")
            completed = await conn.fetchval("SELECT COUNT(*) FROM u24_orders WHERE status='completed'")
            money = await conn.fetchval("SELECT COALESCE(SUM(price), 0) FROM u24_orders WHERE status='completed'")
            masters = await conn.fetchval("SELECT COUNT(*) FROM u24_users WHERE role='master'")
            ratings = await conn.fetchval("SELECT COUNT(*) FROM u24_ratings")

        await update.message.reply_text(
            f"📊 USTA 24 STATISTIKA\n\n"
            f"👥 Foydalanuvchilar: {users}\n"
            f"├── 👨‍🔧 Ustalar: {masters}\n"
            f"└── 👤 Mijozlar: {users - masters}\n\n"
            f"🛠 Buyurtmalar: {orders}\n"
            f"├── ✅ Tugallangan: {completed}\n"
            f"└── ⭐ Reytinglar: {ratings}\n\n"
            f"💰 Tushum: {money:,} so'm"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7\n"
            f"📍 Andijon shahar\n\n"
            f"📋 Vazifalar:\n"
            f"├── 📞 Mijoz va ustalarni bog'lash\n"
            f"├── 🚨 24/7 shosilingch holatlarni boshqarish\n"
            f"├── 📋 Zakazlarni nazorat qilish\n"
            f"└── 👨‍🔧 Yangi ustalarni qabul qilish"
        )
        return

    if text == "🚨 24/7 Rejim":
        await update.message.reply_text(
            "🚨 24/7 SHOSHILINCH REJIM\n\n"
            "📋 STATISTIKA:\n"
            "├── Jami so'rovlar: 5 ta\n"
            "├── ✅ Bajarilgan: 4 ta\n"
            "└── ⏳ Kutilayotgan: 1 ta\n\n"
            "🔴 HOZIR +20%\n"
            "🟡 30 daqiqa +10%\n"
            "🟢 1 soat oddiy\n\n"
            f"📞 {DISPATCHER_PHONE}"
        )
        return

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 CHEGIRMALAR\n\n"
            "1️⃣ 🎉 Yangi yil – 20% (15.01.2026 gacha)\n"
            "2️⃣ 🎁 Do'stni taklif qilish – 50,000 so'm\n"
            "3️⃣ 📱 Telegram orqali – 10%\n\n"
            "[➕ Yangi chegirma]  [✏️ Tahrirlash]"
        )
        return

    if text == "🛠 Xizmat turlari":
        await update.message.reply_text(
            "🛠 XIZMAT TURLARI\n\n"
            "1️⃣ 🔧 Santexnika – актив\n"
            "2️⃣ ⚡ Elektrika – актив\n"
            "3️⃣ 🪑 Mebel yig'ish – актив\n"
            "4️⃣ 🛠 Mebel ta'mirlash – актив\n"
            "5️⃣ 🚚 Ko'chirish – актив\n\n"
            "[➕ Yangi xizmat]  [✏️ Tahrirlash]"
        )
        return

    if text == "📢 E'lonlar":
        await update.message.reply_text(
            "📢 E'LONLAR\n\n"
            "1️⃣ 🔥 Yangi yil aksiyasi – актив\n"
            "2️⃣ 🎁 Do'stni taklif qiling – актив\n"
            "3️⃣ 📱 Telegram orqali – актив\n\n"
            "[➕ Yangi e'lon]  [📨 Yuborish]"
        )
        return

    if text == "⚙️ Sozlamalar":
        await update.message.reply_text(
            "⚙️ SOZLAMALAR\n\n"
            "🔔 Bildirishnoma: ✅\n"
            "🤖 AI yordamchi: ✅\n"
            "💰 Narx tizimi: ✅\n"
            "🌐 Til: 🇺🇿 O'zbek\n"
            "📍 Hudud: Andijon\n"
            "🔐 Xavfsizlik: ✅"
        )
        return

    if text == "📸 Galereya":
        await update.message.reply_text(
            "📸 GALEREYA\n\n"
            "📸 Barcha rasmlar: 48 ta\n"
            "├── 📸 Muammo rasmlari: 25 ta\n"
            "├── 📸 Natija rasmlari: 20 ta\n"
            "└── 📹 Videolar: 3 ta\n\n"
            "[🖼 Ko'rish]  [🗑 Boshqarish]"
        )
        return

    if text == "📱 Botni boshqarish":
        await update.message.reply_text(
            "📱 BOTNI BOSHQARISH\n\n"
            "📊 Bot statistikasi:\n"
            "├── Foydalanuvchilar: 45 ta\n"
            "├── Buyurtmalar: 120 ta\n"
            "└── Xatoliklar: 0 ta\n\n"
            "[🔄 Qayta ishga tushirish]  [📋 Xatoliklar]"
        )
        return

    if text == "📞 Qo'llab-quvvatlash":
        await update.message.reply_text(
            "📞 QO'LLAB-QUVVATLASH\n\n"
            "📨 Mijoz xabarlari: 3 ta\n"
            "📨 Usta xabarlari: 2 ta\n"
            "📋 Shikoyatlar: 0 ta\n\n"
            "[💬 Javob berish]  [📋 Barchasi]"
        )
        return

    await update.message.reply_text(
        "👑 Admin panel:",
        reply_markup=admin_menu(),
    )


# ============================================================
# LOCATION HANDLER
# ============================================================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    await update.message.reply_text(
        f"📍 Joylashuvingiz qabul qilindi!\n\n"
        f"🌐 Kenglik: {location.latitude}\n"
        f"🌐 Uzunlik: {location.longitude}\n\n"
        f"🗺 Sizga yaqin ustalar qidirilmoqda..."
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.exception(
        "Unhandled exception",
        exc_info=context.error,
    )

    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Texnik xatolik yuz berdi.\nIltimos, qayta urinib ko'ring."
            )
    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

async def post_init(application):
    await init_db()
    logger.info("✅ USTA 24 ANDIJON BOT IS READY")


async def post_shutdown(application):
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("🐘 PostgreSQL pool yopildi.")


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ========================================================
    # COMMANDS
    # ========================================================

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("master", master_command))

    # ========================================================
    # CALLBACKS
    # ========================================================

    application.add_handler(CallbackQueryHandler(order_confirm_callback, pattern=r"^order_confirm$"))
    application.add_handler(CallbackQueryHandler(order_cancel_callback, pattern=r"^order_cancel$"))
    application.add_handler(CallbackQueryHandler(master_callback, pattern=r"^(accept|reject|startwork|complete|viewphotos):\d+$"))
    application.add_handler(CallbackQueryHandler(review_callback, pattern=r"^rating_\d+$"))

    # ========================================================
    # PHOTOS
    # ========================================================

    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # ========================================================
    # LOCATION
    # ========================================================

    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    # ========================================================
    # CONTACTS + TEXT
    # ========================================================

    application.add_handler(MessageHandler(filters.CONTACT, handle_order_text))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_order_text,
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(error_handler)

    # ========================================================
    # START
    # ========================================================

    logger.info("🚀 Bot polling started...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
