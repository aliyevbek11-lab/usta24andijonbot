# ============================================================
# USTA24 DISPATCHER BOT
# Telegram: @USTA24DISPATCHER_BOT
# 
# Python 3.11+
# python-telegram-bot==22.3
# asyncpg==0.30.0
# Flask==3.1.1
# gunicorn==23.0.0
#
# AI0GRAM YO'Q
# PostgreSQL
#
# ROLES:
#   MIJOZ
#   USTA
#   DISPATCHER
#   ADMIN
#
# ENV:
#   BOT_TOKEN
#   DATABASE_URL
#   ADMIN_ID
#   ADMIN_IDS
#   DISPATCHER_ID
#   MASTERS_GROUP_ID
# ============================================================

import os
import asyncio
import logging
import json
import threading
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

import asyncpg

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("USTA24")

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN topilmadi!")
    sys.exit(1)

if not DATABASE_URL:
    logger.error("❌ DATABASE_URL topilmadi!")
    sys.exit(1)

MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0").strip() or "0")
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0").strip() or "0")

ADMIN_IDS = set()
admin_id = os.getenv("ADMIN_ID", "").strip()
if admin_id:
    try:
        ADMIN_IDS.add(int(admin_id))
    except ValueError:
        pass

admin_ids = os.getenv("ADMIN_IDS", "").strip()
if admin_ids:
    for item in admin_ids.split(","):
        item = item.strip()
        if item:
            try:
                ADMIN_IDS.add(int(item))
            except ValueError:
                pass

# Agar DISPATCHER_ID adminlar qatoriga qo'shilmagan bo'lsa
if DISPATCHER_ID:
    ADMIN_IDS.add(DISPATCHER_ID)

logger.info(f"✅ ADMIN_IDS: {ADMIN_IDS}")

# ============================================================
# FLASK SERVER
# ============================================================

flask_app = Flask(__name__)

@flask_app.get("/")
def home():
    return "USTA 24 ANDIJON BOT IS RUNNING"

@flask_app.get("/health")
def health():
    return "OK"

def run_flask():
    port = int(os.getenv("PORT", "8080"))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

# ============================================================
# DATABASE
# ============================================================

db_pool: Optional[asyncpg.Pool] = None

async def migrate_orders_table():
    """Add order_number column if not exists"""
    async with db_pool.acquire() as conn:
        # Check if column exists
        row = await conn.fetchrow("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='orders' AND column_name='order_number'
        """)
        
        if not row:
            logger.info("⏳ order_number ustuni qo'shilmoqda...")
            await conn.execute("""
                ALTER TABLE orders ADD COLUMN order_number TEXT UNIQUE
            """)
            logger.info("✅ order_number ustuni qo'shildi")
            
            # Update existing orders with order_number
            await conn.execute("""
                UPDATE orders 
                SET order_number = '#' || to_char(created_at, 'YYMMDDHH24MISS') || '_' || id::text
                WHERE order_number IS NULL
            """)
            logger.info("✅ Mavjud buyurtmalarga order_number berildi")
        else:
            logger.info("✅ order_number ustuni allaqachon mavjud")

async def init_db():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL ENV topilmadi!")

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=60,
    )

    async with db_pool.acquire() as conn:
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                full_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                role TEXT DEFAULT 'mijoz',
                language TEXT DEFAULT 'uz',
                created_at TIMESTAMP DEFAULT NOW(),
                is_blocked BOOLEAN DEFAULT FALSE,
                block_reason TEXT DEFAULT '',
                block_until TIMESTAMP
            )
        """)

        # Masters table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                services TEXT DEFAULT '',
                rating NUMERIC DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                total_earnings BIGINT DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                work_days TEXT DEFAULT '1,2,3,4,5',
                work_start TEXT DEFAULT '08:00',
                work_end TEXT DEFAULT '20:00',
                lunch_start TEXT DEFAULT '13:00',
                lunch_end TEXT DEFAULT '14:00',
                max_orders_per_day INTEGER DEFAULT 5
            )
        """)

        # Orders table - WITH order_number
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number TEXT UNIQUE,
                user_id BIGINT NOT NULL,
                service_type TEXT DEFAULT '',
                service_name TEXT DEFAULT '',
                client_name TEXT DEFAULT '',
                client_phone TEXT DEFAULT '',
                address TEXT DEFAULT '',
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                description TEXT DEFAULT '',
                photo_ids TEXT DEFAULT '',
                preferred_time TEXT DEFAULT '',
                price BIGINT DEFAULT 0,
                status TEXT DEFAULT 'yangi',
                master_id BIGINT,
                master_name TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancel_reason TEXT DEFAULT '',
                rating INTEGER,
                review TEXT DEFAULT ''
            )
        """)

        # Ratings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY,
                order_id INTEGER,
                from_user_id BIGINT,
                to_user_id BIGINT,
                rating INTEGER,
                review TEXT DEFAULT '',
                photo_ids TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Bookings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                master_id BIGINT,
                service_name TEXT DEFAULT '',
                booking_date TEXT DEFAULT '',
                booking_time TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Coupons table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                discount INTEGER DEFAULT 0,
                used_by BIGINT,
                is_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Notifications table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                message TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

    # MIGRATION - BU MUHIM!
    await migrate_orders_table()

    logger.info("✅ PostgreSQL database initialized")

# ============================================================
# DATABASE FUNCTIONS
# ============================================================

async def get_user(user_id: int) -> Optional[Dict]:
    """Get user by ID"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        return dict(row) if row else None

async def save_user(user_id: int, full_name: str = "", phone: str = "", role: str = "mijoz"):
    """Save or update user"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, full_name, phone, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                phone = EXCLUDED.phone,
                role = EXCLUDED.role
        """, user_id, full_name, phone, role)

async def get_master(user_id: int) -> Optional[Dict]:
    """Get master by user_id"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT u.*, m.* 
            FROM users u 
            JOIN masters m ON u.user_id = m.user_id 
            WHERE u.user_id = $1
        """, user_id)
        return dict(row) if row else None

async def get_masters(service_type: str = None) -> List[Dict]:
    """Get all active masters"""
    async with db_pool.acquire() as conn:
        if service_type:
            rows = await conn.fetch("""
                SELECT u.user_id, u.full_name, u.phone, m.*
                FROM users u
                JOIN masters m ON u.user_id = m.user_id
                WHERE u.role = 'usta' AND m.is_active = TRUE 
                AND m.services LIKE $1
                ORDER BY m.rating DESC
            """, f"%{service_type}%")
        else:
            rows = await conn.fetch("""
                SELECT u.user_id, u.full_name, u.phone, m.*
                FROM users u
                JOIN masters m ON u.user_id = m.user_id
                WHERE u.role = 'usta' AND m.is_active = TRUE
                ORDER BY m.rating DESC
            """)
        return [dict(row) for row in rows]

async def create_order(data: Dict) -> int:
    """Create new order"""
    order_number = f"#{datetime.now().strftime('%y%m%d%H%M%S')}_{data['user_id']}"
    
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO orders (
                order_number, user_id, service_type, service_name,
                client_name, client_phone, address, latitude, longitude,
                description, photo_ids, preferred_time, price, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            RETURNING id
        """,
            order_number,
            data['user_id'],
            data.get('service_type', ''),
            data.get('service_name', ''),
            data.get('client_name', ''),
            data.get('client_phone', ''),
            data.get('address', ''),
            data.get('latitude'),
            data.get('longitude'),
            data.get('description', ''),
            data.get('photo_ids', '[]'),
            data.get('preferred_time', ''),
            data.get('price', 0),
            'yangi'
        )
        return row['id']

async def get_order(order_id: int) -> Optional[Dict]:
    """Get order by ID"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
        return dict(row) if row else None

async def get_order_by_number(order_number: str) -> Optional[Dict]:
    """Get order by number"""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM orders WHERE order_number = $1", order_number)
        return dict(row) if row else None

async def get_user_orders(user_id: int, status: str = None) -> List[Dict]:
    """Get user orders"""
    async with db_pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE user_id = $1 AND status = $2 ORDER BY created_at DESC",
                user_id, status
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC",
                user_id
            )
        return [dict(row) for row in rows]

async def get_master_orders(master_id: int, status: str = None) -> List[Dict]:
    """Get master orders"""
    async with db_pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE master_id = $1 AND status = $2 ORDER BY created_at DESC",
                master_id, status
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE master_id = $1 ORDER BY created_at DESC",
                master_id
            )
        return [dict(row) for row in rows]

async def update_order_status(order_id: int, status: str, **kwargs):
    """Update order status"""
    fields = []
    values = []
    for key, value in kwargs.items():
        if value is not None:
            fields.append(f"{key} = ${len(values) + 1}")
            values.append(value)
    
    values.append(status)
    values.append(order_id)
    
    query = f"UPDATE orders SET status = ${len(values) - 1}, " + ", ".join(fields) + " WHERE id = $" + str(len(values))
    
    async with db_pool.acquire() as conn:
        await conn.execute(query, *values)

async def save_rating(order_id: int, from_user_id: int, to_user_id: int, rating: int, review: str = "", photo_ids: str = ""):
    """Save rating"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ratings (order_id, from_user_id, to_user_id, rating, review, photo_ids)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, order_id, from_user_id, to_user_id, rating, review, photo_ids)
        
        # Update master rating
        await conn.execute("""
            UPDATE masters 
            SET rating = (SELECT AVG(rating) FROM ratings WHERE to_user_id = $1),
                rating_count = (SELECT COUNT(*) FROM ratings WHERE to_user_id = $1)
            WHERE user_id = $1
        """, to_user_id)

async def get_all_orders(status: str = None) -> List[Dict]:
    """Get all orders (for admin/dispatcher)"""
    async with db_pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM orders WHERE status = $1 ORDER BY created_at DESC",
                status
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM orders ORDER BY created_at DESC"
            )
        return [dict(row) for row in rows]

# ============================================================
# KEYBOARDS (КЛАВИАТУРАЛАР)
# ============================================================

