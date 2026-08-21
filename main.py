# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
# Python 3.11+
# python-telegram-bot 22.3
# PostgreSQL / asyncpg
# ============================================================

import os
import io
import csv
import asyncio
import logging
from datetime import datetime, timedelta

import asyncpg

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")


# ============================================================
# ENVIRONMENT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")
DISPATCHER_ID_RAW = os.getenv("DISPATCHER_ID")
MASTERS_GROUP_ID_RAW = os.getenv("MASTERS_GROUP_ID")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID topilmadi!")

if not MASTERS_GROUP_ID_RAW:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")


try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID noto'g'ri!")


try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID_RAW)
except ValueError:
    raise RuntimeError("MASTERS_GROUP_ID noto'g'ri!")


DISPATCHER_ID = None

if DISPATCHER_ID_RAW:
    try:
        DISPATCHER_ID = int(DISPATCHER_ID_RAW)
    except ValueError:
        DISPATCHER_ID = None


# ============================================================
# GLOBALS
# ============================================================

DB = None
REMINDER_TASK = None


# ============================================================
# CONSTANTS
# ============================================================

STATUS_NEW = "new"
STATUS_ACCEPTED = "accepted"
STATUS_STARTED = "started"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"

STATUS_TEXT = {
    STATUS_NEW: "🟡 Yangi",
    STATUS_ACCEPTED: "🔵 Qabul qilingan",
    STATUS_STARTED: "🟠 Ish jarayonida",
    STATUS_COMPLETED: "🟢 Tugallangan",
    STATUS_CANCELLED: "🔴 Bekor qilingan",
    STATUS_REJECTED: "❌ Rad etilgan",
}


# ============================================================
# CONVERSATION STATES
# ============================================================

ORDER_NAME = 100
ORDER_PHONE = 101
ORDER_LOCATION = 102
ORDER_SERVICE = 103
ORDER_ADDRESS = 104
ORDER_DESCRIPTION = 105
ORDER_CONFIRM = 106

MASTER_PHONE = 200


# ============================================================
# DATABASE INIT
# ============================================================

async def init_db():

    global DB

    DB = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with DB.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                language TEXT DEFAULT 'uz',
                notifications BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # MASTERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                work_start TEXT DEFAULT '08:00',
                work_end TEXT DEFAULT '22:00',
                services TEXT,
                status TEXT DEFAULT 'active',
                rating NUMERIC(3,2) DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                master_id BIGINT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                service TEXT NOT NULL,
                address TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'new',
                price NUMERIC(12,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # HISTORY
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS order_history (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                user_id BIGINT,
                old_status TEXT,
                new_status TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # REVIEWS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                customer_id BIGINT,
                master_id BIGINT,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # FAVORITES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(customer_id, master_id)
            )
        """)

        # ----------------------------------------------------
        # PRICES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id BIGSERIAL PRIMARY KEY,
                service TEXT UNIQUE NOT NULL,
                price NUMERIC(12,2) DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # COUPONS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id BIGSERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                discount NUMERIC(5,2) DEFAULT 0,
                max_uses INTEGER DEFAULT 0,
                used_count INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # REMINDERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                user_id BIGINT,
                reminder_type TEXT,
                remind_at TIMESTAMP,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # INVITES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                code TEXT UNIQUE,
                invited_count INTEGER DEFAULT 0,
                reward_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ----------------------------------------------------
        # ACTION LOG
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS action_history (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                action TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # MIGRATION FOR OLD DATABASE
        # ----------------------------------------------------

        migration_queries = [
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'uz'
            """,
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS notifications BOOLEAN DEFAULT TRUE
            """,
            """
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS price NUMERIC(12,2) DEFAULT 0
            """,
            """
            ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()
            """,
            """
            ALTER TABLE masters
            ADD COLUMN IF NOT EXISTS work_start TEXT DEFAULT '08:00'
            """,
            """
            ALTER TABLE masters
            ADD COLUMN IF NOT EXISTS work_end TEXT DEFAULT '22:00'
            """,
            """
            ALTER TABLE masters
            ADD COLUMN IF NOT EXISTS services TEXT
            """,
            """
            ALTER TABLE masters
            ADD COLUMN IF NOT EXISTS rating NUMERIC(3,2) DEFAULT 0
            """,
            """
            ALTER TABLE masters
            ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0
            """,
        ]

        for query in migration_queries:
            try:
                await conn.execute(query)
            except Exception:
                logger.exception(
                    "Migration xatosi"
                )

    logger.info("PostgreSQL tayyor.")


# ============================================================
# USER FUNCTIONS
# ============================================================

async def save_user(update: Update):

    if not update.effective_user:
        return

    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else None
    )

    async with DB.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO users (
                id,
                username,
                full_name
            )
            VALUES ($1,$2,$3)

            ON CONFLICT(id)
            DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            """,
            user.id,
            username,
            user.full_name,
        )


async def update_user_phone(
    user_id,
    phone,
):

    async with DB.acquire() as conn:

        await conn.execute(
            """
            UPDATE users
            SET phone=$1,
                updated_at=NOW()
            WHERE id=$2
            """,
            phone,
            user_id,
        )


async def log_action(
    user_id,
    action,
    details="",
):

    try:

        async with DB.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO action_history(
                    user_id,
                    action,
                    details
                )
                VALUES($1,$2,$3)
                """,
                user_id,
                action,
                details,
            )

    except Exception:
        logger.exception(
            "Action log xatosi"
        )


def is_admin(update: Update):

    return bool(
        update.effective_user
        and update.effective_user.id == ADMIN_ID
    )


async def is_master(user_id):

    async with DB.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE telegram_id=$1
            AND status='active'
            """,
            user_id,
        )

    return row


# ============================================================
# MENUS
# ============================================================

def customer_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📝 Buyurtma berish"),
                KeyboardButton("📋 Buyurtmalarim"),
            ],
            [
                KeyboardButton("🔎 Buyurtma holati"),
                KeyboardButton("❌ Buyurtmani bekor qilish"),
            ],
            [
                KeyboardButton("🔄 Qayta buyurtma"),
                KeyboardButton("👨‍🔧 Mening ustalarim"),
            ],
            [
                KeyboardButton("⭐ Reytingim"),
                KeyboardButton("💬 Sharh qoldirish"),
            ],
            [
                KeyboardButton("🔔 Eslatmalarim"),
                KeyboardButton("⚙️ Sozlamalar"),
            ],
        ],
        resize_keyboard=True,
    )


