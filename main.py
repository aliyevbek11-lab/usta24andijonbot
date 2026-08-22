# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
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
import threading
from datetime import datetime
from typing import Optional

import asyncpg

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
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
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

MASTERS_GROUP_ID = int(
    os.getenv("MASTERS_GROUP_ID", "0").strip() or "0"
)

DISPATCHER_ID = int(
    os.getenv("DISPATCHER_ID", "0").strip() or "0"
)

# ADMIN_ID yoki ADMIN_IDS
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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("USTA24")


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


@app.get("/")
def home():
    return "USTA 24 ANDIJON BOT IS RUNNING"


@app.get("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# ============================================================
# DATABASE
# ============================================================

db_pool: Optional[asyncpg.Pool] = None


async def init_db():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL ENV topilmadi!"
        )

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                full_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                role TEXT DEFAULT 'mijoz',
                created_at TIMESTAMP DEFAULT NOW(),
                is_blocked BOOLEAN DEFAULT FALSE,
                block_reason TEXT DEFAULT ''
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS masters (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id)
                    ON DELETE CASCADE,
                services TEXT DEFAULT '',
                rating NUMERIC DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                total_earnings BIGINT DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                order_number TEXT UNIQUE NOT NULL,
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
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY,
                order_id INTEGER,
                from_user_id BIGINT,
                to_user_id BIGINT,
                rating INTEGER,
                review TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

    logger.info("PostgreSQL database initialized")


# ============================================================
# DB HELPERS
# ============================================================

async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM users
            WHERE user_id=$1
            """,
            user_id,
        )


async def save_user(
    user_id: int,
    full_name: str,
    phone: str,
    role: str,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users
            (
                user_id,
                full_name,
                phone,
                role
            )
            VALUES ($1,$2,$3,$4)
            ON CONFLICT(user_id)
            DO UPDATE SET
                full_name=EXCLUDED.full_name,
                phone=EXCLUDED.phone,
                role=EXCLUDED.role
            """,
            user_id,
            full_name,
            phone,
            role,
        )


async def create_master(user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO masters(user_id)
            VALUES($1)
            ON CONFLICT(user_id) DO NOTHING
            """,
            user_id,
        )


async def get_master(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE user_id=$1
            """,
            user_id,
        )


async def get_active_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                u.user_id,
                u.full_name,
                u.phone,
                m.services,
                m.rating,
                m.total_orders
            FROM users u
            JOIN masters m
                ON m.user_id=u.user_id
            WHERE u.role='usta'
              AND m.is_active=TRUE
            ORDER BY m.rating DESC
            """
        )


async def get_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            """,
            order_id,
        )


async def get_order_by_number(order_number: str):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE order_number=$1
            """,
            order_number,
        )


async def get_user_orders(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE user_id=$1
            ORDER BY id DESC
            LIMIT 20
            """,
            user_id,
        )


async def get_master_orders(master_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE master_id=$1
            ORDER BY id DESC
            LIMIT 50
            """,
            master_id,
        )


async def get_new_orders():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE status IN
            ('yangi','taklif_yuborildi')
            ORDER BY id DESC
            LIMIT 50
            """
        )


async def get_all_orders():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM orders
            ORDER BY id DESC
            LIMIT 100
            """
        )


async def update_order(
    order_id: int,
    status: str,
    master_id=None,
    master_name=None,
):
    async with db_pool.acquire() as conn:

        if master_id is not None:
            await conn.execute(
                """
                UPDATE orders
                SET
                    status=$1,
                    master_id=$2,
                    master_name=COALESCE($3,master_name),
                    accepted_at=NOW()
                WHERE id=$4
                """,
                status,
                master_id,
                master_name,
                order_id,
            )
        else:
            await conn.execute(
                """
                UPDATE orders
                SET status=$1
                WHERE id=$2
                """,
                status,
                order_id,
            )


async def create_order(data: dict):

    order_number = (
        "U24-"
        + datetime.now().strftime("%d%m%H%M%S")
    )

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            INSERT INTO orders
            (
                order_number,
                user_id,
                service_type,
                service_name,
                client_name,
                client_phone,
                address,
                latitude,
                longitude,
                description,
                photo_ids,
                preferred_time,
                price,
                status
            )
            VALUES
            (
                $1,$2,$3,$4,$5,$6,$7,
                $8,$9,$10,$11,$12,$13,'yangi'
            )
            RETURNING id
            """,
            order_number,
            data["user_id"],
            data.get("service_type", ""),
            data.get("service_name", ""),
            data.get("client_name", ""),
            data.get("client_phone", ""),
            data.get("address", ""),
            data.get("latitude"),
            data.get("longitude"),
            data.get("description", ""),
            data.get("photo_ids", ""),
            data.get("preferred_time", ""),
            data.get("price", 0),
        )

        return await get_order(row["id"])


# ============================================================
# ROLE
# ============================================================

def get_fixed_role(user_id: int):

    if user_id in ADMIN_IDS:
        return "admin"

    if user_id == DISPATCHER_ID:
        return "dispetcher"

    return None


async def get_role(user_id: int):

    fixed = get_fixed_role(user_id)

    if fixed:
        return fixed

    user = await get_user(user_id)

    if not user:
        return None

    return user["role"]


