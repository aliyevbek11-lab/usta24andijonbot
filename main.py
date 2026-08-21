# ============================================================
# USTA 24 ANDIJON — FULL MAIN.PY
# Python 3.11+
# python-telegram-bot 22.3
# PostgreSQL / asyncpg
#
# ENV:
# BOT_TOKEN=...
# DATABASE_URL=postgresql://...
# ADMIN_ID=123456789
# MASTERS_GROUP_ID=-1001234567890
#
# Optional:
# TIMEZONE=Asia/Tashkent
#
# One bot: CLIENT + MASTER + ADMIN
# ============================================================

import os
import csv
import io
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import asyncpg
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ---------------- CONFIG ----------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("usta24")

pool: Optional[asyncpg.Pool] = None

# ---------------- STATES ----------------

(
    C_NAME,
    C_PHONE,
    C_LOCATION,
    C_SERVICE,
    C_ADDRESS,
    C_COMMENT,
    M_PHONE,
    M_NAME,
    M_SERVICES,
    M_WORKTIME,
    ADMIN_PRICE_SERVICE,
    ADMIN_PRICE_VALUE,
    ADMIN_BROADCAST,
    ADMIN_COUPON_CODE,
    ADMIN_COUPON_DISCOUNT,
) = range(15)

# ---------------- CONSTANTS ----------------

SERVICES = [
    "🪑 Mebel yig‘ish",
    "🔧 Mebel ta’mirlash",
    "🍽 Oshxona mebeli",
    "🚪 Shkaf / garderob",
    "🛏 Karavot",
    "🪑 Stol / stul",
    "📦 Mebel yechish-yig‘ish",
    "🚚 Mebel tashish",
    "🏠 Uy ko‘chirish",
    "🔨 Uyga usta",
]

STATUS_NAMES = {
    "new": "🆕 Yangi",
    "assigned": "👨‍🔧 Ustaga biriktirilgan",
    "accepted": "✅ Qabul qilingan",
    "rejected": "❌ Rad etilgan",
    "in_progress": "🔧 Ish jarayonida",
    "completed": "🏁 Tugallangan",
    "cancelled": "🚫 Bekor qilingan",
}

# ---------------- DB ----------------

