import os
import re
import io
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
# USTA 24 ANDIJON PRO FULL
# =========================================================

BOT_NAME = "USTA 24 ANDIJON"
DISPATCHER_PHONE = "+998 77 069 00 03"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("usta24")


# =========================================================
# CONFIG
# =========================================================

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
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID.strip())
    ADMIN_ID = int(ADMIN_ID.strip())
except ValueError:
    raise RuntimeError(
        "ADMIN_ID va MASTERS_GROUP_ID raqam bo'lishi kerak!"
    )


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return f"{BOT_NAME} PRO FULL ISHLAYAPTI!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# =========================================================
# DATABASE
# =========================================================

db_pool = None


async def init_database():
    global db_pool

    logger.info("PostgreSQL ulanishi...")

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        # =================================================
        # CUSTOMERS
        # =================================================

        await conn.execute(
            """
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
            """
        )

        # =================================================
        # ORDERS
        # =================================================

        await conn.execute(
            """
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
                status TEXT DEFAULT 'open',
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
            """
        )

        # =================================================
        # MASTERS
        # =================================================

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS masters (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE,
                name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                username TEXT,
                service TEXT,
                active BOOLEAN DEFAULT TRUE,
                rating NUMERIC DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # =================================================
        # ORDER HISTORY
        # =================================================

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_history (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                old_status TEXT,
                new_status TEXT,
                changed_by BIGINT,
                changed_by_name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # =================================================
        # REVIEWS
        # =================================================

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                order_id INTEGER UNIQUE NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT,
                rating INTEGER CHECK (rating BETWEEN 1 AND 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # =================================================
        # PRICE SETTINGS
        # =================================================

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_settings (
                id SERIAL PRIMARY KEY,
                service TEXT UNIQUE NOT NULL,
                base_price NUMERIC DEFAULT 0,
                unit TEXT DEFAULT 'order',
                active BOOLEAN DEFAULT TRUE
            )
            """
        )

        # =================================================
        # NOTIFICATIONS
        # =================================================

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                order_id INTEGER,
                customer_id BIGINT,
                notification_type TEXT,
                sent_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # =================================================
        # COMPATIBILITY
        # =================================================

        compatibility = [
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",

            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS master_id BIGINT",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS master_name TEXT",

            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS telegram_id BIGINT",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS phone TEXT",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS username TEXT",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS service TEXT",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS rating NUMERIC DEFAULT 0",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0",
            "ALTER TABLE masters ADD COLUMN IF NOT EXISTS completed_orders INTEGER DEFAULT 0",
        ]

        for sql in compatibility:
            try:
                await conn.execute(sql)
            except Exception as e:
                logger.warning(
                    "Compatibility: %s",
                    e,
                )

        # =================================================
        # DEFAULT SERVICES
        # =================================================

        services = [
            ("🪑 Mebel", 0),
            ("🚚 Yuk tashish / ko'chirish", 0),
            ("🔩 Santexnika", 0),
            ("⚡ Elektr", 0),
            ("🔥 Payvandlash", 0),
            ("🧱 Qurilish", 0),
            ("🧹 Tozalash", 0),
            ("❄️ Konditsioner", 0),
            ("🔨 Boshqa xizmat", 0),
        ]

        for service, price in services:
            await conn.execute(
                """
                INSERT INTO price_settings
                    (service, base_price)
                VALUES ($1, $2)
                ON CONFLICT (service) DO NOTHING
                """,
                service,
                price,
            )

    logger.info("✅ PostgreSQL tayyor.")
    logger.info("✅ Barcha jadvallar tekshirildi.")


# =========================================================
# CUSTOMER
# =========================================================

async def save_customer(
    telegram_id,
    name=None,
    phone=None,
    username=None,
    latitude=None,
    longitude=None,
):
    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO customers (
                telegram_id,
                name,
                phone,
                username,
                latitude,
                longitude,
                last_order_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,NOW())

            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = COALESCE(EXCLUDED.name, customers.name),
                phone = COALESCE(EXCLUDED.phone, customers.phone),
                username = COALESCE(
                    EXCLUDED.username,
                    customers.username
                ),
                latitude = COALESCE(
                    EXCLUDED.latitude,
                    customers.latitude
                ),
                longitude = COALESCE(
                    EXCLUDED.longitude,
                    customers.longitude
                ),
                last_order_at = NOW()
            """,
            telegram_id,
            name,
            phone,
            username,
            latitude,
            longitude,
        )


async def get_customer(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM customers
            WHERE telegram_id = $1
            """,
            telegram_id,
        )


# =========================================================
# ORDERS
# =========================================================

async def create_order(order):
    async with db_pool.acquire() as conn:

        order_id = await conn.fetchval(
            """
            INSERT INTO orders (
                customer_id,
                customer_name,
                phone,
                service,
                address,
                description,
                username,
                latitude,
                longitude,
                status,
                price
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,'open',$10
            )
            RETURNING id
            """,
            order["customer_id"],
            order["name"],
            order["phone"],
            order["service"],
            order["address"],
            order["description"],
            order["username"],
            order.get("latitude"),
            order.get("longitude"),
            order.get("price", 0),
        )

        await conn.execute(
            """
            INSERT INTO order_history (
                order_id,
                old_status,
                new_status,
                changed_by,
                changed_by_name
            )
            VALUES ($1,$2,$3,$4,$5)
            """,
            order_id,
            None,
            "open",
            order["customer_id"],
            order["name"],
        )

        return int(order_id)


async def get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )


async def update_order_status(
    order_id,
    new_status,
    user_id=None,
    user_name=None,
):
    async with db_pool.acquire() as conn:

        old_status = await conn.fetchval(
            """
            SELECT status
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )

        timestamps = {
            "accepted": "accepted_at",
            "in_progress": "started_at",
            "completed": "completed_at",
            "cancelled": "cancelled_at",
            "rejected": "rejected_at",
        }

        column = timestamps.get(new_status)

        if column:
            await conn.execute(
                f"""
                UPDATE orders
                SET
                    status = $1,
                    {column} = NOW()
                WHERE id = $2
                """,
                new_status,
                order_id,
            )
        else:
            await conn.execute(
                """
                UPDATE orders
                SET status = $1
                WHERE id = $2
                """,
                new_status,
                order_id,
            )

        await conn.execute(
            """
            INSERT INTO order_history (
                order_id,
                old_status,
                new_status,
                changed_by,
                changed_by_name
            )
            VALUES ($1,$2,$3,$4,$5)
            """,
            order_id,
            old_status,
            new_status,
            user_id,
            user_name,
        )


async def assign_master(
    order_id,
    master_id,
    master_name,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET
                master_id = $1,
                master_name = $2
            WHERE id = $3
            """,
            master_id,
            master_name,
            order_id,
        )


# =========================================================
# MASTER
# =========================================================

async def add_master(
    phone,
    name,
    service=None,
    telegram_id=None,
    username=None,
):
    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO masters (
                phone,
                name,
                service,
                telegram_id,
                username,
                active
            )
            VALUES ($1,$2,$3,$4,$5,TRUE)

            ON CONFLICT (phone)
            DO UPDATE SET
                name = EXCLUDED.name,
                service = EXCLUDED.service,
                telegram_id = COALESCE(
                    EXCLUDED.telegram_id,
                    masters.telegram_id
                ),
                username = COALESCE(
                    EXCLUDED.username,
                    masters.username
                ),
                active = TRUE
            """,
            phone,
            name,
            service,
            telegram_id,
            username,
        )


async def remove_master(phone):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE masters
            SET active = FALSE
            WHERE phone = $1
            """,
            phone,
        )


async def get_active_masters():
    async with db_pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT *
            FROM masters
            WHERE active = TRUE
            ORDER BY rating DESC, completed_orders DESC
            """
        )


async def get_master_by_phone(phone):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE phone = $1
            """,
            phone,
        )


async def get_master_by_id(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE telegram_id = $1
            """,
            telegram_id,
        )