# ============================================================
# MENUS
# ============================================================

def client_menu():

    return ReplyKeyboardMarkup(
        [
            ["🛒 Buyurtma berish"],
            ["📋 Mening buyurtmalarim", "🔍 Buyurtma holati"],
            ["❌ Buyurtmani bekor qilish", "🔁 Qayta buyurtma"],
            ["⭐ Reytingim", "📝 Sharh qoldirish"],
            ["📞 Dispetcher bilan bog'lanish"],
            ["⚙️ Sozlamalar"],
        ],
        resize_keyboard=True,
    )


def master_menu():

    return ReplyKeyboardMarkup(
        [
            ["👤 Mening profilim"],
            ["🆕 Yangi buyurtmalar"],
            ["📋 Mening buyurtmalarim"],
            ["📊 Mening statistikam"],
            ["💰 Kunlik daromad"],
            ["⭐ Reytingim"],
            ["🕒 Mening grafikim"],
            ["📞 Dispetcher bilan bog'lanish"],
        ],
        resize_keyboard=True,
    )


def dispatcher_menu():

    return ReplyKeyboardMarkup(
        [
            ["📨 Yangi buyurtmalar"],
            ["📋 Barcha buyurtmalar"],
            ["👨‍🔧 Ustalar ro'yxati"],
            ["📊 Statistika"],
            ["🔗 Ustaga biriktirish"],
            ["📞 Admin bilan bog'lanish"],
        ],
        resize_keyboard=True,
    )


def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["👨‍🔧 Ustalar"],
            ["📋 Barcha buyurtmalar"],
            ["👥 Mijozlar"],
            ["📊 Statistika"],
            ["💰 Narxlar"],
            ["📞 Dispetcher bilan bog'lanish"],
        ],
        resize_keyboard=True,
    )


def back_menu():

    return ReplyKeyboardMarkup(
        [["🔙 Orqaga"]],
        resize_keyboard=True,
    )


# ============================================================
# SERVICES
# ============================================================

SERVICES = {
    "🛠 Mebel": {
        "type": "mebel",
        "items": [
            ("🪑 Mebel yig'ish", 75000),
            ("🚪 Shkaf yig'ish", 100000),
            ("🛏 Krovat yig'ish", 80000),
            ("🍽 Oshxona mebeli", 120000),
            ("🪑 Stol-stul", 70000),
            ("🔧 Mebel ta'miri", 75000),
            ("📦 Mebel demontaj", 70000),
            ("🚚 Mebel tashish", 150000),
        ],
    },

    "🚚 Ko'chirish": {
        "type": "kochiruv",
        "items": [
            ("🏠 Uy ko'chirish", 200000),
            ("📦 Kichik yuk", 30000),
            ("📦 O'rta yuk", 50000),
            ("📦 Katta yuk", 80000),
            ("🚛 Yuk tashish", 150000),
        ],
    },

    "🛠 Uy ustasi": {
        "type": "usta",
        "items": [
            ("🚪 Eshik ta'miri", 70000),
            ("🪟 Deraza ta'miri", 65000),
            ("🔒 Qulf almashtirish", 60000),
            ("💡 Chiroq o'rnatish", 50000),
            ("🔌 Rozetka o'rnatish", 60000),
            ("🚿 Santexnika", 80000),
            ("🔧 Quvur ta'miri", 90000),
            ("❓ Boshqa xizmat", 0),
        ],
    },
}


def service_type_keyboard():

    rows = []

    for name in SERVICES:
        rows.append([KeyboardButton(name)])

    rows.append([KeyboardButton("🔙 Orqaga")])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
    )


def service_name_keyboard(service_key: str):

    items = SERVICES[service_key]["items"]

    rows = []

    row = []

    for name, price in items:

        row.append(
            KeyboardButton(name)
        )

        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append(
        [KeyboardButton("🔙 Orqaga")]
    )

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    role = await get_role(user.id)

    if role:

        db_user = await get_user(user.id)

        name = (
            db_user["full_name"]
            if db_user
            else user.first_name
        )

        await update.message.reply_text(
            f"👋 Assalomu alaykum, "
            f"<b>{name}</b>!\n\n"
            f"USTA 24 ANDIJON",
            parse_mode=ParseMode.HTML,
            reply_markup=menu_by_role(role),
        )

        return

    context.user_data.clear()

    context.user_data["state"] = "name"

    await update.message.reply_text(
        "🕌 <b>USTA 24 ANDIJON</b>\n\n"
        "Assalomu alaykum!\n"
        "Xizmatimizga xush kelibsiz.\n\n"
        "👤 Ismingizni kiriting:",
        parse_mode=ParseMode.HTML,
    )


def menu_by_role(role):

    if role == "usta":
        return master_menu()

    if role == "dispetcher":
        return dispatcher_menu()

    if role == "admin":
        return admin_menu()

    return client_menu()


# ============================================================
# PROFILE REGISTRATION
# ============================================================

