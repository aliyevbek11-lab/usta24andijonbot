# ============================================================
# USTA 24 ANDIJON
# ONE BOT = CLIENT + MASTER + ADMIN + MASTERS GROUP
# PostgreSQL AUTO SETUP
#
# Python 3.11+
# python-telegram-bot 22.3
# asyncpg
#
# ENV:
# BOT_TOKEN
# DATABASE_URL
# ADMIN_ID
# DISPATCHER_ID       (optional)
# MASTERS_GROUP_ID    (optional)
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi")

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
    ORDER_SERVICE,
    ORDER_DESCRIPTION,
    ORDER_PHOTO,
    ORDER_ADDRESS,
    ORDER_TIME,
    ORDER_CONFIRM,
    MASTER_NAME,
    MASTER_PHONE,
) = range(8)

# ============================================================
# SERVICES
# ============================================================

SERVICES = [
    "🔧 Santexnika",
    "⚡ Elektrika",
    "🪑 Mebel yig‘ish",
    "🛠 Mebel ta’mirlash",
    "🚚 Ko‘chirish",
    "🚪 Eshik / qulf",
    "🎨 Ta’mirlash / bo‘yoq",
    "❄️ Konditsioner",
    "🔥 Gaz xizmati",
    "🧰 Boshqa xizmat",
]

# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    logger.info("PostgreSQL ulanish...")

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'client',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_orders (
                id BIGSERIAL PRIMARY KEY,

                customer_id BIGINT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',

                service TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                order_time TEXT NOT NULL DEFAULT '',

                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,

                status TEXT NOT NULL DEFAULT 'new',

                master_id BIGINT,
                master_name TEXT NOT NULL DEFAULT '',
                master_phone TEXT NOT NULL DEFAULT '',

                price NUMERIC(12,2) NOT NULL DEFAULT 0,

                emergency BOOLEAN NOT NULL DEFAULT FALSE,
                emergency_percent INTEGER NOT NULL DEFAULT 0,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """)

        # ----------------------------------------------------
        # PHOTOS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_order_photos (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                photo_type TEXT NOT NULL DEFAULT 'problem',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ----------------------------------------------------
        # RATINGS
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                CONSTRAINT u24_rating_value
                CHECK (rating >= 1 AND rating <= 5)
            )
        """)

        # ----------------------------------------------------
        # SERVICES
        # ----------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS u24_services (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        for service in SERVICES:
            await conn.execute(
                """
                INSERT INTO u24_services(name)
                VALUES($1)
                ON CONFLICT(name) DO NOTHING
                """,
                service,
            )

    logger.info("PostgreSQL tayyor.")


# ============================================================
# USER FUNCTIONS
# ============================================================

async def ensure_user(tg_user):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_users
            (
                telegram_id,
                full_name,
                username
            )
            VALUES($1, $2, $3)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                updated_at = NOW()
            """,
            tg_user.id,
            tg_user.full_name or "",
            tg_user.username or "",
        )


async def get_user(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM u24_users
            WHERE telegram_id = $1
            """,
            user_id,
        )


async def set_role(user_id, role):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_users
            SET role = $1,
                updated_at = NOW()
            WHERE telegram_id = $2
            """,
            role,
            user_id,
        )


async def save_phone(user_id, phone):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_users
            SET phone = $1,
                updated_at = NOW()
            WHERE telegram_id = $2
            """,
            phone,
            user_id,
        )


# ============================================================
# ORDER FUNCTIONS
# ============================================================

async def create_order(
    customer_id,
    customer_name,
    customer_phone,
    service,
    description,
    address,
    order_time,
    emergency=False,
    emergency_percent=0,
    latitude=None,
    longitude=None,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO u24_orders
            (
                customer_id,
                customer_name,
                customer_phone,
                service,
                description,
                address,
                order_time,
                emergency,
                emergency_percent,
                latitude,
                longitude
            )
            VALUES
            (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11
            )
            RETURNING id
            """,
            customer_id,
            customer_name,
            customer_phone,
            service,
            description,
            address,
            order_time,
            emergency,
            emergency_percent,
            latitude,
            longitude,
        )

        return row["id"]


async def add_photo(order_id, file_id, photo_type="problem"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO u24_order_photos
            (
                order_id,
                file_id,
                photo_type
            )
            VALUES($1,$2,$3)
            """,
            order_id,
            file_id,
            photo_type,
        )


async def get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM u24_orders
            WHERE id = $1
            """,
            order_id,
        )


async def update_order_status(order_id, status):
    async with db_pool.acquire() as conn:

        if status == "accepted":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1,
                    accepted_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )

        elif status == "started":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1,
                    started_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )

        elif status == "completed":
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1,
                    completed_at = NOW()
                WHERE id = $2
                """,
                status,
                order_id,
            )

        else:
            await conn.execute(
                """
                UPDATE u24_orders
                SET status = $1
                WHERE id = $2
                """,
                status,
                order_id,
            )


