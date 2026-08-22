# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# Python 3.11+
# python-telegram-bot 22.3
# PostgreSQL / asyncpg
#
# 1 BOT = CLIENT + MASTER + ADMIN
# MASTER GROUP = NEW ORDERS
#
# IMPORTANT:
# This file DOES NOT use old "users", "tele", "telegram_id"
# columns. It creates its own tables automatically.
# ============================================================

import os
import logging
import asyncio
from datetime import datetime

import asyncpg

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatType
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
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi")

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | USTA24 | %(message)s",
)

logger = logging.getLogger("USTA24")

db_pool = None

# ============================================================
# STATES
# ============================================================

STATE = {}

# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "🪑 Mebel yig‘ish",
    "🛠 Mebel ta’mirlash",
    "🍳 Oshxona mebeli",
    "🚪 Shkaf / kupe",
    "🛏 Krovat",
    "🪑 Stol / stul",
    "🚚 Mebel tashish",
    "🏠 Ko‘chirish xizmati",
    "⚡ Elektr xizmati",
    "💧 Santexnika",
    "🔥 Gaz xizmati",
    "🚪 Eshik ta’miri",
    "🔨 Boshqa xizmat",
]

# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        # USERS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usta24_users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                username TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'client',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # MASTERS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usta24_masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                phone TEXT DEFAULT '',
                services TEXT DEFAULT '',
                area TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                rating NUMERIC(3,2) NOT NULL DEFAULT 0,
                rating_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ORDERS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usta24_orders (
                id BIGSERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL,
                client_name TEXT NOT NULL DEFAULT '',
                phone TEXT DEFAULT '',
                service TEXT NOT NULL DEFAULT '',
                address TEXT DEFAULT '',
                description TEXT DEFAULT '',
                order_time TEXT DEFAULT '',
                photo_file_ids TEXT DEFAULT '',
                result_photo_ids TEXT DEFAULT '',
                master_id BIGINT,
                master_name TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                payment_method TEXT NOT NULL DEFAULT 'cash_after',
                emergency BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """)

        # RATINGS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usta24_ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                client_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                comment TEXT DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # SERVICES
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS usta24_services (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)

        for service in SERVICES:
            await conn.execute(
                """
                INSERT INTO usta24_services(name)
                VALUES($1)
                ON CONFLICT(name) DO NOTHING
                """,
                service,
            )

    logger.info("PostgreSQL initialized successfully")


# ============================================================
# DB HELPERS
# ============================================================

async def db_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM usta24_users
            WHERE telegram_id=$1
            """,
            telegram_id,
        )


async def db_create_user(
    telegram_id: int,
    full_name: str,
    username: str = "",
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usta24_users
                (telegram_id, full_name, username)
            VALUES
                ($1, $2, $3)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                full_name=EXCLUDED.full_name,
                username=EXCLUDED.username
            """,
            telegram_id,
            full_name,
            username,
        )


async def db_set_phone(telegram_id: int, phone: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE usta24_users
            SET phone=$1
            WHERE telegram_id=$2
            """,
            phone,
            telegram_id,
        )


async def is_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status
            FROM usta24_masters
            WHERE telegram_id=$1
            """,
            telegram_id,
        )

        return bool(row and row["status"] == "approved")


async def is_pending_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status
            FROM usta24_masters
            WHERE telegram_id=$1
            """,
            telegram_id,
        )

        return bool(row and row["status"] == "pending")


async def db_create_master(
    telegram_id: int,
    full_name: str,
    phone: str,
    services: str,
    area: str,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usta24_masters
                (telegram_id, full_name, phone, services, area, status)
            VALUES
                ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                full_name=EXCLUDED.full_name,
                phone=EXCLUDED.phone,
                services=EXCLUDED.services,
                area=EXCLUDED.area,
                status='pending'
            """,
            telegram_id,
            full_name,
            phone,
            services,
            area,
        )

        await conn.execute(
            """
            UPDATE usta24_users
            SET phone=$1
            WHERE telegram_id=$2
            """,
            phone,
            telegram_id,
        )


async def db_get_pending_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM usta24_masters
            WHERE status='pending'
            ORDER BY created_at ASC
            """
        )


async def db_get_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM usta24_masters
            WHERE telegram_id=$1
            """,
            telegram_id,
        )


async def db_approve_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE usta24_masters
            SET status='approved'
            WHERE telegram_id=$1
            """,
            telegram_id,
        )

        await conn.execute(
            """
            UPDATE usta24_users
            SET role='master'
            WHERE telegram_id=$1
            """,
            telegram_id,
        )


async def db_reject_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE usta24_masters
            SET status='rejected'
            WHERE telegram_id=$1
            """,
            telegram_id,
        )


# ============================================================
# ORDER DATABASE
# ============================================================

async def db_create_order(
    client_id: int,
    client_name: str,
    phone: str,
    service: str,
    address: str,
    description: str,
    order_time: str,
    photo_file_ids: str,
    emergency: bool = False,
):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO usta24_orders
            (
                client_id,
                client_name,
                phone,
                service,
                address,
                description,
                order_time,
                photo_file_ids,
                emergency
            )
            VALUES
            ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            RETURNING *
            """,
            client_id,
            client_name,
            phone,
            service,
            address,
            description,
            order_time,
            photo_file_ids,
            emergency,
        )


async def db_get_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM usta24_orders
            WHERE id=$1
            """,
            order_id,
        )


async def db_accept_order(
    order_id: int,
    master_id: int,
    master_name: str,
):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET
                master_id=$2,
                master_name=$3,
                status='accepted',
                accepted_at=NOW()
            WHERE id=$1
              AND status='new'
            RETURNING *
            """,
            order_id,
            master_id,
            master_name,
        )


async def db_reject_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='new',
                master_id=NULL,
                master_name=''
            WHERE id=$1
              AND status='new'
            RETURNING *
            """,
            order_id,
        )


async def db_start_order(order_id: int, master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET
                status='in_progress',
                started_at=NOW()
            WHERE id=$1
              AND master_id=$2
              AND status='accepted'
            RETURNING *
            """,
            order_id,
            master_id,
        )