async def registration_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    state = context.user_data.get("state")

    if state == "name":

        name = (update.message.text or "").strip()

        if len(name) < 2:
            await update.message.reply_text(
                "❌ Ism juda qisqa."
            )
            return

        context.user_data["full_name"] = name
        context.user_data["state"] = "phone"

        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📞 Telefon raqamni yuborish",
                        request_contact=True,
                    )
                ],
                ["✏️ O'zim yozaman"],
            ],
            resize_keyboard=True,
        )

        await update.message.reply_text(
            "📞 Telefon raqamingizni yuboring:",
            reply_markup=keyboard,
        )

        return

    if state == "phone":

        if update.message.contact:

            phone = (
                update.message.contact.phone_number
            )

        else:

            phone = (
                update.message.text or ""
            ).strip()

            if phone == "✏️ O'zim yozaman":
                await update.message.reply_text(
                    "📞 Telefon raqamingizni yozing:"
                )
                return

        context.user_data["phone"] = phone

        role = get_fixed_role(
            update.effective_user.id
        )

        if role:

            await finish_registration(
                update,
                context,
                role,
            )

            return

        keyboard = ReplyKeyboardMarkup(
            [
                ["👤 Mijoz"],
                ["👨‍🔧 Usta"],
            ],
            resize_keyboard=True,
        )

        context.user_data["state"] = "role"

        await update.message.reply_text(
            "👤 Kim sifatida kirasiz?",
            reply_markup=keyboard,
        )

        return

    if state == "role":

        text = update.message.text

        if text == "👤 Mijoz":
            role = "mijoz"

        elif text == "👨‍🔧 Usta":
            role = "usta"

        else:
            await update.message.reply_text(
                "❌ Tugmalardan birini tanlang."
            )
            return

        await finish_registration(
            update,
            context,
            role,
        )


async def finish_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    role: str,
):

    user = update.effective_user

    await save_user(
        user.id,
        context.user_data.get(
            "full_name",
            user.first_name or "",
        ),
        context.user_data.get("phone", ""),
        role,
    )

    if role == "usta":
        await create_master(user.id)

    context.user_data.clear()

    await update.message.reply_text(
        "✅ <b>Ro'yxatdan o'tish tugadi!</b>\n\n"
        "USTA 24 ANDIJON ga xush kelibsiz.",
        parse_mode=ParseMode.HTML,
        reply_markup=menu_by_role(role),
    )


# ============================================================
# ORDER CREATION
# ============================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = await get_user(
        update.effective_user.id
    )

    if not user:
        await update.message.reply_text(
            "❌ Avval /start bosing."
        )
        return

    if user["is_blocked"]:
        await update.message.reply_text(
            "⛔ Siz bloklangansiz."
        )
        return

    context.user_data.clear()

    context.user_data["state"] = "service_type"
    context.user_data["order"] = {
        "user_id": update.effective_user.id
    }

    await update.message.reply_text(
        "🛒 <b>BUYURTMA BERISH</b>\n\n"
        "1️⃣ Xizmat turini tanlang:",
        parse_mode=ParseMode.HTML,
        reply_markup=service_type_keyboard(),
    )


