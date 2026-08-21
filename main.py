# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# 1 BOT = CLIENT + MASTER + ADMIN + DISPATCHER
# + MASTERS GROUP
#
# Python 3.11+
# python-telegram-bot 22.3
# PostgreSQL / asyncpg
#
# ENV:
# BOT_TOKEN
# DATABASE_URL
# ADMIN_ID
# DISPATCHER_ID
# MASTERS_GROUP_ID
#
# OTP YO'Q
# ONLINE PAYMENT YO'Q
# FAQAT NAQD + ISHDAN KEYIN
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
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")

db_pool = None

# ============================================================
# STATES
# ============================================================

(
    C_NAME,
    C_PHONE,
    C_LOCATION,
    C_SERVICE,
    C_PHOTO,
    C_ADDRESS,
    C_TIME,
    C_COMMENT,
    C_CONFIRM,

    EMERGENCY_TYPE,
    EMERGENCY_TIME,

    MASTER_NAME,
    MASTER_PHONE,
    MASTER_SERVICE,
    MASTER_AREA,

    FINISH_PHOTO,

    RATING,
    REVIEW,
) = range(18)


# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "⚡ Elektr",
    "💧 Santexnika",
    "🔥 Gaz",
    "🚪 Eshik",
    "🪑 Mebel",
    "🛠 Mebel yig'ish",
    "🚚 Ko'chirish",
    "🧱 Qurilish / ta'mirlash",
    "🎨 Bo'yash",
    "❄️ Konditsioner",
    "🔧 Boshqa xizmat",
]


# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL topilmadi. Railway Variables ichiga DATABASE_URL qo'ying."
        )

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=60,
    )

    async with db_pool.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Missing columns auto-create
        user_columns = {
            "first_name": "TEXT",
            "last_name": "TEXT",
            "username": "TEXT",
            "phone": "TEXT",
            "role": "TEXT DEFAULT 'client'",
            "is_active": "BOOLEAN DEFAULT TRUE",
            "created_at": "TIMESTAMP DEFAULT NOW()",
        }

        for column, dtype in user_columns.items():
            await conn.execute(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {dtype}"
            )

        # ----------------------------------------------------
        # MASTERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                name TEXT,
                phone TEXT,
                service TEXT,
                area TEXT,
                status TEXT DEFAULT 'pending',
                rating NUMERIC(3,2) DEFAULT 5.00,
                rating_count INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        master_columns = {
            "name": "TEXT",
            "phone": "TEXT",
            "service": "TEXT",
            "area": "TEXT",
            "status": "TEXT DEFAULT 'pending'",
            "rating": "NUMERIC(3,2) DEFAULT 5.00",
            "rating_count": "INTEGER DEFAULT 0",
            "total_orders": "INTEGER DEFAULT 0",
            "completed_orders": "INTEGER DEFAULT 0",
            "created_at": "TIMESTAMP DEFAULT NOW()",
        }

        for column, dtype in master_columns.items():
            await conn.execute(
                f"ALTER TABLE masters ADD COLUMN IF NOT EXISTS {column} {dtype}"
            )

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,

                customer_id BIGINT,
                customer_name TEXT,
                phone TEXT,

                service TEXT,
                address TEXT,
                comment TEXT,

                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,

                problem_photo_ids TEXT,

                requested_time TEXT,

                emergency BOOLEAN DEFAULT FALSE,
                emergency_level TEXT,
                emergency_markup INTEGER DEFAULT 0,

                status TEXT DEFAULT 'new',

                master_id BIGINT,
                master_name TEXT,

                result_photo_ids TEXT,

                final_price NUMERIC(12,2) DEFAULT 0,

                payment_method TEXT DEFAULT 'cash',
                payment_status TEXT DEFAULT 'unpaid',

                started_at TIMESTAMP,
                completed_at TIMESTAMP,

                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        order_columns = {
            "customer_id": "BIGINT",
            "customer_name": "TEXT",
            "phone": "TEXT",
            "service": "TEXT",
            "address": "TEXT",
            "comment": "TEXT",
            "latitude": "DOUBLE PRECISION",
            "longitude": "DOUBLE PRECISION",
            "problem_photo_ids": "TEXT",
            "requested_time": "TEXT",
            "emergency": "BOOLEAN DEFAULT FALSE",
            "emergency_level": "TEXT",
            "emergency_markup": "INTEGER DEFAULT 0",
            "status": "TEXT DEFAULT 'new'",
            "master_id": "BIGINT",
            "master_name": "TEXT",
            "result_photo_ids": "TEXT",
            "final_price": "NUMERIC(12,2) DEFAULT 0",
            "payment_method": "TEXT DEFAULT 'cash'",
            "payment_status": "TEXT DEFAULT 'unpaid'",
            "started_at": "TIMESTAMP",
            "completed_at": "TIMESTAMP",
            "created_at": "TIMESTAMP DEFAULT NOW()",
        }

        for column, dtype in order_columns.items():
            await conn.execute(
                f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {column} {dtype}"
            )

        # ----------------------------------------------------
        # RATINGS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                customer_id BIGINT,
                master_id BIGINT,
                rating INTEGER,
                review TEXT,
                created_at TIMESTAMP DEFAULT NOW()
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
                review TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # NOTIFICATIONS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                text TEXT,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

    logger.info("DATABASE READY")


# ============================================================
# DATABASE HELPERS
# ============================================================

async def db_execute(query, *args):
    async with db_pool.acquire() as conn:
        return await conn.execute(query, *args)


async def db_fetchrow(query, *args):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def db_fetch(query, *args):
    async with db_pool.acquire() as conn:
        return await conn.fetch(query, *args)


# ============================================================
# USER
# ============================================================

async def save_user(user):
    if not user:
        return

    role = "client"

    if user.id == ADMIN_ID:
        role = "admin"
    elif user.id == DISPATCHER_ID:
        role = "dispatcher"
    else:
        master = await db_fetchrow(
            "SELECT status FROM masters WHERE telegram_id=$1",
            user.id,
        )

        if master and master["status"] == "approved":
            role = "master"

    await db_execute("""
        INSERT INTO users
        (
            id,
            first_name,
            last_name,
            username,
            role,
            is_active
        )
        VALUES ($1,$2,$3,$4,$5,TRUE)

        ON CONFLICT (id)
        DO UPDATE SET
            first_name=EXCLUDED.first_name,
            last_name=EXCLUDED.last_name,
            username=EXCLUDED.username,
            role=EXCLUDED.role
    """,
        user.id,
        user.first_name or "",
        user.last_name or "",
        user.username or "",
        role,
    )


async def get_user_role(user_id):
    if user_id == ADMIN_ID:
        return "admin"

    if user_id == DISPATCHER_ID:
        return "dispatcher"

    master = await db_fetchrow(
        "SELECT status FROM masters WHERE telegram_id=$1",
        user_id,
    )

    if master and master["status"] == "approved":
        return "master"

    return "client"


# ============================================================
# KEYBOARDS
# ============================================================

def client_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🛒 Buyurtma berish"),
                KeyboardButton("📋 Mening buyurtmalarim"),
            ],
            [
                KeyboardButton("🔍 Buyurtma holati"),
                KeyboardButton("❌ Bekor qilish"),
            ],
            [
                KeyboardButton("🔁 Qayta buyurtma"),
                KeyboardButton("👨‍🔧 Mening ustalarim"),
            ],
            [
                KeyboardButton("⭐ Reytingim"),
                KeyboardButton("📝 Sharh qoldirish"),
            ],
            [
                KeyboardButton("📌 Eslatmalarim"),
                KeyboardButton("🗺️ Yaqin atrofdagi ustalar"),
            ],
            [
                KeyboardButton("📅 Yozilma (bron)"),
                KeyboardButton("🎁 Loyallik va bonuslar"),
            ],
            [
                KeyboardButton("🤖 AI yordamchi"),
                KeyboardButton("⚙️ Sozlamalar"),
            ],
            [
                KeyboardButton("📊 Mening statistika"),
                KeyboardButton("🏷️ Chegirmalar va aksiyalar"),
            ],
            [
                KeyboardButton("📞 Tez yordam"),
                KeyboardButton("🔔 Bildirishnomalar"),
            ],
            [
                KeyboardButton("📁 Mening hujjatlarim"),
                KeyboardButton("🕊️ Do'stga tavsiya qilish"),
            ],
            [
                KeyboardButton("📞 Dispetcherga qo'ng'iroq"),
                KeyboardButton("🚨 24/7 Shosilinch rejim"),
            ],
            [
                KeyboardButton("🚪 Chiqish"),
            ],
        ],
        resize_keyboard=True,
    )