def get_main_keyboard(role: str = "mijoz") -> ReplyKeyboardMarkup:
    """Asosiy menu"""
    if role == "mijoz":
        return ReplyKeyboardMarkup([
            ["🛒 Buyurtma berish"],
            ["📋 Mening buyurtmalarim", "🔍 Buyurtma holati"],
            ["❌ Buyurtmani bekor qilish", "🔁 Qayta buyurtma"],
            ["👨‍🔧 Mening ustalarim", "⭐ Reytingim"],
            ["📝 Sharh qoldirish", "📌 Eslatmalarim"],
            ["🗺️ Yaqin ustalar", "📅 Yozilma (bron)"],
            ["🎁 Loyallik", "🤖 AI yordamchi"],
            ["📞 Dispetcher bilan bog'lanish", "⚙️ Sozlamalar"],
            ["🚪 Chiqish"]
        ], resize_keyboard=True)
    
    elif role == "usta":
        return ReplyKeyboardMarkup([
            ["👤 Mening profilim", "🆕 Yangi buyurtmalar"],
            ["📋 Mening buyurtmalarim", "✅ Buyurtma qabul qilish"],
            ["🔧 Ishni boshlash", "✅ Ishni yakunlash"],
            ["❌ Buyurtma rad etish", "👥 Mijozlarim"],
            ["📊 Mening statistikam", "💰 Kunlik daromad"],
            ["⭐ Reytingim", "💬 Mijoz bilan chat"],
            ["📊 Ish unumdorligi", "🕒 Mening grafikim"],
            ["⚙️ Sozlamalar", "📞 Dispetcher bilan bog'lanish"],
            ["🚪 Chiqish"]
        ], resize_keyboard=True)
    
    elif role == "dispetcher":
        return ReplyKeyboardMarkup([
            ["📨 Yangi buyurtmalar", "📋 Barcha buyurtmalar"],
            ["👨‍🔧 Ustalar ro'yxati", "🔗 Ustaga biriktirish"],
            ["📊 Statistika", "📄 Hisobotlar"],
            ["⚙️ Sozlamalar", "📞 Admin bilan bog'lanish"],
            ["🔔 Eslatmalar", "🚪 Chiqish"]
        ], resize_keyboard=True)
    
    elif role == "admin":
        return ReplyKeyboardMarkup([
            ["👨‍🔧 Ustalar", "📋 Barcha buyurtmalar"],
            ["👥 Mijozlar", "📊 Statistika"],
            ["📄 Hisobotlar", "💰 Narxlar"],
            ["💬 Xabar tarqatish", "🎟 Kuponlar"],
            ["📸 Rasmlar arxivi", "🚫 Bloklash"],
            ["⚙️ Sozlamalar", "📞 Dispetcher bilan bog'lanish"],
            ["🚪 Chiqish"]
        ], resize_keyboard=True)
    
    return ReplyKeyboardMarkup([["🏠 Bosh menyu"]], resize_keyboard=True)

def get_service_keyboard() -> ReplyKeyboardMarkup:
    """Xizmat turlari"""
    return ReplyKeyboardMarkup([
        ["🛠 Sanitariya", "⚡ Elektr"],
        ["🔧 Mexanik", "🧹 Tozalash"],
        ["📦 Yuk tashish", "❓ Boshqa"],
        ["🔙 Orqaga"]
    ], resize_keyboard=True)