async def order_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    state = context.user_data.get("state")

    if not state.startswith("order_"):
        return

    order = context.user_data.setdefault(
        "order",
        {},
    )

    text = update.message.text or ""

    # --------------------------------------------------------
    # SERVICE TYPE
    # --------------------------------------------------------

    if state == "order_service_type":

        if text == "🔙 Orqaga":

            context.user_data.clear()

            role = await get_role(
                update.effective_user.id
            )

            await update.message.reply_text(
                "🏠 Bosh menyu",
                reply_markup=menu_by_role(role),
            )

            return

        if text not in SERVICES:

            await update.message.reply_text(
                "❌ Xizmat turini tanlang.",
                reply_markup=service_type_keyboard(),
            )

            return

        order["service_type"] = SERVICES[text]["type"]
        order["service_category"] = text

        context.user_data["state"] = (
            "order_service_name"
        )

        await update.message.reply_text(
            "2️⃣ Xizmatni tanlang:",
            reply_markup=service_name_keyboard(text),
        )

        return

    # --------------------------------------------------------
    # SERVICE NAME
    # --------------------------------------------------------

    if state == "order_service_name":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_service_type"
            )

            await update.message.reply_text(
                "1️⃣ Xizmat turini tanlang:",
                reply_markup=service_type_keyboard(),
            )

            return

        category = order.get(
            "service_category"
        )

        valid = [
            item[0]
            for item in SERVICES[category]["items"]
        ]

        if text not in valid:

            await update.message.reply_text(
                "❌ Xizmatni tugmadan tanlang."
            )

            return

        price = 0

        for name, item_price in SERVICES[
            category
        ]["items"]:

            if name == text:
                price = item_price
                break

        order["service_name"] = text
        order["price"] = price

        context.user_data["state"] = (
            "order_name"
        )

        await update.message.reply_text(
            f"✅ {text}\n"
            f"💰 Boshlang'ich narx: "
            f"{price:,} so'm\n\n"
            "3️⃣ Mijoz ismini kiriting:",
            reply_markup=back_menu(),
        )

        return

    # --------------------------------------------------------
    # CLIENT NAME
    # --------------------------------------------------------

    if state == "order_name":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_service_name"
            )

            await update.message.reply_text(
                "2️⃣ Xizmatni tanlang:",
                reply_markup=service_name_keyboard(
                    order["service_category"]
                ),
            )

            return

        if len(text) < 2:

            await update.message.reply_text(
                "❌ Ismni to'g'ri kiriting."
            )

            return

        order["client_name"] = text

        context.user_data["state"] = (
            "order_phone"
        )

        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📞 Telefon raqamni yuborish",
                        request_contact=True,
                    )
                ],
                ["✏️ O'zim yozaman"],
                ["🔙 Orqaga"],
            ],
            resize_keyboard=True,
        )

        await update.message.reply_text(
            "4️⃣ Telefon raqamingiz:",
            reply_markup=keyboard,
        )

        return

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    if state == "order_phone":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_name"
            )

            await update.message.reply_text(
                "3️⃣ Ismingiz:",
                reply_markup=back_menu(),
            )

            return

        if update.message.contact:

            phone = (
                update.message.contact.phone_number
            )

        else:

            phone = text.strip()

            if phone == "✏️ O'zim yozaman":

                await update.message.reply_text(
                    "📞 Telefon raqamingizni yozing:"
                )

                return

        order["client_phone"] = phone

        context.user_data["state"] = (
            "order_address"
        )

        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📍 Geolokatsiya yuborish",
                        request_location=True,
                    )
                ],
                ["✏️ Manzilni yozaman"],
                ["🔙 Orqaga"],
            ],
            resize_keyboard=True,
        )

        await update.message.reply_text(
            "5️⃣ 📍 Manzilingizni yuboring:",
            reply_markup=keyboard,
        )

        return

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    if state == "order_address":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_phone"
            )

            await update.message.reply_text(
                "4️⃣ Telefon raqamingiz:",
                reply_markup=back_menu(),
            )

            return

        if update.message.location:

            loc = update.message.location

            order["latitude"] = loc.latitude
            order["longitude"] = loc.longitude

            order["address"] = (
                f"📍 {loc.latitude}, "
                f"{loc.longitude}"
            )

        else:

            if text == "✏️ Manzilni yozaman":

                await update.message.reply_text(
                    "🏠 Manzilingizni yozing:"
                )

                return

            order["address"] = text

        context.user_data["state"] = (
            "order_description"
        )

        await update.message.reply_text(
            "6️⃣ 📝 Muammo haqida qisqacha "
            "yozing.\n\n"
            "Agar kerak bo'lmasa "
            "«⏭ O'tkazib yuborish» bosing.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["⏭ O'tkazib yuborish"],
                    ["🔙 Orqaga"],
                ],
                resize_keyboard=True,
            ),
        )

        return

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    if state == "order_description":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_address"
            )

            await update.message.reply_text(
                "5️⃣ Manzilni yuboring:",
            )

            return

        if text == "⏭ O'tkazib yuborish":
            order["description"] = ""
        else:
            order["description"] = text

        context.user_data["state"] = (
            "order_photo"
        )

        await update.message.reply_text(
            "7️⃣ 📸 Muammo rasmini yuboring.\n\n"
            "1-5 ta rasm yuborishingiz mumkin.\n"
            "Yoki o'tkazib yuboring.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["⏭ O'tkazib yuborish"],
                    ["🔙 Orqaga"],
                ],
                resize_keyboard=True,
            ),
        )

        return

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    if state == "order_photo":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_description"
            )

            await update.message.reply_text(
                "6️⃣ Izoh:",
                reply_markup=back_menu(),
            )

            return

        photos = context.user_data.setdefault(
            "photos",
            [],
        )

        if update.message.photo:

            photo_id = (
                update.message.photo[-1].file_id
            )

            if len(photos) < 5:
                photos.append(photo_id)

            await update.message.reply_text(
                f"✅ Rasm saqlandi: "
                f"{len(photos)}/5\n\n"
                "Yana rasm yuboring yoki "
                "«⏭ O'tkazib yuborish» bosing."
            )

            return

        if text == "⏭ O'tkazib yuborish":

            order["photo_ids"] = ",".join(
                photos
            )

            context.user_data["state"] = (
                "order_time"
            )

            await update.message.reply_text(
                "8️⃣ 🕐 Qachon kerak?",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["🔴 Hozir"],
                        ["🟡 Bugun"],
                        ["🟢 Ertaga"],
                        ["📅 Boshqa vaqt"],
                        ["🔙 Orqaga"],
                    ],
                    resize_keyboard=True,
                ),
            )

            return

        await update.message.reply_text(
            "📸 Rasm yuboring yoki "
            "«⏭ O'tkazib yuborish» bosing."
        )

        return

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    if state == "order_time":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_photo"
            )

            await update.message.reply_text(
                "📸 Rasm yuboring yoki o'tkazing."
            )

            return

        if text == "📅 Boshqa vaqt":

            context.user_data["state"] = (
                "order_custom_time"
            )

            await update.message.reply_text(
                "📅 Kerakli sana va vaqtni yozing.\n"
                "Masalan: 25.08.2026 15:00",
                reply_markup=back_menu(),
            )

            return

        order["preferred_time"] = text

        await show_order_confirmation(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # CUSTOM TIME
    # --------------------------------------------------------

    if state == "order_custom_time":

        if text == "🔙 Orqaga":

            context.user_data["state"] = (
                "order_time"
            )

            await update.message.reply_text(
                "🕐 Qachon kerak?",
            )

            return

        order["preferred_time"] = text

        await show_order_confirmation(
            update,
            context,
        )


# ============================================================
# ORDER CONFIRMATION
# ============================================================

async def show_order_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    order = context.user_data["order"]

    photos = context.user_data.get(
        "photos",
        [],
    )

    text = (
        "📋 <b>BUYURTMA TEKSHIRUVI</b>\n"
        "════════════════════\n"
        f"🛠 Xizmat: "
        f"{order.get('service_name')}\n"
        f"👤 Ism: "
        f"{order.get('client_name')}\n"
        f"📞 Telefon: "
        f"{order.get('client_phone')}\n"
        f"📍 Manzil: "
        f"{order.get('address')}\n"
        f"📝 Izoh: "
        f"{order.get('description') or 'Yo‘q'}\n"
        f"📸 Rasmlar: "
        f"{len(photos)} ta\n"
        f"🕐 Vaqt: "
        f"{order.get('preferred_time')}\n"
        f"💰 Narx: "
        f"{order.get('price', 0):,} so'm\n"
        "════════════════════\n"
        "Buyurtmani tasdiqlaysizmi?"
    )

    context.user_data["state"] = (
        "order_confirm"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ Tasdiqlash"],
                ["✏️ O'zgartirish"],
                ["❌ Bekor qilish"],
            ],
            resize_keyboard=True,
        ),
    )


