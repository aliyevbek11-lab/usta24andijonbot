import os
import asyncio
import logging
from threading import Thread
from datetime import datetime, timedelta

import asyncpg
from flask import Flask
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# USTA 24 PRO FULL
# Python 3.13 + python-telegram-bot 22.3 + PostgreSQL
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("usta24")

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")
if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

try:
    MASTERS_GROUP_ID = int(str(MASTERS_GROUP_ID).strip())
    ADMIN_ID = int(str(ADMIN_ID).strip())
except ValueError as exc:
    raise RuntimeError("ADMIN_ID va MASTERS_GROUP_ID raqam bo'lishi kerak!") from exc

PHONE = "+998 77 069 00 03"

SERVICES = [
    "🪑 Mebel",
    "🚚 Yuk tashish / ko‘chirish",
    "🔩 Santexnika",
    "⚡ Elektr",
    "🔥 Payvandlash",
    "🔨 Boshqa xizmat",
]

STATUS_TEXT = {
    "open": "🆕 Янги",
    "accepted": "🟡 Қабул қилинган",
    "in_progress": "🔵 Иш жараёнида",
    "completed": "✅ Якунланган",
    "cancelled": "❌ Бекор қилинган",
    "rejected": "🚫 Рад этилган",
}

# =========================================================
# FLASK HEALTH SERVER
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "USTA 24 PRO FULL ISHLAYAPTI!"

@app.route("/health")
def health():
    return "OK"

def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)

# =========================================================
# GLOBAL STATE
# =========================================================

db_pool = None
user_states = {}
broadcast_states = {}

# =========================================================
# DATABASE
# =========================================================

