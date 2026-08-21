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
# USTA 24 PRO
# MAIN.PY
# =========================================================

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

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")


try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID.strip())
    ADMIN_ID = int(ADMIN_ID.strip())
except ValueError:
    raise RuntimeError(
        "ADMIN_ID va MASTERS_GROUP_ID raqam bo‘lishi kerak!"
    )


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 PRO BOT ISHLAYAPTI!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
    )


# =========================================================
# DATABASE
# =========================================================

db_pool = None


async def init_database():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL topilmadi!"
        )

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        # -------------------------------------------------
        # CUSTOMERS
        # -------------------------------------------------

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

        # -------------------------------------------------
        # EXISTING CUSTOMER TABLE COMPATIBILITY
        # -------------------------------------------------

        for column_sql in [
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
        ]:
            try:
                await conn.execute(column_sql)
            except Exception:
                pass

        # -------------------------------------------------
        # ORDERS
        # -------------------------------------------------

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
            """
        )

        # -------------------------------------------------
        # OLD ORDERS COMPATIBILITY
        # -------------------------------------------------

        order_columns = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC DEFAULT 0",
        ]

        for sql in order_columns:
            try:
                await conn.execute(sql)
            except Exception:
                pass

        # -------------------------------------------------
        # MASTERS
        # -------------------------------------------------

        await conn.execute(
            """
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
            """
        )

        # -------------------------------------------------
        # ORDER HISTORY
        # -------------------------------------------------

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

        # -------------------------------------------------
        # REVIEWS
        # -------------------------------------------------

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                order_id INTEGER UNIQUE NOT NULL,
                customer_id BIGINT NOT NULL,
                master_id BIGINT,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        # -------------------------------------------------
        # PRICE SETTINGS
        # -------------------------------------------------

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

        # -------------------------------------------------
        # NOTIFICATIONS
        # -------------------------------------------------

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

        # -------------------------------------------------
        # DEFAULT PRICES
        # -------------------------------------------------

        services = [
            ("🪑 Mebel", 0),
            ("🚚 Yuk tashish / ko‘chirish", 0),
            ("🔩 Santexnika", 0),
            ("⚡ Elektr", 0),
            ("🔥 Payvandlash", 0),
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

    logger.info("✅ PostgreSQL muvaffaqiyatli ulandi.")
    logger.info("✅ USTA 24 PRO database tayyor.")


# =========================================================
# CUSTOMER FUNCTIONS
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
                name = COALESCE($2, customers.name),
                phone = COALESCE($3, customers.phone),
                username = COALESCE($4, customers.username),
                latitude = COALESCE($5, customers.latitude),
                longitude = COALESCE($6, customers.longitude),
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
# ORDER FUNCTIONS
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

        timestamp_map = {
            "accepted": "accepted_at",
            "in_progress": "started_at",
            "completed": "completed_at",
            "cancelled": "cancelled_at",
            "rejected": "rejected_at",
        }

        timestamp_column = timestamp_map.get(
            new_status
        )

        if timestamp_column:

            await conn.execute(
                f"""
                UPDATE orders
                SET
                    status = $1,
                    {timestamp_column} = NOW()
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
# MASTER FUNCTIONS
# =========================================================

async def add_master(
    telegram_id,
    name,
    phone=None,
    username=None,
    service=None,
):
    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO masters (
                telegram_id,
                name,
                phone,
                username,
                service
            )
            VALUES ($1,$2,$3,$4,$5)

            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = $2,
                phone = $3,
                username = $4,
                service = $5,
                active = TRUE
            """,
            telegram_id,
            name,
            phone,
            username,
            service,
        )


async def remove_master(telegram_id):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE masters
            SET active = FALSE
            WHERE telegram_id = $1
            """,
            telegram_id,
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


async def get_master(telegram_id):
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
# STATISTICS
# =========================================================

async def statistics():
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
            status = row["status"]

            if status in result:
                result[status] = int(
                    row["count"]
                )

        return result


