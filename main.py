#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA24 DISPATCHER
🏗️ ONE BOT = CLIENT + MASTER + ADMIN + MASTERS GROUP
🐘 PostgreSQL with asyncpg
🌐 Flask + Gunicorn for Railway
📸 Rasmlar bilan to'liq ishlaydi
"""

import os
import logging
import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from threading import Thread

import asyncpg
from flask import Flask, jsonify, request

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
    ConversationHandler,
)
from telegram.constants import ParseMode

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = os.getenv("DISPATCHER_PHONE", "+998901234567")
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL topilmadi!")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24_DISPATCHER")

db_pool = None
application = None

# ============================================================
# FLASK APP (HEALTH CHECK UCHUN)
# ============================================================

flask_app = Flask(__name__)

@flask_app.route("/")
def health_check():
    return jsonify({
        "status": "ok",
        "service": "USTA24 DISPATCHER",
        "time": datetime.now().isoformat()
    })

@flask_app.route("/health")
def health():
    return jsonify({"status": "healthy"})

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# ============================================================
# DATABASE
# ============================================================

async def init_db():
    """Ma'lumotlar bazasini ishga tushirish"""
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    
    async with db_pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'mijoz',
                is_active BOOLEAN DEFAULT TRUE,
                rating FLOAT DEFAULT 0,
                rating_count INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Orders table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                master_id BIGINT,
                service_type TEXT,
                service_subtype TEXT,
                name TEXT,
                phone TEXT,
                address TEXT,
                address_lat FLOAT,
                address_lng FLOAT,
                description TEXT,
                time_pref TEXT,
                price BIGINT,
                status TEXT DEFAULT 'yangi',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                cancel_reason TEXT,
                images JSONB DEFAULT '[]'::jsonb,
                result_images JSONB DEFAULT '[]'::jsonb,
                status_history JSONB DEFAULT '[]'::jsonb
            )
        """)
        
        # Masters table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE,
                name TEXT,
                phone TEXT,
                service TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                rating FLOAT DEFAULT 0,
                rating_count INT DEFAULT 0,
                total_orders INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Reviews table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                order_id INT,
                master_id BIGINT,
                rating INT,
                text TEXT,
                images JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        logger.info("✅ Database tables ready")

async def get_user(user_id: int) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None

async def add_user(user_id: int, name: str, phone: str = None, role: str = "mijoz"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO users (user_id, name, phone, role) 
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id) DO UPDATE 
               SET name = $2, phone = $3, role = $4, updated_at = CURRENT_TIMESTAMP""",
            user_id, name, phone, role
        )

async def update_user(user_id: int, **kwargs):
    async with db_pool.acquire() as conn:
        fields = []
        values = []
        for key, val in kwargs.items():
            fields.append(f"{key} = ${len(values) + 1}")
            values.append(val)
        values.append(user_id)
        await conn.execute(
            f"UPDATE users SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ${len(values)}",
            *values
        )