async def order_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text

    if text == "❌ Bekor qilish":

        context.user_data.clear()

        await update.message.reply_text(
            "❌ Buyurtma bekor qilindi.",
            reply_markup=client_menu(),
        )

        return

    if text == "✏️ O'zgartirish":

        context.user_data["state"] = (
            "order_service_type"
        )

        await update.message.reply_text(
            "🔄 Buyurtmani qaytadan "
            "to'ldiramiz.\n\n"
            "1️⃣ Xizmat turini tanlang:",
            reply_markup=service_type_keyboard(),
        )

        return

    if text != "✅ Tasdiqlash":

        await update.message.reply_text(
            "❌ Tugmalardan birini bosing."
        )

        return

    order_data = context.user_data["order"]

    order_data["photo_ids"] = ",".join(
        context.user_data.get("photos", [])
    )

    created = await create_order(
        order_data
    )

    context.user_data.clear()

    await update.message.reply_text(
        "🎉 <b>BUYURTMA ҚАБУЛ ҚИЛИНДИ!</b>\n\n"
        f"🆔 <b>{created['order_number']}</b>\n"
        "⏳ Holat: Yangi\n\n"
        "📨 Buyurtmangiz dispetcher va "
        "ustalar guruhiga yuborildi.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )

    await send_order_to_group(
        created,
        context,
    )

    await send_order_to_dispatcher(
        created,
        context,
    )


# ============================================================
# ORDER MESSAGE TO MASTERS GROUP
# ============================================================

def order_text(order):

    return (
        "🆕 <b>YANGI BUYURTMA!</b>\n"
        "════════════════════\n"
        f"🆔 <b>{order['order_number']}</b>\n"
        f"🛠 Xizmat: {order['service_name']}\n"
        f"💰 Narx: {order['price']:,} so'm\n"
        f"🕐 Vaqt: {order['preferred_time']}\n\n"
        "👤 <b>MIJOZ</b>\n"
        f"Ism: {order['client_name']}\n"
        f"📞 {order['client_phone']}\n"
        f"📍 {order['address']}\n"
        f"📝 {order['description'] or 'Yo‘q'}\n"
        "════════════════════"
    )


def master_order_keyboard(order_id):

    return InlineKeyboardMarkup(
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
        ]
    )


async def send_order_to_group(
    order,
    context,
):

    if not MASTERS_GROUP_ID:
        logger.warning(
            "MASTERS_GROUP_ID berilmagan"
        )
        return

    try:

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=order_text(order),
            parse_mode=ParseMode.HTML,
            reply_markup=master_order_keyboard(
                order["id"]
            ),
        )

        photos = [
            x for x in
            (order["photo_ids"] or "").split(",")
            if x
        ]

        for photo_id in photos[:5]:

            await context.bot.send_photo(
                chat_id=MASTERS_GROUP_ID,
                photo=photo_id,
            )

    except Exception as e:

        logger.exception(
            "Masters group error: %s",
            e,
        )


# ============================================================
# DISPATCHER MESSAGE
# ============================================================

