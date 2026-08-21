# ============================================================
# USTA 24 PRO BOT
# SINGLE MAIN.PY
# PostgreSQL + Telegram
# python-telegram-bot 22.3
# ============================================================

import os
import logging
import asyncio
from threading import Thread

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
    ConversationHandler,
    filters,
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MASTERS_GROUP_ID = int(
    os.getenv("MASTERS_GROUP_ID", "0")
)

DISPATCHER_ID = int(
    os.getenv("DISPATCHER_ID", "0")
)


# ============================================================
# CHECK CONFIG
# ============================================================

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi!")


# ============================================================
# GLOBAL DATABASE
# ============================================================

db_pool = None


# ============================================================
# FLASK
# ============================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI"


@flask_app.route("/health")
def health():
    return "OK"


def run_flask():
    flask_app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )


# ============================================================
# DATABASE CONNECTION
# ============================================================

async def init_db():

    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
    )

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id BIGINT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                username TEXT,
                services TEXT,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT,
                customer_name TEXT,
                phone TEXT,
                service TEXT,
                address TEXT,
                description TEXT,
                username TEXT,
                status TEXT DEFAULT 'new',
                master_id BIGINT,
                master_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT,
                customer_id BIGINT,
                master_id BIGINT,
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    logger.info("PostgreSQL tayyor")


# ============================================================
# DATABASE HELPERS
# ============================================================

async def save_customer(
    user_id,
    name=None,
    phone=None,
    username=None,
):

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO customers
            (id, name, phone, username)
            VALUES ($1, $2, $3, $4)

            ON CONFLICT (id)
            DO UPDATE SET
                name = COALESCE($2, customers.name),
                phone = COALESCE($3, customers.phone),
                username = COALESCE($4, customers.username)
            """,
            user_id,
            name,
            phone,
            username,
        )


async def create_order(
    customer_id,
    customer_name,
    phone,
    service,
    address,
    description,
    username,
):

    async with db_pool.acquire() as conn:

        order_id = await conn.fetchval(
            """
            INSERT INTO orders
            (
                customer_id,
                customer_name,
                phone,
                service,
                address,
                description,
                username
            )
            VALUES
            ($1,$2,$3,$4,$5,$6,$7)

            RETURNING id
            """,
            customer_id,
            customer_name,
            phone,
            service,
            address,
            description,
            username,
        )

        return order_id


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
    status,
):

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            UPDATE orders
            SET
                status = $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
            """,
            status,
            order_id,
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
                master_name = $2,
                status = 'assigned',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $3
            """,
            master_id,
            master_name,
            order_id,
        )


async def get_masters():

    async with db_pool.acquire() as conn:

        return await conn.fetch(
            """
            SELECT *
            FROM masters
            WHERE active = TRUE
            ORDER BY id
            """
        )


async def get_master(master_id):

    async with db_pool.acquire() as conn:

        return await conn.fetchrow(
            """
            SELECT *
            FROM masters
            WHERE telegram_id = $1
            """,
            master_id,
        )


async def add_master_db(
    telegram_id,
    name,
    phone,
    username,
    services,
):

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO masters
            (
                telegram_id,
                name,
                phone,
                username,
                services
            )
            VALUES
            ($1,$2,$3,$4,$5)

            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = $2,
                phone = $3,
                username = $4,
                services = $5,
                active = TRUE
            """,
            telegram_id,
            name,
            phone,
            username,
            services,
        )


