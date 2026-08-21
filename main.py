# ============================================================
# USTA 24 ANDIJON
# MAIN.PY
# PostgreSQL + Telegram Bot
# ============================================================

import os
import logging
from datetime import datetime

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

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

MASTERS_GROUP_ID_RAW = os.getenv("MASTERS_GROUP_ID")

if MASTERS_GROUP_ID_RAW:
    try:
        MASTERS_GROUP_ID = int(MASTERS_GROUP_ID_RAW)
    except ValueError:
        MASTERS_GROUP_ID = None
else:
    MASTERS_GROUP_ID = None


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger("USTA24")


# ============================================================
# DATABASE POOL
# ============================================================

db_pool = None


# ============================================================
# DATABASE INIT
# ============================================================

async def init_db():

    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=60,
    )

    async with db_pool.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

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
                status TEXT DEFAULT 'active',
                rating NUMERIC(3,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # SERVICES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
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
                created_at TIMESTAMP DEFAULT NOW(),
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP
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
        # ORDER HISTORY
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
        # FAVORITES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT,
                master_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(customer_id, master_id)
            )
        """)

        # ----------------------------------------------------
        # COUPONS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id BIGSERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                discount NUMERIC(10,2) DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # PAYMENTS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                customer_id BIGINT,
                amount NUMERIC(12,2),
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # DEFAULT SERVICES
        # ----------------------------------------------------

        services = [
            "🪑 Mebel",
            "🚚 Ko‘chirish",
            "🔧 Ta’mirlash",
            "🏠 Uy xizmati",
            "➕ Boshqa",
        ]

        for service in services:

            await conn.execute(
                """
                INSERT INTO services (name)
                VALUES ($1)
                ON CONFLICT (name) DO NOTHING
                """,
                service,
            )

    logger.info("PostgreSQL baza tayyor!")


# ============================================================
# USER FUNCTIONS
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


def get_user_id(update: Update):

    if not update.effective_user:
        return None

    return update.effective_user.id


def is_admin(update: Update):

    user_id = get_user_id(update)

    return user_id in ADMIN_IDS


# ============================================================
# STATUS TEXT
# ============================================================

def status_text(status):

    statuses = {
        "new": "🟡 Yangi",
        "accepted": "🔵 Qabul qilingan",
        "started": "🟠 Ish jarayonida",
        "completed": "🟢 Tugallangan",
        "cancelled": "🔴 Bekor qilingan",
        "rejected": "❌ Rad etilgan",
    }

    return statuses.get(status, status)


# ============================================================
# CUSTOMER MENU
# ============================================================

def customer_menu():

    keyboard = [

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
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


# ============================================================
# ADMIN MENU
# ============================================================

def admin_menu():

    keyboard = [

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
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


# ============================================================
# COMMON KEYBOARDS
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
                    "📱 Telefon raqamim",
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
                    "📍 Geolokatsiyani yuborish",
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

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await save_user(update)

    user = update.effective_user

    if is_admin(update):

        await update.message.reply_text(
            "🛠 USTA 24 ANDIJON\n\n"
            "👑 ADMIN PANEL\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 Telegram ID: {user.id}\n\n"
            "Kerakli bo‘limni tanlang.",
            reply_markup=admin_menu(),
        )

        return

    await update.message.reply_text(
        "🛠 USTA 24 ANDIJON\n\n"
        f"Assalomu alaykum, {user.first_name}! 👋\n\n"
        "Xizmatimizdan foydalanish uchun "
        "menyudan tanlang.",
        reply_markup=customer_menu(),
    )


# ============================================================
# ORDER STATES
# ============================================================

ORDER_NAME = 1
ORDER_PHONE = 2
ORDER_LOCATION = 3
ORDER_SERVICE = 4
ORDER_ADDRESS = 5
ORDER_DESCRIPTION = 6
ORDER_CONFIRM = 7


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

    return ORDER_NAME


# ============================================================
# ORDER NAME
# ============================================================

async def order_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    if len(text) < 2:

        await update.message.reply_text(
            "❌ Ism noto‘g‘ri.\n\n"
            "Ismingizni qayta kiriting:"
        )

        return ORDER_NAME

    context.user_data["name"] = text

    await update.message.reply_text(
        "2️⃣ 📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_keyboard(),
    )

    return ORDER_PHONE


# ============================================================
# ORDER PHONE
# ============================================================

async def order_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    if update.message.contact:

        contact = update.message.contact

        if (
            contact.user_id
            and contact.user_id != user.id
        ):

            await update.message.reply_text(
                "❌ O‘zingizning telefon "
                "raqamingizni yuboring."
            )

            return ORDER_PHONE

        phone = contact.phone_number

    else:

        phone = update.message.text.strip()

        if phone == "❌ Bekor qilish":

            return await cancel_order(
                update,
                context,
            )

        if len(phone) < 7:

            await update.message.reply_text(
                "❌ Telefon raqami noto‘g‘ri."
            )

            return ORDER_PHONE

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "3️⃣ 📍 Geolokatsiyangizni yuboring:",
        reply_markup=location_keyboard(),
    )

    return ORDER_LOCATION


# ============================================================
# ORDER LOCATION
# ============================================================

async def order_location(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message.location:

        if (
            update.message.text
            == "❌ Bekor qilish"
        ):

            return await cancel_order(
                update,
                context,
            )

        await update.message.reply_text(
            "❌ Geolokatsiya kelmadi.\n\n"
            "📍 Geolokatsiyani yuborish "
            "tugmasini bosing."
        )

        return ORDER_LOCATION

    location = update.message.location

    context.user_data["latitude"] = (
        location.latitude
    )

    context.user_data["longitude"] = (
        location.longitude
    )

    await update.message.reply_text(
        "4️⃣ 🛠 Xizmat turini tanlang:",
        reply_markup=service_keyboard(),
    )

    return ORDER_SERVICE


# ============================================================
# ORDER SERVICE
# ============================================================

async def order_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    allowed_services = {
        "🪑 Mebel",
        "🚚 Ko‘chirish",
        "🔧 Ta’mirlash",
        "🏠 Uy xizmati",
        "➕ Boshqa",
    }

    if text not in allowed_services:

        await update.message.reply_text(
            "🛠 Xizmatni tugmalardan tanlang.",
            reply_markup=service_keyboard(),
        )

        return ORDER_SERVICE

    context.user_data["service"] = text

    await update.message.reply_text(
        "5️⃣ 📍 To‘liq manzilni kiriting:",
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

        return ORDER_ADDRESS

    context.user_data["address"] = text

    await update.message.reply_text(
        "6️⃣ 📝 Izoh yozing:\n\n"
        "Masalan:\n"
        "Shkaf yig‘ish kerak.\n"
        "Yoki: Oshxona mebelini o‘rnatish.",
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

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":

        return await cancel_order(
            update,
            context,
        )

    context.user_data["description"] = text

    data = context.user_data

    summary = (
        "📋 BUYURTMA MA'LUMOTLARI\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Ism: {data['name']}\n"
        f"📞 Telefon: {data['phone']}\n"
        f"🛠 Xizmat: {data['service']}\n"
        f"📍 Manzil: {data['address']}\n"
        f"📝 Izoh: {data['description']}\n"
        "📍 Geolokatsiya: ✅\n\n"
        "Ma’lumotlar to‘g‘rimi?"
    )

    await update.message.reply_text(
        summary,
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
            "📝 Buyurtmani qaytadan to‘ldiramiz.\n\n"
            "1️⃣ Ismingizni kiriting:",
            reply_markup=cancel_keyboard(),
        )

        return ORDER_NAME

    if text != "✅ Tasdiqlash":

        await update.message.reply_text(
            "Iltimos, tugmalardan tanlang.",
            reply_markup=confirm_keyboard(),
        )

        return ORDER_CONFIRM

    data = context.user_data

    customer_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        async with conn.transaction():

            # ------------------------------------------------
            # USER PHONE
            # ------------------------------------------------

            await conn.execute(
                """
                UPDATE users
                SET phone = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                data["phone"],
                customer_id,
            )

            # ------------------------------------------------
            # CREATE ORDER
            # ------------------------------------------------

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
                    $1,
                    $2,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8,
                    'new'
                )
                RETURNING id
                """,
                customer_id,
                data["name"],
                data["phone"],
                data["latitude"],
                data["longitude"],
                data["service"],
                data["address"],
                data["description"],
            )

            # ------------------------------------------------
            # HISTORY
            # ------------------------------------------------

            await conn.execute(
                """
                INSERT INTO order_history (
                    order_id,
                    user_id,
                    old_status,
                    new_status,
                    note
                )
                VALUES (
                    $1,
                    $2,
                    NULL,
                    'new',
                    'Buyurtma yaratildi'
                )
                """,
                order_id,
                customer_id,
            )

    # --------------------------------------------------------
    # CUSTOMER RESPONSE
    # --------------------------------------------------------

    await update.message.reply_text(
        "✅ BUYURTMA QABUL QILINDI!\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Buyurtma №{order_id}\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}\n"
        f"🛠 {data['service']}\n"
        f"📍 {data['address']}\n\n"
        "📌 Holat: 🟡 Yangi\n\n"
        "Buyurtmangiz tez orada ko‘rib chiqiladi.",
        reply_markup=customer_menu(),
    )

    # --------------------------------------------------------
    # SEND TO MASTERS GROUP
    # --------------------------------------------------------

    if MASTERS_GROUP_ID:

        try:

            master_text = (
                "🆕 YANGI BUYURTMA\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"🔢 Buyurtma: #{order_id}\n"
                f"👤 Mijoz: {data['name']}\n"
                f"📞 Telefon: {data['phone']}\n"
                f"🛠 Xizmat: {data['service']}\n"
                f"📍 Manzil: {data['address']}\n"
                f"📝 Izoh: {data['description']}\n"
                "📌 Holat: 🟡 Yangi\n"
            )

            await context.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=master_text,
            )

            if (
                data.get("latitude") is not None
                and data.get("longitude") is not None
            ):

                await context.bot.send_location(
                    chat_id=MASTERS_GROUP_ID,
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                )

            logger.info(
                "Order #%s groupga yuborildi.",
                order_id,
            )

        except Exception as e:

            logger.error(
                "Masters groupga yuborishda xato: %s",
                e,
            )

    else:

        logger.warning(
            "MASTERS_GROUP_ID mavjud emas."
        )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# CANCEL ORDER
# ============================================================

async def cancel_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ BUYURTMA BEKOR QILINDI.",
        reply_markup=customer_menu(),
    )

    return ConversationHandler.END


# ============================================================
# MY ORDERS
# ============================================================

async def show_my_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    customer_id = get_user_id(update)

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
            "📋 BUYURTMALARIM\n\n"
            "Sizda hozircha buyurtmalar yo‘q.",
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
            f"📌 {status_text(row['status'])}\n"
            f"🕐 {row['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            "──────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=customer_menu(),
    )


# ============================================================
# CHECK ORDER BY ID
# ============================================================

async def ask_order_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data["waiting_order_id"] = True

    await update.message.reply_text(
        "🔎 BUYURTMA HOLATI\n\n"
        "Buyurtma ID raqamini yuboring.\n\n"
        "Masalan:\n"
        "25",
        reply_markup=cancel_keyboard(),
    )


async def check_order_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get(
        "waiting_order_id"
    ):
        return False

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":

        context.user_data.pop(
            "waiting_order_id",
            None,
        )

        await update.message.reply_text(
            "❌ Bekor qilindi.",
            reply_markup=customer_menu(),
        )

        return True

    if not text.isdigit():

        await update.message.reply_text(
            "❌ Buyurtma ID faqat raqam bo‘lishi kerak.\n\n"
            "Masalan: 25"
        )

        return True

    order_id = int(text)

    customer_id = get_user_id(update)

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT
                id,
                service,
                address,
                description,
                status,
                created_at
            FROM orders
            WHERE id = $1
              AND customer_id = $2
            """,
            order_id,
            customer_id,
        )

    context.user_data.pop(
        "waiting_order_id",
        None,
    )

    if not row:

        await update.message.reply_text(
            "❌ Бундай буюртма топилмади.",
            reply_markup=customer_menu(),
        )

        return True

    await update.message.reply_text(
        "🔎 BUYURTMA HOLATI\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 #{row['id']}\n"
        f"🛠 Xizmat: {row['service']}\n"
        f"📍 Manzil: {row['address']}\n"
        f"📝 Izoh: {row['description']}\n"
        f"📌 Holat: {status_text(row['status'])}\n"
        f"🕐 Sana: "
        f"{row['created_at'].strftime('%d.%m.%Y %H:%M')}",
        reply_markup=customer_menu(),
    )

    return True