def master_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📋 Yangi buyurtmalar"),
                KeyboardButton("✅ Mening faol buyurtmalarim"),
            ],
            [
                KeyboardButton("⏳ Tarix"),
                KeyboardButton("💰 Ish haqi va hisobot"),
            ],
            [
                KeyboardButton("⭐ Reytingim va sharhlar"),
                KeyboardButton("📅 Kunlik ish jadvalim"),
            ],
            [
                KeyboardButton("🔔 Mijozlar bilan bog'lanish"),
                KeyboardButton("📸 Galereya"),
            ],
            [
                KeyboardButton("🛠 Xizmatlarni boshqarish"),
                KeyboardButton("📊 Ish statistikasi"),
            ],
            [
                KeyboardButton("🏷️ Mening narxlarim"),
                KeyboardButton("📍 Ish hududim"),
            ],
            [
                KeyboardButton("📅 Dam olish kunlari"),
                KeyboardButton("🔔 Bildirishnoma sozlamalari"),
            ],
            [
                KeyboardButton("📝 Reytingni oshirish maslahatlar"),
                KeyboardButton("🎁 Usta bonuslari"),
            ],
            [
                KeyboardButton("🤖 AI yordamchi"),
                KeyboardButton("📞 Texnik yordam"),
            ],
            [
                KeyboardButton("📢 E'lonlar va yangiliklar"),
                KeyboardButton("🏆 Ustalar reytingi"),
            ],
            [
                KeyboardButton("📞 Dispetcherga qo'ng'iroq"),
                KeyboardButton("🚨 24/7 Shosilinch rejim"),
            ],
            [
                KeyboardButton("🚪 Chiqish"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("👥 Foydalanuvchilar"),
                KeyboardButton("🛠 Buyurtmalar"),
            ],
            [
                KeyboardButton("👨‍🔧 Ustalar"),
                KeyboardButton("⭐ Reyting va sharhlar"),
            ],
            [
                KeyboardButton("🎁 Loyallik va bonuslar"),
                KeyboardButton("💰 To'lovlar"),
            ],
            [
                KeyboardButton("🏷️ Chegirmalar va aksiyalar"),
                KeyboardButton("🛠 Xizmat turlari"),
            ],
            [
                KeyboardButton("📊 Statistika va hisobot"),
                KeyboardButton("📢 E'lonlar va yangiliklar"),
            ],
            [
                KeyboardButton("📞 Dispetcher"),
                KeyboardButton("⚙️ Sozlamalar"),
            ],
            [
                KeyboardButton("📸 Rasm galereyasi"),
                KeyboardButton("📱 Botni boshqarish"),
            ],
            [
                KeyboardButton("📞 Qo'llab-quvvatlash"),
                KeyboardButton("🚨 24/7 Shosilinch rejim"),
            ],
            [
                KeyboardButton("🚪 Chiqish"),
            ],
        ],
        resize_keyboard=True,
    )


def dispatcher_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📋 Yangi buyurtmalar"),
                KeyboardButton("🔧 Faol buyurtmalar"),
            ],
            [
                KeyboardButton("👨‍🔧 Ustalar"),
                KeyboardButton("👥 Foydalanuvchilar"),
            ],
            [
                KeyboardButton("📊 Statistika"),
                KeyboardButton("🚨 Shoshilinch"),
            ],
            [
                KeyboardButton("📞 Mijoz bilan bog'lanish"),
                KeyboardButton("📞 Usta bilan bog'lanish"),
            ],
            [
                KeyboardButton("🚪 Chiqish"),
            ],
        ],
        resize_keyboard=True,
    )


def service_keyboard():

    rows = []

    for i in range(0, len(SERVICES), 2):
        row = [KeyboardButton(SERVICES[i])]

        if i + 1 < len(SERVICES):
            row.append(KeyboardButton(SERVICES[i + 1]))

        rows.append(row)

    rows.append([KeyboardButton("❌ Bekor qilish")])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
    )


def time_keyboard():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🕐 Hozir"),
                KeyboardButton("🕐 30 daqiqada"),
            ],
            [
                KeyboardButton("🕐 1 soatda"),
                KeyboardButton("🕐 Keyinroq"),
            ],
            [
                KeyboardButton("❌ Bekor qilish"),
            ],
        ],
        resize_keyboard=True,
    )


# ============================================================
# /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    await save_user(user)

    role = await get_user_role(user.id)

    if role == "admin":

        await update.message.reply_text(
            "👨‍💼 <b>USTA 24 ANDIJON — ADMIN</b>\n\n"
            "Тизим бошқарув панелига хуш келибсиз.",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
        return

    if role == "dispatcher":

        await update.message.reply_text(
            "📞 <b>USTA 24 — DISPETCHER</b>\n\n"
            "24/7 диспетчерлик панели.",
            parse_mode="HTML",
            reply_markup=dispatcher_keyboard(),
        )
        return

    if role == "master":

        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 — USTA</b>\n\n"
            "Хуш келибсиз, уста!",
            parse_mode="HTML",
            reply_markup=master_keyboard(),
        )
        return

    await update.message.reply_text(
        "👋 <b>USTA 24 ANDIJON</b>\n\n"
        "Уйингизга ишончли уста чақиринг!\n\n"
        "🛠 Электр\n"
        "💧 Сантехника\n"
        "🔥 Газ\n"
        "🚪 Эшик\n"
        "🪑 Мебель\n"
        "🚚 Кўчириш\n"
        "ва бошқа хизматлар.",
        parse_mode="HTML",
        reply_markup=client_keyboard(),
    )


# ============================================================
# CLIENT ORDER START
# ============================================================

async def order_start(update, context):

    context.user_data.clear()

    context.user_data["order"] = {}

    await update.message.reply_text(
        "🛒 <b>ЯНГИ БУЮРТМА</b>\n\n"
        "1️⃣ Исмингизни ёзинг:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Bekor qilish")]],
            resize_keyboard=True,
        ),
    )

    return C_NAME


# ============================================================
# CLIENT NAME
# ============================================================

async def order_name(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    context.user_data["order"]["customer_name"] = update.message.text.strip()

    await update.message.reply_text(
        "📞 Телефон рақамингизни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📱 Telefon raqamni yuborish",
                        request_contact=True,
                    )
                ],
                [KeyboardButton("❌ Bekor qilish")],
            ],
            resize_keyboard=True,
        ),
    )

    return C_PHONE


# ============================================================
# PHONE
# ============================================================

async def order_phone(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    phone = None

    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()

    context.user_data["order"]["phone"] = phone

    await update.message.reply_text(
        "📍 Геолокациянгизни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📍 Геолокацияни юбориш",
                        request_location=True,
                    )
                ],
                [KeyboardButton("❌ Bekor qilish")],
            ],
            resize_keyboard=True,
        ),
    )

    return C_LOCATION


# ============================================================
# LOCATION
# ============================================================

async def order_location(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    if not update.message.location:
        await update.message.reply_text(
            "❗ Илтимос, <b>📍 Геолокацияни юбориш</b> тугмасини босинг.",
            parse_mode="HTML",
        )
        return C_LOCATION

    location = update.message.location

    context.user_data["order"]["latitude"] = location.latitude
    context.user_data["order"]["longitude"] = location.longitude

    await update.message.reply_text(
        "🛠 <b>Хизмат турини танланг:</b>",
        parse_mode="HTML",
        reply_markup=service_keyboard(),
    )

    return C_SERVICE


# ============================================================
# SERVICE
# ============================================================

async def order_service(update, context):

    text = update.message.text

    if text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    context.user_data["order"]["service"] = text

    await update.message.reply_text(
        "📸 <b>Муаммо расмини юборинг.</b>\n\n"
        "Агар расм бўлмаса:\n"
        "➡️ <b>Расм йўқ</b> деб ёзинг.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("📷 Rasm yo'q")],
                [KeyboardButton("❌ Bekor qilish")],
            ],
            resize_keyboard=True,
        ),
    )

    return C_PHOTO


# ============================================================
# PROBLEM PHOTO
# ============================================================

