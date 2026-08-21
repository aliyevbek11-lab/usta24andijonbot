import os
import asyncio
import logging
import re
import json
from datetime import datetime, timedelta
from threading import Thread
from typing import Dict, Any, Optional, List

from flask import Flask, request, jsonify

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaDocument,
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

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

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
    raise RuntimeError("MASTERS_GROUP_ID va ADMIN_ID raqam bo'lishi kerak!")

# Conversation states
NAME, PHONE, SERVICE, ADDRESS, DESCRIPTION, CONFIRM = range(6)

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("usta24")

# =========================================================
# FLASK APP
# =========================================================

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI!"

@flask_app.route("/health")
def health():
    return "OK"

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    """Webhook endpoint for receiving updates"""
    try:
        data = request.get_json()
        if data:
            logger.info(f"Webhook received: {data}")
            # Process update asynchronously
            asyncio.create_task(process_webhook_update(data))
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

async def process_webhook_update(data):
    """Process webhook update"""
    try:
        # Handle different update types
        if "message" in data:
            # Process message
            pass
        elif "callback_query" in data:
            # Process callback query
            pass
    except Exception as e:
        logger.error(f"Webhook process error: {e}")

@flask_app.route("/api/order/<int:order_id>", methods=["GET"])
def get_order(order_id):
    """API endpoint to get order details"""
    try:
        # Get order from database
        order = asyncio.run(db_get_order(order_id))
        if order:
            return jsonify(dict(order)), 200
        return jsonify({"error": "Order not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route("/api/orders", methods=["GET"])
def get_orders():
    """API endpoint to get all orders"""
    try:
        status = request.args.get("status")
        orders = asyncio.run(db_get_orders(status))
        return jsonify([dict(o) for o in orders]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@flask_app.route("/api/stats", methods=["GET"])
def get_stats():
    """API endpoint to get statistics"""
    try:
        stats = asyncio.run(db_statistics())
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

# =========================================================
# DATABASE
# =========================================================

db_pool = None

async def init_database():
    global db_pool
    
    if not DATABASE_URL:
        logger.warning("DATABASE_URL topilmadi. Memory rejimida ishlaydi.")
        return
    
    try:
        import asyncpg
        
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        
        async with db_pool.acquire() as conn:
            # Create tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_order_at TIMESTAMP,
                    rating FLOAT DEFAULT 0,
                    total_orders INTEGER DEFAULT 0
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer_id BIGINT NOT NULL,
                    customer_name TEXT,
                    phone TEXT,
                    service TEXT,
                    address TEXT,
                    description TEXT,
                    username TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    master_id BIGINT,
                    master_name TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    accepted_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    rejected_at TIMESTAMP,
                    price NUMERIC(10,2),
                    rating FLOAT DEFAULT 0,
                    feedback TEXT
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS masters (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    username TEXT,
                    specialties TEXT[],
                    rating FLOAT DEFAULT 0,
                    total_orders INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    order_id INTEGER,
                    type TEXT,
                    message TEXT,
                    read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_master ON orders(master_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)
            """)
        
        logger.info("PostgreSQL ulandi.")
        
    except Exception as e:
        logger.exception("PostgreSQL ulanishda xato: %s", e)
        db_pool = None

async def db_execute(query, *args):
    """Execute query with retry logic"""
    if not db_pool:
        return None
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with db_pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            logger.warning(f"DB query attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    return None

async def db_fetch(query, *args):
    """Fetch query with retry logic"""
    if not db_pool:
        return None
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with db_pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.warning(f"DB fetch attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    return None

async def db_fetchrow(query, *args):
    """Fetch row with retry logic"""
    if not db_pool:
        return None
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with db_pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.warning(f"DB fetchrow attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    return None

async def db_fetchval(query, *args):
    """Fetch value with retry logic"""
    if not db_pool:
        return None
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with db_pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        except Exception as e:
            logger.warning(f"DB fetchval attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    return None

# Database functions
async def db_save_customer(telegram_id, name, phone, username):
    if not db_pool:
        return
    try:
        await db_execute("""
            INSERT INTO customers (telegram_id, name, phone, username, last_order_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = COALESCE($2, customers.name),
                phone = COALESCE($3, customers.phone),
                username = COALESCE($4, customers.username),
                last_order_at = NOW()
        """, telegram_id, name, phone, username)
    except Exception as e:
        logger.exception("Customer saqlashda xato: %s", e)

async def db_get_customer(telegram_id):
    if not db_pool:
        return None
    try:
        return await db_fetchrow(
            "SELECT * FROM customers WHERE telegram_id = $1",
            telegram_id
        )
    except Exception as e:
        logger.exception("Customer olishda xato: %s", e)
        return None

async def db_create_order(order):
    if not db_pool:
        return None
    try:
        order_id = await db_fetchval("""
            INSERT INTO orders (
                customer_id, customer_name, phone, service,
                address, description, username, status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'open')
            RETURNING id
        """, 
            order["customer_id"],
            order["name"],
            order["phone"],
            order["service"],
            order["address"],
            order["description"],
            order["username"]
        )
        return int(order_id) if order_id else None
    except Exception as e:
        logger.exception("Order yaratishda xato: %s", e)
        return None

async def db_update_status(order_id, status, master_id=None, master_name=None, price=None):
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
        if timestamp_column:
            if price is not None:
                await db_execute(f"""
                    UPDATE orders
                    SET status = $1, master_id = COALESCE($2, master_id),
                        master_name = COALESCE($3, master_name),
                        {timestamp_column} = NOW(), price = $5
                    WHERE id = $4
                """, status, master_id, master_name, order_id, price)
            else:
                await db_execute(f"""
                    UPDATE orders
                    SET status = $1, master_id = COALESCE($2, master_id),
                        master_name = COALESCE($3, master_name),
                        {timestamp_column} = NOW()
                    WHERE id = $4
                """, status, master_id, master_name, order_id)
        else:
            await db_execute("""
                UPDATE orders
                SET status = $1, master_id = COALESCE($2, master_id),
                    master_name = COALESCE($3, master_name)
                WHERE id = $4
            """, status, master_id, master_name, order_id)
    except Exception as e:
        logger.exception("Order #%s status yangilashda xato: %s", order_id, e)

async def db_get_orders(status=None, limit=100):
    if not db_pool:
        return []
    try:
        if status:
            return await db_fetch("""
                SELECT * FROM orders
                WHERE status = $1
                ORDER BY id DESC
                LIMIT $2
            """, status, limit)
        return await db_fetch("""
            SELECT * FROM orders
            ORDER BY id DESC
            LIMIT $1
        """, limit)
    except Exception as e:
        logger.exception("Orderlarni olishda xato: %s", e)
        return []

async def db_get_order(order_id):
    if not db_pool:
        return None
    try:
        return await db_fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
    except Exception as e:
        logger.exception("Order olishda xato: %s", e)
        return None

async def db_statistics():
    result = {
        "total": 0, "open": 0, "accepted": 0,
        "in_progress": 0, "completed": 0,
        "cancelled": 0, "rejected": 0
    }
    if not db_pool:
        return result
    try:
        rows = await db_fetch("""
            SELECT status, COUNT(*) AS count
            FROM orders
            GROUP BY status
        """)
        for row in rows:
            status = row["status"]
            count = int(row["count"])
            if status in result:
                result[status] = count
            result["total"] += count
        return result
    except Exception as e:
        logger.exception("Statistika xatosi: %s", e)
        return result

async def db_save_master(telegram_id, name, phone, username, specialties=None):
    if not db_pool:
        return
    try:
        await db_execute("""
            INSERT INTO masters (telegram_id, name, phone, username, specialties)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = COALESCE($2, masters.name),
                phone = COALESCE($3, masters.phone),
                username = COALESCE($4, masters.username),
                specialties = COALESCE($5, masters.specialties)
        """, telegram_id, name, phone, username, specialties or [])
    except Exception as e:
        logger.exception("Master saqlashda xato: %s", e)

async def db_get_master(telegram_id):
    if not db_pool:
        return None
    try:
        return await db_fetchrow(
            "SELECT * FROM masters WHERE telegram_id = $1",
            telegram_id
        )
    except Exception as e:
        logger.exception("Master olishda xato: %s", e)
        return None

async def db_add_notification(user_id, order_id, type, message):
    if not db_pool:
        return
    try:
        await db_execute("""
            INSERT INTO notifications (user_id, order_id, type, message)
            VALUES ($1, $2, $3, $4)
        """, user_id, order_id, type, message)
    except Exception as e:
        logger.exception("Notification saqlashda xato: %s", e)

async def db_get_notifications(user_id, limit=50):
    if not db_pool:
        return []
    try:
        return await db_fetch("""
            SELECT * FROM notifications
            WHERE user_id = $1 AND read = FALSE
            ORDER BY created_at DESC
            LIMIT $2
        """, user_id, limit)
    except Exception as e:
        logger.exception("Notification olishda xato: %s", e)
        return []

# =========================================================
# MEMORY CACHE
# =========================================================

memory_orders: Dict[int, Dict] = {}
user_orders: Dict[int, Dict] = {}
order_counter = 0

# =========================================================
# MENUS
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup([
        ["🛠 Usta chaqirish", "👤 Mening buyurtmalarim"],
        ["📋 Xizmatlar", "📞 Aloqa", "⭐ Reyting"],
    ], resize_keyboard=True)

def dispatcher_menu():
    return ReplyKeyboardMarkup([
        ["🆕 Yangi buyurtmalar", "🟡 Qabul qilingan"],
        ["🔵 Ish jarayonida", "✅ Yakunlangan"],
        ["❌ Bekor qilingan", "🚫 Rad etilgan"],
        ["📋 Barcha buyurtmalar", "📊 Statistika"],
        ["👥 Ustalar", "📨 Xabarlar"],
    ], resize_keyboard=True)

def service_menu():
    return ReplyKeyboardMarkup([
        ["🪑 Mebel yig'ish", "🔧 Mebel ta'mirlash"],
        ["🍽 Oshxona mebellari", "🚪 Shkaf"],
        ["🛏 Krovat", "🪑 Stol va stul"],
        ["📦 Mebel qismlarga ajratish", "🚚 Yuk tashish"],
        ["🏠 Uy ko'chirish", "🔩 Santexnika"],
        ["⚡ Elektr", "🔥 Payvandlash"],
        ["🔨 Boshqa xizmat", "⬅️ Orqaga"],
    ], resize_keyboard=True)

def master_menu():
    return ReplyKeyboardMarkup([
        ["📋 Mening buyurtmalarim", "✅ Bajarilgan"],
        ["📊 Mening statistikam", "⚙️ Sozlamalar"],
    ], resize_keyboard=True)

# =========================================================
# BOT COMMANDS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    if user:
        # Check if user is master
        master = await db_get_master(user.id)
        if master:
            await update.message.reply_text(
                f"👋 Assalomu alaykum, usta {master['name']}!\n\n"
                "🏠 USTA 24 boshqaruv paneli",
                reply_markup=master_menu()
            )
            return
    
    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "🏠 USTA 24 xizmatiga xush kelibsiz!\n\n"
        "🔧 Uy va ofis uchun ustalar xizmatlari.\n"
        "📍 Andijon shahri\n\n"
        "Kerakli xizmatni tanlang:",
        reply_markup=main_menu()
    )

async def dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ Sizda dispetcher paneliga kirish huquqi yo'q.")
        return
    
    await update.message.reply_text(
        "🛠 USTA 24 DISPETCHER PANELI\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=dispatcher_menu()
    )

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's orders"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    orders = await db_get_orders()  # Get all orders, filter by customer_id
    
    user_orders_list = [o for o in orders if o["customer_id"] == user.id]
    
    if not user_orders_list:
        await update.message.reply_text(
            "📭 Sizning buyurtmalaringiz yo'q.",
            reply_markup=main_menu()
        )
        return
    
    text = "📋 SIZNING BUYURTMALARINGIZ\n\n"
    for order in user_orders_list[:10]:  # Show last 10
        text += format_order(order) + "\n"
    
    if len(user_orders_list) > 10:
        text += f"\n📌 Yana {len(user_orders_list) - 10} ta buyurtma bor"
    
    await update.message.reply_text(text, reply_markup=main_menu())

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show rating system info"""
    if not update.message:
        return
    
    await update.message.reply_text(
        "⭐ USTA 24 REYTING TIZIMI\n\n"
        "🟢 5 yulduz - A'lo darajadagi xizmat\n"
        "🟡 4 yulduz - Yaxshi xizmat\n"
        "🟠 3 yulduz - Qoniqarli xizmat\n"
        "🔴 2 yulduz - Yomon xizmat\n"
        "⭕ 1 yulduz - Juda yomon xizmat\n\n"
        "Buyurtma tugagandan so'ng ustani baholashingiz mumkin.",
        reply_markup=main_menu()
    )

# =========================================================
# ORDER HANDLERS
# =========================================================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    user_id = user.id
    
    # Check if user already has an order in progress
    if user_id in user_orders:
        await update.message.reply_text(
            "⏳ Sizda to'liqsiz buyurtma mavjud. Iltimos, uni tugating.",
            reply_markup=main_menu()
        )
        return
    
    customer = await db_get_customer(user_id)
    
    if customer and customer["name"] and customer["phone"]:
        user_orders[user_id] = {
            "step": "service",
            "name": customer["name"],
            "phone": customer["phone"],
            "editing": False
        }
        await update.message.reply_text(
            f"👋 Salom, {customer['name']}!\n\n"
            "Sizni esladik. ✅\n"
            "Ism va telefon raqamingiz saqlangan.\n\n"
            "3️⃣ Qanday xizmat kerak?",
            reply_markup=service_menu()
        )
        return
    
    user_orders[user_id] = {"step": "name"}
    await update.message.reply_text(
        "📝 Buyurtma berish\n\n"
        "1️⃣ Mijoz ismingizni yozing:"
    )

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm order before sending to masters"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user or user.id not in user_orders:
        return
    
    order = user_orders[user.id]
    
    if order.get("step") != "confirm":
        return
    
    text = (
        "📋 BUYURTMA MA'LUMOTLARI\n\n"
        f"👤 Ism: {order.get('name', '-')}\n"
        f"📞 Telefon: {order.get('phone', '-')}\n"
        f"🛠 Xizmat: {order.get('service', '-')}\n"
        f"📍 Manzil: {order.get('address', '-')}\n"
        f"📝 Izoh: {order.get('description', '-')}\n\n"
        "✅ Buyurtmani tasdiqlaysizmi?"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm_order"),
            InlineKeyboardButton("✏️ O'zgartirish", callback_data="edit_order"),
        ]
    ])
    
    await update.message.reply_text(text, reply_markup=keyboard)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.contact:
        return
    
    user = update.effective_user
    if not user:
        return
    
    user_id = user.id
    
    if user_id not in user_orders:
        return
    
    order = user_orders[user_id]
    if order.get("step") == "phone":
        phone = update.message.contact.phone_number
        order["phone"] = phone
        order["step"] = "service"
        await update.message.reply_text(
            "3️⃣ Qanday xizmat kerak?",
            reply_markup=service_menu()
        )

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    await update.message.reply_text(
        "🛠 USTA 24 XIZMATLARI\n\n"
        "🪑 Mebel yig'ish va ta'mirlash\n"
        "🍽 Oshxona mebellari\n"
        "🚪 Shkaf yig'ish va ta'mirlash\n"
        "🛏 Krovat yig'ish\n"
        "🪑 Stol va stul yig'ish\n"
        "📦 Mebelni qismlarga ajratish va yig'ish\n"
        "🚚 Uy ko'chirish va yuk tashish\n"
        "🔩 Santexnika ishlari\n"
        "⚡ Elektr ishlari\n"
        "🔥 Payvandlash ishlari\n"
        "🔨 Boshqa xizmatlar\n\n"
        "📞 Buyurtma berish uchun «🛠 Usta chaqirish» tugmasini bosing.",
        reply_markup=main_menu()
    )

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "☎️ Telefon: +998 77 069 00 03\n"
        "📧 Email: info@usta24.uz\n"
        "📍 Andijon shahri\n\n"
        "🕐 Ish vaqti: 24/7\n\n"
        "🛠 Usta chaqirish uchun "
        "«🛠 Usta chaqirish» tugmasini bosing.",
        reply_markup=main_menu()
    )

# =========================================================
# DISPATCHER FUNCTIONS
# =========================================================

async def show_orders(update: Update, status=None, title="📋 BUYURTMALAR"):
    if not update.message:
        return
    
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu bo'lim faqat admin uchun.")
        return
    
    db_orders = await db_get_orders(status)
    
    if db_orders:
        text = f"{title}\n\n"
        for order in db_orders[:20]:  # Limit to 20 orders
            text += format_order(order) + "\n"
        if len(db_orders) > 20:
            text += f"\n📌 Yana {len(db_orders) - 20} ta buyurtma bor"
        await update.message.reply_text(text, reply_markup=dispatcher_menu())
        return
    
    # Check memory orders
    result = []
    for order_id, data in memory_orders.items():
        if status is None or data["status"] == status:
            result.append({
                "id": order_id,
                "customer_name": data["order"].get("name"),
                "phone": data["order"].get("phone"),
                "service": data["order"].get("service"),
                "address": data["order"].get("address"),
                "description": data["order"].get("description"),
                "master_name": data.get("master_name"),
                "status": data["status"]
            })
    
    if not result:
        await update.message.reply_text(
            "📭 Hozircha buyurtmalar yo'q.",
            reply_markup=dispatcher_menu()
        )
        return
    
    text = f"{title}\n\n"
    for order in reversed(result[-20:]):
        text += format_order(order) + "\n"
    
    await update.message.reply_text(text, reply_markup=dispatcher_menu())

async def show_statistics(update: Update):
    if not update.message:
        return
    
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu bo'lim faqat admin uchun.")
        return
    
    stats = await db_statistics()
    
    if not db_pool:
        stats = {
            "total": len(memory_orders),
            "open": 0, "accepted": 0, "in_progress": 0,
            "completed": 0, "cancelled": 0, "rejected": 0
        }
        for data in memory_orders.values():
            status = data["status"]
            if status in stats:
                stats[status] += 1
    
    # Get master statistics
    masters = await db_fetch("SELECT COUNT(*) FROM masters")
    master_count = masters[0]["count"] if masters else 0
    
    # Get today's orders
    today = await db_fetch(
        "SELECT COUNT(*) FROM orders WHERE created_at::date = CURRENT_DATE"
    )
    today_count = today[0]["count"] if today else 0
    
    await update.message.reply_text(
        "📊 USTA 24 STATISTIKA\n\n"
        f"📋 Jami buyurtmalar: {stats['total']}\n"
        f"📅 Bugungi: {today_count}\n"
        f"👨‍🔧 Ustalar soni: {master_count}\n\n"
        f"🆕 Yangi: {stats['open']}\n"
        f"🟡 Qabul qilingan: {stats['accepted']}\n"
        f"🔵 Ish jarayonida: {stats['in_progress']}\n"
        f"✅ Yakunlangan: {stats['completed']}\n"
        f"❌ Bekor qilingan: {stats['cancelled']}\n"
        f"🚫 Rad etilgan: {stats['rejected']}",
        reply_markup=dispatcher_menu()
    )

async def show_masters(update: Update):
    if not update.message:
        return
    
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu bo'lim faqat admin uchun.")
        return
    
    masters = await db_fetch(
        "SELECT * FROM masters ORDER BY rating DESC LIMIT 20"
    )
    
    if not masters:
        await update.message.reply_text(
            "📭 Hozircha ustalar ro'yxatga olinmagan.",
            reply_markup=dispatcher_menu()
        )
        return
    
    text = "👥 USTALAR RO'YXATI\n\n"
    for master in masters:
        specialties = ", ".join(master["specialties"]) if master["specialties"] else "-"
        status = "🟢 Faol" if master["is_active"] else "🔴 Faol emas"
        text += (
            f"👤 {master['name']}\n"
            f"📞 {master['phone'] or '-'}\n"
            f"🛠 {specialties}\n"
            f"⭐ {master['rating']:.1f}\n"
            f"📊 {master['total_orders']} ta buyurtma\n"
            f"📌 {status}\n"
            "──────────────\n"
        )
    
    await update.message.reply_text(text, reply_markup=dispatcher_menu())

async def handle_dispatcher_menu(update: Update, text: str):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ Bu menu faqat admin uchun.")
        return True
    
    mapping = {
        "🆕 Yangi buyurtmalar": ("open", "🆕 YANGI BUYURTMALAR"),
        "🟡 Qabul qilingan": ("accepted", "🟡 QABUL QILINGAN"),
        "🔵 Ish jarayonida": ("in_progress", "🔵 ISH JARAYONIDA"),
        "✅ Yakunlangan": ("completed", "✅ YAKUNLANGAN"),
        "❌ Bekor qilingan": ("cancelled", "❌ BEKOR QILINGAN"),
        "🚫 Rad etilgan": ("rejected", "🚫 RAD ETILGAN"),
        "📋 Barcha buyurtmalar": (None, "📋 BARCHA BUYURTMALAR"),
    }
    
    if text == "📊 Statistika":
        await show_statistics(update)
        return True
    
    if text == "👥 Ustalar":
        await show_masters(update)
        return True
    
    if text in mapping:
        status, title = mapping[text]
        await show_orders(update, status, title)
        return True
    
    return False

# =========================================================
# MASTER FUNCTIONS
# =========================================================

async def master_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show orders assigned to this master"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    orders = await db_fetch(
        "SELECT * FROM orders WHERE master_id = $1 AND status IN ('accepted', 'in_progress')",
        user.id
    )
    
    if not orders:
        await update.message.reply_text(
            "📭 Sizga biriktirilgan faol buyurtmalar yo'q.",
            reply_markup=master_menu()
        )
        return
    
    text = "📋 MENGGA BIRIKTIRILGAN BUYURTMALAR\n\n"
    for order in orders:
        text += format_order(order) + "\n"
    
    await update.message.reply_text(text, reply_markup=master_menu())

async def master_completed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show completed orders by this master"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    orders = await db_fetch(
        "SELECT * FROM orders WHERE master_id = $1 AND status = 'completed' ORDER BY id DESC LIMIT 10",
        user.id
    )
    
    if not orders:
        await update.message.reply_text(
            "📭 Siz hali hech qanday buyurtma bajarmagansiz.",
            reply_markup=master_menu()
        )
        return
    
    text = "✅ BAJARILGAN BUYURTMALAR\n\n"
    for order in orders:
        text += format_order(order) + "\n"
    
    await update.message.reply_text(text, reply_markup=master_menu())