async def init_database():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                name TEXT,
                phone TEXT,
                username TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                created_at TIMESTAMP DEFAULT NOW(),
                last_order_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                username TEXT,
                service TEXT,
                active BOOLEAN DEFAULT TRUE,
                rating NUMERIC DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
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
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                status TEXT NOT NULL DEFAULT 'open',
                master_id BIGINT,
                master_name TEXT,
                price NUMERIC DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                rejected_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS order_history (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT,
                changed_by BIGINT,
                changed_by_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                order_id INTEGER UNIQUE NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS price_settings (
                id SERIAL PRIMARY KEY,
                service TEXT UNIQUE NOT NULL,
                base_price NUMERIC DEFAULT 0,
                unit TEXT DEFAULT 'order',
                active BOOLEAN DEFAULT TRUE
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                order_id INTEGER,
                customer_id BIGINT,
                notification_type TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_history (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Migration: old databases
        customer_columns = [
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_order_at TIMESTAMP",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS username TEXT",
        ]
        order_columns = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS username TEXT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS master_id BIGINT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS master_name TEXT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS started_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP",
        ]
        for sql in customer_columns + order_columns:
            try:
                await conn.execute(sql)
            except Exception:
                logger.exception("Migration xatosi: %s", sql)

        for service in SERVICES:
            await conn.execute("""
                INSERT INTO price_settings(service, base_price)
                VALUES($1, 0)
                ON CONFLICT(service) DO NOTHING
            """, service)

    logger.info("PostgreSQL tayyor.")

# =========================================================
# DATABASE HELPERS
# =========================================================

async def save_customer(telegram_id, name=None, phone=None, username=None,
                        latitude=None, longitude=None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO customers
                (telegram_id, name, phone, username, latitude, longitude, last_order_at)
            VALUES($1,$2,$3,$4,$5,$6,NOW())
            ON CONFLICT(telegram_id) DO UPDATE SET
                name = COALESCE($2, customers.name),
                phone = COALESCE($3, customers.phone),
                username = COALESCE($4, customers.username),
                latitude = COALESCE($5, customers.latitude),
                longitude = COALESCE($6, customers.longitude),
                last_order_at = NOW()
        """, telegram_id, name, phone, username, latitude, longitude)

async def get_customer(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM customers WHERE telegram_id=$1", telegram_id
        )

async def create_order(data):
    async with db_pool.acquire() as conn:
        return int(await conn.fetchval("""
            INSERT INTO orders(
                customer_id, customer_name, phone, service, address,
                description, username, latitude, longitude, status, price
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'open',$10)
            RETURNING id
        """,
            data["customer_id"], data["name"], data["phone"], data["service"],
            data["address"], data["description"], data["username"],
            data.get("latitude"), data.get("longitude"), data.get("price", 0)
        ))

async def get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM orders WHERE id=$1", order_id
        )

async def update_order_status(order_id, new_status, user_id=None, user_name=None):
    timestamp_map = {
        "accepted": "accepted_at",
        "in_progress": "started_at",
        "completed": "completed_at",
        "cancelled": "cancelled_at",
        "rejected": "rejected_at",
    }
    async with db_pool.acquire() as conn:
        old_status = await conn.fetchval(
            "SELECT status FROM orders WHERE id=$1", order_id
        )
        if not old_status:
            return False

        if new_status in timestamp_map:
            column = timestamp_map[new_status]
            await conn.execute(
                f"UPDATE orders SET status=$1, {column}=NOW() WHERE id=$2",
                new_status, order_id
            )
        else:
            await conn.execute(
                "UPDATE orders SET status=$1 WHERE id=$2",
                new_status, order_id
            )

        await conn.execute("""
            INSERT INTO order_history(
                order_id, old_status, new_status, changed_by, changed_by_name
            )
            VALUES($1,$2,$3,$4,$5)
        """, order_id, old_status, new_status, user_id, user_name)
        return True

async def assign_master(order_id, master_id, master_name):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders
            SET master_id=$1, master_name=$2
            WHERE id=$3
        """, master_id, master_name, order_id)

async def add_master(telegram_id, name, phone=None, username=None, service=None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO masters(telegram_id,name,phone,username,service,active)
            VALUES($1,$2,$3,$4,$5,TRUE)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=$2, phone=$3, username=$4, service=$5, active=TRUE
        """, telegram_id, name, phone, username, service)

async def remove_master(telegram_id):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE masters SET active=FALSE WHERE telegram_id=$1",
            telegram_id
        )

async def get_active_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM masters
            WHERE active=TRUE
            ORDER BY rating DESC, completed_orders DESC, name
        """)

async def get_master(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM masters WHERE telegram_id=$1", telegram_id
        )

async def get_base_price(service):
    async with db_pool.acquire() as conn:
        value = await conn.fetchval("""
            SELECT base_price FROM price_settings
            WHERE service=$1 AND active=TRUE
        """, service)
        return float(value or 0)

async def set_base_price(service, price):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO price_settings(service,base_price)
            VALUES($1,$2)
            ON CONFLICT(service) DO UPDATE SET
                base_price=$2, active=TRUE
        """, service, price)

# =========================================================
# REVIEWS / RATING
# =========================================================

async def save_review(order_id, customer_id, rating, comment=None):
    async with db_pool.acquire() as conn:
        order = await conn.fetchrow(
            "SELECT customer_id, master_id, status FROM orders WHERE id=$1",
            order_id
        )
        if not order or order["customer_id"] != customer_id:
            return False

        await conn.execute("""
            INSERT INTO reviews(order_id,customer_id,master_id,rating,comment)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(order_id) DO UPDATE SET
                rating=$4, comment=$5
        """, order_id, customer_id, order["master_id"], rating, comment)

        if order["master_id"]:
            stats = await conn.fetchrow("""
                SELECT AVG(rating) AS avg_rating, COUNT(*) AS cnt
                FROM reviews WHERE master_id=$1
            """, order["master_id"])
            await conn.execute("""
                UPDATE masters
                SET rating=$1, rating_count=$2
                WHERE telegram_id=$3
            """, float(stats["avg_rating"] or 0),
                int(stats["cnt"] or 0),
                order["master_id"])
        return True

# =========================================================
# STATS
# =========================================================

async def statistics():
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM orders")
        rows = await conn.fetch("""
            SELECT status, COUNT(*) AS count
            FROM orders GROUP BY status
        """)
    result = {key: 0 for key in STATUS_TEXT}
    result["total"] = int(total or 0)
    for row in rows:
        if row["status"] in result:
            result[row["status"]] = int(row["count"])
    return result

async def period_statistics(days):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT
                COUNT(*) total,
                COUNT(*) FILTER(WHERE status='completed') completed,
                COUNT(*) FILTER(WHERE status='cancelled') cancelled,
                COUNT(*) FILTER(WHERE status='rejected') rejected,
                COALESCE(SUM(price) FILTER(WHERE status='completed'),0) revenue
            FROM orders
            WHERE created_at >= $1
        """, datetime.now() - timedelta(days=days))

async def master_statistics():
    async with db_pool.acquire() as conn:
        return await conn.fetch("""
            SELECT m.*,
                   COUNT(o.id) AS total_orders,
                   COUNT(o.id) FILTER(WHERE o.status='completed') AS completed_db
            FROM masters m
            LEFT JOIN orders o ON o.master_id=m.telegram_id
            GROUP BY m.id
            ORDER BY m.completed_orders DESC, m.rating DESC, m.name
        """)

# =========================================================
# MENUS
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup([
        ["🛠 Уста чақириш"],
        ["📋 Хизматлар", "📞 Алоқа"],
        ["🔁 Қайта буюртма"],
    ], resize_keyboard=True)

def service_menu():
    return ReplyKeyboardMarkup([
        ["🪑 Мебел"],
        ["🚚 Yuk tashish / ko‘chirish"],
        ["🔩 Santexnika"],
        ["⚡ Elektr"],
        ["🔥 Payvandlash"],
        ["🔨 Boshqa xizmat"],
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["🆕 Янги буюртмалар", "📋 Барча буюртмалар"],
        ["👤 Мижозлар", "👨‍🔧 Усталар"],
        ["📊 Статистика", "📈 Ҳисобот"],
        ["➕ Уста қўшиш", "❌ Уста ўчириш"],
        ["💰 Нархлар", "📢 Хабар тарқатиш"],
    ], resize_keyboard=True)

def location_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📍 Геолокациямни юбориш", request_location=True)],
        ["📍 Манзилни қўлда ёзиш"],
    ], resize_keyboard=True, one_time_keyboard=True)