async def order_photo(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    if update.message.photo:

        photos = context.user_data["order"].get(
            "problem_photo_ids",
            [],
        )

        photos.append(
            update.message.photo[-1].file_id
        )

        context.user_data["order"]["problem_photo_ids"] = photos

        await update.message.reply_text(
            "📸 Расм қабул қилинди.\n\n"
            "📍 Энди манзилни ёзинг:"
        )

        return C_ADDRESS

    if update.message.text in ["📷 Rasm yo'q", "Rasm yo'q"]:

        context.user_data["order"]["problem_photo_ids"] = []

        await update.message.reply_text(
            "📍 Энди тўлиқ манзилни ёзинг:"
        )

        return C_ADDRESS

    await update.message.reply_text(
        "❗ Расм юборинг ёки <b>📷 Rasm yo'q</b> тугмасини босинг.",
        parse_mode="HTML",
    )

    return C_PHOTO


# ============================================================
# ADDRESS
# ============================================================

async def order_address(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    context.user_data["order"]["address"] = update.message.text.strip()

    await update.message.reply_text(
        "🕐 <b>Қачон уста керак?</b>",
        parse_mode="HTML",
        reply_markup=time_keyboard(),
    )

    return C_TIME


# ============================================================
# TIME
# ============================================================

async def order_time(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    context.user_data["order"]["requested_time"] = update.message.text

    await update.message.reply_text(
        "📝 Қўшимча изоҳ ёзинг.\n\n"
        "Масалан: розетка ишламайди, шкафни 3-қаватга олиб чиқиш керак.\n\n"
        "Агар изоҳ бўлмаса: <b>Йўқ</b> деб ёзинг.",
        parse_mode="HTML",
    )

    return C_COMMENT


# ============================================================
# COMMENT
# ============================================================

async def order_comment(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    comment = update.message.text.strip()

    if comment.lower() == "йўқ" or comment.lower() == "yo'q":
        comment = ""

    context.user_data["order"]["comment"] = comment

    order = context.user_data["order"]

    photos = order.get("problem_photo_ids", [])

    photo_text = f"✅ {len(photos)} та расм" if photos else "❌ Йўқ"

    emergency_text = "Оддий"

    text = (
        "📋 <b>БУЮРТМА ТЕКШИРУВИ</b>\n\n"
        f"👤 Исм: {order.get('customer_name')}\n"
        f"📞 Телефон: {order.get('phone')}\n"
        f"🛠 Хизмат: {order.get('service')}\n"
        f"📍 Манзил: {order.get('address')}\n"
        f"🕐 Вақт: {order.get('requested_time')}\n"
        f"📸 Муаммо расми: {photo_text}\n"
        f"📝 Изоҳ: {order.get('comment') or 'Йўқ'}\n"
        f"🚨 Режим: {emergency_text}\n\n"
        "Тўғрими?"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Tasdiqlash",
                    callback_data="confirm_order",
                ),
                InlineKeyboardButton(
                    "❌ Bekor qilish",
                    callback_data="cancel_order",
                ),
            ]
        ]
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    return C_CONFIRM


# ============================================================
# CONFIRM ORDER
# ============================================================

async def confirm_order(update, context):

    query = update.callback_query

    await query.answer()

    if query.data == "cancel_order":

        context.user_data.clear()

        await query.edit_message_text(
            "❌ Буюртма бекор қилинди."
        )

        await query.message.reply_text(
            "Асосий меню:",
            reply_markup=client_keyboard(),
        )

        return ConversationHandler.END

    if query.data != "confirm_order":
        return C_CONFIRM

    order = context.user_data.get("order", {})
    user = update.effective_user

    photos = order.get("problem_photo_ids", [])

    row = await db_fetchrow(
        """
        INSERT INTO orders
        (
            customer_id,
            customer_name,
            phone,
            service,
            address,
            comment,
            latitude,
            longitude,
            problem_photo_ids,
            requested_time,
            emergency,
            emergency_level,
            emergency_markup,
            status,
            payment_method,
            payment_status
        )
        VALUES
        (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
            FALSE,NULL,0,'new','cash','unpaid'
        )
        RETURNING id
        """,
        user.id,
        order.get("customer_name"),
        order.get("phone"),
        order.get("service"),
        order.get("address"),
        order.get("comment"),
        order.get("latitude"),
        order.get("longitude"),
        ",".join(photos),
        order.get("requested_time"),
    )

    order_id = row["id"]

    context.user_data.clear()

    await query.edit_message_text(
        f"✅ <b>Буюртмангиз қабул қилинди!</b>\n\n"
        f"🆔 Буюртма №{order_id}\n"
        f"🛠 Хизмат: {order.get('service')}\n"
        f"🕐 Вақт: {order.get('requested_time')}\n\n"
        "👨‍🔧 Усталарга юборилмоқда...",
        parse_mode="HTML",
    )

    await send_order_to_group(order_id)

    await notify_admin(
        f"🆕 <b>ЯНГИ БУЮРТМА!</b>\n\n"
        f"🆔 #{order_id}\n"
        f"👤 {order.get('customer_name')}\n"
        f"📞 {order.get('phone')}\n"
        f"🛠 {order.get('service')}\n"
        f"📍 {order.get('address')}",
    )

    await query.message.reply_text(
        "Асосий меню:",
        reply_markup=client_keyboard(),
    )

    return ConversationHandler.END


# ============================================================
# SEND ORDER TO MASTERS GROUP
# ============================================================

async def send_order_to_group(order_id):

    if not MASTERS_GROUP_ID:
        logger.warning("MASTERS_GROUP_ID not configured")
        return

    order = await db_fetchrow(
        "SELECT * FROM orders WHERE id=$1",
        order_id,
    )

    if not order:
        return

    photos = []

    if order["problem_photo_ids"]:
        photos = [
            x for x in order["problem_photo_ids"].split(",")
            if x
        ]

    text = (
        "🆕 <b>YANGI BUYURTMA!</b>\n\n"
        f"🆔 <b>#{order['id']}</b>\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['phone']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"🕐 Vaqt: {order['requested_time']}\n"
        f"📝 Izoh: {order['comment'] or 'Йўқ'}\n"
        f"📸 Rasm: {'✅ ' + str(len(photos)) + ' ta' if photos else '❌'}\n"
        f"💵 To'lov: FAQAT NAQD + ISHDAN KEYIN\n\n"
        "Қайси уста қабул қилади?"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ QABUL QILISH",
                    callback_data=f"accept:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ RAD ETISH",
                    callback_data=f"reject:{order_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📸 RASMNI KO'RISH",
                    callback_data=f"photos:{order_id}",
                )
            ],
        ]
    )

    message = await application.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Save group message id for later editing
    await db_execute(
        """
        ALTER TABLE orders
        ADD COLUMN IF NOT EXISTS group_message_id BIGINT
        """
    )

    await db_execute(
        """
        UPDATE orders
        SET group_message_id=$1
        WHERE id=$2
        """,
        message.message_id,
        order_id,
    )

    for photo_id in photos:
        try:
            await application.bot.send_photo(
                chat_id=MASTERS_GROUP_ID,
                photo=photo_id,
            )
        except Exception as e:
            logger.error("Photo send error: %s", e)


# ============================================================
# MASTER CALLBACK
# ============================================================

async def master_callback(update, context):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    role = await get_user_role(user_id)

    if role != "master":

        await query.answer(
            "❌ Сиз тасдиқланган уста эмассиз.",
            show_alert=True,
        )
        return

    data = query.data

    if ":" not in data:
        return

    action, value = data.split(":", 1)

    try:
        order_id = int(value)
    except ValueError:
        return

    order = await db_fetchrow(
        "SELECT * FROM orders WHERE id=$1",
        order_id,
    )

    if not order:
        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True,
        )
        return

    # --------------------------------------------------------
    # ACCEPT
    # --------------------------------------------------------

    if action == "accept":

        if order["status"] != "new":

            await query.answer(
                "❌ Бу буюртмани бошқа уста қабул қилган.",
                show_alert=True,
            )
            return

        master = await db_fetchrow(
            """
            SELECT * FROM masters
            WHERE telegram_id=$1
            AND status='approved'
            """,
            user_id,
        )

        if not master:
            return

        await db_execute(
            """
            UPDATE orders
            SET
                status='accepted',
                master_id=$1,
                master_name=$2
            WHERE id=$3
            AND status='new'
            """,
            user_id,
            master["name"],
            order_id,
        )

        await db_execute(
            """
            UPDATE masters
            SET total_orders=total_orders+1
            WHERE telegram_id=$1
            """,
            user_id,
        )

        await query.edit_message_text(
            f"✅ <b>#{order_id} ҚАБУЛ ҚИЛИНДИ</b>\n\n"
            f"👨‍🔧 Уста: {master['name']}\n"
            f"⭐ Рейтинг: {master['rating']}",
            parse_mode="HTML",
        )

        await application.bot.send_message(
            chat_id=order["customer_id"],
            text=(
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"🆔 #{order_id}\n"
                f"👨‍🔧 Usta: {master['name']}\n"
                f"⭐ Reyting: {master['rating']}\n"
                f"🕐 Вақт: {order['requested_time']}"
            ),
            parse_mode="HTML",
        )

        await notify_admin(
            f"✅ <b>БУЮРТМА ҚАБУЛ ҚИЛИНДИ</b>\n\n"
            f"🆔 #{order_id}\n"
            f"👨‍🔧 Уста: {master['name']}\n"
            f"👤 Мижоз: {order['customer_name']}"
        )

        return

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    if action == "reject":

        if order["status"] != "new":
            await query.answer(
                "Буюртма энди янги эмас.",
                show_alert=True,
            )
            return

        await query.answer("Rad etildi")

        await application.bot.send_message(
            chat_id=order["customer_id"],
            text=(
                f"❌ <b>Buyurtmangizni bu usta qabul qilmadi.</b>\n\n"
                f"🆔 #{order_id}\n"
                "🔄 Boshqa ustani qidiramiz..."
            ),
            parse_mode="HTML",
        )

        await query.edit_message_text(
            f"❌ <b>#{order_id} рад этилди.</b>\n\n"
            "🔄 Бошқа усталар кўриб чиқади.",
            parse_mode="HTML",
        )

        # Important:
        # order remains new so another master can accept it
        await db_execute(
            """
            UPDATE orders
            SET status='new'
            WHERE id=$1
            """,
            order_id,
        )

        # Send fresh copy
        await asyncio.sleep(1)

        await send_order_to_group(order_id)

        return

    # --------------------------------------------------------
    # PHOTOS
    # --------------------------------------------------------

    if action == "photos":

        photos = []

        if order["problem_photo_ids"]:
            photos = [
                x for x in order["problem_photo_ids"].split(",")
                if x
            ]

        if not photos:

            await query.answer(
                "📸 Муаммо расми йўқ.",
                show_alert=True,
            )
            return

        await query.answer("Расмлар юборилмоқда...")

        for photo in photos:
            await application.bot.send_photo(
                chat_id=query.from_user.id,
                photo=photo,
            )

        return


# ============================================================
# MASTER START
# ============================================================

async def master_start(update, context):

    user_id = update.effective_user.id

    master = await db_fetchrow(
        "SELECT * FROM masters WHERE telegram_id=$1",
        user_id,
    )

    if master and master["status"] == "approved":

        await update.message.reply_text(
            "👨‍🔧 <b>Уста панели</b>",
            parse_mode="HTML",
            reply_markup=master_keyboard(),
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "👨‍🔧 <b>УСТА БЎЛИШ</b>\n\n"
        "Исмингизни ёзинг:",
        parse_mode="HTML",
    )

    return MASTER_NAME


async def master_register_name(update, context):

    context.user_data["master"] = {
        "name": update.message.text.strip()
    }

    await update.message.reply_text(
        "📞 Телефон рақамингизни юборинг:"
    )

    return MASTER_PHONE


