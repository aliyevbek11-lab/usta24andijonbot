#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA24 DISPATCHER
🏗️ ONE BOT = CLIENT + MASTER + ADMIN + DISPETCHER
🐘 PostgreSQL with asyncpg
📸 Rasmlar bilan to'liq ishlaydi
"""

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

DISPATCHER_PHONE = os.getenv("DISPATCHER_PHONE", "+9987706900003")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL topilmadi!")

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | USTA24_DISPATCHER | %(message)s",
)

logger = logging.getLogger("USTA24_DISPATCHER")

db_pool = None

# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "🛠 Sanitariya",
    "⚡ Elektr",
    "🔧 Mexanik",
    "🧹 Tozalash",
    "📦 Yuk tashish",
    "🪑 Mebel yig'ish",
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
                service_sub TEXT DEFAULT '',
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
                completed_at TIMESTAMPTZ,
                cancelled_at TIMESTAMPTZ,
                cancel_reason TEXT DEFAULT ''
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

    logger.info("✅ PostgreSQL initialized successfully")


# ============================================================
# DB HELPERS
# ============================================================

async def db_user(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM usta24_users WHERE telegram_id=$1",
            telegram_id,
        )

async def db_create_user(telegram_id: int, full_name: str, username: str = ""):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usta24_users (telegram_id, full_name, username)
            VALUES ($1, $2, $3)
            ON CONFLICT(telegram_id)
            DO UPDATE SET full_name=EXCLUDED.full_name, username=EXCLUDED.username
            """,
            telegram_id, full_name, username,
        )

async def db_set_phone(telegram_id: int, phone: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE usta24_users SET phone=$1 WHERE telegram_id=$2",
            phone, telegram_id,
        )

async def db_update_role(telegram_id: int, role: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE usta24_users SET role=$1 WHERE telegram_id=$2",
            role, telegram_id,
        )

# ---------- MASTERS ----------

async def is_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM usta24_masters WHERE telegram_id=$1",
            telegram_id,
        )
        return bool(row and row["status"] == "approved")

async def is_pending_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM usta24_masters WHERE telegram_id=$1",
            telegram_id,
        )
        return bool(row and row["status"] == "pending")

async def db_create_master(telegram_id: int, full_name: str, phone: str, services: str, area: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usta24_masters (telegram_id, full_name, phone, services, area, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT(telegram_id)
            DO UPDATE SET full_name=$2, phone=$3, services=$4, area=$5, status='pending'
            """,
            telegram_id, full_name, phone, services, area,
        )
        await db_set_phone(telegram_id, phone)

async def db_get_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM usta24_masters WHERE telegram_id=$1",
            telegram_id,
        )

async def db_get_master_by_id(master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM usta24_masters WHERE id=$1",
            master_id,
        )

async def db_get_pending_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_masters WHERE status='pending' ORDER BY created_at ASC",
        )

async def db_get_all_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_masters WHERE status='approved' ORDER BY rating DESC",
        )

async def db_approve_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE usta24_masters SET status='approved' WHERE telegram_id=$1",
            telegram_id,
        )
        await db_update_role(telegram_id, 'master')

async def db_reject_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE usta24_masters SET status='rejected' WHERE telegram_id=$1",
            telegram_id,
        )

async def db_delete_master(telegram_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM usta24_masters WHERE telegram_id=$1",
            telegram_id,
        )
        await db_update_role(telegram_id, 'client')

# ---------- ORDERS ----------

async def db_create_order(
    client_id: int,
    client_name: str,
    phone: str,
    service: str,
    service_sub: str,
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
            (client_id, client_name, phone, service, service_sub, address,
             description, order_time, photo_file_ids, emergency)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING *
            """,
            client_id, client_name, phone, service, service_sub,
            address, description, order_time, photo_file_ids, emergency,
        )

async def db_get_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM usta24_orders WHERE id=$1",
            order_id,
        )

async def db_get_orders_by_status(status: str):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_orders WHERE status=$1 ORDER BY created_at DESC",
            status,
        )

async def db_get_all_orders():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_orders ORDER BY created_at DESC LIMIT 50",
        )

async def db_client_orders(client_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_orders WHERE client_id=$1 ORDER BY created_at DESC LIMIT 20",
            client_id,
        )

async def db_master_orders(master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM usta24_orders WHERE master_id=$1 ORDER BY created_at DESC LIMIT 30",
            master_id,
        )

async def db_accept_order(order_id: int, master_id: int, master_name: str):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET master_id=$2, master_name=$3, status='accepted', accepted_at=NOW()
            WHERE id=$1 AND status='new'
            RETURNING *
            """,
            order_id, master_id, master_name,
        )

async def db_reject_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='new', master_id=NULL, master_name=''
            WHERE id=$1 AND status='new'
            RETURNING *
            """,
            order_id,
        )