async def master_statistics():
    async with db_pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT
                m.id,
                m.telegram_id,
                m.name,
                m.phone,
                m.username,
                m.rating,
                m.rating_count,
                m.completed_orders,
                COUNT(o.id) AS total_orders
            FROM masters m
            LEFT JOIN orders o
                ON o.master_id = m.telegram_id
            GROUP BY
                m.id,
                m.telegram_id,
                m.name,
                m.phone,
                m.username,
                m.rating,
                m.rating_count,
                m.completed_orders
            ORDER BY
                m.completed_orders DESC
            """
        )


async def period_statistics(days):
    async with db_pool.acquire() as conn:

        since = datetime.now() - timedelta(
            days=days
        )

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
    comment,
):
    async with db_pool.acquire() as conn:

        master_id = await conn.fetchval(
            """
            SELECT master_id
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )

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
                rating = $4,
                comment = $5
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
                    rating = COALESCE($1,0),
                    rating_count = $2
                WHERE telegram_id = $3
                """,
                float(avg_rating or 0),
                int(count or 0),
                master_id,
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
# MENUS
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Уста чақириш"],
            ["📋 Хизматлар", "📞 Алоқа"],
            ["🔁 Қайта буюртма"],
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
            ["🆕 Янги буюртмалар"],
            ["📋 Барча буюртмалар"],
            ["👤 Мижозлар"],
            ["👨‍🔧 Усталар"],
            ["📊 Статистика"],
            ["📈 Ҳисобот"],
            ["📢 Хабар тарқатиш"],
        ],
        resize_keyboard=True,
    )


# =========================================================
# USER STATES
# =========================================================

user_states = {}


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 хизматларига хуш келибсиз!\n\n"
        "🔧 Уй ва офис учун усталар хизмати.\n"
        "📍 Андижон шаҳри\n\n"
        "Керакли хизматни танланг:",
        reply_markup=main_menu(),
    )


# =========================================================
# SERVICES
# =========================================================

async def services(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🛠 USTA 24 ХИЗМАТЛАРИ\n\n"
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
        "🔨 Бошқа хизмат",
        reply_markup=main_menu(),
    )


# =========================================================
# CONTACT
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "☎️ +998 77 069 00 03\n"
        "📍 Андижон шаҳри",
        reply_markup=main_menu(),
    )


# =========================================================
# START ORDER
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not user:
        return

    customer = await get_customer(
        user.id
    )

    user_states[user.id] = {
        "step": "name"
    }

    if customer and customer["name"]:
        user_states[user.id]["name"] = (
            customer["name"]
        )

        if customer["phone"]:
            user_states[user.id]["phone"] = (
                customer["phone"]
            )

        await update.message.reply_text(
            f"👋 Салом, {customer['name']}!\n\n"
            "Янги буюртма бошлаймиз.\n\n"
            "🛠 Хизматни танланг:",
            reply_markup=service_menu(),
        )

        user_states[user.id]["step"] = "service"

        return

    await update.message.reply_text(
        "📝 Буюртма бериш\n\n"
        "1️⃣ Исмингизни ёзинг:"
    )


# =========================================================
# LOCATION BUTTON
# =========================================================

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
# SEND ORDER TO GROUP
# =========================================================

async def send_order_to_group(
    update,
    context,
    order_id,
):
    order = await get_order(order_id)

    if not order:
        return

    location_text = "-"

    if (
        order["latitude"] is not None
        and order["longitude"] is not None
    ):
        location_text = (
            f"https://maps.google.com/"
            f"?q={order['latitude']},"
            f"{order['longitude']}"
        )

    text = (
        "🆕 USTA 24 — ЯНГИ БУЮРТМА\n\n"
        f"🔢 Буюртма: #{order_id}\n"
        f"👤 Мижоз: {order['customer_name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"🗺 Геолокация: {location_text}\n"
        f"📝 Изоҳ: {order['description']}\n"
        f"💰 Нарх асоси: {order['price']}\n\n"
        "👨‍🔧 Уста танланг:"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "👨‍🔧 Ўзимга олиш",
                    callback_data=f"take:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Бошқа устага",
                    callback_data=f"assign:{order_id}",
                ),
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"reject:{order_id}",
                ),
            ],
        ]
    )

    await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )


# =========================================================
# CALLBACK
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    if ":" not in data:
        return

    action, value = data.split(":", 1)

    try:
        order_id = int(value)
    except ValueError:
        return

    master = query.from_user

    # -----------------------------------------------------
    # TAKE ORDER
    # -----------------------------------------------------

    if action == "take":

        order = await get_order(order_id)

        if not order:
            await query.answer(
                "❌ Буюртма топилмади.",
                show_alert=True,
            )
            return

        if order["status"] != "open":
            await query.answer(
                "⚠️ Бу буюртма аллақачон олинган.",
                show_alert=True,
            )
            return

        master_name = (
            f"@{master.username}"
            if master.username
            else master.full_name
        )

        await add_master(
            master.id,
            master.full_name,
            username=(
                f"@{master.username}"
                if master.username
                else None
            ),
        )

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
            "🔵 Ишни бошлаш учун тугмани босинг.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔵 Ишни бошлаш",
                            callback_data=(
                                f"start:{order_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Бекор қилиш",
                            callback_data=(
                                f"cancel:{order_id}"
                            ),
                        )
                    ],
                ]
            ),
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🟡 Буюртмангиз №{order_id} "
                    "қабул қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "☎️ +998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception(
                "Mijozga xabar yuborilmadi."
            )

        return

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    if action == "start":

        order = await get_order(order_id)

        if not order:
            return

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )
            return

        await update_order_status(
            order_id,
            "in_progress",
            master.id,
            master.full_name,
        )

        await query.edit_message_text(
            f"🔵 ИШ ЖАРАЁНИДА\n\n"
            f"🔢 Буюртма: #{order_id}\n"
            f"👨‍🔧 Уста: {master.full_name}\n\n"
            "Иш тугаганда тугмани босинг.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ишни якунлаш",
                            callback_data=(
                                f"complete:{order_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Бекор қилиш",
                            callback_data=(
                                f"cancel:{order_id}"
                            ),
                        )
                    ],
                ]
            ),
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🔵 Буюртма №{order_id} бўйича "
                    "иш бошланди.\n\n"
                    f"👨‍🔧 Уста: {master.full_name}"
                ),
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # COMPLETE
    # -----------------------------------------------------

    if action == "complete":

        order = await get_order(order_id)

        if not order:
            return

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True,
            )
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
            f"🔢 Буюртма: #{order_id}\n"
            f"👨‍🔧 Уста: {master.full_name}\n\n"
            "⭐ Мижоздан рейтинг сўралади."
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"✅ Буюртмангиз №{order_id} якунланди.\n\n"
                    f"👨‍🔧 Уста: {master.full_name}\n\n"
                    "⭐ Хизматни баҳоланг:"
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⭐ 1",
                                callback_data=(
                                    f"rate:{order_id}:1"
                                ),
                            ),
                            InlineKeyboardButton(
                                "⭐⭐ 2",
                                callback_data=(
                                    f"rate:{order_id}:2"
                                ),
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐ 3",
                                callback_data=(
                                    f"rate:{order_id}:3"
                                ),
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐⭐ 4",
                                callback_data=(
                                    f"rate:{order_id}:4"
                                ),
                            ),
                            InlineKeyboardButton(
                                "⭐⭐⭐⭐⭐ 5",
                                callback_data=(
                                    f"rate:{order_id}:5"
                                ),
                            ),
                        ]
                    ]
                ),
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    if action == "cancel":

        order = await get_order(order_id)

        if not order:
            return

        if order["master_id"] != master.id:
            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
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
            f"👨‍🔧 Уста: {master.full_name}"
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"❌ Буюртмангиз №{order_id} "
                    "бекор қилинди.\n\n"
                    "Янги буюртма беришингиз мумкин."
                ),
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # REJECT
    # -----------------------------------------------------

    if action == "reject":

        order = await get_order(order_id)

        if not order:
            return

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
            f"👨‍🔧 Рад этган: {master.full_name}"
        )

        try:
            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"⚠️ Буюртмангиз №{order_id} "
                    "ушбу уста томонидан қабул қилинмади.\n\n"
                    "Диспетчер бошқа уста топишга ҳаракат қилади."
                ),
            )
        except Exception:
            pass

        return

    # -----------------------------------------------------
    # RATING
    # -----------------------------------------------------

    if action == "rate":

        parts = value.split(":")

        if len(parts) != 2:
            return

        try:
            review_order_id = int(parts[0])
            rating = int(parts[1])
        except ValueError:
            return

        await save_review(
            review_order_id,
            master.id,
            rating,
            None,
        )

        await query.edit_message_text(
            f"⭐ Рейтинг қабул қилинди: {rating}/5\n\n"
            "Раҳмат!"
        )

        return


# =========================================================
# ORDER MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    user_id = user.id

    text = (
        update.message.text or ""
    ).strip()

    # -----------------------------------------------------
    # MAIN MENU
    # -----------------------------------------------------

    if text == "🛠 Уста чақириш":
        await start_order(update, context)
        return

    if text == "📋 Хизматлар":
        await services(update, context)
        return

    if text == "📞 Алоқа":
        await contact(update, context)
        return

    # -----------------------------------------------------
    # ADMIN
    # -----------------------------------------------------

    if user_id == ADMIN_ID:

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

        if text == "👨‍🔧 Усталар":
            await show_masters(
                update,
                context,
            )
            return

        if text == "👤 Мижозлар":
            await show_customers(
                update,
                context,
            )
            return

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

    # -----------------------------------------------------
    # STATE
    # -----------------------------------------------------

    state = user_states.get(user_id)

    if not state:
        await update.message.reply_text(
            "Мениюдан хизматни танланг.",
            reply_markup=main_menu(),
        )
        return

    step = state.get("step")

    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # PHONE
    # -----------------------------------------------------

    if step == "phone":

        phone = None

        if update.message.contact:
            phone = (
                update.message.contact.phone_number
            )
        elif text:
            phone = text

        if not phone:
            await update.message.reply_text(
                "📞 Телефон рақамини юборинг."
            )
            return

        state["phone"] = phone
        state["step"] = "service"

        await update.message.reply_text(
            "3️⃣ Хизматни танланг:",
            reply_markup=service_menu(),
        )

        return

    # -----------------------------------------------------
    # SERVICE
    # -----------------------------------------------------

    if step == "service":

        state["service"] = text
        state["step"] = "location"

        price = await get_base_price(
            text
        )

        state["price"] = price

        await update.message.reply_text(
            "4️⃣ Манзилни юборинг.\n\n"
            "📍 Геолокацияни юборишингиз мумкин:",
            reply_markup=location_keyboard(),
        )

        return

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    if step == "location":

        if update.message.location:

            location = update.message.location

            state["latitude"] = (
                location.latitude
            )

            state["longitude"] = (
                location.longitude
            )

            state["address"] = (
                f"Геолокация: "
                f"{location.latitude}, "
                f"{location.longitude}"
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
            "манзилни қўлда ёзинг."
        )

        return

    # -----------------------------------------------------
    # ADDRESS
    # -----------------------------------------------------

    if step == "address":

        state["address"] = text
        state["step"] = "description"

        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қисқача маълумот ёзинг:"
        )

        return

    # -----------------------------------------------------
    # DESCRIPTION
    # -----------------------------------------------------

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

        order_id = await create_order(
            order
        )

        await send_order_to_group(
            update,
            context,
            order_id,
        )

        user_states.pop(
            user_id,
            None,
        )

        await update.message.reply_text(
            f"✅ Буюртмангиз қабул қилинди!\n\n"
            f"🔢 Буюртма №{order_id}\n\n"
            "👨‍🔧 Усталар гуруҳига юборилди.\n"
            "📞 Тез орада сиз билан боғланишади.\n\n"
            "☎️ +998 77 069 00 03",
            reply_markup=main_menu(),
        )

        return


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
                LIMIT 30
                """,
                status,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT *
                FROM orders
                ORDER BY id DESC
                LIMIT 30
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
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# STATISTICS
# =========================================================