async def master_register_phone(update, context):

    phone = (
        update.message.contact.phone_number
        if update.message.contact
        else update.message.text.strip()
    )

    context.user_data["master"]["phone"] = phone

    await update.message.reply_text(
        "🛠 Қайси хизмат турида ишлайсиз?"
    )

    return MASTER_SERVICE


async def master_register_service(update, context):

    context.user_data["master"]["service"] = update.message.text.strip()

    await update.message.reply_text(
        "📍 Қайси ҳудудларда ишлайсиз?"
    )

    return MASTER_AREA


async def master_register_area(update, context):

    context.user_data["master"]["area"] = update.message.text.strip()

    data = context.user_data["master"]
    user_id = update.effective_user.id

    await db_execute(
        """
        INSERT INTO masters
        (
            telegram_id,
            name,
            phone,
            service,
            area,
            status
        )
        VALUES ($1,$2,$3,$4,$5,'pending')

        ON CONFLICT (telegram_id)
        DO UPDATE SET
            name=EXCLUDED.name,
            phone=EXCLUDED.phone,
            service=EXCLUDED.service,
            area=EXCLUDED.area,
            status='pending'
        """,
        user_id,
        data["name"],
        data["phone"],
        data["service"],
        data["area"],
    )

    await update.message.reply_text(
        "✅ <b>Аризангиз қабул қилинди.</b>\n\n"
        "👨‍💼 Админ тасдиқлашини кутинг.\n"
        "Тасдиқлангандан кейин уста менюси очилади.",
        parse_mode="HTML",
        reply_markup=client_keyboard(),
    )

    await notify_admin(
        "👨‍🔧 <b>ЯНГИ УСТА АРИЗАСИ</b>\n\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}\n"
        f"🛠 {data['service']}\n"
        f"📍 {data['area']}\n"
        f"🆔 Telegram ID: {user_id}",
        keyboard=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Tasdiqlash",
                        callback_data=f"approve_master:{user_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Rad etish",
                        callback_data=f"reject_master:{user_id}",
                    ),
                ]
            ]
        ),
    )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# MASTER WORK CALLBACK
# ============================================================

async def work_callback(update, context):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    role = await get_user_role(user_id)

    if role != "master":
        return

    data = query.data

    if ":" not in data:
        return

    action, value = data.split(":", 1)

    try:
        order_id = int(value)
    except Exception:
        return

    order = await db_fetchrow(
        "SELECT * FROM orders WHERE id=$1",
        order_id,
    )

    if not order:
        return

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if action == "start_work":

        if order["master_id"] != user_id:
            return

        if order["status"] != "accepted":
            await query.answer(
                "❌ Бу буюртма иш бошлаш ҳолатида эмас.",
                show_alert=True,
            )
            return

        await db_execute(
            """
            UPDATE orders
            SET
                status='working',
                started_at=NOW()
            WHERE id=$1
            """,
            order_id,
        )

        await query.edit_message_text(
            f"🔧 <b>#{order_id} — ИШ БОШЛАНДИ</b>",
            parse_mode="HTML",
        )

        await application.bot.send_message(
            chat_id=order["customer_id"],
            text=(
                f"🔧 <b>Ish boshlandi!</b>\n\n"
                f"🆔 #{order_id}\n"
                f"👨‍🔧 Usta: {order['master_name']}"
            ),
            parse_mode="HTML",
        )

        return

    # --------------------------------------------------------
    # FINISH REQUEST
    # --------------------------------------------------------

    if action == "finish_work":

        if order["master_id"] != user_id:
            return

        if order["status"] != "working":
            await query.answer(
                "❌ Иш аввал бошланиши керак.",
                show_alert=True,
            )
            return

        context.user_data["finish_order_id"] = order_id
        context.user_data["finish_photos"] = []

        await query.message.reply_text(
            f"📸 <b>#{order_id} иш натижаси</b>\n\n"
            "Иш тугаганидан кейин натижа расмини юборинг.\n"
            "📸 Камида 1 та расм мажбурий.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [KeyboardButton("✅ Rasmlarni tugatish")],
                    [KeyboardButton("❌ Bekor qilish")],
                ],
                resize_keyboard=True,
            ),
        )

        return FINISH_PHOTO


# ============================================================
# FINISH PHOTO
# ============================================================

async def finish_photo(update, context):

    if update.message.text == "❌ Bekor qilish":

        context.user_data.pop("finish_order_id", None)
        context.user_data.pop("finish_photos", None)

        await update.message.reply_text(
            "Бекор қилинди.",
            reply_markup=master_keyboard(),
        )

        return ConversationHandler.END

    if update.message.photo:

        photo_id = update.message.photo[-1].file_id

        context.user_data.setdefault(
            "finish_photos",
            []
        ).append(photo_id)

        await update.message.reply_text(
            "✅ Расм қабул қилинди.\n"
            "Яна расм юборишингиз мумкин ёки "
            "<b>✅ Rasmlarni tugatish</b>ни босинг.",
            parse_mode="HTML",
        )

        return FINISH_PHOTO

    if update.message.text == "✅ Rasmlarni tugatish":

        photos = context.user_data.get("finish_photos", [])

        if not photos:

            await update.message.reply_text(
                "❗ Камида 1 та натижа расми мажбурий."
            )

            return FINISH_PHOTO

        order_id = context.user_data.get("finish_order_id")

        order = await db_fetchrow(
            "SELECT * FROM orders WHERE id=$1",
            order_id,
        )

        if not order:
            return ConversationHandler.END

        await db_execute(
            """
            UPDATE orders
            SET
                status='completed',
                result_photo_ids=$1,
                completed_at=NOW(),
                payment_method='cash',
                payment_status='unpaid'
            WHERE id=$2
            """,
            ",".join(photos),
            order_id,
        )

        await db_execute(
            """
            UPDATE masters
            SET completed_orders=completed_orders+1
            WHERE telegram_id=$1
            """,
            order["master_id"],
        )

        text = (
            f"✅ <b>Ish yakunlandi!</b>\n\n"
            f"🆔 #{order_id}\n"
            f"👨‍🔧 Usta: {order['master_name']}\n"
            f"📸 Natija rasmlari: {len(photos)} ta\n\n"
            "💵 To'lov: <b>FAQAT NAQD</b>\n"
            "💰 To'lov: <b>ISHDAN KEYIN</b>\n\n"
            "⭐ Устага рейтинг қолдиринг:"
        )

        rating_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐ 1",
                        callback_data=f"rate:{order_id}:1",
                    ),
                    InlineKeyboardButton(
                        "⭐ 2",
                        callback_data=f"rate:{order_id}:2",
                    ),
                    InlineKeyboardButton(
                        "⭐ 3",
                        callback_data=f"rate:{order_id}:3",
                    ),
                    InlineKeyboardButton(
                        "⭐ 4",
                        callback_data=f"rate:{order_id}:4",
                    ),
                    InlineKeyboardButton(
                        "⭐ 5",
                        callback_data=f"rate:{order_id}:5",
                    ),
                ]
            ]
        )

        await application.bot.send_message(
            chat_id=order["customer_id"],
            text=text,
            parse_mode="HTML",
            reply_markup=rating_keyboard,
        )

        for photo in photos:

            try:
                await application.bot.send_photo(
                    chat_id=order["customer_id"],
                    photo=photo,
                )
            except Exception as e:
                logger.error("Result photo customer error: %s", e)

        await application.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=(
                f"✅ <b>#{order_id} BUYURTMA YAKUNLANDI!</b>\n\n"
                f"👨‍🔧 Usta: {order['master_name']}\n"
                f"📸 {len(photos)} ta natija rasmi"
            ),
            parse_mode="HTML",
        )

        await notify_admin(
            f"✅ <b>ИШ ЯКУНЛАНДИ!</b>\n\n"
            f"🆔 #{order_id}\n"
            f"👨‍🔧 {order['master_name']}\n"
            f"👤 {order['customer_name']}\n"
            f"📸 {len(photos)} ta natija rasmi\n"
            f"💵 Тўлов: нақд, ишдан кейин",
        )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Иш муваффақиятли якунланди.",
            reply_markup=master_keyboard(),
        )

        return ConversationHandler.END

    await update.message.reply_text(
        "📸 Илтимос, натижа расмини юборинг."
    )

    return FINISH_PHOTO


# ============================================================
# RATING
# ============================================================

async def rating_callback(update, context):

    query = update.callback_query
    await query.answer()

    data = query.data.split(":")

    if len(data) != 3:
        return

    order_id = int(data[1])
    rating = int(data[2])

    order = await db_fetchrow(
        """
        SELECT *
        FROM orders
        WHERE id=$1
        """,
        order_id,
    )

    if not order:
        return

    if order["customer_id"] != query.from_user.id:
        return

    old = await db_fetchrow(
        """
        SELECT id
        FROM ratings
        WHERE order_id=$1
        AND customer_id=$2
        """,
        order_id,
        query.from_user.id,
    )

    if old:
        await query.answer(
            "Сиз аллақачон рейтинг қолдиргансиз.",
            show_alert=True,
        )
        return

    await db_execute(
        """
        INSERT INTO ratings
        (
            order_id,
            customer_id,
            master_id,
            rating
        )
        VALUES ($1,$2,$3,$4)
        """,
        order_id,
        query.from_user.id,
        order["master_id"],
        rating,
    )

    master = await db_fetchrow(
        """
        SELECT rating, rating_count
        FROM masters
        WHERE telegram_id=$1
        """,
        order["master_id"],
    )

    if master:

        old_rating = float(master["rating"] or 5)
        old_count = int(master["rating_count"] or 0)

        new_count = old_count + 1

        new_rating = (
            (old_rating * old_count) + rating
        ) / new_count

        await db_execute(
            """
            UPDATE masters
            SET
                rating=$1,
                rating_count=$2
            WHERE telegram_id=$3
            """,
            round(new_rating, 2),
            new_count,
            order["master_id"],
        )

    await query.edit_message_text(
        f"⭐ <b>Раҳмат!</b>\n\n"
        f"Сиз <b>{rating}/5</b> рейтинг бердингиз.",
        parse_mode="HTML",
    )

    try:

        await application.bot.send_message(
            chat_id=order["master_id"],
            text=(
                f"⭐ <b>ЯНГИ РЕЙТИНГ!</b>\n\n"
                f"🆔 #{order_id}\n"
                f"⭐ {rating}/5\n\n"
                "Мижоз сизга рейтинг қолдирди."
            ),
            parse_mode="HTML",
        )

    except Exception:
        pass