async def create_order(user_id: int, data: dict) -> int:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO orders (
                user_id, service_type, service_subtype, name, phone,
                address, address_lat, address_lng, description, time_pref, price,
                images, status_history
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
        """,
            user_id,
            data.get("service_type"),
            data.get("service_subtype"),
            data.get("name"),
            data.get("phone"),
            data.get("address"),
            data.get("address_lat"),
            data.get("address_lng"),
            data.get("description"),
            data.get("time_pref"),
            data.get("price", 0),
            json.dumps(data.get("images", [])),
            json.dumps([{"status": "yangi", "time": datetime.now().isoformat()}])
        )
        return row["id"]

async def get_order(order_id: int) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return dict(row) if row else None

async def get_user_orders(user_id: int) -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE user_id = $1 ORDER BY id DESC LIMIT 20",
            user_id
        )
        return [dict(r) for r in rows]

async def get_master_orders(master_id: int) -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE master_id = $1 ORDER BY id DESC",
            master_id
        )
        return [dict(r) for r in rows]

async def get_all_orders() -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM orders ORDER BY id DESC LIMIT 50")
        return [dict(r) for r in rows]

async def get_orders_by_status(status: str) -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE status = $1 ORDER BY id DESC",
            status
        )
        return [dict(r) for r in rows]

async def update_order_status(order_id: int, status: str, **kwargs):
    async with db_pool.acquire() as conn:
        fields = ["status = $1", "updated_at = CURRENT_TIMESTAMP"]
        values = [status]
        
        if status == "qabul" and not kwargs.get("assigned_at"):
            fields.append("assigned_at = CURRENT_TIMESTAMP")
        elif status == "ishda" and not kwargs.get("started_at"):
            fields.append("started_at = CURRENT_TIMESTAMP")
        elif status == "tugadi" and not kwargs.get("finished_at"):
            fields.append("finished_at = CURRENT_TIMESTAMP")
        elif status == "bekor" and not kwargs.get("cancelled_at"):
            fields.append("cancelled_at = CURRENT_TIMESTAMP")
        
        for key, val in kwargs.items():
            fields.append(f"{key} = ${len(values) + 1}")
            values.append(val)
        
        history = await conn.fetchval(
            "SELECT status_history FROM orders WHERE id = $1", order_id
        )
        history_list = json.loads(history) if history else []
        history_list.append({"status": status, "time": datetime.now().isoformat()})
        
        fields.append(f"status_history = ${len(values) + 1}")
        values.append(json.dumps(history_list))
        
        values.append(order_id)
        await conn.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ${len(values)}",
            *values
        )

async def assign_master(order_id: int, master_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """UPDATE orders 
               SET master_id = $1, status = 'qabul', assigned_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
               WHERE id = $2""",
            master_id, order_id
        )
        history = await conn.fetchval(
            "SELECT status_history FROM orders WHERE id = $1", order_id
        )
        history_list = json.loads(history) if history else []
        history_list.append({"status": "qabul", "time": datetime.now().isoformat()})
        await conn.execute(
            "UPDATE orders SET status_history = $1 WHERE id = $2",
            json.dumps(history_list), order_id
        )

async def add_master(user_id: int, name: str, phone: str, service: str) -> int:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO masters (user_id, name, phone, service, is_active)
            VALUES ($1, $2, $3, $4, TRUE)
            RETURNING id
        """, user_id, name, phone, service)
        return row["id"]

async def get_master(master_id: int) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM masters WHERE id = $1", master_id)
        return dict(row) if row else None

async def get_all_masters() -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM masters ORDER BY id")
        return [dict(r) for r in rows]

async def get_active_masters() -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM masters WHERE is_active = TRUE ORDER BY rating DESC"
        )
        return [dict(r) for r in rows]