async def send_order_to_dispatcher(
    order,
    context,
):

    if not DISPATCHER_ID:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📨 USTALARGA YUBORISH",
                    callback_data=(
                        f"send_masters:{order['id']}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ RAD ETISH",
                    callback_data=(
                        f"dispatcher_reject:{order['id']}"
                    ),
                )
            ],
        ]
    )

    try:

        await context.bot.send_message(
            chat_id=DISPATCHER_ID,
            text=(
                "🎧 <b>DISPETCHERGA YANGI BUYURTMA</b>\n\n"
                + order_text(order)
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.exception(
            "Dispatcher message error: %s",
            e,
        )


# ============================================================
# CALLBACKS
# ============================================================

async def callbacks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    # --------------------------------------------------------
    # MASTER ACCEPT
    # --------------------------------------------------------

    if data.startswith("accept:"):

        order_id = int(
            data.split(":")[1]
        )

        order = await get_order(order_id)

        if not order:
            await query.message.reply_text(
                "❌ Buyurtma topilmadi."
            )
            return

        user_id = query.from_user.id

        role = await get_role(user_id)

        if role != "usta":

            await query.answer(
                "Faqat usta qabul qilishi mumkin.",
                show_alert=True,
            )

            return

        if order["master_id"]:

            await query.message.reply_text(
                "⚠️ Bu buyurtmani boshqa usta "
                "allaqachon qabul qilgan."
            )

            return

        master = await get_user(user_id)

        master_name = (
            master["full_name"]
            if master
            else query.from_user.full_name
        )

        await update_order(
            order_id,
            "qabul_qilindi",
            master_id=user_id,
            master_name=master_name,
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"✅ Buyurtma qabul qilindi!\n"
            f"🆔 {order['order_number']}"
        )

        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(
                "✅ <b>Buyurtmangizni usta qabul qildi!</b>\n\n"
                f"🆔 {order['order_number']}\n"
                f"👨‍🔧 Usta: {master_name}\n"
                f"📞 {order['client_phone']}\n\n"
                "Usta siz bilan bog'lanadi."
            ),
            parse_mode=ParseMode.HTML,
        )

        if DISPATCHER_ID:

            await context.bot.send_message(
                chat_id=DISPATCHER_ID,
                text=(
                    "✅ <b>BUYURTMA USTA TOMONIDAN QABUL QILINDI</b>\n\n"
                    f"🆔 {order['order_number']}\n"
                    f"👨‍🔧 Usta: {master_name}\n"
                    f"👤 Mijoz: {order['client_name']}"
                ),
                parse_mode=ParseMode.HTML,
            )

        return

    # --------------------------------------------------------
    # MASTER REJECT
    # --------------------------------------------------------

    if data.startswith("reject:"):

        order_id = int(
            data.split(":")[1]
        )

        role = await get_role(
            query.from_user.id
        )

        if role != "usta":
            return

        await query.message.reply_text(
            "❌ Buyurtma rad etildi."
        )

        return

    # --------------------------------------------------------
    # DISPATCHER SEND MASTERS
    # --------------------------------------------------------

    if data.startswith("send_masters:"):

        if query.from_user.id != DISPATCHER_ID:

            await query.answer(
                "Faqat dispetcher uchun.",
                show_alert=True,
            )

            return

        order_id = int(
            data.split(":")[1]
        )

        order = await get_order(order_id)

        if not order:
            return

        await update_order(
            order_id,
            "taklif_yuborildi",
        )

        await send_order_to_group(
            order,
            context,
        )

        await query.message.reply_text(
            "✅ Buyurtma ustalar guruhiga yuborildi."
        )

        return

    # --------------------------------------------------------
    # DISPATCHER REJECT
    # --------------------------------------------------------

    if data.startswith("dispatcher_reject:"):

        if query.from_user.id != DISPATCHER_ID:
            return

        order_id = int(
            data.split(":")[1]
        )

        order = await get_order(order_id)

        if not order:
            return

        await update_order(
            order_id,
            "bekor_qilindi",
        )

        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(
                "❌ <b>Buyurtmangiz bekor qilindi.</b>\n\n"
                f"🆔 {order['order_number']}\n"
                "Dispetcher bilan bog'lanishingiz mumkin."
            ),
            parse_mode=ParseMode.HTML,
        )

        await query.message.reply_text(
            "❌ Buyurtma bekor qilindi."
        )

        return


# ============================================================
# CLIENT MENU
# ============================================================