# ============================================================
# ADMIN MASTER APPROVAL
# ============================================================

async def admin_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        await query.answer(
            "❌ Фақат админ.",
            show_alert=True,
        )
        return

    data = query.data

    if ":" not in data:
        return

    action, value = data.split(":", 1)

    if action == "approve_master":

        master_id = int(value)

        master = await db_fetchrow(
            "SELECT * FROM masters WHERE telegram_id=$1",
            master_id,
        )

        if not master:
            return

        await db_execute(
            """
            UPDATE masters
            SET status='approved'
            WHERE telegram_id=$1
            """,
            master_id,
        )

        await db_execute(
            """
            UPDATE users
            SET role='master'
            WHERE id=$1
            """,
            master_id,
        )

        await query.edit_message_text(
            f"✅ <b>Уста тасдиқланди</b>\n\n"
            f"👨‍🔧 {master['name']}",
            parse_mode="HTML",
        )

        try:

            await application.bot.send_message(
                chat_id=master_id,
                text=(
                    "🎉 <b>ТАБРИКЛАЙМИЗ!</b>\n\n"
                    "Сиз USTA 24 тизимида уста сифатида тасдиқландингиз.\n\n"
                    "Энди янги буюртмаларни қабул қилишингиз мумкин."
                ),
                parse_mode="HTML",
                reply_markup=master_keyboard(),
            )

        except Exception:
            pass

    elif action == "reject_master":

        master_id = int(value)

        master = await db_fetchrow(
            "SELECT * FROM masters WHERE telegram_id=$1",
            master_id,
        )

        await db_execute(
            """
            UPDATE masters
            SET status='rejected'
            WHERE telegram_id=$1
            """,
            master_id,
        )

        await query.edit_message_text(
            "❌ Уста аризаси рад этилди."
        )

        if master:

            try:

                await application.bot.send_message(
                    chat_id=master_id,
                    text=(
                        "❌ Уста сифатида рўйхатдан ўтиш аризангиз рад этилди.\n\n"
                        "Қўшимча маълумот учун диспетчерга мурожаат қилинг."
                    ),
                )

            except Exception:
                pass


# ============================================================
# ADMIN
# ============================================================

