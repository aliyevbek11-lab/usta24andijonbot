#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA 24 ANDIJON
🏗️ ONE BOT = CLIENT + MASTER + ADMIN + MASTERS GROUP
🐘 PostgreSQL with asyncpg
📦 python-telegram-bot 22.3
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
    WAITING_CONFIRM_ORDER,
) = range(12)

# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "🔧 Santexnika",
    "⚡ Elektr",
    "🪑 Mebel yig'ish",
    "🛠 Mebel ta'mirlash",
    "🚚 Yuk tashish",
    "🚪 Eshik / qulf",
    "🎨 Ta'mirlash / bo'yoq",
    "❄️ Konditsioner",
    "🔥 Gaz xizmati",
    "🧰 Boshqa xizmat",
]

SERVICE_SUB = {
    "🔧 Santexnika": ["🚽 Hojatxona", "🚿 Lavabo", "🔧 Quvur", "🧹 Kanalizatsiya", "📋 Boshqa"],
    "⚡ Elektr": ["💡 Chiroq", "🔌 Rozetka", "🔧 Sim", "⚡ Avtomat", "📋 Boshqa"],
    "🪑 Mebel yig'ish": ["🪑 Stul", "🛋 Divan", "🪑 Stol", "📋 Boshqa"],
    "🛠 Mebel ta'mirlash": ["🚪 Eshik", "🪟 Deraza", "🪑 Mebel", "📋 Boshqa"],
    "🚚 Yuk tashish": ["📦 Kichik (50kg)", "📦 O'rta (200kg)", "📦 Katta (500kg)", "📋 Boshqa"],
    "🚪 Eshik / qulf": ["🚪 Eshik", "🔐 Qulf", "📋 Boshqa"],
    "🎨 Ta'mirlash / bo'yoq": ["🎨 Devor", "🪟 Deraza", "🚪 Eshik", "📋 Boshqa"],
    "❄️ Konditsioner": ["❄️ O'rnatish", "🧹 Tozalash", "🔧 Ta'mirlash", "📋 Boshqa"],
    "🔥 Gaz xizmati": ["🔥 O'rnatish", "🔧 Ta'mirlash", "📋 Boshqa"],
    "🧰 Boshqa xizmat": ["📋 Boshqa"],
}

# ============================================================
# DATABASE FUNCTIONS
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
        # Users
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

        # Orders
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

        # Photos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_order_photos (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                photo_type TEXT NOT NULL DEFAULT 'problem',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Ratings
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

        # Services
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

        # Bonuses
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

        # Reminders
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

        # Urgent requests
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


def address_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📍 Geolokatsiya yuborish", "✏️ Kўlда ёзиш"],
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