async def assign_master(order_id, master_id, master_name, master_phone):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE u24_orders
            SET master_id = $1,
                master_name = $2,
                master_phone = $3,
                status = 'accepted',
                accepted_at = NOW()
            WHERE id = $4
            """,
            master_id,
            master_name,
            master_phone,
            order_id,
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
            ["📌 Eslatmalarim", "🗺 Yaqin atrofdagi ustalar"],
            ["📅 Yozilma", "🎁 Loyallik va bonuslar"],
            ["🤖 AI yordamchi", "⚙️ Sozlamalar"],
            ["📊 Mening statistikam", "🏷 Chegirmalar"],
            ["📞 Tez yordam", "🔔 Bildirishnomalar"],
            ["📁 Mening hujjatlarim", "🕊 Do‘stga tavsiya"],
            ["📞 Dispetcher", "🚨 24/7 Shoshilinch"],
        ],
        resize_keyboard=True,
    )


def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["📋 Yangi buyurtmalar", "✅ Mening faol"],
            ["⏳ Tarix", "💰 Ish haqi"],
            ["⭐ Reytingim", "📅 Kunlik jadval"],
            ["🔔 Mijozlar bilan bog‘lanish", "📸 Galereya"],
            ["🛠 Xizmatlarim", "📊 Ish statistikasi"],
            ["🏷 Mening narxlarim", "📍 Ish hududim"],
            ["📅 Dam olish kunlari", "🔔 Bildirishnoma"],
            ["📝 Reytingni oshirish", "🎁 Usta bonuslari"],
            ["🤖 AI yordamchi", "📞 Texnik yordam"],
            ["📢 E’lonlar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcher", "🚨 24/7 Shoshilinch"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "🛠 Buyurtmalar"],
            ["👨‍🔧 Ustalar", "⭐ Reytinglar"],
            ["🎁 Bonuslar", "💰 To‘lovlar"],
            ["🏷 Chegirmalar", "🛠 Xizmat turlari"],
            ["📊 Statistika", "📢 E’lonlar"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
            ["📸 Galereya", "📱 Botni boshqarish"],
            ["📞 Qo‘llab-quvvatlash", "🚨 24/7 Rejim"],
        ],
        resize_keyboard=True,
    )


def services_keyboard():
    buttons = []

    for service in SERVICES:
        buttons.append([KeyboardButton(service)])

    buttons.append([KeyboardButton("⬅️ Orqaga")])

    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📱 Telefon raqamni yuborish",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user

        await ensure_user(user)

        # ADMIN
        if ADMIN_ID and user.id == ADMIN_ID:
            await set_role(user.id, "admin")

            await update.message.reply_text(
                "👑 USTA 24 ANDIJON\n\n"
                "Админ панелига хуш келибсиз!",
                reply_markup=admin_menu(),
            )
            return

        # Existing user
        db_user = await get_user(user.id)

        if db_user and db_user["role"] == "master":
            await update.message.reply_text(
                "👨‍🔧 USTA 24 ANDIJON\n\n"
                "Usta paneliga xush kelibsiz!",
                reply_markup=master_menu(),
            )
            return

        await set_role(user.id, "client")

        await update.message.reply_text(
            "🏠 USTA 24 ANDIJON\n\n"
            "Assalomu alaykum!\n"
            "Siz mijoz sifatida kirdingiz.\n\n"
            "🛠 Uyga usta chaqiring.\n"
            "⚡ Tez va qulay xizmat.",
            reply_markup=client_menu(),
        )

    except Exception:
        logger.exception("START ERROR")

        await update.message.reply_text(
            "⚠️ Texnik xatolik yuz berdi.\n"
            "Iltimos, qayta urinib ko‘ring."
        )


# ============================================================
# ORDER START
# ============================================================

async def order_start(update, context):
    user = update.effective_user

    db_user = await get_user(user.id)

    if not db_user:
        await ensure_user(user)
        db_user = await get_user(user.id)

    if not db_user["phone"]:
        context.user_data["waiting_phone"] = True

        await update.message.reply_text(
            "📱 Buyurtma berish uchun telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard(),
        )

        return

    context.user_data["order_phone"] = db_user["phone"]

    await update.message.reply_text(
        "🛠 Xizmat turini tanlang:",
        reply_markup=services_keyboard(),
    )

    context.user_data["order_step"] = "service"


# ============================================================
# ORDER TEXT FLOW
# ============================================================

async def handle_order_text(update, context):
    text = update.message.text
    user = update.effective_user

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    if context.user_data.get("waiting_phone"):

        if update.message.contact:
            phone = update.message.contact.phone_number

        else:
            phone = text.strip()

        await save_phone(user.id, phone)

        context.user_data["order_phone"] = phone
        context.user_data["waiting_phone"] = False
        context.user_data["order_step"] = "service"

        await update.message.reply_text(
            "✅ Telefon saqlandi.\n\n"
            "🛠 Xizmat turini tanlang:",
            reply_markup=services_keyboard(),
        )

        return

    # --------------------------------------------------------
    # SERVICE
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "service":

        if text == "⬅️ Orqaga":
            context.user_data.clear()

            await update.message.reply_text(
                "Bosh menyu:",
                reply_markup=client_menu(),
            )
            return

        context.user_data["service"] = text
        context.user_data["order_step"] = "description"

        await update.message.reply_text(
            "📝 Muammo haqida qisqacha yozing:\n\n"
            "Masalan:\n"
            "«Rozetka ishlamayapti»"
        )

        return

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "description":

        context.user_data["description"] = text
        context.user_data["order_step"] = "photo"

        await update.message.reply_text(
            "📸 Muammo rasmini yuboring.\n\n"
            "Agar rasm bo‘lmasa, «O‘tkazib yuborish» deb yozing."
        )

        return

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "photo":

        if text.lower() in [
            "o‘tkazib yuborish",
            "otkazib yuborish",
            "o'tkazib yuborish",
            "skip",
        ]:
            context.user_data["order_step"] = "address"

            await update.message.reply_text(
                "📍 Manzilingizni yozing:"
            )

            return

        # If text is sent instead of photo
        await update.message.reply_text(
            "📸 Iltimos, rasm yuboring yoki "
            "«O‘tkazib yuborish» deb yozing."
        )

        return

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "address":

        context.user_data["address"] = text
        context.user_data["order_step"] = "time"

        await update.message.reply_text(
            "🕐 Qachon usta kerak?\n\n"
            "Masalan: Bugun 15:00"
        )

        return

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "time":

        context.user_data["order_time"] = text
        context.user_data["order_step"] = "confirm"

        service = context.user_data.get("service", "")
        description = context.user_data.get("description", "")
        address = context.user_data.get("address", "")

        await update.message.reply_text(
            "📋 BUYURTMA\n\n"
            f"🛠 Xizmat: {service}\n"
            f"📝 Muammo: {description}\n"
            f"📍 Manzil: {address}\n"
            f"🕐 Vaqt: {text}\n\n"
            "Buyurtmani tasdiqlaysizmi?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ TASDIQLASH",
                            callback_data="order_confirm",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ BEKOR QILISH",
                            callback_data="order_cancel",
                        )
                    ],
                ]
            ),
        )

        return

    # ========================================================
    # MASTER MENU
    # ========================================================

    db_user = await get_user(user.id)

    if db_user and db_user["role"] == "master":

        await master_text(update, context)
        return

    # ========================================================
    # ADMIN MENU
    # ========================================================

    if ADMIN_ID and user.id == ADMIN_ID:

        await admin_text(update, context)
        return

    # ========================================================
    # CLIENT MENU
    # ========================================================

    await client_text(update, context)


# ============================================================
# PHOTO HANDLER
# ============================================================

async def photo_handler(update, context):

    if context.user_data.get("order_step") != "photo":
        return

    photo = update.message.photo[-1]

    context.user_data["problem_photo"] = photo.file_id
    context.user_data["order_step"] = "address"

    await update.message.reply_text(
        "✅ Rasm qabul qilindi.\n\n"
        "📍 Endi manzilingizni yozing:"
    )


# ============================================================
# ORDER CALLBACKS
# ============================================================

async def order_confirm_callback(update, context):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    try:

        db_user = await get_user(user.id)

        order_id = await create_order(
            customer_id=user.id,
            customer_name=user.full_name,
            customer_phone=db_user["phone"] or "",
            service=context.user_data.get("service", ""),
            description=context.user_data.get("description", ""),
            address=context.user_data.get("address", ""),
            order_time=context.user_data.get("order_time", ""),
        )

        photo_id = context.user_data.get("problem_photo")

        if photo_id:
            await add_photo(
                order_id,
                photo_id,
                "problem",
            )

        await query.edit_message_text(
            f"✅ BUYURTMA QABUL QILINDI!\n\n"
            f"🆔 Buyurtma №{order_id}\n"
            f"🛠 {context.user_data.get('service', '')}\n"
            f"📍 {context.user_data.get('address', '')}\n"
            f"🕐 {context.user_data.get('order_time', '')}\n\n"
            "👨‍🔧 Ustalar qidirilmoqda..."
        )

        await send_order_to_group(order_id)

        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🆕 YANGI BUYURTMA!\n\n"
                    f"🆔 №{order_id}\n"
                    f"👤 {user.full_name}\n"
                    f"🛠 {context.user_data.get('service', '')}\n"
                    f"📍 {context.user_data.get('address', '')}",
                )
            except Exception:
                logger.exception("Admin notification error")

        context.user_data.clear()

    except Exception:
        logger.exception("ORDER CREATE ERROR")

        await query.message.reply_text(
            "⚠️ Texnik xatolik yuz berdi.\n"
            "Buyurtma yaratilmadi."
        )


async def order_cancel_callback(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data.clear()

    await query.edit_message_text(
        "❌ Buyurtma bekor qilindi."
    )

    await query.message.reply_text(
        "Bosh menyu:",
        reply_markup=client_menu(),
    )


# ============================================================
# SEND GROUP
# ============================================================

async def send_order_to_group(order_id):

    if not MASTERS_GROUP_ID:
        logger.warning(
            "MASTERS_GROUP_ID mavjud emas."
        )
        return

    order = await get_order(order_id)

    if not order:
        return

    text = (
        "🆕 YANGI BUYURTMA!\n\n"
        f"🆔 #{order['id']}\n"
        f"👤 Mijoz: {order['customer_name']}\n"
        f"📞 Telefon: {order['customer_phone']}\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"📝 Muammo: {order['description']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"🕐 Vaqt: {order['order_time']}\n"
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
                    "🔧 Ishni boshlash",
                    callback_data=f"startwork:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Ishni yakunlash",
                    callback_data=f"complete:{order_id}",
                )
            ],
        ]
    )

    return text, keyboard


# ============================================================
# MASTER CALLBACK
# ============================================================

async def master_callback(update, context):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    db_user = await get_user(user.id)

    if not db_user or db_user["role"] != "master":

        await query.answer(
            "❌ Siz usta sifatida ro‘yxatdan o‘tmagansiz.",
            show_alert=True,
        )

        return

    data = query.data

    try:

        action, order_id_text = data.split(":", 1)

        order_id = int(order_id_text)

        order = await get_order(order_id)

        if not order:
            await query.answer(
                "Buyurtma topilmadi.",
                show_alert=True,
            )
            return

        if action == "accept":

            if order["status"] != "new":

                await query.answer(
                    "Bu buyurtmani boshqa usta olgan.",
                    show_alert=True,
                )
                return

            await assign_master(
                order_id,
                user.id,
                user.full_name,
                db_user["phone"] or "",
            )

            await query.edit_message_text(
                f"✅ BUYURTMA QABUL QILINDI\n\n"
                f"🆔 #{order_id}\n"
                f"👨‍🔧 Usta: {user.full_name}\n"
                f"🛠 {order['service']}\n"
                f"📍 {order['address']}"
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"✅ Buyurtmangiz qabul qilindi!\n\n"
                    f"🆔 #{order_id}\n"
                    f"👨‍🔧 Usta: {user.full_name}\n"
                    f"📞 {db_user['phone']}\n\n"
                    "Usta tez orada bog‘lanadi.",
                )
            except Exception:
                logger.exception(
                    "Customer notification error"
                )

        elif action == "reject":

            await update_order_status(
                order_id,
                "rejected",
            )

            await query.edit_message_text(
                f"❌ #{order_id} rad etildi.\n"
                "🔄 Boshqa usta ko‘rib chiqishi mumkin."
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"❌ #{order_id} buyurtmangizni "
                    "ushbu usta qabul qilmadi.\n\n"
                    "🔄 Boshqa usta qidirilmoqda.",
                )
            except Exception:
                pass

        elif action == "startwork":

            if order["master_id"] != user.id:
                await query.answer(
                    "Bu buyurtma sizga tegishli emas.",
                    show_alert=True,
                )
                return

            await update_order_status(
                order_id,
                "started",
            )

            await query.message.reply_text(
                f"🔧 #{order_id} ish boshlandi!\n"
                f"👨‍🔧 Usta: {user.full_name}"
            )

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"🔧 Ish boshlandi!\n\n"
                    f"🆔 #{order_id}\n"
                    f"👨‍🔧 Usta: {user.full_name}"
                )
            except Exception:
                pass

        elif action == "complete":

            if order["master_id"] != user.id:
                await query.answer(
                    "Bu buyurtma sizga tegishli emas.",
                    show_alert=True,
                )
                return

            await update_order_status(
                order_id,
                "completed",
            )

            await query.message.reply_text(
                f"✅ #{order_id} buyurtma yakunlandi!\n\n"
                "📸 Natija rasmini yuboring."
            )

            context.user_data["complete_order"] = order_id

            try:
                await context.bot.send_message(
                    order["customer_id"],
                    f"✅ Ish yakunlandi!\n\n"
                    f"🆔 #{order_id}\n"
                    f"👨‍🔧 Usta: {user.full_name}\n\n"
                    "💵 To‘lov: Faqat naqd, ish tugagandan keyin.\n\n"
                    "⭐ Ustaga reyting qoldirishingiz mumkin."
                )
            except Exception:
                pass

    except Exception:
        logger.exception("MASTER CALLBACK ERROR")

        await query.message.reply_text(
            "⚠️ Texnik xatolik yuz berdi."
        )


# ============================================================
# CLIENT MENU
# ============================================================

async def client_text(update, context):

    text = update.message.text
    user = update.effective_user

    if text == "🛒 Buyurtma berish":

        await order_start(update, context)
        return

    if text == "📋 Mening buyurtmalarim":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT id, service, status, address, created_at
                FROM u24_orders
                WHERE customer_id = $1
                ORDER BY id DESC
                LIMIT 20
                """,
                user.id,
            )

        if not rows:

            await update.message.reply_text(
                "📋 Sizda hali buyurtmalar yo‘q."
            )
            return

        text_out = "📋 MENING BUYURTMALARIM\n\n"

        for row in rows:

            text_out += (
                f"🆔 #{row['id']}\n"
                f"🛠 {row['service']}\n"
                f"📍 {row['address']}\n"
                f"📌 Holat: {row['status']}\n"
                f"📅 {row['created_at']:%d.%m.%Y %H:%M}\n\n"
            )

        await update.message.reply_text(text_out)
        return

    if text == "🔍 Buyurtma holati":

        await update.message.reply_text(
            "🔍 Buyurtma raqamini yozing.\n\n"
            "Masalan: 125"
        )

        context.user_data["checking_order"] = True
        return

    if context.user_data.get("checking_order"):

        try:
            order_id = int(text)

            order = await get_order(order_id)

            if not order:

                await update.message.reply_text(
                    "❌ Buyurtma topilmadi."
                )
                return

            await update.message.reply_text(
                f"🔍 BUYURTMA #{order_id}\n\n"
                f"🛠 Xizmat: {order['service']}\n"
                f"📍 Manzil: {order['address']}\n"
                f"🕐 Vaqt: {order['order_time']}\n"
                f"📌 Holat: {order['status']}\n"
                f"👨‍🔧 Usta: {order['master_name'] or 'Hali biriktirilmagan'}"
            )

            context.user_data["checking_order"] = False

        except ValueError:

            await update.message.reply_text(
                "❌ Faqat buyurtma raqamini kiriting."
            )

        return

    if text == "❌ Bekor qilish":

        await update.message.reply_text(
            "❌ Bekor qilmoqchi bo‘lgan buyurtma raqamini yozing."
        )

        context.user_data["cancel_order"] = True
        return

    if context.user_data.get("cancel_order"):

        try:

            order_id = int(text)

            order = await get_order(order_id)

            if not order:

                await update.message.reply_text(
                    "❌ Buyurtma topilmadi."
                )
                return

            if order["customer_id"] != user.id:

                await update.message.reply_text(
                    "❌ Bu sizning buyurtmangiz emas."
                )
                return

            await update_order_status(
                order_id,
                "cancelled",
            )

            await update.message.reply_text(
                f"❌ #{order_id} buyurtma bekor qilindi.",
                reply_markup=client_menu(),
            )

            context.user_data["cancel_order"] = False

        except ValueError:

            await update.message.reply_text(
                "❌ Buyurtma raqamini kiriting."
            )

        return

    if text == "🔁 Qayta buyurtma":

        await update.message.reply_text(
            "🔁 Yangi buyurtma berishni boshlaymiz."
        )

        await order_start(update, context)
        return

    if text == "👨‍🔧 Mening ustalarim":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    master_id,
                    master_name,
                    master_phone
                FROM u24_orders
                WHERE customer_id = $1
                  AND master_id IS NOT NULL
                ORDER BY master_name
                """,
                user.id,
            )

        if not rows:

            await update.message.reply_text(
                "👨‍🔧 Hali sizga usta biriktirilmagan."
            )
            return

        out = "👨‍🔧 MENING USTALARIM\n\n"

        for row in rows:

            out += (
                f"👨‍🔧 {row['master_name']}\n"
                f"📞 {row['master_phone']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "⭐ Reytingim":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(rating), 0) AS avg
                FROM u24_ratings
                WHERE customer_id = $1
                """,
                user.id,
            )

        await update.message.reply_text(
            f"⭐ SIZNING REYTINGINGIZ\n\n"
            f"⭐ O‘rtacha: {float(row['avg']):.1f}\n"
            f"📝 Sharhlar: {row['total']}"
        )
        return

    if text == "📝 Sharh qoldirish":

        await update.message.reply_text(
            "📝 Sharh qoldirish funksiyasi.\n\n"
            "Avval yakunlangan buyurtmangizni tanlang."
        )
        return

    if text == "📌 Eslatmalarim":

        await update.message.reply_text(
            "📌 Hozircha eslatmalar mavjud emas."
        )
        return

    if text == "🗺 Yaqin atrofdagi ustalar":

        await update.message.reply_text(
            "🗺 Yaqin atrofdagi ustalarni aniqlash "
            "uchun geolokatsiya funksiyasi ishlatiladi."
        )
        return

    if text == "📅 Yozilma":

        await update.message.reply_text(
            "📅 Bron qilish: buyurtma berishda "
            "kerakli vaqtni ko‘rsating."
        )
        return

    if text == "🎁 Loyallik va bonuslar":

        await update.message.reply_text(
            "🎁 Loyallik dasturi\n\n"
            "Har bir yakunlangan buyurtma sizga bonus beradi."
        )
        return

    if text == "🤖 AI yordamchi":

        await update.message.reply_text(
            "🤖 AI yordamchi tez orada ishga tushadi."
        )
        return

    if text == "⚙️ Sozlamalar":

        await update.message.reply_text(
            "⚙️ Sozlamalar\n\n"
            "📱 Telefon raqamingizni yangilash mumkin."
        )
        return

    if text == "📊 Mening statistikam":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER
                    (WHERE status='completed') AS completed,
                    COUNT(*) FILTER
                    (WHERE status='cancelled') AS cancelled
                FROM u24_orders
                WHERE customer_id = $1
                """,
                user.id,
            )

        await update.message.reply_text(
            f"📊 STATISTIKA\n\n"
            f"📋 Jami: {row['total']}\n"
            f"✅ Tugallangan: {row['completed']}\n"
            f"❌ Bekor qilingan: {row['cancelled']}"
        )
        return

    if text == "🏷 Chegirmalar":

        await update.message.reply_text(
            "🏷 Hozircha faol chegirmalar yo‘q."
        )
        return

    if text == "📞 Tez yordam":

        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"{DISPATCHER_PHONE}\n\n"
            "🕐 24/7"
        )
        return

    if text == "🔔 Bildirishnomalar":

        await update.message.reply_text(
            "🔔 Bildirishnomalar yoqilgan."
        )
        return

    if text == "📁 Mening hujjatlarim":

        await update.message.reply_text(
            "📁 Hujjatlar bo‘limi."
        )
        return

    if text == "🕊 Do‘stga tavsiya":

        await update.message.reply_text(
            "🕊 USTA 24 ANDIJON\n\n"
            "Do‘stlaringizga bizni tavsiya qiling!"
        )
        return

    if text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"{DISPATCHER_PHONE}\n"
            "🕐 24/7\n"
            "📍 Andijon shahar"
        )
        return

    if text == "🚨 24/7 Shoshilinch":

        await update.message.reply_text(
            "🚨 24/7 SHOSHILINCH REJIM\n\n"
            "🔴 HOZIR — +20%\n"
            "🟡 30 daqiqada — +10%\n"
            "🟢 1 soatda — oddiy narx\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "💵 To‘lov: faqat naqd, ish tugagandan keyin."
        )
        return

    await update.message.reply_text(
        "🏠 Bosh menyu:",
        reply_markup=client_menu(),
    )


# ============================================================
# MASTER MENU
# ============================================================

async def master_text(update, context):

    text = update.message.text
    user = update.effective_user

    if text == "📋 Yangi buyurtmalar":

        if not MASTERS_GROUP_ID:

            await update.message.reply_text(
                "⚠️ MASTERS_GROUP_ID sozlanmagan."
            )
            return

        await update.message.reply_text(
            "📋 Yangi buyurtmalar ustalar guruhida chiqadi."
        )
        return

    if text == "✅ Mening faol":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT *
                FROM u24_orders
                WHERE master_id = $1
                  AND status IN ('accepted','started')
                ORDER BY id DESC
                """,
                user.id,
            )

        if not rows:

            await update.message.reply_text(
                "✅ Faol buyurtmalar yo‘q."
            )
            return

        out = "✅ FAOL BUYURTMALAR\n\n"

        for row in rows:

            out += (
                f"🆔 #{row['id']}\n"
                f"🛠 {row['service']}\n"
                f"📍 {row['address']}\n"
                f"📌 {row['status']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "⏳ Tarix":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT *
                FROM u24_orders
                WHERE master_id = $1
                  AND status = 'completed'
                ORDER BY id DESC
                LIMIT 30
                """,
                user.id,
            )

        if not rows:

            await update.message.reply_text(
                "⏳ Tugallangan ishlar yo‘q."
            )
            return

        out = "⏳ ISH TARIXI\n\n"

        for row in rows:

            out += (
                f"🆔 #{row['id']}\n"
                f"🛠 {row['service']}\n"
                f"💰 {row['price']} so‘m\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "💰 Ish haqi":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(price),0) AS money
                FROM u24_orders
                WHERE master_id = $1
                  AND status = 'completed'
                """,
                user.id,
            )

        await update.message.reply_text(
            f"💰 ISH HAQI\n\n"
            f"📋 Ishlar: {row['total']}\n"
            f"💵 Jami: {row['money']} so‘m"
        )
        return

    if text == "⭐ Reytingim":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(AVG(rating),0) AS avg
                FROM u24_ratings
                WHERE master_id = $1
                """,
                user.id,
            )

        await update.message.reply_text(
            f"⭐ USTA REYTINGI\n\n"
            f"⭐ {float(row['avg']):.2f}\n"
            f"📝 {row['total']} ta baho"
        )
        return

    if text == "📊 Ish statistikasi":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER
                    (WHERE status='completed') AS completed,
                    COUNT(*) FILTER
                    (WHERE status='cancelled') AS cancelled
                FROM u24_orders
                WHERE master_id = $1
                """,
                user.id,
            )

        await update.message.reply_text(
            f"📊 ISH STATISTIKASI\n\n"
            f"📋 Jami: {row['total']}\n"
            f"✅ Tugallangan: {row['completed']}\n"
            f"❌ Bekor qilingan: {row['cancelled']}"
        )
        return

    if text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 Dispetcher: {DISPATCHER_PHONE}\n"
            "🕐 24/7"
        )
        return

    if text == "🚨 24/7 Shoshilinch":

        await update.message.reply_text(
            f"🚨 24/7 SHOSHILINCH\n\n"
            f"📞 {DISPATCHER_PHONE}\n\n"
            "🔴 Hozir: +20%\n"
            "🟡 30 daqiqa: +10%\n"
            "🟢 1 soat: oddiy narx"
        )
        return

    await update.message.reply_text(
        "👨‍🔧 Usta menyusi:",
        reply_markup=master_menu(),
    )