# =========================================================
# START / BASIC
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 PRO FULL\n"
        "Уй, мебель, юк ташиш ва бошқа хизматлар.\n\n"
        "Керакли хизматни танланг:",
        reply_markup=main_menu()
    )

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 USTA 24 ХИЗМАТЛАРИ\n\n"
        "🪑 Мебель йиғиш/таъмирлаш\n"
        "🍽 Ошхона мебели\n"
        "🚪 Шкаф\n"
        "🛏 Кровать\n"
        "📦 Мебель ажратиш/йиғиш\n"
        "🚚 Мебель ташиш\n"
        "🏠 Уй кўчириш\n"
        "🔩 Сантехника\n"
        "⚡ Электр\n"
        "🔥 Пайвандлаш\n"
        "🔨 Бошқа хизмат",
        reply_markup=main_menu()
    )

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📞 USTA 24\n\n☎️ {PHONE}\n📍 Андижон шаҳри",
        reply_markup=main_menu()
    )

# =========================================================
# ORDER FLOW
# =========================================================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    customer = await get_customer(user.id)

    state = {"step": "name"}
    if customer and customer["name"]:
        state.update({
            "name": customer["name"],
            "phone": customer["phone"],
            "step": "service",
        })
        user_states[user.id] = state
        await update.message.reply_text(
            f"👋 Салом, {customer['name']}!\n\n🛠 Хизматни танланг:",
            reply_markup=service_menu()
        )
    else:
        user_states[user.id] = state
        await update.message.reply_text("📝 1️⃣ Исмингизни ёзинг:")

async def create_and_send_order(update, context, state):
    user = update.effective_user
    username = f"@{user.username}" if user.username else None

    await save_customer(
        user.id, state.get("name"), state.get("phone"), username,
        state.get("latitude"), state.get("longitude")
    )

    order_id = await create_order({
        "customer_id": user.id,
        "name": state.get("name"),
        "phone": state.get("phone"),
        "service": state.get("service"),
        "address": state.get("address"),
        "description": state.get("description"),
        "username": username,
        "latitude": state.get("latitude"),
        "longitude": state.get("longitude"),
        "price": state.get("price", 0),
    })

    await send_order_to_group(context, order_id)
    user_states.pop(user.id, None)

    await update.message.reply_text(
        f"✅ Буюртмангиз қабул қилинди!\n\n"
        f"🔢 Буюртма №{order_id}\n"
        "👨‍🔧 Усталар гуруҳига юборилди.\n"
        "📞 Тез орада сиз билан боғланишади.\n\n"
        f"☎️ {PHONE}",
        reply_markup=main_menu()
    )

async def send_order_to_group(context, order_id):
    order = await get_order(order_id)
    if not order:
        return

    location = "-"
    if order["latitude"] is not None and order["longitude"] is not None:
        location = (
            f"https://maps.google.com/?q="
            f"{order['latitude']},{order['longitude']}"
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍🔧 Ўзимга олиш", callback_data=f"take:{order_id}")],
        [
            InlineKeyboardButton("🔄 Бошқа устага", callback_data=f"assign:{order_id}"),
            InlineKeyboardButton("🚫 Рад этиш", callback_data=f"reject:{order_id}")
        ],
    ])

    text = (
        "🆕 USTA 24 — ЯНГИ БУЮРТМА\n\n"
        f"🔢 Буюртма: #{order_id}\n"
        f"👤 Мижоз: {order['customer_name'] or '-'}\n"
        f"📞 Телефон: {order['phone'] or '-'}\n"
        f"🛠 Хизмат: {order['service'] or '-'}\n"
        f"📍 Манзил: {order['address'] or '-'}\n"
        f"🗺 Геолокация: {location}\n"
        f"📝 Изоҳ: {order['description'] or '-'}\n"
        f"💰 Нарх асоси: {order['price'] or 0}\n\n"
        "👨‍🔧 Қабул қилиш ёки рад этиш:"
    )
    await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        reply_markup=keyboard
    )