# =========================================================
# PRICE
# =========================================================

async def get_base_price(service):
    async with db_pool.acquire() as conn:
        value = await conn.fetchval(
            """
            SELECT base_price
            FROM price_settings
            WHERE service = $1
              AND active = TRUE
            """,
            service,
        )

        return float(value or 0)


# =========================================================
# STATISTICS
# =========================================================

async def get_statistics():
    async with db_pool.acquire() as conn:

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM orders
            GROUP BY status
            """
        )

        result = {
            "total": int(total or 0),
            "open": 0,
            "accepted": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0,
            "rejected": 0,
        }

        for row in rows:
            if row["status"] in result:
                result[row["status"]] = int(row["count"])

        return result


async def get_period_statistics(days):
    async with db_pool.acquire() as conn:

        since = datetime.now() - timedelta(days=days)

        return await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed,
                COUNT(*) FILTER (
                    WHERE status = 'cancelled'
                ) AS cancelled,
                COUNT(*) FILTER (
                    WHERE status = 'rejected'
                ) AS rejected
            FROM orders
            WHERE created_at >= $1
            """,
            since,
        )


# =========================================================
# REVIEWS
# =========================================================

async def save_review(
    order_id,
    customer_id,
    rating,
    comment=None,
):
    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            """
            SELECT customer_id, master_id
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )

        if not order:
            return False

        if order["customer_id"] != customer_id:
            return False

        master_id = order["master_id"]

        await conn.execute(
            """
            INSERT INTO reviews (
                order_id,
                customer_id,
                master_id,
                rating,
                comment
            )
            VALUES ($1,$2,$3,$4,$5)

            ON CONFLICT (order_id)
            DO UPDATE SET
                rating = EXCLUDED.rating,
                comment = EXCLUDED.comment
            """,
            order_id,
            customer_id,
            master_id,
            rating,
            comment,
        )

        if master_id:

            avg_rating = await conn.fetchval(
                """
                SELECT AVG(rating)
                FROM reviews
                WHERE master_id = $1
                """,
                master_id,
            )

            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM reviews
                WHERE master_id = $1
                """,
                master_id,
            )

            await conn.execute(
                """
                UPDATE masters
                SET
                    rating = $1,
                    rating_count = $2
                WHERE telegram_id = $3
                """,
                float(avg_rating or 0),
                int(count or 0),
                master_id,
            )

        return True


# =========================================================
# USER STATES
# =========================================================

user_states = {}


# =========================================================
# MENUS
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Уста чақириш", "📋 Хизматлар"],
            ["📋 Буюртмаларим", "🔁 Қайта буюртма"],
            ["📞 Диспетчер"],
        ],
        resize_keyboard=True,
    )