async def db_complete_order(
    order_id: int,
    master_id: int,
    result_photo_ids: str,
):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET
                status='completed',
                result_photo_ids=$3,
                completed_at=NOW()
            WHERE id=$1
              AND master_id=$2
              AND status='in_progress'
            RETURNING *
            """,
            order_id,
            master_id,
            result_photo_ids,
        )


async def db_cancel_order(order_id: int, client_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='cancelled'
            WHERE id=$1
              AND client_id=$2
              AND status IN ('new','accepted')
            RETURNING *
            """,
            order_id,
            client_id,
        )


async def db_client_orders(client_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM usta24_orders
            WHERE client_id=$1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            client_id,
        )


async def db_master_orders(master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM usta24_orders
            WHERE master_id=$1
            ORDER BY created_at DESC
            LIMIT 30
            """,
            master_id,
        )


async def db_statistics():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status='new') AS new,
                COUNT(*) FILTER (WHERE status='accepted') AS accepted,
                COUNT(*) FILTER (WHERE status='in_progress') AS progress,
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='cancelled') AS cancelled
            FROM usta24_orders
            """
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
            ["🎁 Bonuslar", "🏷 Chegirmalar"],
            ["📞 Dispetcher", "🚨 24/7 Shoshilinch"],
            ["👨‍🔧 Usta bo‘lish", "⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )


def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar", "📋 Mening faol buyurtmalarim"],
            ["⏳ Buyurtmalar tarixi", "💰 Ish haqi"],
            ["⭐ Reytingim", "📊 Ish statistikasi"],
            ["📅 Ish jadvalim", "🛠 Xizmatlarim"],
            ["📍 Ish hududim", "🎁 Usta bonuslari"],
            ["🔔 Bildirishnomalar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcher", "🚨 24/7"],
            ["⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "👨‍🔧 Ustalar"],
            ["🛠 Buyurtmalar", "⭐ Reytinglar"],
            ["💰 To‘lovlar", "🎁 Bonuslar"],
            ["🏷 Chegirmalar", "🛠 Xizmat turlari"],
            ["📊 Statistika", "📢 E'lonlar"],
            ["📸 Galereya", "📞 Dispetcher"],
            ["⚙️ Sozlamalar", "🚨 24/7"],
        ],
        resize_keyboard=True,
    )


def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 2):
        row = SERVICES[i:i + 2]
        rows.append(row)

    rows.append(["⬅️ Orqaga"])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def master_registration_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📞 Telefon yuborish", request_contact=True)],
            ["❌ Bekor qilish"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user = update.effective_user

    await db_create_user(
        user.id,
        user.full_name or "",
        user.username or "",
    )

    STATE.pop(user.id, None)

    # ADMIN ALWAYS HAS ADMIN MENU
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 <b>USTA 24 ADMIN</b>\n\n"
            "Админ панелига хуш келибсиз.",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return

    # APPROVED MASTER
    if await is_master(user.id):
        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 — USTA PANEL</b>\n\n"
            "Сиз тасдиқланган устасиз.",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    # CLIENT
    await update.message.reply_text(
        "👋 <b>USTA 24 ANDIJON</b>\n\n"
        "Хуш келибсиз!\n"
        "Хизмат керак бўлса, буюртма беринг.",
        parse_mode="HTML",
        reply_markup=client_menu(),
    )


# ============================================================
# MASTER REGISTRATION
# ============================================================

async def start_master_registration(update, context):
    user = update.effective_user

    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 Сиз админсиз.",
            reply_markup=admin_menu(),
        )
        return

    if await is_master(user.id):
        await update.message.reply_text(
            "👨‍🔧 Сиз аллақачон тасдиқланган устасиз.",
            reply_markup=master_menu(),
        )
        return

    if await is_pending_master(user.id):
        await update.message.reply_text(
            "⏳ Аризангиз админ тасдиғини кутяпти.",
            reply_markup=client_menu(),
        )
        return

    STATE[user.id] = {
        "type": "master_register",
        "step": "phone",
        "data": {},
    }

    await update.message.reply_text(
        "👨‍🔧 <b>USTA BO‘LISH</b>\n\n"
        "Аввало телефон рақамингизни юборинг.",
        parse_mode="HTML",
        reply_markup=master_registration_keyboard(),
    )


# ============================================================
# CLIENT ORDER
# ============================================================

async def start_order(update, context):
    user = update.effective_user

    STATE[user.id] = {
        "type": "order",
        "step": "service",
        "data": {
            "photos": [],
        },
    }

    await update.message.reply_text(
        "🛒 <b>ЯНГИ БУЮРТМА</b>\n\n"
        "Хизмат турини танланг:",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )


async def handle_order_state(update, context):
    user = update.effective_user
    state = STATE.get(user.id)

    if not state:
        return False

    text = update.message.text or ""

    # --------------------------------------------------------
    # MASTER REGISTRATION
    # --------------------------------------------------------

    if state["type"] == "master_register":

        if text == "❌ Bekor qilish":
            STATE.pop(user.id, None)

            await update.message.reply_text(
                "❌ Ариза бекор қилинди.",
                reply_markup=client_menu(),
            )
            return True

        if state["step"] == "phone":

            if update.message.contact:
                phone = update.message.contact.phone_number
            else:
                phone = text.strip()

            state["data"]["phone"] = phone
            state["step"] = "services"

            await update.message.reply_text(
                "🛠 Қайси хизматларни бажарасиз?\n\n"
                "Масалан:\n"
                "Электр, сантехника, мебель...",
            )
            return True

        if state["step"] == "services":
            state["data"]["services"] = text
            state["step"] = "area"

            await update.message.reply_text(
                "📍 Ишлайдиган ҳудудингизни ёзинг.\n"
                "Масалан: Andijon shahar"
            )
            return True

        if state["step"] == "area":

            state["data"]["area"] = text

            await db_create_master(
                user.id,
                user.full_name or "",
                state["data"]["phone"],
                state["data"]["services"],
                state["data"]["area"],
            )

            STATE.pop(user.id, None)

            await update.message.reply_text(
                "✅ <b>Ариза қабул қилинди!</b>\n\n"
                "Админ тасдиғини кутинг.",
                parse_mode="HTML",
                reply_markup=client_menu(),
            )

            # SEND TO ADMIN
            if ADMIN_ID:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "✅ TASDIQLASH",
                            callback_data=f"master_approve:{user.id}",
                        ),
                        InlineKeyboardButton(
                            "❌ RAD ETISH",
                            callback_data=f"master_reject:{user.id}",
                        ),
                    ]
                ])

                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "👨‍🔧 <b>YANGI USTA ARIZASI!</b>\n\n"
                        f"👤 Ism: {user.full_name}\n"
                        f"🆔 Telegram ID: {user.id}\n"
                        f"📞 Telefon: {state['data']['phone']}\n"
                        f"🛠 Xizmatlar: {state['data']['services']}\n"
                        f"📍 Hudud: {state['data']['area']}"
                    ),
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )

            return True

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    if state["type"] == "order":

        if text == "❌ Bekor qilish":
            STATE.pop(user.id, None)

            await update.message.reply_text(
                "❌ Буюртма бекор қилинди.",
                reply_markup=client_menu(),
            )
            return True

        if state["step"] == "service":

            if text not in SERVICES:
                await update.message.reply_text(
                    "Илтимос, хизмат турини тугмалардан танланг.",
                    reply_markup=service_keyboard(),
                )
                return True

            state["data"]["service"] = text
            state["step"] = "phone"

            await update.message.reply_text(
                "📞 Телефон рақамингизни юборинг.",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [
                            KeyboardButton(
                                "📞 Telefon yuborish",
                                request_contact=True,
                            )
                        ],
                        ["❌ Bekor qilish"],
                    ],
                    resize_keyboard=True,
                ),
            )
            return True

        if state["step"] == "phone":

            if update.message.contact:
                phone = update.message.contact.phone_number
            else:
                phone = text.strip()

            state["data"]["phone"] = phone
            state["step"] = "address"

            await db_set_phone(user.id, phone)

            await update.message.reply_text(
                "📍 Манзилни ёзинг:"
            )
            return True

        if state["step"] == "address":

            state["data"]["address"] = text
            state["step"] = "description"

            await update.message.reply_text(
                "📝 Муаммони қисқача ёзинг.\n\n"
                "Масалан: розетка ишламаяпти."
            )
            return True

        if state["step"] == "description":

            state["data"]["description"] = text
            state["step"] = "time"

            await update.message.reply_text(
                "🕐 Қачон боришимиз керак?\n\n"
                "Масалан: 10:30 ёки ҳозир."
            )
            return True

        if state["step"] == "time":

            state["data"]["time"] = text
            state["step"] = "photo"

            await update.message.reply_text(
                "📸 Муаммо расмини юборишингиз мумкин.\n\n"
                "Расм бўлмаса, <b>⏭ O‘tkazish</b>ни босинг.",
                parse_mode="HTML",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["⏭ O‘tkazish"],
                        ["❌ Bekor qilish"],
                    ],
                    resize_keyboard=True,
                ),
            )
            return True

        if state["step"] == "photo":

            if update.message.photo:
                file_id = update.message.photo[-1].file_id
                state["data"]["photos"].append(file_id)

                await update.message.reply_text(
                    "📸 Расм қабул қилинди.\n"
                    "Яна расм юборишингиз мумкин ёки:",
                    reply_markup=ReplyKeyboardMarkup(
                        [
                            ["✅ Tasdiqlash"],
                            ["⏭ O‘tkazish"],
                            ["❌ Bekor qilish"],
                        ],
                        resize_keyboard=True,
                    ),
                )
                return True

            if text == "⏭ O‘tkazish" or text == "✅ Tasdiqlash":

                await show_order_confirmation(update)
                return True

        if state["step"] == "confirm":

            if text == "❌ Bekor qilish":
                STATE.pop(user.id, None)

                await update.message.reply_text(
                    "❌ Буюртма бекор қилинди.",
                    reply_markup=client_menu(),
                )
                return True

            if text == "✏️ O‘zgartirish":
                state["step"] = "service"

                await update.message.reply_text(
                    "🛠 Хизматни қайта танланг:",
                    reply_markup=service_keyboard(),
                )
                return True

            if text == "✅ BUYURTMA YUBORISH":

                await create_and_send_order(
                    update,
                    context,
                    state,
                )
                return True

    return False


# ============================================================
# ORDER CONFIRMATION
# ============================================================