async def db_init():
    global pool

    if DATABASE_URL:
        pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )

        async with pool.acquire() as con:
            await con.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    role TEXT NOT NULL DEFAULT 'customer',
                    phone TEXT,
                    language TEXT DEFAULT 'uz',
                    notifications BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS customers (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    address TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS masters (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    full_name TEXT,
                    phone TEXT,
                    services TEXT,
                    work_time TEXT,
                    approved BOOLEAN DEFAULT FALSE,
                    active BOOLEAN DEFAULT TRUE,
                    rating NUMERIC(3,2) DEFAULT 0,
                    rating_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    price NUMERIC(14,2) DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id BIGSERIAL PRIMARY KEY,
                    customer_id BIGINT REFERENCES users(user_id),
                    customer_name TEXT NOT NULL,
                    phone TEXT,
                    service TEXT NOT NULL,
                    address TEXT,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    comment TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    master_id BIGINT,
                    master_name TEXT,
                    price NUMERIC(14,2),
                    coupon_code TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    accepted_at TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    cancelled_at TIMESTAMPTZ
                );

                CREATE TABLE IF NOT EXISTS order_status_history (
                    id BIGSERIAL PRIMARY KEY,
                    order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
                    old_status TEXT,
                    new_status TEXT,
                    changed_by BIGINT,
                    note TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS ratings (
                    id BIGSERIAL PRIMARY KEY,
                    order_id BIGINT UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
                    customer_id BIGINT,
                    master_id BIGINT,
                    customer_rating INTEGER,
                    master_rating INTEGER,
                    customer_comment TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS customer_favorites (
                    customer_id BIGINT,
                    master_id BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY(customer_id, master_id)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id BIGSERIAL PRIMARY KEY,
                    order_id BIGINT REFERENCES orders(id) ON DELETE CASCADE,
                    user_id BIGINT,
                    kind TEXT,
                    due_at TIMESTAMPTZ,
                    sent BOOLEAN DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS coupons (
                    code TEXT PRIMARY KEY,
                    discount_percent INTEGER NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS coupon_usage (
                    code TEXT,
                    user_id BIGINT,
                    order_id BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS broadcasts (
                    id BIGSERIAL PRIMARY KEY,
                    text TEXT NOT NULL,
                    created_by BIGINT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS admin_logs (
                    id BIGSERIAL PRIMARY KEY,
                    admin_id BIGINT,
                    action TEXT,
                    details TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            for service in SERVICES:
                await con.execute(
                    """
                    INSERT INTO services(name)
                    VALUES($1)
                    ON CONFLICT(name) DO NOTHING
                    """,
                    service,
                )
    else:
        logger.warning("DATABASE_URL not set. PostgreSQL is required for persistent data.")


async def db_user(tg_user, role="customer"):
    if not pool:
        return

    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO users(user_id, username, full_name, role)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(user_id) DO UPDATE SET
                username=EXCLUDED.username,
                full_name=EXCLUDED.full_name
            """,
            tg_user.id,
            tg_user.username,
            tg_user.full_name,
            role,
        )


async def db_get_user(user_id):
    if not pool:
        return None

    async with pool.acquire() as con:
        return await con.fetchrow(
            "SELECT * FROM users WHERE user_id=$1",
            user_id,
        )


async def db_set_role(user_id, role):
    if not pool:
        return
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE users SET role=$1 WHERE user_id=$2",
            role,
            user_id,
        )


async def db_create_customer(user_id, address, lat, lon):
    if not pool:
        return
    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO customers(user_id,address,latitude,longitude)
            VALUES($1,$2,$3,$4)
            ON CONFLICT(user_id) DO UPDATE SET
                address=EXCLUDED.address,
                latitude=EXCLUDED.latitude,
                longitude=EXCLUDED.longitude,
                updated_at=NOW()
            """,
            user_id,
            address,
            lat,
            lon,
        )


async def db_create_order(data):
    if not pool:
        raise RuntimeError("DATABASE_URL is not configured")

    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            INSERT INTO orders(
                customer_id, customer_name, phone, service, address,
                latitude, longitude, comment, status
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,'new')
            RETURNING id
            """,
            data["customer_id"],
            data["customer_name"],
            data["phone"],
            data["service"],
            data["address"],
            data["latitude"],
            data["longitude"],
            data["comment"],
        )

        order_id = row["id"]

        await con.execute(
            """
            INSERT INTO order_status_history(order_id,new_status,changed_by)
            VALUES($1,'new',$2)
            """,
            order_id,
            data["customer_id"],
        )

        return order_id


async def db_order(order_id):
    if not pool:
        return None
    async with pool.acquire() as con:
        return await con.fetchrow(
            "SELECT * FROM orders WHERE id=$1",
            order_id,
        )


async def db_orders_customer(user_id, mode="all"):
    if not pool:
        return []

    condition = ""
    if mode == "active":
        condition = "AND status IN ('new','assigned','accepted','in_progress')"
    elif mode == "completed":
        condition = "AND status='completed'"

    async with pool.acquire() as con:
        return await con.fetch(
            f"""
            SELECT * FROM orders
            WHERE customer_id=$1 {condition}
            ORDER BY id DESC
            LIMIT 100
            """,
            user_id,
        )


async def db_orders_master(master_id, mode="active"):
    if not pool:
        return []

    if mode == "active":
        condition = "status IN ('assigned','accepted','in_progress')"
    else:
        condition = "status IN ('completed','rejected','cancelled')"

    async with pool.acquire() as con:
        return await con.fetch(
            f"""
            SELECT * FROM orders
            WHERE master_id=$1 AND {condition}
            ORDER BY id DESC
            LIMIT 100
            """,
            master_id,
        )


async def db_change_status(order_id, new_status, user_id, note=None):
    if not pool:
        return None

    async with pool.acquire() as con:
        async with con.transaction():
            old = await con.fetchval(
                "SELECT status FROM orders WHERE id=$1 FOR UPDATE",
                order_id,
            )

            if old is None:
                return None

            await con.execute(
                """
                UPDATE orders SET
                    status=$1,
                    accepted_at=CASE WHEN $1='accepted' THEN NOW() ELSE accepted_at END,
                    started_at=CASE WHEN $1='in_progress' THEN NOW() ELSE started_at END,
                    completed_at=CASE WHEN $1='completed' THEN NOW() ELSE completed_at END,
                    cancelled_at=CASE WHEN $1='cancelled' THEN NOW() ELSE cancelled_at END
                WHERE id=$2
                """,
                new_status,
                order_id,
            )

            await con.execute(
                """
                INSERT INTO order_status_history(
                    order_id,old_status,new_status,changed_by,note
                )
                VALUES($1,$2,$3,$4,$5)
                """,
                order_id,
                old,
                new_status,
                user_id,
                note,
            )

            return old


async def db_assign_master(order_id, master_id, master_name, admin_id):
    if not pool:
        return False

    async with pool.acquire() as con:
        result = await con.execute(
            """
            UPDATE orders SET
                master_id=$1,
                master_name=$2,
                status='assigned'
            WHERE id=$3
            """,
            master_id,
            master_name,
            order_id,
        )

        if result != "UPDATE 1":
            return False

        await con.execute(
            """
            INSERT INTO order_status_history(
                order_id,old_status,new_status,changed_by
            )
            VALUES($1,'new','assigned',$2)
            """,
            order_id,
            admin_id,
        )

        return True


async def db_get_approved_masters():
    if not pool:
        return []

    async with pool.acquire() as con:
        return await con.fetch(
            """
            SELECT * FROM masters
            WHERE approved=TRUE AND active=TRUE
            ORDER BY rating DESC, full_name
            """
        )


async def db_get_master(master_id):
    if not pool:
        return None
    async with pool.acquire() as con:
        return await con.fetchrow(
            "SELECT * FROM masters WHERE user_id=$1",
            master_id,
        )


async def db_register_master(user_id, name, phone, services, worktime):
    if not pool:
        return

    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO masters(
                user_id,full_name,phone,services,work_time,approved
            )
            VALUES($1,$2,$3,$4,$5,FALSE)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=EXCLUDED.full_name,
                phone=EXCLUDED.phone,
                services=EXCLUDED.services,
                work_time=EXCLUDED.work_time
            """,
            user_id,
            name,
            phone,
            services,
            worktime,
        )
        await con.execute(
            "UPDATE users SET role='master',phone=$1 WHERE user_id=$2",
            phone,
            user_id,
        )


async def db_approve_master(master_id, approved=True):
    if not pool:
        return
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE masters SET approved=$1 WHERE user_id=$2",
            approved,
            master_id,
        )
        await con.execute(
            "UPDATE users SET role='master' WHERE user_id=$1",
            master_id,
        )


async def db_master_requests():
    if not pool:
        return []
    async with pool.acquire() as con:
        return await con.fetch(
            """
            SELECT * FROM masters
            WHERE approved=FALSE
            ORDER BY created_at DESC
            """
        )


async def db_update_price(service, price):
    if not pool:
        return
    async with pool.acquire() as con:
        await con.execute(
            "UPDATE services SET price=$1 WHERE name=$2",
            price,
            service,
        )


async def db_prices():
    if not pool:
        return []
    async with pool.acquire() as con:
        return await con.fetch(
            "SELECT * FROM services WHERE active=TRUE ORDER BY id"
        )


async def db_create_coupon(code, discount):
    if not pool:
        return
    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO coupons(code,discount_percent)
            VALUES($1,$2)
            ON CONFLICT(code) DO UPDATE SET
                discount_percent=EXCLUDED.discount_percent,
                active=TRUE
            """,
            code.upper(),
            discount,
        )


async def db_get_stats():
    if not pool:
        return {}

    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER(WHERE status='new') AS new,
                COUNT(*) FILTER(WHERE status='assigned') AS assigned,
                COUNT(*) FILTER(WHERE status='accepted') AS accepted,
                COUNT(*) FILTER(WHERE status='in_progress') AS progress,
                COUNT(*) FILTER(WHERE status='completed') AS completed,
                COUNT(*) FILTER(WHERE status='cancelled') AS cancelled,
                COALESCE(SUM(price) FILTER(WHERE status='completed'),0) AS revenue
            FROM orders
            """
        )
        customers = await con.fetchval("SELECT COUNT(*) FROM users WHERE role='customer'")
        masters = await con.fetchval("SELECT COUNT(*) FROM masters WHERE approved=TRUE")

        return {
            "total": row["total"],
            "new": row["new"],
            "assigned": row["assigned"],
            "accepted": row["accepted"],
            "progress": row["progress"],
            "completed": row["completed"],
            "cancelled": row["cancelled"],
            "revenue": row["revenue"],
            "customers": customers,
            "masters": masters,
        }


async def db_export_orders():
    if not pool:
        return b""

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT id,customer_name,phone,service,address,
                   comment,status,master_name,price,created_at,
                   accepted_at,started_at,completed_at
            FROM orders
            ORDER BY id DESC
            """
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID","Customer","Phone","Service","Address","Comment",
        "Status","Master","Price","Created","Accepted","Started","Completed"
    ])

    for r in rows:
        writer.writerow([
            r["id"], r["customer_name"], r["phone"], r["service"],
            r["address"], r["comment"], r["status"], r["master_name"],
            r["price"], r["created_at"], r["accepted_at"],
            r["started_at"], r["completed_at"]
        ])

    return output.getvalue().encode("utf-8-sig")


# ---------------- KEYBOARDS ----------------

def client_menu():
    return ReplyKeyboardMarkup(
        [
            ["📝 Buyurtma berish", "📋 Buyurtmalarim"],
            ["🔎 Buyurtma holati", "❌ Bekor qilish"],
            ["🔁 Qayta buyurtma", "👨‍🔧 Mening ustalarim"],
            ["⭐ Reytingim", "💬 Sharh qoldirish"],
            ["🔔 Eslatmalarim", "⚙️ Sozlamalar"],
            ["👨‍🔧 Usta bo‘lish"],
        ],
        resize_keyboard=True,
    )


def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar", "📋 Mening buyurtmalarim"],
            ["👤 Profil", "👥 Mijozlarim"],
            ["📊 Mening statistikam", "💰 Kunlik daromad"],
            ["⭐ Reytingim"],
            ["🏠 Asosiy menyu"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Ustalar", "📦 Buyurtmalar"],
            ["👤 Mijozlar", "📊 Statistika"],
            ["📈 Hisobot", "💰 Narxlar"],
            ["📢 Xabarlar", "🎟 Kuponlar"],
            ["⚙️ Sozlamalar"],
            ["🏠 Asosiy menyu"],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        [["❌ Bekor qilish"]],
        resize_keyboard=True,
    )


def location_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Geolokatsiyani yuborish", request_location=True)],
            ["⏭ O‘tkazib yuborish"],
            ["❌ Bekor qilish"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------------- HELPERS ----------------

def is_admin(user_id):
    return user_id == ADMIN_ID and ADMIN_ID != 0


async def safe_send(bot, chat_id, text, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except Exception:
        logger.exception("Telegram send error")
        return None


def order_text(order):
    return (
        f"📦 <b>BUYURTMA #{order['id']}</b>\n\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['phone'] or '-'}\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"📍 Manzil: {order['address'] or '-'}\n"
        f"💬 Izoh: {order['comment'] or '-'}\n"
        f"👨‍🔧 Usta: {order['master_name'] or 'Hali biriktirilmagan'}\n"
        f"💰 Narx: {order['price'] or '-'}\n"
        f"📌 Holat: {STATUS_NAMES.get(order['status'], order['status'])}"
    )


async def notify_admin(context, text):
    if ADMIN_ID:
        await safe_send(context.bot, ADMIN_ID, text)


async def notify_masters_group(context, order):
    if not MASTERS_GROUP_ID:
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Qabul qilish",
                callback_data=f"accept:{order['id']}"
            ),
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"reject:{order['id']}"
            ),
        ]
    ])

    await safe_send(
        context.bot,
        MASTERS_GROUP_ID,
        order_text(order),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


# ---------------- START / ROLE ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db_user(user)

    if is_admin(user.id):
        await db_set_role(user.id, "admin")
        await update.message.reply_text(
            "👑 <b>USTA 24 ANDIJON — ADMIN</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu(),
        )
        return

    row = await db_get_master(user.id)

    if row and row["approved"]:
        await db_set_role(user.id, "master")
        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 ANDIJON — USTA</b>\n\n"
            "Xush kelibsiz!",
            parse_mode=ParseMode.HTML,
            reply_markup=master_menu(),
        )
        return

    await update.message.reply_text(
        "👤 <b>USTA 24 ANDIJON</b>\n\n"
        "Xush kelibsiz!\n"
        "Uyga xizmat ko‘rsatish uchun buyurtma bering.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )


async def menu_command(update, context):
    user = update.effective_user

    if is_admin(user.id):
        await update.message.reply_text(
            "👑 Admin menyu",
            reply_markup=admin_menu(),
        )
        return

    master = await db_get_master(user.id)
    if master and master["approved"]:
        await update.message.reply_text(
            "👨‍🔧 Usta menyu",
            reply_markup=master_menu(),
        )
        return

    await update.message.reply_text(
        "👤 Mijoz menyu",
        reply_markup=client_menu(),
    )


# ---------------- CLIENT ORDER ----------------

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"] = {}
    await update.message.reply_text(
        "📝 <b>Yangi buyurtma</b>\n\n"
        "1️⃣ Ismingizni yozing:",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )
    return C_NAME


async def order_name(update, context):
    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if len(text) < 2:
        await update.message.reply_text("❌ Ismni to‘g‘ri kiriting.")
        return C_NAME

    context.user_data["order"]["customer_name"] = text

    await update.message.reply_text(
        "2️⃣ 📞 Telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("📱 Telefon raqamim", request_contact=True)],
                ["❌ Bekor qilish"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return C_PHONE


async def order_phone(update, context):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()

    if phone == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if len(phone) < 7:
        await update.message.reply_text("❌ Telefon raqamini to‘g‘ri kiriting.")
        return C_PHONE

    context.user_data["order"]["phone"] = phone

    await update.message.reply_text(
        "3️⃣ 📍 Joylashuvingizni yuboring:",
        reply_markup=location_keyboard(),
    )
    return C_LOCATION


async def order_location(update, context):
    if update.message.text == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if update.message.location:
        loc = update.message.location
        context.user_data["order"]["latitude"] = loc.latitude
        context.user_data["order"]["longitude"] = loc.longitude
        await update.message.reply_text("✅ Geolokatsiya qabul qilindi.")
    else:
        context.user_data["order"]["latitude"] = None
        context.user_data["order"]["longitude"] = None

    await update.message.reply_text(
        "4️⃣ 🛠 Xizmat turini tanlang:",
        reply_markup=ReplyKeyboardMarkup(
            [[s] for s in SERVICES] + [["❌ Bekor qilish"]],
            resize_keyboard=True,
        ),
    )
    return C_SERVICE


async def order_service(update, context):
    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if text not in SERVICES:
        await update.message.reply_text("❌ Xizmatlardan birini tanlang.")
        return C_SERVICE

    context.user_data["order"]["service"] = text

    await update.message.reply_text(
        "5️⃣ 📍 To‘liq manzilni yozing:\n\n"
        "Masalan: Andijon shahar, Bobur ko‘chasi, 10-uy",
        reply_markup=cancel_keyboard(),
    )
    return C_ADDRESS


async def order_address(update, context):
    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if len(text) < 3:
        await update.message.reply_text("❌ Manzilni to‘liqroq yozing.")
        return C_ADDRESS

    context.user_data["order"]["address"] = text

    await update.message.reply_text(
        "6️⃣ 💬 Qo‘shimcha izoh yozing.\n"
        "Agar izoh bo‘lmasa: <b>Yo‘q</b> deb yozing.",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )
    return C_COMMENT


async def order_comment(update, context):
    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await order_cancel(update, context)

    if text.lower() in ("yo‘q", "yo'q", "yok", "yoq", "-"):
        text = ""

    data = context.user_data["order"]
    data["comment"] = text
    data["customer_id"] = update.effective_user.id

    try:
        order_id = await db_create_order(data)
    except Exception as e:
        logger.exception("Order create error")
        await update.message.reply_text(
            "❌ Buyurtmani saqlashda xatolik yuz berdi.\n"
            "Iltimos, keyinroq qayta urinib ko‘ring."
        )
        return ConversationHandler.END

    order = await db_order(order_id)

    await update.message.reply_text(
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"🆔 Buyurtma ID: <b>#{order_id}</b>\n"
        f"📌 Holat: {STATUS_NAMES['new']}\n\n"
        "Usta biriktirilganda sizga xabar beramiz.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )

    await notify_admin(
        context,
        "🆕 <b>YANGI BUYURTMA</b>\n\n" + order_text(order),
    )
    await notify_masters_group(context, order)

    context.user_data.pop("order", None)

    return ConversationHandler.END


async def order_cancel(update, context):
    context.user_data.pop("order", None)

    await update.message.reply_text(
        "❌ Buyurtma berish bekor qilindi.",
        reply_markup=client_menu(),
    )
    return ConversationHandler.END


# ---------------- CLIENT ORDERS ----------------

async def my_orders(update, context):
    rows = await db_orders_customer(update.effective_user.id, "all")

    if not rows:
        await update.message.reply_text(
            "📋 Sizda hozircha buyurtmalar yo‘q.",
            reply_markup=client_menu(),
        )
        return

    text = "📋 <b>Mening buyurtmalarim</b>\n\n"

    for r in rows[:30]:
        text += (
            f"🆔 #{r['id']} — {STATUS_NAMES.get(r['status'], r['status'])}\n"
            f"🛠 {r['service']}\n"
            f"📅 {r['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )


async def order_status_start(update, context):
    await update.message.reply_text(
        "🔎 Buyurtma ID raqamini yuboring.\n"
        "Masalan: <b>100001</b>",
        parse_mode=ParseMode.HTML,
    )


async def order_status_text(update, context):
    text = update.message.text.strip()

    if not text.isdigit():
        return

    order = await db_order(int(text))

    if not order:
        await update.message.reply_text("❌ Bunday buyurtma topilmadi.")
        return

    if order["customer_id"] != update.effective_user.id and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bu buyurtma sizga tegishli emas.")
        return

    await update.message.reply_text(
        order_text(order),
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )


async def cancel_order_start(update, context):
    rows = await db_orders_customer(update.effective_user.id, "active")

    if not rows:
        await update.message.reply_text("📭 Bekor qilinadigan faol buyurtma yo‘q.")
        return

    buttons = []
    for r in rows:
        buttons.append([
            InlineKeyboardButton(
                f"❌ #{r['id']} — {r['service'][:25]}",
                callback_data=f"cancel:{r['id']}",
            )
        ])

    await update.message.reply_text(
        "❌ Bekor qilmoqchi bo‘lgan buyurtmani tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def reorder(update, context):
    rows = await db_orders_customer(update.effective_user.id, "completed")

    if not rows:
        await update.message.reply_text(
            "🔁 Qayta buyurtma uchun tugallangan buyurtmangiz yo‘q."
        )
        return

    r = rows[0]

    context.user_data["order"] = {
        "customer_name": r["customer_name"],
        "phone": r["phone"],
        "service": r["service"],
        "address": r["address"],
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "comment": r["comment"] or "",
        "customer_id": update.effective_user.id,
    }

    await update.message.reply_text(
        f"🔁 Oldingi xizmat: <b>{r['service']}</b>\n\n"
        "Izohni yangilash uchun yozing yoki <b>Yo‘q</b> deb yozing.",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )

    return C_COMMENT


async def favorites(update, context):
    if not pool:
        await update.message.reply_text("Ma'lumotlar bazasi ulanmagan.")
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT m.*
            FROM customer_favorites f
            JOIN masters m ON m.user_id=f.master_id
            WHERE f.customer_id=$1
            ORDER BY f.created_at DESC
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Sevimli ustalaringiz hozircha yo‘q."
        )
        return

    text = "👨‍🔧 <b>Mening ustalarim</b>\n\n"
    for r in rows:
        text += (
            f"👨‍🔧 {r['full_name']}\n"
            f"📞 {r['phone'] or '-'}\n"
            f"⭐ {r['rating']}\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def client_rating(update, context):
    if not pool:
        await update.message.reply_text("⭐ Hozircha reyting mavjud emas.")
        return

    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT
                COUNT(*) FILTER(WHERE customer_rating IS NOT NULL) AS count,
                COALESCE(AVG(customer_rating),0) AS avg
            FROM ratings
            WHERE customer_id=$1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"⭐ <b>Mening reytingim</b>\n\n"
        f"Baholar soni: {row['count']}\n"
        f"O‘rtacha: {float(row['avg']):.2f}",
        parse_mode=ParseMode.HTML,
    )


async def reviews_start(update, context):
    if not pool:
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT o.id,o.service
            FROM orders o
            LEFT JOIN ratings r ON r.order_id=o.id
            WHERE o.customer_id=$1
              AND o.status='completed'
              AND r.id IS NULL
            ORDER BY o.id DESC
            LIMIT 10
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text(
            "💬 Hozircha sharh qoldirish uchun buyurtma yo‘q."
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"⭐ #{r['id']} — {r['service'][:22]}",
                callback_data=f"rate:{r['id']}",
            )
        ]
        for r in rows
    ]

    await update.message.reply_text(
        "💬 Buyurtmani tanlang:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ---------------- MASTER REGISTRATION ----------------

async def master_register_start(update, context):
    existing = await db_get_master(update.effective_user.id)

    if existing and existing["approved"]:
        await update.message.reply_text(
            "✅ Siz allaqachon tasdiqlangan ustasiz.",
            reply_markup=master_menu(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👨‍🔧 <b>Usta bo‘lish</b>\n\n"
        "Telefon raqamingizni yuboring:",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("📱 Telefon raqamim", request_contact=True)],
                ["❌ Bekor qilish"],
            ],
            resize_keyboard=True,
        ),
    )
    return M_PHONE


async def master_phone(update, context):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text(
            "Bekor qilindi.",
            reply_markup=client_menu(),
        )
        return ConversationHandler.END

    phone = (
        update.message.contact.phone_number
        if update.message.contact
        else update.message.text.strip()
    )

    context.user_data["master"] = {"phone": phone}

    await update.message.reply_text(
        "👤 To‘liq ism-familiyangizni yozing:",
        reply_markup=cancel_keyboard(),
    )
    return M_NAME


async def master_name(update, context):
    context.user_data["master"]["name"] = update.message.text.strip()

    await update.message.reply_text(
        "🛠 Qaysi xizmatlarni bajarasiz?\n\n"
        "Xizmat nomlarini vergul bilan yozing.\n"
        "Masalan: Mebel yig‘ish, Mebel ta’mirlash",
        reply_markup=cancel_keyboard(),
    )
    return M_SERVICES


async def master_services(update, context):
    context.user_data["master"]["services"] = update.message.text.strip()

    await update.message.reply_text(
        "🕐 Ish vaqtingizni yozing.\n"
        "Masalan: 09:00 - 20:00",
        reply_markup=cancel_keyboard(),
    )
    return M_WORKTIME


async def master_worktime(update, context):
    data = context.user_data["master"]
    data["worktime"] = update.message.text.strip()

    await db_register_master(
        update.effective_user.id,
        data["name"],
        data["phone"],
        data["services"],
        data["worktime"],
    )

    await update.message.reply_text(
        "✅ <b>Usta bo‘lish so‘rovingiz yuborildi.</b>\n\n"
        "👑 Admin tasdiqlaganidan keyin usta menyusi ochiladi.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )

    await notify_admin(
        context,
        "👨‍🔧 <b>YANGI USTA SO‘ROVI</b>\n\n"
        f"ID: <code>{update.effective_user.id}</code>\n"
        f"Ism: {data['name']}\n"
        f"Telefon: {data['phone']}\n"
        f"Xizmatlar: {data['services']}\n"
        f"Ish vaqti: {data['worktime']}",
    )

    context.user_data.pop("master", None)
    return ConversationHandler.END


# ---------------- MASTER MENU ----------------

async def master_profile(update, context):
    m = await db_get_master(update.effective_user.id)

    if not m:
        await update.message.reply_text(
            "❌ Siz usta sifatida ro‘yxatdan o‘tmagansiz."
        )
        return

    await update.message.reply_text(
        f"👨‍🔧 <b>PROFIL</b>\n\n"
        f"👤 {m['full_name']}\n"
        f"📞 {m['phone'] or '-'}\n"
        f"🛠 {m['services'] or '-'}\n"
        f"🕐 {m['work_time'] or '-'}\n"
        f"⭐ {m['rating']}\n"
        f"📊 Baholar: {m['rating_count']}\n"
        f"Holat: {'✅ Tasdiqlangan' if m['approved'] else '⏳ Kutilmoqda'}",
        parse_mode=ParseMode.HTML,
        reply_markup=master_menu(),
    )


async def master_new_orders(update, context):
    if not pool:
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT * FROM orders
            WHERE status='new'
            ORDER BY id DESC
            LIMIT 30
            """
        )

    if not rows:
        await update.message.reply_text("🆕 Yangi buyurtmalar yo‘q.")
        return

    for r in rows:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Qabul qilish",
                    callback_data=f"accept:{r['id']}"
                ),
                InlineKeyboardButton(
                    "❌ Rad etish",
                    callback_data=f"reject:{r['id']}"
                ),
            ]
        ])

        await update.message.reply_text(
            order_text(r),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def master_orders(update, context):
    rows = await db_orders_master(update.effective_user.id, "active")

    if not rows:
        await update.message.reply_text(
            "📋 Faol buyurtmalaringiz yo‘q."
        )
        return

    for r in rows:
        keyboard = []

        if r["status"] == "accepted":
            keyboard.append([
                InlineKeyboardButton(
                    "🔧 Ishni boshlash",
                    callback_data=f"start:{r['id']}"
                )
            ])
        elif r["status"] == "in_progress":
            keyboard.append([
                InlineKeyboardButton(
                    "🏁 Ishni yakunlash",
                    callback_data=f"complete:{r['id']}"
                )
            ])

        await update.message.reply_text(
            order_text(r),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        )


async def master_customers(update, context):
    if not pool:
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT DISTINCT customer_id,customer_name,phone
            FROM orders
            WHERE master_id=$1
            ORDER BY customer_name
            LIMIT 100
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text("👥 Hali mijozlaringiz yo‘q.")
        return

    text = "👥 <b>Mijozlarim</b>\n\n"
    for r in rows:
        text += (
            f"👤 {r['customer_name']}\n"
            f"📞 {r['phone'] or '-'}\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def master_stats(update, context):
    if not pool:
        return

    async with pool.acquire() as con:
        row = await con.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER(WHERE status='completed') AS completed,
                COALESCE(SUM(price) FILTER(WHERE status='completed'),0) AS revenue,
                COALESCE(AVG(
                    CASE WHEN status='completed'
                    THEN EXTRACT(EPOCH FROM (completed_at-created_at))/3600
                    END
                ),0) AS avg_hours
            FROM orders
            WHERE master_id=$1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"📊 <b>Mening statistikam</b>\n\n"
        f"📦 Jami: {row['total']}\n"
        f"🏁 Tugallangan: {row['completed']}\n"
        f"💰 Daromad: {row['revenue']}\n"
        f"⏱ O‘rtacha vaqt: {float(row['avg_hours']):.1f} soat",
        parse_mode=ParseMode.HTML,
    )


async def master_daily_income(update, context):
    if not pool:
        return

    async with pool.acquire() as con:
        value = await con.fetchval(
            """
            SELECT COALESCE(SUM(price),0)
            FROM orders
            WHERE master_id=$1
              AND status='completed'
              AND completed_at >= CURRENT_DATE
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"💰 <b>Bugungi daromad:</b> {value}",
        parse_mode=ParseMode.HTML,
    )


async def master_rating(update, context):
    m = await db_get_master(update.effective_user.id)

    if not m:
        await update.message.reply_text("⭐ Reyting topilmadi.")
        return

    await update.message.reply_text(
        f"⭐ <b>Mening reytingim</b>\n\n"
        f"Reyting: {m['rating']}\n"
        f"Baholar: {m['rating_count']}",
        parse_mode=ParseMode.HTML,
    )


# ---------------- CALLBACKS ----------------

async def callbacks(update, context):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if ":" not in data:
        return

    action, raw_id = data.split(":", 1)

    try:
        order_id = int(raw_id)
    except ValueError:
        return

    order = await db_order(order_id)

    if not order:
        await query.edit_message_text("❌ Buyurtma topilmadi.")
        return

    # MASTER ACCEPT
    if action == "accept":
        m = await db_get_master(user_id)

        if not m or not m["approved"]:
            await query.answer("❌ Siz tasdiqlangan usta emassiz.", show_alert=True)
            return

        if order["status"] != "new":
            await query.answer("⚠️ Bu buyurtma allaqachon olingan.", show_alert=True)
            return

        await db_assign_master(
            order_id,
            user_id,
            m["full_name"],
            user_id,
        )

        await safe_send(
            context.bot,
            order["customer_id"],
            f"✅ <b>Buyurtma #{order_id}</b>\n\n"
            f"👨‍🔧 Usta: {m['full_name']}\n"
            "Buyurtmangiz qabul qilindi.",
            parse_mode=ParseMode.HTML,
        )

        await query.edit_message_text(
            f"✅ Buyurtma #{order_id} sizga biriktirildi."
        )
        return

    # MASTER REJECT
    if action == "reject":
        m = await db_get_master(user_id)

        if not m or not m["approved"]:
            await query.answer("❌ Ruxsat yo‘q.", show_alert=True)
            return

        await db_change_status(
            order_id,
            "rejected",
            user_id,
            "Master rejected",
        )

        await query.edit_message_text(
            f"❌ Buyurtma #{order_id} rad etildi."
        )
        return

    # START
    if action == "start":
        if order["master_id"] != user_id:
            await query.answer("❌ Bu buyurtma sizga tegishli emas.", show_alert=True)
            return

        await db_change_status(order_id, "in_progress", user_id)

        await safe_send(
            context.bot,
            order["customer_id"],
            f"🔧 <b>Buyurtma #{order_id}</b>\n\n"
            "Usta ishni boshladi.",
            parse_mode=ParseMode.HTML,
        )

        await query.edit_message_text(
            f"🔧 Buyurtma #{order_id}: ish boshlandi."
        )
        return

    # COMPLETE
    if action == "complete":
        if order["master_id"] != user_id:
            await query.answer("❌ Ruxsat yo‘q.", show_alert=True)
            return

        await db_change_status(order_id, "completed", user_id)

        await safe_send(
            context.bot,
            order["customer_id"],
            f"🏁 <b>Buyurtma #{order_id} tugallandi.</b>\n\n"
            "Iltimos, ustaga baho bering:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐ 1", callback_data=f"rating:{order_id}:1"),
                    InlineKeyboardButton("⭐ 2", callback_data=f"rating:{order_id}:2"),
                    InlineKeyboardButton("⭐ 3", callback_data=f"rating:{order_id}:3"),
                ],
                [
                    InlineKeyboardButton("⭐ 4", callback_data=f"rating:{order_id}:4"),
                    InlineKeyboardButton("⭐ 5", callback_data=f"rating:{order_id}:5"),
                ],
            ]),
        )

        await query.edit_message_text(
            f"🏁 Buyurtma #{order_id} tugallandi."
        )
        return

    # CUSTOMER CANCEL
    if action == "cancel":
        if order["customer_id"] != user_id:
            await query.answer("❌ Ruxsat yo‘q.", show_alert=True)
            return

        if order["status"] not in ("new", "assigned", "accepted"):
            await query.answer(
                "⚠️ Bu buyurtmani bekor qilib bo‘lmaydi.",
                show_alert=True,
            )
            return

        await db_change_status(order_id, "cancelled", user_id)

        await query.edit_message_text(
            f"🚫 Buyurtma #{order_id} bekor qilindi."
        )

        if order["master_id"]:
            await safe_send(
                context.bot,
                order["master_id"],
                f"🚫 Buyurtma #{order_id} mijoz tomonidan bekor qilindi.",
            )
        return

    # RATING
    if action == "rating":
        parts = data.split(":")
        if len(parts) != 3:
            return

        rating = int(parts[2])

        if order["customer_id"] != user_id:
            await query.answer("❌ Ruxsat yo‘q.", show_alert=True)
            return

        if not pool:
            return

        async with pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO ratings(
                    order_id,customer_id,master_id,customer_rating
                )
                VALUES($1,$2,$3,$4)
                ON CONFLICT(order_id) DO UPDATE SET
                    customer_rating=EXCLUDED.customer_rating
                """,
                order_id,
                user_id,
                order["master_id"],
                rating,
            )

            if order["master_id"]:
                await con.execute(
                    """
                    UPDATE masters
                    SET
                        rating = (
                            SELECT COALESCE(AVG(customer_rating),0)
                            FROM ratings
                            WHERE master_id=$1
                              AND customer_rating IS NOT NULL
                        ),
                        rating_count = (
                            SELECT COUNT(*)
                            FROM ratings
                            WHERE master_id=$1
                              AND customer_rating IS NOT NULL
                        )
                    WHERE user_id=$1
                    """,
                    order["master_id"],
                )

        await query.edit_message_text(
            f"⭐ Rahmat! Siz {rating}/5 baho berdingiz."
        )
        return


# ---------------- ADMIN ----------------

async def admin_guard(update):
    return is_admin(update.effective_user.id)


async def admin_masters(update, context):
    if not await admin_guard(update):
        return

    buttons = [
        [InlineKeyboardButton(
            "📋 Usta so‘rovlari",
            callback_data="admin:master_requests"
        )],
        [InlineKeyboardButton(
            "👨‍🔧 Tasdiqlangan ustalar",
            callback_data="admin:masters"
        )],
    ]

    await update.message.reply_text(
        "👨‍🔧 <b>Ustalar boshqaruvi</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_orders(update, context):
    if not await admin_guard(update):
        return

    if not pool:
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT * FROM orders
            ORDER BY id DESC
            LIMIT 30
            """
        )

    if not rows:
        await update.message.reply_text("📦 Buyurtmalar yo‘q.")
        return

    for r in rows[:20]:
        buttons = []

        if r["status"] in ("new", "rejected"):
            buttons.append([
                InlineKeyboardButton(
                    "👨‍🔧 Ustaga biriktirish",
                    callback_data=f"adminassign:{r['id']}"
                )
            ])

        await update.message.reply_text(
            order_text(r),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )


async def admin_customers(update, context):
    if not await admin_guard(update):
        return

    if not pool:
        return

    async with pool.acquire() as con:
        rows = await con.fetch(
            """
            SELECT u.user_id,u.full_name,u.username,u.phone,
                   COUNT(o.id) AS orders_count
            FROM users u
            LEFT JOIN orders o ON o.customer_id=u.user_id
            WHERE u.role='customer'
            GROUP BY u.user_id
            ORDER BY orders_count DESC
            LIMIT 100
            """
        )

    text = "👤 <b>Mijozlar</b>\n\n"
    for r in rows:
        text += (
            f"👤 {r['full_name'] or '-'}\n"
            f"📞 {r['phone'] or '-'}\n"
            f"📦 Buyurtmalar: {r['orders_count']}\n\n"
        )

    await update.message.reply_text(
        text[:4000],
        parse_mode=ParseMode.HTML,
    )


async def admin_stats(update, context):
    if not await admin_guard(update):
        return

    s = await db_get_stats()

    await update.message.reply_text(
        f"📊 <b>USTA 24 STATISTIKA</b>\n\n"
        f"👤 Mijozlar: {s.get('customers',0)}\n"
        f"👨‍🔧 Ustalar: {s.get('masters',0)}\n"
        f"📦 Jami buyurtmalar: {s.get('total',0)}\n"
        f"🆕 Yangi: {s.get('new',0)}\n"
        f"👨‍🔧 Biriktirilgan: {s.get('assigned',0)}\n"
        f"✅ Qabul qilingan: {s.get('accepted',0)}\n"
        f"🔧 Jarayonda: {s.get('progress',0)}\n"
        f"🏁 Tugallangan: {s.get('completed',0)}\n"
        f"🚫 Bekor qilingan: {s.get('cancelled',0)}\n"
        f"💰 Tushum: {s.get('revenue',0)}",
        parse_mode=ParseMode.HTML,
    )


async def admin_report(update, context):
    if not await admin_guard(update):
        return

    data = await db_export_orders()

    await update.message.reply_document(
        document=io.BytesIO(data),
        filename=f"usta24_orders_{datetime.now():%Y%m%d_%H%M}.csv",
        caption="📈 USTA 24 buyurtmalar hisoboti",
    )


async def admin_prices(update, context):
    if not await admin_guard(update):
        return

    rows = await db_prices()

    buttons = [
        [
            InlineKeyboardButton(
                f"{r['name'][:25]} — {r['price'] or 0}",
                callback_data=f"price:{r['id']}",
            )
        ]
        for r in rows
    ]

    await update.message.reply_text(
        "💰 <b>Xizmat narxlari</b>\n\n"
        "Narxni o‘zgartirish uchun xizmatni tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_broadcast_start(update, context):
    if not await admin_guard(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 Barcha mijozlarga yuboriladigan xabarni yozing:",
        reply_markup=cancel_keyboard(),
    )
    return ADMIN_BROADCAST


async def admin_broadcast_send(update, context):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text(
            "Bekor qilindi.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    if not pool:
        return ConversationHandler.END

    text = update.message.text

    async with pool.acquire() as con:
        users = await con.fetch(
            """
            SELECT user_id FROM users
            WHERE notifications=TRUE AND role='customer'
            """
        )

        await con.execute(
            """
            INSERT INTO broadcasts(text,created_by)
            VALUES($1,$2)
            """,
            text,
            update.effective_user.id,
        )

    sent = 0

    for u in users:
        msg = await safe_send(
            context.bot,
            u["user_id"],
            f"📢 <b>USTA 24</b>\n\n{text}",
            parse_mode=ParseMode.HTML,
        )
        if msg:
            sent += 1
        await asyncio.sleep(0.03)

    await update.message.reply_text(
        f"✅ Xabar yuborildi.\n"
        f"📨 Qabul qiluvchilar: {len(users)}\n"
        f"✅ Yetkazildi: {sent}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


async def admin_coupon_start(update, context):
    if not await admin_guard(update):
        return ConversationHandler.END

    await update.message.reply_text(
        "🎟 Kupon kodini yozing.\n"
        "Masalan: USTA10",
        reply_markup=cancel_keyboard(),
    )
    return ADMIN_COUPON_CODE


async def admin_coupon_code(update, context):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text(
            "Bekor qilindi.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    context.user_data["coupon_code"] = update.message.text.strip().upper()

    await update.message.reply_text(
        "Chegirma foizini yozing.\n"
        "Masalan: 10",
        reply_markup=cancel_keyboard(),
    )
    return ADMIN_COUPON_DISCOUNT


async def admin_coupon_discount(update, context):
    try:
        discount = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting.")
        return ADMIN_COUPON_DISCOUNT

    if not 1 <= discount <= 100:
        await update.message.reply_text("❌ 1 dan 100 gacha kiriting.")
        return ADMIN_COUPON_DISCOUNT

    code = context.user_data.pop("coupon_code")

    await db_create_coupon(code, discount)

    await update.message.reply_text(
        f"✅ Kupon yaratildi.\n\n"
        f"🎟 {code}\n"
        f"💸 {discount}%",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


async def admin_settings(update, context):
    if not await admin_guard(update):
        return

    await update.message.reply_text(
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"Admin ID: <code>{ADMIN_ID}</code>\n"
        f"Masters Group ID: <code>{MASTERS_GROUP_ID}</code>\n"
        f"Database: {'✅ PostgreSQL' if pool else '❌ ulanmagan'}",
        parse_mode=ParseMode.HTML,
    )


# ---------------- ADMIN CALLBACKS ----------------

async def admin_callbacks(update, context):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    await query.answer()

    data = query.data

    if data == "admin:master_requests":
        rows = await db_master_requests()

        if not rows:
            await query.edit_message_text(
                "📭 Yangi usta so‘rovlari yo‘q."
            )
            return

        for r in rows:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Tasdiqlash",
                        callback_data=f"approve:{r['user_id']}"
                    ),
                    InlineKeyboardButton(
                        "❌ Rad etish",
                        callback_data=f"deny:{r['user_id']}"
                    ),
                ]
            ])

            await safe_send(
                context.bot,
                query.from_user.id,
                f"👨‍🔧 <b>Usta so‘rovi</b>\n\n"
                f"ID: <code>{r['user_id']}</code>\n"
                f"👤 {r['full_name']}\n"
                f"📞 {r['phone']}\n"
                f"🛠 {r['services']}\n"
                f"🕐 {r['work_time']}",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

        await query.edit_message_text(
            "📋 Usta so‘rovlari yuborildi."
        )
        return

    if data == "admin:masters":
        rows = await db_get_approved_masters()

        if not rows:
            await query.edit_message_text("📭 Tasdiqlangan ustalar yo‘q.")
            return

        text = "👨‍🔧 <b>Tasdiqlangan ustalar</b>\n\n"

        for r in rows:
            text += (
                f"👨‍🔧 {r['full_name']}\n"
                f"📞 {r['phone']}\n"
                f"⭐ {r['rating']}\n"
                f"ID: <code>{r['user_id']}</code>\n\n"
            )

        await query.edit_message_text(
            text[:4000],
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("approve:"):
        master_id = int(data.split(":")[1])
        await db_approve_master(master_id, True)

        await safe_send(
            context.bot,
            master_id,
            "🎉 <b>Tabriklaymiz!</b>\n\n"
            "Sizning usta sifatidagi profilingiz admin tomonidan tasdiqlandi.",
            parse_mode=ParseMode.HTML,
            reply_markup=master_menu(),
        )

        await query.edit_message_text(
            f"✅ Usta <code>{master_id}</code> tasdiqlandi.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("deny:"):
        master_id = int(data.split(":")[1])
        await db_approve_master(master_id, False)

        await safe_send(
            context.bot,
            master_id,
            "❌ Usta bo‘lish so‘rovingiz rad etildi.",
        )

        await query.edit_message_text(
            f"❌ Usta <code>{master_id}</code> rad etildi.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("adminassign:"):
        order_id = int(data.split(":")[1])
        masters = await db_get_approved_masters()

        if not masters:
            await query.answer(
                "❌ Tasdiqlangan usta yo‘q.",
                show_alert=True,
            )
            return

        buttons = [
            [
                InlineKeyboardButton(
                    f"👨‍🔧 {m['full_name']} ⭐{m['rating']}",
                    callback_data=f"assign:{order_id}:{m['user_id']}",
                )
            ]
            for m in masters
        ]

        await query.message.reply_text(
            f"👨‍🔧 #{order_id} uchun ustani tanlang:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data.startswith("assign:"):
        _, order_raw, master_raw = data.split(":")
        order_id = int(order_raw)
        master_id = int(master_raw)

        m = await db_get_master(master_id)

        if not m:
            await query.answer("Usta topilmadi.", show_alert=True)
            return

        ok = await db_assign_master(
            order_id,
            master_id,
            m["full_name"],
            query.from_user.id,
        )

        if not ok:
            await query.answer("❌ Buyurtma topilmadi.", show_alert=True)
            return

        order = await db_order(order_id)

        await safe_send(
            context.bot,
            master_id,
            "🆕 <b>Sizga yangi buyurtma biriktirildi!</b>\n\n"
            + order_text(order),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Qabul qilish",
                        callback_data=f"accept:{order_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Rad etish",
                        callback_data=f"reject:{order_id}"
                    ),
                ]
            ]),
        )

        await safe_send(
            context.bot,
            order["customer_id"],
            f"👨‍🔧 <b>Buyurtma #{order_id}</b>\n\n"
            f"Usta biriktirildi: {m['full_name']}",
            parse_mode=ParseMode.HTML,
        )

        await query.edit_message_text(
            f"✅ #{order_id} — {m['full_name']} ustaga biriktirildi."
        )
        return

    if data.startswith("price:"):
        if not pool:
            return

        service_id = int(data.split(":")[1])

        async with pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT * FROM services WHERE id=$1",
                service_id,
            )

        if not row:
            return

        context.user_data["price_service"] = row["name"]

        await query.message.reply_text(
            f"💰 <b>{row['name']}</b>\n\n"
            f"Joriy narx: {row['price'] or 0}\n\n"
            "Yangi narxni yuboring:",
            parse_mode=ParseMode.HTML,
        )
        return


# ---------------- TEXT ROUTER ----------------

async def text_router(update, context):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id

    # Price editing
    if is_admin(user_id) and context.user_data.get("price_service"):
        try:
            price = float(text)
            service = context.user_data.pop("price_service")
            await db_update_price(service, price)
            await update.message.reply_text(
                f"✅ {service}\n💰 Yangi narx: {price}",
                reply_markup=admin_menu(),
            )
        except ValueError:
            await update.message.reply_text("❌ Narxni raqamda kiriting.")
        return

    # Admin
    if is_admin(user_id):
        if text == "👨‍🔧 Ustalar":
            await admin_masters(update, context)
            return
        if text == "📦 Buyurtmalar":
            await admin_orders(update, context)
            return
        if text == "👤 Mijozlar":
            await admin_customers(update, context)
            return
        if text == "📊 Statistika":
            await admin_stats(update, context)
            return
        if text == "📈 Hisobot":
            await admin_report(update, context)
            return
        if text == "💰 Narxlar":
            await admin_prices(update, context)
            return
        if text == "📢 Xabarlar":
            await admin_broadcast_start(update, context)
            return
        if text == "🎟 Kuponlar":
            await admin_coupon_start(update, context)
            return
        if text == "⚙️ Sozlamalar":
            await admin_settings(update, context)
            return
        if text == "🏠 Asosiy menyu":
            await update.message.reply_text(
                "👑 Admin menyu",
                reply_markup=admin_menu(),
            )
            return

    # Master
    m = await db_get_master(user_id)

    if m and m["approved"]:
        if text == "🆕 Yangi buyurtmalar":
            await master_new_orders(update, context)
            return
        if text == "📋 Mening buyurtmalarim":
            await master_orders(update, context)
            return
        if text == "👤 Profil":
            await master_profile(update, context)
            return
        if text == "👥 Mijozlarim":
            await master_customers(update, context)
            return
        if text == "📊 Mening statistikam":
            await master_stats(update, context)
            return
        if text == "💰 Kunlik daromad":
            await master_daily_income(update, context)
            return
        if text == "⭐ Reytingim":
            await master_rating(update, context)
            return
        if text == "🏠 Asosiy menyu":
            await update.message.reply_text(
                "👨‍🔧 Usta menyu",
                reply_markup=master_menu(),
            )
            return

    # Client
    if text == "📝 Buyurtma berish":
        # ConversationHandler handles it
        return

    if text == "📋 Buyurtmalarim":
        await my_orders(update, context)
        return

    if text == "🔎 Buyurtma holati":
        await order_status_start(update, context)
        return

    if text == "❌ Bekor qilish":
        await cancel_order_start(update, context)
        return

    if text == "🔁 Qayta buyurtma":
        await reorder(update, context)
        return

    if text == "👨‍🔧 Mening ustalarim":
        await favorites(update, context)
        return

    if text == "⭐ Reytingim":
        await client_rating(update, context)
        return

    if text == "💬 Sharh qoldirish":
        await reviews_start(update, context)
        return

    if text == "🔔 Eslatmalarim":
        await update.message.reply_text(
            "🔔 Eslatmalar avtomatik yuboriladi:\n\n"
            "• Buyurtma qabul qilinganda\n"
            "• Ish boshlanganda\n"
            "• Ish tugaganda\n"
            "• Baho berish vaqti kelganda"
        )
        return

    if text == "⚙️ Sozlamalar":
        await update.message.reply_text(
            "⚙️ <b>Sozlamalar</b>\n\n"
            "🌐 Til: O‘zbek\n"
            "🔔 Xabarlar: Yoqilgan",
            parse_mode=ParseMode.HTML,
        )
        return

    if text == "👨‍🔧 Usta bo‘lish":
        await master_register_start(update, context)
        return


# ---------------- REMINDERS ----------------

async def reminder_worker(app):
    while True:
        try:
            if pool:
                async with pool.acquire() as con:
                    rows = await con.fetch(
                        """
                        SELECT r.*,o.customer_name,o.status,o.id AS oid
                        FROM reminders r
                        JOIN orders o ON o.id=r.order_id
                        WHERE r.sent=FALSE
                          AND r.due_at <= NOW()
                        LIMIT 50
                        """
                    )

                    for r in rows:
                        text = None

                        if r["kind"] == "rating":
                            text = (
                                f"⭐ <b>Buyurtma #{r['oid']}</b>\n\n"
                                "Iltimos, xizmat sifatini baholang."
                            )
                        elif r["kind"] == "accepted":
                            text = (
                                f"🔔 <b>Buyurtma #{r['oid']}</b>\n\n"
                                "Buyurtmangiz qabul qilinganiga 2 soat bo‘ldi."
                            )
                        elif r["kind"] == "progress":
                            text = (
                                f"🔔 <b>Buyurtma #{r['oid']}</b>\n\n"
                                "Ish jarayonini tekshirish vaqti."
                            )

                        if text:
                            await safe_send(
                                app.bot,
                                r["user_id"],
                                text,
                                parse_mode=ParseMode.HTML,
                            )

                        await con.execute(
                            "UPDATE reminders SET sent=TRUE WHERE id=$1",
                            r["id"],
                        )

        except Exception:
            logger.exception("Reminder worker error")

        await asyncio.sleep(60)


async def create_reminder(order_id, user_id, kind, hours):
    if not pool:
        return

    async with pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO reminders(order_id,user_id,kind,due_at)
            VALUES($1,$2,$3,NOW()+($4 || ' hours')::interval)
            """,
            order_id,
            user_id,
            kind,
            str(hours),
        )


# ---------------- ERROR HANDLER ----------------

async def error_handler(update, context):
    logger.exception(
        "Unhandled exception",
        exc_info=context.error,
    )


# ---------------- POST INIT / SHUTDOWN ----------------

async def post_init(application):
    await db_init()

    application.create_task(
        reminder_worker(application)
    )

    logger.info("USTA 24 started")


async def post_shutdown(application):
    global pool

    if pool:
        await pool.close()
        pool = None

    logger.info("USTA 24 stopped")


# ---------------- MAIN ----------------

def build_application():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Client order conversation
    order_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^📝 Buyurtma berish$"),
                order_start,
            )
        ],
        states={
            C_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_name)
            ],
            C_PHONE: [
                MessageHandler(
                    (filters.CONTACT | filters.TEXT) & ~filters.COMMAND,
                    order_phone,
                )
            ],
            C_LOCATION: [
                MessageHandler(
                    (filters.LOCATION | filters.TEXT) & ~filters.COMMAND,
                    order_location,
                )
            ],
            C_SERVICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_service)
            ],
            C_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_address)
            ],
            C_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_comment)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", order_cancel),
            MessageHandler(
                filters.Regex(r"^❌ Bekor qilish$"),
                order_cancel,
            ),
        ],
        allow_reentry=True,
    )

    master_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^👨‍🔧 Usta bo‘lish$"),
                master_register_start,
            )
        ],
        states={
            M_PHONE: [
                MessageHandler(
                    (filters.CONTACT | filters.TEXT) & ~filters.COMMAND,
                    master_phone,
                )
            ],
            M_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, master_name)
            ],
            M_SERVICES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, master_services)
            ],
            M_WORKTIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, master_worktime)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", order_cancel),
        ],
        allow_reentry=True,
    )

    broadcast_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^📢 Xabarlar$"),
                admin_broadcast_start,
            )
        ],
        states={
            ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", order_cancel),
        ],
    )

    coupon_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r"^🎟 Kuponlar$"),
                admin_coupon_start,
            )
        ],
        states={
            ADMIN_COUPON_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_coupon_code)
            ],
            ADMIN_COUPON_DISCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_coupon_discount)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", order_cancel),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(order_conv)
    app.add_handler(master_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(coupon_conv)

    # General callback handlers
    app.add_handler(
        CallbackQueryHandler(
            admin_callbacks,
            pattern=r"^(admin:|approve:|deny:|adminassign:|assign:|price:)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callbacks,
            pattern=r"^(accept:|reject:|start:|complete:|cancel:|rating:)"
        )
    )

    # Status ID handler
    app.add_handler(
        MessageHandler(
            filters.Regex(r"^\d+$"),
            order_status_text,
        )
    )

    # General text router must be last
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router,
        )
    )

    app.add_error_handler(error_handler)

    return app


def main():
    app = build_application()
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