def service_menu():
    return ReplyKeyboardMarkup(
        [
            ["🪑 Mebel"],
            ["🚚 Yuk tashish / ko'chirish"],
            ["🔩 Santexnika"],
            ["⚡ Elektr"],
            ["🔥 Payvandlash"],
            ["🧱 Qurilish"],
            ["🧹 Tozalash"],
            ["❄️ Konditsioner"],
            ["🔨 Boshqa xizmat"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Янги буюртмалар"],
            ["📋 Барча буюртмалар"],
            ["👤 Мижозлар"],
            ["👨‍🔧 Усталар"],
            ["➕ Уста қўшиш"],
            ["➖ Устани ўчириш"],
            ["📊 Статистика"],
            ["📈 Ҳисобот"],
            ["📢 Хабар тарқатиш"],
            ["💰 Нархлар"],
        ],
        resize_keyboard=True,
    )


def location_keyboard():
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📍 Геолокациямни юбориш",
                    request_location=True,
                )
            ],
            ["📍 Манзилни қўлда ёзиш"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# =========================================================
# START
# =========================================================

async def start(update, context):
    if not update.message:
        return

    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 ANDIJON PRO FULL\n\n"
        "🏠 Уй хизматлари\n"
        "🪑 Мебель\n"
        "🚚 Юк ташиш ва кўчириш\n"
        "🔧 Турли усталар хизмати\n\n"
        "Керакли хизматни танланг:",
        reply_markup=main_menu(),
    )


# =========================================================
# SERVICES
# =========================================================

async def services(update, context):
    await update.message.reply_text(
        "🛠 USTA 24 ANDIJON ХИЗМАТЛАРИ\n\n"
        "🪑 Мебель йиғиш ва таъмирлаш\n"
        "🍽 Ошхона мебели\n"
        "🚪 Шкаф\n"
        "🛏 Кровать\n"
        "🪑 Стол ва стул\n"
        "📦 Мебель ажратиш/йиғиш\n"
        "🚚 Мебель ташиш\n"
        "🏠 Уй кўчириш\n"
        "🔩 Сантехника\n"
        "⚡ Электр\n"
        "🔥 Пайвандлаш\n"
        "🧱 Қурилиш\n"
        "🧹 Тозалаш\n"
        "❄️ Кондиционер\n"
        "🔨 Бошқа хизмат",
        reply_markup=main_menu(),
    )


# =========================================================
# CONTACT
# =========================================================

async def dispatcher_contact(update, context):
    await update.message.reply_text(
        "📞 USTA 24 ANDIJON\n\n"
        "👨‍💼 Уста диспетчери\n\n"
        f"☎️ {DISPATCHER_PHONE}\n\n"
        "Буюртма, уста ёки хизмат бўйича мурожаат қилишингиз мумкин.",
        reply_markup=main_menu(),
    )


# =========================================================
# START ORDER
# =========================================================

async def start_order(update, context):
    user = update.effective_user

    if not user:
        return

    customer = await get_customer(user.id)

    user_states[user.id] = {
        "step": "name"
    }

    if customer and customer["name"]:

        user_states[user.id]["name"] = customer["name"]

        if customer["phone"]:
            user_states[user.id]["phone"] = customer["phone"]

        user_states[user.id]["step"] = "service"

        await update.message.reply_text(
            f"👋 Салом, {customer['name']}!\n\n"
            "🆕 Янги буюртма.\n\n"
            "🛠 Хизматни танланг:",
            reply_markup=service_menu(),
        )

        return

    await update.message.reply_text(
        "📝 ЯНГИ БУЮРТМА\n\n"
        "1️⃣ Исмингизни ёзинг:"
    )


# =========================================================
# SEND ORDER TO GROUP
# =========================================================

async def send_order_to_group(
    context,
    order_id,
):
    order = await get_order(order_id)

    if not order:
        return

    location = "-"

    if (
        order["latitude"] is not None
        and order["longitude"] is not None
    ):
        location = (
            f"https://maps.google.com/?q="
            f"{order['latitude']},"
            f"{order['longitude']}"
        )

    text = (
        "🆕 USTA 24 ANDIJON\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Буюртма: #{order_id}\n"
        f"👤 Мижоз: {order['customer_name'] or '-'}\n"
        f"📞 Телефон: {order['phone'] or '-'}\n"
        f"🛠 Хизмат: {order['service'] or '-'}\n"
        f"📍 Манзил: {order['address'] or '-'}\n"
        f"🗺 Геолокация: {location}\n"
        f"📝 Изоҳ: {order['description'] or '-'}\n"
        f"💰 Нарх асоси: {order['price'] or 0}\n\n"
        "👨‍🔧 Буюртмани олиш:"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟡 Буюртмани олиш",
                    callback_data=f"take:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"reject:{order_id}",
                )
            ],
        ]
    )

    await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )


# =========================================================
# MASTER ASSIGN MENU
# =========================================================

async def show_assign_menu(query, order_id):
    masters = await get_active_masters()

    buttons = []

    for master in masters:
        title = (
            f"👨‍🔧 {master['name']}"
            f" | ⭐ {float(master['rating'] or 0):.1f}"
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    title,
                    callback_data=(
                        f"setmaster:{order_id}:"
                        f"{master['telegram_id']}"
                    ),
                )
            ]
        )

    if not buttons:
        buttons = [
            [
                InlineKeyboardButton(
                    "❌ Фаол уста йўқ",
                    callback_data="noop:0",
                )
            ]
        ]

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# CALLBACK
# =========================================================