# ============================================================
# KEYBOARDS
# ============================================================

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🛒 Buyurtma berish"), KeyboardButton("📋 Buyurtmalarim")],
        [KeyboardButton("🔍 Holat tekshirish"), KeyboardButton("❌ Bekor qilish")],
        [KeyboardButton("🔁 Qayta buyurtma"), KeyboardButton("👨‍🔧 Mening ustalarim")],
        [KeyboardButton("⭐ Reytingim"), KeyboardButton("📝 Sharh qoldirish")],
        [KeyboardButton("📌 Eslatmalarim"), KeyboardButton("🗺️ Yaqin ustalar")],
        [KeyboardButton("📅 Yozilma"), KeyboardButton("🎁 Loyallik")],
        [KeyboardButton("🤖 AI yordamchi"), KeyboardButton("⚙️ Sozlamalar")],
        [KeyboardButton("📞 Dispetcher"), KeyboardButton("ℹ️ Yordam")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("👨‍🔧 Ustalar"), KeyboardButton("📋 Barcha buyurtmalar")],
        [KeyboardButton("👥 Mijozlar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("📄 Hisobot"), KeyboardButton("💰 Narxlar")],
        [KeyboardButton("💬 Xabar tarqatish"), KeyboardButton("🎟 Kuponlar")],
        [KeyboardButton("📸 Rasmlar arxivi"), KeyboardButton("⚙️ Sozlamalar")],
        [KeyboardButton("📞 Dispetcher"), KeyboardButton("🚪 Chiqish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_dispetcher_keyboard():
    keyboard = [
        [KeyboardButton("📨 Yangi buyurtmalar"), KeyboardButton("📋 Barcha buyurtmalar")],
        [KeyboardButton("👨‍🔧 Ustalar"), KeyboardButton("🔗 Ustaga biriktirish")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("📄 Hisobot")],
        [KeyboardButton("⚙️ Sozlamalar"), KeyboardButton("📞 Admin")],
        [KeyboardButton("🚪 Chiqish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_master_keyboard():
    keyboard = [
        [KeyboardButton("👤 Profil"), KeyboardButton("🆕 Yangi buyurtmalar")],
        [KeyboardButton("📋 Mening buyurtmalarim"), KeyboardButton("✅ Qabul qilish")],
        [KeyboardButton("🔧 Ishni boshlash"), KeyboardButton("✅ Ishni yakunlash")],
        [KeyboardButton("❌ Rad etish"), KeyboardButton("👥 Mijozlarim")],
        [KeyboardButton("📊 Statistika"), KeyboardButton("💰 Daromad")],
        [KeyboardButton("⭐ Reytingim"), KeyboardButton("📞 Dispetcher")],
        [KeyboardButton("⚙️ Sozlamalar"), KeyboardButton("🚪 Chiqish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_service_keyboard():
    keyboard = [
        [KeyboardButton("🛠 Sanitariya"), KeyboardButton("⚡ Elektr")],
        [KeyboardButton("🔧 Mexanik"), KeyboardButton("🧹 Tozalash")],
        [KeyboardButton("📦 Yuk tashish"), KeyboardButton("❓ Boshqa")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_service_sub_keyboard(service: str):
    keyboards = {
        "🛠 Sanitariya": [
            ["🚽 Hojatxona", "🚿 Lavabo"],
            ["🔧 Quvur", "🧹 Kanalizatsiya"],
            ["🚰 Suv o'rnatish", "📋 Boshqa"],
            ["🔙 Orqaga"]
        ],
        "⚡ Elektr": [
            ["💡 Chiroq", "🔌 Rozetka"],
            ["🔧 Sim almashtirish", "⚡ Avtomat"],
            ["📹 Kamera", "📋 Boshqa"],
            ["🔙 Orqaga"]
        ],
        "🔧 Mexanik": [
            ["🚪 Eshik", "🪟 Deraza"],
            ["🪑 Mebel yig'ish", "❄️ Konditsioner"],
            ["🔒 Qulf almashtirish", "📋 Boshqa"],
            ["🔙 Orqaga"]
        ],
        "🧹 Tozalash": [
            ["🏠 Uy tozalash", "🏢 Ofis tozalash"],
            ["🧶 Gilam tozalash", "🪟 Deraza tozalash"],
            ["🧹 Umumiy", "📋 Boshqa"],
            ["🔙 Orqaga"]
        ],
        "📦 Yuk tashish": [
            ["📦 Kichik yuk", "📦 O'rta yuk"],
            ["📦 Katta yuk", "🏠 Ko'chirish"],
            ["🚛 Yuk tashish", "📋 Boshqa"],
            ["🔙 Orqaga"]
        ],
        "❓ Boshqa": [
            ["📝 O'zim yozaman"],
            ["🔙 Orqaga"]
        ]
    }
    keys = keyboards.get(service, [["🔙 Orqaga"]])
    keyboard = [[KeyboardButton(k) for k in row] for row in keys]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_time_keyboard():
    keyboard = [
        [KeyboardButton("🔴 Hozir"), KeyboardButton("🟡 Bugun kechqurun")],
        [KeyboardButton("🟢 Ertaga ertalab"), KeyboardButton("📆 Boshqa vaqt")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_confirm_keyboard():
    keyboard = [
        [KeyboardButton("✅ Tasdiqlash"), KeyboardButton("❌ Bekor qilish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_reason_keyboard():
    keyboard = [
        [KeyboardButton("⏳ Uzoq kutish"), KeyboardButton("💰 Narx baland")],
        [KeyboardButton("🕐 Vaqt mos emas"), KeyboardButton("🔄 Boshqa usta topdim")],
        [KeyboardButton("❌ Endi kerak emas"), KeyboardButton("📝 Boshqa sabab")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_rating_keyboard():
    keyboard = [
        [KeyboardButton("⭐ 1"), KeyboardButton("⭐⭐ 2"), KeyboardButton("⭐⭐⭐ 3")],
        [KeyboardButton("⭐⭐⭐⭐ 4"), KeyboardButton("⭐⭐⭐⭐⭐ 5")],
        [KeyboardButton("🔙 Orqaga")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_skip_keyboard():
    keyboard = [[KeyboardButton("⏭ O'tkazib yuborish")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_keyboard():
    keyboard = [[KeyboardButton("🔙 Orqaga")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ============================================================
# CONVERSATION STATES
# ============================================================

SERVICE, SERVICE_SUB, ORDER_NAME, ORDER_PHONE, ORDER_ADDRESS, \
ORDER_ADDRESS_TEXT, ORDER_IMAGE, ORDER_DESCRIPTION, ORDER_TIME, \
ORDER_TIME_DATE, ORDER_TIME_HOUR, ORDER_COUPON, ORDER_CONFIRM = range(13)

CHECK_STATUS = range(13, 14)
CANCEL_ORDER, CANCEL_REASON, CANCEL_CONFIRM = range(14, 17)
REVIEW_ORDER, REVIEW_RATING, REVIEW_TEXT, REVIEW_IMAGE, REVIEW_CONFIRM = range(17, 22)
ADMIN_ADD_MASTER_NAME, ADMIN_ADD_MASTER_PHONE, ADMIN_ADD_MASTER_SERVICE = range(22, 25)
ADMIN_DELETE_MASTER = range(25, 26)
ADMIN_ASSIGN_ORDER, ADMIN_ASSIGN_MASTER = range(26, 28)
ADMIN_BROADCAST = range(28, 29)
MASTER_ACCEPT, MASTER_ACCEPT_TIME = range(29, 31)
MASTER_START = range(31, 32)
MASTER_FINISH, MASTER_FINISH_IMAGE = range(32, 34)
MASTER_REJECT = range(34, 35)

# ============================================================
# START COMMAND
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    
    if user_id == ADMIN_ID:
        await update.message.reply_text(
            "👑 <b>Admin paneliga xush kelibsiz!</b>",
            reply_markup=get_admin_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return
    
    if not user:
        await update.message.reply_text(
            "🇺🇿 <b>USTA24 DISPATCHER</b> botiga xush kelibsiz!\n\n"
            "👤 Ismingizni kiriting (faqat ism, familiya kerak emas):",
            parse_mode=ParseMode.HTML
        )
        return
    
    role = user.get("role", "mijoz")
    
    if role == "usta":
        await update.message.reply_text(
            f"👋 Salom, {user.get('name', 'Usta')}!",
            reply_markup=get_master_keyboard()
        )
    elif role == "dispetcher":
        await update.message.reply_text(
            f"👋 Salom, {user.get('name', 'Dispetcher')}!",
            reply_markup=get_dispetcher_keyboard()
        )
    else:
        await update.message.reply_text(
            f"👋 Salom, {user.get('name', 'Mijoz')}!",
            reply_markup=get_main_keyboard()
        )

async def start_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Iltimos, ismingizni to'g'ri kiriting:")
        return
    
    context.user_data["reg_name"] = name
    
    await update.message.reply_text(
        "📱 Telefon raqamingizni kiriting:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📞 Kontakt yuborish", request_contact=True)]],
            resize_keyboard=True
        )
    )
    return

async def start_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    
    name = context.user_data.get("reg_name", "Foydalanuvchi")
    
    await add_user(user_id, name, phone, "mijoz")
    
    await update.message.reply_text(
        f"✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n"
        f"👤 Ism: {name}\n"
        f"📞 Telefon: {phone}",
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

# ============================================================
# BUYURTMA BERISH
# ============================================================

async def buyurtma_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛒 <b>Buyurtma berish</b>\n\n"
        "1️⃣ Xizmat turini tanlang:",
        reply_markup=get_service_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return SERVICE

async def service_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Orqaga":
        await update.message.reply_text("🏠 Bosh menyu:", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data["service_type"] = text
    
    await update.message.reply_text(
        f"2️⃣ {text} xizmat turini tanlang:",
        reply_markup=get_service_sub_keyboard(text)
    )
    return SERVICE_SUB

async def service_sub_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Orqaga":
        await update.message.reply_text(
            "1️⃣ Xizmat turini tanlang:",
            reply_markup=get_service_keyboard()
        )
        return SERVICE
    
    context.user_data["service_subtype"] = text
    
    await update.message.reply_text(
        "3️⃣ 👤 <b>Ismingiz:</b> (Familiya kerak emas!)",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_NAME

async def order_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Iltimos, ismingizni to'g'ri kiriting:")
        return ORDER_NAME
    
    context.user_data["order_name"] = name
    
    await update.message.reply_text(
        "4️⃣ 📞 <b>Telefon raqamingiz:</b>",
        parse_mode=ParseMode.HTML
    )
    return ORDER_PHONE

async def order_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
    
    context.user_data["order_phone"] = phone
    
    await update.message.reply_text(
        "5️⃣ 📍 <b>Manzil:</b>\n"
        "📍 Geolokatsiya yuborish yoki matn bilan yozing:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("📍 Geolokatsiya yuborish", request_location=True)],
                [KeyboardButton("✏️ Matn bilan yozish")],
                [KeyboardButton("🔙 Orqaga")]
            ],
            resize_keyboard=True
        ),
        parse_mode=ParseMode.HTML
    )
    return ORDER_ADDRESS

async def order_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.location:
        context.user_data["address_lat"] = update.message.location.latitude
        context.user_data["address_lng"] = update.message.location.longitude
        context.user_data["address"] = f"{update.message.location.latitude}, {update.message.location.longitude}"
        
        await update.message.reply_text(
            "6️⃣ 📸 <b>Rasm yuborish (ixtiyoriy)</b>",
            reply_markup=get_skip_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return ORDER_IMAGE
    
    elif update.message.text == "✏️ Matn bilan yozish":
        await update.message.reply_text(
            "✏️ Manzilni matn bilan yozing:",
            reply_markup=ReplyKeyboardRemove()
        )
        return ORDER_ADDRESS_TEXT
    
    elif update.message.text == "🔙 Orqaga":
        await update.message.reply_text(
            "5️⃣ 📍 Manzil:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [KeyboardButton("📍 Geolokatsiya yuborish", request_location=True)],
                    [KeyboardButton("✏️ Matn bilan yozish")],
                    [KeyboardButton("🔙 Orqaga")]
                ],
                resize_keyboard=True
            )
        )
        return ORDER_ADDRESS
    
    return ORDER_ADDRESS

async def order_address_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["address"] = update.message.text
    context.user_data["address_lat"] = None
    context.user_data["address_lng"] = None
    
    await update.message.reply_text(
        "6️⃣ 📸 <b>Rasm yuborish (ixtiyoriy)</b>",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_IMAGE

async def order_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⏭ O'tkazib yuborish":
        context.user_data["images"] = []
        await update.message.reply_text(
            "7️⃣ 📝 <b>Izoh (ixtiyoriy)</b>",
            reply_markup=get_skip_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return ORDER_DESCRIPTION
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        if "images" not in context.user_data:
            context.user_data["images"] = []
        context.user_data["images"].append({"file_id": file_id, "type": "muammo"})
        
        await update.message.reply_text(
            f"✅ Rasm qabul qilindi! ({len(context.user_data['images'])} ta)",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("⏭ Davom etish")]],
                resize_keyboard=True
            )
        )
        return ORDER_IMAGE
    
    if update.message.text == "⏭ Davom etish":
        await update.message.reply_text(
            "7️⃣ 📝 <b>Izoh (ixtiyoriy)</b>",
            reply_markup=get_skip_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return ORDER_DESCRIPTION
    
    await update.message.reply_text("❌ Iltimos, rasm yuboring yoki '⏭ O'tkazib yuborish' tugmasini bosing.")
    return ORDER_IMAGE

async def order_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "⏭ O'tkazib yuborish":
        context.user_data["description"] = ""
    else:
        context.user_data["description"] = update.message.text
    
    await update.message.reply_text(
        "8️⃣ 🕐 <b>Vaqtni tanlang:</b>",
        reply_markup=get_time_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_TIME

async def order_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Orqaga":
        await update.message.reply_text(
            "7️⃣ 📝 Izoh (ixtiyoriy):",
            reply_markup=get_skip_keyboard()
        )
        return ORDER_DESCRIPTION
    
    if text == "📆 Boshqa vaqt":
        await update.message.reply_text(
            "📅 Kunni tanlang (YYYY-MM-DD):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ORDER_TIME_DATE
    
    context.user_data["time_pref"] = text
    
    await update.message.reply_text(
        "9️⃣ 💰 <b>Narx: 120,000 so'm</b>\n\n"
        "🎟 Kupon kodi bo'lsa kiriting:",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_COUPON

async def order_time_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        datetime.strptime(update.message.text, "%Y-%m-%d")
        context.user_data["time_pref"] = f"📅 {update.message.text}"
        
        await update.message.reply_text(
            "🕐 Soatni tanlang (HH:MM):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ORDER_TIME_HOUR
    except:
        await update.message.reply_text("❌ Iltimos, to'g'ri formatda yozing (YYYY-MM-DD):")
        return ORDER_TIME_DATE

async def order_time_hour(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["time_pref"] = f"{context.user_data.get('time_pref')} {update.message.text}"
    
    await update.message.reply_text(
        "9️⃣ 💰 <b>Narx: 120,000 so'm</b>\n\n"
        "🎟 Kupon kodi bo'lsa kiriting:",
        reply_markup=get_skip_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_COUPON

async def order_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = 120000
    
    if update.message.text != "⏭ O'tkazib yuborish":
        coupon = update.message.text.strip().upper()
        if coupon == "WELCOME10":
            price = 108000
            await update.message.reply_text("✅ 10% chegirma!")
        elif coupon == "SALE20":
            price = 96000
            await update.message.reply_text("✅ 20% chegirma!")
    
    context.user_data["price"] = price
    
    data = context.user_data
    images_count = len(data.get("images", []))
    
    text = (
        f"📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
        f"🛠 Xizmat: {data.get('service_type')} – {data.get('service_subtype')}\n"
        f"👤 Ism: {data.get('order_name')}\n"
        f"📞 Telefon: {data.get('order_phone')}\n"
        f"📍 Manzil: {data.get('address')}\n"
        f"📸 Rasm: {images_count} ta\n"
        f"📝 Izoh: {data.get('description') or 'Yo\'q'}\n"
        f"🕐 Vaqt: {data.get('time_pref')}\n"
        f"💰 Narx: {price:,} so'm\n\n"
        "✅ Tasdiqlaysizmi?"
    )
    
    await update.message.reply_text(
        text,
        reply_markup=get_confirm_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ORDER_CONFIRM

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("❌ Buyurtma bekor qilindi.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    if update.message.text == "✅ Tasdiqlash":
        data = context.user_data
        
        order_id = await create_order(update.effective_user.id, {
            "service_type": data.get("service_type"),
            "service_subtype": data.get("service_subtype"),
            "name": data.get("order_name"),
            "phone": data.get("order_phone"),
            "address": data.get("address"),
            "address_lat": data.get("address_lat"),
            "address_lng": data.get("address_lng"),
            "description": data.get("description"),
            "time_pref": data.get("time_pref"),
            "price": data.get("price", 120000),
            "images": data.get("images", [])
        })
        
        await update.message.reply_text(
            f"✅ <b>Buyurtma yuborildi!</b>\n\n"
            f"🆔 #{order_id}",
            reply_markup=get_main_keyboard(),
            parse_mode=ParseMode.HTML
        )
        
        # Xabar yuborish
        text = (
            f"🆕 <b>YANGI BUYURTMA!</b>\n\n"
            f"🆔 #{order_id}\n"
            f"🛠 {data.get('service_type')} – {data.get('service_subtype')}\n"
            f"👤 {data.get('order_name')}\n"
            f"📞 {data.get('order_phone')}\n"
            f"📍 {data.get('address')}\n"
            f"💰 {data.get('price', 120000):,} so'm\n"
            f"🕐 {data.get('time_pref')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍🔧 Usta biriktirish", callback_data=f"assign_{order_id}")],
            [InlineKeyboardButton("🖼 Rasmlarni ko'rish", callback_data=f"view_images_{order_id}")]
        ])
        
        if ADMIN_ID:
            await application.bot.send_message(ADMIN_ID, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        if MASTERS_GROUP_ID:
            await application.bot.send_message(MASTERS_GROUP_ID, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        
        return ConversationHandler.END
    
    await update.message.reply_text("❌ Iltimos, ✅ Tasdiqlash yoki ❌ Bekor qilish tugmasini bosing.")
    return ORDER_CONFIRM

# ============================================================
# CALLBACKS
# ============================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("assign_"):
        order_id = int(data.split("_")[1])
        order = await get_order(order_id)
        
        if not order:
            await query.edit_message_text("❌ Buyurtma topilmadi!")
            return
        
        masters = await get_active_masters()
        
        if not masters:
            await query.edit_message_text("❌ Hali faol ustalar yo'q!")
            return
        
        keyboard = InlineKeyboardMarkup([])
        for master in masters:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    f"👨‍🔧 {master.get('name')} - {master.get('service')} (⭐{master.get('rating', 0)})",
                    callback_data=f"assign_to_{order_id}_{master.get('id')}"
                )
            ])
        
        await query.edit_message_text(
            f"🔗 <b>Ustani tanlang</b>\n\n"
            f"🆔 #{order_id}",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        return
    
    if data.startswith("assign_to_"):
        parts = data.split("_")
        order_id = int(parts[2])
        master_id = int(parts[3])
        
        await assign_master(order_id, master_id)
        
        order = await get_order(order_id)
        master = await get_master(master_id)
        
        await query.edit_message_text(
            f"✅ <b>Usta biriktirildi!</b>\n\n"
            f"🆔 #{order_id}\n"
            f"👨‍🔧 {master.get('name')}",
            parse_mode=ParseMode.HTML
        )
        
        if order and order.get("user_id"):
            await application.bot.send_message(
                order.get("user_id"),
                f"✅ <b>Usta biriktirildi!</b>\n\n"
                f"🆔 #{order_id}\n"
                f"👨‍🔧 {master.get('name')}",
                parse_mode=ParseMode.HTML
            )
        return
    
    if data.startswith("view_images_"):
        order_id = int(data.split("_")[2])
        order = await get_order(order_id)
        
        if not order:
            await query.edit_message_text("❌ Buyurtma topilmadi!")
            return
        
        images = json.loads(order.get("images", "[]"))
        
        text = f"🖼 <b>Buyurtma #{order_id} rasmlari</b>\n\n"
        text += f"📸 Rasmlar: {len(images)} ta"
        
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return

# ============================================================
# MAIN
# ============================================================

async def main():
    global application
    
    await init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    application.add_handler(CommandHandler("start", start))
    
    # Callback
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Buyurtma conversation
    buyurtma_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), buyurtma_start)],
        states={
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_select)],
            SERVICE_SUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_sub_select)],
            ORDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_name)],
            ORDER_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, order_phone)],
            ORDER_ADDRESS: [MessageHandler(filters.LOCATION | filters.TEXT & ~filters.COMMAND, order_address)],
            ORDER_ADDRESS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_address_text)],
            ORDER_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, order_image)],
            ORDER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_description)],
            ORDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_time)],
            ORDER_TIME_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_time_date)],
            ORDER_TIME_HOUR: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_time_hour)],
            ORDER_COUPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_coupon)],
            ORDER_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_confirm)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    )
    application.add_handler(buyurtma_conv)
    
    # Start name handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start_name), group=1)
    application.add_handler(MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, start_phone), group=2)
    
    # Other handlers
    application.add_handler(MessageHandler(filters.Regex("^📋 Buyurtmalarim$"), async def my_orders(update, context):
        user_id = update.effective_user.id
        orders = await get_user_orders(user_id)
        
        if not orders:
            await update.message.reply_text("📋 Siz hali buyurtma bermagansiz.")
            return
        
        text = "📋 <b>Mening buyurtmalarim:</b>\n\n"
        for order in orders[:10]:
            status_emoji = {
                "yangi": "🆕", "qabul": "✅", "ishda": "🔧", "tugadi": "✅", "bekor": "❌"
            }.get(order.get("status"), "🆕")
            text += f"{status_emoji} #{order['id']} – {order.get('service_type')} – {order.get('status')}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    ))
    
    application.add_handler(MessageHandler(filters.Regex("^🔍 Holat tekshirish$"), async def check_status(update, context):
        await update.message.reply_text(
            "🔍 <b>Buyurtma holati</b>\n\n"
            "🆔 Buyurtma raqamini kiriting:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard()
        )
    ))
    
    application.add_handler(MessageHandler(filters.Regex("^❌ Bekor qilish$"), async def cancel_start(update, context):
        await update.message.reply_text(
            "❌ <b>Buyurtmani bekor qilish</b>\n\n"
            "🆔 Buyurtma raqamini kiriting:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_keyboard()
        )
    ))
    
    application.add_handler(MessageHandler(filters.Regex("^🔙 Orqaga$"), async def back(update, context):
        user_id = update.effective_user.id
        user = await get_user(user_id)
        
        if user_id == ADMIN_ID:
            await update.message.reply_text("🏠 Admin menyusi:", reply_markup=get_admin_keyboard())
        elif user.get("role") == "usta":
            await update.message.reply_text("🏠 Usta menyusi:", reply_markup=get_master_keyboard())
        elif user.get("role") == "dispetcher":
            await update.message.reply_text("🏠 Dispetcher menyusi:", reply_markup=get_dispetcher_keyboard())
        else:
            await update.message.reply_text("🏠 Bosh menyu:", reply_markup=get_main_keyboard())
    ))
    
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ Yordam$"), async def help_msg(update, context):
        await update.message.reply_text(
            "📖 <b>Yordam</b>\n\n"
            "🛒 Buyurtma berish\n"
            "📋 Buyurtmalarim\n"
            "🔍 Holat tekshirish\n"
            "❌ Bekor qilish\n\n"
            "📞 Dispetcher: +998901234567",
            parse_mode=ParseMode.HTML
        )
    ))
    
    # Flask ni alohida threadda ishga tushirish
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Botni ishga tushirish
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    logger.info("🚀 USTA24 DISPATCHER ishga tushdi!")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot to'xtatildi!")
        sys.exit(0)