async def admin_users(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    row = await db_fetchrow(
        """
        SELECT
            COUNT(*) AS total
        FROM users
        """
    )

    await update.message.reply_text(
        f"👥 <b>ФОЙДАЛАНУВЧИЛАР</b>\n\n"
        f"👤 Жами: {row['total']}",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )


async def admin_orders(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    rows = await db_fetch(
        """
        SELECT id, customer_name, service, status
        FROM orders
        ORDER BY id DESC
        LIMIT 20
        """
    )

    if not rows:

        await update.message.reply_text(
            "📋 Буюртмалар йўқ."
        )
        return

    text = "🛠 <b>СЎНГГИ БУЮРТМАЛАР</b>\n\n"

    for row in rows:

        text += (
            f"#{row['id']} | "
            f"{row['customer_name']} | "
            f"{row['service']} | "
            f"{row['status']}\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


async def admin_masters(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    rows = await db_fetch(
        """
        SELECT
            telegram_id,
            name,
            phone,
            service,
            area,
            status,
            rating
        FROM masters
        ORDER BY id DESC
        """
    )

    if not rows:

        await update.message.reply_text(
            "👨‍🔧 Усталар ҳали йўқ."
        )
        return

    text = "👨‍🔧 <b>УСТАЛАР</b>\n\n"

    for row in rows:

        text += (
            f"👤 {row['name']}\n"
            f"📞 {row['phone']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['area']}\n"
            f"📌 {row['status']}\n"
            f"⭐ {row['rating']}\n"
            f"🆔 {row['telegram_id']}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


async def admin_statistics(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    users = await db_fetchrow(
        "SELECT COUNT(*) AS n FROM users"
    )

    orders = await db_fetchrow(
        "SELECT COUNT(*) AS n FROM orders"
    )

    new_orders = await db_fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM orders
        WHERE status='new'
        """
    )

    working = await db_fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM orders
        WHERE status='working'
        """
    )

    completed = await db_fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM orders
        WHERE status='completed'
        """
    )

    masters = await db_fetchrow(
        """
        SELECT COUNT(*) AS n
        FROM masters
        WHERE status='approved'
        """
    )

    await update.message.reply_text(
        "📊 <b>USTA 24 STATISTIKA</b>\n\n"
        f"👥 Фойдаланувчилар: {users['n']}\n"
        f"🛠 Жами буюртмалар: {orders['n']}\n"
        f"🆕 Янги: {new_orders['n']}\n"
        f"🔧 Жараёнда: {working['n']}\n"
        f"✅ Якунланган: {completed['n']}\n"
        f"👨‍🔧 Фаол усталар: {masters['n']}\n",
        parse_mode="HTML",
    )


# ============================================================
# ADMIN ORDER BUTTONS
# ============================================================

async def admin_order_callback(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data.startswith("admin_confirm:"):

        order_id = int(data.split(":")[1])

        await db_execute(
            """
            UPDATE orders
            SET payment_status='paid'
            WHERE id=$1
            """,
            order_id,
        )

        await query.edit_message_text(
            f"✅ #{order_id} тўлови тасдиқланди."
        )

    elif data.startswith("admin_reject:"):

        order_id = int(data.split(":")[1])

        await db_execute(
            """
            UPDATE orders
            SET status='cancelled'
            WHERE id=$1
            """,
            order_id,
        )

        await query.edit_message_text(
            f"❌ #{order_id} рад этилди."
        )


# ============================================================
# CLIENT ORDERS
# ============================================================

async def my_orders(update, context):

    user_id = update.effective_user.id

    rows = await db_fetch(
        """
        SELECT
            id,
            service,
            status,
            requested_time,
            master_name,
            created_at
        FROM orders
        WHERE customer_id=$1
        ORDER BY id DESC
        LIMIT 20
        """,
        user_id,
    )

    if not rows:

        await update.message.reply_text(
            "📋 Сизда ҳали буюртмалар йўқ."
        )
        return

    text = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"

    status_names = {
        "new": "🆕 Янги",
        "accepted": "✅ Қабул қилинган",
        "working": "🔧 Иш жараёнида",
        "completed": "🏁 Якунланган",
        "cancelled": "❌ Бекор қилинган",
    }

    for row in rows:

        text += (
            f"🆔 #{row['id']}\n"
            f"🛠 {row['service']}\n"
            f"📌 {status_names.get(row['status'], row['status'])}\n"
            f"🕐 {row['requested_time']}\n"
            f"👨‍🔧 {row['master_name'] or 'Ҳали бириктирилмаган'}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# ORDER STATUS
# ============================================================

async def order_status(update, context):

    user_id = update.effective_user.id

    row = await db_fetchrow(
        """
        SELECT *
        FROM orders
        WHERE customer_id=$1
        ORDER BY id DESC
        LIMIT 1
        """,
        user_id,
    )

    if not row:

        await update.message.reply_text(
            "🔍 Сизда ҳали буюртма йўқ."
        )
        return

    status_names = {
        "new": "🆕 Янги — уста кутилмоқда",
        "accepted": "✅ Уста қабул қилди",
        "working": "🔧 Иш бошланган",
        "completed": "🏁 Иш якунланган",
        "cancelled": "❌ Бекор қилинган",
    }

    await update.message.reply_text(
        f"🔍 <b>БУЮРТМА #{row['id']}</b>\n\n"
        f"🛠 {row['service']}\n"
        f"📌 {status_names.get(row['status'], row['status'])}\n"
        f"👨‍🔧 {row['master_name'] or 'Ҳали йўқ'}\n"
        f"🕐 {row['requested_time']}",
        parse_mode="HTML",
    )


# ============================================================
# CANCEL ORDER
# ============================================================

async def cancel_client_order(update, context):

    user_id = update.effective_user.id

    row = await db_fetchrow(
        """
        SELECT *
        FROM orders
        WHERE customer_id=$1
        AND status IN ('new','accepted')
        ORDER BY id DESC
        LIMIT 1
        """,
        user_id,
    )

    if not row:

        await update.message.reply_text(
            "❌ Бекор қилиш мумкин бўлган буюртма йўқ."
        )
        return

    await db_execute(
        """
        UPDATE orders
        SET status='cancelled'
        WHERE id=$1
        """,
        row["id"],
    )

    await update.message.reply_text(
        f"❌ <b>#{row['id']} буюртма бекор қилинди.</b>",
        parse_mode="HTML",
    )

    await notify_admin(
        f"❌ <b>БУЮРТМА БЕКОР ҚИЛИНДИ</b>\n\n"
        f"#{row['id']}\n"
        f"👤 {row['customer_name']}"
    )


# ============================================================
# EMERGENCY START
# ============================================================

async def emergency_start(update, context):

    await update.message.reply_text(
        "🚨 <b>24/7 ШОШИЛИНЧ РЕЖИМ</b>\n\n"
        "Қандай ҳолат?\n\n"
        "💧 Сув\n"
        "⚡ Электр\n"
        "🔥 Газ\n"
        "🚪 Эшик\n"
        "🚰 Қувур\n"
        "🛠 Бошқа",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton("💧 Сув"),
                    KeyboardButton("⚡ Электр"),
                ],
                [
                    KeyboardButton("🔥 Газ"),
                    KeyboardButton("🚪 Эшик"),
                ],
                [
                    KeyboardButton("🚰 Қувур"),
                    KeyboardButton("🛠 Boshqa"),
                ],
                [
                    KeyboardButton("❌ Bekor qilish"),
                ],
            ],
            resize_keyboard=True,
        ),
    )

    return EMERGENCY_TYPE


async def emergency_type(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    context.user_data["emergency_type"] = update.message.text

    await update.message.reply_text(
        "⏱ <b>Қачон уста керак?</b>\n\n"
        "🔴 ҲОЗИР — 10-15 дақиқа — +20%\n"
        "🟡 ЯРИМ СОАТДА — +10%\n"
        "🟢 1 СОАТДА — оддий нарх",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("🔴 Hozir (+20%)")],
                [KeyboardButton("🟡 Yarim soatda (+10%)")],
                [KeyboardButton("🟢 1 soatda")],
                [KeyboardButton("❌ Bekor qilish")],
            ],
            resize_keyboard=True,
        ),
    )

    return EMERGENCY_TIME


async def emergency_time(update, context):

    if update.message.text == "❌ Bekor qilish":
        return await cancel_conversation(update, context)

    user_id = update.effective_user.id

    markup = 0
    level = update.message.text

    if "+20%" in level:
        markup = 20
    elif "+10%" in level:
        markup = 10

    row = await db_fetchrow(
        """
        SELECT
            first_name,
            phone
        FROM users
        WHERE id=$1
        """,
        user_id,
    )

    name = (
        row["first_name"]
        if row and row["first_name"]
        else update.effective_user.first_name
    )

    phone = row["phone"] if row else ""

    order = await db_fetchrow(
        """
        INSERT INTO orders
        (
            customer_id,
            customer_name,
            phone,
            service,
            address,
            comment,
            requested_time,
            emergency,
            emergency_level,
            emergency_markup,
            status,
            payment_method,
            payment_status
        )
        VALUES
        (
            $1,$2,$3,$4,$5,$6,$7,TRUE,$8,$9,
            'new','cash','unpaid'
        )
        RETURNING id
        """,
        user_id,
        name,
        phone,
        context.user_data.get("emergency_type"),
        "Манзил диспетчер орқали аниқланади",
        "🚨 ШОШИЛИНЧ БУЮРТМА",
        level,
        level,
        markup,
    )

    order_id = order["id"]

    await send_order_to_group(order_id)

    await notify_admin(
        f"🚨 <b>ШОШИЛИНЧ БУЮРТМА!</b>\n\n"
        f"🆔 #{order_id}\n"
        f"👤 {name}\n"
        f"📞 {phone}\n"
        f"🚨 {context.user_data.get('emergency_type')}\n"
        f"⏱ {level}\n"
        f"💰 Устама: +{markup}%"
    )

    await update.message.reply_text(
        f"🚨 <b>ШОШИЛИНЧ БУЮРТМА ҚАБУЛ ҚИЛИНДИ!</b>\n\n"
        f"🆔 #{order_id}\n"
        f"⏱ {level}\n"
        f"💰 Устама: +{markup}%\n\n"
        "👨‍🔧 Яқиндаги устага юборилди.\n"
        "📞 Диспетчер: "
        f"<a href='tel:{DISPATCHER_PHONE}'>{DISPATCHER_PHONE}</a>",
        parse_mode="HTML",
        reply_markup=client_keyboard(),
    )

    context.user_data.clear()

    return ConversationHandler.END


# ============================================================
# GENERIC CLIENT FEATURES
# ============================================================

async def client_feature(update, context):

    text = update.message.text

    responses = {

        "👨‍🔧 Mening ustalarim":
            "👨‍🔧 <b>МЕНИНГ УСТАЛАРИМ</b>\n\n"
            "Ҳали доимий уста сақланмаган.",

        "⭐ Reytingim":
            "⭐ <b>РЕЙТИНГИМ</b>\n\n"
            "Сизнинг мижоз сифатидаги рейтингингиз яқинда қўшилади.",

        "📝 Sharh qoldirish":
            "📝 Шарҳ қолдириш учун аввал якунланган буюртмани танланг.",

        "📌 Eslatmalarim":
            "📌 Ҳозирча эслатмаларингиз йўқ.",

        "🗺️ Yaqin atrofdagi ustalar":
            "🗺️ Яқин усталарни кўрсатиш функцияси геолокация асосида ишлайди.",

        "📅 Yozilma (bron)":
            "📅 Брон қилиш хизмати: уста ва вақт танлаш орқали.",

        "🎁 Loyallik va bonuslar":
            "🎁 Лояллик дастури.\n\n"
            "Бонуслар тизими ишлаб чиқилмоқда.",

        "🤖 AI yordamchi":
            "🤖 AI ёрдамчи.\n\n"
            "Хизмат танлаш ва муаммони аниқлашда ёрдам беради.",

        "⚙️ Sozlamalar":
            "⚙️ <b>Созламалар</b>\n\n"
            "Телефон, исм ва билдиришнома созламалари.",

        "📊 Mening statistika":
            "📊 Сизнинг статистикангиз.",

        "🏷️ Chegirmalar va aksiyalar":
            "🏷️ Ҳозирча фаол акциялар йўқ.",

        "📞 Tez yordam":
            f"📞 <b>ТЕЗ ЁРДАМ</b>\n\n"
            f"Диспетчер: {DISPATCHER_PHONE}",

        "🔔 Bildirishnomalar":
            "🔔 Билдиришномалар ёқилган.",

        "📁 Mening hujjatlarim":
            "📁 Ҳужжатларингиз ҳозирча йўқ.",

        "🕊️ Do'stga tavsiya qilish":
            "🕊️ Дўстингизга USTA 24 ни тавсия қилинг!",

        "📞 Dispetcherga qo'ng'iroq":
            f"📞 <b>ДИСПЕТЧЕР</b>\n\n"
            f"<a href='tel:{DISPATCHER_PHONE}'>{DISPATCHER_PHONE}</a>\n"
            "🕐 24/7",

    }

    if text in responses:

        await update.message.reply_text(
            responses[text],
            parse_mode="HTML",
        )


# ============================================================
# MASTER FEATURES
# ============================================================

async def master_feature(update, context):

    user_id = update.effective_user.id

    role = await get_user_role(user_id)

    if role != "master":
        return

    text = update.message.text

    if text == "📋 Yangi buyurtmalar":

        rows = await db_fetch(
            """
            SELECT
                id,
                service,
                customer_name,
                address,
                requested_time
            FROM orders
            WHERE status='new'
            ORDER BY id DESC
            LIMIT 20
            """
        )

        if not rows:

            await update.message.reply_text(
                "📋 Ҳозир янги буюртмалар йўқ."
            )
            return

        result = "📋 <b>ЯНГИ БУЮРТМАЛАР</b>\n\n"

        for row in rows:

            result += (
                f"🆔 #{row['id']}\n"
                f"🛠 {row['service']}\n"
                f"👤 {row['customer_name']}\n"
                f"📍 {row['address']}\n"
                f"🕐 {row['requested_time']}\n\n"
            )

        await update.message.reply_text(
            result,
            parse_mode="HTML",
        )

    elif text == "✅ Mening faol buyurtmalarim":

        rows = await db_fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id=$1
            AND status IN ('accepted','working')
            ORDER BY id DESC
            """,
            user_id,
        )

        if not rows:

            await update.message.reply_text(
                "✅ Фаол буюртмалар йўқ."
            )
            return

        for row in rows:

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔧 Ishni boshlash",
                            callback_data=f"start_work:{row['id']}",
                        ),
                        InlineKeyboardButton(
                            "✅ Ishni yakunlash",
                            callback_data=f"finish_work:{row['id']}",
                        ),
                    ]
                ]
            )

            await update.message.reply_text(
                f"🆔 #{row['id']}\n"
                f"🛠 {row['service']}\n"
                f"👤 {row['customer_name']}\n"
                f"📍 {row['address']}\n"
                f"📌 {row['status']}",
                reply_markup=keyboard,
            )

    elif text == "⏳ Tarix":

        rows = await db_fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id=$1
            AND status='completed'
            ORDER BY id DESC
            LIMIT 20
            """,
            user_id,
        )

        if not rows:

            await update.message.reply_text(
                "⏳ Якунланган буюртмалар йўқ."
            )
            return

        result = "⏳ <b>ЯКУНЛАНГАН ИШЛАР</b>\n\n"

        for row in rows:

            result += (
                f"#{row['id']} | "
                f"{row['service']} | "
                f"{row['customer_name']}\n"
            )

        await update.message.reply_text(
            result,
            parse_mode="HTML",
        )

    elif text == "💰 Ish haqi va hisobot":

        row = await db_fetchrow(
            """
            SELECT
                COUNT(*) AS count,
                COALESCE(SUM(final_price),0) AS total
            FROM orders
            WHERE master_id=$1
            AND status='completed'
            """,
            user_id,
        )

        await update.message.reply_text(
            "💰 <b>ИШ ҲАҚИ ВА ҲИСОБОТ</b>\n\n"
            f"🏁 Якунланган ишлар: {row['count']}\n"
            f"💵 Жами: {row['total']} сўм\n\n"
            "Тўлов усули: нақд.",
            parse_mode="HTML",
        )

    elif text == "⭐ Reytingim va sharhlar":

        master = await db_fetchrow(
            """
            SELECT rating, rating_count
            FROM masters
            WHERE telegram_id=$1
            """,
            user_id,
        )

        await update.message.reply_text(
            "⭐ <b>РЕЙТИНГИМ</b>\n\n"
            f"⭐ Рейтинг: {master['rating'] if master else 0}\n"
            f"👥 Баҳолар: {master['rating_count'] if master else 0}",
            parse_mode="HTML",
        )

    elif text == "📊 Ish statistikasi":

        row = await db_fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='working') AS working,
                COUNT(*) FILTER (WHERE status='accepted') AS accepted
            FROM orders
            WHERE master_id=$1
            """,
            user_id,
        )

        await update.message.reply_text(
            "📊 <b>ИШ СТАТИСТИКАСИ</b>\n\n"
            f"✅ Якунланган: {row['completed']}\n"
            f"🔧 Жараёнда: {row['working']}\n"
            f"⏳ Қабул қилинган: {row['accepted']}",
            parse_mode="HTML",
        )

    elif text == "📞 Dispetcherga qo'ng'iroq":

        await update.message.reply_text(
            f"📞 Диспетчер: "
            f"<a href='tel:{DISPATCHER_PHONE}'>{DISPATCHER_PHONE}</a>\n"
            "🕐 24/7",
            parse_mode="HTML",
        )

    elif text == "🏆 Ustalar reytingi":

        rows = await db_fetch(
            """
            SELECT name, rating, rating_count
            FROM masters
            WHERE status='approved'
            ORDER BY rating DESC
            LIMIT 10
            """
        )

        if not rows:

            await update.message.reply_text(
                "🏆 Ҳали усталар йўқ."
            )
            return

        result = "🏆 <b>TOP 10 УСТАЛАР</b>\n\n"

        for i, row in enumerate(rows, 1):

            result += (
                f"{i}. 👨‍🔧 {row['name']} — "
                f"⭐ {row['rating']} "
                f"({row['rating_count']})\n"
            )

        await update.message.reply_text(
            result,
            parse_mode="HTML",
        )

    elif text == "🚨 24/7 Shosilinch rejim":

        await update.message.reply_text(
            f"🚨 24/7 режим\n"
            f"📞 Диспетчер: {DISPATCHER_PHONE}\n"
            "🔴 ҲОЗИР +20%\n"
            "🟡 ЯРИМ СОАТ +10%\n"
            "🟢 1 СОАТ оддий нарх"
        )

    elif text == "📢 E'lonlar va yangiliklar":

        await update.message.reply_text(
            "📢 Ҳозирча янги эълонлар йўқ."
        )

    elif text == "🎁 Usta bonuslari":

        await update.message.reply_text(
            "🎁 Уста бонуслари тизими."
        )

    elif text == "🤖 AI yordamchi":

        await update.message.reply_text(
            "🤖 AI ёрдамчи."
        )

    elif text == "📞 Texnik yordam":

        await update.message.reply_text(
            f"📞 Техник ёрдам: {DISPATCHER_PHONE}"
        )

    elif text == "🔔 Mijozlar bilan bog'lanish":

        await update.message.reply_text(
            "🔔 Мижоз билан боғланиш учун актив буюртмадан фойдаланинг."
        )

    elif text == "📸 Galereya":

        await update.message.reply_text(
            "📸 Сизнинг иш натижаларингиз галереяси."
        )

    elif text == "🛠 Xizmatlarni boshqarish":

        await update.message.reply_text(
            "🛠 Хизматларингизни бошқариш функцияси."
        )

    elif text == "🏷️ Mening narxlarim":

        await update.message.reply_text(
            "🏷️ Нарҳларингизни админ билан келишинг."
        )

    elif text == "📍 Ish hududim":

        await update.message.reply_text(
            "📍 Иш ҳудудингизни админга билдиринг."
        )

    elif text == "📅 Kunlik ish jadvalim":

        await update.message.reply_text(
            "📅 Бугунги иш жадвалингиз."
        )

    elif text == "📅 Dam olish kunlari":

        await update.message.reply_text(
            "📅 Дам олиш кунлари созламаси."
        )

    elif text == "🔔 Bildirishnoma sozlamalari":

        await update.message.reply_text(
            "🔔 Билдиришномалар ёқилган."
        )

    elif text == "📝 Reytingni oshirish maslahatlar":

        await update.message.reply_text(
            "📝 Рейтингни ошириш учун:\n"
            "• Вақтида боринг\n"
            "• Сифатли ишланг\n"
            "• Мижоз билан яхши муомала қилинг\n"
            "• Иш натижасини расмга олинг"
        )