async def callback_handler(update, context):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    parts = data.split(":")

    action = parts[0]

    # =====================================================
    # NOOP
    # =====================================================

    if action == "noop":
        return

    # =====================================================
    # RATE
    # =====================================================

    if action == "rate":

        if len(parts) != 3:
            return

        try:
            order_id = int(parts[1])
            rating = int(parts[2])
        except ValueError:
            return

        customer_id = query.from_user.id

        success = await save_review(
            order_id,
            customer_id,
            rating,
        )

        if not success:
            await query.answer(
                "❌ Рейтинг бериш мумкин эмас.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            f"⭐ Рейтинг қабул қилинди: {rating}/5\n\n"
            "Раҳмат! USTA 24 ANDIJON сизга яна хизмат қилишдан мамнун."
        )

        return

    # =====================================================
    # ORDER ID ACTIONS
    # =====================================================

    if len(parts) < 2:
        return

    try:
        order_id = int(parts[1])
    except ValueError:
        return

    master = query.from_user
    order = await get_order(order_id)

    if not order:
        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True,
        )
        return

    # =====================================================
    # TAKE
    # =====================================================

    if action == "take":

        if order["status"] != "open":
            await query.answer(
                "⚠️ Бу буюртма аллақачон олинган.",
                show_alert=True,
            )
            return

        master_db = await get_master_by_id(master.id)

        if not master_db:

            await query.answer(
                "❌ Сиз ҳали тизимга уста сифатида қўшилмагансиз.",
                show_alert=True,
            )

            return

        master_name = master_db["name"]

        await assign_master(
            order_id,
            master.id,
            master_name,
        )

        await update_order_status(
            order_id,
            "accepted",
            master.id,
            master_name,
        )

        await query.edit_message_text(
            f"🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 Уста: {master_name}\n\n"
            "Ишни бошлаш мумкин.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔵 Ишни бошлаш",
                            callback_data=f"start:{order_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Бекор қилиш",
                            callback_data=f"cancel:{order_id}",
                        )
                    ],
                ]
            ),
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    f"☎️ Диспетчер: {DISPATCHER_PHONE}"
                ),
            )
        except Exception:
            logger.exception("Customer notification error")

        return

    # =====================================================
    # REJECT
    # =====================================================

    if action == "reject":

        if order["status"] != "open":
            await query.answer(
                "⚠️ Буюртма аллақачон ўзгарган.",
                show_alert=True,
            )
            return

        await update_order_status(
            order_id,
            "rejected",
            master.id,
            master.full_name,
        )

        await query.edit_message_text(
            f"🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 {master.full_name}"
        )

        return

    # =====================================================
    # START
    # =====================================================

    if action == "start":

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )
            return

        if order["status"] != "accepted":
            return

        await update_order_status(
            order_id,
            "in_progress",
            master.id,
            master.full_name,
        )

        await query.edit_message_text(
            f"🔵 ИШ ЖАРАЁНИДА\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 {master.full_name}\n\n"
            "Иш тугаганда якунланг.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ишни якунлаш",
                            callback_data=f"complete:{order_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Бекор қилиш",
                            callback_data=f"cancel:{order_id}",
                        )
                    ],
                ]
            ),
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🔵 Буюртма №{order_id} бўйича иш бошланди.\n\n"
                    f"👨‍🔧 Уста: {master.full_name}"
                ),
            )
        except Exception:
            pass

        return

    # =====================================================
    # COMPLETE
    # =====================================================

    if action == "complete":

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга тегишли эмас.",
                show_alert=True,
            )
            return

        if order["status"] != "in_progress":
            return

        await update_order_status(
            order_id,
            "completed",
            master.id,
            master.full_name,
        )

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE masters
                SET completed_orders =
                    completed_orders + 1
                WHERE telegram_id = $1
                """,
                master.id,
            )

        await query.edit_message_text(
            f"✅ ИШ ЯКУНЛАНДИ\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 {master.full_name}\n\n"
            "⭐ Мижоздан рейтинг сўралди."
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"✅ Буюртма №{order_id} якунланди.\n\n"
                    f"👨‍🔧 Уста: {master.full_name}\n\n"
                    "⭐ Устани баҳоланг:"
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⭐ 1",
                                callback_data=f"rate:{order_id}:1",
                            ),
                            InlineKeyboardButton(
                                "⭐⭐ 2",
                                callback_data=f"rate:{order_id}:2",
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐ 3",
                                callback_data=f"rate:{order_id}:3",
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐⭐ 4",
                                callback_data=f"rate:{order_id}:4",
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐⭐⭐ 5",
                                callback_data=f"rate:{order_id}:5",
                            ),
                        ]
                    ]
                ),
            )
        except Exception:
            pass

        return

    # =====================================================
    # CANCEL
    # =====================================================

    if action == "cancel":

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга тегишли эмас.",
                show_alert=True,
            )
            return

        await update_order_status(
            order_id,
            "cancelled",
            master.id,
            master.full_name,
        )

        await query.edit_message_text(
            f"❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 {master.full_name}"
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"❌ Буюртма №{order_id} бекор қилинди.\n\n"
                    f"☎️ Диспетчер: {DISPATCHER_PHONE}"
                ),
            )
        except Exception:
            pass

        return

    # =====================================================
    # ASSIGN MENU
    # =====================================================

    if action == "assign":

        if master.id != ADMIN_ID:
            await query.answer(
                "❌ Фақат админ.",
                show_alert=True,
            )
            return

        await show_assign_menu(
            query,
            order_id,
        )

        return

    # =====================================================
    # SET MASTER
    # =====================================================

    if action == "setmaster":

        if master.id != ADMIN_ID:
            await query.answer(
                "❌ Фақат админ.",
                show_alert=True,
            )
            return

        if len(parts) != 3:
            return

        try:
            master_id = int(parts[2])
        except ValueError:
            return

        selected = await get_master_by_id(master_id)

        if not selected:
            await query.answer(
                "❌ Уста топилмади.",
                show_alert=True,
            )
            return

        await assign_master(
            order_id,
            master_id,
            selected["name"],
        )

        await update_order_status(
            order_id,
            "accepted",
            ADMIN_ID,
            "ADMIN",
        )

        await query.edit_message_text(
            f"🟡 БУЮРТМА БИРИКТИРИЛДИ\n\n"
            f"🔢 #{order_id}\n"
            f"👨‍🔧 Уста: {selected['name']}"
        )

        if selected["telegram_id"]:

            try:
                await context.bot.send_message(
                    chat_id=selected["telegram_id"],
                    text=(
                        "🆕 СИЗГА БУЮРТМА БЕРИЛДИ\n\n"
                        f"🔢 #{order_id}\n"
                        f"👤 Мижоз: {order['customer_name']}\n"
                        f"📞 Телефон: {order['phone']}\n"
                        f"🛠 Хизмат: {order['service']}\n"
                        f"📍 Манзил: {order['address']}\n"
                        f"📝 Изоҳ: {order['description']}\n"
                    ),
                )
            except Exception:
                logger.exception(
                    "Master notification error"
                )

        return


# =========================================================
# ADMIN: ADD MASTER START
# =========================================================

async def admin_add_master(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    user_states[ADMIN_ID] = {
        "step": "master_phone"
    }

    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "1️⃣ Устанинг телефон рақамини юборинг:\n\n"
        "Масалан:\n"
        "+998901234567"
    )


# =========================================================
# ADMIN: REMOVE MASTER
# =========================================================

async def admin_remove_master(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    user_states[ADMIN_ID] = {
        "step": "remove_master_phone"
    }

    await update.message.reply_text(
        "➖ УСТАНИ ЎЧИРИШ\n\n"
        "Устанинг телефон рақамини юборинг:"
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(update, context):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    user_id = user.id

    text = (
        update.message.text or ""
    ).strip()

    # =====================================================
    # ADMIN MENU
    # =====================================================

    if user_id == ADMIN_ID:

        if text == "🆕 Янги буюртмалар":
            await show_orders(
                update,
                "open",
                "🆕 ЯНГИ БУЮРТМАЛАР",
            )
            return

        if text == "📋 Барча буюртмалар":
            await show_orders(
                update,
                None,
                "📋 БАРЧА БУЮРТМАЛАР",
            )
            return

        if text == "👤 Мижозлар":
            await show_customers(
                update,
                context,
            )
            return

        if text == "👨‍🔧 Усталар":
            await show_masters(
                update,
                context,
            )
            return

        if text == "➕ Уста қўшиш":
            await admin_add_master(
                update,
                context,
            )
            return

        if text == "➖ Устани ўчириш":
            await admin_remove_master(
                update,
                context,
            )
            return

        if text == "📊 Статистика":
            await show_statistics(
                update,
                context,
            )
            return

        if text == "📈 Ҳисобот":
            await show_reports(
                update,
                context,
            )
            return

        if text == "📢 Хабар тарқатиш":
            user_states[ADMIN_ID] = {
                "step": "broadcast"
            }

            await update.message.reply_text(
                "📢 ХАБАР ТАРҚАТИШ\n\n"
                "Юбориладиган хабарни ёзинг:"
            )
            return

        if text == "💰 Нархлар":
            await show_prices(
                update,
                context,
            )
            return

    # =====================================================
    # MAIN MENU
    # =====================================================

    if text == "🛠 Уста чақириш":
        await start_order(update, context)
        return

    if text == "📋 Хизматлар":
        await services(update, context)
        return

    if text == "📞 Диспетчер":
        await dispatcher_contact(update, context)
        return

    if text == "📋 Буюртмаларим":
        await my_orders(update, context)
        return

    if text == "🔁 Қайта буюртма":
        await repeat_order(update, context)
        return

    # =====================================================
    # STATE
    # =====================================================

    state = user_states.get(user_id)

    if not state:
        await update.message.reply_text(
            "Керакли хизматни менюдан танланг.",
            reply_markup=main_menu(),
        )
        return

    step = state.get("step")

    # =====================================================
    # MASTER PHONE
    # =====================================================

    if step == "master_phone":

        phone = text

        if update.message.contact:
            phone = update.message.contact.phone_number

        phone = normalize_phone(phone)

        if not phone:
            await update.message.reply_text(
                "❌ Телефон рақами нотўғри.\n"
                "Масалан: +998901234567"
            )
            return

        state["phone"] = phone
        state["step"] = "master_name"

        await update.message.reply_text(
            "2️⃣ Устанинг исмини ёзинг:"
        )
        return

    # =====================================================
    # MASTER NAME
    # =====================================================

    if step == "master_name":

        state["name"] = text
        state["step"] = "master_service"

        await update.message.reply_text(
            "3️⃣ Уста қайси хизматни бажаради?\n\n"
            "Масалан: Мебель, Электр, Сантехника"
        )
        return

    # =====================================================
    # MASTER SERVICE
    # =====================================================

    if step == "master_service":

        await add_master(
            phone=state["phone"],
            name=state["name"],
            service=text,
        )

        user_states.pop(
            user_id,
            None,
        )

        await update.message.reply_text(
            "✅ УСТА ҚЎШИЛДИ!\n\n"
            f"👨‍🔧 Исм: {state['name']}\n"
            f"📞 Телефон: {state['phone']}\n"
            f"🛠 Хизмат: {text}\n\n"
            "⚠️ Уста Telegram орқали /start босиб "
            "бот билан боғлангандан кейин Telegram аккаунти "
            "ҳам автоматик боғланади.",
            reply_markup=admin_menu(),
        )
        return

    # =====================================================
    # REMOVE MASTER
    # =====================================================

    if step == "remove_master_phone":

        phone = normalize_phone(text)

        master = await get_master_by_phone(phone)

        if not master:
            await update.message.reply_text(
                "❌ Бу телефон рақами билан уста топилмади."
            )
            return

        await remove_master(phone)

        user_states.pop(
            user_id,
            None,
        )

        await update.message.reply_text(
            "✅ Уста фаол рўйхатдан ўчирилди.\n\n"
            f"👨‍🔧 {master['name']}\n"
            f"📞 {phone}",
            reply_markup=admin_menu(),
        )
        return

    # =====================================================
    # BROADCAST
    # =====================================================

    if step == "broadcast":

        if user_id != ADMIN_ID:
            return

        message_text = text

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT telegram_id
                FROM customers
                WHERE telegram_id IS NOT NULL
                """
            )

        sent = 0
        failed = 0

        for row in rows:

            try:
                await context.bot.send_message(
                    chat_id=row["telegram_id"],
                    text=message_text,
                )
                sent += 1

                await asyncio.sleep(0.05)

            except Exception:
                failed += 1

        user_states.pop(
            user_id,
            None,
        )

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИЛДИ\n\n"
            f"✅ Юборилди: {sent}\n"
            f"❌ Хато: {failed}",
            reply_markup=admin_menu(),
        )
        return

    # =====================================================
    # CUSTOMER NAME
    # =====================================================

    if step == "name":

        state["name"] = text
        state["step"] = "phone"

        await update.message.reply_text(
            "2️⃣ Телефон рақамингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton(
                            "📱 Рақамимни юбориш",
                            request_contact=True,
                        )
                    ]
                ],
                resize_keyboard=True,
            ),
        )
        return

    # =====================================================
    # CUSTOMER PHONE
    # =====================================================

    if step == "phone":

        phone = None

        if update.message.contact:
            phone = update.message.contact.phone_number
        elif text:
            phone = text

        phone = normalize_phone(phone)

        if not phone:
            await update.message.reply_text(
                "📞 Телефон рақамини тўғри юборинг."
            )
            return

        state["phone"] = phone
        state["step"] = "service"

        await update.message.reply_text(
            "3️⃣ Хизматни танланг:",
            reply_markup=service_menu(),
        )
        return

    # =====================================================
    # SERVICE
    # =====================================================

    if step == "service":

        state["service"] = text
        state["price"] = await get_base_price(text)
        state["step"] = "location"

        await update.message.reply_text(
            "4️⃣ Манзилни юборинг.\n\n"
            "📍 Геолокация юборишингиз мумкин:",
            reply_markup=location_keyboard(),
        )
        return

    # =====================================================
    # LOCATION
    # =====================================================

    if step == "location":

        if update.message.location:

            loc = update.message.location

            state["latitude"] = loc.latitude
            state["longitude"] = loc.longitude

            state["address"] = (
                f"Геолокация: "
                f"{loc.latitude}, {loc.longitude}"
            )

            state["step"] = "description"

            await update.message.reply_text(
                "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
            )
            return

        if text == "📍 Манзилни қўлда ёзиш":

            state["step"] = "address"

            await update.message.reply_text(
                "📍 Манзилингизни ёзинг:"
            )
            return

        await update.message.reply_text(
            "📍 Геолокация юборинг ёки "
            "манзилни қўлда ёзишни танланг."
        )
        return

    # =====================================================
    # ADDRESS
    # =====================================================

    if step == "address":

        state["address"] = text
        state["step"] = "description"

        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
        )
        return

    # =====================================================
    # DESCRIPTION
    # =====================================================

    if step == "description":

        state["description"] = text

        username = (
            f"@{user.username}"
            if user.username
            else None
        )

        await save_customer(
            user.id,
            state.get("name"),
            state.get("phone"),
            username,
            state.get("latitude"),
            state.get("longitude"),
        )

        order = {
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
        }

        order_id = await create_order(order)

        await send_order_to_group(
            context,
            order_id,
        )

        user_states.pop(
            user_id,
            None,
        )

        await update.message.reply_text(
            "✅ БУЮРТМАНГИЗ ҚАБУЛ ҚИЛИНДИ!\n\n"
            f"🔢 Буюртма №{order_id}\n"
            "👨‍🔧 Усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            f"☎️ Диспетчер: {DISPATCHER_PHONE}",
            reply_markup=main_menu(),
        )
        return