def master_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🆕 Yangi buyurtmalar"),
                KeyboardButton("📋 Mening buyurtmalarim"),
            ],
            [
                KeyboardButton("👤 Profil"),
                KeyboardButton("👥 Mijozlarim"),
            ],
            [
                KeyboardButton("▶️ Ishni boshlash"),
                KeyboardButton("✅ Ishni yakunlash"),
            ],
            [
                KeyboardButton("❌ Buyurtmani rad etish"),
                KeyboardButton("📊 Mening statistikam"),
            ],
            [
                KeyboardButton("💰 Kunlik daromad"),
                KeyboardButton("⭐ Reytingim"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("👨‍🔧 Ustalar"),
                KeyboardButton("📋 Buyurtmalar"),
            ],
            [
                KeyboardButton("👤 Mijozlar"),
                KeyboardButton("📊 Statistika"),
            ],
            [
                KeyboardButton("📑 Hisobot"),
                KeyboardButton("💵 Narxlar"),
            ],
            [
                KeyboardButton("📢 Xabarlar"),
                KeyboardButton("🎟 Kuponlar"),
            ],
            [
                KeyboardButton("⚙️ Sozlamalar"),
            ],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "❌ Bekor qilish"
                )
            ]
        ],
        resize_keyboard=True,
    )