def confirm_keyboard():
    """Тасдиқлаш ва рад қилиш кнопкалари"""
    return ReplyKeyboardMarkup(
        [
            ["✅ Тасдиқлаш", "❌ Рад қилиш"],
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
    context.user_data["order_step"] = "service"

    await update.message.reply_text(
        "🛠 Xizmat turini tanlang:",
        reply_markup=services_keyboard(),
    )


# ============================================================
# ORDER TEXT FLOW
# ============================================================

async def handle_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if await master_register_handler(update, context):
        return

    # =========================================================
    # CONFIRM / REJECT (ТАСДИҚЛАШ / РАД ҚИЛИШ)
    # =========================================================
    if context.user_data.get("order_step") == "confirm":
        if text == "✅ Тасдиқлаш":
            await order_confirm_action(update, context)
            return
        elif text == "❌ Рад қилиш":
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Буюртма бекор қилинди.",
                reply_markup=client_menu(),
            )
            return
        else:
            await update.message.reply_text(
                "❌ Илтимос, ✅ Тасдиқлаш ёки ❌ Рад қилиш тугмасини босинг.",
                reply_markup=confirm_keyboard(),
            )
            return

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------
    if context.user_data.get("waiting_phone"):
        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = text.strip()

        if not phone or len(phone) < 9:
            await update.message.reply_text(
                "❌ Телефон рақам нотоғри. Қайта уриниб кўринг:",
                reply_markup=phone_keyboard(),
            )
            return

        await save_phone(user.id, phone)
        context.user_data["order_phone"] = phone
        context.user_data["waiting_phone"] = False
        context.user_data["order_step"] = "service"

        await update.message.reply_text(
            "✅ Телефон сақланди.\n\n🛠 Хизмат турини танланг:",
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
                f"📋 {text} хизматидан бирини танланг:",
                reply_markup=sub_services_keyboard(text),
            )
        else:
            await update.message.reply_text(
                "❌ Илтимос, хизматлар рўйхатидан танланг:",
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
                "🛠 Хизмат турини танланг:",
                reply_markup=services_keyboard(),
            )
            return

        context.user_data["sub_service"] = text
        context.user_data["order_step"] = "description"

        await update.message.reply_text(
            "📝 Муаммо ҳақида қисқача ёзинг:\n\nМасалан: «Розетка ишламаяпти»"
        )
        return

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "description":
        if len(text) < 3:
            await update.message.reply_text("❌ Илтимос, камида 3 ҳарфдан иборат тавсиф ёзинг:")
            return

        context.user_data["description"] = text
        context.user_data["order_step"] = "photo"

        await update.message.reply_text(
            "📸 Муаммо расмини юборинг.\n\n"
            "Агар расм бўлмаса, «⏭ O'tkazib yuborish» деб ёзинг."
        )
        return

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "photo":
        if text.lower() in ["⏭ o'tkazib yuborish", "otkazib yuborish", "skip"]:
            context.user_data["problem_photo"] = ""
            context.user_data["order_step"] = "address"
            context.user_data["address_type"] = "text"
            await update.message.reply_text(
                "📍 Манзилни қандай юбормоқчисиз?",
                reply_markup=address_keyboard(),
            )
            return

        await update.message.reply_text(
            "📸 Илтимос, расм юборинг ёки «⏭ O'tkazib yuborish» деб ёзинг."
        )
        return

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "address":
        if text == "📍 Geolokatsiya yuborish":
            await update.message.reply_text(
                "📍 Геолокациянгизни юборинг!\n\n"
                "📎 Иловадаги 📍 тугмасини босинг."
            )
            context.user_data["address_type"] = "location"
            return

        if text == "✏️ Kўлда ёзиш":
            await update.message.reply_text(
                "✏️ Манзилингизни матн кўринишида ёзинг:"
            )
            context.user_data["address_type"] = "text"
            return

        # Agar matn yozilgan bo'lsa
        if context.user_data.get("address_type") == "text":
            if len(text) < 5:
                await update.message.reply_text("❌ Илтимос, тўлиқ манзил ёзинг (камида 5 ҳарф):")
                return

            context.user_data["address"] = text
            context.user_data["order_step"] = "time"

            await update.message.reply_text(
                "🕐 Қачон уста керак?",
                reply_markup=time_keyboard(),
            )
            return

        # Agar address_type tanlanmagan bo'lsa
        await update.message.reply_text(
            "📍 Манзилни қандай юбормоқчисиз?",
            reply_markup=address_keyboard(),
        )
        return

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------
    if context.user_data.get("order_step") == "time":
        if text == "⬅️ Orqaga":
            context.user_data["order_step"] = "address"
            context.user_data["address_type"] = "text"
            await update.message.reply_text(
                "📍 Манзилни қандай юбормоқчисиз?",
                reply_markup=address_keyboard(),
            )
            return

        context.user_data["order_time"] = text
        context.user_data["order_step"] = "confirm"

        service = context.user_data.get("service", "")
        sub_service = context.user_data.get("sub_service", "")
        description = context.user_data.get("description", "")
        address = context.user_data.get("address", "")
        order_time = context.user_data.get("order_time", "")

        await update.message.reply_text(
            f"📋 БУЮРТМА МАЪЛУМОТЛАРИ\n\n"
            f"🛠 Хизмат: {service}\n"
            f"📋 Тури: {sub_service}\n"
            f"📝 Муаммо: {description}\n"
            f"📍 Манзил: {address}\n"
            f"🕐 Вақт: {order_time}\n\n"
            "✅ Буюртмани тасдиқлайсизми?",
            reply_markup=confirm_keyboard(),
        )
        return

    # ========================================================
    # CHECK ORDER STATUS
    # ========================================================
    if context.user_data.get("checking_order"):
        try:
            order_num = text.strip()
            if not order_num.startswith("#"):
                order_num = f"#{order_num}"

            order = await get_order_by_num(order_num)
            if not order:
                await update.message.reply_text("❌ Буюртма топилмади.")
                return

            await update.message.reply_text(
                f"🔍 БУЮРТМА {order['order_num']}\n\n"
                f"🛠 Хизмат: {order['service']} – {order['sub_service']}\n"
                f"📍 Манзил: {order['address']}\n"
                f"🕐 Вақт: {order['order_time']}\n"
                f"📌 Ҳолат: {order['status']}\n"
                f"👨‍🔧 Уста: {order['master_name'] or 'Ҳали бириктирилмаган'}"
            )
            context.user_data["checking_order"] = False
            return
        except:
            await update.message.reply_text("❌ Нотоғри формат. Масалан: 1245")
            return

    # ========================================================
    # CANCEL ORDER
    # ========================================================
    if context.user_data.get("cancel_order"):
        try:
            order_num = text.strip()
            if not order_num.startswith("#"):
                order_num = f"#{order_num}"

            order = await get_order_by_num(order_num)
            if not order:
                await update.message.reply_text("❌ Буюртма топилмади.")
                return

            if order["customer_id"] != user.id:
                await update.message.reply_text("❌ Бу сизнинг буюртмангиз эмас.")
                return

            if order["status"] not in ["new", "accepted"]:
                await update.message.reply_text("❌ Бу буюртмани бекор қилиб бўлмайди.")
                return

            await update_order_status(order["id"], "cancelled")
            await update.message.reply_text(
                f"❌ {order['order_num']} буюртма бекор қилинди.",
                reply_markup=client_menu(),
            )
            context.user_data["cancel_order"] = False
            return
        except:
            await update.message.reply_text("❌ Нотоғри формат. Масалан: 1245")
            return

    # ========================================================
    # REVIEW - SELECT MASTER
    # ========================================================
    if context.user_data.get("review_step") == "select_master":
        try:
            order_id = int(text)
            order = await get_order(order_id)

            if not order or order["customer_id"] != user.id:
                await update.message.reply_text("❌ Буюртма топилмади.")
                return

            if not order["master_id"]:
                await update.message.reply_text("❌ Бу буюртмага уста бириктирилмаган.")
                return

            context.user_data["review_order_id"] = order_id
            context.user_data["review_master_id"] = order["master_id"]
            context.user_data["review_step"] = "rating"

            await update.message.reply_text(
                "⭐ Устага баҳо беринг:",
                reply_markup=rating_keyboard(),
            )
            return
        except:
            await update.message.reply_text("❌ Нотоғри формат. Буюртма рақамини ёзинг.")
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
# ORDER CONFIRM ACTION
# ============================================================

async def order_confirm_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тасдиқлаш тугмаси босилганда ишлайди"""
    message = update.message
    user = update.effective_user

    try:
        # Foydalanuvchi ma'lumotlarini olish
        db_user = await get_user(user.id)

        if not db_user:
            await ensure_user(user)
            db_user = await get_user(user.id)

        # Ma'lumotlarni olish
        service = context.user_data.get("service", "")
        sub_service = context.user_data.get("sub_service", "")
        description = context.user_data.get("description", "")
        address = context.user_data.get("address", "")
        order_time = context.user_data.get("order_time", "")
        phone = context.user_data.get("order_phone", "")
        problem_photo = context.user_data.get("problem_photo", "")
        latitude = context.user_data.get("latitude", 0)
        longitude = context.user_data.get("longitude", 0)

        # Telefon raqamni tekshirish
        if not phone:
            await message.reply_text(
                "❌ Телефон рақам топилмади. Илтимос, қайта уриниб кўринг.",
                reply_markup=client_menu()
            )
            context.user_data.clear()
            return

        # Buyurtma yaratish
        order_id, order_num = await create_order(
            customer_id=user.id,
            customer_name=user.full_name or "Михоз",
            customer_phone=phone,
            service=service,
            sub_service=sub_service,
            description=description,
            address=address,
            order_time=order_time,
            latitude=latitude,
            longitude=longitude,
        )

        # Rasmni saqlash
        if problem_photo:
            await add_photo(order_id, problem_photo, "problem")

        # Мижозга хабар
        await message.reply_text(
            f"✅ БУЮРТМА ҚАБУЛ ҚИЛИНДИ!\n\n"
            f"🆔 {order_num}\n"
            f"🛠 {service} – {sub_service}\n"
            f"📍 {address}\n"
            f"🕐 {order_time}\n\n"
            "👨‍🔧 Усталар қидирилмоқда...\n"
            "📨 Тез орада хабар берамиз!",
            reply_markup=client_menu(),
        )

        # Гуруппага юбориш
        if MASTERS_GROUP_ID:
            try:
                await send_order_to_group(context.bot, order_id)
            except Exception as e:
                logger.error(f"Group send error: {e}")

        # Админга хабар
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🆕 ЯНГИ БУЮРТМА!\n\n"
                    f"🆔 {order_num}\n"
                    f"👤 {user.full_name}\n"
                    f"📞 {phone}\n"
                    f"🛠 {service}\n"
                    f"📍 {address}\n"
                    f"🕐 {order_time}"
                )
            except Exception as e:
                logger.error(f"Admin send error: {e}")

        # Бонус қўшиш
        await add_bonus(user.id, order_id, 10, "order_created")

        # Тозалаш
        context.user_data.clear()

    except Exception as e:
        logger.exception("ORDER CREATE ERROR")
        await message.reply_text(
            f"⚠️ Техник хатолик юз берди: {str(e)}\n"
            "Илтимос, қайта уриниб кўринг.",
            reply_markup=client_menu()
        )
        context.user_data.clear()


# ============================================================
# SEND ORDER TO GROUP
# ============================================================

async def send_order_to_group(bot, order_id):
    order = await get_order(order_id)
    if not order:
        return

    text = (
        f"🆕 ЯНГИ БУЮРТМА!\n\n"
        f"🆔 {order['order_num']}\n"
        f"👤 Михоз: {order['customer_name']}\n"
        f"📞 Телефон: {order['customer_phone']}\n"
        f"🛠 Хизмат: {order['service']} – {order['sub_service']}\n"
        f"📝 Муаммо: {order['description']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"🕐 Вақт: {order['order_time']}\n"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ ҚАБУЛ ҚИЛИШ", callback_data=f"accept:{order['id']}"),
                InlineKeyboardButton("❌ РАД ЭТИШ", callback_data=f"reject:{order['id']}"),
            ],
            [
                InlineKeyboardButton("🔧 Ишни бошлаш", callback_data=f"startwork:{order['id']}"),
            ],
            [
                InlineKeyboardButton("✅ Ишни якунлаш", callback_data=f"complete:{order['id']}"),
            ],
            [
                InlineKeyboardButton("📸 Расмларни кўриш", callback_data=f"viewphotos:{order['id']}"),
            ],
        ]
    )

    await bot.send_message(
        MASTERS_GROUP_ID,
        text,
        reply_markup=keyboard,
    )


# ============================================================
# PHOTO HANDLER
# ============================================================

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1]

    # Order photo
    if context.user_data.get("order_step") == "photo":
        context.user_data["problem_photo"] = photo.file_id
        context.user_data["order_step"] = "address"
        context.user_data["address_type"] = "text"

        await update.message.reply_text(
            "✅ Расм қабул қилинди!\n\n"
            "📍 Манзилни қандай юбормоқчисиз?",
            reply_markup=address_keyboard(),
        )
        return

    # Complete work photo
    if context.user_data.get("complete_order"):
        order_id = context.user_data["complete_order"]

        await add_photo(order_id, photo.file_id, "result")

        await update.message.reply_text(
            "✅ Натижа расми қабул қилинди!\n\n"
            "💰 Иш нархини ёзинг (сўмда):\n"
            "Масалан: 150000"
        )
        context.user_data["complete_step"] = "price"
        return

    await update.message.reply_text(
        "📸 Расм қабул қилинди.\n"
        "Буюртма бериш учун менюдан фойдаланинг."
    )


# ============================================================
# LOCATION HANDLER
# ============================================================

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location

    if context.user_data.get("order_step") == "address" and context.user_data.get("address_type") == "location":
        context.user_data["address"] = f"📍 {location.latitude}, {location.longitude}"
        context.user_data["latitude"] = location.latitude
        context.user_data["longitude"] = location.longitude
        context.user_data["order_step"] = "time"

        await update.message.reply_text(
            f"✅ Жойлашувингиз қабул қилинди!\n\n"
            f"🌐 Кенглик: {location.latitude}\n"
            f"🌐 Узунлик: {location.longitude}\n\n"
            "🕐 Қачон уста керак?",
            reply_markup=time_keyboard(),
        )
        return

    await update.message.reply_text(
        f"📍 Жойлашувингиз қабул қилинди!\n\n"
        f"🌐 Кенглик: {location.latitude}\n"
        f"🌐 Узунлик: {location.longitude}"
    )


# ============================================================
# ORDER CALLBACKS
# ============================================================

async def order_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Bu funksiya endi ishlatilmaydi, chunki биз кнопкаларни қўшдик
    await query.message.reply_text(
        "⚠️ Илтимос, ✅ Тасдиқлаш ёки ❌ Рад қилиш тугмасини босинг.",
        reply_markup=confirm_keyboard(),
    )


async def order_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    await query.edit_message_text("❌ Буюртма бекор қилинди.")
    await query.message.reply_text("Бош меню:", reply_markup=client_menu())


# ============================================================
# MASTER CALLBACK
# ============================================================

async def master_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db_user = await get_user(user.id)

    if not db_user or db_user["role"] != "master":
        await query.answer("❌ Сиз уста сифатида рўйхатдан ўтмагансиз.", show_alert=True)
        return

    data = query.data

    try:
        action, order_id_text = data.split(":", 1)
        order_id = int(order_id_text)
        order = await get_order(order_id)

        if not order:
            await query.answer("Буюртма топилмади.", show_alert=True)
            return

        # ACCEPT
        if action == "accept":
            if order["status"] != "new":
                await query.answer("Бу буюртмани бошқа уста олган.", show_alert=True)
                return

            await assign_master(order_id, user.id, user.full_name, db_user["phone"] or "")

            await query.edit_message_text(
                f"✅ БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
                f"🆔 {order['order_num']}\n"
                f"👨‍🔧 Уста: {user.full_name}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}"
            )

            # Мижозга хабар
            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"✅ Буюртмангиз қабул қилинди!\n\n"
                    f"🆔 {order['order_num']}\n"
                    f"👨‍🔧 Уста: {user.full_name}\n"
                    f"📞 {db_user['phone']}\n\n"
                    "Уста тез орада боғланади.",
                )
            except Exception:
                pass
            return

        # REJECT
        if action == "reject":
            await update_order_status(order_id, "rejected")

            await query.edit_message_text(
                f"❌ {order['order_num']} рад этилди.\n🔄 Бошқа уста кўриб чиқиши мумкин."
            )

            # Мижозга хабар
            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"❌ {order['order_num']} буюртмангизни ушбу уста қабул қилмади.\n\n🔄 Бошқа уста қидирилмоқда.",
                )
            except Exception:
                pass
            return

        # START WORK
        if action == "startwork":
            if order["master_id"] != user.id:
                await query.answer("Бу буюртма сизга тегишли эмас.", show_alert=True)
                return

            await update_order_status(order_id, "started")

            await query.message.reply_text(
                f"🔧 {order['order_num']} иш бошланди!\n👨‍🔧 Уста: {user.full_name}"
            )

            # Мижозга хабар
            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"🔧 Иш бошланди!\n\n🆔 {order['order_num']}\n👨‍🔧 Уста: {user.full_name}",
                )
            except Exception:
                pass
            return

        # COMPLETE
        if action == "complete":
            if order["master_id"] != user.id:
                await query.answer("Бу буюртма сизга тегишли эмас.", show_alert=True)
                return

            await query.message.reply_text(
                f"📸 {order['order_num']} буюртма учун натижа расмини юборинг.\n\n"
                "📸 Расм юборинг (мажбурий!)"
            )

            context.user_data["complete_order"] = order_id
            return

        # VIEW PHOTOS
        if action == "viewphotos":
            async with db_pool.acquire() as conn:
                photos = await conn.fetch(
                    "SELECT * FROM u24_order_photos WHERE order_id = $1",
                    order_id,
                )

            if not photos:
                await query.answer("Бу буюртмада расмлар йўқ.")
                return

            for photo in photos:
                await query.message.reply_photo(photo["file_id"])
            return

    except Exception as e:
        logger.exception("MASTER CALLBACK ERROR")
        await query.message.reply_text("⚠️ Техник хатолик юз берди.")


# ============================================================
# REVIEW CALLBACK
# ============================================================

async def review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("rating_"):
        rating = int(data.split("_")[1])
        context.user_data["review_rating"] = rating
        context.user_data["review_step"] = "comment"

        await query.message.edit_text(
            f"⭐ Баҳо: {rating} юлдуз\n\n📝 Шарҳингизни ёзинг:"
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
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE customer_id = $1
                ORDER BY id DESC
                LIMIT 20
                """,
                user.id,
            )

        if not rows:
            await update.message.reply_text("📋 Сизда ҳали буюртмалар йўқ.")
            return

        out = "📋 МЕНИНГ БУЮРТМАЛАРИМ\n\n"
        for row in rows:
            out += (
                f"🆔 {row['order_num']}\n"
                f"🛠 {row['service']}\n"
                f"📍 {row['address']}\n"
                f"📌 Ҳолат: {row['status']}\n"
                f"📅 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "🔍 Buyurtma holati":
        await update.message.reply_text(
            "🔍 Буюртма рақамини ёзинг.\n\nМасалан: 1245"
        )
        context.user_data["checking_order"] = True
        return

    if text == "❌ Bekor qilish":
        await update.message.reply_text(
            "❌ Бекор қилмоқчи бўлган буюртма рақамини ёзинг.\n\nМасалан: 1245"
        )
        context.user_data["cancel_order"] = True
        return

    if text == "🔁 Qayta buyurtma":
        await update.message.reply_text("🔁 Янги буюртма беришни бошлаймиз.")
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
            await update.message.reply_text("👨‍🔧 Ҳали сизга уста бириктирилмаган.")
            return

        out = "👨‍🔧 МЕНИНГ УСТАЛАРИМ\n\n"
        for row in rows:
            out += f"👨‍🔧 {row['master_name']}\n📞 {row['master_phone']}\n\n"

        await update.message.reply_text(out)
        return

    if text == "⭐ Reytingim":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(rating), 0) AS avg
                FROM u24_ratings
                WHERE customer_id = $1
                """,
                user.id,
            )

        bonuses = await get_user_bonus(user.id)

        await update.message.reply_text(
            f"⭐ РЕЙТИНГИНГИЗ\n\n"
            f"⭐ Ўртача: {float(row['avg']):.2f}\n"
            f"📝 Шарҳлар: {row['total']}\n\n"
            f"🎁 Бонуслар: {bonuses:,} балл\n"
            f"💰 1 балл = 100 сўм\n"
            f"💵 Жами: {bonuses * 100:,} сўм"
        )
        return

    if text == "📝 Sharh qoldirish":
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM u24_orders
                WHERE customer_id = $1 AND status = 'completed'
                ORDER BY id DESC
                """,
                user.id,
            )

        if not rows:
            await update.message.reply_text(
                "📝 Сизда якунланган буюртмалар йўқ.\n"
                "Аввал буюртма беринг ва иш якунлансин."
            )
            return

        out = "📝 ШАРҲ ҚОЛДИРИШ\n\n"
        out += "Қайси буюртма учун шарҳ қолдирмоқчисиз?\n"
        out += "Буюртма рақамини ёзинг:\n\n"

        for row in rows[:5]:
            out += f"🆔 {row['order_num']} – {row['service']}\n"

        await update.message.reply_text(out)
        context.user_data["review_step"] = "select_master"
        return

    if text == "📌 Eslatmalarim":
        await update.message.reply_text("📌 Ҳозирча эслатмалар мавжуд эмас.")
        return

    if text == "🗺 Yaqin atrofdagi ustalar":
        await update.message.reply_text(
            "🗺 Яқин атрофдаги усталарни аниқлаш учун геолокация функцияси ишлатилади.\n\n"
            "📍 Жойлашувингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📍 Геолокация юбориш", request_location=True)]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return

    if text == "📅 Yozilma":
        await update.message.reply_text(
            "📅 Брон қилиш: буюртма беришда керакли вақтни кўрсатинг."
        )
        return

    if text == "🎁 Loyallik va bonuslar":
        bonuses = await get_user_bonus(user.id)

        if bonuses < 500:
            level = "🥉 Мис"
        elif bonuses < 1000:
            level = "🥈 Кумуш"
        elif bonuses < 3000:
            level = "🥇 Олтин"
        elif bonuses < 5000:
            level = "💎 Платина"
        else:
            level = "👑 Олмос"

        await update.message.reply_text(
            f"🎁 ЛОЯЛЛИК ВА БОНУСЛАР\n\n"
            f"💰 Бонус балл: {bonuses:,}\n"
            f"💵 1 балл = 100 сўм\n"
            f"💵 Жами: {bonuses * 100:,} сўм\n\n"
            f"🏆 Даражангиз: {level}\n\n"
            f"📋 Даражалар:\n"
            f"├── 🥉 Мис: 0-500 балл\n"
            f"├── 🥈 Кумуш: 501-1000 балл\n"
            f"├── 🥇 Олтин: 1001-3000 балл\n"
            f"├── 💎 Платина: 3001-5000 балл\n"
            f"└── 👑 Олмос: 5000+ балл"
        )
        return

    if text == "🤖 AI yordamchi":
        await update.message.reply_text(
            "🤖 AI ЁРДАМЧИ\n\n"
            "1️⃣ 💬 Савол-жавоб\n"
            "2️⃣ 📝 Буюртма тавсияси\n"
            "3️⃣ 💰 Нарх ҳисоблаш\n"
            "4️⃣ 📅 Вақт режалаш\n"
            "5️⃣ 📸 Расм таҳлили\n\n"
            "Саводингизни ёзинг, AI ёрдамчи жавоб беради."
        )
        return

    if text == "⚙️ Sozlamalar":
        db_user = await get_user(user.id)
        await update.message.reply_text(
            f"⚙️ СОЗЛАМАЛАР\n\n"
            f"👤 Исм: {db_user['full_name']}\n"
            f"📞 Телефон: {db_user['phone']}\n"
            f"🎭 Рол: {db_user['role']}\n"
            f"🌐 Тил: 🇺🇿 Ўзбек\n\n"
            f"🔔 Билдиришномалар: ✅ Ёқилган\n\n"
            f"📞 Диспетчер: {DISPATCHER_PHONE}"
        )
        return

    if text == "📊 Mening statistikam":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status='completed') AS completed,
                    COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
                FROM u24_orders
                WHERE customer_id = $1
                """,
                user.id,
            )

        bonuses = await get_user_bonus(user.id)

        await update.message.reply_text(
            f"📊 МЕНИНГ СТАТИСТИКАМ\n\n"
            f"📋 Жами буюртмалар: {row['total']}\n"
            f"✅ Тугалланган: {row['completed']}\n"
            f"❌ Бекор қилинган: {row['cancelled']}\n"
            f"📌 Жараёнда: {row['total'] - row['completed'] - row['cancelled']}\n\n"
            f"🎁 Бонуслар: {bonuses:,} балл"
        )
        return

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 ЧЕГИРМАЛАР ВА АКСИЯЛАР\n\n"
            "Ҳозирча фаол чегирмалар йўқ.\n\n"
            "🔔 Янгиликлар учун билдиришномаларни ёқинг!"
        )
        return

    if text == "📞 Tez yordam":
        await update.message.reply_text(
            f"📞 ТЕЗ ЁРДАМ\n\n"
            f"1️⃣ 📞 Диспетчер: {DISPATCHER_PHONE}\n"
            f"2️⃣ 💬 Бот орқали ёзинг: @usta24_bot\n\n"
            f"❓ Кўп сўраладиган саволлар:\n\n"
            f"Қ: Қандай буюртма бериш мумкин?\n"
            f"А: '🛒 Буюртма бериш' тугмасини босинг!\n\n"
            f"Қ: Нарх қандай ҳисобланади?\n"
            f"А: Хизмат турига қараб 40,000-80,000 сўм/соат\n\n"
            f"Қ: Тўлов қандай амалга оширилади?\n"
            f"А: Фақат нақд пул! Ишдан кейин тўлов!\n\n"
            f"Қ: 24/7 режим қандай ишлайди?\n"
            f"А: Шошилинч ҳолатда 10-15 дақиқада етиб борамиз!"
        )
        return

    if text == "🔔 Bildirishnomalar":
        await update.message.reply_text(
            "🔔 БИЛДИРИШНОМАЛАР\n\n"
            "✅ Янги буюртма\n"
            "✅ Буюртма ҳолати ўзгариши\n"
            "✅ Уста хабарлари\n"
            "❌ Реклама хабарлари\n\n"
            "🔊 Овоз: ✅ Ёқилган"
        )
        return

    if text == "📁 Mening hujjatlarim":
        await update.message.reply_text(
            "📁 МЕНИНГ ҲУЖЖАТЛАРИМ\n\n"
            "1️⃣ 📄 Чеклар (0 та)\n"
            "2️⃣ 📄 Шартномалар (0 та)\n"
            "3️⃣ 📄 Ҳисоботлар (0 та)\n\n"
            "📤 Ҳужжатлар тез орада қўшилади."
        )
        return

    if text == "🕊 Do'stga tavsiya":
        await update.message.reply_text(
            "🕊 ДО'СТГА ТАВСИЯ ҚИЛИШ\n\n"
            "1️⃣ 📤 Telegram орқали улашиш\n"
            "2️⃣ 🔗 Ҳавола: https://t.me/usta24_bot\n"
            "3️⃣ 📱 QR код\n\n"
            "🎁 Ҳар бир дўстингиз учун 50,000 сўм бонус!"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 ДИСПЕТЧЕР\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7 – КУТИШ ЙЎҚ!\n"
            f"📍 Андижон шаҳар\n\n"
            f"📋 Вазифалар:\n"
            f"├── 📞 Михоз ва усталарни боғлаш\n"
            f"├── 🚨 24/7 шошилинч ҳолатларни бошқариш\n"
            f"├── 📋 Заказларни назорат қилиш\n"
            f"└── 👨‍🔧 Янги усталарни қабул қилиш"
        )
        return

    if text == "🚨 24/7 Shoshilinch":
        await update.message.reply_text(
            "🚨 24/7 ШОШИЛИНЧ РЕЖИМ\n\n"
            "⚡ ДОЛЗАРБ ҲОЛАТЛАР:\n"
            "├── 💧 Сув тўхтаб қолди\n"
            "├── ⚡ Электр ўчиб қолди\n"
            "├── 🔥 Газ оқаётган\n"
            "├── 🚪 Эшик синиб қолди\n"
            "└── 🚰 Қувур ёрилган\n\n"
            "🕐 24/7 УСТА КЕРАК:\n"
            "├── 🔴 ҲОЗИР (10-15 дақиқа) – 20% устама\n"
            "├── 🟡 30 дақиқада – 10% устама\n"
            "└── 🟢 1 соатда – оддий нарх\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "💵 ТЎЛОВ: Фақат нақд! Ишдан кейин!\n"
            "📸 Натижа расми мажбурий!"
        )
        return

    await update.message.reply_text(
        "❓ Тушунарсиз буюртма.\n"
        "Илтимос, менюдан танланг:",
        reply_markup=client_menu(),
    )


# ============================================================
# MASTER TEXT HANDLER (ҚИСҚАРТИРИЛГАН)
# ============================================================

async def master_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "📋 Yangi buyurtmalar":
        if not MASTERS_GROUP_ID:
            await update.message.reply_text("⚠️ MASTERS_GROUP_ID созланмаган.")
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
            await update.message.reply_text("📋 Ҳозирча янги буюртмалар йўқ.")
            return

        out = "📋 ЯНГИ БУЮРТМАЛАР\n\n"
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
            await update.message.reply_text("✅ Фаол буюртмалар йўқ.")
            return

        out = "✅ ФАОЛ БУЮРТМАЛАР\n\n"
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
            await update.message.reply_text("⏳ Тугалланган ишлар йўқ.")
            return

        out = "⏳ ИШ ТАРИХИ\n\n"
        for row in rows:
            out += (
                f"🆔 {row['order_num']}\n"
                f"🛠 {row['service']}\n"
                f"💰 {row['price']} сўм\n"
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
            f"💰 ИШ ҲАҚИ\n\n"
            f"📋 Ишлар: {row['total']}\n"
            f"💵 Жами: {row['money']:,} сўм"
        )
        return

    if text == "⭐ Reytingim":
        rating = await get_master_rating(user.id)

        await update.message.reply_text(
            f"⭐ УСТА РЕЙТИНГИ\n\n"
            f"⭐ {float(rating['avg']):.2f}\n"
            f"📝 {rating['total']} та баҳо\n\n"
            f"📊 Ўз ўрнингизни билиш учун яхши ишланг!"
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
            f"📊 ИШ СТАТИСТИКАСИ\n\n"
            f"📋 Жами: {row['total']}\n"
            f"✅ Тугалланган: {row['completed']}\n"
            f"❌ Бекор қилинган: {row['cancelled']}\n"
            f"📌 Жараёнда: {row['total'] - row['completed'] - row['cancelled']}"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 ДИСПЕТЧЕР\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7"
        )
        return

    if text == "🚨 24/7 Shoshilinch":
        await update.message.reply_text(
            f"🚨 24/7 ШОШИЛИНЧ\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "🔴 ҲОЗИР: +20%\n"
            "🟡 30 дақиқа: +10%\n"
            "🟢 1 соат: оддий нарх\n\n"
            "💰 Тўлов: Фақат нақд! Ишдан кейин!"
        )
        return

    await update.message.reply_text(
        "👨‍🔧 Уста менюси:",
        reply_markup=master_menu(),
    )


# ============================================================
# ADMIN TEXT HANDLER (ҚИСҚАРТИРИЛГАН)
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
            f"👥 ФОЙДАЛАНУВЧИЛАР\n\n"
            f"👤 Жами: {row['total']}\n"
            f"🛒 Михозлар: {row['clients']}\n"
            f"👨‍🔧 Усталар: {row['masters']}\n"
            f"👑 Админлар: {row['admins']}"
        )
        return

    if text == "🛠 Buyurtmalar":
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status='new') AS new,
                    COUNT(*) FILTER (WHERE status='accepted') AS accepted,
                    COUNT(*) FILTER (WHERE status='started') AS started,
                    COUNT(*) FILTER (WHERE status='completed') AS completed,
                    COUNT(*) FILTER (WHERE status='cancelled') AS cancelled,
                    COALESCE(SUM(price), 0) AS total_price
                FROM u24_orders
                """
            )

        await update.message.reply_text(
            f"🛠 БУЮРТМАЛАР\n\n"
            f"📋 Жами: {row['total']}\n"
            f"🆕 Янги: {row['new']}\n"
            f"✅ Қабул қилинган: {row['accepted']}\n"
            f"🔧 Жараёнда: {row['started']}\n"
            f"🏁 Тугаган: {row['completed']}\n"
            f"❌ Бекор: {row['cancelled']}\n\n"
            f"💰 Жами: {row['total_price']:,} сўм"
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
            await update.message.reply_text("👨‍🔧 Ҳали усталар йўқ.")
            return

        out = "👨‍🔧 УСТАЛАР\n\n"
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
            await update.message.reply_text("⭐ Ҳали рейтинглар йўқ.")
            return

        out = "⭐ TOP УСТАЛАР\n\n"
        for i, row in enumerate(rows, 1):
            out += f"{i}. 👨‍🔧 ID:{row['master_id']} ⭐{float(row['avg']):.2f} ({row['total']})\n"

        await update.message.reply_text(out)
        return

    if text == "🎁 Bonuslar":
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM u24_bonuses")
            count = await conn.fetchval("SELECT COUNT(*) FROM u24_bonuses")

        await update.message.reply_text(
            f"🎁 БОНУСЛАР\n\n"
            f"💰 Жами бонус: {total:,} балл\n"
            f"📋 Трансакциялар: {count} та"
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
            f"💰 ТЎЛОВЛАР\n\n"
            f"💵 Жами: {total:,} сўм\n"
            f"📋 Тугалланган: {count} та буюртма\n\n"
            f"📊 Ўртача: {total // count if count else 0:,} сўм"
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
            f"📊 USTA 24 СТАТИСТИКА\n\n"
            f"👥 Фойдаланувчилар: {users}\n"
            f"├── 👨‍🔧 Усталар: {masters}\n"
            f"└── 👤 Михозлар: {users - masters}\n\n"
            f"🛠 Буюртмалар: {orders}\n"
            f"├── ✅ Тугалланган: {completed}\n"
            f"└── ⭐ Рейтинглар: {ratings}\n\n"
            f"💰 Тушум: {money:,} сўм"
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 ДИСПЕТЧЕР\n\n"
            f"📱 {DISPATCHER_PHONE}\n"
            f"🕐 24/7\n"
            f"📍 Андижон шаҳар\n\n"
            f"📋 Вазифалар:\n"
            f"├── 📞 Михоз ва усталарни боғлаш\n"
            f"├── 🚨 24/7 шошилинч ҳолатларни бошқариш\n"
            f"├── 📋 Заказларни назорат қилиш\n"
            f"└── 👨‍🔧 Янги усталарни қабул қилиш"
        )
        return

    if text == "🚨 24/7 Rejim":
        await update.message.reply_text(
            "🚨 24/7 ШОШИЛИНЧ РЕЖИМ\n\n"
            "📋 СТАТИСТИКА:\n"
            "├── Жами сўровлар: 5 та\n"
            "├── ✅ Бажарилган: 4 та\n"
            "└── ⏳ Кутилаётган: 1 та\n\n"
            "🔴 ҲОЗИР +20%\n"
            "🟡 30 дақиқа +10%\n"
            "🟢 1 соат оддий\n\n"
            f"📞 {DISPATCHER_PHONE}"
        )
        return

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 ЧЕГИРМАЛАР\n\n"
            "1️⃣ 🎉 Янги йил – 20% (15.01.2026 гача)\n"
            "2️⃣ 🎁 Дўстни таклиф қилиш – 50,000 сўм\n"
            "3️⃣ 📱 Telegram орқали – 10%\n\n"
            "[➕ Янги чегирма]  [✏️ Таҳрирлаш]"
        )
        return

    if text == "🛠 Xizmat turlari":
        await update.message.reply_text(
            "🛠 ХИЗМАТ ТУРЛАРИ\n\n"
            "1️⃣ 🔧 Сантехника – актив\n"
            "2️⃣ ⚡ Электрика – актив\n"
            "3️⃣ 🪑 Мебел йиғиш – актив\n"
            "4️⃣ 🛠 Мебел таъмирлаш – актив\n"
            "5️⃣ 🚚 Юк ташиш – актив\n\n"
            "[➕ Янги хизмат]  [✏️ Таҳрирлаш]"
        )
        return

    if text == "📢 E'lonlar":
        await update.message.reply_text(
            "📢 ЭЪЛОНЛАР\n\n"
            "1️⃣ 🔥 Янги йил аксияси – актив\n"
            "2️⃣ 🎁 Дўстни таклиф қилинг – актив\n"
            "3️⃣ 📱 Telegram орқали – актив\n\n"
            "[➕ Янги эълон]  [📨 Юбориш]"
        )
        return

    if text == "⚙️ Sozlamalar":
        await update.message.reply_text(
            "⚙️ СОЗЛАМАЛАР\n\n"
            "🔔 Билдиришнома: ✅\n"
            "🤖 AI ёрдамчи: ✅\n"
            "💰 Нарх тизими: ✅\n"
            "🌐 Тил: 🇺🇿 Ўзбек\n"
            "📍 Ҳудуд: Андижон\n"
            "🔐 Хавфсизлик: ✅"
        )
        return

    if text == "📸 Galereya":
        await update.message.reply_text(
            "📸 ГАЛЕРЕЯ\n\n"
            "📸 Барча расмлар: 48 та\n"
            "├── 📸 Муаммо расмлари: 25 та\n"
            "├── 📸 Натижа расмлари: 20 та\n"
            "└── 📹 Видеолар: 3 та\n\n"
            "[🖼 Кўриш]  [🗑 Бошқариш]"
        )
        return

    if text == "📱 Botni boshqarish":
        await update.message.reply_text(
            "📱 БОТНИ БОШҚАРИШ\n\n"
            "📊 Бот статистикаси:\n"
            "├── Фойдаланувчилар: 45 та\n"
            "├── Буюртмалар: 120 та\n"
            "└── Хато liklar: 0 та\n\n"
            "[🔄 Қайта ишга тушириш]  [📋 Хатоликлар]"
        )
        return

    if text == "📞 Qo'llab-quvvatlash":
        await update.message.reply_text(
            "📞 ҚЎЛЛАБ-ҚУВВАТЛАШ\n\n"
            "📨 Михоз хабарлари: 3 та\n"
            "📨 Уста хабарлари: 2 та\n"
            "📋 Шикоятлар: 0 та\n\n"
            "[💬 Жавоб бериш]  [📋 Барчаси]"
        )
        return

    await update.message.reply_text(
        "👑 Админ панели:",
        reply_markup=admin_menu(),
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
                "⚠️ Техник хатолик юз берди.\nИлтимос, қайта уриниб кўринг."
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