async def delete_master_db(master_id):

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            UPDATE masters
            SET active = FALSE
            WHERE telegram_id = $1
            """,
            master_id,
        )


# ============================================================
# MENUS
# ============================================================

def client_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("🛠 Уста чақириш"),
            ],
            [
                KeyboardButton("📋 Хизматлар"),
                KeyboardButton("📞 Алоқа"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("👤 Мижозлар"),
                KeyboardButton("👨‍🔧 Усталар"),
            ],
            [
                KeyboardButton("➕ Уста қўшиш"),
                KeyboardButton("👨‍🔧 Усталар рўйхати"),
            ],
            [
                KeyboardButton("🗑 Устани ўчириш"),
                KeyboardButton("📊 Статистика"),
            ],
            [
                KeyboardButton("📢 Хабар тарқатиш"),
            ],
            [
                KeyboardButton("⬅️ Бош меню"),
            ],
        ],
        resize_keyboard=True,
    )


def masters_menu():

    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("➕ Уста қўшиш"),
            ],
            [
                KeyboardButton("👨‍🔧 Усталар рўйхати"),
            ],
            [
                KeyboardButton("🗑 Устани ўчириш"),
            ],
            [
                KeyboardButton("⬅️ Админ меню"),
            ],
        ],
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    await save_customer(
        user.id,
        user.full_name,
        None,
        user.username,
    )

    context.user_data.clear()

    if user.id == ADMIN_ID:

        await update.message.reply_text(
            "👑 USTA 24 АДМИН\n\n"
            "Админ меню:",
            reply_markup=admin_menu(),
        )

        return

    await update.message.reply_text(
        "🏠 USTA 24 га хуш келибсиз!\n\n"
        "Уйингизга ишончли уста чақиринг.",
        reply_markup=client_menu(),
    )


# ============================================================
# ADMIN START
# ============================================================

async def admin_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return

    await update.message.reply_text(
        "👑 USTA 24 АДМИН\n\n"
        "Бўлимни танланг:",
        reply_markup=admin_menu(),
    )


# ============================================================
# SERVICES
# ============================================================

async def show_services(
    update,
    context,
):

    await update.message.reply_text(
        "📋 ХИЗМАТЛАР\n\n"
        "🪑 Мебель йиғиш\n"
        "🔧 Мебель таъмири\n"
        "🍽 Кухня мебель\n"
        "🚪 Шкаф йиғиш\n"
        "🛏 Кровать йиғиш\n"
        "🪑 Стол-стул йиғиш\n"
        "📦 Мебель ечиш/йиғиш\n"
        "🚚 Мебель ташиш\n"
        "🏠 Уй кўчириш\n\n"
        "Керакли хизматни буюртма орқали танланг."
    )


# ============================================================
# CONTACT
# ============================================================

async def show_contact(
    update,
    context,
):

    await update.message.reply_text(
        "📞 АЛОҚА\n\n"
        "USTA 24\n"
        "📱 Буюртма бериш учун:\n"
        "🛠 «Уста чақириш» тугмасини босинг."
    )


# ============================================================
# CLIENT ORDER START
# ============================================================

async def order_start(
    update,
    context,
):

    context.user_data["order"] = {}

    await update.message.reply_text(
        "1️⃣ Исмингизни ёзинг:"
    )

    context.user_data["order_step"] = "name"


# ============================================================
# CLIENT TEXT HANDLER
# ============================================================

async def client_handler(
    update,
    context,
):

    if not update.message:
        return

    text = update.message.text or ""

    user = update.effective_user

    # --------------------------------------------------------
    # MAIN BUTTONS
    # --------------------------------------------------------

    if text == "🛠 Уста чақириш":

        await order_start(
            update,
            context,
        )

        return

    if text == "📋 Хизматлар":

        await show_services(
            update,
            context,
        )

        return

    if text == "📞 Алоқа":

        await show_contact(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # ORDER PROCESS
    # --------------------------------------------------------

    if context.user_data.get("order_step"):

        order = context.user_data.setdefault(
            "order",
            {},
        )

        step = context.user_data[
            "order_step"
        ]

        # NAME

        if step == "name":

            order["name"] = text

            context.user_data[
                "order_step"
            ] = "phone"

            keyboard = [
                [
                    KeyboardButton(
                        "📱 Телефон рақамимни юбориш",
                        request_contact=True,
                    )
                ]
            ]

            await update.message.reply_text(
                "2️⃣ Телефон рақамингизни юборинг:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )

            return

        # PHONE TEXT

        if step == "phone":

            order["phone"] = text

            context.user_data[
                "order_step"
            ] = "service"

            await update.message.reply_text(
                "3️⃣ Хизмат турини ёзинг:\n\n"
                "Масалан:\n"
                "🪑 Мебель\n"
                "🚚 Мебель ташиш\n"
                "🏠 Уй кўчириш"
            )

            return

        # SERVICE

        if step == "service":

            order["service"] = text

            context.user_data[
                "order_step"
            ] = "address"

            await update.message.reply_text(
                "4️⃣ Манзилингизни ёзинг:"
            )

            return

        # ADDRESS

        if step == "address":

            order["address"] = text

            context.user_data[
                "order_step"
            ] = "description"

            await update.message.reply_text(
                "5️⃣ Қандай иш кераклигини ёзинг:"
            )

            return

        # DESCRIPTION

        if step == "description":

            order["description"] = text

            order_id = await create_order(
                customer_id=user.id,
                customer_name=order["name"],
                phone=order["phone"],
                service=order["service"],
                address=order["address"],
                description=order["description"],
                username=user.username,
            )

            await save_customer(
                user.id,
                order["name"],
                order["phone"],
                user.username,
            )

            context.user_data.clear()

            await update.message.reply_text(
                f"✅ Буюртмангиз қабул қилинди!\n\n"
                f"🔢 Буюртма: #{order_id}\n"
                f"🛠 Хизмат: {order['service']}\n"
                f"📍 Манзил: {order['address']}\n\n"
                "Диспетчер тез орада сиз билан боғланади.",
                reply_markup=client_menu(),
            )

            # SEND TO DISPATCHER

            buttons = [
                [
                    InlineKeyboardButton(
                        "👨‍🔧 Уста танлаш",
                        callback_data=f"assign_{order_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel_{order_id}",
                    )
                ],
            ]

            order_text = (
                "🆕 ЯНГИ БУЮРТМА\n\n"
                f"🔢 Буюртма: #{order_id}\n"
                f"👤 Мижоз: {order['name']}\n"
                f"📞 Телефон: {order['phone']}\n"
                f"🛠 Хизмат: {order['service']}\n"
                f"📍 Манзил: {order['address']}\n"
                f"📝 Изоҳ: {order['description']}\n"
            )

            # GROUP

            try:

                await context.bot.send_message(
                    chat_id=MASTERS_GROUP_ID,
                    text=order_text,
                    reply_markup=InlineKeyboardMarkup(
                        buttons
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Guruhga yuborishda xato: {e}"
                )

            # DISPATCHER

            if DISPATCHER_ID:

                try:

                    await context.bot.send_message(
                        chat_id=DISPATCHER_ID,
                        text=order_text,
                        reply_markup=InlineKeyboardMarkup(
                            buttons
                        ),
                    )

                except Exception as e:

                    logger.error(
                        f"Dispatcherga yuborishda xato: {e}"
                    )

            return


# ============================================================
# CONTACT HANDLER
# ============================================================

async def contact_handler(
    update,
    context,
):

    if not update.message:
        return

    contact = update.message.contact

    if not contact:
        return

    if context.user_data.get(
        "order_step"
    ) != "phone":

        return

    order = context.user_data.setdefault(
        "order",
        {},
    )

    order["phone"] = contact.phone_number

    context.user_data[
        "order_step"
    ] = "service"

    await save_customer(
        update.effective_user.id,
        update.effective_user.full_name,
        contact.phone_number,
        update.effective_user.username,
    )

    await update.message.reply_text(
        "3️⃣ Хизмат турини ёзинг:\n\n"
        "Масалан:\n"
        "🪑 Мебель\n"
        "🚚 Мебель ташиш\n"
        "🏠 Уй кўчириш",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "🪑 Мебель"
                    ),
                    KeyboardButton(
                        "🚚 Мебель ташиш"
                    ),
                ],
                [
                    KeyboardButton(
                        "🏠 Уй кўчириш"
                    ),
                ],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# LOCATION
# ============================================================

async def location_handler(
    update,
    context,
):

    if not update.message:
        return

    if context.user_data.get(
        "order_step"
    ) != "address":

        return

    location = update.message.location

    if not location:
        return

    address = (
        f"GPS: {location.latitude}, "
        f"{location.longitude}"
    )

    order = context.user_data.setdefault(
        "order",
        {},
    )

    order["address"] = address

    context.user_data[
        "order_step"
    ] = "description"

    await update.message.reply_text(
        "5️⃣ Қандай иш кераклигини ёзинг:"
    )


# ============================================================
# FORMAT ORDER
# ============================================================

def format_order(order):

    return (
        "📦 БУЮРТМА\n\n"
        f"🔢 №{order['id']}\n"
        f"👤 Мижоз: {order['customer_name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"📝 Изоҳ: {order['description']}\n"
        f"👨‍🔧 Уста: "
        f"{order['master_name'] or 'Танланмаган'}\n"
        f"📌 Ҳолат: {order['status']}"
    )


# ============================================================
# ASSIGN MASTER
# ============================================================

async def assign_master_start(
    update,
    context,
    order_id,
):

    masters = await get_masters()

    if not masters:

        await update.callback_query.answer(
            "Усталар мавжуд эмас.",
            show_alert=True,
        )

        return

    buttons = []

    for master in masters:

        buttons.append(
            [
                InlineKeyboardButton(
                    f"👨‍🔧 {master['name']}",
                    callback_data=(
                        f"selectmaster_"
                        f"{order_id}_"
                        f"{master['telegram_id']}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "❌ Бекор қилиш",
                callback_data=f"cancel_{order_id}",
            )
        ]
    )

    await update.callback_query.message.reply_text(
        "👨‍🔧 Усталардан бирини танланг:",
        reply_markup=InlineKeyboardMarkup(
            buttons
        ),
    )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def callback_router(
    update,
    context,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    # --------------------------------------------------------
    # ASSIGN
    # --------------------------------------------------------

    if data.startswith("assign_"):

        order_id = int(
            data.split("_")[1]
        )

        await assign_master_start(
            update,
            context,
            order_id,
        )

        return

    # --------------------------------------------------------
    # SELECT MASTER
    # --------------------------------------------------------

    if data.startswith(
        "selectmaster_"
    ):

        parts = data.split("_")

        order_id = int(parts[1])
        master_id = int(parts[2])

        master = await get_master(
            master_id
        )

        if not master:

            await query.message.reply_text(
                "❌ Уста топилмади."
            )

            return

        await assign_master(
            order_id,
            master_id,
            master["name"],
        )

        order = await get_order(
            order_id
        )

        if not order:

            return

        await query.message.reply_text(
            f"✅ Буюртма #{order_id}\n"
            f"👨‍🔧 {master['name']} га берилди."
        )

        # SEND MASTER

        master_text = (
            "🔔 СИЗГА ЯНГИ БУЮРТМА!\n\n"
            f"🔢 Буюртма: #{order_id}\n"
            f"👤 Мижоз: {order['customer_name']}\n"
            f"📞 Телефон: {order['phone']}\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n"
            f"📝 Изоҳ: {order['description']}\n"
        )

        master_buttons = [
            [
                InlineKeyboardButton(
                    "✅ Қабул қилиш",
                    callback_data=f"accept_{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ Рад этиш",
                    callback_data=f"reject_{order_id}",
                ),
            ]
        ]

        try:

            await context.bot.send_message(
                chat_id=master_id,
                text=master_text,
                reply_markup=InlineKeyboardMarkup(
                    master_buttons
                ),
            )

        except Exception as e:

            logger.error(
                f"Masterga yuborishda xato: {e}"
            )

            await query.message.reply_text(
                "⚠️ Устага хабар юборилмади.\n"
                "Уста ботни /start қилиши керак."
            )

        return

    # --------------------------------------------------------
    # ACCEPT
    # --------------------------------------------------------

    if data.startswith("accept_"):

        order_id = int(
            data.split("_")[1]
        )

        order = await get_order(
            order_id
        )

        if not order:
            return

        await update_order_status(
            order_id,
            "accepted",
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"✅ Буюртма #{order_id} қабул қилинди."
        )

        # CUSTOMER

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"👨‍🔧 Уста буюртмангизни қабул қилди.\n\n"
                    f"🔢 Буюртма: #{order_id}\n"
                    f"👨‍🔧 Уста: {order['master_name']}\n\n"
                    "Уста тез орада сиз билан боғланади."
                ),
            )

        except Exception as e:

            logger.error(
                f"Customerga xato: {e}"
            )

        # START BUTTON

        await query.message.reply_text(
            "Ишни бошлаганда тугмани босинг:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "▶️ Ишни бошлаш",
                            callback_data=f"start_{order_id}",
                        )
                    ]
                ]
            ),
        )

        return

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    if data.startswith("reject_"):

        order_id = int(
            data.split("_")[1]
        )

        order = await get_order(
            order_id
        )

        if not order:
            return

        await update_order_status(
            order_id,
            "rejected",
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"❌ Буюртма #{order_id} рад этилди."
        )

        # DISPATCHER

        if DISPATCHER_ID:

            try:

                await context.bot.send_message(
                    chat_id=DISPATCHER_ID,
                    text=(
                        f"⚠️ Буюртма #{order_id} "
                        "уста томонидан рад этилди.\n\n"
                        "Қайта уста танланг."
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔄 Қайта уста танлаш",
                                    callback_data=(
                                        f"assign_{order_id}"
                                    ),
                                )
                            ]
                        ]
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Dispatcher xatosi: {e}"
                )

        return

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if data.startswith("start_"):

        order_id = int(
            data.split("_")[1]
        )

        order = await get_order(
            order_id
        )

        if not order:
            return

        await update_order_status(
            order_id,
            "in_progress",
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"🔵 Буюртма #{order_id}\n"
            "Иш бошланди.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Ишни якунлаш",
                            callback_data=f"done_{order_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Бекор қилиш",
                            callback_data=f"cancel_{order_id}",
                        )
                    ],
                ]
            ),
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🔵 Буюртма #{order_id}\n\n"
                    "Уста ишни бошлади."
                ),
            )

        except Exception as e:

            logger.error(
                f"Customer xatosi: {e}"
            )

        return

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    if data.startswith("done_"):

        order_id = int(
            data.split("_")[1]
        )

        order = await get_order(
            order_id
        )

        if not order:
            return

        await update_order_status(
            order_id,
            "completed",
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"✅ Буюртма #{order_id} якунланди."
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🎉 Буюртма #{order_id} якунланди!\n\n"
                    "⭐ Устага баҳо беришингиз мумкин:"
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⭐ 1",
                                callback_data=f"rate_{order_id}_1",
                            ),
                            InlineKeyboardButton(
                                "⭐ 2",
                                callback_data=f"rate_{order_id}_2",
                            ),
                            InlineKeyboardButton(
                                "⭐ 3",
                                callback_data=f"rate_{order_id}_3",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "⭐ 4",
                                callback_data=f"rate_{order_id}_4",
                            ),
                            InlineKeyboardButton(
                                "⭐ 5",
                                callback_data=f"rate_{order_id}_5",
                            ),
                        ],
                    ]
                ),
            )

        except Exception as e:

            logger.error(
                f"Rating yuborishda xato: {e}"
            )

        return

    # --------------------------------------------------------
    # CANCEL
    # --------------------------------------------------------

    if data.startswith("cancel_"):

        order_id = int(
            data.split("_")[1]
        )

        order = await get_order(
            order_id
        )

        if not order:
            return

        await update_order_status(
            order_id,
            "cancelled",
        )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"❌ Буюртма #{order_id} бекор қилинди."
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"❌ Буюртма #{order_id} бекор қилинди."
                ),
            )

        except Exception:
            pass

        return

    # --------------------------------------------------------
    # RATE
    # --------------------------------------------------------

    if data.startswith("rate_"):

        parts = data.split("_")

        order_id = int(parts[1])
        rating = int(parts[2])

        order = await get_order(
            order_id
        )

        if not order:
            return

        async with db_pool.acquire() as conn:

            await conn.execute(
                """
                INSERT INTO reviews
                (
                    order_id,
                    customer_id,
                    master_id,
                    rating
                )
                VALUES
                ($1,$2,$3,$4)
                """,
                order_id,
                order["customer_id"],
                order["master_id"],
                rating,
            )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"⭐ Раҳмат!\n\n"
            f"Сизнинг баҳонгиз: {rating}/5"
        )

        return


# ============================================================
# ADMIN - CUSTOMERS
# ============================================================

async def customer_base(
    update,
    context,
):

    async with db_pool.acquire() as conn:

        customers = await conn.fetch(
            """
            SELECT *
            FROM customers
            ORDER BY created_at DESC
            LIMIT 30
            """
        )

    if not customers:

        await update.message.reply_text(
            "👤 Мижозлар ҳали йўқ."
        )

        return

    text = "👤 МИЖОЗЛАР\n\n"

    for customer in customers:

        username = (
            f"@{customer['username']}"
            if customer["username"]
            else "йўқ"
        )

        text += (
            f"🆔 {customer['id']}\n"
            f"👤 {customer['name'] or '-'}\n"
            f"📞 {customer['phone'] or '-'}\n"
            f"🔗 {username}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000]
    )


# ============================================================
# ADMIN - MASTERS LIST
# ============================================================

async def masters_list(
    update,
    context,
):

    masters = await get_masters()

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Усталар ҳали қўшилмаган."
        )

        return

    text = "👨‍🔧 УСТАЛАР\n\n"

    for master in masters:

        username = (
            f"@{master['username']}"
            if master["username"]
            else "йўқ"
        )

        text += (
            f"🆔 ID: {master['telegram_id']}\n"
            f"👤 Исм: {master['name']}\n"
            f"📞 Телефон: {master['phone'] or '-'}\n"
            f"🔗 Username: {username}\n"
            f"🛠 Хизматлар: {master['services'] or '-'}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text[:4000]
    )


# ============================================================
# ADMIN - ADD MASTER START
# ============================================================

async def add_master_start(
    update,
    context,
):

    context.user_data.clear()

    context.user_data[
        "master_add"
    ] = True

    context.user_data[
        "master_step"
    ] = "id"

    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "1️⃣ Устанинг Telegram ID рақамини юборинг:"
    )


# ============================================================
# ADMIN - ADD MASTER HANDLER
# ============================================================

async def add_master_handler(
    update,
    context,
):

    text = update.message.text.strip()

    step = context.user_data.get(
        "master_step"
    )

    data = context.user_data.setdefault(
        "new_master",
        {},
    )

    if step == "id":

        try:

            data["id"] = int(text)

        except ValueError:

            await update.message.reply_text(
                "❌ ID рақам бўлиши керак."
            )

            return

        context.user_data[
            "master_step"
        ] = "name"

        await update.message.reply_text(
            "2️⃣ Устанинг исмини юборинг:"
        )

        return

    if step == "name":

        data["name"] = text

        context.user_data[
            "master_step"
        ] = "phone"

        await update.message.reply_text(
            "3️⃣ Телефон рақамини юборинг:"
        )

        return

    if step == "phone":

        data["phone"] = text

        context.user_data[
            "master_step"
        ] = "username"

        await update.message.reply_text(
            "4️⃣ Username юборинг.\n\n"
            "Масалан: @usta123\n"
            "Агар бўлмаса: -"
        )

        return

    if step == "username":

        username = text

        if username == "-":
            username = None

        data["username"] = username

        context.user_data[
            "master_step"
        ] = "services"

        await update.message.reply_text(
            "5️⃣ Уста хизматларини ёзинг:\n\n"
            "Масалан:\n"
            "Мебель, кухня, шкаф, ташиш"
        )

        return

    if step == "services":

        data["services"] = text

        await add_master_db(
            telegram_id=data["id"],
            name=data["name"],
            phone=data["phone"],
            username=data["username"],
            services=data["services"],
        )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Уста муваффақиятли қўшилди!\n\n"
            f"👤 Исм: {data['name']}\n"
            f"🆔 ID: {data['id']}\n"
            f"📞 Телефон: {data['phone']}\n"
            f"🛠 Хизматлар: {data['services']}",
            reply_markup=admin_menu(),
        )


# ============================================================
# ADMIN - DELETE MASTER START
# ============================================================

async def delete_master_start(
    update,
    context,
):

    context.user_data.clear()

    context.user_data[
        "delete_master"
    ] = True

    await update.message.reply_text(
        "🗑 УСТАНИ ЎЧИРИШ\n\n"
        "Устанинг Telegram ID рақамини юборинг:"
    )


# ============================================================
# ADMIN - DELETE MASTER HANDLER
# ============================================================

async def delete_master_handler(
    update,
    context,
):

    text = update.message.text.strip()

    try:

        master_id = int(text)

    except ValueError:

        await update.message.reply_text(
            "❌ ID рақам бўлиши керак."
        )

        return

    master = await get_master(
        master_id
    )

    if not master:

        await update.message.reply_text(
            "❌ Бу ID билан уста топилмади."
        )

        context.user_data.clear()

        return

    await delete_master_db(
        master_id
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Уста ўчирилди.\n\n"
        f"👤 {master['name']}\n"
        f"🆔 {master_id}",
        reply_markup=admin_menu(),
    )


# ============================================================
# ADMIN - STATISTICS
# ============================================================

async def statistics(
    update,
    context,
):

    async with db_pool.acquire() as conn:

        customers = await conn.fetchval(
            "SELECT COUNT(*) FROM customers"
        )

        orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders"
        )

        new_orders = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = 'new'
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

        masters = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM masters
            WHERE active = TRUE
            """
        )

    await update.message.reply_text(
        "📊 USTA 24 СТАТИСТИКА\n\n"
        f"👤 Мижозлар: {customers}\n"
        f"👨‍🔧 Фаол усталар: {masters}\n"
        f"📦 Жами буюртмалар: {orders}\n"
        f"🆕 Янги: {new_orders}\n"
        f"✅ Якунланган: {completed}\n"
        f"❌ Бекор қилинган: {cancelled}"
    )