async def show_statistics(
    update,
    context,
):
    if update.effective_user.id != ADMIN_ID:
        return

    s = await statistics()

    await update.message.reply_text(
        "📊 USTA 24 ТЎЛИҚ СТАТИСТИКА\n\n"
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
# MASTER STATISTICS
# =========================================================

async def show_masters(
    update,
    context,
):
    if update.effective_user.id != ADMIN_ID:
        return

    rows = await master_statistics()

    if not rows:
        await update.message.reply_text(
            "👨‍🔧 Ҳозирча усталар йўқ.",
            reply_markup=admin_menu(),
        )
        return

    text = "👨‍🔧 УСТАЛАР СТАТИСТИКАСИ\n\n"

    for row in rows:

        text += (
            f"👨‍🔧 {row['name']}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"📋 Буюртмалар: {row['total_orders']}\n"
            f"✅ Якунланган: {row['completed_orders']}\n"
            f"⭐ Рейтинг: "
            f"{float(row['rating'] or 0):.1f}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# CUSTOMERS
# =========================================================

async def show_customers(
    update,
    context,
):
    if update.effective_user.id != ADMIN_ID:
        return

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM customers
            ORDER BY id DESC
            LIMIT 30
            """
        )

    if not rows:
        await update.message.reply_text(
            "👤 Мижозлар базаси бўш."
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
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# REPORTS
# =========================================================

async def show_reports(
    update,
    context,
):
    if update.effective_user.id != ADMIN_ID:
        return

    day = await period_statistics(1)
    week = await period_statistics(7)
    month = await period_statistics(30)

    await update.message.reply_text(
        "📈 USTA 24 ҲИСОБОТ\n\n"

        "📅 КУНЛИК\n"
        f"📋 Жами: {day['total']}\n"
        f"✅ Якунланган: {day['completed']}\n"
        f"❌ Бекор: {day['cancelled']}\n\n"

        "📅 ҲАФТАЛИК\n"
        f"📋 Жами: {week['total']}\n"
        f"✅ Якунланган: {week['completed']}\n"
        f"❌ Бекор: {week['cancelled']}\n\n"

        "📅 ОЙЛИК\n"
        f"📋 Жами: {month['total']}\n"
        f"✅ Якунланган: {month['completed']}\n"
        f"❌ Бекор: {month['cancelled']}\n",
        reply_markup=admin_menu(),
    )


# =========================================================
# REPEAT ORDER
# =========================================================

async def repeat_order(
    update,
    context,
):
    user = update.effective_user

    if not user:
        return

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
            "📭 Сизда аввалги буюртма топилмади."
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
        "🔁 Қайта буюртма\n\n"
        f"🛠 Хизмат: {row['service']}\n"
        f"📍 Манзил: {row['address']}\n\n"
        "📝 Қўшимча изоҳни ёзинг:"
    )


# =========================================================
# DISPATCHER COMMAND
# =========================================================

async def dispatcher(
    update,
    context,
):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Кириш ҳуқуқи йўқ."
        )
        return

    await update.message.reply_text(
        "👑 USTA 24 АДМИН БОШҚАРУВИ",
        reply_markup=admin_menu(),
    )


# =========================================================
# ID COMMAND
# =========================================================

async def chat_id(
    update,
    context,
):
    await update.message.reply_text(
        f"🆔 Chat ID: {update.effective_chat.id}"
    )


# =========================================================
# ERROR
# =========================================================

async def error_handler(
    update,
    context,
):
    logger.error(
        "BOT XATOSI",
        exc_info=context.error,
    )


# =========================================================
# AUTOMATIC REMINDERS
# =========================================================

async def reminder_job(
    context: ContextTypes.DEFAULT_TYPE,
):
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
                        f"🔔 Эслатма\n\n"
                        f"Буюртма №{row['id']} "
                        "бўйича уста ҳали ишни бошламаган.\n\n"
                        "☎️ USTA 24\n"
                        "+998 77 069 00 03"
                    ),
                )

            except Exception:
                pass

    except Exception:
        logger.exception(
            "Reminder xatosi."
        )


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

    # 30 daqiqada reminder tekshiradi
    application.job_queue.run_repeating(
        reminder_job,
        interval=1800,
        first=60,
    )

    logger.info(
        "✅ USTA 24 PRO Telegram polling ishga tushdi."
    )

    try:

        while True:
            await asyncio.sleep(3600)

    finally:

        await application.updater.stop()
        await application.stop()
        await application.shutdown()


def main():

    logger.info(
        "================================="
    )
    logger.info(
        "USTA 24 PRO BOT START"
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
        "DATABASE_URL = %s",
        bool(DATABASE_URL),
    )
    logger.info(
        "================================="
    )

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

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

    application.add_handler(
        CallbackQueryHandler(
            callback_handler,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.LOCATION | filters.CONTACT,
            handle_message,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    application.add_error_handler(
        error_handler
    )

    flask_thread = Thread(
        target=run_flask,
        daemon=True,
    )

    flask_thread.start()

    logger.info(
        "✅ Flask server ishga tushdi."
    )

    asyncio.run(
        run_bot(application)
    )


if __name__ == "__main__":
    main()
