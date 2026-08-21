# ============================================================
# USTA 24 ANDIJON
# MAIN.PY
# ============================================================

import os
import logging
import asyncpg

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
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


if DISPATCHER_ID_RAW:
    try:
        DISPATCHER_ID = int(DISPATCHER_ID_RAW)
    except ValueError:
        DISPATCHER_ID = None
else:
    DISPATCHER_ID = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("USTA24")


# ============================================================
# DATABASE
# ============================================================

db_pool = None


async def init_db():

    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
    )

    async with db_pool.acquire() as conn:

        # USERS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # MASTERS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                status TEXT DEFAULT 'active',
                rating NUMERIC(3,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ORDERS
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
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP
            )
        """)

        # HISTORY
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

        # REVIEWS
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

        # FAVORITES
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT,
                master_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(customer_id, master_id)
            )
        """)

        # REMINDERS
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

    logger.info("PostgreSQL tayyor!")


# ============================================================
# USER
# ============================================================

async def save_user(update: Update):

    user = update.effective_user

    if not user:
        return

    username = (
        f"@{user.username}"
        if user.username
        else None
    )

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO users (
                id,
                username,
                full_name
            )
            VALUES ($1, $2, $3)

            ON CONFLICT (id)
            DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            """,
            user.id,
            username,
            user.full_name,
        )


def is_admin(update: Update):

    return (
        update.effective_user
        and update.effective_user.id == ADMIN_ID
    )


# ============================================================
# CUSTOMER MENU
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


# ============================================================
# ADMIN MENU
# ============================================================

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


# ============================================================
# BASIC KEYBOARDS
# ============================================================

def cancel_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("❌ Bekor qilish")
            ]
        ],
        resize_keyboard=True,
    )


def phone_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    text="📱 Telefon raqamim",
                    request_contact=True,
                )
            ],
            [
                KeyboardButton("❌ Bekor qilish")
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
                    text="📍 Geolokatsiyani yuborish",
                    request_location=True,
                )
            ],
            [
                KeyboardButton("❌ Bekor qilish")
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
                KeyboardButton("❌ Bekor qilish")
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
                KeyboardButton("❌ Bekor qilish")
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await save_user(update)

    if is_admin(update):

        await update.message.reply_text(
            "🛠 USTA 24 ANDIJON\n\n"
            "👑 ADMIN PANEL\n\n"
            f"🆔 Sizning ID: {update.effective_user.id}",
            reply_markup=admin_menu(),
        )

    else:

        await update.message.reply_text(
            "🛠 USTA 24 ANDIJON\n\n"
            f"Assalomu alaykum, "
            f"{update.effective_user.first_name}! 👋\n\n"
            "Kerakli bo‘limni tanlang.",
            reply_markup=customer_menu(),
        )


# ============================================================
# ORDER STATES
# ============================================================

NAME = 1
PHONE = 2
LOCATION = 3
SERVICE = 4
ADDRESS = 5
DESCRIPTION = 6
CONFIRM = 7


# ============================================================
# ORDER START
# ============================================================

async def order_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    context.user_data["customer_id"] = (
        update.effective_user.id
    )

    await update.message.reply_text(
        "📝 YANGI BUYURTMA\n\n"
        "1️⃣ Ismingizni kiriting:",
        reply_markup=cancel_keyboard(),
    )

    return NAME


# ============================================================
# NAME
# ============================================================

async def get_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await cancel_order(update, context)

    if len(text) < 2:

        await update.message.reply_text(
            "❌ Ism juda qisqa.\n"
            "Ismingizni qayta kiriting:"
        )

        return NAME

    context.user_data["name"] = text

    await update.message.reply_text(
        "2️⃣ 📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard(),
    )

    return PHONE


# ============================================================
# PHONE
# ============================================================

async def get_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.message.contact:

        contact = update.message.contact

        if (
            contact.user_id
            and contact.user_id
            != update.effective_user.id
        ):

            await update.message.reply_text(
                "❌ O‘zingizning telefon "
                "raqamingizni yuboring."
            )

            return PHONE

        phone = contact.phone_number

    else:

        text = update.message.text.strip()

        if text == "❌ Bekor qilish":
            return await cancel_order(
                update,
                context,
            )

        phone = text

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "3️⃣ 📍 Geolokatsiyangizni yuboring.\n\n"
        "Pastdagi tugmani bosing:",
        reply_markup=location_keyboard(),
    )

    return LOCATION


# ============================================================
# LOCATION
# ============================================================

async def get_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    # Bekor qilish
    if (
        update.message.text
        and update.message.text
        == "❌ Bekor qilish"
    ):

        return await cancel_order(
            update,
            context,
        )

    # MUHIM: Telegram LOCATION
    if update.message.location:

        loc = update.message.location

        context.user_data["latitude"] = (
            float(loc.latitude)
        )

        context.user_data["longitude"] = (
            float(loc.longitude)
        )

        await update.message.reply_text(
            "✅ Geolokatsiya qabul qilindi.\n\n"
            "4️⃣ 🛠 Xizmat turini tanlang:",
            reply_markup=service_keyboard(),
        )

        return SERVICE

    # Agar location kelmasa
    await update.message.reply_text(
        "❌ Geolokatsiya kelmadi.\n\n"
        "📍 «Geolokatsiyani yuborish» "
        "tugmasini bosing.",
        reply_markup=location_keyboard(),
    )

    return LOCATION


# ============================================================
# SERVICE
# ============================================================

async def get_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await cancel_order(
            update,
            context,
        )

    services = {
        "🪑 Mebel",
        "🚚 Ko‘chirish",
        "🔧 Ta’mirlash",
        "🏠 Uy xizmati",
        "➕ Boshqa",
    }

    if text not in services:

        await update.message.reply_text(
            "🛠 Xizmatni tugmalardan tanlang.",
            reply_markup=service_keyboard(),
        )

        return SERVICE

    context.user_data["service"] = text

    await update.message.reply_text(
        "5️⃣ 📍 To‘liq manzilni kiriting:",
        reply_markup=cancel_keyboard(),
    )

    return ADDRESS


# ============================================================
# ADDRESS
# ============================================================

async def get_address(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await cancel_order(
            update,
            context,
        )

    if len(text) < 3:

        await update.message.reply_text(
            "❌ Manzilni to‘liq kiriting."
        )

        return ADDRESS

    context.user_data["address"] = text

    await update.message.reply_text(
        "6️⃣ 📝 Izoh yozing:\n\n"
        "Masalan:\n"
        "Shkaf yig‘ish kerak.",
        reply_markup=cancel_keyboard(),
    )

    return DESCRIPTION


# ============================================================
# DESCRIPTION
# ============================================================

async def get_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await cancel_order(
            update,
            context,
        )

    context.user_data["description"] = text

    d = context.user_data

    await update.message.reply_text(
        "📋 BUYURTMA MA'LUMOTLARI\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Ism: {d['name']}\n"
        f"📞 Telefon: {d['phone']}\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"📍 Manzil: {d['address']}\n"
        f"📝 Izoh: {d['description']}\n"
        "📍 Geolokatsiya: ✅\n\n"
        "Ma’lumotlar to‘g‘rimi?",
        reply_markup=confirm_keyboard(),
    )

    return CONFIRM


# ============================================================
# CONFIRM
# ============================================================

async def confirm_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":
        return await cancel_order(
            update,
            context,
        )

    if text == "✏️ O‘zgartirish":

        customer_id = update.effective_user.id

        context.user_data.clear()

        context.user_data["customer_id"] = (
            customer_id
        )

        await update.message.reply_text(
            "📝 Buyurtmani qaytadan boshlaymiz.\n\n"
            "1️⃣ Ismingizni kiriting:",
            reply_markup=cancel_keyboard(),
        )

        return NAME

    if text != "✅ Tasdiqlash":

        await update.message.reply_text(
            "Iltimos, tugmalardan tanlang.",
            reply_markup=confirm_keyboard(),
        )

        return CONFIRM

    d = context.user_data

    customer_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        async with conn.transaction():

            await conn.execute(
                """
                UPDATE users
                SET phone = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                d["phone"],
                customer_id,
            )

            order_id = await conn.fetchval(
                """
                INSERT INTO orders (
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
                VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,'new'
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
            )

            await conn.execute(
                """
                INSERT INTO order_history (
                    order_id,
                    user_id,
                    new_status,
                    note
                )
                VALUES (
                    $1,
                    $2,
                    'new',
                    'Buyurtma yaratildi'
                )
                """,
                order_id,
                customer_id,
            )

    # ========================================================
    # CUSTOMER
    # ========================================================

    await update.message.reply_text(
        "✅ BUYURTMA QABUL QILINDI!\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Buyurtma: #{order_id}\n"
        f"👤 Mijoz: {d['name']}\n"
        f"📞 Telefon: {d['phone']}\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"📍 Manzil: {d['address']}\n\n"
        "📌 Holat: 🟡 Yangi\n\n"
        "Buyurtmangiz ustalarga yuborildi.",
        reply_markup=customer_menu(),
    )

    # ========================================================
    # MASTERS GROUP
    # ========================================================

    try:

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

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=group_text,
        )

        # LOCATION
        await context.bot.send_location(
            chat_id=MASTERS_GROUP_ID,
            latitude=d["latitude"],
            longitude=d["longitude"],
        )

        logger.info(
            "Buyurtma #%s guruhga yuborildi.",
            order_id,
        )

    except Exception as e:

        logger.exception(
            "MASTERS_GROUP_ID ga yuborishda xato: %s",
            e,
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
# MY ORDERS
# ============================================================

async def my_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    customer_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                id,
                service,
                address,
                status,
                created_at
            FROM orders
            WHERE customer_id = $1
            ORDER BY id DESC
            LIMIT 30
            """,
            customer_id,
        )

    if not rows:

        await update.message.reply_text(
            "📋 Sizda hozircha buyurtmalar yo‘q.",
            reply_markup=customer_menu(),
        )

        return

    text = "📋 BUYURTMALARIM\n━━━━━━━━━━━━━━\n\n"

    status_map = {
        "new": "🟡 Yangi",
        "accepted": "🔵 Qabul qilingan",
        "started": "🟠 Ish jarayonida",
        "completed": "🟢 Tugallangan",
        "cancelled": "🔴 Bekor qilingan",
        "rejected": "❌ Rad etilgan",
    }

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['address']}\n"
            f"📌 {status_map.get(row['status'], row['status'])}\n"
            f"🕐 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=customer_menu(),
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

    async with db_pool.acquire() as conn:

        customers = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        masters = await conn.fetchval(
            "SELECT COUNT(*) FROM masters"
        )

        orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        today = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at::date = CURRENT_DATE
            """
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'completed'
            """
        )

    await update.message.reply_text(
        "📊 USTA 24 ANDIJON\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Mijozlar: {customers}\n"
        f"👨‍🔧 Ustalar: {masters}\n"
        f"📋 Buyurtmalar: {orders}\n"
        f"📅 Bugun: {today}\n"
        f"🟢 Tugallangan: {completed}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN ORDERS
# ============================================================

async def admin_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        new = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='new'
            """
        )

        accepted = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='accepted'
            """
        )

        started = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='started'
            """
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status='completed'
            """
        )

    await update.message.reply_text(
        "📋 BUYURTMALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Jami: {total}\n"
        f"🟡 Yangi: {new}\n"
        f"🔵 Qabul qilingan: {accepted}\n"
        f"🟠 Ish jarayonida: {started}\n"
        f"🟢 Tugallangan: {completed}",
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

    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

    await update.message.reply_text(
        "👤 MIJOZLAR\n\n"
        f"Jami mijozlar: {total}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN MASTERS
# ============================================================

async def admin_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):
        return

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                telegram_id,
                username,
                full_name,
                phone,
                status
            FROM masters
            ORDER BY id DESC
            """
        )

    if not rows:

        await update.message.reply_text(
            "👨‍🔧 Hozircha usta yo‘q.\n\n"
            "Usta qo‘shish funksiyasini keyingi "
            "bosqichda ulaymiz.",
            reply_markup=admin_menu(),
        )

        return

    text = "👨‍🔧 USTALAR\n━━━━━━━━━━━━━━\n\n"

    for row in rows:

        username = row["username"] or "username yo‘q"

        text += (
            f"👨‍🔧 {row['full_name']}\n"
            f"🔗 {username}\n"
            f"🆔 ID: {row['telegram_id']}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"📌 {row['status']}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
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

    async with db_pool.acquire() as conn:

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
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        )

        month = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
            """
        )

    await update.message.reply_text(
        "📑 HISOBOT\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📅 Bugun: {today}\n"
        f"📆 7 kun: {week}\n"
        f"🗓 30 kun: {month}",
        reply_markup=admin_menu(),
    )