# =========================================================
# PHONE NORMALIZE
# =========================================================

def normalize_phone(phone):

    if not phone:
        return None

    phone = str(phone).strip()

    phone = re.sub(
        r"[^\d+]",
        "",
        phone,
    )

    if phone.startswith("998"):
        phone = "+" + phone

    if phone.startswith("8") and len(phone) == 10:
        phone = "+998" + phone[1:]

    if not phone.startswith("+"):
        return None

    if not re.fullmatch(
        r"\+998\d{9}",
        phone,
    ):
        return None

    return phone


# =========================================================
# MY ORDERS
# =========================================================

async def my_orders(update, context):

    user = update.effective_user

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM orders
            WHERE customer_id = $1
            ORDER BY id DESC
            LIMIT 10
            """,
            user.id,
        )

    if not rows:
        await update.message.reply_text(
            "📭 Сизда ҳозирча буюртмалар йўқ.",
            reply_markup=main_menu(),
        )
        return

    text = "📋 БУЮРТМАЛАРИМ\n\n"

    status_names = {
        "open": "🆕 Янги",
        "accepted": "🟡 Қабул қилинган",
        "in_progress": "🔵 Иш жараёнида",
        "completed": "✅ Якунланган",
        "cancelled": "❌ Бекор қилинган",
        "rejected": "🚫 Рад этилган",
    }

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"🛠 {row['service']}\n"
            f"📍 {row['address']}\n"
            f"📌 {status_names.get(row['status'], row['status'])}\n"
            f"👨‍🔧 {row['master_name'] or '-'}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=main_menu(),
    )


# =========================================================
# REPEAT ORDER
# =========================================================

async def repeat_order(update, context):

    user = update.effective_user

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE customer_id = $1
            ORDER BY id DESC
            LIMIT 1
            """,
            user.id,
        )

    if not row:
        await update.message.reply_text(
            "📭 Аввалги буюртма топилмади.",
            reply_markup=main_menu(),
        )
        return

    user_states[user.id] = {
        "step": "description",
        "name": row["customer_name"],
        "phone": row["phone"],
        "service": row["service"],
        "address": row["address"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "price": row["price"] or 0,
    }

    await update.message.reply_text(
        "🔁 ҚАЙТА БУЮРТМА\n\n"
        f"🛠 Хизмат: {row['service']}\n"
        f"📍 Манзил: {row['address']}\n\n"
        "📝 Қўшимча изоҳни ёзинг:"
    )


# =========================================================
# SHOW ORDERS
# =========================================================

async def show_orders(
    update,
    status=None,
    title="📋 БУЮРТМАЛАР",
):

    if update.effective_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:

        if status:
            rows = await conn.fetch(
                """
                SELECT *
                FROM orders
                WHERE status = $1
                ORDER BY id DESC
                LIMIT 50
                """,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT *
                FROM orders
                ORDER BY id DESC
                LIMIT 50
                """
            )

    if not rows:
        await update.message.reply_text(
            "📭 Буюртмалар топилмади.",
            reply_markup=admin_menu(),
        )
        return

    text = f"{title}\n\n"

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['customer_name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🛠 {row['service'] or '-'}\n"
            f"📍 {row['address'] or '-'}\n"
            f"📌 {row['status']}\n"
            f"👨‍🔧 {row['master_name'] or '-'}\n"
            f"💰 {row['price'] or 0}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000],
        reply_markup=admin_menu(),
    )


# =========================================================
# STATISTICS
# =========================================================

async def show_statistics(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    s = await get_statistics()

    await update.message.reply_text(
        "📊 USTA 24 ANDIJON\n"
        "ТЎЛИҚ СТАТИСТИКА\n\n"
        f"📋 Жами: {s['total']}\n\n"
        f"🆕 Янги: {s['open']}\n"
        f"🟡 Қабул қилинган: {s['accepted']}\n"
        f"🔵 Иш жараёнида: {s['in_progress']}\n"
        f"✅ Якунланган: {s['completed']}\n"
        f"❌ Бекор қилинган: {s['cancelled']}\n"
        f"🚫 Рад этилган: {s['rejected']}",
        reply_markup=admin_menu(),
    )


# =========================================================
# MASTERS
# =========================================================

async def show_masters(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    rows = await get_active_masters()

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Фаол усталар йўқ.",
            reply_markup=admin_menu(),
        )
        return

    text = "👨‍🔧 УСТАЛАР\n\n"

    for row in rows:

        telegram_status = (
            "🟢 Telegram уланган"
            if row["telegram_id"]
            else "🟡 Telegram уланмаган"
        )

        text += (
            f"👨‍🔧 {row['name']}\n"
            f"📞 {row['phone']}\n"
            f"🛠 {row['service'] or '-'}\n"
            f"⭐ {float(row['rating'] or 0):.1f}\n"
            f"✅ Якунланган: {row['completed_orders']}\n"
            f"{telegram_status}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000],
        reply_markup=admin_menu(),
    )


# =========================================================
# CUSTOMERS
# =========================================================

async def show_customers(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM customers
            ORDER BY id DESC
            LIMIT 50
            """
        )

    if not rows:
        await update.message.reply_text(
            "👤 Мижозлар базаси бўш.",
            reply_markup=admin_menu(),
        )
        return

    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"

    for row in rows:

        text += (
            f"👤 {row['name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🆔 {row['telegram_id']}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000],
        reply_markup=admin_menu(),
    )


# =========================================================
# REPORTS
# =========================================================

async def show_reports(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    day = await get_period_statistics(1)
    week = await get_period_statistics(7)
    month = await get_period_statistics(30)

    await update.message.reply_text(
        "📈 USTA 24 ANDIJON ҲИСОБОТ\n\n"

        "📅 КУНЛИК\n"
        f"📋 Жами: {day['total']}\n"
        f"✅ Якунланган: {day['completed']}\n"
        f"❌ Бекор: {day['cancelled']}\n"
        f"🚫 Рад: {day['rejected']}\n\n"

        "📅 ҲАФТАЛИК\n"
        f"📋 Жами: {week['total']}\n"
        f"✅ Якунланган: {week['completed']}\n"
        f"❌ Бекор: {week['cancelled']}\n"
        f"🚫 Рад: {week['rejected']}\n\n"

        "📅 ОЙЛИК\n"
        f"📋 Жами: {month['total']}\n"
        f"✅ Якунланган: {month['completed']}\n"
        f"❌ Бекор: {month['cancelled']}\n"
        f"🚫 Рад: {month['rejected']}",
        reply_markup=admin_menu(),
    )


# =========================================================
# PRICES
# =========================================================

async def show_prices(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM price_settings
            ORDER BY id
            """
        )

    text = "💰 НАРХ ҲИСОБЛАШ АСОСИ\n\n"

    for row in rows:

        text += (
            f"🛠 {row['service']}\n"
            f"💰 База: {row['base_price']}\n"
            f"📏 Бирлик: {row['unit']}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000],
        reply_markup=admin_menu(),
    )


# =========================================================
# DISPATCHER
# =========================================================

async def dispatcher(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Кириш ҳуқуқи йўқ."
        )
        return

    await update.message.reply_text(
        "👑 USTA 24 ANDIJON\n"
        "АДМИН / ДИСПЕТЧЕР БОШҚАРУВИ",
        reply_markup=admin_menu(),
    )


# =========================================================
# CHAT ID
# =========================================================

async def chat_id(update, context):

    await update.message.reply_text(
        f"🆔 Chat ID: {update.effective_chat.id}"
    )


# =========================================================
# REMINDER JOB
# =========================================================

async def reminder_job(context):

    if not db_pool:
        return

    try:

        async with db_pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT *
                FROM orders
                WHERE status = 'accepted'
                  AND accepted_at <
                      NOW() - INTERVAL '2 hours'
                LIMIT 20
                """
            )

        for row in rows:

            try:

                await context.bot.send_message(
                    chat_id=row["customer_id"],
                    text=(
                        "🔔 USTA 24 ЭСЛАТМА\n\n"
                        f"🔢 Буюртма №{row['id']}\n"
                        "👨‍🔧 Уста буюртмани қабул қилган.\n"
                        "⏳ Иш ҳали бошланмаган.\n\n"
                        f"☎️ Диспетчер: {DISPATCHER_PHONE}"
                    ),
                )

                async with db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO notifications (
                            order_id,
                            customer_id,
                            notification_type
                        )
                        VALUES ($1,$2,$3)
                        """,
                        row["id"],
                        row["customer_id"],
                        "accepted_reminder",
                    )

            except Exception:
                logger.exception(
                    "Reminder customer error"
                )

    except Exception:
        logger.exception(
            "Reminder job error"
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update, context):

    logger.error(
        "BOT XATOSI",
        exc_info=context.error,
    )


# =========================================================
# RUN BOT
# =========================================================

async def run_bot(application):

    await init_database()

    await application.initialize()

    await application.start()

    # =====================================================
    # JOB QUEUE
    # =====================================================

    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue mavjud emas! "
            "requirements.txt da "
            "python-telegram-bot[job-queue] kerak."
        )

    application.job_queue.run_repeating(
        reminder_job,
        interval=1800,
        first=60,
        name="usta24_reminder",
    )

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    logger.info(
        "======================================"
    )
    logger.info(
        "✅ USTA 24 ANDIJON PRO FULL ISHLADI"
    )
    logger.info(
        "☎️ Dispatcher: %s",
        DISPATCHER_PHONE,
    )
    logger.info(
        "======================================"
    )

    try:

        while True:
            await asyncio.sleep(3600)

    finally:

        await application.updater.stop()
        await application.stop()
        await application.shutdown()

        if db_pool:
            await db_pool.close()


# =========================================================
# MAIN
# =========================================================

def main():

    logger.info(
        "======================================"
    )
    logger.info(
        "USTA 24 ANDIJON PRO FULL START"
    )
    logger.info(
        "ADMIN_ID = %s",
        ADMIN_ID,
    )
    logger.info(
        "MASTERS_GROUP_ID = %s",
        MASTERS_GROUP_ID,
    )
    logger.info(
        "DATABASE = %s",
        bool(DATABASE_URL),
    )
    logger.info(
        "DISPATCHER = %s",
        DISPATCHER_PHONE,
    )
    logger.info(
        "======================================"
    )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # =====================================================
    # COMMANDS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "dispatcher",
            dispatcher,
        )
    )

    application.add_handler(
        CommandHandler(
            "id",
            chat_id,
        )
    )

    # =====================================================
    # CALLBACK
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            callback_handler,
        )
    )

    # =====================================================
    # LOCATION / CONTACT
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.LOCATION | filters.CONTACT,
            handle_message,
        )
    )

    # =====================================================
    # TEXT
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    application.add_error_handler(
        error_handler
    )

    # =====================================================
    # FLASK
    # =====================================================

    flask_thread = Thread(
        target=run_flask,
        daemon=True,
    )

    flask_thread.start()

    logger.info(
        "✅ Flask server ishga tushdi."
    )

    # =====================================================
    # ASYNC
    # =====================================================

    asyncio.run(
        run_bot(application)
    )


if __name__ == "__main__":
    main()