# ============================================================
# DISPATCHER
# ============================================================

async def dispatcher_feature(update, context):

    if update.effective_user.id != DISPATCHER_ID:
        return

    text = update.message.text

    if text == "📋 Yangi buyurtmalar":

        rows = await db_fetch(
            """
            SELECT id, customer_name, service, status
            FROM orders
            WHERE status='new'
            ORDER BY id DESC
            LIMIT 30
            """
        )

        if not rows:

            await update.message.reply_text(
                "📋 Янги буюртмалар йўқ."
            )
            return

        result = "📋 <b>ЯНГИ БУЮРТМАЛАР</b>\n\n"

        for row in rows:

            result += (
                f"#{row['id']} | "
                f"{row['customer_name']} | "
                f"{row['service']}\n"
            )

        await update.message.reply_text(
            result,
            parse_mode="HTML",
        )

    elif text == "🔧 Faol buyurtmalar":

        rows = await db_fetch(
            """
            SELECT id, customer_name, master_name, status
            FROM orders
            WHERE status IN ('accepted','working')
            ORDER BY id DESC
            LIMIT 30
            """
        )

        result = "🔧 <b>ФАОЛ БУЮРТМАЛАР</b>\n\n"

        for row in rows:

            result += (
                f"#{row['id']} | "
                f"{row['customer_name']} | "
                f"{row['master_name'] or 'Уста йўқ'} | "
                f"{row['status']}\n"
            )

        await update.message.reply_text(
            result or "Фаол буюртмалар йўқ.",
            parse_mode="HTML",
        )

    elif text == "👨‍🔧 Ustalar":

        rows = await db_fetch(
            """
            SELECT name, phone, status, rating
            FROM masters
            ORDER BY rating DESC
            """
        )

        result = "👨‍🔧 <b>УСТАЛАР</b>\n\n"

        for row in rows:

            result += (
                f"👤 {row['name']}\n"
                f"📞 {row['phone']}\n"
                f"📌 {row['status']}\n"
                f"⭐ {row['rating']}\n\n"
            )

        await update.message.reply_text(
            result or "Усталар йўқ.",
            parse_mode="HTML",
        )

    elif text == "👥 Foydalanuvchilar":

        row = await db_fetchrow(
            "SELECT COUNT(*) AS n FROM users"
        )

        await update.message.reply_text(
            f"👥 Фойдаланувчилар: {row['n']}"
        )

    elif text == "📊 Statistika":

        users = await db_fetchrow(
            "SELECT COUNT(*) AS n FROM users"
        )

        orders = await db_fetchrow(
            "SELECT COUNT(*) AS n FROM orders"
        )

        completed = await db_fetchrow(
            """
            SELECT COUNT(*) AS n
            FROM orders
            WHERE status='completed'
            """
        )

        await update.message.reply_text(
            "📊 <b>ДИСПЕТЧЕР СТАТИСТИКАСИ</b>\n\n"
            f"👥 Users: {users['n']}\n"
            f"🛠 Orders: {orders['n']}\n"
            f"✅ Completed: {completed['n']}",
            parse_mode="HTML",
        )

    elif text == "🚨 Shoshilinch":

        rows = await db_fetch(
            """
            SELECT id, customer_name, service, emergency_level
            FROM orders
            WHERE emergency=TRUE
            AND status NOT IN ('completed','cancelled')
            ORDER BY id DESC
            """
        )

        result = "🚨 <b>ШОШИЛИНЧ БУЮРТМАЛАР</b>\n\n"

        for row in rows:

            result += (
                f"#{row['id']} | "
                f"{row['customer_name']} | "
                f"{row['service']} | "
                f"{row['emergency_level']}\n"
            )

        await update.message.reply_text(
            result or "🚨 Шошилинч буюртмалар йўқ.",
            parse_mode="HTML",
        )

    elif text in [
        "📞 Mijoz bilan bog'lanish",
        "📞 Usta bilan bog'lanish",
    ]:

        await update.message.reply_text(
            f"📞 Диспетчер рақами: {DISPATCHER_PHONE}"
        )


# ============================================================
# ADMIN FEATURES
# ============================================================

