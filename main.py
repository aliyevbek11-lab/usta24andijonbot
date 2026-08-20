import os
import asyncio
import logging
from datetime import datetime, timedelta

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
# USTA 24 — BIR BOT, LEKIN 3 ALOHIDA QISM
# 1) MIJOZ: bot bilan shaxsiy chat
# 2) USTALAR: faqat buyurtmalar guruhida buyurtma
# 3) ADMIN: /dispatcher orqali boshqaruv
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

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
    raise RuntimeError("MASTERS_GROUP_ID va ADMIN_ID raqam bo‘lishi kerak!")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("usta24")

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI!"

@app.route("/health")
def health():
    return "OK"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))

# =========================================================
# DATABASE
# =========================================================

db_pool = None

async def init_database():
    global db_pool

    if not DATABASE_URL:
        logger.warning("DATABASE_URL yo‘q. Memory rejimi.")
        return

    try:
        import asyncpg

        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
        )

        async with db_pool.acquire() as c:
            await c.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    telegram_id BIGINT PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    username TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_order_at TIMESTAMP
                )
            """)

            await c.execute("""
                CREATE TABLE IF NOT EXISTS masters (
                    telegram_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    username TEXT,
                    phone TEXT,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            await c.execute("""
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
                    rejected_at TIMESTAMP,
                    reminder_sent BOOLEAN DEFAULT FALSE
                )
            """)

            await c.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id SERIAL PRIMARY KEY,
                    order_id INTEGER UNIQUE NOT NULL,
                    customer_id BIGINT NOT NULL,
                    master_id BIGINT,
                    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
                    text TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            await c.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    service TEXT PRIMARY KEY,
                    base_price NUMERIC DEFAULT 0
                )
            """)

            for service, price in [
                ("🪑 Mebel", 0),
                ("🚚 Yuk tashish / ko‘chirish", 0),
                ("🔩 Santexnika", 0),
                ("⚡ Elektr", 0),
                ("🔥 Payvandlash", 0),
                ("🔨 Boshqa xizmat", 0),
            ]:
                await c.execute("""
                    INSERT INTO prices(service, base_price)
                    VALUES($1, $2)
                    ON CONFLICT(service) DO NOTHING
                """, service, price)

        logger.info("PostgreSQL ulandi.")
    except Exception:
        logger.exception("Database ulanish xatosi.")
        db_pool = None

async def q(query, *args, fetch=False, one=False):
    if not db_pool:
        return None if one else ([] if fetch else None)
    try:
        async with db_pool.acquire() as c:
            if one:
                return await c.fetchrow(query, *args)
            if fetch:
                return await c.fetch(query, *args)
            return await c.execute(query, *args)
    except Exception:
        logger.exception("DB query xatosi")
        return None if one else ([] if fetch else None)

# =========================================================
# MEMORY FALLBACK
# =========================================================

user_state = {}
memory_orders = {}
memory_customers = {}
memory_masters = {}
memory_reviews = {}
memory_prices = {
    "🪑 Mebel": 0,
    "🚚 Yuk tashish / ko‘chirish": 0,
    "🔩 Santexnika": 0,
    "⚡ Elektr": 0,
    "🔥 Payvandlash": 0,
    "🔨 Boshqa xizmat": 0,
}
memory_order_id = 0

# =========================================================
# MENUS
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Usta chaqirish"],
            ["📋 Xizmatlar", "📞 Aloqa"],
            ["🔁 Qayta buyurtma"],
        ],
        resize_keyboard=True,
    )

def service_menu():
    return ReplyKeyboardMarkup(
        [
            ["🪑 Mebel"],
            ["🚚 Yuk tashish / ko‘chirish"],
            ["🔩 Santexnika"],
            ["⚡ Elektr"],
            ["🔥 Payvandlash"],
            ["🔨 Boshqa xizmat"],
        ],
        resize_keyboard=True,
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar", "🟡 Qabul qilingan"],
            ["🔵 Ish jarayonida", "✅ Yakunlangan"],
            ["❌ Bekor qilingan", "🚫 Rad etilgan"],
            ["📋 Barcha buyurtmalar"],
            ["📊 To‘liq statistika"],
            ["👨‍🔧 Usta statistikasi"],
            ["👤 Mijozlar bazasi"],
            ["👨‍🔧 Ustalar boshqaruvi"],
            ["📢 Xabar tarqatish"],
            ["📈 Hisobot"],
            ["💰 Narxlar"],
        ],
        resize_keyboard=True,
    )

def master_manage_menu():
    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Usta qo‘shish"],
            ["🗑 Usta o‘chirish"],
            ["👨‍🔧 Ustalar ro‘yxati"],
            ["⬅️ Admin menyu"],
        ],
        resize_keyboard=True,
    )

# =========================================================
# CUSTOMER
# =========================================================

async def save_customer(user, name=None, phone=None, lat=None, lon=None):
    username = f"@{user.username}" if user.username else None

    if db_pool:
        await q("""
            INSERT INTO customers
            (telegram_id,name,phone,username,latitude,longitude,last_order_at)
            VALUES($1,$2,$3,$4,$5,$6,NOW())
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=COALESCE($2,customers.name),
                phone=COALESCE($3,customers.phone),
                username=COALESCE($4,customers.username),
                latitude=COALESCE($5,customers.latitude),
                longitude=COALESCE($6,customers.longitude),
                last_order_at=NOW()
        """, user.id, name, phone, username, lat, lon)
    else:
        old = memory_customers.get(user.id, {})
        memory_customers[user.id] = {
            **old,
            "name": name or old.get("name"),
            "phone": phone or old.get("phone"),
            "username": username or old.get("username"),
            "latitude": lat if lat is not None else old.get("latitude"),
            "longitude": lon if lon is not None else old.get("longitude"),
        }

async def get_customer(user_id):
    if db_pool:
        return await q("""
            SELECT * FROM customers WHERE telegram_id=$1
        """, user_id, one=True)
    return memory_customers.get(user_id)

# =========================================================
# ORDERS
# =========================================================

async def create_order(order):
    global memory_order_id

    if db_pool:
        row = await q("""
            INSERT INTO orders
            (customer_id,customer_name,phone,service,address,description,
             username,latitude,longitude,status,price)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'open',$10)
            RETURNING id
        """,
        order["customer_id"], order["name"], order["phone"],
        order["service"], order["address"], order["description"],
        order["username"], order.get("latitude"), order.get("longitude"),
        order.get("price", 0), one=True)
        if row:
            return int(row["id"])

    memory_order_id += 1
    oid = memory_order_id
    memory_orders[oid] = {
        **order,
        "id": oid,
        "status": "open",
        "master_id": None,
        "master_name": None,
        "created_at": datetime.now(),
    }
    return oid

async def get_order(order_id):
    if db_pool:
        return await q("SELECT * FROM orders WHERE id=$1", order_id, one=True)
    return memory_orders.get(order_id)

async def update_order(order_id, status, master_id=None, master_name=None):
    stamp = {
        "accepted": "accepted_at",
        "in_progress": "started_at",
        "completed": "completed_at",
        "cancelled": "cancelled_at",
        "rejected": "rejected_at",
    }.get(status)

    if db_pool:
        if stamp:
            await q(f"""
                UPDATE orders SET status=$1,
                master_id=COALESCE($2,master_id),
                master_name=COALESCE($3,master_name),
                {stamp}=NOW()
                WHERE id=$4
            """, status, master_id, master_name, order_id)
        else:
            await q("""
                UPDATE orders SET status=$1,
                master_id=COALESCE($2,master_id),
                master_name=COALESCE($3,master_name)
                WHERE id=$4
            """, status, master_id, master_name, order_id)
    else:
        o = memory_orders.get(order_id)
        if o:
            o["status"] = status
            if master_id is not None:
                o["master_id"] = master_id
            if master_name is not None:
                o["master_name"] = master_name

async def get_orders(status=None, limit=50):
    if db_pool:
        if status:
            return await q("""
                SELECT * FROM orders WHERE status=$1
                ORDER BY id DESC LIMIT $2
            """, status, limit, fetch=True)
        return await q("""
            SELECT * FROM orders ORDER BY id DESC LIMIT $1
        """, limit, fetch=True)
    values = list(memory_orders.values())
    if status:
        values = [x for x in values if x["status"] == status]
    return list(reversed(values[-limit:]))

# =========================================================
# PRICE
# =========================================================

async def get_price(service):
    if db_pool:
        row = await q("SELECT base_price FROM prices WHERE service=$1", service, one=True)
        return float(row["base_price"]) if row else 0
    return float(memory_prices.get(service, 0))

async def set_price(service, price):
    if db_pool:
        await q("""
            INSERT INTO prices(service,base_price) VALUES($1,$2)
            ON CONFLICT(service) DO UPDATE SET base_price=$2
        """, service, price)
    else:
        memory_prices[service] = price

# =========================================================
# FORMAT
# =========================================================

STATUS_UZ = {
    "open": "🆕 Янги",
    "accepted": "🟡 Қабул қилинган",
    "in_progress": "🔵 Иш жараёнида",
    "completed": "✅ Якунланган",
    "cancelled": "❌ Бекор қилинган",
    "rejected": "🚫 Рад этилган",
}

def order_value(o, key, default="-"):
    if isinstance(o, dict):
        return o.get(key, default)
    return o[key] if o.get(key) is not None else default

def order_text(o):
    oid = order_value(o, "id")
    name = order_value(o, "customer_name", order_value(o, "name"))
    phone = order_value(o, "phone")
    service = order_value(o, "service")
    address = order_value(o, "address")
    desc = order_value(o, "description")
    master = order_value(o, "master_name")
    status = order_value(o, "status")
    price = order_value(o, "price", 0)
    return (
        f"🔢 Буюртма: #{oid}\n"
        f"👤 Мижоз: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"🛠 Хизмат: {service}\n"
        f"📍 Манзил: {address}\n"
        f"📝 Изоҳ: {desc}\n"
        f"👨‍🔧 Уста: {master}\n"
        f"💰 Нарх асоси: {price}\n"
        f"📌 Ҳолат: {STATUS_UZ.get(status,status)}"
    )

# =========================================================
# START / CUSTOMER MENUS
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 хизматларига хуш келибсиз.\n"
        "📍 Андижон шаҳри\n\n"
        "Керакли хизматни танланг:",
        reply_markup=main_menu(),
    )

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 USTA 24 ХИЗМАТЛАРИ\n\n"
        "🪑 Мебель йиғиш/таъмирлаш\n"
        "🚚 Юк ташиш / уй кўчириш\n"
        "🔩 Сантехника\n"
        "⚡ Электр\n"
        "🔥 Пайвандлаш\n"
        "🔨 Бошқа хизматлар",
        reply_markup=main_menu(),
    )

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "+998 77 069 00 03\n"
        "📍 Андижон шаҳри",
        reply_markup=main_menu(),
    )

# =========================================================
# ORDER START
# =========================================================

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    customer = await get_customer(user.id)

    if customer and customer["name"] and customer["phone"]:
        name = customer["name"]
        phone = customer["phone"]
        user_state[user.id] = {
            "step": "service",
            "name": name,
            "phone": phone,
        }
        await update.message.reply_text(
            f"👋 Салом, {name}!\n\n"
            "Исм ва телефон рақамингиз сақланган. ✅\n\n"
            "🛠 Хизматни танланг:",
            reply_markup=service_menu(),
        )
    else:
        user_state[user.id] = {"step": "name"}
        await update.message.reply_text(
            "📝 Буюртма бериш\n\n"
            "1️⃣ Исмингизни ёзинг:"
        )

# =========================================================
# GEOLOCATION
# =========================================================

async def ask_location(update, context):
    button = KeyboardButton(
        "📍 Геолокациямни юбориш",
        request_location=True,
    )
    await update.message.reply_text(
        "📍 Манзилни ёзинг ёки жойлашувингизни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [[button], ["⏭ Манзилни матн билан киритиш"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

# =========================================================
# SEND ORDER TO MASTERS
# =========================================================

async def send_order_to_masters(update, context, order):
    user = update.effective_user
    username = f"@{user.username}" if user.username else "username йўқ"

    order["customer_id"] = user.id
    order["username"] = username

    await save_customer(
        user,
        order.get("name"),
        order.get("phone"),
        order.get("latitude"),
        order.get("longitude"),
    )

    order_id = await create_order(order)

    location_line = ""
    if order.get("latitude") and order.get("longitude"):
        location_line = (
            f"\n🌍 Геолокация: "
            f"{order['latitude']}, {order['longitude']}"
        )

    text = (
        "🆕 ЯНГИ БУЮРТМА\n\n"
        f"🔢 Буюртма: #{order_id}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}"
        f"{location_line}\n"
        f"📝 Изоҳ: {order['description']}\n"
        f"👤 Telegram: {username}\n\n"
        "🚨 Уста қабул қилиши мумкин:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Қабул қилиш",
                callback_data=f"accept:{order_id}",
            ),
            InlineKeyboardButton(
                "❌ Рад этиш",
                callback_data=f"reject:{order_id}",
            ),
        ]
    ])

    sent = await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )

    if db_pool:
        await q(
            "UPDATE orders SET reminder_sent=FALSE WHERE id=$1",
            order_id,
        )
    else:
        if order_id in memory_orders:
            memory_orders[order_id]["group_message_id"] = sent.message_id

    return order_id

# =========================================================
# CALLBACKS
# =========================================================

async def order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return

    action, raw_id = data.split(":", 1)
    try:
        order_id = int(raw_id)
    except ValueError:
        return

    o = await get_order(order_id)
    if not o:
        await query.answer("❌ Буюртма топилмади.", show_alert=True)
        return

    user = query.from_user
    master_name = f"@{user.username}" if user.username else user.full_name

    # Faqat ustalar guruhi orqali kelgan order action.
    # Admin ham tugmani bosishi mumkin, lekin odatiy holatda usta ishlaydi.
    if action == "accept":
        current = order_value(o, "status")
        if current != "open":
            await query.answer(
                "⚠️ Буюртма аллақачон қабул қилинган.",
                show_alert=True,
            )
            return

        await update_order(order_id, "accepted", user.id, master_name)

        text = (
            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
            f"{order_text(await get_order(order_id))}\n\n"
            "🔵 Ишни бошлаш:"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔵 Ишни бошлаш",
                    callback_data=f"startjob:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"cancel:{order_id}",
                ),
            ]
        ])
        await query.edit_message_text(text, reply_markup=keyboard)

        fresh = await get_order(order_id)
        customer_id = order_value(fresh, "customer_id")
        try:
            await context.bot.send_message(
                customer_id,
                f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n\n"
                f"👨‍🔧 Уста: {master_name}\n\n"
                "☎️ USTA 24\n+998 77 069 00 03",
            )
        except Exception:
            logger.warning("Mijozga accept xabari yuborilmadi.")

        try:
            await context.bot.send_message(
                user.id,
                f"🟡 Сизга №{order_id} буюртма бириктирилди.\n"
                "🔵 Ишни бошлаш учун гуруҳдаги тугмадан фойдаланинг.",
            )
        except Exception:
            pass
        return

    if action == "reject":
        if order_value(o, "status") != "open":
            await query.answer("⚠️ Буюртма аллақачон ўзгарган.", show_alert=True)
            return

        await update_order(order_id, "rejected", user.id, master_name)
        fresh = await get_order(order_id)

        await query.edit_message_text(
            "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n" + order_text(fresh)
        )

        # Рад этилганда мижозга "бошқа уста қидирилади" деган хабар.
        try:
            await context.bot.send_message(
                order_value(fresh, "customer_id"),
                f"⚠️ Буюртмангиз №{order_id} ушбу уста томонидан қабул қилинмади.\n\n"
                "Бошқа уста топиш устида ишлаймиз.\n"
                "☎️ USTA 24: +998 77 069 00 03",
            )
        except Exception:
            pass
        return

    if action in ("startjob", "complete", "cancel"):
        if order_value(o, "master_id") != user.id:
            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )
            return

    if action == "startjob":
        if order_value(o, "status") != "accepted":
            await query.answer("⚠️ Ҳолат нотўғри.", show_alert=True)
            return
        await update_order(order_id, "in_progress")
        fresh = await get_order(order_id)
        await query.edit_message_text(
            "🔵 ИШ ЖАРАЁНИДА\n\n" + order_text(fresh),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Ишни якунлаш",
                        callback_data=f"complete:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel:{order_id}",
                    ),
                ]
            ]),
        )
        try:
            await context.bot.send_message(
                order_value(fresh, "customer_id"),
                f"🔵 №{order_id} буюртма бўйича иш бошланди.\n"
                f"👨‍🔧 Уста: {master_name}",
            )
        except Exception:
            pass
        return

    if action == "complete":
        if order_value(o, "status") != "in_progress":
            await query.answer("⚠️ Буюртма иш жараёнида эмас.", show_alert=True)
            return
        await update_order(order_id, "completed")
        fresh = await get_order(order_id)
        await query.edit_message_text(
            "✅ ИШ ЯКУНЛАНДИ\n\n" + order_text(fresh)
        )
        try:
            await context.bot.send_message(
                order_value(fresh, "customer_id"),
                f"✅ №{order_id} буюртмангиз якунланди.\n\n"
                f"👨‍🔧 Уста: {master_name}\n\n"
                "⭐ Устага баҳо бериш учун /review буйруғини юборинг.",
            )
        except Exception:
            pass
        return

    if action == "cancel":
        if order_value(o, "status") not in ("accepted", "in_progress"):
            await query.answer("⚠️ Ҳозир бекор қилиб бўлмайди.", show_alert=True)
            return
        await update_order(order_id, "cancelled")
        fresh = await get_order(order_id)
        await query.edit_message_text(
            "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n" + order_text(fresh)
        )
        try:
            await context.bot.send_message(
                order_value(fresh, "customer_id"),
                f"❌ №{order_id} буюртмангиз бекор қилинди.\n"
                "Янги буюртма беришингиз мумкин.",
            )
        except Exception:
            pass
        return

    if action == "reassign":
        if user.id != ADMIN_ID:
            await query.answer("❌ Фақат админ.", show_alert=True)
            return
        masters = await get_masters()
        rows = []
        for m in masters:
            mid = m["telegram_id"] if not isinstance(m, dict) else m["telegram_id"]
            name = m["name"] if not isinstance(m, dict) else m["name"]
            rows.append([
                InlineKeyboardButton(
                    f"👨‍🔧 {name}",
                    callback_data=f"assign:{order_id}:{mid}",
                )
            ])
        await query.message.reply_text(
            f"🔄 №{order_id} буюртмани қайси устага бериш?",
            reply_markup=InlineKeyboardMarkup(rows or [
                [InlineKeyboardButton("Усталар йўқ", callback_data="noop:0")]
            ]),
        )
        return

    if action == "assign":
        parts = data.split(":")
        if len(parts) != 3 or user.id != ADMIN_ID:
            return
        try:
            target_id = int(parts[2])
        except ValueError:
            return
        masters = await get_masters()
        target = next(
            (m for m in masters if (m["telegram_id"] if not isinstance(m, dict) else m["telegram_id"]) == target_id),
            None,
        )
        if not target:
            await query.answer("Уста топилмади.", show_alert=True)
            return
        target_name = target["name"] if not isinstance(target, dict) else target["name"]
        await update_order(order_id, "accepted", target_id, target_name)
        fresh = await get_order(order_id)
        await query.message.reply_text(
            f"🔄 №{order_id} буюртма {target_name} устага берилди."
        )
        try:
            await context.bot.send_message(
                target_id,
                "🔄 Сизга янги буюртма бириктирилди.\n\n" + order_text(fresh)
            )
        except Exception:
            pass

# =========================================================
# MASTERS
# =========================================================

async def get_masters():
    if db_pool:
        return await q(
            "SELECT * FROM masters WHERE active=TRUE ORDER BY name",
            fetch=True,
        )
    return [
        v for v in memory_masters.values()
        if v.get("active", True)
    ]

async def add_master(tg_id, name, username=None, phone=None):
    if db_pool:
        await q("""
            INSERT INTO masters(telegram_id,name,username,phone,active)
            VALUES($1,$2,$3,$4,TRUE)
            ON CONFLICT(telegram_id) DO UPDATE SET
                name=$2,username=$3,phone=$4,active=TRUE
        """, tg_id, name, username, phone)
    else:
        memory_masters[tg_id] = {
            "telegram_id": tg_id,
            "name": name,
            "username": username,
            "phone": phone,
            "active": True,
        }

async def remove_master(tg_id):
    if db_pool:
        await q(
            "UPDATE masters SET active=FALSE WHERE telegram_id=$1",
            tg_id,
        )
    elif tg_id in memory_masters:
        memory_masters[tg_id]["active"] = False

# =========================================================
# ADMIN
# =========================================================

async def dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Сиз админ эмассиз.")
        return
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "👑 USTA 24 АДМИН БОШҚАРУВИ\n\n"
        "Керакли бўлимни танланг:",
        reply_markup=admin_menu(),
    )

async def show_orders(update, status=None, title="📋 БУЮРТМАЛАР"):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = await get_orders(status)
    if not orders:
        await update.message.reply_text(
            "📭 Буюртмалар йўқ.",
            reply_markup=admin_menu(),
        )
        return

    text = title + "\n\n"
    for o in orders:
        text += order_text(o) + "\n──────────────\n"

    # Telegram message limit.
    for i in range(0, len(text), 3800):
        await update.message.reply_text(text[i:i+3800])

    await update.message.reply_text(
        "🔄 Бошқа устага бериш учун /reassign БУЮРТМА_ID",
        reply_markup=admin_menu(),
    )

async def statistics(update):
    if update.effective_user.id != ADMIN_ID:
        return

    orders = await get_orders(None, 10000)
    counts = {x: 0 for x in STATUS_UZ}
    for o in orders:
        s = order_value(o, "status")
        if s in counts:
            counts[s] += 1

    await update.message.reply_text(
        "📊 USTA 24 ТЎЛИҚ СТАТИСТИКА\n\n"
        f"📋 Жами: {len(orders)}\n"
        f"🆕 Янги: {counts['open']}\n"
        f"🟡 Қабул қилинган: {counts['accepted']}\n"
        f"🔵 Иш жараёнида: {counts['in_progress']}\n"
        f"✅ Якунланган: {counts['completed']}\n"
        f"❌ Бекор қилинган: {counts['cancelled']}\n"
        f"🚫 Рад этилган: {counts['rejected']}",
        reply_markup=admin_menu(),
    )

async def master_statistics(update):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = await get_orders(None, 10000)
    data = {}
    for o in orders:
        mid = order_value(o, "master_id")
        if not mid:
            continue
        name = order_value(o, "master_name")
        if mid not in data:
            data[mid] = {
                "name": name,
                "total": 0,
                "completed": 0,
                "cancelled": 0,
                "rejected": 0,
            }
        data[mid]["total"] += 1
        data[mid][order_value(o, "status")] = data[mid].get(
            order_value(o, "status"), 0
        ) + 1

    if not data:
        await update.message.reply_text(
            "👨‍🔧 Ҳали уста статистикаси йўқ.",
            reply_markup=admin_menu(),
        )
        return

    text = "👨‍🔧 УСТА СТАТИСТИКАСИ\n\n"
    for d in data.values():
        text += (
            f"👨‍🔧 {d['name']}\n"
            f"📋 Жами: {d['total']}\n"
            f"✅ Якунланган: {d.get('completed',0)}\n"
            f"❌ Бекор: {d.get('cancelled',0)}\n"
            f"🚫 Рад: {d.get('rejected',0)}\n\n"
        )
    await update.message.reply_text(text, reply_markup=admin_menu())

async def customer_database(update):
    if update.effective_user.id != ADMIN_ID:
        return
    if db_pool:
        rows = await q(
            "SELECT * FROM customers ORDER BY last_order_at DESC LIMIT 100",
            fetch=True,
        )
    else:
        rows = list(memory_customers.values())

    if not rows:
        await update.message.reply_text("👤 Мижозлар базаси ҳозирча бўш.")
        return

    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"
    for r in rows:
        name = r["name"] if not isinstance(r, dict) else r.get("name")
        phone = r["phone"] if not isinstance(r, dict) else r.get("phone")
        tid = r["telegram_id"] if not isinstance(r, dict) else r.get("telegram_id")
        text += f"👤 {name or '-'}\n📞 {phone or '-'}\n🆔 {tid}\n────────\n"
    await update.message.reply_text(text[:3900], reply_markup=admin_menu())

async def masters_menu(update):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
        reply_markup=master_manage_menu(),
    )

async def masters_list(update):
    masters = await get_masters()
    if not masters:
        await update.message.reply_text(
            "👨‍🔧 Фаол усталар йўқ.",
            reply_markup=master_manage_menu(),
        )
        return
    text = "👨‍🔧 ФАОЛ УСТАЛАР\n\n"
    for m in masters:
        text += (
            f"👨‍🔧 {m['name']}\n"
            f"🆔 {m['telegram_id']}\n"
            f"📞 {m.get('phone') if isinstance(m, dict) else m['phone'] or '-'}\n"
            "────────\n"
        )
    await update.message.reply_text(text, reply_markup=master_manage_menu())

# =========================================================
# REPORT / EXPORT BASIS
# =========================================================

async def report(update):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = await get_orders(None, 10000)

    today = datetime.now().date()
    week = today - timedelta(days=7)
    month = today - timedelta(days=30)

    day_count = week_count = month_count = 0
    for o in orders:
        created = order_value(o, "created_at")
        if isinstance(created, datetime):
            d = created.date()
            if d == today:
                day_count += 1
            if d >= week:
                week_count += 1
            if d >= month:
                month_count += 1

    await update.message.reply_text(
        "📈 ҲИСОБОТ\n\n"
        f"📅 Бугун: {day_count} та буюртма\n"
        f"📅 7 кун: {week_count} та буюртма\n"
        f"📅 30 кун: {month_count} та буюртма\n\n"
        "📥 Excel учун маълумотлар базага сақланмоқда.\n"
        "Кейинги босқичда .xlsx экспортни улаймиз.",
        reply_markup=admin_menu(),
    )

# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(update):
    if update.effective_user.id != ADMIN_ID:
        return
    user_state[ADMIN_ID] = {"step": "broadcast"}
    await update.message.reply_text(
        "📢 Барча мижозларга юбориладиган хабарни ёзинг.\n\n"
        "Бекор қилиш: /cancel"
    )

# =========================================================
# REASSIGN
# =========================================================

async def reassign(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Фақат админ.")
        return
    if not context.args:
        await update.message.reply_text(
            "Формат: /reassign 25"
        )
        return
    try:
        oid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID нотўғри.")
        return

    o = await get_order(oid)
    if not o:
        await update.message.reply_text("❌ Буюртма топилмади.")
        return

    masters = await get_masters()
    buttons = []
    for m in masters:
        mid = m["telegram_id"] if not isinstance(m, dict) else m["telegram_id"]
        name = m["name"] if not isinstance(m, dict) else m["name"]
        buttons.append([
            InlineKeyboardButton(
                f"👨‍🔧 {name}",
                callback_data=f"assign:{oid}:{mid}",
            )
        ])

    await update.message.reply_text(
        f"🔄 №{oid} учун янги устани танланг:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# =========================================================
# REVIEW
# =========================================================

async def review_command(update, context):
    user = update.effective_user
    orders = await get_orders("completed", 100)
    customer_orders = [
        o for o in orders
        if order_value(o, "customer_id") == user.id
    ]
    if not customer_orders:
        await update.message.reply_text(
            "⭐ Якунланган буюртмангиз топилмади."
        )
        return

    oid = order_value(customer_orders[0], "id")
    user_state[user.id] = {
        "step": "review_rating",
        "order_id": oid,
    }
    await update.message.reply_text(
        f"⭐ №{oid} буюртма учун баҳо беринг: 1–5"
    )

async def save_review(order_id, customer_id, rating, text, master_id):
    if db_pool:
        await q("""
            INSERT INTO reviews(order_id,customer_id,master_id,rating,text)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(order_id) DO UPDATE SET
                rating=$4,text=$5
        """, order_id, customer_id, master_id, rating, text)
    else:
        memory_reviews[order_id] = {
            "order_id": order_id,
            "customer_id": customer_id,
            "master_id": master_id,
            "rating": rating,
            "text": text,
        }

# =========================================================
# REPEAT ORDER
# =========================================================

async def repeat_order(update, context):
    user = update.effective_user
    orders = await get_orders(None, 100)
    mine = [
        o for o in orders
        if order_value(o, "customer_id") == user.id
    ]
    if not mine:
        await update.message.reply_text(
            "🔁 Олдинги буюртма топилмади."
        )
        return

    o = mine[0]
    user_state[user.id] = {
        "step": "repeat_confirm",
        "source": o,
    }
    await update.message.reply_text(
        "🔁 Охирги буюртмани қайта бериш:\n\n"
        + order_text(o)
        + "\n\n"
        "«Ҳа» деб ёзинг ёки /cancel босинг."
    )

# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user
    text = (update.message.text or "").strip()

    # ---------- ADMIN ----------
    if user.id == ADMIN_ID:
        admin_buttons = {
            "🆕 Yangi buyurtmalar",
            "🟡 Qabul qilingan",
            "🔵 Ish jarayonida",
            "✅ Yakunlangan",
            "❌ Bekor qilingan",
            "🚫 Rad etilgan",
            "📋 Barcha buyurtmalar",
            "📊 To‘liq statistika",
            "👨‍🔧 Usta statistikasi",
            "👤 Mijozlar bazasi",
            "👨‍🔧 Ustalar boshqaruvi",
            "📢 Xabar tarqatish",
            "📈 Hisobot",
            "💰 Narxlar",
            "👨‍🔧 Usta qo‘shish",
            "🗑 Usta o‘chirish",
            "👨‍🔧 Ustalar ro‘yxati",
            "⬅️ Admin menyu",
        }
        if text in admin_buttons:
            if text == "🆕 Yangi buyurtmalar":
                await show_orders(update, "open", "🆕 ЯНГИ БУЮРТМАЛАР")
            elif text == "🟡 Qabul qilingan":
                await show_orders(update, "accepted", "🟡 ҚАБУЛ ҚИЛИНГАН")
            elif text == "🔵 Ish jarayonida":
                await show_orders(update, "in_progress", "🔵 ИШ ЖАРАЁНИДА")
            elif text == "✅ Yakunlangan":
                await show_orders(update, "completed", "✅ ЯКУНЛАНГАН")
            elif text == "❌ Bekor qilingan":
                await show_orders(update, "cancelled", "❌ БЕКОР ҚИЛИНГАН")
            elif text == "🚫 Rad etilgan":
                await show_orders(update, "rejected", "🚫 РАД ЭТИЛГАН")
            elif text == "📋 Barcha buyurtmalar":
                await show_orders(update, None, "📋 БАРЧА БУЮРТМАЛАР")
            elif text == "📊 To‘liq statistika":
                await statistics(update)
            elif text == "👨‍🔧 Usta statistikasi":
                await master_statistics(update)
            elif text == "👤 Mijozlar bazasi":
                await customer_database(update)
            elif text == "👨‍🔧 Ustalar boshqaruvi":
                await masters_menu(update)
            elif text == "👨‍🔧 Ustalar ro‘yxati":
                await masters_list(update)
            elif text == "👨‍🔧 Usta qo‘shish":
                user_state[ADMIN_ID] = {"step": "add_master"}
                await update.message.reply_text(
                    "👨‍🔧 Уста қўшиш.\n\n"
                    "Формат:\n"
                    "Telegram ID | Исм | Телефон"
                )
            elif text == "🗑 Usta o‘chirish":
                user_state[ADMIN_ID] = {"step": "remove_master"}
                await update.message.reply_text(
                    "🗑 Ўчириладиган устанинг Telegram ID рақамини ёзинг."
                )
            elif text == "📢 Xabar tarqatish":
                await broadcast_start(update)
            elif text == "📈 Hisobot":
                await report(update)
            elif text == "💰 Narxlar":
                user_state[ADMIN_ID] = {"step": "price"}
                await update.message.reply_text(
                    "💰 Нарх асосини ўзгартириш.\n\n"
                    "Формат:\n"
                    "Хизмат | сумма\n\n"
                    "Масалан:\n"
                    "🪑 Mebel | 50000"
                )
            elif text == "⬅️ Admin menyu":
                await dispatcher(update, context)
            return

        state = user_state.get(ADMIN_ID, {})
        if state.get("step") == "add_master":
            try:
                parts = [x.strip() for x in text.split("|")]
                tg_id = int(parts[0])
                name = parts[1]
                phone = parts[2] if len(parts) > 2 else None
                await add_master(tg_id, name, None, phone)
                user_state.pop(ADMIN_ID, None)
                await update.message.reply_text(
                    f"✅ Уста қўшилди: {name}",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.message.reply_text(
                    "❌ Формат нотўғри. Telegram ID | Исм | Телефон"
                )
            return

        if state.get("step") == "remove_master":
            try:
                await remove_master(int(text))
                user_state.pop(ADMIN_ID, None)
                await update.message.reply_text(
                    "✅ Уста фаол рўйхатдан ўчирилди.",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.message.reply_text("❌ ID нотўғри.")
            return

        if state.get("step") == "price":
            try:
                service, value = [x.strip() for x in text.split("|", 1)]
                await set_price(service, float(value))
                user_state.pop(ADMIN_ID, None)
                await update.message.reply_text(
                    f"✅ {service} учун нарх асоси {value} қилиб сақланди.",
                    reply_markup=admin_menu(),
                )
            except Exception:
                await update.message.reply_text(
                    "❌ Формат: Хизмат | сумма"
                )
            return

        if state.get("step") == "broadcast":
            user_state.pop(ADMIN_ID, None)
            if db_pool:
                rows = await q(
                    "SELECT telegram_id FROM customers",
                    fetch=True,
                )
            else:
                rows = [
                    {"telegram_id": x}
                    for x in memory_customers
                ]
            sent = 0
            for r in rows or []:
                tid = r["telegram_id"]
                try:
                    await context.bot.send_message(tid, text)
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    pass
            await update.message.reply_text(
                f"📢 Хабар тарқатилди.\n✅ Юборилди: {sent}",
                reply_markup=admin_menu(),
            )
            return

    # ---------- CUSTOMER MAIN ----------
    if text == "🛠 Usta chaqirish":
        await start_order(update, context)
        return
    if text == "📋 Xizmatlar":
        await services(update, context)
        return
    if text == "📞 Aloqa":
        await contact(update, context)
        return
    if text == "🔁 Qayta buyurtma":
        await repeat_order(update, context)
        return

    state = user_state.get(user.id)
    if not state:
        await update.message.reply_text(
            "Илтимос, менюдан танланг.",
            reply_markup=main_menu(),
        )
        return

    step = state.get("step")

    if step == "name":
        state["name"] = text
        state["step"] = "phone"
        button = KeyboardButton(
            "📱 Телефон рақамимни юбориш",
            request_contact=True,
        )
        await update.message.reply_text(
            "2️⃣ Телефон рақамингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [[button]], resize_keyboard=True, one_time_keyboard=True
            ),
        )
        return

    if step == "phone":
        phone = (
            update.message.contact.phone_number
            if update.message.contact
            else text
        )
        if not phone:
            await update.message.reply_text("📞 Телефон рақамини юборинг.")
            return
        state["phone"] = phone
        state["step"] = "service"
        await update.message.reply_text(
            "3️⃣ Хизматни танланг:",
            reply_markup=service_menu(),
        )
        return

    if step == "service":
        if text not in memory_prices and text not in (
            "🪑 Mebel", "🚚 Yuk tashish / ko‘chirish",
            "🔩 Santexnika", "⚡ Elektr",
            "🔥 Payvandlash", "🔨 Boshqa xizmat",
        ):
            await update.message.reply_text(
                "🛠 Хизматни тугмадан танланг.",
                reply_markup=service_menu(),
            )
            return
        state["service"] = text
        state["price"] = await get_price(text)
        state["step"] = "location"
        await ask_location(update, context)
        return

    if step == "location":
        if update.message.location:
            state["latitude"] = update.message.location.latitude
            state["longitude"] = update.message.location.longitude
            state["address"] = (
                f"Геолокация: {state['latitude']}, {state['longitude']}"
            )
            state["step"] = "description"
            await update.message.reply_text(
                "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
            )
            return

        if text == "⏭ Манзилни матн билан киритиш":
            state["step"] = "address"
            await update.message.reply_text(
                "📍 Манзилингизни ёзинг:"
            )
            return

        # If customer types address directly.
        state["address"] = text
        state["step"] = "description"
        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
        )
        return

    if step == "address":
        state["address"] = text
        state["step"] = "description"
        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
        )
        return

    if step == "description":
        if not text:
            await update.message.reply_text("📝 Изоҳ ёзинг.")
            return
        state["description"] = text
        try:
            oid = await send_order_to_masters(update, context, state.copy())
        except Exception:
            logger.exception("Ustalar guruhiga yuborishda xato")
            await update.message.reply_text(
                "❌ Буюртмани юборишда хато. Админ билан боғланинг."
            )
            return

        user_state.pop(user.id, None)
        await update.message.reply_text(
            f"✅ Буюртмангиз қабул қилинди!\n\n"
            f"🔢 Буюртма №{oid}\n"
            "👨‍🔧 Усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            "☎️ +998 77 069 00 03",
            reply_markup=main_menu(),
        )
        return

    if step == "repeat_confirm":
        if text.lower() in ("ha", "ҳа", "да", "yes"):
            old = state["source"]
            price = await get_price(order_value(old, "service"))
            order = {
                "name": order_value(old, "customer_name"),
                "phone": order_value(old, "phone"),
                "service": order_value(old, "service"),
                "address": order_value(old, "address"),
                "description": order_value(old, "description"),
                "price": price,
                "customer_id": user.id,
            }
            try:
                oid = await send_order_to_masters(update, context, order)
                user_state.pop(user.id, None)
                await update.message.reply_text(
                    f"🔁 Қайта буюртма қабул қилинди: №{oid}",
                    reply_markup=main_menu(),
                )
            except Exception:
                await update.message.reply_text("❌ Қайта буюртмада хато.")
        else:
            user_state.pop(user.id, None)
            await update.message.reply_text(
                "Бекор қилинди.",
                reply_markup=main_menu(),
            )
        return

    if step == "review_rating":
        try:
            rating = int(text)
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⭐ 1 дан 5 гача рақам ёзинг.")
            return
        state["rating"] = rating
        state["step"] = "review_text"
        await update.message.reply_text(
            "💬 Отзывингизни ёзинг:"
        )
        return

    if step == "review_text":
        oid = state["order_id"]
        o = await get_order(oid)
        await save_review(
            oid,
            user.id,
            state["rating"],
            text,
            order_value(o, "master_id"),
        )
        user_state.pop(user.id, None)
        await update.message.reply_text(
            "⭐ Раҳмат! Баҳонгиз ва отзывиңиз сақланди.",
            reply_markup=main_menu(),
        )
        return

# =========================================================
# COMMANDS
# =========================================================

async def cancel_command(update, context):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "❌ Амалиёт бекор қилинди.",
        reply_markup=main_menu(),
    )

async def chat_id_command(update, context):
    await update.message.reply_text(
        f"🆔 Chat ID: {update.effective_chat.id}\n"
        f"📌 Type: {update.effective_chat.type}"
    )

# =========================================================
# REMINDERS
# =========================================================

async def reminder_loop(application):
    while True:
        try:
            orders = await get_orders("accepted", 500)
            now = datetime.now()
            for o in orders:
                created = order_value(o, "accepted_at")
                if isinstance(created, datetime) and now - created > timedelta(hours=2):
                    customer_id = order_value(o, "customer_id")
                    oid = order_value(o, "id")
                    try:
                        await application.bot.send_message(
                            customer_id,
                            f"🔔 Эслатма: №{oid} буюртма бўйича иш ҳолатини "
                            "USTA 24 назорат қилмоқда."
                        )
                    except Exception:
                        pass
        except Exception:
            logger.exception("Reminder loop xatosi")
        await asyncio.sleep(600)

# =========================================================
# ERROR / RUN
# =========================================================

async def error_handler(update, context):
    logger.error("BOT XATOSI", exc_info=context.error)

async def run_bot(application):
    await application.initialize()
    await init_database()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    reminder_task = asyncio.create_task(reminder_loop(application))
    logger.info("✅ Telegram polling ishga tushdi.")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        reminder_task.cancel()
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

def main():
    logger.info("================================")
    logger.info("USTA 24 BOT START")
    logger.info("MASTERS_GROUP_ID=%s", MASTERS_GROUP_ID)
    logger.info("ADMIN_ID=%s", ADMIN_ID)
    logger.info("DATABASE_URL=%s", bool(DATABASE_URL))
    logger.info("================================")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("dispatcher", dispatcher))
    application.add_handler(CommandHandler("id", chat_id_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("reassign", reassign))
    application.add_handler(CommandHandler("review", review_command))

    application.add_handler(CallbackQueryHandler(order_callback))

    application.add_handler(
        MessageHandler(filters.CONTACT | filters.LOCATION, handle_message)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    application.add_error_handler(error_handler)

    Thread = __import__("threading").Thread
    Thread(target=run_flask, daemon=True).start()

    asyncio.run(run_bot(application))

if __name__ == "__main__":
    main()