def phone_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📱 Telefon raqamim",
                    request_contact=True,
                )
            ],
            [
                KeyboardButton(
                    "❌ Bekor qilish"
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
            [
                KeyboardButton(
                    "❌ Bekor qilish"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def service_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🪑 Mebel"),
                KeyboardButton("🚚 Ko‘chirish"),
            ],
            [
                KeyboardButton("🔧 Ta’mirlash"),
                KeyboardButton("🏠 Uy xizmati"),
            ],
            [
                KeyboardButton("➕ Boshqa"),
            ],
            [
                KeyboardButton(
                    "❌ Bekor qilish"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def confirm_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("✅ Tasdiqlash"),
                KeyboardButton("✏️ O‘zgartirish"),
            ],
            [
                KeyboardButton(
                    "❌ Bekor qilish"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await save_user(update)

    user_id = update.effective_user.id

    if is_admin(update):

        await update.message.reply_text(
            "🛠 USTA 24 ANDIJON\n\n"
            "👑 ADMIN PANEL\n\n"
            f"🆔 Admin ID: {ADMIN_ID}",
            reply_markup=admin_menu(),
        )

        return

    master = await is_master(user_id)

    if master:

        await update.message.reply_text(
            "🛠 USTA 24 ANDIJON\n\n"
            "👨‍🔧 USTA PANEL\n\n"
            f"👤 {master['full_name']}",
            reply_markup=master_menu(),
        )

        return

    await update.message.reply_text(
        "🛠 USTA 24 ANDIJON\n\n"
        f"Assalomu alaykum, "
        f"{update.effective_user.first_name}! 👋\n\n"
        "Xizmat kerak bo‘lsa, "
        "«📝 Buyurtma berish» tugmasini bosing.",
        reply_markup=customer_menu(),
    )


# ============================================================
# ORDER START
# ============================================================

async def order_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    context.user_data[
        "customer_id"
    ] = update.effective_user.id

    await update.message.reply_text(
        "📝 YANGI BUYURTMA\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ 👤 Ismingizni kiriting:",
        reply_markup=cancel_keyboard(),
    )

    return ORDER_NAME


# ============================================================
# ORDER NAME
# ============================================================

async def order_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        if not update.message:
            return ORDER_NAME

        text = (
            update.message.text or ""
        ).strip()

        logger.info(
            "NAME: user=%s text=%s",
            update.effective_user.id,
            text,
        )

        if text == "❌ Bekor qilish":

            return await cancel_order(
                update,
                context,
            )

        if len(text) < 2:

            await update.message.reply_text(
                "❌ Ism juda qisqa.\n\n"
                "Ismingizni qayta kiriting:"
            )

            return ORDER_NAME

        context.user_data[
            "name"
        ] = text

        await update.message.reply_text(
            "2️⃣ 📞 Telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard(),
        )

        return ORDER_PHONE

    except Exception as e:

        logger.exception(
            "order_name ERROR: %s",
            e,
        )

        await update.message.reply_text(
            "⚠️ Xatolik yuz berdi.\n"
            "Ismingizni yana yuboring:"
        )

        return ORDER_NAME


# ============================================================
# ORDER PHONE
# ============================================================

async def order_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        if not update.message:
            return ORDER_PHONE

        if update.message.contact:

            contact = update.message.contact

            if (
                contact.user_id
                and contact.user_id
                != update.effective_user.id
            ):

                await update.message.reply_text(
                    "❌ O‘zingizning telefon "
                    "raqamingizni yuboring.",
                    reply_markup=phone_keyboard(),
                )

                return ORDER_PHONE

            phone = contact.phone_number

        else:

            text = (
                update.message.text or ""
            ).strip()

            if text == "❌ Bekor qilish":

                return await cancel_order(
                    update,
                    context,
                )

            phone = text

        if not phone:

            await update.message.reply_text(
                "❌ Telefon raqamini yuboring.",
                reply_markup=phone_keyboard(),
            )

            return ORDER_PHONE

        context.user_data[
            "phone"
        ] = phone

        await update_user_phone(
            update.effective_user.id,
            phone,
        )

        await update.message.reply_text(
            "3️⃣ 📍 Geolokatsiyangizni yuboring.\n\n"
            "Pastdagi tugmani bosing:",
            reply_markup=location_keyboard(),
        )

        logger.info(
            "PHONE OK: user=%s",
            update.effective_user.id,
        )

        return ORDER_LOCATION

    except Exception as e:

        logger.exception(
            "order_phone ERROR: %s",
            e,
        )

        await update.message.reply_text(
            "⚠️ Telefonni qabul qilishda xatolik.\n"
            "Qaytadan yuboring.",
            reply_markup=phone_keyboard(),
        )

        return ORDER_PHONE


# ============================================================
# ORDER LOCATION - TUZATILGAN
# ============================================================

async def order_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        if not update.message:
            return ORDER_LOCATION

        # ----------------------------------------------------
        # LOCATION KELDI
        # ----------------------------------------------------

        if update.message.location:

            location = update.message.location

            context.user_data[
                "latitude"
            ] = float(location.latitude)

            context.user_data[
                "longitude"
            ] = float(location.longitude)

            logger.info(
                "LOCATION OK: user=%s lat=%s lon=%s",
                update.effective_user.id,
                location.latitude,
                location.longitude,
            )

            await update.message.reply_text(
                "✅ Geolokatsiya qabul qilindi.\n\n"
                "4️⃣ 🛠 Xizmat turini tanlang:",
                reply_markup=service_keyboard(),
            )

            return ORDER_SERVICE

        # ----------------------------------------------------
        # BEKOR QILISH
        # ----------------------------------------------------

        text = (
            update.message.text or ""
        ).strip()

        if text == "❌ Bekor qilish":

            return await cancel_order(
                update,
                context,
            )

        # ----------------------------------------------------
        # LOCATION EMAS
        # ----------------------------------------------------

        await update.message.reply_text(
            "❌ Geolokatsiya kelmadi.\n\n"
            "📍 «Geolokatsiyani yuborish» "
            "tugmasini bosing.",
            reply_markup=location_keyboard(),
        )

        return ORDER_LOCATION

    except Exception as e:

        logger.exception(
            "order_location ERROR: %s",
            e,
        )

        await update.message.reply_text(
            "⚠️ Geolokatsiyani qabul qilishda "
            "xatolik yuz berdi.\n\n"
            "📍 Tugmani yana bosing.",
            reply_markup=location_keyboard(),
        )

        return ORDER_LOCATION


# ============================================================
# ORDER SERVICE
# ============================================================

async def order_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    allowed = {
        "🪑 Mebel",
        "🚚 Ko‘chirish",
        "🔧 Ta’mirlash",
        "🏠 Uy xizmati",
        "➕ Boshqa",
    }

    if text not in allowed:

        await update.message.reply_text(
            "🛠 Xizmatni tugmalardan tanlang:",
            reply_markup=service_keyboard(),
        )

        return ORDER_SERVICE

    context.user_data[
        "service"
    ] = text

    await update.message.reply_text(
        "5️⃣ 📍 To‘liq manzilni yozing:\n\n"
        "Masalan:\n"
        "Andijon shahar, Bobur ko‘chasi 77",
        reply_markup=cancel_keyboard(),
    )

    return ORDER_ADDRESS


# ============================================================
# ORDER ADDRESS
# ============================================================

async def order_address(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    if len(text) < 3:

        await update.message.reply_text(
            "❌ Manzilni to‘liqroq kiriting:"
        )

        return ORDER_ADDRESS

    context.user_data[
        "address"
    ] = text

    await update.message.reply_text(
        "6️⃣ 📝 Izoh yozing:\n\n"
        "Masalan:\n"
        "Shkaf yig‘ish kerak.",
        reply_markup=cancel_keyboard(),
    )

    return ORDER_DESCRIPTION


# ============================================================
# ORDER DESCRIPTION
# ============================================================

async def order_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    if not text:
        text = "Izoh yo‘q"

    context.user_data[
        "description"
    ] = text

    d = context.user_data

    await update.message.reply_text(
        "📋 BUYURTMA TEKSHIRUVI\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Ism: {d.get('name')}\n"
        f"📞 Telefon: {d.get('phone')}\n"
        f"🛠 Xizmat: {d.get('service')}\n"
        f"📍 Manzil: {d.get('address')}\n"
        f"📝 Izoh: {d.get('description')}\n"
        "📍 Geolokatsiya: ✅\n\n"
        "Buyurtmani tasdiqlaysizmi?",
        reply_markup=confirm_keyboard(),
    )

    return ORDER_CONFIRM


# ============================================================
# CREATE ORDER
# ============================================================

async def order_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    if text == "✏️ O‘zgartirish":

        customer_id = (
            update.effective_user.id
        )

        context.user_data.clear()

        context.user_data[
            "customer_id"
        ] = customer_id

        await update.message.reply_text(
            "📝 Buyurtmani qaytadan boshlaymiz.\n\n"
            "1️⃣ 👤 Ismingizni kiriting:",
            reply_markup=cancel_keyboard(),
        )

        return ORDER_NAME

    if text != "✅ Tasdiqlash":

        await update.message.reply_text(
            "Iltimos, tugmalardan tanlang.",
            reply_markup=confirm_keyboard(),
        )

        return ORDER_CONFIRM

    d = context.user_data

    customer_id = (
        update.effective_user.id
    )

    required = [
        "name",
        "phone",
        "latitude",
        "longitude",
        "service",
        "address",
        "description",
    ]

    missing = [
        key
        for key in required
        if key not in d
    ]

    if missing:

        logger.error(
            "ORDER DATA MISSING: %s",
            missing,
        )

        await update.message.reply_text(
            "⚠️ Buyurtma ma’lumotlari to‘liq emas.\n"
            "Iltimos, buyurtmani qaytadan boshlang.",
            reply_markup=customer_menu(),
        )

        context.user_data.clear()

        return ConversationHandler.END

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    try:

        async with DB.acquire() as conn:

            async with conn.transaction():

                order_id = await conn.fetchval(
                    """
                    INSERT INTO orders(
                        customer_id,
                        name,
                        phone,
                        latitude,
                        longitude,
                        service,
                        address,
                        description,
                        status
                    )
                    VALUES(
                        $1,$2,$3,$4,$5,
                        $6,$7,$8,$9
                    )
                    RETURNING id
                    """,
                    customer_id,
                    d["name"],
                    d["phone"],
                    d["latitude"],
                    d["longitude"],
                    d["service"],
                    d["address"],
                    d["description"],
                    STATUS_NEW,
                )

                await conn.execute(
                    """
                    INSERT INTO order_history(
                        order_id,
                        user_id,
                        old_status,
                        new_status,
                        note
                    )
                    VALUES(
                        $1,$2,$3,$4,$5
                    )
                    """,
                    order_id,
                    customer_id,
                    None,
                    STATUS_NEW,
                    "Buyurtma yaratildi",
                )

    except Exception as e:

        logger.exception(
            "ORDER CREATE ERROR: %s",
            e,
        )

        await update.message.reply_text(
            "❌ Buyurtmani saqlashda xatolik yuz berdi.\n\n"
            "Iltimos, keyinroq qayta urinib ko‘ring.",
            reply_markup=customer_menu(),
        )

        return ConversationHandler.END

    # --------------------------------------------------------
    # CUSTOMER MESSAGE
    # --------------------------------------------------------

    await update.message.reply_text(
        "✅ BUYURTMA QABUL QILINDI!\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Buyurtma: #{order_id}\n"
        f"👤 Mijoz: {d['name']}\n"
        f"📞 Telefon: {d['phone']}\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"📍 Manzil: {d['address']}\n\n"
        "📌 Holat: 🟡 Yangi\n\n"
        "👨‍🔧 Buyurtma ustalarga yuborildi.",
        reply_markup=customer_menu(),
    )

    # --------------------------------------------------------
    # MASTER GROUP
    # --------------------------------------------------------

    group_text = (
        "🆕 YANGI BUYURTMA\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Buyurtma: #{order_id}\n"
        f"👤 Mijoz: {d['name']}\n"
        f"📞 Telefon: {d['phone']}\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"📍 Manzil: {d['address']}\n"
        f"📝 Izoh: {d['description']}\n"
        "📌 Holat: 🟡 Yangi"
    )

    try:

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=group_text,
        )

        await context.bot.send_location(
            chat_id=MASTERS_GROUP_ID,
            latitude=d["latitude"],
            longitude=d["longitude"],
        )

    except Exception as e:

        logger.exception(
            "MASTER GROUP ERROR: %s",
            e,
        )

    await log_action(
        customer_id,
        "create_order",
        f"order_id={order_id}",
    )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# CANCEL
# ============================================================

async def cancel_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Buyurtma bekor qilindi.",
        reply_markup=customer_menu(),
    )

    return ConversationHandler.END


# ============================================================
# CUSTOMER ORDERS
# ============================================================

async def my_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                id,
                service,
                address,
                status,
                price,
                created_at
            FROM orders
            WHERE customer_id=$1
            ORDER BY id DESC
            LIMIT 50
            """,
            user_id,
        )

    if not rows:

        await update.message.reply_text(
            "📋 Sizda hozircha buyurtmalar yo‘q.",
            reply_markup=customer_menu(),
        )

        return

    text = (
        "📋 BUYURTMALARIM\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['address']}\n"
            f"📌 {STATUS_TEXT.get(row['status'], row['status'])}\n"
            f"💰 {row['price'] or 0}\n"
            f"🕐 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=customer_menu(),
    )


# ============================================================
# CUSTOMER ORDER STATUS
# ============================================================

async def order_status_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "🔎 Buyurtma ID raqamini yuboring:\n\n"
        "Masalan: 25",
        reply_markup=cancel_keyboard(),
    )

    context.user_data[
        "waiting_order_status"
    ] = True


async def process_order_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get(
        "waiting_order_status"
    ):
        return False

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        context.user_data.clear()

        await update.message.reply_text(
            "❌ Bekor qilindi.",
            reply_markup=customer_menu(),
        )

        return True

    if not text.isdigit():

        await update.message.reply_text(
            "❌ Faqat buyurtma ID raqamini yuboring."
        )

        return True

    order_id = int(text)

    async with DB.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            AND customer_id=$2
            """,
            order_id,
            update.effective_user.id,
        )

    if not row:

        await update.message.reply_text(
            "❌ Bu buyurtma topilmadi."
        )

        return True

    await update.message.reply_text(
        f"🔎 BUYURTMA #{row['id']}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🛠 Xizmat: {row['service']}\n"
        f"📍 Manzil: {row['address']}\n"
        f"📌 Holat: "
        f"{STATUS_TEXT.get(row['status'], row['status'])}\n"
        f"💰 Narx: {row['price'] or 0}",
        reply_markup=customer_menu(),
    )

    context.user_data.clear()

    return True


# ============================================================
# CUSTOMER CANCEL ORDER
# ============================================================

async def customer_cancel_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "❌ Bekor qilmoqchi bo‘lgan "
        "buyurtma ID raqamini yuboring:",
        reply_markup=cancel_keyboard(),
    )

    context.user_data[
        "waiting_cancel_order"
    ] = True


async def process_customer_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get(
        "waiting_cancel_order"
    ):
        return False

    text = (
        update.message.text or ""
    ).strip()

    if text == "❌ Bekor qilish":

        context.user_data.clear()

        await update.message.reply_text(
            "❌ Bekor qilindi.",
            reply_markup=customer_menu(),
        )

        return True

    if not text.isdigit():

        await update.message.reply_text(
            "❌ Buyurtma ID raqamini yuboring."
        )

        return True

    order_id = int(text)

    async with DB.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            AND customer_id=$2
            """,
            order_id,
            update.effective_user.id,
        )

        if not row:

            await update.message.reply_text(
                "❌ Buyurtma topilmadi."
            )

            return True

        if row["status"] in (
            STATUS_COMPLETED,
            STATUS_CANCELLED,
        ):

            await update.message.reply_text(
                "❌ Bu buyurtmani bekor qilib bo‘lmaydi."
            )

            return True

        await conn.execute(
            """
            UPDATE orders
            SET status=$1,
                cancelled_at=NOW(),
                updated_at=NOW()
            WHERE id=$2
            """,
            STATUS_CANCELLED,
            order_id,
        )

        await conn.execute(
            """
            INSERT INTO order_history(
                order_id,
                user_id,
                old_status,
                new_status,
                note
            )
            VALUES($1,$2,$3,$4,$5)
            """,
            order_id,
            update.effective_user.id,
            row["status"],
            STATUS_CANCELLED,
            "Mijoz bekor qildi",
        )

    await update.message.reply_text(
        f"✅ Buyurtma #{order_id} bekor qilindi.",
        reply_markup=customer_menu(),
    )

    context.user_data.clear()

    return True


# ============================================================
# MASTER REGISTRATION
# ============================================================

async def master_register_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "👨‍🔧 USTA RO‘YXATDAN O‘TISH\n\n"
        "Telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard(),
    )

    return MASTER_PHONE


async def master_register_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.message.contact:

        phone = (
            update.message.contact.phone_number
        )

    else:

        phone = (
            update.message.text or ""
        ).strip()

    if not phone:

        await update.message.reply_text(
            "❌ Telefon raqamingizni yuboring.",
            reply_markup=phone_keyboard(),
        )

        return MASTER_PHONE

    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else None
    )

    async with DB.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO masters(
                telegram_id,
                username,
                full_name,
                phone,
                status
            )
            VALUES($1,$2,$3,$4,'active')

            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username=EXCLUDED.username,
                full_name=EXCLUDED.full_name,
                phone=EXCLUDED.phone,
                status='active',
                updated_at=NOW()
            """,
            user.id,
            username,
            user.full_name,
            phone,
        )

        await conn.execute(
            """
            UPDATE users
            SET phone=$1
            WHERE id=$2
            """,
            phone,
            user.id,
        )

    await update.message.reply_text(
        "✅ Usta sifatida ro‘yxatdan o‘tdingiz!\n\n"
        "👨‍🔧 Usta paneli ochildi.",
        reply_markup=master_menu(),
    )

    await log_action(
        user.id,
        "master_register",
        "",
    )

    return ConversationHandler.END


# ============================================================
# MASTER PROFILE
# ============================================================

async def master_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:

        await update.message.reply_text(
            "❌ Siz usta sifatida ro‘yxatdan "
            "o‘tmagansiz."
        )

        return

    await update.message.reply_text(
        "👨‍🔧 PROFIL\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Ism: {master['full_name']}\n"
        f"📞 Telefon: {master['phone'] or '-'}\n"
        f"🔗 Username: {master['username'] or '-'}\n"
        f"🆔 ID: {master['telegram_id']}\n"
        f"🕐 Ish vaqti: "
        f"{master['work_start']} - {master['work_end']}\n"
        f"🛠 Xizmatlar: "
        f"{master['services'] or 'Belgilanmagan'}\n"
        f"⭐ Reyting: {master['rating'] or 0}",
        reply_markup=master_menu(),
    )


# ============================================================
# MASTER NEW ORDERS
# ============================================================

async def master_new_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE status=$1
            AND master_id IS NULL
            ORDER BY id DESC
            LIMIT 20
            """,
            STATUS_NEW,
        )

    if not rows:

        await update.message.reply_text(
            "🆕 Hozircha yangi buyurtmalar yo‘q.",
            reply_markup=master_menu(),
        )

        return

    for row in rows:

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Qabul qilish",
                        callback_data=(
                            f"accept:{row['id']}"
                        ),
                    ),
                    InlineKeyboardButton(
                        "❌ Rad etish",
                        callback_data=(
                            f"reject:{row['id']}"
                        ),
                    ),
                ]
            ]
        )

        await update.message.reply_text(
            "🆕 YANGI BUYURTMA\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🔢 #{row['id']}\n"
            f"👤 {row['name']}\n"
            f"📞 {row['phone']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['address']}\n"
            f"📝 {row['description']}",
            reply_markup=keyboard,
        )


# ============================================================
# MASTER ACCEPT
# ============================================================

async def master_accept_order(
    query,
    context,
    order_id,
):

    master_id = query.from_user.id

    master = await is_master(master_id)

    if not master:

        await query.answer(
            "❌ Siz usta emassiz.",
            show_alert=True,
        )

        return

    async with DB.acquire() as conn:

        async with conn.transaction():

            row = await conn.fetchrow(
                """
                SELECT *
                FROM orders
                WHERE id=$1
                FOR UPDATE
                """,
                order_id,
            )

            if not row:

                await query.answer(
                    "❌ Buyurtma topilmadi.",
                    show_alert=True,
                )

                return

            if row["status"] != STATUS_NEW:

                await query.answer(
                    "❌ Buyurtma allaqachon olingan.",
                    show_alert=True,
                )

                return

            await conn.execute(
                """
                UPDATE orders
                SET master_id=$1,
                    status=$2,
                    accepted_at=NOW(),
                    updated_at=NOW()
                WHERE id=$3
                """,
                master_id,
                STATUS_ACCEPTED,
                order_id,
            )

            await conn.execute(
                """
                INSERT INTO order_history(
                    order_id,
                    user_id,
                    old_status,
                    new_status,
                    note
                )
                VALUES($1,$2,$3,$4,$5)
                """,
                order_id,
                master_id,
                STATUS_NEW,
                STATUS_ACCEPTED,
                "Usta qabul qildi",
            )

    await query.edit_message_text(
        "✅ BUYURTMA QABUL QILINDI\n\n"
        f"🔢 #{order_id}\n"
        f"👨‍🔧 Usta: {master['full_name']}"
    )

    # Customerga xabar
    try:

        await context.bot.send_message(
            chat_id=row["customer_id"],
            text=(
                "👨‍🔧 BUYURTMANGIZ QABUL QILINDI!\n\n"
                f"🔢 Buyurtma: #{order_id}\n"
                f"👨‍🔧 Usta: {master['full_name']}\n"
                f"📞 Usta telefoni: "
                f"{master['phone'] or '-'}\n\n"
                "📌 Holat: 🔵 Qabul qilingan"
            ),
        )

    except Exception:
        logger.exception(
            "Customer notify error"
        )

    await query.answer(
        "Buyurtma sizga biriktirildi."
    )


# ============================================================
# MASTER REJECT
# ============================================================

async def master_reject_order(
    query,
    context,
    order_id,
):

    master = await is_master(
        query.from_user.id
    )

    if not master:

        await query.answer(
            "❌ Siz usta emassiz.",
            show_alert=True,
        )

        return

    async with DB.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            """,
            order_id,
        )

        if not row:

            await query.answer(
                "❌ Buyurtma topilmadi.",
                show_alert=True,
            )

            return

        await conn.execute(
            """
            INSERT INTO order_history(
                order_id,
                user_id,
                old_status,
                new_status,
                note
            )
            VALUES($1,$2,$3,$4,$5)
            """,
            order_id,
            query.from_user.id,
            row["status"],
            row["status"],
            f"Usta rad etdi: {master['full_name']}",
        )

    await query.edit_message_text(
        f"❌ Buyurtma #{order_id} rad etildi."
    )

    await query.answer(
        "Buyurtma rad etildi."
    )


# ============================================================
# MASTER MY ORDERS
# ============================================================

async def master_my_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id=$1
            ORDER BY id DESC
            LIMIT 50
            """,
            update.effective_user.id,
        )

    if not rows:

        await update.message.reply_text(
            "📋 Sizga hali buyurtma biriktirilmagan.",
            reply_markup=master_menu(),
        )

        return

    text = (
        "📋 MENING BUYURTMALARIM\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['name']}\n"
            f"📞 {row['phone']}\n"
            f"🛠 {row['service']}\n"
            f"📌 "
            f"{STATUS_TEXT.get(row['status'], row['status'])}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=master_menu(),
    )


# ============================================================
# MASTER START WORK
# ============================================================

async def master_start_work(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return

    await update.message.reply_text(
        "▶️ Ishni boshlash uchun "
        "buyurtma ID raqamini yuboring:"
    )

    context.user_data[
        "master_start_work"
    ] = True


# ============================================================
# MASTER COMPLETE
# ============================================================

async def master_complete(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return

    await update.message.reply_text(
        "✅ Ishni yakunlash uchun "
        "buyurtma ID raqamini yuboring:"
    )

    context.user_data[
        "master_complete"
    ] = True


# ============================================================
# MASTER PROCESS ID
# ============================================================

async def process_master_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = (
        update.message.text or ""
    ).strip()

    if not text.isdigit():
        return False

    order_id = int(text)

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return False

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if context.user_data.get(
        "master_start_work"
    ):

        async with DB.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT *
                FROM orders
                WHERE id=$1
                AND master_id=$2
                """,
                order_id,
                update.effective_user.id,
            )

            if not row:

                await update.message.reply_text(
                    "❌ Buyurtma topilmadi yoki "
                    "sizga biriktirilmagan."
                )

                return True

            await conn.execute(
                """
                UPDATE orders
                SET status=$1,
                    started_at=NOW(),
                    updated_at=NOW()
                WHERE id=$2
                """,
                STATUS_STARTED,
                order_id,
            )

            await conn.execute(
                """
                INSERT INTO order_history(
                    order_id,
                    user_id,
                    old_status,
                    new_status,
                    note
                )
                VALUES($1,$2,$3,$4,$5)
                """,
                order_id,
                update.effective_user.id,
                row["status"],
                STATUS_STARTED,
                "Usta ishni boshladi",
            )

        context.user_data.pop(
            "master_start_work",
            None,
        )

        await update.message.reply_text(
            f"▶️ Buyurtma #{order_id} "
            "ish jarayoniga o'tdi.",
            reply_markup=master_menu(),
        )

        try:

            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"▶️ Buyurtma #{order_id}\n\n"
                    "Usta ishni boshladi.\n"
                    "📌 Holat: 🟠 Ish jarayonida"
                ),
            )

        except Exception:
            pass

        return True

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    if context.user_data.get(
        "master_complete"
    ):

        async with DB.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT *
                FROM orders
                WHERE id=$1
                AND master_id=$2
                """,
                order_id,
                update.effective_user.id,
            )

            if not row:

                await update.message.reply_text(
                    "❌ Buyurtma topilmadi."
                )

                return True

            await conn.execute(
                """
                UPDATE orders
                SET status=$1,
                    completed_at=NOW(),
                    updated_at=NOW()
                WHERE id=$2
                """,
                STATUS_COMPLETED,
                order_id,
            )

            await conn.execute(
                """
                INSERT INTO order_history(
                    order_id,
                    user_id,
                    old_status,
                    new_status,
                    note
                )
                VALUES($1,$2,$3,$4,$5)
                """,
                order_id,
                update.effective_user.id,
                row["status"],
                STATUS_COMPLETED,
                "Usta ishni yakunladi",
            )

        context.user_data.pop(
            "master_complete",
            None,
        )

        await update.message.reply_text(
            f"✅ Buyurtma #{order_id} "
            "tugallandi.",
            reply_markup=master_menu(),
        )

        try:

            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"✅ Buyurtma #{order_id} "
                    "tugallandi!\n\n"
                    "⭐ Ustaga baho berishingiz mumkin."
                ),
            )

        except Exception:
            pass

        return True

    return False


# ============================================================
# MASTER STATISTICS
# ============================================================

async def master_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    master = await is_master(
        update.effective_user.id
    )

    if not master:
        return

    async with DB.acquire() as conn:

        daily = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE master_id=$1
            AND created_at::date=CURRENT_DATE
            """,
            master["telegram_id"],
        )

        weekly = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE master_id=$1
            AND created_at >= NOW()-INTERVAL '7 days'
            """,
            master["telegram_id"],
        )

        monthly = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE master_id=$1
            AND created_at >= NOW()-INTERVAL '30 days'
            """,
            master["telegram_id"],
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE master_id=$1
            AND status='completed'
            """,
            master["telegram_id"],
        )

    await update.message.reply_text(
        "📊 MENING STATISTIKAM\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Bugun: {daily}\n"
        f"📆 Haftalik: {weekly}\n"
        f"🗓 Oylik: {monthly}\n"
        f"✅ Tugallangan: {completed}\n"
        f"⭐ Reyting: {master['rating'] or 0}",
        reply_markup=master_menu(),
    )


# ============================================================
# ADMIN MASTER LIST
# ============================================================

async def admin_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM masters
            ORDER BY id DESC
            """
        )

    if not rows:

        await update.message.reply_text(
            "👨‍🔧 Ustalar ro‘yxati bo‘sh.\n\n"
            "Usta qo‘shish:\n"
            "/usta_qosh @username\n\n"
            "Usta o‘chirish:\n"
            "/usta_ochirish @username",
            reply_markup=admin_menu(),
        )

        return

    text = (
        "👨‍🔧 USTALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for row in rows:

        text += (
            f"👤 {row['full_name']}\n"
            f"🔗 {row['username'] or '-'}\n"
            f"🆔 ID: {row['telegram_id']}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"📌 {row['status']}\n"
            f"⭐ {row['rating'] or 0}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN ADD MASTER BY USERNAME
# ============================================================

async def admin_add_master(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    if not context.args:

        await update.message.reply_text(
            "👨‍🔧 USTA QO‘SHISH\n\n"
            "Username orqali:\n\n"
            "/usta_qosh @username\n\n"
            "⚠️ Usta avval botga /start "
            "bosgan bo‘lishi kerak."
        )

        return

    username = context.args[0].strip()

    if not username.startswith("@"):
        username = "@" + username

    async with DB.acquire() as conn:

        user = await conn.fetchrow(
            """
            SELECT *
            FROM users
            WHERE LOWER(username)=LOWER($1)
            """,
            username,
        )

        if not user:

            await update.message.reply_text(
                "❌ Bu username bazada topilmadi.\n\n"
                "Usta avval botga /start bosishi kerak."
            )

            return

        await conn.execute(
            """
            INSERT INTO masters(
                telegram_id,
                username,
                full_name,
                phone,
                status
            )
            VALUES($1,$2,$3,$4,'active')

            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username=EXCLUDED.username,
                full_name=EXCLUDED.full_name,
                phone=EXCLUDED.phone,
                status='active',
                updated_at=NOW()
            """,
            user["id"],
            user["username"],
            user["full_name"],
            user["phone"],
        )

    await update.message.reply_text(
        "✅ USTA QO‘SHILDI!\n\n"
        f"👤 {user['full_name']}\n"
        f"🔗 {user['username']}\n"
        f"🆔 ID: {user['id']}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN DELETE MASTER BY USERNAME
# ============================================================

async def admin_delete_master(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    if not context.args:

        await update.message.reply_text(
            "👨‍🔧 USTA O‘CHIRISH\n\n"
            "Username orqali:\n\n"
            "/usta_ochirish @username"
        )

        return

    username = context.args[0].strip()

    if not username.startswith("@"):
        username = "@" + username

    async with DB.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE LOWER(username)=LOWER($1)
            """,
            username,
        )

        if not row:

            await update.message.reply_text(
                "❌ Bunday usta topilmadi."
            )

            return

        await conn.execute(
            """
            UPDATE masters
            SET status='deleted',
                updated_at=NOW()
            WHERE telegram_id=$1
            """,
            row["telegram_id"],
        )

    await update.message.reply_text(
        "✅ USTA O‘CHIRILDI!\n\n"
        f"👤 {row['full_name']}\n"
        f"🔗 {row['username']}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN ALL ORDERS
# ============================================================

async def admin_all_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            ORDER BY id DESC
            LIMIT 50
            """
        )

    if not rows:

        await update.message.reply_text(
            "📋 Buyurtmalar yo‘q.",
            reply_markup=admin_menu(),
        )

        return

    text = (
        "📋 BARCHA BUYURTMALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['name']}\n"
            f"📞 {row['phone']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['address']}\n"
            f"📌 "
            f"{STATUS_TEXT.get(row['status'], row['status'])}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN CUSTOMERS
# ============================================================

async def admin_customers(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        active = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT customer_id)
            FROM orders
            WHERE status IN(
                'new',
                'accepted',
                'started'
            )
            """
        )

    await update.message.reply_text(
        "👤 MIJOZLAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Jami: {total}\n"
        f"🟢 Faol: {active}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN STATISTICS
# ============================================================

async def admin_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        customers = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        masters = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM masters
            WHERE status='active'
            """
        )

        orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        today = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at::date=CURRENT_DATE
            """
        )

        week = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at >= NOW()-INTERVAL '7 days'
            """
        )

        month = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at >= NOW()-INTERVAL '30 days'
            """
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='completed'
            """
        )

        cancelled = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='cancelled'
            """
        )

    await update.message.reply_text(
        "📊 USTA 24 ANDIJON\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Mijozlar: {customers}\n"
        f"👨‍🔧 Ustalar: {masters}\n"
        f"📋 Buyurtmalar: {orders}\n\n"
        f"📅 Bugun: {today}\n"
        f"📆 7 kun: {week}\n"
        f"🗓 30 kun: {month}\n\n"
        f"✅ Tugallangan: {completed}\n"
        f"❌ Bekor: {cancelled}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN REPORT
# ============================================================

async def admin_report(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        today = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at::date=CURRENT_DATE
            """
        )

        week = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at >= NOW()-INTERVAL '7 days'
            """
        )

        month = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at >= NOW()-INTERVAL '30 days'
            """
        )

        revenue = await conn.fetchval(
            """
            SELECT COALESCE(SUM(price),0)
            FROM orders
            WHERE status='completed'
            """
        )

    await update.message.reply_text(
        "📑 HISOBOT\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Bugun: {today}\n"
        f"📆 Haftalik: {week}\n"
        f"🗓 Oylik: {month}\n"
        f"💰 Umumiy daromad: {revenue}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN EXPORT CSV
# ============================================================

async def admin_export(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                id,
                customer_id,
                master_id,
                name,
                phone,
                service,
                address,
                description,
                status,
                price,
                created_at
            FROM orders
            ORDER BY id DESC
            """
        )

    output = io.StringIO()

    writer = csv.writer(
        output
    )

    writer.writerow(
        [
            "ID",
            "Customer ID",
            "Master ID",
            "Name",
            "Phone",
            "Service",
            "Address",
            "Description",
            "Status",
            "Price",
            "Created",
        ]
    )

    for row in rows:

        writer.writerow(
            [
                row["id"],
                row["customer_id"],
                row["master_id"],
                row["name"],
                row["phone"],
                row["service"],
                row["address"],
                row["description"],
                row["status"],
                row["price"],
                row["created_at"],
            ]
        )

    data = output.getvalue().encode(
        "utf-8-sig"
    )

    file = io.BytesIO(data)

    file.name = (
        "usta24_orders.csv"
    )

    await update.message.reply_document(
        document=InputFile(
            file,
            filename="usta24_orders.csv",
        ),
        caption="📊 USTA 24 buyurtmalar eksporti",
    )


# ============================================================
# ADMIN PRICES
# ============================================================

async def admin_prices(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM prices
            ORDER BY id
            """
        )

    text = (
        "💵 NARXLAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not rows:

        text += (
            "Narxlar hali kiritilmagan.\n\n"
            "Keyin xizmatlar bo‘yicha narxlarni "
            "shu bo‘limdan boshqaramiz."
        )

    else:

        for row in rows:

            text += (
                f"🛠 {row['service']}\n"
                f"💰 {row['price']}\n"
                f"📌 {'Faol' if row['active'] else 'O‘chiq'}\n"
                "────────────\n"
            )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN COUPONS
# ============================================================

async def admin_coupons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with DB.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM coupons
            ORDER BY id DESC
            LIMIT 30
            """
        )

    text = (
        "🎟 KUPONLAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not rows:

        text += "Hozircha kuponlar yo‘q."

    else:

        for row in rows:

            text += (
                f"🎟 {row['code']}\n"
                f"💸 Chegirma: {row['discount']}%\n"
                f"📊 {row['used_count']}/"
                f"{row['max_uses']}\n"
                "────────────\n"
            )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN SETTINGS
# ============================================================

async def admin_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    await update.message.reply_text(
        "⚙️ USTA 24 SOZLAMALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👑 ADMIN_ID:\n{ADMIN_ID}\n\n"
        f"👨‍🔧 MASTERS_GROUP_ID:\n"
        f"{MASTERS_GROUP_ID}\n\n"
        f"🎧 DISPATCHER_ID:\n"
        f"{DISPATCHER_ID or '-'}\n\n"
        "📌 Environment Variables orqali "
        "boshqariladi.",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN BROADCAST
# ============================================================

async def admin_broadcast_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    await update.message.reply_text(
        "📢 XABAR TARQATISH\n\n"
        "Yuboriladigan xabarni yozing:"
    )

    context.user_data[
        "broadcast"
    ] = True


async def admin_broadcast_process(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return False

    if not context.user_data.get(
        "broadcast"
    ):
        return False

    text = update.message.text

    async with DB.acquire() as conn:

        users = await conn.fetch(
            """
            SELECT id
            FROM users
            WHERE notifications=TRUE
            """
        )

    sent = 0

    for user in users:

        try:

            await context.bot.send_message(
                chat_id=user["id"],
                text=text,
            )

            sent += 1

            await asyncio.sleep(
                0.05
            )

        except Exception:
            pass

    context.user_data.pop(
        "broadcast",
        None,
    )

    await update.message.reply_text(
        f"✅ Xabar yuborildi.\n\n"
        f"📨 Yuborildi: {sent}",
        reply_markup=admin_menu(),
    )

    return True# ============================================================
# CALLBACKS
# ============================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    if ":" not in data:
        return

    action, value = data.split(
        ":",
        1,
    )

    if not value.isdigit():
        return

    order_id = int(value)

    if action == "accept":

        await master_accept_order(
            query,
            context,
            order_id,
        )

    elif action == "reject":

        await master_reject_order(
            query,
            context,
            order_id,
        )


# ============================================================
# GENERAL TEXT ROUTER
# ============================================================

async def text_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    # --------------------------------------------------------
    # ORDER STATUS WAITING
    # --------------------------------------------------------

    if await process_order_status(
        update,
        context,
    ):
        return

    # --------------------------------------------------------
    # CUSTOMER CANCEL WAITING
    # --------------------------------------------------------

    if await process_customer_cancel(
        update,
        context,
    ):
        return

    # --------------------------------------------------------
    # MASTER ID ACTIONS
    # --------------------------------------------------------

    if await process_master_id(
        update,
        context,
    ):
        return

    # --------------------------------------------------------
    # ADMIN BROADCAST
    # --------------------------------------------------------

    if await admin_broadcast_process(
        update,
        context,
    ):
        return

    text = update.message.text

    # ========================================================
    # ADMIN
    # ========================================================

    if is_admin(update):

        if text == "👨‍🔧 Ustalar":

            await admin_masters(
                update,
                context,
            )
            return

        if text == "📋 Buyurtmalar":

            await admin_all_orders(
                update,
                context,
            )
            return

        if text == "👤 Mijozlar":

            await admin_customers(
                update,
                context,
            )
            return

        if text == "📊 Statistika":

            await admin_statistics(
                update,
                context,
            )
            return

        if text == "📑 Hisobot":

            await admin_report(
                update,
                context,
            )
            return

        if text == "💵 Narxlar":

            await admin_prices(
                update,
                context,
            )
            return

        if text == "📢 Xabarlar":

            await admin_broadcast_start(
                update,
                context,
            )
            return

        if text == "🎟 Kuponlar":

            await admin_coupons(
                update,
                context,
            )
            return

        if text == "⚙️ Sozlamalar":

            await admin_settings(
                update,
                context,
            )
            return

    # ========================================================
    # MASTER
    # ========================================================

    master = await is_master(
        update.effective_user.id
    )

    if master:

        if text == "🆕 Yangi buyurtmalar":

            await master_new_orders(
                update,
                context,
            )
            return

        if text == "📋 Mening buyurtmalarim":

            await master_my_orders(
                update,
                context,
            )
            return

        if text == "👤 Profil":

            await master_profile(
                update,
                context,
            )
            return

        if text == "▶️ Ishni boshlash":

            await master_start_work(
                update,
                context,
            )
            return

        if text == "✅ Ishni yakunlash":

            await master_complete(
                update,
                context,
            )
            return

        if text == "📊 Mening statistikam":

            await master_statistics(
                update,
                context,
            )
            return

        if text == "👥 Mijozlarim":

            await update.message.reply_text(
                "👥 MIJOZLARIM\n\n"
                "Sizga buyurtma bergan mijozlar "
                "ro‘yxati keyingi bosqichda "
                "kengaytiriladi.",
                reply_markup=master_menu(),
            )
            return

        if text == "💰 Kunlik daromad":

            async with DB.acquire() as conn:

                income = await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(price),0)
                    FROM orders
                    WHERE master_id=$1
                    AND status='completed'
                    AND completed_at::date=CURRENT_DATE
                    """,
                    master["telegram_id"],
                )

            await update.message.reply_text(
                f"💰 KUNLIK DAROMAD\n\n"
                f"{income or 0}",
                reply_markup=master_menu(),
            )

            return

        if text == "⭐ Reytingim":

            await update.message.reply_text(
                f"⭐ REYTINGIM\n\n"
                f"{master['rating'] or 0}\n"
                f"Baholar soni: "
                f"{master['rating_count'] or 0}",
                reply_markup=master_menu(),
            )

            return

    # ========================================================
    # CUSTOMER
    # ========================================================

    if text == "📋 Buyurtmalarim":

        await my_orders(
            update,
            context,
        )
        return

    if text == "🔎 Buyurtma holati":

        await order_status_start(
            update,
            context,
        )
        return

    if text == "❌ Buyurtmani bekor qilish":

        await customer_cancel_start(
            update,
            context,
        )
        return

    if text == "🔄 Qayta buyurtma":

        await update.message.reply_text(
            "🔄 Qayta buyurtma\n\n"
            "Yangi buyurtma yaratish uchun "
            "«📝 Buyurtma berish»ni bosing.",
            reply_markup=customer_menu(),
        )
        return

    if text == "👨‍🔧 Mening ustalarim":

        await update.message.reply_text(
            "👨‍🔧 MENING USTALARIM\n\n"
            "Bu yerda ishlatgan va sevimli "
            "ustalaringiz ko‘rsatiladi.",
            reply_markup=customer_menu(),
        )
        return

    if text == "⭐ Reytingim":

        await update.message.reply_text(
            "⭐ REYTINGIM\n\n"
            "Sizning baholaringiz shu yerda "
            "ko‘rsatiladi.",
            reply_markup=customer_menu(),
        )
        return

    if text == "💬 Sharh qoldirish":

        await update.message.reply_text(
            "💬 SHARH QOLDIRISH\n\n"
            "Tugallangan buyurtma ID raqamini "
            "yuborib baho qoldirish tizimi "
            "ulanadi.",
            reply_markup=customer_menu(),
        )
        return

    if text == "🔔 Eslatmalarim":

        await update.message.reply_text(
            "🔔 ESLATMALARIM\n\n"
            "Faol buyurtmalar bo‘yicha "
            "eslatmalar shu yerda boshqariladi.",
            reply_markup=customer_menu(),
        )
        return

    if text == "⚙️ Sozlamalar":

        await update.message.reply_text(
            "⚙️ SOZLAMALAR\n\n"
            "🌐 Til\n"
            "🔔 Xabarlar",
            reply_markup=customer_menu(),
        )
        return

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    await update.message.reply_text(
        "🛠 USTA 24 ANDIJON\n\n"
        "Menyudan kerakli bo‘limni tanlang.",
        reply_markup=(
            admin_menu()
            if is_admin(update)
            else master_menu()
            if master
            else customer_menu()
        ),
    )


# ============================================================
# REMINDER SYSTEM - ЎЧИРИЛДИ (ВАҚТИНЧА)
# ============================================================

# async def reminder_loop(...):
#     pass


# ============================================================
# POST INIT - ТЎҒРИЛАНДИ
# ============================================================

async def post_init(
    application: Application,
):

    global REMINDER_TASK

    await init_db()

    # ❌ REMINDER ВАҚТИНЧА ЎЧИРИЛДИ
    # REMINDER_TASK = asyncio.create_task(
    #     reminder_loop(application)
    # )

    logger.info("==================================")
    logger.info("USTA 24 ANDIJON ISHGA TUSHDI")
    logger.info("ADMIN_ID=%s", ADMIN_ID)
    logger.info("DISPATCHER_ID=%s", DISPATCHER_ID)
    logger.info("MASTERS_GROUP_ID=%s", MASTERS_GROUP_ID)
    logger.info("==================================")


# ============================================================
# POST SHUTDOWN
# ============================================================

async def post_shutdown(
    application: Application,
):

    global REMINDER_TASK
    global DB

    if REMINDER_TASK:

        REMINDER_TASK.cancel()

        try:
            await REMINDER_TASK
        except asyncio.CancelledError:
            pass

    if DB:

        await DB.close()

    logger.info(
        "USTA 24 to‘xtadi."
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "BOT ERROR: %s",
        context.error,
    )


# ============================================================
# MAIN - TUZATILGAN
# ============================================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ========================================================
    # ORDER CONVERSATION - TUZATILGAN
    # ========================================================

    order_conversation = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex(r"^📝 Buyurtma berish$") & filters.ChatType.PRIVATE,
                order_start,
            )
        ],

        states={

            # ------------------------------------------------
            # NAME
            # ------------------------------------------------

            ORDER_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_name,
                )
            ],

            # ------------------------------------------------
            # PHONE
            # ------------------------------------------------

            ORDER_PHONE: [
                MessageHandler(
                    filters.CONTACT & filters.ChatType.PRIVATE,
                    order_phone,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_phone,
                ),
            ],

            # ------------------------------------------------
            # LOCATION - TUZATILGAN
            # ------------------------------------------------

            ORDER_LOCATION: [
                MessageHandler(
                    filters.LOCATION & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_location,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_location,
                ),
            ],

            # ------------------------------------------------
            # SERVICE
            # ------------------------------------------------

            ORDER_SERVICE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_service,
                )
            ],

            # ------------------------------------------------
            # ADDRESS
            # ------------------------------------------------

            ORDER_ADDRESS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_address,
                )
            ],

            # ------------------------------------------------
            # DESCRIPTION
            # ------------------------------------------------

            ORDER_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_description,
                )
            ],

            # ------------------------------------------------
            # CONFIRM
            # ------------------------------------------------

            ORDER_CONFIRM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    order_confirm,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            ),
            MessageHandler(
                filters.Regex(r"^❌ Bekor qilish$") & filters.ChatType.PRIVATE,
                cancel_order,
            ),
        ],

        allow_reentry=False,
    )

    application.add_handler(
        order_conversation
    )

    # ========================================================
    # MASTER REGISTRATION
    # ========================================================

    master_registration = ConversationHandler(

        entry_points=[
            CommandHandler(
                "usta_register",
                master_register_start,
            )
        ],

        states={

            MASTER_PHONE: [
                MessageHandler(
                    filters.CONTACT & filters.ChatType.PRIVATE,
                    master_register_phone,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                    master_register_phone,
                ),
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            )
        ],
    )

    application.add_handler(
        master_registration
    )

    # ========================================================
    # START
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # ========================================================
    # ADMIN COMMANDS
    # ========================================================

    application.add_handler(
        CommandHandler(
            "usta_qosh",
            admin_add_master,
        )
    )

    application.add_handler(
        CommandHandler(
            "usta_ochirish",
            admin_delete_master,
        )
    )

    application.add_handler(
        CommandHandler(
            "export",
            admin_export,
        )
    )

    # ========================================================
    # CALLBACKS
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )

    # ========================================================
    # GENERAL TEXT - FAQAT PRIVATE CHAT
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            text_router,
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Telegram polling boshlandi..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