async def master_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show master's statistics"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    master = await db_get_master(user.id)
    if not master:
        await update.message.reply_text(
            "❌ Siz usta sifatida ro'yxatdan o'tmagansiz.",
            reply_markup=main_menu()
        )
        return
    
    # Get statistics
    stats = await db_fetchrow("""
        SELECT 
            COUNT(*) AS total,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed,
            COUNT(CASE WHEN status = 'in_progress' THEN 1 END) AS in_progress,
            COUNT(CASE WHEN status = 'accepted' THEN 1 END) AS accepted
        FROM orders
        WHERE master_id = $1
    """, user.id)
    
    await update.message.reply_text(
        "📊 MENG'A STATISTIKA\n\n"
        f"👤 Usta: {master['name']}\n"
        f"⭐ Reyting: {master['rating']:.1f}\n"
        f"📊 Jami buyurtmalar: {master['total_orders']}\n\n"
        f"📋 Bajarilgan: {stats['completed'] if stats else 0}\n"
        f"🔵 Ish jarayonida: {stats['in_progress'] if stats else 0}\n"
        f"🟡 Qabul qilingan: {stats['accepted'] if stats else 0}",
        reply_markup=master_menu()
    )

async def master_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master settings menu"""
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    master = await db_get_master(user.id)
    if not master:
        await update.message.reply_text("❌ Siz usta sifatida ro'yxatdan o'tmagansiz.")
        return
    
    status = "Faol" if master["is_active"] else "Faol emas"
    await update.message.reply_text(
        "⚙️ USTA SOZLAMALARI\n\n"
        f"👤 Ism: {master['name']}\n"
        f"📞 Telefon: {master['phone'] or '-'}\n"
        f"🛠 Mutaxassislik: {', '.join(master['specialties']) if master['specialties'] else '-'}\n"
        f"📌 Holat: {status}\n\n"
        "🔄 Holatni o'zgartirish uchun pastdagi tugmani bosing.",
        reply_markup=ReplyKeyboardMarkup([
            ["🟢 Faol holat", "🔴 Faol emas"],
            ["⬅️ Orqaga"]
        ], resize_keyboard=True)
    )

# =========================================================
# SEND ORDER TO MASTERS
# =========================================================

async def send_order_to_masters(update: Update, context: ContextTypes.DEFAULT_TYPE, order: Dict):
    global order_counter
    
    user = update.effective_user
    if not user:
        raise RuntimeError("Telegram user topilmadi!")
    
    username = f"@{user.username}" if user.username else "username yo'q"
    
    order["customer_id"] = user.id
    order["username"] = username
    
    await db_save_customer(user.id, order.get("name"), order.get("phone"), username)
    
    db_order_id = await db_create_order(order)
    
    if db_order_id:
        order_id = db_order_id
    else:
        order_counter += 1
        order_id = order_counter
    
    memory_orders[order_id] = {
        "customer_id": user.id,
        "status": "open",
        "master_id": None,
        "master_name": None,
        "order": order.copy()
    }
    
    # Get active masters
    active_masters = await db_fetch(
        "SELECT telegram_id, name FROM masters WHERE is_active = TRUE"
    )
    
    message = (
        "🆕 YANGI BUYURTMA\n\n"
        f"🔢 Buyurtma: #{order_id}\n\n"
        f"👤 Mijoz: {order.get('name', '-')}\n"
        f"📞 Telefon: {order.get('phone', '-')}\n"
        f"🛠 Xizmat: {order.get('service', '-')}\n"
        f"📍 Manzil: {order.get('address', '-')}\n"
        f"📝 Izoh: {order.get('description', '-')}\n\n"
        f"👤 Telegram: {username}\n"
        f"🆔 User ID: {user.id}\n\n"
        "🚨 Usta buyurtmani qabul qilish uchun tugmani bosing."
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Qabul qilish", callback_data=f"accept:{order_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{order_id}"),
        ]
    ])
    
    # Send to masters group
    sent = await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=message,
        reply_markup=keyboard
    )
    
    memory_orders[order_id]["message_id"] = sent.message_id
    
    # Notify active masters individually (optional)
    for master in active_masters:
        try:
            await context.bot.send_message(
                chat_id=master["telegram_id"],
                text=f"🔔 Yangi buyurtma #{order_id} keldi!\n"
                     f"🛠 Xizmat: {order.get('service', '-')}"
            )
        except Exception:
            pass
    
    logger.info("✅ Buyurtma #%s ustalar guruhiga yuborildi.", order_id)
    
    # Add notification for admin
    await db_add_notification(
        ADMIN_ID,
        order_id,
        "new_order",
        f"Yangi buyurtma #{order_id} qabul qilindi"
    )
    
    return order_id

# =========================================================
# ORDER CALLBACKS
# =========================================================

async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    data = query.data or ""
    
    # Handle confirm/cancel order
    if data == "confirm_order":
        user = query.from_user
        if user and user.id in user_orders:
            order = user_orders[user.id]
            try:
                order_id = await send_order_to_masters(update, context, order)
                del user_orders[user.id]
                await query.edit_message_text(
                    f"✅ Buyurtmangiz qabul qilindi!\n\n"
                    f"🔢 Buyurtma №{order_id}\n\n"
                    "👨‍🔧 Buyurtma ustalar guruhiga yuborildi.\n"
                    "📞 Tez orada siz bilan bog'lanamiz.\n\n"
                    "☎️ USTA 24: +998 77 069 00 03",
                    reply_markup=main_menu() if hasattr(query, 'message') else None
                )
            except Exception as e:
                logger.exception("Buyurtma yuborishda xato: %s", e)
                await query.edit_message_text(
                    "❌ Buyurtmani yuborishda xatolik yuz berdi.\n"
                    "Iltimos, qaytadan urinib ko'ring."
                )
        return
    
    if data == "edit_order":
        user = query.from_user
        if user and user.id in user_orders:
            order = user_orders[user.id]
            order["editing"] = True
            order["step"] = "service"
            await query.edit_message_text(
                "✏️ Ma'lumotlarni o'zgartirish.\n\n"
                "Qanday xizmat kerak?",
                reply_markup=service_menu()
            )
        return
    
    if ":" not in data:
        return
    
    action, order_id_text = data.split(":", 1)
    
    try:
        order_id = int(order_id_text)
    except ValueError:
        await query.answer("❌ Buyurtma raqami noto'g'ri.", show_alert=True)
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
                }
            }
            memory_orders[order_id] = order_data
    
    if not order_data:
        await query.answer("❌ Buyurtma topilmadi.", show_alert=True)
        return
    
    master = query.from_user
    master_name = f"@{master.username}" if master.username else master.full_name
    order_info = order_data["order"]
    
    # ACCEPT
    if action == "accept":
        if order_data["status"] != "open":
            await query.answer("⚠️ Bu buyurtmani boshqa usta qabul qilgan.", show_alert=True)
            return
        
        order_data["status"] = "accepted"
        order_data["master_id"] = master.id
        order_data["master_name"] = master_name
        
        await db_update_status(order_id, "accepted", master.id, master_name)
        
        # Save master info
        await db_save_master(master.id, master_name, None, master.username, None)
        
        group_text = (
            "🟡 BUYURTMA QABUL QILINDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n\n"
            f"👤 Mijoz: {order_info.get('name', '-')}\n"
            f"📞 Telefon: {order_info.get('phone', '-')}\n"
            f"🛠 Xizmat: {order_info.get('service', '-')}\n"
            f"📍 Manzil: {order_info.get('address', '-')}\n"
            f"📝 Izoh: {order_info.get('description', '-')}\n\n"
            f"👨‍🔧 Qabul qilgan usta: {master_name}\n\n"
            "🔵 Ishni boshlash uchun tugmani bosing."
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔵 Ishni boshlash", callback_data=f"startjob:{order_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"cancel:{order_id}"),
            ]
        ])
        
        await query.edit_message_text(group_text, reply_markup=keyboard)
        
        # Notify master
        try:
            await context.bot.send_message(
                chat_id=master.id,
                text=(
                    f"🟡 BUYURTMA SIZGA BIRIKTIRILDI\n\n"
                    f"🔢 Buyurtma: #{order_id}\n"
                    f"👤 Mijoz: {order_info.get('name', '-')}\n"
                    f"📞 Telefon: {order_info.get('phone', '-')}\n"
                    f"🛠 Xizmat: {order_info.get('service', '-')}\n"
                    f"📍 Manzil: {order_info.get('address', '-')}\n\n"
                    f"📝 Izoh:\n{order_info.get('description', '-')}\n\n"
                    "🔵 «Ishni boshlash» tugmasini bosing."
                )
            )
        except Exception:
            pass
        
        # Notify customer
        try:
            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"🟡 Buyurtmangiz №{order_id} qabul qilindi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "Tez orada usta ishni boshlaydi.\n\n"
                    "☎️ USTA 24\n+998 77 069 00 03"
                )
            )
        except Exception:
            pass
        
        # Add notification
        await db_add_notification(ADMIN_ID, order_id, "accepted", f"Buyurtma #{order_id} qabul qilindi")
        return
    
    # START JOB
    if action == "startjob":
        if order_data["status"] != "accepted":
            await query.answer("⚠️ Buyurtma ish boshlash holatida emas.", show_alert=True)
            return
        
        if order_data.get("master_id") != master.id:
            await query.answer("❌ Bu buyurtma sizga biriktirilmagan.", show_alert=True)
            return
        
        order_data["status"] = "in_progress"
        await db_update_status(order_id, "in_progress")
        
        group_text = (
            "🔵 ISH JARAYONIDA\n\n"
            f"🔢 Buyurtma: #{order_id}\n\n"
            f"👤 Mijoz: {order_info.get('name', '-')}\n"
            f"📞 Telefon: {order_info.get('phone', '-')}\n"
            f"🛠 Xizmat: {order_info.get('service', '-')}\n"
            f"📍 Manzil: {order_info.get('address', '-')}\n"
            f"📝 Izoh: {order_info.get('description', '-')}\n\n"
            f"👨‍🔧 Usta: {master_name}\n\n"
            "Ish tugagach, «✅ Ishni yakunlash»ni bosing."
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Ishni yakunlash", callback_data=f"complete:{order_id}"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data=f"cancel:{order_id}"),
            ]
        ])
        
        await query.edit_message_text(group_text, reply_markup=keyboard)
        
        # Notify customer
        try:
            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"🔵 Buyurtmangiz №{order_id} bo'yicha ish boshlandi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "☎️ USTA 24\n+998 77 069 00 03"
                )
            )
        except Exception:
            pass
        
        await db_add_notification(ADMIN_ID, order_id, "started", f"Buyurtma #{order_id} ish boshlandi")
        return
    
    # COMPLETE
    if action == "complete":
        if order_data["status"] != "in_progress":
            await query.answer("⚠️ Buyurtma ish jarayonida emas.", show_alert=True)
            return
        
        if order_data.get("master_id") != master.id:
            await query.answer("❌ Bu buyurtma sizga biriktirilmagan.", show_alert=True)
            return
        
        order_data["status"] = "completed"
        await db_update_status(order_id, "completed")
        
        # Update master stats
        await db_execute(
            "UPDATE masters SET total_orders = total_orders + 1 WHERE telegram_id = $1",
            master.id
        )
        
        # Request feedback from customer
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⭐ 1", callback_data=f"rate:{order_id}:1"),
                InlineKeyboardButton("⭐ 2", callback_data=f"rate:{order_id}:2"),
                InlineKeyboardButton("⭐ 3", callback_data=f"rate:{order_id}:3"),
                InlineKeyboardButton("⭐ 4", callback_data=f"rate:{order_id}:4"),
                InlineKeyboardButton("⭐ 5", callback_data=f"rate:{order_id}:5"),
            ]
        ])
        
        try:
            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"✅ Buyurtmangiz №{order_id} yakunlandi!\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "Iltimos, ustani baholang:",
                    reply_markup=keyboard
                )
            
        except Exception:
            pass
        
        completed_text = (
            "✅ ISH YAKUNLANDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n\n"
            f"👤 Mijoz: {order_info.get('name', '-')}\n"
            f"📞 Telefon: {order_info.get('phone', '-')}\n"
            f"🛠 Xizmat: {order_info.get('service', '-')}\n"
            f"📍 Manzil: {order_info.get('address', '-')}\n"
            f"📝 Izoh: {order_info.get('description', '-')}\n\n"
            f"👨‍🔧 Usta: {master_name}\n"
            "📌 Holat: Yakunlandi\n\n"
            "☎️ USTA 24\n+998 77 069 00 03"
        )
        
        await query.edit_message_text(completed_text)
        
        await db_add_notification(ADMIN_ID, order_id, "completed", f"Buyurtma #{order_id} yakunlandi")
        return
    
    # CANCEL
    if action == "cancel":
        if order_data["status"] not in ("accepted", "in_progress"):
            await query.answer("⚠️ Bu buyurtmani hozir bekor qilib bo'lmaydi.", show_alert=True)
            return
        
        if order_data.get("master_id") != master.id:
            await query.answer("❌ Bu buyurtma sizga biriktirilmagan.", show_alert=True)
            return
        
        order_data["status"] = "cancelled"
        await db_update_status(order_id, "cancelled")
        
        cancelled_text = (
            "❌ BUYURTMA BEKOR QILINDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n\n"
            f"👤 Mijoz: {order_info.get('name', '-')}\n"
            f"📞 Telefon: {order_info.get('phone', '-')}\n"
            f"🛠 Xizmat: {order_info.get('service', '-')}\n"
            f"📍 Manzil: {order_info.get('address', '-')}\n"
            f"📝 Izoh: {order_info.get('description', '-')}\n\n"
            f"👨‍🔧 Usta: {master_name}\n"
            "❌ Holat: Bekor qilindi\n\n"
            "☎️ USTA 24\n+998 77 069 00 03"
        )
        
        await query.edit_message_text(cancelled_text)
        
        try:
            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"❌ Buyurtmangiz №{order_id} bekor qilindi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "Yangi buyurtma berishingiz mumkin.\n\n"
                    "☎️ USTA 24\n+998 77 069 00 03"
                )
            )
        except Exception:
            pass
        
        await db_add_notification(ADMIN_ID, order_id, "cancelled", f"Buyurtma #{order_id} bekor qilindi")
        return
    
    # REJECT
    if action == "reject":
        if order_data["status"] != "open":
            await query.answer("⚠️ Bu buyurtma allaqachon o'zgargan.", show_alert=True)
            return
        
        order_data["status"] = "rejected"
        order_data["master_id"] = master.id
        order_data["master_name"] = master_name
        
        await db_update_status(order_id, "rejected", master.id, master_name)
        
        rejected_text = (
            "🚫 BUYURTMA RAD ETILDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n\n"
            f"👤 Mijoz: {order_info.get('name', '-')}\n"
            f"📞 Telefon: {order_info.get('phone', '-')}\n"
            f"🛠 Xizmat: {order_info.get('service', '-')}\n"
            f"📍 Manzil: {order_info.get('address', '-')}\n"
            f"📝 Izoh: {order_info.get('description', '-')}\n\n"
            f"🚫 Rad etgan usta: {master_name}"
        )
        
        await query.edit_message_text(rejected_text)
        
        try:
            await context.bot.send_message(
                chat_id=order_data["customer_id"],
                text=(
                    f"⚠️ Buyurtmangiz №{order_id} "
                    "tanlangan usta tomonidan qabul qilinmadi.\n\n"
                    "Boshqa usta topish uchun dispetcher bilan "
                    "bog'lanishingiz mumkin.\n\n"
                    "☎️ USTA 24\n+998 77 069 00 03"
                )
            )
        except Exception:
            pass
        
        await db_add_notification(ADMIN_ID, order_id, "rejected", f"Buyurtma #{order_id} rad etildi")
        return
    
    # RATE
    if action == "rate":
        _, order_id_str, rating_str = data.split(":", 2)
        order_id = int(order_id_str)
        rating = int(rating_str)
        
        await db_execute(
            "UPDATE orders SET rating = $1 WHERE id = $2",
            rating, order_id
        )
        
        # Update master rating
        row = await db_fetchrow("SELECT master_id FROM orders WHERE id = $1", order_id)
        if row and row["master_id"]:
            master_rating = await db_fetchrow(
                "SELECT AVG(rating) FROM orders WHERE master_id = $1 AND rating > 0",
                row["master_id"]
            )
            if master_rating and master_rating["avg"]:
                await db_execute(
                    "UPDATE masters SET rating = $1 WHERE telegram_id = $2",
                    master_rating["avg"], row["master_id"]
                )
        
        await query.edit_message_text(
            f"⭐ Rahmat! Siz ustani {rating} yulduz bilan baholadingiz.\n\n"
            "☎️ USTA 24\n+998 77 069 00 03"
        )
        return

# =========================================================
# MAIN MESSAGE HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.effective_user
    if not user:
        return
    
    user_id = user.id
    text = (update.message.text or "").strip()
    
    # Check if user is master
    master = await db_get_master(user_id)
    
    # Master menu
    if master and text in ["📋 Mening buyurtmalarim", "✅ Bajarilgan", "📊 Mening statistikam", "⚙️ Sozlamalar"]:
        if text == "📋 Mening buyurtmalarim":
            await master_my_orders(update, context)
        elif text == "✅ Bajarilgan":
            await master_completed(update, context)
        elif text == "📊 Mening statistikam":
            await master_statistics(update, context)
        elif text == "⚙️ Sozlamalar":
            await master_settings(update, context)
        return
    
    # Master status toggle
    if master and text in ["🟢 Faol holat", "🔴 Faol emas"]:
        is_active = text == "🟢 Faol holat"
        await db_execute(
            "UPDATE masters SET is_active = $1 WHERE telegram_id = $2",
            is_active, user_id
        )
        await update.message.reply_text(
            f"✅ Holat o'zgartirildi: {'Faol' if is_active else 'Faol emas'}",
            reply_markup=master_menu()
        )
        return
    
    # Dispatcher menu
    dispatcher_buttons = {
        "🆕 Yangi buyurtmalar", "🟡 Qabul qilingan", "🔵 Ish jarayonida",
        "✅ Yakunlangan", "❌ Bekor qilingan", "🚫 Rad etilgan",
        "📋 Barcha buyurtmalar", "📊 Statistika", "👥 Ustalar"
    }
    
    if text in dispatcher_buttons:
        await handle_dispatcher_menu(update, text)
        return
    
    # Main menu
    if text == "🛠 Usta chaqirish":
        await start_order(update, context)
        return
    
    if text == "📋 Xizmatlar":
        await services(update, context)
        return
    
    if text == "📞 Aloqa":
        await contact(update, context)
        return
    
    if text == "👤 Mening buyurtmalarim":
        await my_orders(update, context)
        return
    
    if text == "⭐ Reyting":
        await rating(update, context)
        return
    
    if text == "⬅️ Orqaga":
        await update.message.reply_text(
            "🏠 Bosh menu",
            reply_markup=main_menu()
        )
        return
    
    # Order flow
    if user_id not in user_orders:
        # Check if it's a service selection from service menu
        service_buttons = [
            "🪑 Mebel yig'ish", "🔧 Mebel ta'mirlash", "🍽 Oshxona mebellari",
            "🚪 Shkaf", "🛏 Krovat", "🪑 Stol va stul", "📦 Mebel qismlarga ajratish",
            "🚚 Yuk tashish", "🏠 Uy ko'chirish", "🔩 Santexnika",
            "⚡ Elektr", "🔥 Payvandlash", "🔨 Boshqa xizmat"
        ]
        
        if text in service_buttons:
            # Start order if not started
            await start_order(update, context)
            # Now handle the service selection
            if user_id in user_orders:
                order = user_orders[user_id]
                if order.get("step") == "service":
                    order["service"] = text
                    order["step"] = "address"
                    await update.message.reply_text(
                        "4️⃣ Manzilingizni yozing:\n\n"
                        "Masalan:\n"
                        "Andijon shahar, Boburshoh ko'chasi, 15-uy"
                    )
            return
        
        await update.message.reply_text(
            "Iltimos, menyudan kerakli xizmatni tanlang.",
            reply_markup=main_menu()
        )
        return
    
    order = user_orders[user_id]
    step = order.get("step")
    editing = order.get("editing", False)
    
    # NAME
    if step == "name":
        if not text:
            await update.message.reply_text("📝 Iltimos, ismingizni yozing:")
            return
        
        order["name"] = text
        order["step"] = "phone"
        
        phone_button = KeyboardButton(
            "📱 Telefon raqamimni yuborish",
            request_contact=True
        )
        keyboard = ReplyKeyboardMarkup(
            [[phone_button]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        
        await update.message.reply_text(
            "2️⃣ Telefon raqamingizni yuboring:",
            reply_markup=keyboard
        )
        return
    
    # SERVICE
    if step == "service":
        service_buttons = [
            "🪑 Mebel yig'ish", "🔧 Mebel ta'mirlash", "🍽 Oshxona mebellari",
            "🚪 Shkaf", "🛏 Krovat", "🪑 Stol va stul", "📦 Mebel qismlarga ajratish",
            "🚚 Yuk tashish", "🏠 Uy ko'chirish", "🔩 Santexnika",
            "⚡ Elektr", "🔥 Payvandlash", "🔨 Boshqa xizmat"
        ]
        
        if text == "⬅️ Orqaga":
            del user_orders[user_id]
            await update.message.reply_text(
                "🏠 Bosh menu",
                reply_markup=main_menu()
            )
            return
        
        if text not in service_buttons:
            await update.message.reply_text(
                "Iltimos, xizmat turini tanlang:",
                reply_markup=service_menu()
            )
            return
        
        order["service"] = text
        order["step"] = "address"
        
        await update.message.reply_text(
            "4️⃣ Manzilingizni yozing:\n\n"
            "Masalan:\n"
            "Andijon shahar, Boburshoh ko'chasi, 15-uy"
        )
        return
    
    # ADDRESS
    if step == "address":
        if not text:
            await update.message.reply_text("📍 Iltimos, manzilingizni yozing.")
            return
        
        order["address"] = text
        order["step"] = "description"
        
        await update.message.reply_text(
            "5️⃣ Buyurtma haqida qisqacha ma'lumot yozing:\n\n"
            "Masalan:\n"
            "Shkaf yig'ish kerak.\n"
            "Yoki:\n"
            "Uy ko'chirish kerak, 3-qavat."
        )
        return
    
    # DESCRIPTION
    if step == "description":
        if not text:
            await update.message.reply_text(
                "📝 Iltimos, buyurtma haqida qisqacha ma'lumot yozing."
            )
            return
        
        order["description"] = text
        order["step"] = "confirm"
        
        # Show confirmation
        await confirm_order(update, context)
        return

# =========================================================
# FORMAT FUNCTIONS
# =========================================================

def format_order(order, status_text=None):
    if isinstance(order, dict):
        order_id = order.get("id", "-")
        name = order.get("customer_name") or order.get("name", "-")
        phone = order.get("phone", "-")
        service = order.get("service", "-")
        address = order.get("address", "-")
        description = order.get("description", "-")
        master = order.get("master_name") or "-"
        status = order.get("status", "-")
    else:
        order_id = order["id"]
        name = order["customer_name"] or "-"
        phone = order["phone"] or "-"
        service = order["service"] or "-"
        address = order["address"] or "-"
        description = order["description"] or "-"
        master = order["master_name"] or "-"
        status = order["status"]
    
    status_display = status_text or status
    
    return (
        f"🔢 Buyurtma: #{order_id}\n"
        f"👤 Mijoz: {name}\n"
        f"📞 Telefon: {phone}\n"
        f"🛠 Xizmat: {service}\n"
        f"📍 Manzil: {address}\n"
        f"📝 Izoh: {description}\n"
        f"👨‍🔧 Usta: {master}\n"
        f"📌 Holat: {status_display}\n"
        "──────────────"
    )

# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("BOT XATOSI:", exc_info=context.error)
    
    # Notify admin
    try:
        if isinstance(update, Update) and update.effective_message:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Bot xatosi:\n{str(context.error)[:200]}"
            )
    except Exception:
        pass

# =========================================================
# RUN BOT
# =========================================================

async def run_bot(application):
    await application.initialize()
    await init_database()
    await application.start()
    
    # Use webhook if URL is provided, else use polling
    if WEBHOOK_URL:
        webhook_path = "/webhook"
        full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
        await application.bot.set_webhook(url=full_webhook_url)
        logger.info(f"✅ Webhook set to: {full_webhook_url}")
    else:
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        logger.info("✅ Telegram polling ishga tushdi.")
    
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if WEBHOOK_URL:
            await application.bot.delete_webhook()
        else:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()

# =========================================================
# MAIN
# =========================================================

def main():
    logger.info("=" * 50)
    logger.info("USTA 24 BOT START")
    logger.info(f"MASTERS_GROUP_ID = {MASTERS_GROUP_ID}")
    logger.info(f"ADMIN_ID = {ADMIN_ID}")
    logger.info(f"DATABASE_URL mavjud: {bool(DATABASE_URL)}")
    logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
    logger.info("=" * 50)
    
    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("dispatcher", dispatcher))
    application.add_handler(CommandHandler("id", chat_id_command))
    application.add_handler(CommandHandler("myorders", my_orders))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(order_callback))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start Flask server
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server ishga tushdi.")
    
    # Run bot
    asyncio.run(run_bot(application))

if __name__ == "__main__":
    main()