async def client_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text

    user_id = update.effective_user.id

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    if text == "🛒 Buyurtma berish":

        await start_order(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # MY ORDERS
    # --------------------------------------------------------

    if text == "📋 Mening buyurtmalarim":

        orders = await get_user_orders(
            user_id
        )

        if not orders:

            await update.message.reply_text(
                "📋 Hozircha buyurtmalaringiz yo'q."
            )

            return

        lines = [
            "📋 <b>SIZNING BUYURTMALARINGIZ</b>\n"
        ]

        for order in orders[:10]:

            lines.append(
                f"🆔 {order['order_number']}\n"
                f"🛠 {order['service_name']}\n"
                f"📌 Holat: {order['status']}\n"
                f"💰 {order['price']:,} so'm\n"
                "────────────"
            )

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

        return

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    if text == "🔍 Buyurtma holati":

        orders = await get_user_orders(
            user_id
        )

        if not orders:

            await update.message.reply_text(
                "📋 Buyurtma topilmadi."
            )

            return

        order = orders[0]

        await update.message.reply_text(
            f"🔍 <b>BUYURTMA HOLATI</b>\n\n"
            f"🆔 {order['order_number']}\n"
            f"🛠 {order['service_name']}\n"
            f"📌 {order['status']}\n"
            f"👨‍🔧 {order['master_name'] or 'Hali biriktirilmagan'}",
            parse_mode=ParseMode.HTML,
        )

        return

    # --------------------------------------------------------
    # DISPATCHER
    # --------------------------------------------------------

    if text == "📞 Dispetcher bilan bog'lanish":

        if DISPATCHER_ID:

            await context.bot.send_message(
                chat_id=DISPATCHER_ID,
                text=(
                    "📞 <b>MIJOZ DISPETCHER BILAN BOG'LANMOQDA</b>\n\n"
                    f"👤 ID: {user_id}\n"
                    f"👤 Ism: {update.effective_user.full_name}"
                ),
                parse_mode=ParseMode.HTML,
            )

        await update.message.reply_text(
            "📞 Dispetcherga xabar yuborildi."
        )

        return


# ============================================================
# MASTER MENU
# ============================================================

async def master_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text

    user_id = update.effective_user.id

    if text == "🆕 Yangi buyurtmalar":

        orders = await get_new_orders()

        if not orders:

            await update.message.reply_text(
                "🆕 Hozircha yangi buyurtmalar yo'q."
            )

            return

        for order in orders[:10]:

            await update.message.reply_text(
                order_text(order),
                parse_mode=ParseMode.HTML,
                reply_markup=master_order_keyboard(
                    order["id"]
                ),
            )

        return

    if text == "📋 Mening buyurtmalarim":

        orders = await get_master_orders(
            user_id
        )

        if not orders:

            await update.message.reply_text(
                "📋 Sizda buyurtmalar yo'q."
            )

            return

        for order in orders[:10]:

            await update.message.reply_text(
                f"🆔 {order['order_number']}\n"
                f"🛠 {order['service_name']}\n"
                f"👤 {order['client_name']}\n"
                f"📌 {order['status']}\n"
                f"💰 {order['price']:,} so'm"
            )

        return

    if text == "👤 Mening profilim":

        user = await get_user(user_id)
        master = await get_master(user_id)

        await update.message.reply_text(
            "👨‍🔧 <b>USTA PROFILI</b>\n\n"
            f"👤 Ism: {user['full_name']}\n"
            f"📞 Telefon: {user['phone']}\n"
            f"⭐ Reyting: {master['rating']}\n"
            f"📋 Buyurtmalar: "
            f"{master['total_orders']}",
            parse_mode=ParseMode.HTML,
        )

        return

    if text == "📊 Mening statistikam":

        master = await get_master(user_id)

        await update.message.reply_text(
            "📊 <b>MENING STATISTIKAM</b>\n\n"
            f"📋 Buyurtmalar: "
            f"{master['total_orders']}\n"
            f"⭐ Reyting: "
            f"{master['rating']}\n"
            f"💰 Daromad: "
            f"{master['total_earnings']:,} so'm",
            parse_mode=ParseMode.HTML,
        )

        return

    if text == "⭐ Reytingim":

        master = await get_master(user_id)

        await update.message.reply_text(
            f"⭐ Sizning reytingingiz: "
            f"{master['rating']}"
        )

        return

    if text == "📞 Dispetcher bilan bog'lanish":

        if DISPATCHER_ID:

            await context.bot.send_message(
                chat_id=DISPATCHER_ID,
                text=(
                    "📞 <b>USTA DISPETCHER BILAN BOG'LANMOQDA</b>\n\n"
                    f"👨‍🔧 ID: {user_id}\n"
                    f"Ism: {update.effective_user.full_name}"
                ),
                parse_mode=ParseMode.HTML,
            )

        await update.message.reply_text(
            "📞 Dispetcherga xabar yuborildi."
        )


# ============================================================
# DISPATCHER MENU
# ============================================================

async def dispatcher_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    text = update.message.text

    if update.effective_user.id != DISPATCHER_ID:
        return

    if text == "📨 Yangi buyurtmalar":

        orders = await get_new_orders()

        if not orders:

            await update.message.reply_text(
                "📨 Yangi buyurtmalar yo'q."
            )

            return

        for order in orders:

            await update.message.reply_text(
                order_text(order),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📨 USTALARGA YUBORISH",
                                callback_data=(
                                    f"send_masters:{order['id']}"
                                ),
                            )
                        ]
                    ]
                ),
            )

        return

    if text == "📋 Barcha buyurtmalar":

        orders = await get_all_orders()

        if not orders:

            await update.message.reply_text(
                "Buyurtmalar yo'q."
            )

            return

        for order in orders[:20]:

            await update.message.reply_text(
                f"🆔 {order['order_number']}\n"
                f"🛠 {order['service_name']}\n"
                f"👤 {order['client_name']}\n"
                f"📌 {order['status']}\n"
                f"👨‍🔧 "
                f"{order['master_name'] or '-'}"
            )

        return

    if text == "👨‍🔧 Ustalar ro'yxati":

        masters = await get_active_masters()

        if not masters:

            await update.message.reply_text(
                "👨‍🔧 Ustalar topilmadi."
            )

            return

        lines = [
            "👨‍🔧 <b>USTALAR</b>\n"
        ]

        for master in masters:

            lines.append(
                f"👨‍🔧 {master['full_name']}\n"
                f"📞 {master['phone']}\n"
                f"⭐ {master['rating']}\n"
                "────────────"
            )

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

        return

    if text == "📊 Statistika":

        async with db_pool.acquire() as conn:

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM orders"
            )

            new = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='yangi'
                """
            )

            accepted = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='qabul_qilindi'
                """
            )

            completed = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='yakunlandi'
                """
            )

        await update.message.reply_text(
            "📊 <b>STATISTIKA</b>\n\n"
            f"📋 Jami: {total}\n"
            f"🆕 Yangi: {new}\n"
            f"✅ Qabul qilingan: {accepted}\n"
            f"🏁 Yakunlangan: {completed}",
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# ADMIN MENU
# ============================================================

async def admin_actions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id not in ADMIN_IDS:
        return

    text = update.message.text

    if text == "👨‍🔧 Ustalar":

        masters = await get_active_masters()

        if not masters:

            await update.message.reply_text(
                "Ustalar yo'q."
            )

            return

        lines = [
            "👨‍🔧 <b>USTALAR</b>\n"
        ]

        for master in masters:

            lines.append(
                f"👤 {master['full_name']}\n"
                f"🆔 {master['user_id']}\n"
                f"📞 {master['phone']}\n"
                f"⭐ {master['rating']}\n"
                f"📋 {master['total_orders']}\n"
                "────────────"
            )

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

        return

    if text == "📋 Barcha buyurtmalar":

        orders = await get_all_orders()

        if not orders:

            await update.message.reply_text(
                "Buyurtmalar yo'q."
            )

            return

        for order in orders[:30]:

            await update.message.reply_text(
                f"🆔 {order['order_number']}\n"
                f"👤 {order['client_name']}\n"
                f"🛠 {order['service_name']}\n"
                f"📌 {order['status']}\n"
                f"👨‍🔧 "
                f"{order['master_name'] or '-'}"
            )

        return

    if text == "👥 Mijozlar":

        async with db_pool.acquire() as conn:

            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM users
                WHERE role='mijoz'
                """
            )

        await update.message.reply_text(
            f"👥 Mijozlar soni: {count}"
        )

        return

    if text == "📊 Statistika":

        async with db_pool.acquire() as conn:

            users = await conn.fetchval(
                "SELECT COUNT(*) FROM users"
            )

            orders = await conn.fetchval(
                "SELECT COUNT(*) FROM orders"
            )

            masters = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM users
                WHERE role='usta'
                """
            )

        await update.message.reply_text(
            "📊 <b>USTA 24 STATISTIKA</b>\n\n"
            f"👥 Foydalanuvchilar: {users}\n"
            f"👨‍🔧 Ustalar: {masters}\n"
            f"📋 Buyurtmalar: {orders}",
            parse_mode=ParseMode.HTML,
        )

        return

    if text == "💰 Narxlar":

        await update.message.reply_text(
            "💰 <b>XIZMATLAR NARXLARI</b>\n\n"
            "🪑 Mebel yig'ish — 75 000 so'm\n"
            "🚪 Shkaf — 100 000 so'm\n"
            "🛏 Krovat — 80 000 so'm\n"
            "🍽 Oshxona mebeli — 120 000 so'm\n"
            "🚚 Uy ko'chirish — 200 000 so'm\n"
            "💡 Chiroq — 50 000 so'm\n"
            "🔌 Rozетка — 60 000 so'm\n"
            "🚿 Santexnika — 80 000 so'm",
            parse_mode=ParseMode.HTML,
        )


# ============================================================
# GLOBAL ROUTER
# ============================================================

async def message_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    user_id = update.effective_user.id

    # --------------------------------------------------------
    # REGISTRATION
    # --------------------------------------------------------

    state = context.user_data.get("state", "")

    if state in (
        "name",
        "phone",
        "role",
    ):

        await registration_message(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    if state.startswith("order_"):

        if state == "order_confirm":

            await order_confirmation(
                update,
                context,
            )

        else:

            await order_message(
                update,
                context,
            )

        return

    # --------------------------------------------------------
    # FIXED ROLE
    # --------------------------------------------------------

    role = await get_role(user_id)

    if role == "admin":

        await admin_actions(
            update,
            context,
        )

        return

    if role == "dispetcher":

        await dispatcher_actions(
            update,
            context,
        )

        return

    if role == "usta":

        await master_actions(
            update,
            context,
        )

        return

    await client_actions(
        update,
        context,
    )


# ============================================================
# UNKNOWN COMMAND
# ============================================================

async def unknown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    role = await get_role(
        update.effective_user.id
    )

    if role:

        await update.message.reply_text(
            "❌ Tushunmadim. Menyudagi "
            "tugmalardan foydalaning.",
            reply_markup=menu_by_role(role),
        )

    else:

        await update.message.reply_text(
            "❌ Avval /start bosing."
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "Telegram error: %s",
        context.error,
    )


# ============================================================
# MAIN
# ============================================================

async def post_init(
    application: Application,
):

    await init_db()

    logger.info(
        "========================================"
    )

    logger.info(
        "USTA 24 ANDIJON BOT IS STARTING"
    )

    logger.info(
        "ADMIN_IDS=%s",
        list(ADMIN_IDS),
    )

    logger.info(
        "DISPATCHER_ID=%s",
        DISPATCHER_ID,
    )

    logger.info(
        "MASTERS_GROUP_ID=%s",
        MASTERS_GROUP_ID,
    )

    logger.info(
        "========================================"
    )


def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN ENV topilmadi!"
        )

    # Flask Railway health server
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True,
    )

    flask_thread.start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callbacks
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            | filters.CONTACT
            | filters.LOCATION
            | filters.PHOTO,
            message_router,
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Telegram polling started..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