# ============================================================
# ADMIN SEND
# ============================================================

async def send_command(
    update,
    context,
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return

    if not context.args:

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return

    msg = " ".join(
        context.args
    )

    async with db_pool.acquire() as conn:

        customers = await conn.fetch(
            """
            SELECT id
            FROM customers
            """
        )

    count = 0

    for customer in customers:

        try:

            await context.bot.send_message(
                chat_id=customer["id"],
                text=msg,
            )

            count += 1

            await asyncio.sleep(
                0.05
            )

        except Exception as e:

            logger.error(
                f"Xabar yuborilmadi "
                f"{customer['id']}: {e}"
            )

    await update.message.reply_text(
        "📢 ХАБАР ЮБОРИЛДИ\n\n"
        f"👥 {count} та мижозга юборилди."
    )


# ============================================================
# ADMIN BUTTONS
# ============================================================

async def admin_button_handler(
    update,
    context,
):

    if not update.message:
        return False

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text or ""

    if text == "👤 Мижозлар":

        await customer_base(
            update,
            context,
        )

        return True

    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
            reply_markup=masters_menu(),
        )

        return True

    if text == "➕ Уста қўшиш":

        await add_master_start(
            update,
            context,
        )

        return True

    if text == "👨‍🔧 Усталар рўйхати":

        await masters_list(
            update,
            context,
        )

        return True

    if text == "🗑 Устани ўчириш":

        await delete_master_start(
            update,
            context,
        )

        return True

    if text == "📊 Статистика":

        await statistics(
            update,
            context,
        )

        return True

    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return True

    if text == "⬅️ Админ меню":

        await update.message.reply_text(
            "👑 USTA 24 АДМИН",
            reply_markup=admin_menu(),
        )

        return True

    if text == "⬅️ Бош меню":

        await update.message.reply_text(
            "🏠 USTA 24\n\n"
            "Асосий меню:",
            reply_markup=client_menu(),
        )

        return True

    return False