async def db_start_order(order_id: int, master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='in_progress', started_at=NOW()
            WHERE id=$1 AND master_id=$2 AND status='accepted'
            RETURNING *
            """,
            order_id, master_id,
        )

async def db_complete_order(order_id: int, master_id: int, result_photo_ids: str):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='completed', result_photo_ids=$3, completed_at=NOW()
            WHERE id=$1 AND master_id=$2 AND status='in_progress'
            RETURNING *
            """,
            order_id, master_id, result_photo_ids,
        )

async def db_cancel_order(order_id: int, client_id: int, reason: str = ""):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            UPDATE usta24_orders
            SET status='cancelled', cancelled_at=NOW(), cancel_reason=$3
            WHERE id=$1 AND client_id=$2 AND status IN ('new','accepted')
            RETURNING *
            """,
            order_id, client_id, reason,
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
            ["📞 Dispetcher", "🚨 Shoshilinch"],
            ["👨‍🔧 Usta bo'lish", "⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )

def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar", "📋 Mening buyurtmalarim"],
            ["✅ Qabul qilish", "🔧 Ishni boshlash"],
            ["✅ Ishni yakunlash", "❌ Rad etish"],
            ["👥 Mijozlarim", "📊 Statistika"],
            ["💰 Daromad", "⭐ Reytingim"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )

def dispetcher_menu():
    return ReplyKeyboardMarkup(
        [
            ["📨 Yangi buyurtmalar", "📋 Barcha buyurtmalar"],
            ["👨‍🔧 Ustalar", "🔗 Ustaga biriktirish"],
            ["📊 Statistika", "📄 Hisobot"],
            ["⚙️ Sozlamalar", "📞 Admin"],
        ],
        resize_keyboard=True,
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Ustalar", "📋 Barcha buyurtmalar"],
            ["👥 Mijozlar", "📊 Statistika"],
            ["📄 Hisobot", "💰 Narxlar"],
            ["💬 Xabar tarqatish", "🎟 Kuponlar"],
            ["📸 Rasmlar arxivi", "⚙️ Sozlamalar"],
            ["📞 Dispetcher", "🚨 Shoshilinch"],
        ],
        resize_keyboard=True,
    )

def service_keyboard():
    rows = []
    for i in range(0, len(SERVICES), 2):
        row = SERVICES[i:i + 2]
        rows.append(row)
    rows.append(["⬅️ Orqaga"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)

def service_sub_keyboard(service: str):
    subs = {
        "🛠 Sanitariya": ["🚽 Hojatxona", "🚿 Lavabo", "🔧 Quvur", "🧹 Kanalizatsiya"],
        "⚡ Elektr": ["💡 Chiroq", "🔌 Rozetka", "🔧 Sim", "⚡ Avtomat"],
        "🔧 Mexanik": ["🚪 Eshik", "🪟 Deraza", "🪑 Mebel", "❄️ Konditsioner"],
        "🧹 Tozalash": ["🏠 Uy", "🏢 Ofis", "🧶 Gilam", "🪟 Deraza"],
        "📦 Yuk tashish": ["📦 Kichik", "📦 O'rta", "📦 Katta", "🏠 Ko'chirish"],
    }
    keys = subs.get(service, ["📋 Boshqa"])
    rows = [[KeyboardButton(k)] for k in keys]
    rows.append([KeyboardButton("⬅️ Orqaga")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)

def time_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🔴 Hozir", "🟡 Bugun kechqurun"],
            ["🟢 Ertaga ertalab", "📆 Boshqa vaqt"],
            ["⬅️ Orqaga"],
        ],
        resize_keyboard=True,
    )

def confirm_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["✅ Tasdiqlash", "❌ Bekor qilish"],
        ],
        resize_keyboard=True,
    )

def cancel_reason_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["⏳ Uzoq kutish", "💰 Narx baland"],
            ["🕐 Vaqt mos emas", "🔄 Boshqa usta topdim"],
            ["❌ Endi kerak emas", "📝 Boshqa sabab"],
            ["⬅️ Orqaga"],
        ],
        resize_keyboard=True,
    )

def rating_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["⭐ 1", "⭐ 2", "⭐ 3"],
            ["⭐ 4", "⭐ 5"],
        ],
        resize_keyboard=True,
    )

def skip_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["⏭ O'tkazib yuborish"],
        ],
        resize_keyboard=True,
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["⬅️ Orqaga"],
        ],
        resize_keyboard=True,
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

    # ADMIN
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 <b>USTA24 DISPATCHER – ADMIN</b>\n\n"
            "Админ панелига хуш келибсиз.",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return

    # DISPETCHER
    if user.id == DISPATCHER_ID:
        await update.message.reply_text(
            "📞 <b>USTA24 DISPATCHER – DISPETCHER</b>\n\n"
            "Диспетчер панелига хуш келибсиз.",
            parse_mode="HTML",
            reply_markup=dispetcher_menu(),
        )
        return

    # APPROVED MASTER
    if await is_master(user.id):
        await update.message.reply_text(
            "👨‍🔧 <b>USTA24 DISPATCHER – USTA</b>\n\n"
            "Сиз тасдиқланган устасиз.",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    # CLIENT
    await update.message.reply_text(
        "👋 <b>USTA24 DISPATCHER</b>\n\n"
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

    if user.id == ADMIN_ID or user.id == DISPATCHER_ID:
        await update.message.reply_text("❌ Сиз админ ёки диспетчерсиз.", reply_markup=admin_menu())
        return

    if await is_master(user.id):
        await update.message.reply_text("👨‍🔧 Сиз аллақачон тасдиқланган устасиз.", reply_markup=master_menu())
        return

    if await is_pending_master(user.id):
        await update.message.reply_text("⏳ Аризангиз админ тасдиғини кутяпти.", reply_markup=client_menu())
        return

    context.user_data['master_reg'] = {'step': 'phone'}

    await update.message.reply_text(
        "👨‍🔧 <b>USTA BO'LISH</b>\n\n"
        "Аввало телефон рақамингизни юборинг.",
        parse_mode="HTML",
        reply_markup=master_registration_keyboard(),
    )

# ============================================================
# ORDER CONVERSATION (SODDA)
# ============================================================

async def start_order(update, context):
    user = update.effective_user

    context.user_data['order'] = {
        'step': 'service',
        'photos': [],
        'result_photos': [],
    }

    await update.message.reply_text(
        "🛒 <b>ЯНГИ БУЮРТМА</b>\n\n"
        "1️⃣ Хизмат турини танланг:",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )

async def handle_order(update, context):
    user = update.effective_user
    order = context.user_data.get('order')

    if not order:
        return False

    text = update.message.text or ""
    step = order.get('step')

    # ---------- SERVICE ----------
    if step == 'service':
        if text == "⬅️ Orqaga":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

        if text not in SERVICES:
            await update.message.reply_text("Илтимос, хизмат турини тугмалардан танланг.", reply_markup=service_keyboard())
            return True

        order['service'] = text
        order['step'] = 'service_sub'

        await update.message.reply_text(
            f"2️⃣ {text} хизмат турини аниқланг:",
            reply_markup=service_sub_keyboard(text),
        )
        return True

    # ---------- SERVICE SUB ----------
    if step == 'service_sub':
        if text == "⬅️ Orqaga":
            order['step'] = 'service'
            await update.message.reply_text("1️⃣ Хизмат турини танланг:", reply_markup=service_keyboard())
            return True

        order['service_sub'] = text
        order['step'] = 'phone'

        await update.message.reply_text(
            "3️⃣ 📞 Телефон рақамингизни юборинг.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📞 Telefon yuborish", request_contact=True)], ["❌ Bekor qilish"]],
                resize_keyboard=True,
            ),
        )
        return True

    # ---------- PHONE ----------
    if step == 'phone':
        if text == "❌ Bekor qilish":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = text.strip()

        order['phone'] = phone
        order['step'] = 'address'

        await db_set_phone(user.id, phone)

        await update.message.reply_text(
            "4️⃣ 📍 Манзилни ёзинг:",
            reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True),
        )
        return True

    # ---------- ADDRESS ----------
    if step == 'address':
        if text == "❌ Bekor qilish":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

        order['address'] = text
        order['step'] = 'description'

        await update.message.reply_text(
            "5️⃣ 📝 Муаммони қисқача ёзинг:",
            reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True),
        )
        return True

    # ---------- DESCRIPTION ----------
    if step == 'description':
        if text == "❌ Bekor qilish":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

        order['description'] = text
        order['step'] = 'time'

        await update.message.reply_text(
            "6️⃣ 🕐 Қачон керак?",
            reply_markup=time_keyboard(),
        )
        return True

    # ---------- TIME ----------
    if step == 'time':
        if text == "⬅️ Orqaga":
            order['step'] = 'description'
            await update.message.reply_text("5️⃣ 📝 Муаммони ёзинг:", reply_markup=ReplyKeyboardMarkup([["❌ Bekor qilish"]], resize_keyboard=True))
            return True

        order['time'] = text
        order['step'] = 'photo'

        await update.message.reply_text(
            "7️⃣ 📸 Муаммо расмини юборинг (ихтиёрий):",
            reply_markup=skip_keyboard(),
        )
        return True

    # ---------- PHOTO ----------
    if step == 'photo':
        if text == "⏭ O'tkazib yuborish":
            await show_order_confirm(update, context)
            return True

        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            order['photos'].append(file_id)

            await update.message.reply_text(
                f"✅ Расм қабул қилинди! ({len(order['photos'])} та)\n"
                "Яна расм юборинг ёки '✅ Tasdiqlash'ни босинг.",
                reply_markup=ReplyKeyboardMarkup(
                    [["✅ Tasdiqlash"], ["⏭ O'tkazib yuborish"], ["❌ Bekor qilish"]],
                    resize_keyboard=True,
                ),
            )
            return True

        if text == "✅ Tasdiqlash":
            await show_order_confirm(update, context)
            return True

        if text == "❌ Bekor qilish":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

    # ---------- CONFIRM ----------
    if step == 'confirm':
        if text == "❌ Bekor qilish":
            context.user_data.pop('order', None)
            await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
            return True

        if text == "✏️ O'zgartirish":
            order['step'] = 'service'
            await update.message.reply_text("1️⃣ Хизмат турини қайта танланг:", reply_markup=service_keyboard())
            return True

        if text == "✅ BUYURTMA YUBORISH":
            await create_and_send_order(update, context)
            return True

    return False

async def show_order_confirm(update, context):
    user = update.effective_user
    order = context.user_data.get('order')

    if not order:
        return

    order['step'] = 'confirm'

    text = (
        "📋 <b>БУЮРТМА ТЕКШИРУВИ</b>\n\n"
        f"👤 {user.full_name}\n"
        f"📞 {order.get('phone', '')}\n"
        f"🛠 {order.get('service', '')} – {order.get('service_sub', '')}\n"
        f"📍 {order.get('address', '')}\n"
        f"📝 {order.get('description', '')}\n"
        f"🕐 {order.get('time', '')}\n"
        f"📸 Расмлар: {len(order.get('photos', []))} та\n\n"
        "✅ Ҳаммаси тўғрими?"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ BUYURTMA YUBORISH"],
                ["✏️ O'zgartirish", "❌ Bekor qilish"],
            ],
            resize_keyboard=True,
        ),
    )

async def create_and_send_order(update, context):
    user = update.effective_user
    order = context.user_data.get('order')

    if not order:
        return

    db_order = await db_create_order(
        client_id=user.id,
        client_name=user.full_name or "",
        phone=order.get('phone', ''),
        service=order.get('service', ''),
        service_sub=order.get('service_sub', ''),
        address=order.get('address', ''),
        description=order.get('description', ''),
        order_time=order.get('time', ''),
        photo_file_ids=",".join(order.get('photos', [])),
        emergency=False,
    )

    order_id = db_order['id']

    context.user_data.pop('order', None)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ QABUL QILISH", callback_data=f"order_accept:{order_id}"),
            InlineKeyboardButton("❌ RAD ETISH", callback_data=f"order_reject:{order_id}"),
        ],
        [InlineKeyboardButton("👨‍🔧 Usta biriktirish", callback_data=f"order_assign:{order_id}")],
        [InlineKeyboardButton("🖼 Rasmlarni ko'rish", callback_data=f"view_images:{order_id}")],
    ])

    group_text = (
        "🆕 <b>YANGI BUYURTMA!</b>\n\n"
        f"🆔 №{order_id}\n"
        f"👤 {db_order['client_name']}\n"
        f"📞 {db_order['phone']}\n"
        f"🛠 {db_order['service']} – {db_order['service_sub']}\n"
        f"📍 {db_order['address']}\n"
        f"📝 {db_order['description']}\n"
        f"🕐 {db_order['order_time']}\n"
        f"📸 Расм: {'✅' if db_order['photo_file_ids'] else '❌'}\n\n"
        "💵 <b>Тўлов: НАҚД — ИШДАН КЕЙИН</b>"
    )

    # MASTERS GROUP
    if MASTERS_GROUP_ID:
        sent = await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=group_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        if db_order['photo_file_ids']:
            ids = [x.strip() for x in db_order['photo_file_ids'].split(',') if x.strip()]
            for file_id in ids:
                try:
                    await context.bot.send_photo(chat_id=MASTERS_GROUP_ID, photo=file_id)
                except:
                    pass

    # ADMIN
    if ADMIN_ID:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 <b>Янги буюртма №{order_id}</b>\n👤 {db_order['client_name']}\n🛠 {db_order['service']}",
            parse_mode="HTML",
        )

    # DISPETCHER
    if DISPATCHER_ID:
        await context.bot.send_message(
            chat_id=DISPATCHER_ID,
            text=f"🆕 <b>Янги буюртма №{order_id}</b>\n👤 {db_order['client_name']}\n🛠 {db_order['service']}\n📍 {db_order['address']}",
            parse_mode="HTML",
        )

    await update.message.reply_text(
        f"✅ <b>Буюртмангиз қабул қилинди!</b>\n\n🆔 №{order_id}\n👨‍🔧 Усталарга юборилди.",
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

    # ---------- MASTER APPROVE ----------
    if data.startswith("master_approve:"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Фақат админ!", show_alert=True)
            return

        master_id = int(data.split(":")[1])
        await db_approve_master(master_id)

        master = await db_get_master(master_id)

        await query.edit_message_text(
            f"✅ <b>Уста тасдиқланди!</b>\n\n👤 {master['full_name']}",
            parse_mode="HTML",
        )

        try:
            await context.bot.send_message(
                chat_id=master_id,
                text="🎉 <b>Табриклаймиз!</b>\n\nСиз уста сифатида тасдиқландингиз.\nЭнди /start босинг.",
                parse_mode="HTML",
                reply_markup=master_menu(),
            )
        except:
            pass
        return

    # ---------- MASTER REJECT ----------
    if data.startswith("master_reject:"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Фақат админ!", show_alert=True)
            return

        master_id = int(data.split(":")[1])
        await db_reject_master(master_id)

        await query.edit_message_text("❌ <b>Уста ради этди!</b>", parse_mode="HTML")
        return

    # ---------- ORDER ACCEPT ----------
    if data.startswith("order_accept:"):
        order_id = int(data.split(":")[1])

        if user.id != ADMIN_ID and user.id != DISPATCHER_ID and not await is_master(user.id):
            await query.answer("❌ Фақат уста, админ ёки диспетчер!", show_alert=True)
            return

        order = await db_get_order(order_id)

        if not order or order["status"] != "new":
            await query.answer("⚠️ Буюртма ҳолати ўзгарган!", show_alert=True)
            return

        master = await db_get_master(user.id) if await is_master(user.id) else None
        master_name = master['full_name'] if master else "Уста"

        accepted = await db_accept_order(order_id, user.id, master_name)

        if accepted:
            await query.edit_message_text(
                f"✅ <b>Буюртма қабул қилинди!</b>\n🆔 №{order_id}\n👨‍🔧 {master_name}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔧 ISHNI BOSHLASH", callback_data=f"order_start:{order_id}")]
                ]),
            )

            try:
                await context.bot.send_message(
                    chat_id=order["client_id"],
                    text=f"✅ <b>Буюртмангиз қабул қилинди!</b>\n🆔 №{order_id}\n👨‍🔧 Уста: {master_name}",
                    parse_mode="HTML",
                )
            except:
                pass
        return

    # ---------- ORDER REJECT ----------
    if data.startswith("order_reject:"):
        order_id = int(data.split(":")[1])

        if user.id != ADMIN_ID and user.id != DISPATCHER_ID and not await is_master(user.id):
            await query.answer("❌ Фақат уста, админ ёки диспетчер!", show_alert=True)
            return

        await db_reject_order(order_id)

        await query.edit_message_text(f"❌ <b>№{order_id} ради этди!</b>", parse_mode="HTML")

        # Qayta jo'natish
        order = await db_get_order(order_id)
        if order and MASTERS_GROUP_ID:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ QABUL QILISH", callback_data=f"order_accept:{order_id}"),
                    InlineKeyboardButton("❌ RAD ETISH", callback_data=f"order_reject:{order_id}"),
                ]
            ])
            await context.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=f"🔄 <b>Буюртма №{order_id} қайта очилди!</b>",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        return

    # ---------- ORDER START ----------
    if data.startswith("order_start:"):
        order_id = int(data.split(":")[1])

        if not await is_master(user.id):
            await query.answer("❌ Фақат уста!", show_alert=True)
            return

        started = await db_start_order(order_id, user.id)

        if started:
            await query.edit_message_text(
                f"🔧 <b>Иш бошланди!</b>\n🆔 №{order_id}",
                parse_mode="HTML",
            )

            order = await db_get_order(order_id)
            if order:
                await context.bot.send_message(
                    chat_id=order["client_id"],
                    text=f"🔧 <b>Иш бошланди!</b>\n🆔 №{order_id}",
                    parse_mode="HTML",
                )
        return

    # ---------- ORDER ASSIGN ----------
    if data.startswith("order_assign:"):
        order_id = int(data.split(":")[1])

        if user.id != ADMIN_ID and user.id != DISPATCHER_ID:
            await query.answer("❌ Фақат админ ёки диспетчер!", show_alert=True)
            return

        masters = await db_get_all_masters()

        if not masters:
            await query.answer("❌ Усталар йўқ!", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([])
        for master in masters:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    f"👨‍🔧 {master['full_name']} (⭐{master['rating']})",
                    callback_data=f"assign_to:{order_id}:{master['telegram_id']}"
                )
            ])

        await query.edit_message_text(
            f"👨‍🔧 <b>Устани танланг</b>\n🆔 №{order_id}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        return

    # ---------- ASSIGN TO MASTER ----------
    if data.startswith("assign_to:"):
        parts = data.split(":")
        order_id = int(parts[1])
        master_id = int(parts[2])

        if user.id != ADMIN_ID and user.id != DISPATCHER_ID:
            await query.answer("❌ Фақат админ ёки диспетчер!", show_alert=True)
            return

        master = await db_get_master(master_id)

        if not master:
            await query.answer("❌ Уста топилмади!", show_alert=True)
            return

        accepted = await db_accept_order(order_id, master_id, master['full_name'])

        if accepted:
            await query.edit_message_text(
                f"✅ <b>Уста бириктирилди!</b>\n🆔 №{order_id}\n👨‍🔧 {master['full_name']}",
                parse_mode="HTML",
            )

            await context.bot.send_message(
                chat_id=master_id,
                text=f"🆕 <b>Янги буюртма!</b>\n🆔 №{order_id}\n👤 {accepted['client_name']}\n🛠 {accepted['service']}\n📍 {accepted['address']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ QABUL QILISH", callback_data=f"order_accept:{order_id}")],
                    [InlineKeyboardButton("🔧 ISHNI BOSHLASH", callback_data=f"order_start:{order_id}")]
                ]),
            )
        return

    # ---------- VIEW IMAGES ----------
    if data.startswith("view_images:"):
        order_id = int(data.split(":")[1])
        order = await db_get_order(order_id)

        if not order:
            await query.edit_message_text("❌ Буюртма топилмади!")
            return

        text = f"🖼 <b>Буюртма №{order_id} расмлари</b>\n\n"
        text += f"📸 Муаммо расми: {'✅' if order['photo_file_ids'] else '❌'}\n"
        text += f"📸 Натижа расми: {'✅' if order['result_photo_ids'] else '❌'}"

        await query.edit_message_text(text, parse_mode="HTML")
        return

# ============================================================
# MAIN MESSAGE ROUTER
# ============================================================

async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user
    text = update.message.text or ""

    # ---------- ORDER ----------
    if await handle_order(update, context):
        return

    # ---------- ADMIN ----------
    if user.id == ADMIN_ID:
        await admin_handler(update, context)
        return

    # ---------- DISPETCHER ----------
    if user.id == DISPATCHER_ID:
        await dispetcher_handler(update, context)
        return

    # ---------- MASTER ----------
    if await is_master(user.id):
        await master_handler(update, context)
        return

    # ---------- CLIENT ----------
    await client_handler(update, context)

# ============================================================
# CLIENT HANDLER
# ============================================================

async def client_handler(update, context):
    user = update.effective_user
    text = update.message.text or ""

    if text == "🛒 Buyurtma berish":
        await start_order(update, context)
        return

    if text == "👨‍🔧 Usta bo'lish":
        await start_master_registration(update, context)
        return

    if text == "📋 Mening buyurtmalarim":
        orders = await db_client_orders(user.id)
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=client_menu())
            return

        out = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"
        for o in orders[:10]:
            status_emoji = {"new": "🆕", "accepted": "✅", "in_progress": "🔧", "completed": "✅", "cancelled": "❌"}.get(o['status'], "🆕")
            out += f"{status_emoji} №{o['id']} – {o['service']} – {o['status']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=client_menu())
        return

    if text == "🔍 Buyurtma holati":
        await update.message.reply_text(
            "🔍 <b>Buyurtma holati</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text.isdigit():
        order = await db_get_order(int(text))
        if order:
            status_text = {
                "new": "🆕 Янги (диспетчер текширади)",
                "accepted": "✅ Қабул қилинди",
                "in_progress": "🔧 Иш жараёнида",
                "completed": "✅ Тугатилди",
                "cancelled": "❌ Бекор қилинди"
            }.get(order['status'], "🆕 Янги")

            await update.message.reply_text(
                f"🔍 <b>Буюртма №{order['id']}</b>\n\n"
                f"📌 Ҳолат: {status_text}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}\n"
                f"👨‍🔧 Уста: {order['master_name'] or 'Кутилмоқда'}",
                parse_mode="HTML",
            )
        return

    if text == "❌ Bekor qilish":
        await update.message.reply_text(
            "❌ <b>Бекор қилиш</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(f"📞 <b>Диспетчер</b>\n\n{DISPATCHER_PHONE}\n🕐 24/7", parse_mode="HTML", reply_markup=client_menu())
        return

    if text == "🚨 Shoshilinch":
        await update.message.reply_text(
            f"🚨 <b>ШОШИЛИНЧ</b>\n\n📞 {DISPATCHER_PHONE}\n🕐 24/7",
            parse_mode="HTML",
            reply_markup=client_menu(),
        )
        return

    if text == "⭐ Reytingim":
        await update.message.reply_text("⭐ Рейтинг бўлими.", reply_markup=client_menu())
        return

    if text == "📝 Sharh qoldirish":
        await update.message.reply_text("📝 Шарҳ бўлими.", reply_markup=client_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=client_menu())

# ============================================================
# MASTER HANDLER
# ============================================================

async def master_handler(update, context):
    user = update.effective_user
    text = update.message.text or ""

    if text == "🆕 Yangi buyurtmalar":
        orders = await db_get_orders_by_status("new")
        if not orders:
            await update.message.reply_text("🆕 Янги буюртмалар йўқ.", reply_markup=master_menu())
            return

        out = "🆕 <b>ЯНГИ БУЮРТМАЛАР</b>\n\n"
        for o in orders[:5]:
            out += f"🆔 №{o['id']} – {o['service']} – {o['client_name']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=master_menu())
        return

    if text == "📋 Mening buyurtmalarim":
        orders = await db_master_orders(user.id)
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=master_menu())
            return

        out = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"
        for o in orders[:10]:
            status_emoji = {"new": "🆕", "accepted": "✅", "in_progress": "🔧", "completed": "✅", "cancelled": "❌"}.get(o['status'], "🆕")
            out += f"{status_emoji} №{o['id']} – {o['service']} – {o['status']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=master_menu())
        return

    if text == "✅ Qabul qilish":
        await update.message.reply_text(
            "✅ <b>Қабул қилиш</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text.isdigit():
        order_id = int(text)
        order = await db_get_order(order_id)

        if order and order["status"] == "new":
            master = await db_get_master(user.id)
            accepted = await db_accept_order(order_id, user.id, master['full_name'])

            if accepted:
                await update.message.reply_text(
                    f"✅ <b>Буюртма №{order_id} қабул қилинди!</b>",
                    parse_mode="HTML",
                    reply_markup=master_menu(),
                )
                return

        await update.message.reply_text("❌ Буюртмани қабул қилиб бўлмади.", reply_markup=master_menu())
        return

    if text == "🔧 Ishni boshlash":
        await update.message.reply_text(
            "🔧 <b>Ишни бошлаш</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text == "✅ Ishni yakunlash":
        await update.message.reply_text(
            "✅ <b>Ишни якунлаш</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text == "❌ Rad etish":
        await update.message.reply_text(
            "❌ <b>Рад этиш</b>\n\n🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text == "📊 Statistika":
        orders = await db_master_orders(user.id)
        total = len(orders)
        completed = len([o for o in orders if o["status"] == "completed"])

        await update.message.reply_text(
            f"📊 <b>СТАТИСТИКА</b>\n\n"
            f"📋 Жами: {total}\n"
            f"✅ Якунланган: {completed}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    if text == "💰 Daromad":
        orders = await db_master_orders(user.id)
        completed = [o for o in orders if o["status"] == "completed"]
        income = len(completed) * 100000

        await update.message.reply_text(
            f"💰 <b>ДАРОМАД</b>\n\n"
            f"📊 Якунланган: {len(completed)} та\n"
            f"💰 Даромад: {income:,} so'm",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    if text == "⭐ Reytingim":
        master = await db_get_master(user.id)
        await update.message.reply_text(
            f"⭐ <b>РЕЙТИНГИМ</b>\n\n"
            f"⭐ Рейтинг: {master['rating']}\n"
            f"👥 Баҳолар: {master['rating_count']}",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(f"📞 Диспетчер: {DISPATCHER_PHONE}", reply_markup=master_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=master_menu())

# ============================================================
# DISPETCHER HANDLER
# ============================================================

async def dispetcher_handler(update, context):
    text = update.message.text or ""

    if text == "📨 Yangi buyurtmalar":
        orders = await db_get_orders_by_status("new")
        if not orders:
            await update.message.reply_text("📨 Янги буюртмалар йўқ.", reply_markup=dispetcher_menu())
            return

        out = "📨 <b>ЯНГИ БУЮРТМАЛАР</b>\n\n"
        for o in orders[:10]:
            out += f"🆔 №{o['id']} – {o['service']} – {o['client_name']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=dispetcher_menu())
        return

    if text == "📋 Barcha buyurtmalar":
        orders = await db_get_all_orders()
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=dispetcher_menu())
            return

        out = "📋 <b>БАРЧА БУЮРТМАЛАР</b>\n\n"
        for o in orders[:20]:
            out += f"🆔 №{o['id']} – {o['service']} – {o['status']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=dispetcher_menu())
        return

    if text == "👨‍🔧 Ustalar":
        masters = await db_get_all_masters()
        if not masters:
            await update.message.reply_text("👨‍🔧 Усталар йўқ.", reply_markup=dispetcher_menu())
            return

        out = "👨‍🔧 <b>УСТАЛАР</b>\n\n"
        for m in masters:
            out += f"👨‍🔧 {m['full_name']} – ⭐{m['rating']} – {m['services']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=dispetcher_menu())
        return

    if text == "🔗 Ustaga biriktirish":
        await update.message.reply_text(
            "🔗 <b>Устага бириктириш</b>\n\n"
            "🆔 Буюртма ID рақамини киритинг:",
            parse_mode="HTML",
            reply_markup=back_keyboard(),
        )
        return

    if text == "📊 Statistika":
        stats = await db_statistics()
        if stats:
            await update.message.reply_text(
                f"📊 <b>СТАТИСТИКА</b>\n\n"
                f"📋 Жами: {stats['total']}\n"
                f"🆕 Янги: {stats['new']}\n"
                f"✅ Қабул: {stats['accepted']}\n"
                f"🔧 Жараёнда: {stats['progress']}\n"
                f"✅ Якунланган: {stats['completed']}\n"
                f"❌ Бекор: {stats['cancelled']}",
                parse_mode="HTML",
                reply_markup=dispetcher_menu(),
            )
        return

    if text == "📄 Hisobot":
        await update.message.reply_text("📄 Ҳисобот бўлими.", reply_markup=dispetcher_menu())
        return

    if text == "📞 Admin":
        await update.message.reply_text(f"👑 Админ ID: {ADMIN_ID}", reply_markup=dispetcher_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=dispetcher_menu())

# ============================================================
# ADMIN HANDLER
# ============================================================

async def admin_handler(update, context):
    user = update.effective_user
    text = update.message.text or ""

    if user.id != ADMIN_ID:
        return

    if text == "👨‍🔧 Ustalar":
        masters = await db_get_pending_masters()
        approved = len(await db_get_all_masters())

        await update.message.reply_text(
            f"👨‍🔧 <b>УСТАЛАР</b>\n\n"
            f"✅ Тасдиқланган: {approved}\n"
            f"⏳ Кутилаётган: {len(masters)}",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )

        for m in masters[:5]:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ TASDIQLASH", callback_data=f"master_approve:{m['telegram_id']}"),
                    InlineKeyboardButton("❌ RAD", callback_data=f"master_reject:{m['telegram_id']}"),
                ]
            ])
            await update.message.reply_text(
                f"👤 {m['full_name']}\n📞 {m['phone']}\n🛠 {m['services']}",
                reply_markup=keyboard,
            )
        return

    if text == "📋 Barcha buyurtmalar":
        orders = await db_get_all_orders()
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=admin_menu())
            return

        out = "📋 <b>БАРЧА БУЮРТМАЛАР</b>\n\n"
        for o in orders[:20]:
            out += f"🆔 №{o['id']} – {o['service']} – {o['status']}\n"

        await update.message.reply_text(out, parse_mode="HTML", reply_markup=admin_menu())
        return

    if text == "📊 Statistika":
        stats = await db_statistics()
        if stats:
            await update.message.reply_text(
                f"📊 <b>СТАТИСТИКА</b>\n\n"
                f"📋 Жами: {stats['total']}\n"
                f"🆕 Янги: {stats['new']}\n"
                f"✅ Қабул: {stats['accepted']}\n"
                f"🔧 Жараёнда: {stats['progress']}\n"
                f"✅ Якунланган: {stats['completed']}\n"
                f"❌ Бекор: {stats['cancelled']}",
                parse_mode="HTML",
                reply_markup=admin_menu(),
            )
        return

    if text == "👥 Mijozlar":
        async with db_pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM usta24_users")
        await update.message.reply_text(f"👥 <b>МИЖОЗЛАР</b>\n\nЖами: {count}", parse_mode="HTML", reply_markup=admin_menu())
        return

    if text == "💬 Xabar tarqatish":
        await update.message.reply_text("💬 Хабар тарқатиш бўлими.", reply_markup=admin_menu())
        return

    if text == "💰 Narxlar":
        await update.message.reply_text("💰 Нархлар бўлими.", reply_markup=admin_menu())
        return

    if text == "🎟 Kuponlar":
        await update.message.reply_text("🎟 Купонлар бўлими.", reply_markup=admin_menu())
        return

    if text == "📸 Rasmlar arxivi":
        await update.message.reply_text("📸 Расмлар архиви.", reply_markup=admin_menu())
        return

    if text == "⚙️ Sozlamalar":
        await update.message.reply_text(
            "⚙️ <b>СОЗЛАМАЛАР</b>\n\n"
            f"👑 Admin ID: {ADMIN_ID}\n"
            f"📞 Dispetcher ID: {DISPATCHER_ID}\n"
            f"📢 Гуруҳ ID: {MASTERS_GROUP_ID}",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(f"📞 Диспетчер: {DISPATCHER_PHONE}", reply_markup=admin_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=admin_menu())

# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Xatolik:", exc_info=context.error)

# ============================================================
# STARTUP
# ============================================================

async def post_init(application: Application):
    await init_db()
    logger.info("=" * 40)
    logger.info("🚀 USTA24 DISPATCHER STARTED")
    logger.info(f"👑 ADMIN_ID={ADMIN_ID}")
    logger.info(f"📞 DISPATCHER_ID={DISPATCHER_ID}")
    logger.info(f"📢 MASTERS_GROUP_ID={MASTERS_GROUP_ID}")
    logger.info("=" * 40)

async def post_shutdown(application: Application):
    global db_pool
    if db_pool:
        await db_pool.close()
    logger.info("Database pool closed")

# ============================================================
# MAIN
# ============================================================

def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))

    application.add_handler(
        CallbackQueryHandler(
            callbacks,
            pattern=r"^(master_|order_|assign_to:|view_images:)"
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
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