def get_sub_service_keyboard(service_type: str) -> ReplyKeyboardMarkup:
    """Xizmat turi bo'yicha quyi menu"""
    services = {
        "sanitariya": ["🚽 Hojatxona o'rnatish", "🚿 Lavabo o'rnatish", "🔧 Quvur ta'miri", "🧹 Kanalizatsiya tozalash", "🚰 Suv o'rnatish", "📋 Boshqa"],
        "elektr": ["💡 Chiroq o'rnatish", "🔌 Rozetka o'rnatish", "🔧 Sim almashtirish", "⚡ Avtomat o'chirgich", "📹 Kamera o'rnatish", "📋 Boshqa"],
        "mexanik": ["🚪 Eshik ta'miri", "🪟 Deraza ta'miri", "🪑 Mebel yig'ish", "❄️ Konditsioner o'rnatish", "🔒 Qulf almashtirish", "📋 Boshqa"],
        "tozalash": ["🏠 Uy tozalash", "🏢 Ofis tozalash", "🧶 Gilam tozalash", "🪟 Deraza tozalash", "🧹 Umumiy tozalash", "📋 Boshqa"],
        "yuk_tashish": ["📦 Kichik yuk", "📦 O'rta yuk", "📦 Katta yuk", "🏠 Ko'chirish", "🚛 Yuk tashish", "📋 Boshqa"]
    }
    
    buttons = services.get(service_type, ["📋 Boshqa"])
    keyboard = []
    row = []
    for btn in buttons:
        row.append(KeyboardButton(btn))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(["🔙 Orqaga"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_time_keyboard() -> ReplyKeyboardMarkup:
    """Vaqt tanlash"""
    return ReplyKeyboardMarkup([
        ["🔴 Hozir", "🟡 Bugun kechqurun"],
        ["🟢 Ertaga ertalab", "📆 Boshqa vaqt"],
        ["🔙 Orqaga"]
    ], resize_keyboard=True)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Bekor qilish sabablari"""
    return ReplyKeyboardMarkup([
        ["⏳ Uzoq kutish", "💰 Narx baland"],
        ["🕐 Vaqt mos emas", "🔄 Boshqa usta topdim"],
        ["❌ Endi kerak emas", "🏠 Manzil o'zgardi"],
        ["📝 Boshqa sabab", "🔙 Orqaga"]
    ], resize_keyboard=True)

def get_rating_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Rating keyboard"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rating_1_{order_id}"),
            InlineKeyboardButton("⭐⭐ 2", callback_data=f"rating_2_{order_id}"),
            InlineKeyboardButton("⭐⭐⭐ 3", callback_data=f"rating_3_{order_id}"),
            InlineKeyboardButton("⭐⭐⭐⭐ 4", callback_data=f"rating_4_{order_id}"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐ 5", callback_data=f"rating_5_{order_id}")
        ]
    ])

def get_order_actions_keyboard(order_id: int, order_status: str) -> InlineKeyboardMarkup:
    """Order action buttons for master"""
    buttons = []
    
    if order_status == "taklif_yuborildi":
        buttons.append([
            InlineKeyboardButton("✅ ҚАБУЛ", callback_data=f"accept_{order_id}"),
            InlineKeyboardButton("❌ РАД ЭТИШ", callback_data=f"reject_{order_id}")
        ])
        buttons.append([
            InlineKeyboardButton("📞 ҚЎНҒИРОҚ", callback_data=f"call_{order_id}"),
            InlineKeyboardButton("📍 МАНЗИЛ", callback_data=f"location_{order_id}")
        ])
    
    return InlineKeyboardMarkup(buttons) if buttons else None

# ============================================================
# SERVICE INFO
# ============================================================

def get_service_info(service_name: str) -> Optional[Dict]:
    """Xizmat haqida malumot"""
    info = {
        "🚽 Hojatxona o'rnatish": {
            "price": 80000, "time": 1.5, 
            "desc": "Янги унитаз ўрнатиш, эскисини демонтаж қилиш",
            "extra": "Эски унитазни олиб чиқиш 10,000 сўм қўшимча"
        },
        "🚿 Lavabo o'rnatish": {
            "price": 70000, "time": 1.0,
            "desc": "Янги раковина ўрнатиш, миксер улаш",
            "extra": "Эски раковинани олиб чиқиш 10,000 сўм қўшимча"
        },
        "🔧 Quvur ta'miri": {
            "price": 90000, "time": 1.5,
            "desc": "Сув ёки канализация қувурларини таъмирлаш",
            "extra": "Қувур материаллари қўшимча тўланади"
        },
        "💡 Chiroq o'rnatish": {
            "price": 50000, "time": 0.75,
            "desc": "Шамдон, люстра ёки ёритиш мосламасини ўрнатиш",
            "extra": "Люстрани демонтаж қилиш 10,000 сўм қўшимча"
        },
        "🔌 Rozetka o'rnatish": {
            "price": 60000, "time": 0.75,
            "desc": "Янги розетка ўрнатиш, эскисини алмаштириш",
            "extra": "2 тадан ортиқ розетка учун ҳар бири 20,000 сўм"
        },
        "❄️ Konditsioner o'rnatish": {
            "price": 150000, "time": 2.5,
            "desc": "Кондиционер ўрнатиш, фреон тўлдириш",
            "extra": "Эски кондиционерни демонтаж 30,000 сўм"
        },
        "🏠 Uy tozalash": {
            "price": 50000, "time": 2.5,
            "desc": "Хоналарни чангдан тозалаш, полларни ювиш",
            "extra": "3 хоналик уй учун ўртача 2.5 соат"
        },
        "📦 Kichik yuk": {
            "price": 30000, "time": 0.5,
            "desc": "10 кг гача бўлган юкни ташиш",
            "extra": "Бир жойдан иккинчи жойга"
        },
        "📦 O'rta yuk": {
            "price": 50000, "time": 1.0,
            "desc": "10-30 кг гача бўлган юкни ташиш",
            "extra": "Маиший техника ва бошқалар"
        },
        "📦 Katta yuk": {
            "price": 80000, "time": 1.5,
            "desc": "30 кг дан оғир юкни ташиш",
            "extra": "Мебель, шкаф, холодильник"
        },
        "🏠 Ko'chirish": {
            "price": 200000, "time": 3.5,
            "desc": "Уй кўчириш – тўлиқ юкни кўчириш",
            "extra": "2 хоналик уй учун ўртача нарх"
        }
    }
    return info.get(service_name)

# ============================================================
# SEND NOTIFICATIONS
# ============================================================

application: Application = None

async def send_message(user_id: int, text: str, keyboard=None, parse_mode=None):
    """Send message to user"""
    global application
    try:
        if application and application.bot:
            if keyboard:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=parse_mode or ParseMode.HTML
                )
            else:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=parse_mode or ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Xabar yuborishda xatolik: {e}")

async def send_photo(user_id: int, photo_id: str, caption: str = None, keyboard=None):
    """Send photo to user"""
    global application
    try:
        if application and application.bot:
            await application.bot.send_photo(
                chat_id=user_id,
                photo=photo_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Rasm yuborishda xatolik: {e}")

async def send_order_to_master(order: Dict, master_id: int):
    """Send order to master with photo"""
    photo_ids = order.get('photo_ids')
    if photo_ids:
        try:
            photo_ids = json.loads(photo_ids)
        except:
            photo_ids = []
    
    text = f"""
🕌 Assalomu alaykum, уста!

🆕 <b>ЯНГИ ЗАКАЗ!</b>
═══════════════════════════════════
🆔 {order['order_number']}
🛠 {order['service_name']}
💰 {order['price']:,} so'm
🕐 {order['preferred_time']}

👤 <b>МИЖОЗ:</b>
├── {order['client_name']}
├── 📞 {order['client_phone']}
└── 📍 {order['address']}

📸 <b>МУАММО РАСМИ:</b>
═══════════════════════════════════
"""
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ҚАБУЛ", callback_data=f"accept_{order['id']}"),
            InlineKeyboardButton("❌ РАД ЭТИШ", callback_data=f"reject_{order['id']}")
        ],
        [
            InlineKeyboardButton("📞 ҚЎНҒИРОҚ", callback_data=f"call_{order['id']}"),
            InlineKeyboardButton("📍 МАНЗИЛ", callback_data=f"location_{order['id']}")
        ],
        [
            InlineKeyboardButton("🖼 РАСМЛАРНИ КЎРИШ", callback_data=f"view_photos_{order['id']}")
        ]
    ])
    
    await send_message(master_id, text, keyboard, ParseMode.HTML)
    
    # Send photos
    if photo_ids:
        for photo_id in photo_ids[:3]:
            await send_photo(master_id, photo_id)

async def send_order_to_dispatcher(order: Dict):
    """Send order to dispatcher"""
    photo_ids = order.get('photo_ids')
    if photo_ids:
        try:
            photo_ids = json.loads(photo_ids)
        except:
            photo_ids = []
    
    text = f"""
🕌 Assalomu alaykum, диспетчер!

🆕 <b>ЯНГИ ЗАКАЗ!</b>
═══════════════════════════════════
🆔 {order['order_number']} │ ⏳ Kutilmoqda

🛠 {order['service_name']}
💰 {order['price']:,} so'm
👤 {order['client_name']} – 📞 {order['client_phone']}
📍 {order['address']}
📝 {order.get('description', 'Йўқ')}
═══════════════════════════════════
📸 {'✅ ' + str(len(photo_ids)) + ' та' if photo_ids else '❌ Рамс йўқ'}
═══════════════════════════════════
"""
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ҚАБУЛ", callback_data=f"disp_accept_{order['id']}"),
            InlineKeyboardButton("❌ РАД ЭТИШ", callback_data=f"disp_reject_{order['id']}")
        ],
        [
            InlineKeyboardButton("📨 УСТАГА ЮБОРИШ", callback_data=f"disp_master_{order['id']}"),
            InlineKeyboardButton("📨 ҲАММАГА ЮБОРИШ", callback_data=f"disp_all_{order['id']}")
        ],
        [
            InlineKeyboardButton("📝 ИЗОҲ ҚЎШИШ", callback_data=f"disp_note_{order['id']}"),
            InlineKeyboardButton("🖼 РАСМЛАРНИ КЎРИШ", callback_data=f"view_photos_{order['id']}")
        ]
    ])
    
    # Send to all admins/dispatchers
    for admin_id in ADMIN_IDS:
        await send_message(admin_id, text, keyboard, ParseMode.HTML)
        if photo_ids:
            for photo_id in photo_ids[:3]:
                await send_photo(admin_id, photo_id)

async def send_order_to_all_masters(order: Dict):
    """Send order to all active masters"""
    masters = await get_masters(order.get('service_type'))
    
    if not masters:
        logger.warning(f"No masters found for service: {order.get('service_type')}")
        return
    
    for master in masters:
        await send_order_to_master(order, master['user_id'])
    
    # Update order status
    await update_order_status(order['id'], "taklif_yuborildi")
    
    logger.info(f"Order {order['order_number']} sent to {len(masters)} masters")

# ============================================================
# CONVERSATION STATES
# ============================================================

# Order states
SERVICE_TYPE, SERVICE_NAME, CLIENT_NAME, CLIENT_PHONE, ADDRESS, PHOTO, DESCRIPTION, TIME, CONFIRM = range(9)

# Profile states
LANG, NAME, PHONE, ROLE = range(4)

# Master states
MASTER_TIME, MASTER_CANCEL, MASTER_COMPLETE, MASTER_PAYMENT = range(4)

# Booking states
BOOKING_DATE, BOOKING_TIME, BOOKING_MASTER = range(3)

# ============================================================
# HANDLERS
# ============================================================

# ---------- START ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command"""
    user_id = update.effective_user.id
    
    # Check if user exists
    user = await get_user(user_id)
    
    if user and user.get('is_blocked'):
        await update.message.reply_text(
            f"⛔ Сиз блоклангансиз!\n📝 Сабаб: {user.get('block_reason', 'Ноаниқ')}"
        )
        return ConversationHandler.END
    
    # Language selection
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")]
    ])
    
    await update.message.reply_text(
        "🕌 Assalomu alaykum! USTA24 хизматига хуш келибсиз!\n\n"
        "🌍 <b>Tilni tanlang:</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return LANG

async def lang_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Language selection callback"""
    query = update.callback_query
    await query.answer()
    
    lang = query.data.split("_")[1]
    context.user_data['language'] = lang
    
    messages = {
        "uz": "👤 <b>Ismingizni kiriting:</b>\n\n⚠️ Familiya kerak emas!",
        "ru": "👤 <b>Введите ваше имя:</b>\n\n⚠️ Фамилия не нужна!",
        "en": "👤 <b>Enter your name:</b>\n\n⚠️ No surname needed!",
        "tr": "👤 <b>Adınızı girin:</b>\n\n⚠️ Soyad gerekmez!"
    }
    
    await query.edit_message_text(
        messages.get(lang, messages["uz"]),
        parse_mode=ParseMode.HTML
    )
    return NAME

async def name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user name"""
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("❌ Илтимос, исмингизни тўғри киритинг (камида 2 ҳарф)!")
        return NAME
    
    context.user_data['full_name'] = name
    
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📞 Kontakt yuborish", request_contact=True)],
        [KeyboardButton("✏️ O'zim yozaman")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "📞 <b>Telefon raqamingiz:</b>\n\n"
        "📱 Raqamni yuborish учун тугмани босинг ёки ўзингиз ёзинг:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return PHONE

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user phone"""
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
        if not phone.startswith("+") and not phone.startswith("998"):
            phone = "+998" + phone
    
    context.user_data['phone'] = phone
    
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("👤 Mijoz"), KeyboardButton("👨‍🔧 Usta")],
        [KeyboardButton("👑 Admin"), KeyboardButton("📞 Dispetcher")]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "👤 <b>Kim sifatida kirasiz?</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return ROLE

async def role_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user role"""
    role_map = {
        "👤 Mijoz": "mijoz",
        "👨‍🔧 Usta": "usta",
        "👑 Admin": "admin",
        "📞 Dispetcher": "dispetcher"
    }
    
    role = role_map.get(update.message.text, "mijoz")
    
    # Check admin
    if role == "admin" and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Сиз админ эмассиз! Мижоз сифатида киринг.")
        role = "mijoz"
    
    user_id = update.effective_user.id
    data = context.user_data
    
    await save_user(
        user_id=user_id,
        full_name=data.get('full_name', ''),
        phone=data.get('phone', ''),
        role=role
    )
    
    # If master, create master record
    if role == "usta":
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO masters (user_id)
                VALUES ($1)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)
    
    await update.message.reply_text(
        f"✅ <b>Xush kelibsiz, {data.get('full_name', '')}!</b>\n\n"
        f"🏠 <b>{role.capitalize()} BOSH MENYUSI</b>",
        reply_markup=get_main_keyboard(role),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    user = await get_user(update.effective_user.id)
    role = user.get('role', 'mijoz') if user else 'mijoz'
    
    await update.message.reply_text(
        "❌ Бекор қилинди!",
        reply_markup=get_main_keyboard(role)
    )
    return ConversationHandler.END

# ---------- ORDER ----------

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start order process"""
    user_id = update.effective_user.id
    user = await get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Илтимос, /start босиб қайта киринг!")
        return ConversationHandler.END
    
    if user.get('is_blocked'):
        await update.message.reply_text(f"⛔ Сиз блоклангансиз!\n📝 Сабаб: {user.get('block_reason', 'Ноаниқ')}")
        return ConversationHandler.END
    
    context.user_data['user_id'] = user_id
    context.user_data['photo_ids'] = json.dumps([])
    
    await update.message.reply_text(
        "📌 <b>1-ҚАДАМ: Xizmat turini tanlang</b>\n\n"
        "🛠 Қайси хизмат турни танлайсиз?",
        reply_markup=get_service_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return SERVICE_TYPE

async def order_service_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select service type"""
    if update.message.text == "🔙 Orqaga":
        user = await get_user(update.effective_user.id)
        role = user.get('role', 'mijoz') if user else 'mijoz'
        await update.message.reply_text(
            "🏠 Bosh menyu",
            reply_markup=get_main_keyboard(role)
        )
        return ConversationHandler.END
    
    service_map = {
        "🛠 Sanitariya": "sanitariya",
        "⚡ Elektr": "elektr",
        "🔧 Mexanik": "mexanik",
        "🧹 Tozalash": "tozalash",
        "📦 Yuk tashish": "yuk_tashish",
        "❓ Boshqa": "boshqa"
    }
    
    service_type = service_map.get(update.message.text)
    if not service_type:
        await update.message.reply_text("❌ Илтимос, тугмалардан бирини босинг!")
        return SERVICE_TYPE
    
    context.user_data['service_type'] = service_type
    
    # Show service description
    desc = get_service_description(service_type)
    await update.message.reply_text(
        f"📌 <b>2-ҚАДАМ: Хизматни танланг</b>\n\n"
        f"{desc}\n\n"
        f"🔽 Қуйидаги хизматлардан бирини танланг:",
        reply_markup=get_sub_service_keyboard(service_type),
        parse_mode=ParseMode.HTML
    )
    return SERVICE_NAME

def get_service_description(service_type: str) -> str:
    """Xizmat turi haqida malumot"""
    desc = {
        "sanitariya": "🛠 <b>Sanitariya хизматлари:</b>\n"
                      "🚽 Hojatxona o'rnatish – 80,000 сўм/соат\n"
                      "🚿 Lavabo o'rnatish – 70,000 сўм/соат\n"
                      "🔧 Quvur ta'miri – 90,000 сўм/соат\n"
                      "🧹 Kanalizatsiya tozalash – 100,000 сўм/соат\n"
                      "🚰 Suv o'rnatish – 85,000 сўм/соат",
        "elektr": "⚡ <b>Elektr хизматлари:</b>\n"
                  "💡 Chiroq o'rnatish – 50,000 сўм/соат\n"
                  "🔌 Rozetka o'rnatish – 60,000 сўм/соат\n"
                  "🔧 Sim almashtirish – 80,000 сўм/соат\n"
                  "⚡ Avtomat o'chirgich – 70,000 сўм/соат\n"
                  "📹 Kamera o'rnatish – 90,000 сўм/соат",
        "mexanik": "🔧 <b>Mexanik хизматлари:</b>\n"
                   "🚪 Eshik ta'miri – 70,000 сўм/соат\n"
                   "🪟 Deraza ta'miri – 65,000 сўм/соат\n"
                   "🪑 Mebel yig'ish – 75,000 сўм/соат\n"
                   "❄️ Konditsioner o'rnatish – 150,000 сўм/соат\n"
                   "🔒 Qulf almashtirish – 60,000 сўм/соат",
        "tozalash": "🧹 <b>Tozalash хизматлари:</b>\n"
                    "🏠 Uy tozalash – 50,000 сўм/соат\n"
                    "🏢 Ofis tozalash – 60,000 сўм/соат\n"
                    "🧶 Gilam tozalash – 70,000 сўм/соат\n"
                    "🪟 Deraza tozalash – 55,000 сўм/соат\n"
                    "🧹 Umumiy tozalash – 65,000 сўм/соат",
        "yuk_tashish": "📦 <b>Yuk tashish хизматлари:</b>\n"
                       "📦 Kichik yuk – 30,000 сўм\n"
                       "📦 O'rta yuk – 50,000 сўм\n"
                       "📦 Katta yuk – 80,000 сўм\n"
                       "🏠 Ko'chirish – 200,000 сўм\n"
                       "🚛 Yuk tashish – 150,000 сўм",
        "boshqa": "❓ <b>Бошқа хизматлар</b>\n"
                  "📝 Илтимос, изоҳда ёзинг"
    }
    return desc.get(service_type, "Хизмат маълумотлари топилмади")

async def order_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select service name"""
    if update.message.text == "🔙 Orqaga":
        await update.message.reply_text(
            "📌 <b>1-ҚАДАМ: Xizmat turini tanlang</b>",
            reply_markup=get_service_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return SERVICE_TYPE
    
    service_name = update.message.text
    context.user_data['service_name'] = service_name
    
    # Show service info
    info = get_service_info(service_name)
    if info:
        total_price = info['price'] * info['time']
        text = f"""
📋 <b>{service_name}</b>
═══════════════════════════════════
📌 {info['desc']}

💰 Нарх: {info['price']:,} сўм/соат
⏱ Вақт: {info['time']} соат
💵 Жами: {int(total_price):,} сўм
═══════════════════════════════════
⚠️ <b>Эслатма:</b> {info['extra']}
"""
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        context.user_data['price'] = int(total_price)
    else:
        await update.message.reply_text("📝 Бошқа хизмат учун изоҳда ёзинг")
        context.user_data['price'] = 0
    
    await update.message.reply_text(
        "👤 <b>3-ҚАДАМ: Ismingizni kiriting:</b>\n\n"
        "⚠️ Familiya kerak emas!",
        reply_markup=ReplyKeyboardMarkup([["🔙 Orqaga"]], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    return CLIENT_NAME

async def order_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get client name"""
    if update.message.text == "🔙 Orqaga":
        service_type = context.user_data.get('service_type', 'sanitariya')
        await update.message.reply_text(
            "📌 <b>2-ҚАДАМ: Хизматни танланг</b>",
            reply_markup=get_sub_service_keyboard(service_type),
            parse_mode=ParseMode.HTML
        )
        return SERVICE_NAME
    
    if len(update.message.text) < 2:
        await update.message.reply_text("❌ Илтимос, исмингизни тўғри киритинг (камида 2 ҳарф)!")
        return CLIENT_NAME
    
    context.user_data['client_name'] = update.message.text
    
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("📞 Kontakt yuborish", request_contact=True)],
        [KeyboardButton("✏️ O'zim yozaman")],
        ["🔙 Orqaga"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "📞 <b>4-ҚАДАМ: Telefon raqamingiz:</b>",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return CLIENT_PHONE

async def order_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get client phone"""
    if update.message.text == "🔙 Orqaga":
        await update.message.reply_text(
            "👤 <b>3-ҚАДАМ: Ismingizni kiriting:</b>",
            reply_markup=ReplyKeyboardMarkup([["🔙 Orqaga"]], resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        return CLIENT_NAME
    
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
        if not phone.startswith("+") and not phone.startswith("998"):
            phone = "+998" + phone
    
    context.user_data['client_phone'] = phone
    
    keyboard = ReplyKeyboardMarkup([
        ["📍 Geolokatsiya yuborish"],
        ["✏️ Matn bilan yozish"],
        ["🔙 Orqaga"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "📍 <b>5-ҚАДАМ: Manzilni kiriting:</b>\n\n"
        "🏠 Уй/офис манзилингизни ёзинг:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return ADDRESS

async def order_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get address"""
    if update.message.text == "🔙 Orqaga":
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("📞 Kontakt yuborish", request_contact=True)],
            [KeyboardButton("✏️ O'zim yozaman")],
            ["🔙 Orqaga"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "📞 <b>4-ҚАДАМ: Telefon raqamingiz:</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        return CLIENT_PHONE
    
    if update.message.location:
        address = f"📍 {update.message.location.latitude}, {update.message.location.longitude}"
        context.user_data['latitude'] = update.message.location.latitude
        context.user_data['longitude'] = update.message.location.longitude
    else:
        address = update.message.text
    
    context.user_data['address'] = address
    
    keyboard = ReplyKeyboardMarkup([
        ["📸 Rasm yuborish"],
        ["⏭ O'tkazib yuborish"],
        ["🔙 Orqaga"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "📸 <b>6-ҚАДАМ: Muammo joyini suratga oling!</b>\n\n"
        "🖼 [📸 Rasm yuborish] (1-5 та)\n\n"
        "📌 <b>Nima uchun rasm?</b>\n"
        "✅ Usta muammoni oldindan ko'radi\n"
        "✅ Narx aniqroq hisoblanadi\n"
        "✅ Usta asboblarni olib keladi",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    return PHOTO

async def order_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get photo"""
    if update.message.text == "🔙 Orqaga":
        keyboard = ReplyKeyboardMarkup([
            ["📍 Geolokatsiya yuborish"],
            ["✏️ Matn bilan yozish"],
            ["🔙 Orqaga"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "📍 <b>5-ҚАДАМ: Manzilni kiriting:</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        return ADDRESS
    
    if update.message.text == "⏭ O'tkazib yuborish":
        await ask_description(update, context)
        return DESCRIPTION
    
    if update.message.photo:
        photo_ids = context.user_data.get('photo_ids', '[]')
        try:
            photo_list = json.loads(photo_ids)
        except:
            photo_list = []
        
        photo_id = update.message.photo[-1].file_id
        photo_list.append(photo_id)
        context.user_data['photo_ids'] = json.dumps(photo_list)
        
        if len(photo_list) >= 5:
            await update.message.reply_text("✅ Максимал 5 та расм юбордингиз!")
            await ask_description(update, context)
            return DESCRIPTION
        else:
            await update.message.reply_text(
                f"✅ <b>Rasm qabul qilindi!</b>\n"
                f"🖼 {len(photo_list)} та rasm saqlandi\n"
                f"📸 Maksimal 5 та rasm yuborishingiz mumkin",
                reply_markup=ReplyKeyboardMarkup([
                    ["📸 Yana rasm"],
                    ["⏭ Davom etish"],
                    ["🔙 Orqaga"]
                ], resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )
            return PHOTO
    
    if update.message.text == "📸 Yana rasm":
        await update.message.reply_text("📸 Расм юборинг:")
        return PHOTO
    
    if update.message.text == "⏭ Davom etish":
        await ask_description(update, context)
        return DESCRIPTION
    
    await update.message.reply_text("❌ Илтимос, расм юборинг ёки [⏭ O'tkazib yuborish] босинг!")
    return PHOTO

async def ask_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for description"""
    await update.message.reply_text(
        "📝 <b>7-ҚАДАМ: Izoh (ixtiyoriy):</b>\n\n"
        "Қўшимча маълумотларни ёзинг (хона, қават, ва бошқалар):",
        reply_markup=ReplyKeyboardMarkup([
            ["⏭ O'tkazib yuborish"],
            ["🔙 Orqaga"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

async def order_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get description"""
    if update.message.text == "🔙 Orqaga":
        keyboard = ReplyKeyboardMarkup([
            ["📸 Rasm yuborish"],
            ["⏭ O'tkazib yuborish"],
            ["🔙 Orqaga"]
        ], resize_keyboard=True)
        await update.message.reply_text(
            "📸 <b>6-ҚАДАМ: Muammo joyini suratga oling!</b>",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
        return PHOTO
    
    if update.message.text == "⏭ O'tkazib yuborish":
        context.user_data['description'] = ""
    else:
        context.user_data['description'] = update.message.text
    
    await update.message.reply_text(
        "🕐 <b>8-ҚАДАМ: Qachon kerak?</b>",
        reply_markup=get_time_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return TIME

async def order_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get time"""
    if update.message.text == "🔙 Orqaga":
        await update.message.reply_text(
            "📝 <b>7-ҚАДАМ: Izoh (ixtiyoriy):</b>",
            reply_markup=ReplyKeyboardMarkup([
                ["⏭ O'tkazib yuborish"],
                ["🔙 Orqaga"]
            ], resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        return DESCRIPTION
    
    if update.message.text == "📆 Boshqa vaqt":
        await update.message.reply_text(
            "📅 <b>Kunni tanlang:</b>",
            reply_markup=ReplyKeyboardMarkup([
                ["22-08", "23-08"],
                ["24-08", "25-08"],
                ["26-08", "27-08"],
                ["28-08", "🔙 Orqaga"]
            ], resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        return TIME
    
    context.user_data['preferred_time'] = update.message.text
    await show_confirmation(update, context)
    return CONFIRM

async def order_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get date for booking"""
    date = update.message.text
    context.user_data['selected_date'] = date
    
    await update.message.reply_text(
        f"📅 {date} куни учун соатни танланг:",
        reply_markup=ReplyKeyboardMarkup([
            ["08:00", "09:00", "10:00"],
            ["11:00", "12:00", "13:00"],
            ["14:00", "15:00", "16:00"],
            ["17:00", "18:00", "19:00"],
            ["20:00", "21:00", "🔙 Orqaga"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    return TIME

async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order confirmation"""
    data = context.user_data
    
    photo_ids = data.get('photo_ids', '[]')
    try:
        photo_list = json.loads(photo_ids)
    except:
        photo_list = []
    
    text = f"""
📋 <b>Buyurtma ma'lumotlari:</b>
═══════════════════════════════════
🛠 {data.get('service_name', 'Ноаниқ')}
👤 Исм: {data.get('client_name', 'Ноаниқ')}
📞 {data.get('client_phone', 'Ноаниқ')}
📍 {data.get('address', 'Ноаниқ')}
📸 Rasm: {'✅ ' + str(len(photo_list)) + ' та' if photo_list else '❌ Rasm yo\'q'}
📝 Изоҳ: {data.get('description', 'Йўқ')}
🕐 Вақт: {data.get('preferred_time', 'Ноаниқ')}
💰 Нарх: {data.get('price', 0):,} сўм
═══════════════════════════════════

<b>10-ҚАДАМ: Тасдиқлаш</b>
"""
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup([
            ["✅ TASDIQLASH"],
            ["✏️ TAHRIRLASH"],
            ["❌ BEKOR QILISH"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm order - THIS IS THE MOST IMPORTANT BUTTON!"""
    
    # CHECK: "❌ BEKOR QILISH"
    if update.message.text == "❌ BEKOR QILISH":
        await update.message.reply_text(
            "❌ Буюртма бекор қилинди!",
            reply_markup=get_main_keyboard("mijoz")
        )
        return ConversationHandler.END
    
    # CHECK: "✏️ TAHRIRLASH"
    if update.message.text == "✏️ TAHRIRLASH":
        await update.message.reply_text(
            "📝 Қайси маълумотни ўзгартирмоқчисиз?\n\n"
            "1️⃣ Хизмат тури\n"
            "2️⃣ Исм\n"
            "3️⃣ Телефон\n"
            "4️⃣ Манзил\n"
            "5️⃣ Расм\n"
            "6️⃣ Изоҳ\n"
            "7️⃣ Вақт\n\n"
            "Қайта бошлаш учун /start босинг."
        )
        return CONFIRM
    
    # CHECK: "✅ TASDIQLASH" - THIS IS THE MAIN CONFIRM BUTTON
    if update.message.text == "✅ TASDIQLASH":
        data = context.user_data
        
        # Create order in database
        order_data = {
            'user_id': data.get('user_id'),
            'service_type': data.get('service_type'),
            'service_name': data.get('service_name'),
            'client_name': data.get('client_name'),
            'client_phone': data.get('client_phone'),
            'address': data.get('address'),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'description': data.get('description', ''),
            'photo_ids': data.get('photo_ids', '[]'),
            'preferred_time': data.get('preferred_time'),
            'price': data.get('price', 0)
        }
        
        try:
            order_id = await create_order(order_data)
            order = await get_order(order_id)
            
            if not order:
                await update.message.reply_text("❌ Буюртма яратишда хатолик! Қайта уриниб кўринг.")
                return CONFIRM
            
            # Send success message to client
            await update.message.reply_text(
                f"🎉 <b>BUYURTMA YUBORILDI!</b>\n"
                f"═══════════════════════════════════\n"
                f"🆔 {order['order_number']}\n"
                f"⏳ Holat: Dispetcher tekshiradi...\n"
                f"📨 Tasdiqlov xabari yuborildi\n"
                f"═══════════════════════════════════\n\n"
                f"📞 Устани кутинг!",
                reply_markup=get_main_keyboard("mijoz"),
                parse_mode=ParseMode.HTML
            )
            
            # Send to dispatcher
            await send_order_to_dispatcher(order)
            
            # Send to all masters automatically
            await send_order_to_all_masters(order)
            
            logger.info(f"✅ Order {order['order_number']} created by user {data.get('user_id')}")
            
        except Exception as e:
            logger.error(f"Order creation error: {e}")
            await update.message.reply_text(
                f"❌ Буюртма яратишда хатолик: {str(e)}\n\n"
                f"Илтимос, қайта уриниб кўринг ёки /start босинг."
            )
        
        return ConversationHandler.END
    
    # If none of the above
    await update.message.reply_text(
        "❌ Илтимос, тугмалардан бирини босинг:\n"
        "✅ TASDIQLASH\n"
        "✏️ TAHRIRLASH\n"
        "❌ BEKOR QILISH"
    )
    return CONFIRM

# ---------- MASTER ACCEPT ----------

async def master_accept_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master accept order"""
    user = await get_user(update.effective_user.id)
    if not user or user.get('role') != 'usta':
        await update.message.reply_text("❌ Бу бўлим фақат усталар учун!")
        return
    
    orders = await get_master_orders(update.effective_user.id, "taklif_yuborildi")
    
    if not orders:
        await update.message.reply_text("❌ Сизга янги заказлар келмаган.")
        return
    
    await update.message.reply_text(
        f"📋 <b>Янги заказлар ({len(orders)} та)</b>\n\n"
        f"Ҳар бир заказга эълон келди. Илтимос, эълондаги [✅ ҚАБУЛ] ёки [❌ РАД ЭТИШ] тугмаларини босинг.",
        parse_mode=ParseMode.HTML
    )
    
    for order in orders[:5]:
        await send_order_to_master(order, update.effective_user.id)

# ---------- MASTER ACCEPT/REJECT CALLBACKS ----------

async def accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master accepts order - THIS CALLBACK MUST WORK!"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[1])
    except:
        await query.edit_message_text("❌ Хатолик! Қайта уриниб кўринг.")
        return
    
    order = await get_order(order_id)
    
    if not order:
        await query.edit_message_text("❌ Буюртма топилмади!")
        return
    
    # Check if order is still available
    if order['status'] != "taklif_yuborildi":
        await query.edit_message_text(
            f"❌ Бу заказ бошқа уста томонидан қабул қилинган!\n"
            f"🆔 {order['order_number']}\n"
            f"📊 Ҳолат: {order['status']}"
        )
        return
    
    # Update order
    await update_order_status(
        order_id, 
        "qabul_qilindi", 
        master_id=query.from_user.id,
        master_name=query.from_user.full_name,
        accepted_at=datetime.now()
    )
    
    # Get master info
    master = await get_user(query.from_user.id)
    master_name = master.get('full_name', query.from_user.full_name) if master else query.from_user.full_name
    
    # Notify client
    await send_message(
        order['user_id'],
        f"✅ <b>Заказингиз қабул қилинди!</b>\n"
        f"═══════════════════════════════════\n"
        f"🆔 {order['order_number']}\n"
        f"👨‍🔧 Уста: {master_name}\n"
        f"⏱ Ҳозир келяпти\n"
        f"═══════════════════════════════════\n\n"
        f"📞 Уста билан боғланиш: @{query.from_user.username or 'телефон орқали'}",
        parse_mode=ParseMode.HTML
    )
    
    # Notify dispatcher
    for admin_id in ADMIN_IDS:
        await send_message(
            admin_id,
            f"✅ <b>Уста заказни қабул қилди!</b>\n"
            f"🆔 {order['order_number']}\n"
            f"👨‍🔧 {master_name}\n"
            f"📞 @{query.from_user.username or query.from_user.id}",
            parse_mode=ParseMode.HTML
        )
    
    # Response to master
    await query.edit_message_text(
        f"✅ <b>Заказ қабул қилинди!</b>\n"
        f"═══════════════════════════════════\n"
        f"🆔 {order['order_number']}\n"
        f"👤 {order['client_name']}\n"
        f"📞 {order['client_phone']}\n"
        f"📍 {order['address']}\n"
        f"═══════════════════════════════════\n\n"
        f"🔧 <b>Ишни бошлаш учун</b> бош менюдан [🔧 Ishni boshlash] босинг.",
        reply_markup=get_main_keyboard("usta"),
        parse_mode=ParseMode.HTML
    )

async def reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master rejects order"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[1])
    except:
        await query.edit_message_text("❌ Хатолик! Қайта уриниб кўринг.")
        return
    
    order = await get_order(order_id)
    
    if not order:
        await query.edit_message_text("❌ Буюртма топилмади!")
        return
    
    # Check if order is still available
    if order['status'] != "taklif_yuborildi":
        await query.edit_message_text(
            f"❌ Бу заказ бошқа ҳолатда!\n"
            f"🆔 {order['order_number']}\n"
            f"📊 Ҳолат: {order['status']}"
        )
        return
    
    # Ask for reason
    keyboard = ReplyKeyboardMarkup([
        ["💰 Narz baland", "📍 Manzil uzoq"],
        ["⏰ Vaqt mos emas", "🛠 Bu xizmatni qilmayman"],
        ["📝 Boshqa sabab", "🔙 Orqaga"]
    ], resize_keyboard=True)
    
    await query.message.reply_text(
        f"❌ <b>Рад этиш сабабини танланг:</b>\n"
        f"🆔 {order['order_number']}",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    
    context.user_data['reject_order_id'] = order_id
    context.user_data['waiting_reject_reason'] = True
    
    await query.edit_message_text(
        f"❌ Заказни рад этиш учун сабаб танланг 👆",
        parse_mode=ParseMode.HTML
    )

async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reject reason"""
    if not context.user_data.get('waiting_reject_reason'):
        return
    
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_reject_reason'] = False
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("usta")
        )
        return
    
    reason = update.message.text
    order_id = context.user_data.get('reject_order_id')
    
    if order_id:
        await update_order_status(order_id, "rad_etildi", cancel_reason=reason)
        order = await get_order(order_id)
        
        # Notify dispatcher
        for admin_id in ADMIN_IDS:
            await send_message(
                admin_id,
                f"❌ <b>Уста заказни рад этди!</b>\n"
                f"🆔 {order['order_number']}\n"
                f"👨‍🔧 {update.effective_user.full_name}\n"
                f"📝 Сабаб: {reason}",
                parse_mode=ParseMode.HTML
            )
        
        await update.message.reply_text(
            f"❌ <b>Заказ рад этилди!</b>\n"
            f"🆔 {order['order_number']}\n"
            f"📝 Сабаб: {reason}",
            reply_markup=get_main_keyboard("usta"),
            parse_mode=ParseMode.HTML
        )
    
    context.user_data['waiting_reject_reason'] = False

# ---------- MASTER START WORK ----------

async def master_start_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master start work"""
    user = await get_user(update.effective_user.id)
    if not user or user.get('role') != 'usta':
        await update.message.reply_text("❌ Бу бўлим фақат усталар учун!")
        return
    
    orders = await get_master_orders(update.effective_user.id, "qabul_qilindi")
    
    if not orders:
        await update.message.reply_text("❌ Сизда бошланмаган заказлар йўқ.")
        return
    
    text = "📋 <b>Бошланмаган заказлар:</b>\n\n"
    for i, order in enumerate(orders[:5], 1):
        text += f"{i}. 🆔 {order['order_number']} – {order['service_name']}\n"
    
    text += f"\nЗаказни бошлаш учун рақамни (1-{min(5, len(orders))}) ёки ID рақамни ёзинг:"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    context.user_data['waiting_start'] = True
    context.user_data['start_orders'] = orders

async def handle_start_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start work"""
    if not context.user_data.get('waiting_start'):
        return
    
    text = update.message.text.strip()
    orders = context.user_data.get('start_orders', [])
    
    # Try to get order by number
    order = None
    try:
        # Check if it's a number (1, 2, 3...)
        idx = int(text) - 1
        if 0 <= idx < len(orders):
            order = orders[idx]
    except ValueError:
        # Check if it's an order number
        order = await get_order_by_number(text)
    
    if not order:
        await update.message.reply_text(
            f"❌ Бундай заказ топилмади!\n"
            f"Илтимос, 1-{min(5, len(orders))} оралиғидаги рақам ёки заказ ID ни ёзинг."
        )
        return
    
    if order.get('master_id') != update.effective_user.id:
        await update.message.reply_text("❌ Бу заказ сизга тегишли эмас!")
        return
    
    if order.get('status') != "qabul_qilindi":
        await update.message.reply_text(f"❌ Бу заказ ҳолати '{order.get('status')}', бошлаб бўлмайди!")
        return
    
    # Start work
    await update_order_status(order['id'], "jarayonda", started_at=datetime.now())
    
    await update.message.reply_text(
        f"✅ <b>Иш бошланди!</b>\n"
        f"═══════════════════════════════════\n"
        f"🆔 {order['order_number']}\n"
        f"⏱ Бошланган вақт: {datetime.now().strftime('%H:%M')}\n"
        f"═══════════════════════════════════\n\n"
        f"Иш тугагандан сўнг [✅ Ishni yakunlash] босинг.",
        reply_markup=get_main_keyboard("usta"),
        parse_mode=ParseMode.HTML
    )
    
    # Notify client
    await send_message(
        order['user_id'],
        f"🔧 <b>Уста ишни бошлади!</b>\n"
        f"═══════════════════════════════════\n"
        f"🆔 {order['order_number']}\n"
        f"👨‍🔧 {update.effective_user.full_name}\n"
        f"⏱ Бошланган вақт: {datetime.now().strftime('%H:%M')}",
        parse_mode=ParseMode.HTML
    )
    
    # Notify dispatcher
    for admin_id in ADMIN_IDS:
        await send_message(
            admin_id,
            f"🔧 <b>Уста ишни бошлади!</b>\n"
            f"🆔 {order['order_number']}\n"
            f"👨‍🔧 {update.effective_user.full_name}",
            parse_mode=ParseMode.HTML
        )
    
    context.user_data['waiting_start'] = False
    context.user_data['start_orders'] = []

# ---------- MASTER COMPLETE ----------

async def master_complete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master complete work"""
    user = await get_user(update.effective_user.id)
    if not user or user.get('role') != 'usta':
        await update.message.reply_text("❌ Бу бўлим фақат усталар учун!")
        return
    
    orders = await get_master_orders(update.effective_user.id, "jarayonda")
    
    if not orders:
        await update.message.reply_text("❌ Сизда тугалламаган заказлар йўқ.")
        return
    
    text = "📋 <b>Тугалламаган заказлар:</b>\n\n"
    for i, order in enumerate(orders[:5], 1):
        text += f"{i}. 🆔 {order['order_number']} – {order['service_name']}\n"
    
    text += f"\nЗаказни тугаллаш учун рақамни (1-{min(5, len(orders))}) ёки ID рақамни ёзинг:"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    context.user_data['waiting_complete'] = True
    context.user_data['complete_orders'] = orders

async def handle_complete_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle complete work"""
    if not context.user_data.get('waiting_complete'):
        return
    
    text = update.message.text.strip()
    orders = context.user_data.get('complete_orders', [])
    
    # Try to get order by number
    order = None
    try:
        idx = int(text) - 1
        if 0 <= idx < len(orders):
            order = orders[idx]
    except ValueError:
        order = await get_order_by_number(text)
    
    if not order:
        await update.message.reply_text(
            f"❌ Бундай заказ топилмади!\n"
            f"Илтимос, 1-{min(5, len(orders))} оралиғидаги рақам ёки заказ ID ни ёзинг."
        )
        return
    
    if order.get('master_id') != update.effective_user.id:
        await update.message.reply_text("❌ Бу заказ сизга тегишли эмас!")
        return
    
    if order.get('status') != "jarayonda":
        await update.message.reply_text(f"❌ Бу заказ ҳолати '{order.get('status')}', тугаллаб бўлмайди!")
        return
    
    context.user_data['complete_order_id'] = order['id']
    
    await update.message.reply_text(
        "📸 <b>Натижа расми (МАЖБУРИЙ!)</b>\n"
        "═══════════════════════════════════\n"
        "🖼 Иш натижасини суратга олиб юборинг (1-5 та расм):\n"
        "⚠️ Расм юбормасангиз, заказ тугалланмайди!\n"
        "═══════════════════════════════════\n\n"
        "📸 Расм юборинг ёки бекор қилиш учун [🔙 Orqaga] босинг.",
        reply_markup=ReplyKeyboardMarkup([
            ["🔙 Orqaga"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    context.user_data['waiting_complete_photos'] = True
    context.user_data['complete_photos'] = []

async def handle_complete_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle complete photos"""
    if not context.user_data.get('waiting_complete_photos'):
        return
    
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_complete_photos'] = False
        context.user_data['complete_photos'] = []
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("usta")
        )
        return
    
    if not update.message.photo:
        await update.message.reply_text("❌ Илтимос, расм юборинг ёки [🔙 Orqaga] босинг!")
        return
    
    photo_list = context.user_data.get('complete_photos', [])
    photo_id = update.message.photo[-1].file_id
    photo_list.append(photo_id)
    context.user_data['complete_photos'] = photo_list
    
    if len(photo_list) >= 5:
        await update.message.reply_text("✅ Максимал 5 та расм юбордингиз!")
        await ask_complete_payment(update, context)
    else:
        await update.message.reply_text(
            f"✅ {len(photo_list)} та расм қабул қилинди!\n"
            f"📸 Яна расм юборинг ёки [✅ ТЎЛОВ] босинг:",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ ТЎЛОВ"],
                ["🔙 Orqaga"]
            ], resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )

async def ask_complete_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask payment info"""
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_complete_photos'] = False
        context.user_data['complete_photos'] = []
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("usta")
        )
        return
    
    await update.message.reply_text(
        "💰 <b>Тўлов маълумотлари:</b>\n"
        "═══════════════════════════════════\n\n"
        "Тўлов турини танланг:",
        reply_markup=ReplyKeyboardMarkup([
            ["💵 Naqd", "💳 Plastik"],
            ["📱 Click", "📱 Payme"],
            ["🔙 Orqaga"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )
    context.user_data['waiting_payment'] = True

async def handle_payment_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment type"""
    if not context.user_data.get('waiting_payment'):
        return
    
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_payment'] = False
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("usta")
        )
        return
    
    payment_type = update.message.text
    if payment_type in ["💵 Naqd", "💳 Plastik", "📱 Click", "📱 Payme"]:
        context.user_data['payment_type'] = payment_type
        
        await update.message.reply_text(
            "✅ <b>Тўлов олиндими?</b>",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Ha", "❌ Yo'q"],
                ["🔙 Orqaga"]
            ], resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        context.user_data['waiting_payment_confirm'] = True

async def handle_payment_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment confirm"""
    if not context.user_data.get('waiting_payment_confirm'):
        return
    
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_payment_confirm'] = False
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("usta")
        )
        return
    
    if update.message.text == "✅ Ha":
        order_id = context.user_data.get('complete_order_id')
        photo_list = context.user_data.get('complete_photos', [])
        payment_type = context.user_data.get('payment_type', 'Naqd')
        
        if order_id:
            # Save photos to order
            await update_order_status(
                order_id,
                "tugallandi",
                completed_at=datetime.now(),
                photo_ids=json.dumps(photo_list)
            )
            
            order = await get_order(order_id)
            
            # Update master stats
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE masters 
                    SET total_orders = total_orders + 1,
                        total_earnings = total_earnings + $1
                    WHERE user_id = $2
                """, order.get('price', 0), update.effective_user.id)
            
            # Notify client
            await send_message(
                order['user_id'],
                f"✅ <b>Ишингиз тугалланди!</b>\n"
                f"═══════════════════════════════════\n"
                f"🆔 {order['order_number']}\n"
                f"💰 Тўлов: {order['price']:,} сўм – {payment_type} – ✅ Олинди\n"
                f"👨‍🔧 Уста: {update.effective_user.full_name}\n"
                f"═══════════════════════════════════\n\n"
                f"⭐ <b>Устани баҳоланг!</b>",
                reply_markup=get_rating_keyboard(order_id),
                parse_mode=ParseMode.HTML
            )
            
            # Send photos to client
            for photo_id in photo_list[:3]:
                await send_photo(order['user_id'], photo_id)
            
            # Notify dispatcher
            for admin_id in ADMIN_IDS:
                await send_message(
                    admin_id,
                    f"✅ <b>Заказ тугалланди!</b>\n"
                    f"═══════════════════════════════════\n"
                    f"🆔 {order['order_number']}\n"
                    f"👨‍🔧 Уста: {update.effective_user.full_name}\n"
                    f"💰 Тўлов: {order['price']:,} сўм – {payment_type}\n"
                    f"📸 Натижа расми: {len(photo_list)} та\n"
                    f"═══════════════════════════════════\n",
                    parse_mode=ParseMode.HTML
                )
            
            await update.message.reply_text(
                f"🎉 <b>ИШ ТУГАЛЛАНДИ!</b>\n"
                f"═══════════════════════════════════\n"
                f"🆔 {order['order_number']}\n"
                f"💰 Тўлов: {order['price']:,} сўм – {payment_type} – ✅ Олинди\n"
                f"📸 Натижа расми: {len(photo_list)} та\n"
                f"═══════════════════════════════════\n\n"
                f"🏠 Bosh menyu",
                reply_markup=get_main_keyboard("usta"),
                parse_mode=ParseMode.HTML
            )
            
            # Clear context
            context.user_data['waiting_complete'] = False
            context.user_data['waiting_complete_photos'] = False
            context.user_data['waiting_payment'] = False
            context.user_data['waiting_payment_confirm'] = False
            context.user_data['complete_photos'] = []
            context.user_data['complete_orders'] = []
            
    elif update.message.text == "❌ Yo'q":
        await update.message.reply_text(
            "❌ Тўлов олинмаган!\n\n"
            "Илтимос, тўловни олинг ва қайта урининг.",
            reply_markup=ReplyKeyboardMarkup([
                ["✅ Ha", "❌ Yo'q"],
                ["🔙 Orqaga"]
            ], resize_keyboard=True)
        )

# ---------- RATING ----------

async def rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rating callback"""
    query = update.callback_query
    await query.answer()
    
    try:
        parts = query.data.split("_")
        rating = int(parts[1])
        order_id = int(parts[2])
    except:
        await query.edit_message_text("❌ Хатолик! Қайта уриниб кўринг.")
        return
    
    order = await get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Буюртма топилмади!")
        return
    
    # Save rating
    await save_rating(
        order_id=order_id,
        from_user_id=query.from_user.id,
        to_user_id=order.get('master_id', 0),
        rating=rating
    )
    
    await query.edit_message_text(
        f"✅ <b>Рейтинг қолдирилди!</b>\n"
        f"⭐ {rating} юлдуз\n\n"
        f"📝 <b>Шарҳ ёзишни хоҳласангиз, матн ёзинг:</b>\n"
        f"(Шарҳ ёзмасангиз, /start босинг)",
        parse_mode=ParseMode.HTML
    )
    
    context.user_data['rating_order_id'] = order_id
    context.user_data['waiting_review'] = True

async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle review"""
    if not context.user_data.get('waiting_review'):
        return
    
    review = update.message.text
    order_id = context.user_data.get('rating_order_id')
    
    if order_id:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE orders SET review = $1 WHERE id = $2",
                review, order_id
            )
        
        await update.message.reply_text(
            f"✅ <b>Шарҳ қолдирилди!</b>\n"
            f"📝 \"{review}\"\n\n"
            f"🏠 Bosh menyu",
            reply_markup=get_main_keyboard("mijoz"),
            parse_mode=ParseMode.HTML
        )
    
    context.user_data['waiting_review'] = False

# ---------- MY ORDERS ----------

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's orders"""
    user_id = update.effective_user.id
    orders = await get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text(
            "📋 <b>Сизда буюртмалар йўқ.</b>\n\n"
            "🛒 Янги буюртма бериш учун [🛒 Buyurtma berish] босинг.",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = "📋 <b>Сизнинг буюртмаларингиз:</b>\n\n"
    for order in orders[:10]:
        status_emoji = {
            "yangi": "🆕",
            "taklif_yuborildi": "📨",
            "qabul_qilindi": "✅",
            "jarayonda": "🔧",
            "tugallandi": "✅",
            "rad_etildi": "❌"
        }.get(order.get('status', ''), "📌")
        
        text += f"{status_emoji} {order['order_number']} – {order['service_name']}\n"
        text += f"   📊 Ҳолат: {order['status']}\n"
        text += f"   💰 {order['price']:,} сўм\n\n"
    
    if len(orders) > 10:
        text += f"📊 Жами: {len(orders)} та буюртма\n"
        text += f"📌 Батафсил маълумот учун /start босинг."
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ---------- ORDER STATUS ----------

async def order_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check order status"""
    user_id = update.effective_user.id
    orders = await get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text(
            "📋 <b>Сизда буюртмалар йўқ.</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = "🔍 <b>Охирги буюртмаларингиз ҳолати:</b>\n\n"
    for order in orders[:5]:
        status_map = {
            "yangi": "🆕 Янги",
            "taklif_yuborildi": "📨 Таклиф юборилди",
            "qabul_qilindi": "✅ Қабул қилинди",
            "jarayonda": "🔧 Жараёнда",
            "tugallandi": "✅ Тугалланди",
            "rad_etildi": "❌ Рад этилди"
        }
        status_text = status_map.get(order.get('status', ''), order.get('status', ''))
        
        text += f"🆔 {order['order_number']}\n"
        text += f"   📊 {status_text}\n"
        text += f"   🛠 {order['service_name']}\n"
        text += f"   💰 {order['price']:,} сўм\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ---------- CANCEL ORDER ----------

async def cancel_order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start cancel order"""
    user_id = update.effective_user.id
    orders = await get_user_orders(user_id, "taklif_yuborildi")
    
    if not orders:
        await update.message.reply_text(
            "❌ Сизда бекор қилиш мумкин бўлган буюртмалар йўқ.\n\n"
            "ℹ️ Фақат 'Таклиф юборилди' ҳолатидаги буюртмаларни бекор қилиш мумкин."
        )
        return
    
    text = "❌ <b>Бекор қилиш мумкин бўлган буюртмалар:</b>\n\n"
    for i, order in enumerate(orders[:5], 1):
        text += f"{i}. 🆔 {order['order_number']} – {order['service_name']}\n"
    
    text += f"\nБекор қилиш учун рақамни (1-{min(5, len(orders))}) ёки ID рақамни ёзинг:"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    context.user_data['cancel_orders'] = orders
    context.user_data['waiting_cancel'] = True

async def handle_cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel order"""
    if not context.user_data.get('waiting_cancel'):
        return
    
    text = update.message.text.strip()
    orders = context.user_data.get('cancel_orders', [])
    
    # Try to get order
    order = None
    try:
        idx = int(text) - 1
        if 0 <= idx < len(orders):
            order = orders[idx]
    except ValueError:
        order = await get_order_by_number(text)
    
    if not order:
        await update.message.reply_text(
            f"❌ Бундай заказ топилмади!\n"
            f"Илтимос, 1-{min(5, len(orders))} оралиғидаги рақам ёки заказ ID ни ёзинг."
        )
        return
    
    context.user_data['cancel_order_id'] = order['id']
    
    await update.message.reply_text(
        f"❌ <b>Бекор қилиш сабабини танланг:</b>\n"
        f"🆔 {order['order_number']}",
        reply_markup=get_cancel_keyboard(),
        parse_mode=ParseMode.HTML
    )
    context.user_data['waiting_cancel_reason'] = True
    context.user_data['waiting_cancel'] = False

async def handle_cancel_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel reason"""
    if not context.user_data.get('waiting_cancel_reason'):
        return
    
    if update.message.text == "🔙 Orqaga":
        context.user_data['waiting_cancel_reason'] = False
        await update.message.reply_text(
            "🔙 Орқага",
            reply_markup=get_main_keyboard("mijoz")
        )
        return
    
    reason = update.message.text
    order_id = context.user_data.get('cancel_order_id')
    
    if order_id:
        await update_order_status(order_id, "bekor_qilingan", cancel_reason=reason)
        order = await get_order(order_id)
        
        # Notify client
        await update.message.reply_text(
            f"❌ <b>Буюртма бекор қилинди!</b>\n"
            f"═══════════════════════════════════\n"
            f"🆔 {order['order_number']}\n"
            f"📝 Сабаб: {reason}\n"
            f"═══════════════════════════════════\n\n"
            f"🔄 Қайта буюртма бериш учун [🛒 Buyurtma berish] босинг.",
            reply_markup=get_main_keyboard("mijoz"),
            parse_mode=ParseMode.HTML
        )
        
        # Notify dispatcher
        for admin_id in ADMIN_IDS:
            await send_message(
                admin_id,
                f"❌ <b>Мижоз буюртмани бекор қилди!</b>\n"
                f"🆔 {order['order_number']}\n"
                f"👤 {order['client_name']}\n"
                f"📝 Сабаб: {reason}",
                parse_mode=ParseMode.HTML
            )
        
        # Notify master if assigned
        if order.get('master_id'):
            await send_message(
                order['master_id'],
                f"❌ <b>Буюртма бекор қилинди!</b>\n"
                f"🆔 {order['order_number']}\n"
                f"👤 Мижоз: {order['client_name']}\n"
                f"📝 Сабаб: {reason}",
                parse_mode=ParseMode.HTML
            )
    
    context.user_data['waiting_cancel_reason'] = False

# ---------- REORDER ----------

async def reorder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start reorder"""
    user_id = update.effective_user.id
    orders = await get_user_orders(user_id, "tugallandi")
    
    if not orders:
        await update.message.reply_text(
            "📋 <b>Тугалланган буюртмалар йўқ.</b>\n\n"
            "🛒 Янги буюртма бериш учун [🛒 Buyurtma berish] босинг.",
            parse_mode=ParseMode.HTML
        )
        return
    
    text = "🔄 <b>Қайта буюртма бериш учун тугалланган буюртмалар:</b>\n\n"
    for i, order in enumerate(orders[:5], 1):
        text += f"{i}. 🆔 {order['order_number']} – {order['service_name']}\n"
        text += f"   💰 {order['price']:,} сўм\n\n"
    
    text += f"\nҚайта буюртма бериш учун рақамни (1-{min(5, len(orders))}) ёки ID рақамни ёзинг:"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    context.user_data['reorder_orders'] = orders
    context.user_data['waiting_reorder'] = True

async def handle_reorder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reorder"""
    if not context.user_data.get('waiting_reorder'):
        return
    
    text = update.message.text.strip()
    orders = context.user_data.get('reorder_orders', [])
    
    # Try to get order
    order = None
    try:
        idx = int(text) - 1
        if 0 <= idx < len(orders):
            order = orders[idx]
    except ValueError:
        order = await get_order_by_number(text)
    
    if not order:
        await update.message.reply_text(
            f"❌ Бундай заказ топилмади!\n"
            f"Илтимос, 1-{min(5, len(orders))} оралиғидаги рақам ёки заказ ID ни ёзинг."
        )
        return
    
    # Create new order from old
    order_data = {
        'user_id': order['user_id'],
        'service_type': order['service_type'],
        'service_name': order['service_name'],
        'client_name': order['client_name'],
        'client_phone': order['client_phone'],
        'address': order['address'],
        'latitude': order.get('latitude'),
        'longitude': order.get('longitude'),
        'description': order.get('description', ''),
        'photo_ids': order.get('photo_ids', '[]'),
        'preferred_time': "Hozir",
        'price': order.get('price', 0)
    }
    
    try:
        new_order_id = await create_order(order_data)
        new_order = await get_order(new_order_id)
        
        await update.message.reply_text(
            f"✅ <b>Қайта буюртма берилди!</b>\n"
            f"═══════════════════════════════════\n"
            f"🆔 ЯНГИ: {new_order['order_number']}\n"
            f"🛠 {new_order['service_name']}\n"
            f"💰 {new_order['price']:,} сўм\n"
            f"═══════════════════════════════════\n\n"
            f"⏳ Усталар таклиф юборилди...",
            reply_markup=get_main_keyboard("mijoz"),
            parse_mode=ParseMode.HTML
        )
        
        # Send to dispatcher
        await send_order_to_dispatcher(new_order)
        await send_order_to_all_masters(new_order)
        
    except Exception as e:
        logger.error(f"Reorder error: {e}")
        await update.message.reply_text(
            f"❌ Қайта буюртма беришда хатолик! Қайта уриниб кўринг."
        )
    
    context.user_data['waiting_reorder'] = False

# ---------- BACK TO MENU ----------

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main menu"""
    user = await get_user(update.effective_user.id)
    role = user.get('role', 'mijoz') if user else 'mijoz'
    
    await update.message.reply_text(
        f"🏠 <b>{role.capitalize()} BOSH MENYUSI</b>",
        reply_markup=get_main_keyboard(role),
        parse_mode=ParseMode.HTML
    )

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logout"""
    await update.message.reply_text(
        "👋 Хайр! Қайта кириш учун /start босинг.",
        reply_markup=ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
    )

# ---------- DISPATCHER HANDLERS ----------

async def dispatcher_new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show new orders to dispatcher"""
    user = await get_user(update.effective_user.id)
    if not user or user.get('role') not in ['dispetcher', 'admin']:
        await update.message.reply_text("❌ Бу бўлим фақат диспетчер ва админлар учун!")
        return
    
    orders = await get_all_orders("yangi")
    
    if not orders:
        await update.message.reply_text("📋 Янги буюртмалар йўқ.")
        return
    
    text = f"📨 <b>Янги буюртмалар ({len(orders)} та)</b>\n\n"
    for order in orders[:10]:
        text += f"🆔 {order['order_number']} – {order['service_name']}\n"
        text += f"   👤 {order['client_name']} – 📞 {order['client_phone']}\n"
        text += f"   💰 {order['price']:,} сўм\n"
        text += f"   📍 {order['address']}\n\n"
    
    if len(orders) > 10:
        text += f"📊 Жами: {len(orders)} та буюртма"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ---------- DISPATCHER CALLBACKS ----------

async def dispatcher_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher accepts order"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ Хатолик!")
        return
    
    await update_order_status(order_id, "dispetcher_qabul_qildi")
    await query.edit_message_text(
        query.message.text + "\n\n✅ Диспетчер томонидан қабул қилинди!"
    )

async def dispatcher_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher rejects order"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ Хатолик!")
        return
    
    await update_order_status(order_id, "dispetcher_rad_etdi")
    await query.edit_message_text(
        query.message.text + "\n\n❌ Диспетчер томонидан рад этилди!"
    )

async def dispatcher_send_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher sends order to specific master"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ Хатолик!")
        return
    
    order = await get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Буюртма топилмади!")
        return
    
    masters = await get_masters(order.get('service_type'))
    if not masters:
        await query.edit_message_text("❌ Бу хизмат бўйича усталар топилмади!")
        return
    
    # Send to first master
    await send_order_to_master(order, masters[0]['user_id'])
    await update_order_status(order_id, "taklif_yuborildi", master_id=masters[0]['user_id'])
    
    await query.edit_message_text(
        query.message.text + f"\n\n✅ Устага таклиф юборилди: {masters[0]['full_name']}"
    )

async def dispatcher_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatcher sends order to all masters"""
    query = update.callback_query
    await query.answer()
    
    try:
        order_id = int(query.data.split("_")[2])
    except:
        await query.edit_message_text("❌ Хатолик!")
        return
    
    order = await get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Буюртма топилмади!")
        return
    
    await send_order_to_all_masters(order)
    
    await query.edit_message_text(
        query.message.text + f"\n\n✅ Барча усталарга таклиф юборилди!"
    )

# ---------- UNKNOWN ----------

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown messages"""
    user = await get_user(update.effective_user.id)
    role = user.get('role', 'mijoz') if user else 'mijoz'
    await update.message.reply_text(
        "❌ Тушунмадим! Илтимос, тугмалардан бирини босинг.\n\n"
        "🏠 Bosh menyu учун [🏠 Bosh menyu] босинг.",
        reply_markup=get_main_keyboard(role)
    )

# ============================================================
# MAIN
# ============================================================

application: Application = None

async def main():
    global application
    
    logger.info("🚀 USTA24 DISPATCHER боти ишга тушмоқда...")
    
    # Init database
    await init_db()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ---------- START CONVERSATION ----------
    start_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(lang_selection, pattern="^lang_")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_input)],
            PHONE: [
                MessageHandler(filters.CONTACT, phone_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)
            ],
            ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, role_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(start_conv)
    
    # ---------- ORDER CONVERSATION ----------
    order_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), order_start)],
        states={
            SERVICE_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_service_type)],
            SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_service_name)],
            CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_client_name)],
            CLIENT_PHONE: [
                MessageHandler(filters.CONTACT, order_client_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_client_phone)
            ],
            ADDRESS: [
                MessageHandler(filters.LOCATION, order_address),
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_address)
            ],
            PHOTO: [
                MessageHandler(filters.PHOTO, order_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_photo)
            ],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_description)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_time)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(order_conv)
    
    # ---------- DATE HANDLER ----------
    for date in ["22-08", "23-08", "24-08", "25-08", "26-08", "27-08", "28-08"]:
        application.add_handler(MessageHandler(
            filters.Regex(f"^{date}$"), order_date
        ))
    
    # ---------- MASTER ACCEPT/REJECT ----------
    application.add_handler(MessageHandler(
        filters.Regex("^✅ Buyurtma qabul qilish$"), master_accept_start
    ))
    application.add_handler(CallbackQueryHandler(accept_callback, pattern="^accept_"))
    application.add_handler(CallbackQueryHandler(reject_callback, pattern="^reject_"))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_reject_reason
    ))
    
    # ---------- MASTER START WORK ----------
    application.add_handler(MessageHandler(
        filters.Regex("^🔧 Ishni boshlash$"), master_start_work
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_start_work
    ))
    
    # ---------- MASTER COMPLETE ----------
    application.add_handler(MessageHandler(
        filters.Regex("^✅ Ishni yakunlash$"), master_complete_start
    ))
    application.add_handler(MessageHandler(
        filters.PHOTO, handle_complete_photos
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^✅ ТЎЛОВ$"), ask_complete_payment
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^(💵 Naqd|💳 Plastik|📱 Click|📱 Payme)$"), handle_payment_type
    ))
    application.add_handler(MessageHandler(
        filters.Regex("^(✅ Ha|❌ Yo'q)$"), handle_payment_confirm
    ))
    
    # ---------- MY ORDERS ----------
    application.add_handler(MessageHandler(
        filters.Regex("^📋 Mening buyurtmalarim$"), my_orders
    ))
    
    # ---------- ORDER STATUS ----------
    application.add_handler(MessageHandler(
        filters.Regex("^🔍 Buyurtma holati$"), order_status
    ))
    
    # ---------- CANCEL ORDER ----------
    application.add_handler(MessageHandler(
        filters.Regex("^❌ Buyurtmani bekor qilish$"), cancel_order_start
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_cancel_order
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_cancel_reason
    ))
    
    # ---------- REORDER ----------
    application.add_handler(MessageHandler(
        filters.Regex("^🔁 Qayta buyurtma$"), reorder_start
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_reorder
    ))
    
    # ---------- RATING ----------
    application.add_handler(CallbackQueryHandler(rating_callback, pattern="^rating_"))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_review
    ))
    
    # ---------- DISPATCHER ----------
    application.add_handler(MessageHandler(
        filters.Regex("^📨 Yangi buyurtmalar$"), dispatcher_new_orders
    ))
    application.add_handler(CallbackQueryHandler(dispatcher_accept, pattern="^disp_accept_"))
    application.add_handler(CallbackQueryHandler(dispatcher_reject, pattern="^disp_reject_"))
    application.add_handler(CallbackQueryHandler(dispatcher_send_master, pattern="^disp_master_"))
    application.add_handler(CallbackQueryHandler(dispatcher_send_all, pattern="^disp_all_"))
    
    # ---------- OTHER CALLBACKS ----------
    async def view_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        try:
            order_id = int(query.data.split("_")[2])
        except:
            await query.edit_message_text("❌ Хатолик!")
            return
        
        order = await get_order(order_id)
        if not order:
            await query.edit_message_text("❌ Буюртма топилмади!")
            return
        
        photo_ids = order.get('photo_ids')
        if not photo_ids:
            await query.edit_message_text("📸 Расмлар топилмади!")
            return
        
        try:
            photos = json.loads(photo_ids)
        except:
            photos = []
        
        if not photos:
            await query.edit_message_text("📸 Расмлар топилмади!")
            return
        
        await query.edit_message_text(f"📸 {len(photos)} та расм:")
        for photo_id in photos[:5]:
            await send_photo(query.from_user.id, photo_id)
    
    application.add_handler(CallbackQueryHandler(view_photos, pattern="^view_photos_"))
    
    async def call_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        try:
            order_id = int(query.data.split("_")[1])
        except:
            await query.edit_message_text("❌ Хатолик!")
            return
        
        order = await get_order(order_id)
        if not order:
            await query.edit_message_text("❌ Буюртма топилмади!")
            return
        
        await query.edit_message_text(
            f"📞 <b>Мижоз билан боғланиш:</b>\n"
            f"═══════════════════════════════════\n"
            f"👤 {order['client_name']}\n"
            f"📞 {order['client_phone']}\n"
            f"═══════════════════════════════════\n\n"
            f"🆔 {order['order_number']}",
            parse_mode=ParseMode.HTML
        )
    
    application.add_handler(CallbackQueryHandler(call_client, pattern="^call_"))
    
    async def view_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        try:
            order_id = int(query.data.split("_")[1])
        except:
            await query.edit_message_text("❌ Хатолик!")
            return
        
        order = await get_order(order_id)
        if not order:
            await query.edit_message_text("❌ Буюртма топилмади!")
            return
        
        if order.get('latitude') and order.get('longitude'):
            await query.edit_message_text(
                f"📍 <b>Манзил:</b>\n"
                f"═══════════════════════════════════\n"
                f"{order['address']}\n"
                f"═══════════════════════════════════\n\n"
                f"🌐 Google Maps:\n"
                f"https://maps.google.com/?q={order['latitude']},{order['longitude']}",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.edit_message_text(
                f"📍 <b>Манзил:</b>\n"
                f"═══════════════════════════════════\n"
                f"{order['address']}",
                parse_mode=ParseMode.HTML
            )
    
    application.add_handler(CallbackQueryHandler(view_location, pattern="^location_"))
    
    # ---------- GENERAL HANDLERS ----------
    application.add_handler(MessageHandler(filters.Regex("^🏠 Bosh menyu$"), back_to_menu))
    application.add_handler(MessageHandler(filters.Regex("^🚪 Chiqish$"), logout))
    
    # ---------- UNKNOWN ----------
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    
    # ---------- START POLLING ----------
    logger.info("✅ USTA24 DISPATCHER боти ишга тушди!")
    
    # Start Flask in thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep running
    while True:
        await asyncio.sleep(1)

# ============================================================
# SIGNAL HANDLERS
# ============================================================

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    logger.info("🛑 Бот тўхтатилмоқда...")
    sys.exit(0)

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    # Set signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот тўхтатилди!")
    except Exception as e:
        logger.error(f"❌ Хатолик: {e}")
        sys.exit(1)