# ============================================================
# ALL TEXT
# ============================================================

async def all_text_handler(
    update,
    context,
):

    if not update.message:
        return

    uid = update.effective_user.id

    # ADMIN PROCESS

    if uid == ADMIN_ID:

        if context.user_data.get(
            "master_add"
        ):

            await add_master_handler(
                update,
                context,
            )

            return

        if context.user_data.get(
            "delete_master"
        ):

            await delete_master_handler(
                update,
                context,
            )

            return

        handled = await admin_button_handler(
            update,
            context,
        )

        if handled:
            return

    # CLIENT

    await client_handler(
        update,
        context,
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context,
):

    logger.error(
        "Telegram error:",
        exc_info=context.error,
    )


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application: Application,
):

    await init_db()


# ============================================================
# MAIN
# ============================================================

def main():

    application = (
        Application
        .builder()
        .token(TOKEN)
        .post_init(post_init)
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
            "admin",
            admin_start,
        )
    )

    application.add_handler(
        CommandHandler(
            "send",
            send_command,
        )
    )

    # --------------------------------------------------------
    # CALLBACK
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_router,
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
    # LOCATION
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.LOCATION,
            location_handler,
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            all_text_handler,
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    # --------------------------------------------------------
    # FLASK
    # --------------------------------------------------------

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    print(
        "======================================"
    )

    print(
        "USTA 24 PRO BOT ISHLAYAPTI"
    )

    print(
        "PostgreSQL: ULANGAN"
    )

    print(
        "======================================"
    )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