# =========================================================
# CALLBACKS
# =========================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    parts = data.split(":")
    action = parts[0]

    try:
        order_id = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return

    actor = query.from_user
    actor_name = actor.full_name

    # Rating is customer action: rate:ORDER:RATING
    if action == "rate" and len(parts) == 3:
        try:
            rating = int(parts[2])
        except ValueError:
            return
        ok = await save_review(order_id, actor.id, rating)
        if ok:
            await query.edit_message_text(f"⭐ Рейтинг қабул қилинди: {rating}/5\nРаҳмат!")
        else:
            await query.answer("❌ Бу рейтингни бериш ҳуқуқингиз йўқ.", show_alert=True)
        return

    order = await get_order(order_id)
    if not order:
        await query.answer("❌ Буюртма топилмади.", show_alert=True)
        return

    # TAKE
    if action == "take":
        if order["status"] != "open":
            await query.answer("⚠️ Буюртма аллақачон ўзгарган.", show_alert=True)
            return

        await add_master(
            actor.id, actor.full_name,
            username=f"@{actor.username}" if actor.username else None
        )
        await assign_master(order_id, actor.id, actor_name)
        await update_order_status(order_id, "accepted", actor.id, actor_name)

        await query.edit_message_text(
            f"🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
            f"🔢 #{order_id}\n👨‍🔧 Уста: {actor_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔵 Ишни бошлаш", callback_data=f"start:{order_id}")],
                [InlineKeyboardButton("❌ Бекор қилиш", callback_data=f"cancel:{order_id}")]
            ])
        )
        await safe_send(
            context, order["customer_id"],
            f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n👨‍🔧 Уста: {actor_name}\n☎️ {PHONE}"
        )
        return

    # START
    if action == "start":
        if order["master_id"] != actor.id:
            await query.answer("❌ Бу буюртма сизга бириктирилмаган.", show_alert=True)
            return
        if order["status"] != "accepted":
            await query.answer("⚠️ Ҳолат ўзгарган.", show_alert=True)
            return

        await update_order_status(order_id, "in_progress", actor.id, actor_name)
        await query.edit_message_text(
            f"🔵 ИШ ЖАРАЁНИДА\n\n🔢 #{order_id}\n👨‍🔧 {actor_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ишни якунлаш", callback_data=f"complete:{order_id}")],
                [InlineKeyboardButton("❌ Бекор қилиш", callback_data=f"cancel:{order_id}")]
            ])
        )
        await safe_send(context, order["customer_id"],
                        f"🔵 Буюртма №{order_id} бўйича иш бошланди.\n👨‍🔧 {actor_name}")
        return

    # COMPLETE
    if action == "complete":
        if order["master_id"] != actor.id:
            await query.answer("❌ Бу буюртма сизга бириктирилмаган.", show_alert=True)
            return
        if order["status"] != "in_progress":
            await query.answer("⚠️ Буюртма иш жараёнида эмас.", show_alert=True)
            return

        await update_order_status(order_id, "completed", actor.id, actor_name)
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE masters SET completed_orders=completed_orders+1 WHERE telegram_id=$1",
                actor.id
            )

        await query.edit_message_text(
            f"✅ ИШ ЯКУНЛАНДИ\n\n🔢 #{order_id}\n👨‍🔧 {actor_name}\n\n⭐ Мижоздан рейтинг сўралди."
        )
        await safe_send(
            context, order["customer_id"],
            f"✅ Буюртмангиз №{order_id} якунланди.\n👨‍🔧 Уста: {actor_name}\n\n⭐ Хизматни баҳоланг:",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("1⭐", callback_data=f"rate:{order_id}:1"),
                InlineKeyboardButton("2⭐", callback_data=f"rate:{order_id}:2"),
                InlineKeyboardButton("3⭐", callback_data=f"rate:{order_id}:3"),
                InlineKeyboardButton("4⭐", callback_data=f"rate:{order_id}:4"),
                InlineKeyboardButton("5⭐", callback_data=f"rate:{order_id}:5"),
            ]])
        )
        return

    # CANCEL
    if action == "cancel":
        if order["master_id"] != actor.id and actor.id != ADMIN_ID:
            await query.answer("❌ Ҳуқуқ йўқ.", show_alert=True)
            return
        if order["status"] in ("completed", "cancelled", "rejected"):
            await query.answer("⚠️ Буюртма аллақачон якунланган.", show_alert=True)
            return

        await update_order_status(order_id, "cancelled", actor.id, actor_name)
        await query.edit_message_text(f"❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n🔢 #{order_id}\n👨‍🔧 {actor_name}")
        await safe_send(context, order["customer_id"],
                        f"❌ Буюртмангиз №{order_id} бекор қилинди.\n\nЯнги буюртма беришингиз мумкин.")
        return

    # REJECT
    if action == "reject":
        if order["status"] != "open":
            await query.answer("⚠️ Буюртма аллақачон ўзгарган.", show_alert=True)
            return
        await update_order_status(order_id, "rejected", actor.id, actor_name)
        await query.edit_message_text(f"🚫 БУЮРТМА РАД ЭТИЛДИ\n\n🔢 #{order_id}\n👨‍🔧 {actor_name}")
        await safe_send(context, order["customer_id"],
                        f"⚠️ Буюртма №{order_id} бу уста томонидан қабул қилинмади.")
        return

    # ASSIGN: only admin can select another master
    if action == "assign":
        if actor.id != ADMIN_ID:
            await query.answer("❌ Бошқа устага беришни фақат админ амалга оширади.", show_alert=True)
            return
        masters = await get_active_masters()
        if not masters:
            await query.answer("❌ Фаол усталар йўқ.", show_alert=True)
            return
        buttons = []
        for m in masters:
            buttons.append([InlineKeyboardButton(
                f"👨‍🔧 {m['name']} ⭐{float(m['rating'] or 0):.1f}",
                callback_data=f"to:{order_id}:{m['telegram_id']}"
            )])
        await query.message.reply_text(
            f"🔄 #{order_id} учун устани танланг:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # TO MASTER: admin only
    if action == "to" and len(parts) == 3:
        if actor.id != ADMIN_ID:
            await query.answer("❌ Ҳуқуқ йўқ.", show_alert=True)
            return
        try:
            master_id = int(parts[2])
        except ValueError:
            return
        master = await get_master(master_id)
        if not master or not master["active"]:
            await query.answer("❌ Уста топилмади.", show_alert=True)
            return

        await assign_master(order_id, master_id, master["name"])
        await update_order_status(order_id, "accepted", ADMIN_ID, "ADMIN")
        await safe_send(
            context, master_id,
            f"🆕 Сизга янги буюртма бириктирилди: #{order_id}\n"
            f"🛠 {order['service']}\n📍 {order['address']}\n📞 {order['phone']}",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🔵 Ишни бошлаш", callback_data=f"start:{order_id}")],
                [InlineKeyboardButton("❌ Бекор қилиш", callback_data=f"cancel:{order_id}")]
            ])
        )
        await query.answer("✅ Устага бириктирилди.")
        return