async def show_order_confirmation(update):
    user = update.effective_user
    state = STATE[user.id]
    data = state["data"]

    state["step"] = "confirm"

    photos = data.get("photos", [])

    text = (
        "📋 <b>БУЮРТМА ТЕКШИРУВИ</b>\n\n"
        f"👤 {user.full_name}\n"
        f"📞 {data.get('phone','')}\n"
        f"🛠 {data.get('service','')}\n"
        f"📍 {data.get('address','')}\n"
        f"📝 {data.get('description','')}\n"
        f"🕐 {data.get('time','')}\n"
        f"📸 Расмлар: {len(photos)} та\n\n"
        "💵 Тўлов: НАҚД — ИШДАН КЕЙИН\n\n"
        "Ҳаммаси тўғрими?"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ BUYURTMA YUBORISH"],
                ["✏️ O‘zgartirish", "❌ Bekor qilish"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# CREATE + SEND ORDER TO MASTER GROUP
# ============================================================

async def create_and_send_order(update, context, state):
    user = update.effective_user
    data = state["data"]

    order = await db_create_order(
        client_id=user.id,
        client_name=user.full_name or "",
        phone=data.get("phone", ""),
        service=data.get("service", ""),
        address=data.get("address", ""),
        description=data.get("description", ""),
        order_time=data.get("time", ""),
        photo_file_ids=",".join(data.get("photos", [])),
        emergency=False,
    )

    order_id = order["id"]

    STATE.pop(user.id, None)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ QABUL QILISH",
                callback_data=f"order_accept:{order_id}",
            ),
            InlineKeyboardButton(
                "❌ RAD ETISH",
                callback_data=f"order_reject:{order_id}",
            ),
        ]
    ])

    group_text = (
        "🆕 <b>YANGI BUYURTMA!</b>\n\n"
        f"🆔 №{order_id}\n"
        f"👤 {order['client_name']}\n"
        f"📞 {order['phone']}\n"
        f"🛠 {order['service']}\n"
        f"📍 {order['address']}\n"
        f"📝 {order['description']}\n"
        f"🕐 {order['order_time']}\n"
        f"📸 Муаммо расми: "
        f"{'✅' if order['photo_file_ids'] else '❌'}\n\n"
        "💵 <b>Тўлов: НАҚД — ИШДАН КЕЙИН</b>\n\n"
        "⏳ <b>УСТА КУТИЛМОҚДА</b>"
    )

    # SEND TO MASTERS GROUP
    if MASTERS_GROUP_ID:

        sent = await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=group_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        # SEND PHOTOS
        if order["photo_file_ids"]:
            ids = [
                x.strip()
                for x in order["photo_file_ids"].split(",")
                if x.strip()
            ]

            for file_id in ids:
                try:
                    await context.bot.send_photo(
                        chat_id=MASTERS_GROUP_ID,
                        photo=file_id,
                    )
                except Exception:
                    logger.exception("Could not send order photo")

    # ADMIN NOTIFICATION
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🆕 <b>YANGI BUYURTMA №{order_id}</b>\n\n"
                    f"👤 {order['client_name']}\n"
                    f"📞 {order['phone']}\n"
                    f"🛠 {order['service']}\n"
                    f"📍 {order['address']}"
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Admin notification failed")

    await update.message.reply_text(
        f"✅ <b>Буюртмангиз қабул қилинди!</b>\n\n"
        f"🆔 Буюртма №{order_id}\n\n"
        "👨‍🔧 Усталарга юборилди.\n"
        "Уста қабул қилганда сизга хабар берамиз.",
        parse_mode="HTML",
        reply_markup=client_menu(),
    )


# ============================================================
# CALLBACKS
# ============================================================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    user = query.from_user
    data = query.data or ""

    # ========================================================
    # MASTER APPROVAL
    # ========================================================

    if data.startswith("master_approve:"):

        if user.id != ADMIN_ID:
            await query.answer(
                "❌ Бу фақат админ учун.",
                show_alert=True,
            )
            return

        master_id = int(data.split(":")[1])

        master = await db_get_master(master_id)

        if not master:
            await query.edit_message_text(
                "❌ Уста топилмади."
            )
            return

        await db_approve_master(master_id)

        await query.edit_message_text(
            "✅ <b>USTA TASDIQLANDI</b>\n\n"
            f"👤 {master['full_name']}\n"
            f"📞 {master['phone']}",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=master_id,
                text=(
                    "🎉 <b>Табриклаймиз!</b>\n\n"
                    "Сизнинг уста сифатидаги аризангиз тасдиқланди.\n\n"
                    "Энди /start босинг."
                ),
                parse_mode="HTML",
                reply_markup=master_menu(),
            )
        except Exception:
            logger.exception("Could not notify approved master")

        return

    if data.startswith("master_reject:"):

        if user.id != ADMIN_ID:
            await query.answer(
                "❌ Бу фақат админ учун.",
                show_alert=True,
            )
            return

        master_id = int(data.split(":")[1])

        master = await db_get_master(master_id)

        if not master:
            await query.edit_message_text(
                "❌ Уста топилмади."
            )
            return

        await db_reject_master(master_id)

        await query.edit_message_text(
            "❌ <b>USTA ARIZASI RAD ETILDI</b>",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=master_id,
                text=(
                    "❌ Уста бўлиш аризангиз рад этилди.\n\n"
                    "Қўшимча маълумот учун диспетчерга мурожаат қилинг."
                ),
            )
        except Exception:
            pass

        return

    # ========================================================
    # ORDER ACCEPT
    # ========================================================

    if data.startswith("order_accept:"):

        if user.id == ADMIN_ID:
            pass
        elif not await is_master(user.id):
            await query.answer(
                "❌ Фақат тасдиқланган уста қабул қилиши мумкин.",
                show_alert=True,
            )
            return

        order_id = int(data.split(":")[1])

        order = await db_get_order(order_id)

        if not order:
            await query.answer(
                "Буюртма топилмади.",
                show_alert=True,
            )
            return

        if order["status"] != "new":
            await query.answer(
                "⚠️ Бу буюртмани бошқа уста олган ёки ҳолати ўзгарган.",
                show_alert=True,
            )
            return

        master = await db_get_master(user.id)

        if not master:
            await query.answer(
                "Уста маълумоти топилмади.",
                show_alert=True,
            )
            return

        accepted = await db_accept_order(
            order_id,
            user.id,
            master["full_name"],
        )

        if not accepted:
            await query.answer(
                "⚠️ Буюртмани қабул қилиб бўлмади.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "✅ <b>BUYURTMA QABUL QILINDI</b>\n\n"
            f"🆔 №{order_id}\n"
            f"👨‍🔧 Usta: {master['full_name']}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address']}\n\n"
            "🔧 Ишни бошлаш учун тугмани босинг.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔧 ISHNI BOSHLASH",
                        callback_data=f"order_start:{order_id}",
                    )
                ]
            ]),
        )

        # CLIENT
        try:
            await context.bot.send_message(
                chat_id=order["client_id"],
                text=(
                    "✅ <b>Буюртмангиз қабул қилинди!</b>\n\n"
                    f"🆔 №{order_id}\n"
                    f"👨‍🔧 Уста: {master['full_name']}\n"
                    f"🛠 {order['service']}\n"
                    f"📍 {order['address']}\n\n"
                    "Уста ишни бошлаши кутилмоқда."
                ),
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Client notification failed")

        return

    # ========================================================
    # ORDER REJECT
    # ========================================================

    if data.startswith("order_reject:"):

        if not await is_master(user.id):
            await query.answer(
                "❌ Фақат тасдиқланган уста.",
                show_alert=True,
            )
            return

        order_id = int(data.split(":")[1])

        order = await db_get_order(order_id)

        if not order or order["status"] != "new":
            await query.answer(
                "⚠️ Буюртма аллақачон ўзгарган.",
                show_alert=True,
            )
            return

        await db_reject_order(order_id)

        await query.answer("❌ Рад этилди")

        await query.edit_message_text(
            f"❌ <b>№{order_id} rad etildi.</b>\n\n"
            "🔄 Бошқа усталар кўриши мумкин.",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=order["client_id"],
                text=(
                    f"ℹ️ Буюртма №{order_id}ни бир уста рад этди.\n\n"
                    "🔄 Бошқа усталардан бири қабул қилиши кутилмоқда."
                ),
            )
        except Exception:
            pass

        # IMPORTANT:
        # send order again to group with fresh buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ QABUL QILISH",
                    callback_data=f"order_accept:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ RAD ETISH",
                    callback_data=f"order_reject:{order_id}",
                ),
            ]
        ])

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=(
                "🔄 <b>BUYURTMA QAYTA OCHILDI</b>\n\n"
                f"🆔 №{order_id}\n"
                f"👤 {order['client_name']}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}\n\n"
                "👨‍🔧 Бошқа уста қабул қилиши мумкин."
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        return

    # ========================================================
    # START ORDER
    # ========================================================

    if data.startswith("order_start:"):

        if not await is_master(user.id):
            await query.answer(
                "❌ Фақат уста.",
                show_alert=True,
            )
            return

        order_id = int(data.split(":")[1])

        order = await db_get_order(order_id)

        if not order:
            return

        started = await db_start_order(
            order_id,
            user.id,
        )

        if not started:
            await query.answer(
                "⚠️ Буюртма ҳолати ўзгарган.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            "🔧 <b>ISH BOSHLANDI</b>\n\n"
            f"🆔 №{order_id}\n"
            f"👨‍🔧 {order['master_name']}\n"
            f"🛠 {order['service']}\n\n"
            "Иш тугаганда натижа расмини юборинг.",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=order["client_id"],
                text=(
                    "🔧 <b>Иш бошланди!</b>\n\n"
                    f"🆔 №{order_id}\n"
                    f"👨‍🔧 Уста: {order['master_name']}\n"
                    f"🛠 {order['service']}"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

        STATE[user.id] = {
            "type": "complete_order",
            "step": "photo",
            "order_id": order_id,
            "photos": [],
        }

        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "📸 <b>Иш натижаси расмини юборинг.</b>\n\n"
                "Камида 1 та расм мажбурий."
            ),
            parse_mode="HTML",
        )

        return


# ============================================================
# MASTER RESULT PHOTO
# ============================================================

async def handle_master_photo(update, context):

    user = update.effective_user
    state = STATE.get(user.id)

    if not state:
        return False

    if state.get("type") != "complete_order":
        return False

    if state.get("step") != "photo":
        return False

    if not update.message.photo:
        await update.message.reply_text(
            "📸 Илтимос, иш натижасининг расмини юборинг."
        )
        return True

    file_id = update.message.photo[-1].file_id

    state["photos"].append(file_id)

    await update.message.reply_text(
        "📸 Расм қабул қилинди.\n\n"
        "Яна расм юборишингиз мумкин.\n"
        "Тайёр бўлса:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ Ishni yakunlash"],
                ["📸 Yana rasm"],
            ],
            resize_keyboard=True,
        ),
    )

    state["step"] = "finish"

    return True