async def admin_feature(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text

    if text == "👥 Foydalanuvchilar":
        await admin_users(update, context)

    elif text == "🛠 Buyurtmalar":
        await admin_orders(update, context)

    elif text == "👨‍🔧 Ustalar":
        await admin_masters(update, context)

    elif text == "📊 Statistika va hisobot":
        await admin_statistics(update, context)

    elif text == "⭐ Reyting va sharhlar":

        row = await db_fetchrow(
            """
            SELECT
                COUNT(*) AS count,
                COALESCE(AVG(rating),0) AS avg
            FROM ratings
            """
        )

        await update.message.reply_text(
            "⭐ <b>РЕЙТИНГЛАР</b>\n\n"
            f"⭐ Ўртача: {float(row['avg']):.2f}\n"
            f"📝 Жами баҳолар: {row['count']}",
            parse_mode="HTML",
        )

    elif text == "💰 To'lovlar":

        row = await db_fetchrow(
            """
            SELECT COUNT(*) AS n
            FROM orders
            WHERE payment_status='unpaid'
            AND status='completed'
            """
        )

        await update.message.reply_text(
            "💰 <b>ТЎЛОВЛАР</b>\n\n"
            f"⏳ Тўлови тасдиқланмаган: {row['n']}\n\n"
            "💵 Фақат нақд.\n"
            "🚫 Онлайн тўлов йўқ.\n"
            "🚫 Аванс йўқ.",
            parse_mode="HTML",
        )

    elif text == "🎁 Loyallik va bonuslar":
        await update.message.reply_text(
            "🎁 Лояллик ва бонус тизими."
        )

    elif text == "🏷️ Chegirmalar va aksiyalar":
        await update.message.reply_text(
            "🏷️ Акциялар ва чегирмалар."
        )

    elif text == "🛠 Xizmat turlari":

        text_services = "\n".join(
            f"• {service}"
            for service in SERVICES
        )

        await update.message.reply_text(
            "🛠 <b>ХИЗМАТ ТУРЛАРИ</b>\n\n"
            + text_services,
            parse_mode="HTML",
        )

    elif text == "📢 E'lonlar va yangiliklar":

        await update.message.reply_text(
            "📢 Эълонлар бўлими."
        )

    elif text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 <b>ДИСПЕТЧЕР</b>\n\n"
            f"{DISPATCHER_PHONE}\n"
            "🕐 24/7",
            parse_mode="HTML",
        )

    elif text == "⚙️ Sozlamalar":

        await update.message.reply_text(
            "⚙️ Админ созламалари."
        )

    elif text == "📸 Rasm galereyasi":

        await update.message.reply_text(
            "📸 Рasm galereyasi."
        )

    elif text == "📱 Botni boshqarish":

        await update.message.reply_text(
            "📱 Бот ишлаяпти.\n\n"
            "🤖 1 bot\n"
            "🗄 PostgreSQL\n"
            "📨 Masters group\n"
            "👤 Client\n"
            "👨‍🔧 Master\n"
            "👨‍💼 Admin\n"
            "📞 Dispatcher"
        )

    elif text == "📞 Qo'llab-quvvatlash":

        await update.message.reply_text(
            f"📞 Support: {DISPATCHER_PHONE}"
        )

    elif text == "🚨 24/7 Shosilinch rejim":

        await update.message.reply_text(
            "🚨 <b>24/7 ШОШИЛИНЧ РЕЖИМ</b>\n\n"
            "🔴 ҲОЗИР: +20%\n"
            "🟡 ЯРИМ СОАТ: +10%\n"
            "🟢 1 СОАТ: оддий нарх\n\n"
            f"📞 {DISPATCHER_PHONE}",
            parse_mode="HTML",
        )


# ============================================================
# CONTACT
# ============================================================

async def contact_handler(update, context):

    if update.message.contact:

        phone = update.message.contact.phone_number

        await db_execute(
            """
            UPDATE users
            SET phone=$1
            WHERE id=$2
            """,
            phone,
            update.effective_user.id,
        )


# ============================================================
# CANCEL CONVERSATION
# ============================================================

async def cancel_conversation(update, context):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Амалиёт бекор қилинди.",
        reply_markup=client_keyboard(),
    )

    return ConversationHandler.END


# ============================================================
# NOTIFY ADMIN
# ============================================================

async def notify_admin(text, keyboard=None):

    if not ADMIN_ID:
        return

    try:

        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.error(
            "Admin notification error: %s",
            e,
        )


# ============================================================
# HELP
# ============================================================

async def help_command(update, context):

    await update.message.reply_text(
        "ℹ️ <b>USTA 24 ANDIJON</b>\n\n"
        "🛠 Уйга уста чақириш\n"
        "📞 Диспетчер: "
        f"<a href='tel:{DISPATCHER_PHONE}'>{DISPATCHER_PHONE}</a>\n"
        "🕐 24/7",
        parse_mode="HTML",
    )


# ============================================================
# GLOBAL MESSAGE ROUTER
# ============================================================

async def message_router(update, context):

    if not update.message:
        return

    user = update.effective_user

    await save_user(user)

    role = await get_user_role(user.id)

    text = update.message.text or ""

    # --------------------------------------------------------
    # EXIT
    # --------------------------------------------------------

    if text == "🚪 Chiqish":

        if role == "admin":
            keyboard = admin_keyboard()
        elif role == "master":
            keyboard = master_keyboard()
        elif role == "dispatcher":
            keyboard = dispatcher_keyboard()
        else:
            keyboard = client_keyboard()

        await update.message.reply_text(
            "🚪 Менюга қайтдингиз.",
            reply_markup=keyboard,
        )
        return

    # --------------------------------------------------------
    # CLIENT
    # --------------------------------------------------------

    if role == "client":

        if text == "🛒 Buyurtma berish":
            return

        if text == "📋 Mening buyurtmalarim":
            await my_orders(update, context)
            return

        if text == "🔍 Buyurtma holati":
            await order_status(update, context)
            return

        if text == "❌ Bekor qilish":
            await cancel_client_order(update, context)
            return

        await client_feature(update, context)

    # --------------------------------------------------------
    # MASTER
    # --------------------------------------------------------

    elif role == "master":

        await master_feature(update, context)

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    elif role == "admin":

        await admin_feature(update, context)

    # --------------------------------------------------------
    # DISPATCHER
    # --------------------------------------------------------

    elif role == "dispatcher":

        await dispatcher_feature(update, context)


# ============================================================
# APPLICATION
# ============================================================

application = None


# ============================================================
# POST INIT
# ============================================================

async def post_init(app):

    global application

    application = app

    await init_db()

    logger.info("USTA 24 BOT STARTED")


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    logger.error(
        "Exception while handling update:",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global application

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN topilmadi!"
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # --------------------------------------------------------
    # CLIENT ORDER CONVERSATION
    # --------------------------------------------------------

    order_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🛒 Buyurtma berish$"),
                order_start,
            )
        ],
        states={

            C_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    order_name,
                )
            ],

            C_PHONE: [
                MessageHandler(
                    (filters.CONTACT | filters.TEXT)
                    & ~filters.COMMAND,
                    order_phone,
                )
            ],

            C_LOCATION: [
                MessageHandler(
                    filters.LOCATION | filters.TEXT,
                    order_location,
                )
            ],

            C_SERVICE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    order_service,
                )
            ],

            C_PHOTO: [
                MessageHandler(
                    filters.PHOTO | filters.TEXT,
                    order_photo,
                )
            ],

            C_ADDRESS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    order_address,
                )
            ],

            C_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    order_time,
                )
            ],

            C_COMMENT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    order_comment,
                )
            ],

            C_CONFIRM: [],

        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_conversation,
            ),
        ],

        allow_reentry=True,
    )

    # --------------------------------------------------------
    # MASTER REGISTRATION
    # --------------------------------------------------------

    master_conversation = ConversationHandler(
        entry_points=[
            CommandHandler(
                "master",
                master_start,
            )
        ],

        states={

            MASTER_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    master_register_name,
                )
            ],

            MASTER_PHONE: [
                MessageHandler(
                    filters.CONTACT | filters.TEXT,
                    master_register_phone,
                )
            ],

            MASTER_SERVICE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    master_register_service,
                )
            ],

            MASTER_AREA: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    master_register_area,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_conversation,
            )
        ],

        allow_reentry=True,
    )

    # --------------------------------------------------------
    # EMERGENCY
    # --------------------------------------------------------

    emergency_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🚨 24/7 Shosilinch rejim$"),
                emergency_start,
            )
        ],

        states={

            EMERGENCY_TYPE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    emergency_type,
                )
            ],

            EMERGENCY_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    emergency_time,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_conversation,
            )
        ],

        allow_reentry=True,
    )

    # --------------------------------------------------------
    # FINISH WORK
    # --------------------------------------------------------

    finish_conversation = ConversationHandler(
        entry_points=[],

        states={

            FINISH_PHOTO: [
                MessageHandler(
                    filters.PHOTO | filters.TEXT,
                    finish_photo,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_conversation,
            )
        ],

        allow_reentry=True,
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    application.add_handler(
        master_conversation
    )

    application.add_handler(
        order_conversation
    )

    application.add_handler(
        emergency_conversation
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            master_callback,
            pattern=r"^(accept|reject|photos):",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            work_callback,
            pattern=r"^(start_work|finish_work):",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            rating_callback,
            pattern=r"^rate:",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^(approve_master|reject_master):",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_order_callback,
            pattern=r"^admin_",
        )
    )

    # --------------------------------------------------------
    # CONTACT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            contact_handler,
        )
    )

    # --------------------------------------------------------
    # FINISH PHOTO
    # --------------------------------------------------------

    application.add_handler(
        finish_conversation
    )

    # --------------------------------------------------------
    # ALL OTHER MESSAGES
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            message_router,
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Starting USTA 24 ANDIJON..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