# ============================================================
# ADMIN
# ============================================================

async def admin_text(update, context):

    text = update.message.text

    if text == "👥 Foydalanuvchilar":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER
                    (WHERE role='client') AS clients,
                    COUNT(*) FILTER
                    (WHERE role='master') AS masters,
                    COUNT(*) FILTER
                    (WHERE role='admin') AS admins
                FROM u24_users
                """
            )

        await update.message.reply_text(
            f"👥 FOYDALANUVCHILAR\n\n"
            f"👤 Jami: {row['total']}\n"
            f"🛒 Mijozlar: {row['clients']}\n"
            f"👨‍🔧 Ustalar: {row['masters']}\n"
            f"👑 Adminlar: {row['admins']}"
        )
        return

    if text == "🛠 Buyurtmalar":

        async with db_pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER
                    (WHERE status='new') AS new,
                    COUNT(*) FILTER
                    (WHERE status='accepted') AS accepted,
                    COUNT(*) FILTER
                    (WHERE status='started') AS started,
                    COUNT(*) FILTER
                    (WHERE status='completed') AS completed,
                    COUNT(*) FILTER
                    (WHERE status='cancelled') AS cancelled
                FROM u24_orders
                """
            )

        await update.message.reply_text(
            f"🛠 BUYURTMALAR\n\n"
            f"📋 Jami: {row['total']}\n"
            f"🆕 Yangi: {row['new']}\n"
            f"✅ Qabul qilingan: {row['accepted']}\n"
            f"🔧 Jarayonda: {row['started']}\n"
            f"🏁 Tugagan: {row['completed']}\n"
            f"❌ Bekor: {row['cancelled']}"
        )
        return

    if text == "👨‍🔧 Ustalar":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT
                    telegram_id,
                    full_name,
                    phone
                FROM u24_users
                WHERE role='master'
                ORDER BY full_name
                """
            )

        if not rows:

            await update.message.reply_text(
                "👨‍🔧 Hali ustalar yo‘q."
            )
            return

        out = "👨‍🔧 USTALAR\n\n"

        for row in rows:

            out += (
                f"👨‍🔧 {row['full_name']}\n"
                f"🆔 {row['telegram_id']}\n"
                f"📞 {row['phone']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "⭐ Reytinglar":

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT
                    master_id,
                    COUNT(*) AS total,
                    AVG(rating) AS avg
                FROM u24_ratings
                GROUP BY master_id
                ORDER BY avg DESC
                LIMIT 10
                """
            )

        if not rows:

            await update.message.reply_text(
                "⭐ Hali reytinglar yo‘q."
            )
            return

        out = "⭐ TOP USTALAR\n\n"

        for i, row in enumerate(rows, 1):

            out += (
                f"{i}. 👨‍🔧 {row['master_id']}\n"
                f"⭐ {float(row['avg']):.2f}\n"
                f"📝 {row['total']}\n\n"
            )

        await update.message.reply_text(out)
        return

    if text == "📊 Statistika":

        async with db_pool.acquire() as conn:

            users = await conn.fetchval(
                "SELECT COUNT(*) FROM u24_users"
            )

            orders = await conn.fetchval(
                "SELECT COUNT(*) FROM u24_orders"
            )

            completed = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM u24_orders
                WHERE status='completed'
                """
            )

            money = await conn.fetchval(
                """
                SELECT COALESCE(SUM(price),0)
                FROM u24_orders
                WHERE status='completed'
                """
            )

        await update.message.reply_text(
            f"📊 USTA 24 STATISTIKA\n\n"
            f"👥 Foydalanuvchilar: {users}\n"
            f"🛠 Buyurtmalar: {orders}\n"
            f"✅ Tugallangan: {completed}\n"
            f"💰 Tushum: {money} so‘m"
        )
        return

    if text == "📞 Dispetcher":

        await update.message.reply_text(
            f"📞 DISPETCHER\n\n"
            f"{DISPATCHER_PHONE}\n"
            "🕐 24/7"
        )
        return

    if text == "🚨 24/7 Rejim":

        await update.message.reply_text(
            "🚨 24/7 SHOSHILINCH REJIM\n\n"
            "🔴 HOZIR +20%\n"
            "🟡 30 DAQIQA +10%\n"
            "🟢 1 SOAT oddiy narx\n\n"
            f"📞 {DISPATCHER_PHONE}"
        )
        return

    await update.message.reply_text(
        "👑 Admin panel:",
        reply_markup=admin_menu(),
    )


# ============================================================
# MASTER REGISTRATION
# ============================================================

async def master_command(update, context):

    user = update.effective_user

    await ensure_user(user)

    await update.message.reply_text(
        "👨‍🔧 USTA RO‘YXATDAN O‘TISH\n\n"
        "Ismingizni yozing:"
    )

    context.user_data["master_register"] = "name"


async def master_register_handler(update, context):

    state = context.user_data.get("master_register")

    if not state:
        return False

    user = update.effective_user

    if state == "name":

        context.user_data["master_name"] = update.message.text

        context.user_data["master_register"] = "phone"

        await update.message.reply_text(
            "📞 Telefon raqamingizni yuboring:",
            reply_markup=phone_keyboard(),
        )

        return True

    if state == "phone":

        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = update.message.text

        await save_phone(user.id, phone)

        await set_role(
            user.id,
            "master",
        )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Siz USTA sifatida ro‘yxatdan o‘tdingiz!\n\n"
            "Endi guruhdagi buyurtmalarni qabul qilishingiz mumkin.",
            reply_markup=master_menu(),
        )

        return True

    return False


# ============================================================
# GROUP ORDERS
# ============================================================

async def group_message(update, context):

    if not update.effective_chat:
        return

    if update.effective_chat.id != MASTERS_GROUP_ID:
        return

    # Only process commands/callbacks in group.
    # Orders are sent automatically by the bot.


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    logger.exception(
        "Unhandled exception",
        exc_info=context.error,
    )

    try:

        if update and update.effective_message:

            await update.effective_message.reply_text(
                "⚠️ Texnik xatolik yuz berdi.\n"
                "Iltimos, qayta urinib ko‘ring."
            )

    except Exception:
        pass


# ============================================================
# MAIN
# ============================================================

async def post_init(application):

    await init_db()

    logger.info(
        "USTA 24 ANDIJON BOT IS READY"
    )


async def post_shutdown(application):

    global db_pool

    if db_pool:

        await db_pool.close()

        logger.info(
            "PostgreSQL pool yopildi."
        )


def main():

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
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
            "master",
            master_command,
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            order_confirm_callback,
            pattern=r"^order_confirm$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            order_cancel_callback,
            pattern=r"^order_cancel$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            master_callback,
            pattern=r"^(accept|reject|startwork|complete):\d+$",
        )
    )

    # --------------------------------------------------------
    # PHOTOS
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_handler,
        )
    )

    # --------------------------------------------------------
    # CONTACTS + TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            handle_order_text,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_order_text,
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Bot polling started..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