# ============================================================
# FINISH ORDER
# ============================================================

async def finish_order(update, context):

    user = update.effective_user
    state = STATE.get(user.id)

    if not state:
        return False

    if state.get("type") != "complete_order":
        return False

    if update.message.text != "✅ Ishni yakunlash":
        return False

    photos = state.get("photos", [])

    if not photos:
        await update.message.reply_text(
            "❌ Камида 1 та натижа расми мажбурий."
        )
        return True

    order_id = state["order_id"]

    order = await db_get_order(order_id)

    if not order:
        STATE.pop(user.id, None)
        return True

    completed = await db_complete_order(
        order_id,
        user.id,
        ",".join(photos),
    )

    if not completed:
        await update.message.reply_text(
            "⚠️ Буюртмани якунлаб бўлмади."
        )
        return True

    STATE.pop(user.id, None)

    await update.message.reply_text(
        f"✅ <b>№{order_id} буюртма якунланди!</b>\n\n"
        "💵 Тўлов: НАҚД — ИШДАН КЕЙИН\n"
        "⭐ Мижоздан рейтинг кутилмоқда.",
        parse_mode="HTML",
        reply_markup=master_menu(),
    )

    # CLIENT
    try:
        await context.bot.send_message(
            chat_id=order["client_id"],
            text=(
                "✅ <b>ИШ ЯКУНЛАНДИ!</b>\n\n"
                f"🆔 №{order_id}\n"
                f"👨‍🔧 Уста: {order['master_name']}\n"
                f"🛠 {order['service']}\n\n"
                "💵 Тўлов: НАҚД — ИШДАН КЕЙИН\n\n"
                "⭐ Илтимос, устага рейтинг беринг."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⭐ REYTING QOLDIRISH",
                        callback_data=f"rating:{order_id}",
                    )
                ]
            ]),
        )

        # RESULT PHOTOS
        for file_id in photos:
            await context.bot.send_photo(
                chat_id=order["client_id"],
                photo=file_id,
                caption=f"📸 №{order_id} — иш натижаси",
            )

    except Exception:
        logger.exception("Could not send result to client")

    # ADMIN
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "✅ <b>ISH YAKUNLANDI</b>\n\n"
                    f"🆔 №{order_id}\n"
                    f"👤 {order['client_name']}\n"
                    f"👨‍🔧 {order['master_name']}\n"
                    f"🛠 {order['service']}\n"
                    f"📸 Натижа расмлари: {len(photos)} та"
                ),
                parse_mode="HTML",
            )

            for file_id in photos:
                await context.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=file_id,
                )

        except Exception:
            logger.exception("Admin completion notification failed")

    return True