# =========================================================
# SAFE SEND
# =========================================================

async def safe_send(context, chat_id, text, reply_markup=None):
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )
    except Exception:
        logger.exception("Xabar yuborilmadi: %s", chat_id)

# =========================================================
# ADMIN VIEWS
# =========================================================

async def show_orders(update, status=None, title="📋 БУЮРТМАЛАР"):
    if update.effective_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        if status:
            rows = await conn.fetch("""
                SELECT * FROM orders WHERE status=$1 ORDER BY id DESC LIMIT 50
            """, status)
        else:
            rows = await conn.fetch("""
                SELECT * FROM orders ORDER BY id DESC LIMIT 50
            """)
    if not rows:
        await update.message.reply_text("📭 Буюртмалар топилмади.", reply_markup=admin_menu())
        return

    text = title + "\n\n"
    for row in rows:
        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['customer_name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🛠 {row['service'] or '-'}\n"
            f"📍 {row['address'] or '-'}\n"
            f"📌 {STATUS_TEXT.get(row['status'], row['status'])}\n"
            f"👨‍🔧 {row['master_name'] or '-'}\n"
            "────────────\n"
        )
    await update.message.reply_text(text[:4000], reply_markup=admin_menu())

async def show_statistics(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    s = await statistics()
    await update.message.reply_text(
        "📊 USTA 24 ТЎЛИҚ СТАТИСТИКА\n\n"
        f"📋 Жами: {s['total']}\n"
        f"🆕 Янги: {s['open']}\n"
        f"🟡 Қабул қилинган: {s['accepted']}\n"
        f"🔵 Иш жараёнида: {s['in_progress']}\n"
        f"✅ Якунланган: {s['completed']}\n"
        f"❌ Бекор қилинган: {s['cancelled']}\n"
        f"🚫 Рад этилган: {s['rejected']}",
        reply_markup=admin_menu()
    )

async def show_masters(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    rows = await master_statistics()
    if not rows:
        await update.message.reply_text("👨‍🔧 Усталар йўқ.", reply_markup=admin_menu())
        return
    text = "👨‍🔧 УСТАЛАР\n\n"
    for r in rows:
        text += (
            f"👨‍🔧 {r['name']}\n"
            f"🆔 {r['telegram_id']}\n"
            f"📞 {r['phone'] or '-'}\n"
            f"🛠 {r['service'] or 'Барча'}\n"
            f"⭐ {float(r['rating'] or 0):.1f} ({r['rating_count']})\n"
            f"📋 Жами: {r['total_orders']}\n"
            f"✅ Якунланган: {r['completed_db']}\n"
            f"{'🟢 Фаол' if r['active'] else '🔴 Нофаол'}\n"
            "────────────\n"
        )
    await update.message.reply_text(text[:4000], reply_markup=admin_menu())

async def show_customers(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.*,
                   COUNT(o.id) AS orders_count
            FROM customers c
            LEFT JOIN orders o ON o.customer_id=c.telegram_id
            GROUP BY c.id
            ORDER BY c.id DESC LIMIT 50
        """)
    if not rows:
        await update.message.reply_text("👤 Мижозлар базаси бўш.", reply_markup=admin_menu())
        return
    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"
    for r in rows:
        text += (
            f"👤 {r['name'] or '-'}\n"
            f"📞 {r['phone'] or '-'}\n"
            f"📋 Буюртмалар: {r['orders_count']}\n"
            f"🆔 {r['telegram_id']}\n"
            "────────────\n"
        )
    await update.message.reply_text(text[:4000], reply_markup=admin_menu())

async def show_reports(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    day = await period_statistics(1)
    week = await period_statistics(7)
    month = await period_statistics(30)
    def block(title, r):
        return (
            f"{title}\n"
            f"📋 Жами: {r['total']}\n"
            f"✅ Якунланган: {r['completed']}\n"
            f"❌ Бекор: {r['cancelled']}\n"
            f"🚫 Рад: {r['rejected']}\n"
            f"💰 Якунланган сумма: {float(r['revenue'] or 0):,.0f}\n\n"
        )
    await update.message.reply_text(
        "📈 USTA 24 ҲИСОБОТ\n\n" +
        block("📅 КУНЛИК", day) +
        block("📅 ҲАФТАЛИК", week) +
        block("📅 ОЙЛИК", month),
        reply_markup=admin_menu()
    )

async def price_menu(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT service, base_price FROM price_settings
            WHERE active=TRUE ORDER BY id
        """)
    text = "💰 НАРХЛАР\n\n"
    for r in rows:
        text += f"🛠 {r['service']}: {float(r['base_price'] or 0):,.0f}\n"
    text += "\nНархни ўзгартириш: /price ХИЗМАТ|СУММА"
    await update.message.reply_text(text, reply_markup=admin_menu())

# =========================================================
# ADMIN ADD/REMOVE MASTER
# =========================================================

async def begin_add_master(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    user_states[ADMIN_ID] = {"step": "admin_add_master_id"}
    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "1️⃣ Устанинг Telegram ID рақамини юборинг:"
    )

async def begin_remove_master(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    user_states[ADMIN_ID] = {"step": "admin_remove_master_id"}
    await update.message.reply_text("❌ Ўчириш учун устанинг Telegram ID рақамини юборинг:")

async def price_command(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text("Формат: /price Хизмат номи|50000")
        return
    service, amount = raw.split("|", 1)
    try:
        price = float(amount.strip())
    except ValueError:
        await update.message.reply_text("❌ Сумма рақам бўлиши керак.")
        return
    await set_base_price(service.strip(), price)
    await update.message.reply_text(f"✅ Нарх сақланди: {service.strip()} = {price:,.0f} сўм")

# =========================================================
# BROADCAST
# =========================================================

async def begin_broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    broadcast_states[ADMIN_ID] = True
    await update.message.reply_text(
        "📢 ХАБАР ТАРҚАТИШ\n\n"
        "Мижозлар базасига юбориладиган хабарни ёзинг.\n"
        "Бекор қилиш: /cancel"
    )

async def cancel_command(update, context):
    if update.effective_user.id == ADMIN_ID:
        broadcast_states.pop(ADMIN_ID, None)
        user_states.pop(ADMIN_ID, None)
        await update.message.reply_text("❌ Амал бекор қилинди.", reply_markup=admin_menu())

async def do_broadcast(update, context, text):
    if update.effective_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        ids = await conn.fetch("SELECT telegram_id FROM customers")
    sent = failed = 0
    for row in ids:
        try:
            await context.bot.send_message(chat_id=row["telegram_id"], text=text)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO broadcast_history(admin_id,message,sent_count,failed_count)
            VALUES($1,$2,$3,$4)
        """, ADMIN_ID, text, sent, failed)
    broadcast_states.pop(ADMIN_ID, None)
    await update.message.reply_text(
        f"📢 Тарқатиш якунланди.\n\n✅ Юборилди: {sent}\n❌ Хато: {failed}",
        reply_markup=admin_menu()
    )

# =========================================================
# REPEAT ORDER
# =========================================================

async def repeat_order(update, context):
    user = update.effective_user
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM orders
            WHERE customer_id=$1
            ORDER BY id DESC LIMIT 1
        """, user.id)
    if not row:
        await update.message.reply_text("📭 Аввалги буюртма топилмади.", reply_markup=main_menu())
        return
    user_states[user.id] = {
        "step": "description",
        "name": row["customer_name"],
        "phone": row["phone"],
        "service": row["service"],
        "address": row["address"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "price": float(row["price"] or 0),
    }
    await update.message.reply_text(
        "🔁 ҚАЙТА БУЮРТМА\n\n"
        f"🛠 {row['service']}\n"
        f"📍 {row['address']}\n\n"
        "📝 Қўшимча изоҳни ёзинг:"
    )

# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user
    if not user:
        return
    uid = user.id
    text = (update.message.text or "").strip()

    # Broadcast has priority
    if uid == ADMIN_ID and broadcast_states.get(ADMIN_ID):
        if text:
            await do_broadcast(update, context, text)
        return

    # Admin menu
    if uid == ADMIN_ID:
        admin_actions = {
            "📊 Статистика": lambda: show_statistics(update, context),
            "📈 Ҳисобот": lambda: show_reports(update, context),
            "👨‍🔧 Усталар": lambda: show_masters(update, context),
            "👤 Мижозлар": lambda: show_customers(update, context),
            "🆕 Янги буюртмалар": lambda: show_orders(update, "open", "🆕 ЯНГИ БУЮРТМАЛАР"),
            "📋 Барча буюртмалар": lambda: show_orders(update, None, "📋 БАРЧА БУЮРТМАЛАР"),
            "💰 Нархлар": lambda: price_menu(update, context),
            "➕ Уста қўшиш": lambda: begin_add_master(update, context),
            "❌ Уста ўчириш": lambda: begin_remove_master(update, context),
            "📢 Хабар тарқатиш": lambda: begin_broadcast(update, context),
        }
        if text in admin_actions:
            await admin_actions[text]()
            return

    # Main menu
    if text == "🛠 Уста чақириш":
        await start_order(update, context)
        return
    if text == "📋 Хизматлар":
        await services(update, context)
        return
    if text == "📞 Алоқа":
        await contact(update, context)
        return
    if text == "🔁 Қайта буюртма":
        await repeat_order(update, context)
        return

    state = user_states.get(uid)
    if not state:
        await update.message.reply_text(
            "Менюдан хизматни танланг.",
            reply_markup=admin_menu() if uid == ADMIN_ID else main_menu()
        )
        return

    step = state.get("step")

    # Admin add master
    if uid == ADMIN_ID and step == "admin_add_master_id":
        try:
            state["master_id"] = int(text)
        except ValueError:
            await update.message.reply_text("❌ Telegram ID рақам бўлиши керак.")
            return
        state["step"] = "admin_add_master_name"
        await update.message.reply_text("2️⃣ Устанинг исмини ёзинг:")
        return

    if uid == ADMIN_ID and step == "admin_add_master_name":
        state["name"] = text
        state["step"] = "admin_add_master_phone"
        await update.message.reply_text("3️⃣ Телефонини ёзинг ёки - деб ёзинг:")
        return

    if uid == ADMIN_ID and step == "admin_add_master_phone":
        phone = None if text == "-" else text
        await add_master(state["master_id"], state["name"], phone=phone)
        user_states.pop(ADMIN_ID, None)
        await update.message.reply_text("✅ Уста қўшилди/фаоллаштирилди.", reply_markup=admin_menu())
        return

    if uid == ADMIN_ID and step == "admin_remove_master_id":
        try:
            master_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Telegram ID рақам бўлиши керак.")
            return
        await remove_master(master_id)
        user_states.pop(ADMIN_ID, None)
        await update.message.reply_text("✅ Уста нофаол қилинди.", reply_markup=admin_menu())
        return

    # Customer order
    if step == "name":
        state["name"] = text
        state["step"] = "phone"
        await update.message.reply_text(
            "2️⃣ Телефон рақамингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("📱 Рақамимни юбориш", request_contact=True)]],
                resize_keyboard=True
            )
        )
        return

    if step == "phone":
        phone = update.message.contact.phone_number if update.message.contact else text
        if not phone:
            await update.message.reply_text("📞 Телефон рақамини юборинг.")
            return
        state["phone"] = phone
        state["step"] = "service"
        await update.message.reply_text("3️⃣ Хизматни танланг:", reply_markup=service_menu())
        return

    if step == "service":
        if text not in SERVICES:
            # Accept service aliases from the visible menu
            aliases = {
                "🪑 Mebel": "🪑 Мебел",
                "🚚 Yuk tashish / ko‘chirish": "🚚 Yuk tashish / ko‘chirish",
                "🔩 Santexnika": "🔩 Santexnika",
                "⚡ Elektr": "⚡ Elektr",
                "🔥 Payvandlash": "🔥 Payvandlash",
                "🔨 Boshqa xizmat": "🔨 Boshqa xizmat",
            }
            text = aliases.get(text, text)
        state["service"] = text
        state["price"] = await get_base_price(text)
        state["step"] = "location"
        await update.message.reply_text(
            "4️⃣ Манзилни юборинг.\n\n📍 Геолокацияни юборишингиз мумкин:",
            reply_markup=location_keyboard()
        )
        return

    if step == "location":
        if update.message.location:
            loc = update.message.location
            state["latitude"] = loc.latitude
            state["longitude"] = loc.longitude
            state["address"] = f"Геолокация: {loc.latitude}, {loc.longitude}"
            state["step"] = "description"
            await update.message.reply_text("5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:")
            return
        if text == "📍 Манзилни қўлда ёзиш":
            state["step"] = "address"
            await update.message.reply_text("📍 Манзилингизни ёзинг:")
            return
        await update.message.reply_text("📍 Геолокация юборинг ёки манзилни қўлда ёзинг.")
        return

    if step == "address":
        state["address"] = text
        state["step"] = "description"
        await update.message.reply_text("5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:")
        return

    if step == "description":
        state["description"] = text
        await create_and_send_order(update, context, state)
        return

# =========================================================
# COMMANDS
# =========================================================

async def dispatcher(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Кириш ҳуқуқи йўқ.")
        return
    await update.message.reply_text("👑 USTA 24 PRO FULL АДМИН", reply_markup=admin_menu())

async def chat_id(update, context):
    await update.message.reply_text(f"🆔 Chat ID: {update.effective_chat.id}")

# =========================================================
# REMINDERS
# =========================================================

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        async with db_pool.acquire() as conn:
            accepted = await conn.fetch("""
                SELECT * FROM orders
                WHERE status='accepted'
                  AND accepted_at < NOW() - INTERVAL '2 hours'
                LIMIT 20
            """)
            in_progress = await conn.fetch("""
                SELECT * FROM orders
                WHERE status='in_progress'
                  AND started_at < NOW() - INTERVAL '6 hours'
                LIMIT 20
            """)

        for row in accepted:
            await safe_send(
                context, row["customer_id"],
                f"🔔 Эслатма\n\nБуюртма №{row['id']} қабул қилинганига 2 соат бўлди.\n"
                "Уста ишни бошламаган бўлса, USTA 24 билан боғланинг.\n☎️ " + PHONE
            )
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO notifications(order_id,customer_id,notification_type)
                    VALUES($1,$2,'accepted_2h')
                """, row["id"], row["customer_id"])

        for row in in_progress:
            await safe_send(
                context, row["customer_id"],
                f"🔔 Эслатма\n\nБуюртма №{row['id']} бўйича иш жараёни 6 соатдан ошди.\n☎️ " + PHONE
            )
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO notifications(order_id,customer_id,notification_type)
                    VALUES($1,$2,'in_progress_6h')
                """, row["id"], row["customer_id"])
    except Exception:
        logger.exception("Reminder xatosi")

# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update, context):
    logger.error("BOT XATOSI", exc_info=context.error)

# =========================================================
# MAIN
# =========================================================

async def run_bot(application):
    await application.initialize()
    await init_database()
    await application.start()

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    # JobQueue is available only with the [job-queue] extra.
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            reminder_job,
            interval=1800,
            first=60,
        )
        logger.info("✅ Reminder JobQueue ишга тушди.")
    else:
        logger.error(
            "❌ JobQueue мавжуд эмас. "
            "requirements.txt да python-telegram-bot[job-queue]==22.3 бўлиши шарт."
        )

    logger.info("✅ USTA 24 PRO FULL polling ишга тушди.")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        if db_pool:
            await db_pool.close()

def main():
    logger.info("=================================")
    logger.info("USTA 24 PRO FULL START")
    logger.info("ADMIN_ID=%s", ADMIN_ID)
    logger.info("MASTERS_GROUP_ID=%s", MASTERS_GROUP_ID)
    logger.info("DATABASE_URL=%s", bool(DATABASE_URL))
    logger.info("=================================")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("dispatcher", dispatcher))
    application.add_handler(CommandHandler("id", chat_id))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(
        MessageHandler(filters.LOCATION | filters.CONTACT, handle_message)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    application.add_error_handler(error_handler)

    Thread(target=run_flask, daemon=True).start()
    logger.info("✅ Flask server ишга тушди.")

    asyncio.run(run_bot(application))

if __name__ == "__main__":
    main()