# ============================================================
# TEXT HANDLER
# ============================================================

async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    text = update.message.text

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    if not is_admin(update):

        if text == "📋 Buyurtmalarim":

            await my_orders(
                update,
                context,
            )
            return

        if text == "🔄 Qayta buyurtma":

            await update.message.reply_text(
                "🔄 Qayta buyurtma funksiyasi "
                "keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )
            return

        if text == "👨‍🔧 Mening ustalarim":

            await update.message.reply_text(
                "👨‍🔧 Mening ustalarim\n\n"
                "Bu bo‘lim keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )
            return

        if text == "⭐ Reytingim":

            await update.message.reply_text(
                "⭐ Reytingim\n\n"
                "Hozircha reytingingiz mavjud emas.",
                reply_markup=customer_menu(),
            )
            return

        if text == "💬 Sharh qoldirish":

            await update.message.reply_text(
                "💬 Sharh qoldirish\n\n"
                "Tugallangan buyurtmadan keyin "
                "sharh qoldirish ulanadi.",
                reply_markup=customer_menu(),
            )
            return

        if text == "🔔 Eslatmalarim":

            await update.message.reply_text(
                "🔔 Eslatmalarim\n\n"
                "Reminder tizimi keyingi bosqichda ulanadi.",
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

        if text == "🔎 Buyurtma holati":

            await update.message.reply_text(
                "🔎 Buyurtma holati\n\n"
                "Buyurtma ID raqamini yuborish "
                "funksiyasi keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )
            return

        if text == "❌ Buyurtmani bekor qilish":

            await update.message.reply_text(
                "❌ Buyurtmani bekor qilish funksiyasi "
                "keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )
            return

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    if is_admin(update):

        if text == "👨‍🔧 Ustalar":

            await admin_masters(
                update,
                context,
            )
            return

        if text == "📋 Buyurtmalar":

            await admin_orders(
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

            await update.message.reply_text(
                "💵 NARXLAR\n\n"
                "🛠 Xizmat narxlari\n"
                "🎟 Chegirmalar\n\n"
                "Keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )
            return

        if text == "📢 Xabarlar":

            await update.message.reply_text(
                "📢 XABARLAR\n\n"
                "📢 Xabar tarqatish\n"
                "📝 Shablonlar\n"
                "🎁 Taklifnomalar\n\n"
                "Keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )
            return

        if text == "🎟 Kuponlar":

            await update.message.reply_text(
                "🎟 KUPONLAR\n\n"
                "➕ Yaratish\n"
                "✏️ Tahrirlash\n"
                "📊 Statistika\n\n"
                "Keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )
            return

        if text == "⚙️ Sozlamalar":

            await update.message.reply_text(
                "⚙️ SOZLAMALAR\n\n"
                f"👑 Admin ID: {ADMIN_ID}\n"
                f"👨‍🔧 Guruh ID: {MASTERS_GROUP_ID}\n"
                f"🎧 Dispatcher ID: "
                f"{DISPATCHER_ID or '-'}",
                reply_markup=admin_menu(),
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
            else customer_menu()
        ),
    )


# ============================================================
# ERROR
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
# POST INIT
# ============================================================

async def post_init(
    application: Application,
):

    await init_db()

    logger.info(
        "========================================"
    )

    logger.info(
        "USTA 24 ANDIJON ISHGA TUSHDI"
    )

    logger.info(
        "ADMIN_ID = %s",
        ADMIN_ID,
    )

    logger.info(
        "DISPATCHER_ID = %s",
        DISPATCHER_ID,
    )

    logger.info(
        "MASTERS_GROUP_ID = %s",
        MASTERS_GROUP_ID,
    )

    logger.info(
        "========================================"
    )


# ============================================================
# POST SHUTDOWN
# ============================================================

async def post_shutdown(
    application: Application,
):

    global db_pool

    if db_pool:

        await db_pool.close()

        logger.info(
            "PostgreSQL yopildi."
        )


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

    # ========================================================
    # ORDER CONVERSATION
    # ========================================================

    order_conversation = ConversationHandler(

        entry_points=[
            MessageHandler(
                filters.Regex(
                    r"^📝 Buyurtma berish$"
                ),
                order_start,
            )
        ],

        states={

            NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_name,
                )
            ],

            PHONE: [
                MessageHandler(
                    filters.CONTACT,
                    get_phone,
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_phone,
                ),
            ],

            # MUHIM:
            # LOCATION birinchi turadi
            # TEXT ikkinchi turadi
            LOCATION: [
                MessageHandler(
                    filters.LOCATION,
                    get_location,
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_location,
                ),
            ],

            SERVICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_service,
                )
            ],

            ADDRESS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_address,
                )
            ],

            DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    get_description,
                )
            ],

            CONFIRM: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    confirm_order,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            ),
            MessageHandler(
                filters.Regex(
                    r"^❌ Bekor qilish$"
                ),
                cancel_order,
            ),
        ],

        allow_reentry=True,
    )

    application.add_handler(
        order_conversation
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
    # TEXT
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Bot polling boshlanmoqda..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