# ============================================================
# CANCEL EXISTING ORDER
# ============================================================

async def ask_cancel_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data["waiting_cancel_order"] = True

    await update.message.reply_text(
        "❌ BUYURTMANI BEKOR QILISH\n\n"
        "Bekor qilmoqchi bo‘lgan buyurtma "
        "ID raqamini yuboring.\n\n"
        "Masalan: 25",
        reply_markup=cancel_keyboard(),
    )


async def cancel_existing_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get(
        "waiting_cancel_order"
    ):
        return False

    text = update.message.text.strip()

    if text == "❌ Bekor qilish":

        context.user_data.pop(
            "waiting_cancel_order",
            None,
        )

        await update.message.reply_text(
            "❌ Bekor qilindi.",
            reply_markup=customer_menu(),
        )

        return True

    if not text.isdigit():

        await update.message.reply_text(
            "❌ ID raqam bo‘lishi kerak."
        )

        return True

    order_id = int(text)
    customer_id = get_user_id(update)

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT
                id,
                status
            FROM orders
            WHERE id = $1
              AND customer_id = $2
            """,
            order_id,
            customer_id,
        )

        if not row:

            context.user_data.pop(
                "waiting_cancel_order",
                None,
            )

            await update.message.reply_text(
                "❌ Buyurtma topilmadi.",
                reply_markup=customer_menu(),
            )

            return True

        if row["status"] in (
            "completed",
            "cancelled",
        ):

            context.user_data.pop(
                "waiting_cancel_order",
                None,
            )

            await update.message.reply_text(
                "❌ Bu buyurtmani bekor qilib bo‘lmaydi.",
                reply_markup=customer_menu(),
            )

            return True

        await conn.execute(
            """
            UPDATE orders
            SET status = 'cancelled',
                cancelled_at = NOW()
            WHERE id = $1
            """,
            order_id,
        )

        await conn.execute(
            """
            INSERT INTO order_history (
                order_id,
                user_id,
                old_status,
                new_status,
                note
            )
            VALUES (
                $1,
                $2,
                $3,
                'cancelled',
                'Mijoz bekor qildi'
            )
            """,
            order_id,
            customer_id,
            row["status"],
        )

    context.user_data.pop(
        "waiting_cancel_order",
        None,
    )

    await update.message.reply_text(
        f"✅ Buyurtma #{order_id} bekor qilindi.",
        reply_markup=customer_menu(),
    )

    return True


# ============================================================
# ADMIN ORDERS
# ============================================================

async def admin_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):

        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )

        return

    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        new_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'new'
            """
        )

        accepted = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'accepted'
            """
        )

        started = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'started'
            """
        )

        completed = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'completed'
            """
        )

        cancelled = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'cancelled'
            """
        )

    await update.message.reply_text(
        "📋 BUYURTMALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 Jami: {total}\n"
        f"🟡 Yangi: {new_count}\n"
        f"🔵 Qabul qilingan: {accepted}\n"
        f"🟠 Ish jarayonida: {started}\n"
        f"🟢 Tugallangan: {completed}\n"
        f"🔴 Bekor qilingan: {cancelled}",
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

        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )

        return

    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        active = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT customer_id)
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
            """
        )

    await update.message.reply_text(
        "👤 MIJOZLAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Jami mijozlar: {total}\n"
        f"🔥 Faol mijozlar: {active}",
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

        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )

        return

    async with db_pool.acquire() as conn:

        customers = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        masters = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM masters
            WHERE status = 'active'
            """
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
        f"📋 Jami buyurtmalar: {orders}\n"
        f"📅 Bugun: {today}\n"
        f"📆 7 kun: {week}\n"
        f"🗓 30 kun: {month}\n"
        f"🟢 Tugallangan: {completed}",
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

        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )

        return

    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM masters"
        )

        active = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM masters
            WHERE status = 'active'
            """
        )

    await update.message.reply_text(
        "👨‍🔧 USTALAR\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👨‍🔧 Jami: {total}\n"
        f"🟢 Faol: {active}\n\n"
        "➕ Usta qo‘shish — keyingi bosqich\n"
        "🗑 Usta o‘chirish — keyingi bosqich\n"
        "🔗 Ustaga biriktirish — keyingi bosqich\n"
        "🔄 Boshqa ustaga berish — keyingi bosqich",
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

        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )

        return

    async with db_pool.acquire() as conn:

        today = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE created_at::date = CURRENT_DATE
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
        f"📆 Hafta: {week}\n"
        f"🗓 Oy: {month}\n\n"
        "📤 CSV/Excel eksport keyingi bosqichda ulanadi.",
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

    text = update.message.text.strip()

    # ========================================================
    # ACTIVE ID INPUTS
    # ========================================================

    if await check_order_id(
        update,
        context,
    ):
        return

    if await cancel_existing_order(
        update,
        context,
    ):
        return

    # ========================================================
    # CUSTOMER
    # ========================================================

    if not is_admin(update):

        if text == "📝 Buyurtma berish":
            return await order_start(
                update,
                context,
            )

        if text == "📋 Buyurtmalarim":
            return await show_my_orders(
                update,
                context,
            )

        if text == "🔎 Buyurtma holati":
            return await ask_order_status(
                update,
                context,
            )

        if text == "❌ Buyurtmani bekor qilish":
            return await ask_cancel_order(
                update,
                context,
            )

        if text == "🔄 Qayta buyurtma":

            await update.message.reply_text(
                "🔄 QAYTA BUYURTMA\n\n"
                "Bu funksiya keyingi bosqichda "
                "oldingi buyurtmadan avtomatik "
                "yaratiladi.",
                reply_markup=customer_menu(),
            )

            return

        if text == "👨‍🔧 Mening ustalarim":

            await update.message.reply_text(
                "👨‍🔧 MENING USTALARIM\n\n"
                "⭐ Ishlatgan ustalarim\n"
                "❤️ Sevimli ustalarim\n\n"
                "Bu bo‘lim keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )

            return

        if text == "⭐ Reytingim":

            await update.message.reply_text(
                "⭐ REYTINGIM\n\n"
                "Reyting tizimi keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )

            return

        if text == "💬 Sharh qoldirish":

            await update.message.reply_text(
                "💬 SHARH QOLDIRISH\n\n"
                "Tugallangan buyurtma uchun sharh "
                "qoldirish keyingi bosqichda ulanadi.",
                reply_markup=customer_menu(),
            )

            return

        if text == "🔔 Eslatmalarim":

            await update.message.reply_text(
                "🔔 ESLATMALARIM\n\n"
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

    # ========================================================
    # ADMIN
    # ========================================================

    if is_admin(update):

        if text == "👨‍🔧 Ustalar":
            return await admin_masters(
                update,
                context,
            )

        if text == "📋 Buyurtmalar":
            return await admin_orders(
                update,
                context,
            )

        if text == "👤 Mijozlar":
            return await admin_customers(
                update,
                context,
            )

        if text == "📊 Statistika":
            return await admin_statistics(
                update,
                context,
            )

        if text == "📑 Hisobot":
            return await admin_report(
                update,
                context,
            )

        if text == "💵 Narxlar":

            await update.message.reply_text(
                "💵 NARXLAR\n\n"
                "🛠 Xizmat narxlari\n"
                "🎟 Chegirmalar\n\n"
                "Bu bo‘lim keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )

            return

        if text == "📢 Xabarlar":

            await update.message.reply_text(
                "📢 XABARLAR\n\n"
                "📢 Xabar tarqatish\n"
                "📝 Shablonlar\n"
                "🎁 Taklifnomalar\n\n"
                "Bu bo‘lim keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )

            return

        if text == "🎟 Kuponlar":

            await update.message.reply_text(
                "🎟 KUPONLAR\n\n"
                "➕ Yaratish\n"
                "✏️ Tahrirlash\n"
                "📊 Statistika\n\n"
                "Bu bo‘lim keyingi bosqichda ulanadi.",
                reply_markup=admin_menu(),
            )

            return

        if text == "⚙️ Sozlamalar":

            await update.message.reply_text(
                "⚙️ SOZLAMALAR\n\n"
                "🆔 Guruh ID\n"
                "👑 Admin ID\n"
                "🔔 Eslatma vaqtlari",
                reply_markup=admin_menu(),
            )

            return

    # ========================================================
    # DEFAULT
    # ========================================================

    await update.message.reply_text(
        "🛠 USTA 24 ANDIJON\n\n"
        "Kerakli bo‘limni menyudan tanlang.",
        reply_markup=(
            admin_menu()
            if is_admin(update)
            else customer_menu()
        ),
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "BOT ERROR: %s",
        context.error,
        exc_info=context.error,
    )


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application: Application,
):

    await init_db()

    logger.info(
        "USTA 24 ANDIJON: PostgreSQL ulandi."
    )

    if MASTERS_GROUP_ID:
        logger.info(
            "MASTERS_GROUP_ID: %s",
            MASTERS_GROUP_ID,
        )
    else:
        logger.warning(
            "MASTERS_GROUP_ID mavjud emas."
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
            "PostgreSQL connection yopildi."
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

            ORDER_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_name,
                )
            ],

            ORDER_PHONE: [
                MessageHandler(
                    filters.CONTACT,
                    order_phone,
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_phone,
                ),
            ],

            ORDER_LOCATION: [
                MessageHandler(
                    filters.LOCATION,
                    order_location,
                ),
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_location,
                ),
            ],

            ORDER_SERVICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_service,
                )
            ],

            ORDER_ADDRESS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_address,
                )
            ],

            ORDER_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    order_description,
                )
            ],

            ORDER_CONFIRM: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
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
            start_command,
        )
    )

    # ========================================================
    # GENERAL TEXT
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
        "🛠 USTA 24 ANDIJON ishga tushmoqda..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