# ============================================================
# RATING
# ============================================================

async def rating_callback(update, context):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    if not query.data.startswith("rating:"):
        return

    order_id = int(query.data.split(":")[1])

    order = await db_get_order(order_id)

    if not order or order["client_id"] != user.id:
        await query.answer(
            "❌ Бу буюртма сизники эмас.",
            show_alert=True,
        )
        return

    if order["status"] != "completed":
        await query.answer(
            "⚠️ Буюртма ҳали якунланмаган.",
            show_alert=True,
        )
        return

    STATE[user.id] = {
        "type": "rating",
        "order_id": order_id,
    }

    await query.message.reply_text(
        "⭐ <b>Устага баҳо беринг:</b>",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["⭐ 1", "⭐ 2", "⭐ 3"],
                ["⭐ 4", "⭐ 5"],
            ],
            resize_keyboard=True,
        ),
    )


async def handle_rating(update, context):

    user = update.effective_user
    state = STATE.get(user.id)

    if not state or state.get("type") != "rating":
        return False

    text = update.message.text or ""

    if not text.startswith("⭐"):
        return False

    try:
        rating = int(text.replace("⭐", "").strip())
    except Exception:
        return True

    order_id = state["order_id"]

    order = await db_get_order(order_id)

    if not order or not order["master_id"]:
        STATE.pop(user.id, None)
        return True

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO usta24_ratings
                (order_id, client_id, master_id, rating)
            VALUES
                ($1,$2,$3,$4)
            """,
            order_id,
            user.id,
            order["master_id"],
            rating,
        )

        await conn.execute(
            """
            UPDATE usta24_masters
            SET
                rating =
                    (
                        COALESCE(rating,0) * COALESCE(rating_count,0)
                        + $2
                    )
                    /
                    (COALESCE(rating_count,0) + 1),
                rating_count=COALESCE(rating_count,0)+1
            WHERE telegram_id=$1
            """,
            order["master_id"],
            rating,
        )

    STATE.pop(user.id, None)

    await update.message.reply_text(
        f"⭐ <b>Рейтинг қабул қилинди!</b>\n\n"
        f"Сиз {rating}/5 баҳо бердингиз.\n"
        "Раҳмат!",
        parse_mode="HTML",
        reply_markup=client_menu(),
    )

    try:
        await context.bot.send_message(
            chat_id=order["master_id"],
            text=(
                "⭐ <b>Мижоз сизга рейтинг қолдирди!</b>\n\n"
                f"🆔 №{order_id}\n"
                f"⭐ Баҳо: {rating}/5"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    return True


# ============================================================
# CLIENT MENU
# ============================================================

async def client_menu_handler(update, context):

    text = update.message.text
    user = update.effective_user

    if text == "🛒 Buyurtma berish":
        await start_order(update, context)
        return True

    if text == "👨‍🔧 Usta bo‘lish":
        await start_master_registration(update, context)
        return True

    if text == "📋 Mening buyurtmalarim":

        orders = await db_client_orders(user.id)

        if not orders:
            await update.message.reply_text(
                "📋 Сизда ҳали буюртмалар йўқ.",
                reply_markup=client_menu(),
            )
            return True

        text_out = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"

        for order in orders[:10]:
            text_out += (
                f"🆔 №{order['id']}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}\n"
                f"📌 Ҳолат: {order['status']}\n\n"
            )

        await update.message.reply_text(
            text_out,
            parse_mode="HTML",
            reply_markup=client_menu(),
        )
        return True

    if text == "🔍 Buyurtma holati":

        orders = await db_client_orders(user.id)

        if not orders:
            await update.message.reply_text(
                "Буюртма топилмади.",
                reply_markup=client_menu(),
            )
            return True

        order = orders[0]

        await update.message.reply_text(
            f"🔍 <b>Сўнгги буюртма</b>\n\n"
            f"🆔 №{order['id']}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address']}\n"
            f"📌 Ҳолат: {order['status']}\n"
            f"👨‍🔧 Уста: {order['master_name'] or 'Кутилмоқда'}",
            parse_mode="HTML",
            reply_markup=client_menu(),
        )
        return True

    if text == "❌ Bekor qilish":

        orders = await db_client_orders(user.id)

        active = [
            x for x in orders
            if x["status"] in ("new", "accepted")
        ]

        if not active:
            await update.message.reply_text(
                "Бекор қилиш мумкин бўлган буюртма йўқ.",
                reply_markup=client_menu(),
            )
            return True

        order = active[0]

        await db_cancel_order(
            order["id"],
            user.id,
        )

        await update.message.reply_text(
            f"❌ №{order['id']} буюртма бекор қилинди.",
            reply_markup=client_menu(),
        )
        return True

    if text == "📞 Dispetcher":
        await update.message.reply_text(
            f"📞 <b>Диспетчер</b>\n\n"
            f"{DISPATCHER_PHONE}\n"
            "🕐 24/7",
            parse_mode="HTML",
            reply_markup=client_menu(),
        )
        return True

    if text == "🚨 24/7 Shoshilinch":
        await update.message.reply_text(
            "🚨 <b>24/7 ШОШИЛИНЧ РЕЖИМ</b>\n\n"
            "Дарҳол ёрдам керакми?\n\n"
            "📞 Диспетчер:\n"
            f"{DISPATCHER_PHONE}\n\n"
            "💵 Тўлов: фақат нақд, ишдан кейин.",
            parse_mode="HTML",
            reply_markup=client_menu(),
        )
        return True

    if text == "🎁 Bonuslar":
        await update.message.reply_text(
            "🎁 Ҳозирча бонус тизими тайёрланмоқда.",
            reply_markup=client_menu(),
        )
        return True

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 Ҳозирча акциялар йўқ.",
            reply_markup=client_menu(),
        )
        return True

    if text == "👨‍🔧 Mening ustalarim":
        await update.message.reply_text(
            "👨‍🔧 Сизга хизмат кўрсатган усталар шу ерда кўрсатилади.",
            reply_markup=client_menu(),
        )
        return True

    if text == "⭐ Reytingim":
        await update.message.reply_text(
            "⭐ Сизнинг рейтингларингиз буюртмалар тарихи билан боғланган.",
            reply_markup=client_menu(),
        )
        return True

    if text == "📝 Sharh qoldirish":
        await update.message.reply_text(
            "📝 Шарҳ қолдириш учун аввал якунланган буюртмангиз бўлиши керак.",
            reply_markup=client_menu(),
        )
        return True

    if text == "🔁 Qayta buyurtma":
        await start_order(update, context)
        return True

    return False


# ============================================================
# MASTER MENU
# ============================================================

async def master_menu_handler(update, context):

    user = update.effective_user
    text = update.message.text

    if not await is_master(user.id):
        return False

    if text == "🆕 Yangi buyurtmalar":

        await update.message.reply_text(
            "🆕 Янги буюртмалар усталар группасига автоматик юборилади.\n\n"
            "Группага кириб, [✅ QABUL QILISH] тугмасини босинг.",
            reply_markup=master_menu(),
        )
        return True

    if text == "📋 Mening faol buyurtmalarim":

        orders = await db_master_orders(user.id)

        active = [
            x for x in orders
            if x["status"] in ("accepted", "in_progress")
        ]

        if not active:
            await update.message.reply_text(
                "📋 Фаол буюртмалар йўқ.",
                reply_markup=master_menu(),
            )
            return True

        out = "📋 <b>ФАОЛ БУЮРТМАЛАР</b>\n\n"

        for o in active:
            out += (
                f"🆔 №{o['id']}\n"
                f"👤 {o['client_name']}\n"
                f"🛠 {o['service']}\n"
                f"📍 {o['address']}\n"
                f"📌 {o['status']}\n\n"
            )

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "⏳ Buyurtmalar tarixi":

        orders = await db_master_orders(user.id)

        completed = [
            x for x in orders
            if x["status"] == "completed"
        ]

        if not completed:
            await update.message.reply_text(
                "⏳ Якунланган буюртмалар йўқ.",
                reply_markup=master_menu(),
            )
            return True

        out = "⏳ <b>ТАРИХ</b>\n\n"

        for o in completed:
            out += (
                f"🆔 №{o['id']} — "
                f"{o['service']}\n"
            )

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "⭐ Reytingim":

        master = await db_get_master(user.id)

        await update.message.reply_text(
            f"⭐ <b>РЕЙТИНГИМ</b>\n\n"
            f"⭐ Рейтинг: {master['rating']}\n"
            f"👥 Баолар: {master['rating_count']}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "💰 Ish haqi":
        await update.message.reply_text(
            "💰 Иш ҳақи: буюртма якунлангандан кейин ҳисобланади.\n"
            "Тўлов тури — нақд.",
            reply_markup=master_menu(),
        )
        return True

    if text == "📊 Ish statistikasi":

        orders = await db_master_orders(user.id)

        total = len(orders)
        completed = len([
            x for x in orders
            if x["status"] == "completed"
        ])

        await update.message.reply_text(
            f"📊 <b>ИШ СТАТИСТИКАСИ</b>\n\n"
            f"📋 Жами: {total}\n"
            f"✅ Якунланган: {completed}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 Диспетчер: {DISPATCHER_PHONE}\n"
            "🕐 24/7",
            reply_markup=master_menu(),
        )
        return True

    if text == "🚨 24/7":

        await update.message.reply_text(
            f"🚨 <b>24/7 ШОШИЛИНЧ</b>\n\n"
            f"📞 {DISPATCHER_PHONE}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "📅 Ish jadvalim":
        await update.message.reply_text(
            "📅 Иш жадвали ҳозирча стандарт режимда.",
            reply_markup=master_menu(),
        )
        return True

    if text == "🛠 Xizmatlarim":

        master = await db_get_master(user.id)

        await update.message.reply_text(
            f"🛠 <b>ХИЗМАТЛАРИМ</b>\n\n"
            f"{master['services']}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    if text == "📍 Ish hududim":

        master = await db_get_master(user.id)

        await update.message.reply_text(
            f"📍 Иш ҳудуди:\n{master['area']}",
            reply_markup=master_menu(),
        )
        return True

    if text == "🎁 Usta bonuslari":
        await update.message.reply_text(
            "🎁 Бонус тизими тайёрланмоқда.",
            reply_markup=master_menu(),
        )
        return True

    if text == "🔔 Bildirishnomalar":
        await update.message.reply_text(
            "🔔 Билдиришномалар ёқилган.",
            reply_markup=master_menu(),
        )
        return True

    if text == "🏆 Ustalar reytingi":

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT full_name, rating, rating_count
                FROM usta24_masters
                WHERE status='approved'
                ORDER BY rating DESC, rating_count DESC
                LIMIT 10
                """
            )

        if not rows:
            text_out = "🏆 Ҳозирча усталар йўқ."
        else:
            text_out = "🏆 <b>TOP 10 USTALAR</b>\n\n"

            for i, row in enumerate(rows, 1):
                text_out += (
                    f"{i}. 👨‍🔧 {row['full_name']} — "
                    f"⭐ {row['rating']}\n"
                )

        await update.message.reply_text(
            text_out,
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return True

    return False


# ============================================================
# ADMIN MENU
# ============================================================

async def admin_menu_handler(update, context):

    user = update.effective_user

    if user.id != ADMIN_ID:
        return False

    text = update.message.text

    if text == "👨‍🔧 Ustalar":

        masters = await db_get_pending_masters()

        async with db_pool.acquire() as conn:
            approved = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM usta24_masters
                WHERE status='approved'
                """
            )

        out = (
            "👨‍🔧 <b>USTALAR</b>\n\n"
            f"✅ Тасдиқланган: {approved}\n"
            f"⏳ Кутиб турган: {len(masters)}"
        )

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )

        # show pending
        for master in masters[:10]:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ TASDIQLASH",
                        callback_data=f"master_approve:{master['telegram_id']}",
                    ),
                    InlineKeyboardButton(
                        "❌ RAD",
                        callback_data=f"master_reject:{master['telegram_id']}",
                    ),
                ]
            ])

            await update.message.reply_text(
                "👨‍🔧 <b>КУТИБ ТУРГАН УСТА</b>\n\n"
                f"👤 {master['full_name']}\n"
                f"📞 {master['phone']}\n"
                f"🛠 {master['services']}\n"
                f"📍 {master['area']}",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        return True

    if text == "🛠 Buyurtmalar":

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, COUNT(*) AS count
                FROM usta24_orders
                GROUP BY status
                ORDER BY status
                """
            )

        if not rows:
            out = "🛠 Буюртмалар ҳали йўқ."
        else:
            out = "🛠 <b>BUYURTMALAR</b>\n\n"

            for row in rows:
                out += (
                    f"📌 {row['status']}: "
                    f"{row['count']}\n"
                )

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "📊 Statistika":

        s = await db_statistics()

        await update.message.reply_text(
            "📊 <b>USTA 24 STATISTIKA</b>\n\n"
            f"📋 Жами: {s['total']}\n"
            f"🆕 Янги: {s['new']}\n"
            f"✅ Қабул қилинган: {s['accepted']}\n"
            f"🔧 Жараёнда: {s['progress']}\n"
            f"🏁 Якунланган: {s['completed']}\n"
            f"❌ Бекор қилинган: {s['cancelled']}",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "👥 Foydalanuvchilar":

        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM usta24_users
                """
            )

        await update.message.reply_text(
            f"👥 <b>ФОЙДАЛАНУВЧИЛАР</b>\n\n"
            f"Жами: {count}",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 <b>ДИСПЕТЧЕР</b>\n\n"
            f"{DISPATCHER_PHONE}\n"
            "🕐 24/7",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "🚨 24/7":

        await update.message.reply_text(
            f"🚨 <b>24/7 РЕЖИМ</b>\n\n"
            f"Диспетчер: {DISPATCHER_PHONE}",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "🛠 Xizmat turlari":

        out = "🛠 <b>ХИЗМАТ ТУРЛАРИ</b>\n\n"

        for service in SERVICES:
            out += f"• {service}\n"

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "💰 To‘lovlar":

        await update.message.reply_text(
            "💰 <b>ТЎЛОВ ТИЗИМИ</b>\n\n"
            "✅ Фақат нақд\n"
            "✅ Иш тугагач 100%\n\n"
            "❌ Click\n"
            "❌ Payme\n"
            "❌ Uzcard online\n"
            "❌ Visa/Mastercard\n"
            "❌ Аванс",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    if text == "🎁 Bonuslar":
        await update.message.reply_text(
            "🎁 Бонус тизими.",
            reply_markup=admin_menu(),
        )
        return True

    if text == "🏷 Chegirmalar":
        await update.message.reply_text(
            "🏷 Акциялар ва чегирмалар.",
            reply_markup=admin_menu(),
        )
        return True

    if text == "📢 E'lonlar":
        await update.message.reply_text(
            "📢 Эълонлар бўлими.",
            reply_markup=admin_menu(),
        )
        return True

    if text == "📸 Galereya":
        await update.message.reply_text(
            "📸 Галерея бўлими.",
            reply_markup=admin_menu(),
        )
        return True

    if text == "⭐ Reytinglar":

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT full_name, rating, rating_count
                FROM usta24_masters
                WHERE status='approved'
                ORDER BY rating DESC
                LIMIT 10
                """
            )

        out = "⭐ <b>USTALAR REYTINGI</b>\n\n"

        for i, row in enumerate(rows, 1):
            out += (
                f"{i}. {row['full_name']} — "
                f"⭐ {row['rating']} "
                f"({row['rating_count']} та)\n"
            )

        await update.message.reply_text(
            out,
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return True

    return False


# ============================================================
# MAIN MESSAGE ROUTER
# ============================================================

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user = update.effective_user

    # MASTER PHOTO / FINISH
    if await handle_master_photo(update, context):
        return

    if await finish_order(update, context):
        return

    # RATING
    if await handle_rating(update, context):
        return

    # ACTIVE STATES
    if user.id in STATE:

        if await handle_order_state(update, context):
            return

    # ADMIN FIRST
    if user.id == ADMIN_ID:

        if await admin_menu_handler(update, context):
            return

        return

    # MASTER SECOND
    if await is_master(user.id):

        if await master_menu_handler(update, context):
            return

        return

    # CLIENT
    if await client_menu_handler(update, context):
        return

    # UNKNOWN TEXT
    await update.message.reply_text(
        "Илтимос, менюдан танланг.",
        reply_markup=client_menu(),
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):

    logger.exception(
        "Unhandled exception:",
        exc_info=context.error,
    )

    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ Texnik xatolik yuz berdi. "
                "Iltimos, qayta urinib ko‘ring."
            )
    except Exception:
        pass


# ============================================================
# STARTUP
# ============================================================

async def post_init(application: Application):

    await init_db()

    logger.info("========================================")
    logger.info("USTA 24 ANDIJON STARTED")
    logger.info("ADMIN_ID=%s", ADMIN_ID)
    logger.info("DISPATCHER_ID=%s", DISPATCHER_ID)
    logger.info("MASTERS_GROUP_ID=%s", MASTERS_GROUP_ID)
    logger.info("DATABASE=PostgreSQL")
    logger.info("========================================")


async def post_shutdown(application: Application):

    global db_pool

    if db_pool:
        await db_pool.close()

    logger.info("Database pool closed")


# ============================================================
# APPLICATION
# ============================================================

def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CallbackQueryHandler(
            callbacks,
            pattern=r"^(master_|order_)"
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            rating_callback,
            pattern=r"^rating:"
        )
    )

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.ALL,
            message_router,
        )
    )

    application.add_error_handler(error_handler)

    logger.info("Bot polling started")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
