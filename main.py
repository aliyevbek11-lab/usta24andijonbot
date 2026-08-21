# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# Python 3.13
# python-telegram-bot 22.3
# asyncpg 0.30.0
# Flask 3.1.1
# gunicorn 23.0.0
#
# 1 BOT = CLIENT + MASTER + ADMIN + DISPATCHER + GROUP
# ============================================================

import os
import asyncio
import logging
import threading
from datetime import datetime

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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")


# ============================================================
# ENVIRONMENT
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 ANDIJON BOT IS RUNNING"


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


# ============================================================
# DATABASE
# ============================================================

pool = None


async def init_db():
    global pool

    if not DATABASE_URL:
        logger.warning("DATABASE_URL topilmadi!")
        return

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=60,
    )

    async with pool.acquire() as conn:

        # ----------------------------------------------------
        # USERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # ORDERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,

                customer_id BIGINT,
                customer_name TEXT,
                phone TEXT,

                service TEXT,
                description TEXT,
                address TEXT,

                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,

                problem_photo TEXT,

                order_time TEXT,

                status TEXT DEFAULT 'new',

                master_id BIGINT,
                master_name TEXT,

                result_photo TEXT,

                price NUMERIC DEFAULT 0,

                rating INTEGER,
                review TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # MASTERS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                telegram_id BIGINT PRIMARY KEY,

                full_name TEXT,
                phone TEXT,

                services TEXT,
                work_area TEXT,

                rating NUMERIC DEFAULT 5,
                rating_count INTEGER DEFAULT 0,

                approved BOOLEAN DEFAULT FALSE,
                active BOOLEAN DEFAULT TRUE,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # REVIEWS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,

                order_id INTEGER,
                customer_id BIGINT,
                master_id BIGINT,

                rating INTEGER,
                review TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # NOTES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,

                user_id BIGINT,
                text TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # BOOKINGS
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,

                user_id BIGINT,
                order_id INTEGER,

                booking_time TEXT,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ----------------------------------------------------
        # SERVICES
        # ----------------------------------------------------

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                price TEXT,
                active BOOLEAN DEFAULT TRUE
            )
        """)

        services = [
            ("Мебель йиғиш", "Келишилган нарх"),
            ("Мебель таъмирлаш", "Келишилган нарх"),
            ("Кухонная мебель", "Келишилган нарх"),
            ("Шкаф", "Келишилган нарх"),
            ("Кровать", "Келишилган нарх"),
            ("Стол", "Келишилган нарх"),
            ("Стул", "Келишилган нарх"),
            ("Мебель кўчириш", "Келишилган нарх"),
            ("Уй кўчириш", "Келишилган нарх"),
            ("Электрик", "Келишилган нарх"),
            ("Сантехник", "Келишилган нарх"),
            ("Эшик таъмири", "Келишилган нарх"),
        ]

        for name, price in services:
            await conn.execute(
                """
                INSERT INTO services (name, price)
                VALUES ($1, $2)
                ON CONFLICT (name) DO NOTHING
                """,
                name,
                price,
            )

    logger.info("DATABASE READY")


# ============================================================
# USER
# ============================================================

async def save_user(user, role="client", phone=None):

    if not pool:
        return

    await pool.execute(
        """
        INSERT INTO users
        (
            telegram_id,
            full_name,
            username,
            phone,
            role
        )
        VALUES ($1,$2,$3,$4,$5)

        ON CONFLICT (telegram_id)
        DO UPDATE SET
            full_name = EXCLUDED.full_name,
            username = EXCLUDED.username,
            phone = COALESCE(EXCLUDED.phone, users.phone),
            role = EXCLUDED.role
        """,
        user.id,
        user.full_name,
        user.username,
        phone,
        role,
    )


async def get_user_role(user_id):

    if user_id == ADMIN_ID:
        return "admin"

    if user_id == DISPATCHER_ID:
        return "dispatcher"

    if not pool:
        return "client"

    row = await pool.fetchrow(
        """
        SELECT role
        FROM users
        WHERE telegram_id=$1
        """,
        user_id,
    )

    if row:
        return row["role"]

    return "client"


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
            ["📌 Eslatmalarim", "🗺️ Yaqin atrofdagi ustalar"],
            ["📅 Yozilma (bron)", "🎁 Loyallik va bonuslar"],
            ["🤖 AI yordamchi", "⚙️ Sozlamalar"],
            ["📊 Mening statistika", "🏷️ Chegirmalar va aksiyalar"],
            ["📞 Tez yordam", "🔔 Bildirishnomalar"],
            ["📁 Mening hujjatlarim", "🕊️ Do'stga tavsiya qilish"],
            ["📞 Dispetcherga qo'ng'iroq", "🚨 24/7 Shosilinch rejim"],
            ["👨‍🔧 Usta rejimi"],
        ],
        resize_keyboard=True,
    )


def master_menu():

    return ReplyKeyboardMarkup(
        [
            ["📋 Yangi buyurtmalar", "✅ Mening faol buyurtmalarim"],
            ["⏳ Tarix", "💰 Ish haqi va hisobot"],
            ["⭐ Reytingim va sharhlar", "📅 Kunlik ish jadvalim"],
            ["🔔 Mijozlar bilan bog'lanish", "📸 Galereya"],
            ["🛠 Xizmatlarni boshqarish", "📊 Ish statistikasi"],
            ["🏷️ Mening narxlarim", "📍 Ish hududim"],
            ["📅 Dam olish kunlari", "🔔 Bildirishnoma sozlamalari"],
            ["📝 Reytingni oshirish", "🎁 Usta bonuslari"],
            ["🤖 AI yordamchi", "📞 Texnik yordam"],
            ["📢 E'lonlar va yangiliklar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcherga qo'ng'iroq", "🚨 24/7 Shosilinch rejim"],
            ["👤 Mijoz rejimi"],
        ],
        resize_keyboard=True,
    )


def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "🛠 Buyurtmalar"],
            ["👨‍🔧 Ustalar", "⭐ Reyting va sharhlar"],
            ["🎁 Loyallik va bonuslar", "💰 To'lovlar"],
            ["🏷️ Chegirmalar va aksiyalar", "🛠 Xizmat turlari"],
            ["📊 Statistika va hisobot", "📢 E'lonlar va yangiliklar"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
            ["📸 Rasm galereyasi", "📱 Botni boshqarish"],
            ["📞 Qo'llab-quvvatlash", "🚨 24/7 Shosilinch rejim"],
            ["👤 Mijoz rejimi"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not user:
        return

    role = await get_user_role(user.id)

    await save_user(
        user,
        role=role,
    )

    if role == "admin":

        await update.message.reply_text(
            "👑 USTA 24 ANDIJON\n\n"
            "Админ панелига хуш келибсиз.",
            reply_markup=admin_menu(),
        )
        return

    if role == "dispatcher":

        await update.message.reply_text(
            "📞 USTA 24 ANDIJON\n\n"
            "Диспетчер режими.\n"
            "24/7 хизмат.",
            reply_markup=admin_menu(),
        )
        return

    if role == "master":

        await update.message.reply_text(
            "👨‍🔧 USTA 24 ANDIJON\n\n"
            "Уста панели.",
            reply_markup=master_menu(),
        )
        return

    await update.message.reply_text(
        "👋 Ассалому алайкум!\n\n"
        "🏠 USTA 24 ANDIJON\n"
        "Уйингизга уста чақиринг.\n\n"
        "🛠 Мебель\n"
        "⚡ Электрик\n"
        "💧 Сантехник\n"
        "🚪 Эшик\n"
        "🚚 Кўчириш\n\n"
        "24/7 хизмат.",
        reply_markup=client_menu(),
    )


# ============================================================
# ORDER STATE
# ============================================================

# context.user_data:
#
# order_step
# order_service
# order_description
# order_address
# order_time
# order_photo
# order_phone


async def start_order(update, context):

    context.user_data.clear()

    context.user_data["order_step"] = "service"

    keyboard = [
        [KeyboardButton("🪑 Мебель")],
        [KeyboardButton("⚡ Электрик")],
        [KeyboardButton("💧 Сантехник")],
        [KeyboardButton("🚪 Эшик")],
        [KeyboardButton("🚚 Кўчириш")],
        [KeyboardButton("🛠 Бошқа хизмат")],
    ]

    await update.message.reply_text(
        "🛒 БУЮРТМА БЕРИШ\n\n"
        "1️⃣ Хизмат турини танланг:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
        ),
    )


# ============================================================
# PHONE
# ============================================================

async def ask_phone(update, context):

    keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "📞 Телефон рақамимни юбориш",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "📞 Телефон рақамингизни юборинг:",
        reply_markup=keyboard,
    )


# ============================================================
# ORDER CREATE
# ============================================================

async def create_order(update, context):

    user = update.effective_user

    service = context.user_data.get("order_service", "Бошқа")
    description = context.user_data.get("order_description", "")
    address = context.user_data.get("order_address", "")
    order_time = context.user_data.get("order_time", "")
    photo = context.user_data.get("order_photo")
    phone = context.user_data.get("order_phone", "")

    if not pool:

        await update.message.reply_text(
            "❌ DATABASE_URL уланмаган."
        )
        return

    order_id = await pool.fetchval(
        """
        INSERT INTO orders
        (
            customer_id,
            customer_name,
            phone,
            service,
            description,
            address,
            order_time,
            problem_photo,
            status
        )
        VALUES
        (
            $1,$2,$3,$4,$5,$6,$7,$8,'new'
        )
        RETURNING id
        """,
        user.id,
        user.full_name,
        phone,
        service,
        description,
        address,
        order_time,
        photo,
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ БУЮРТМАНГИЗ ҚАБУЛ ҚИЛИНДИ!\n\n"
        f"🆔 Заказ №{order_id}\n"
        f"🛠 Хизмат: {service}\n"
        f"👤 Мижоз: {user.full_name}\n"
        f"📞 Телефон: {phone}\n"
        f"📍 Манзил: {address}\n"
        f"🕐 Вақт: {order_time}\n\n"
        f"👨‍🔧 Ҳозир усталарга юборилади.",
        reply_markup=client_menu(),
    )

    await send_order_to_group(order_id)


# ============================================================
# SEND ORDER TO MASTERS GROUP
# ============================================================

async def send_order_to_group(order_id):

    if not MASTERS_GROUP_ID:
        logger.warning("MASTERS_GROUP_ID topilmadi")
        return

    row = await pool.fetchrow(
        """
        SELECT *
        FROM orders
        WHERE id=$1
        """,
        order_id,
    )

    if not row:
        return

    text = (
        f"🆕 YANGI BUYURTMA! #{row['id']}\n\n"
        f"🛠 Xizmat: {row['service']}\n"
        f"👤 Mijoz: {row['customer_name']}\n"
        f"📞 Telefon: {row['phone']}\n"
        f"📍 Manzil: {row['address']}\n"
        f"🕐 Vaqt: {row['order_time']}\n"
        f"📝 Izoh: {row['description'] or '-'}\n\n"
        f"💰 To'lov: Faqat naqd + ish tugagach"
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
        ]
    )

    try:

        if row["problem_photo"]:

            await application.bot.send_photo(
                chat_id=MASTERS_GROUP_ID,
                photo=row["problem_photo"],
                caption=text,
                reply_markup=keyboard,
            )

        else:

            await application.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=text,
                reply_markup=keyboard,
            )

    except Exception as e:

        logger.error(
            f"GROUP SEND ERROR: {e}"
        )


# ============================================================
# ACCEPT / REJECT
# ============================================================

async def order_callback(update, context):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    data = query.data

    if not data:
        return

    action, order_id_str = data.split(":")

    order_id = int(order_id_str)

    # --------------------------------------------------------
    # ACCEPT
    # --------------------------------------------------------

    if action == "accept":

        role = await get_user_role(user.id)

        if role != "master":

            await query.answer(
                "❌ Сиз тасдиқланган уста эмассиз.",
                show_alert=True,
            )
            return

        master_name = user.full_name

        updated = await pool.execute(
            """
            UPDATE orders
            SET
                status='accepted',
                master_id=$1,
                master_name=$2,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=$3
            AND status='new'
            """,
            user.id,
            master_name,
            order_id,
        )

        if updated == "UPDATE 0":

            await query.edit_message_text(
                "⚠️ Бу буюртма аллақачон қабул қилинган ёки бекор қилинган."
            )
            return

        row = await pool.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            """,
            order_id,
        )

        await query.edit_message_text(
            f"✅ BUYURTMA QABUL QILINDI!\n\n"
            f"🆔 #{order_id}\n"
            f"👨‍🔧 Usta: {master_name}\n"
            f"👤 Mijoz: {row['customer_name']}"
        )

        try:

            await application.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"✅ Буюртмангиз қабул қилинди!\n\n"
                    f"🆔 #{order_id}\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    f"Уста ишни бошлаши кутилмоқда."
                ),
            )

        except Exception as e:
            logger.error(e)

        return

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    if action == "reject":

        row = await pool.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            """,
            order_id,
        )

        if not row:
            return

        await pool.execute(
            """
            UPDATE orders
            SET
                status='new',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=$1
            """,
            order_id,
        )

        await query.edit_message_text(
            f"❌ #{order_id} рад этилди.\n"
            f"🔄 Бошқа усталар кўриб чиқиши мумкин."
        )

        try:

            await application.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"❌ Буюртмангиздаги уста қабул қилмади.\n\n"
                    f"🆔 #{order_id}\n"
                    f"🔄 Бошқа усталарни қидиряпмиз..."
                ),
            )

        except Exception as e:
            logger.error(e)

        # қайта группага чиқариш
        await send_order_to_group(order_id)


# ============================================================
# MASTER START WORK
# ============================================================

async def master_start_work(update, context):

    if not pool:
        return

    user = update.effective_user

    row = await pool.fetchrow(
        """
        SELECT *
        FROM orders
        WHERE master_id=$1
        AND status='accepted'
        ORDER BY id DESC
        LIMIT 1
        """,
        user.id,
    )

    if not row:

        await update.message.reply_text(
            "📭 Сизда иш бошлаш учун буюртма йўқ."
        )
        return

    await pool.execute(
        """
        UPDATE orders
        SET
            status='in_progress',
            updated_at=CURRENT_TIMESTAMP
        WHERE id=$1
        """,
        row["id"],
    )

    await update.message.reply_text(
        f"🔧 #{row['id']} иш бошланди!"
    )

    try:

        await application.bot.send_message(
            chat_id=row["customer_id"],
            text=(
                f"🔧 ИШ БОШЛАНДИ!\n\n"
                f"🆔 #{row['id']}\n"
                f"👨‍🔧 Уста: {user.full_name}\n\n"
                f"Уста ҳозир ишни бажармоқда."
            ),
        )

    except Exception as e:
        logger.error(e)


# ============================================================
# MASTER FINISH
# ============================================================

async def master_finish(update, context):

    user = update.effective_user

    row = await pool.fetchrow(
        """
        SELECT *
        FROM orders
        WHERE master_id=$1
        AND status='in_progress'
        ORDER BY id DESC
        LIMIT 1
        """,
        user.id,
    )

    if not row:

        await update.message.reply_text(
            "❌ Сизда якунланадиган иш йўқ."
        )
        return

    context.user_data["finish_order_id"] = row["id"]

    await update.message.reply_text(
        f"📸 #{row['id']} иш натижаси расмини юборинг.\n\n"
        f"⚠️ РАСМ МАЖБУРИЙ."
    )


# ============================================================
# PHOTO
# ============================================================

async def handle_photo(update, context):

    user = update.effective_user

    photo = update.message.photo[-1]

    file_id = photo.file_id

    # --------------------------------------------------------
    # ORDER PHOTO
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "photo":

        context.user_data["order_photo"] = file_id

        context.user_data["order_step"] = "address"

        await update.message.reply_text(
            "📍 Энди манзилингизни ёзинг:"
        )

        return

    # --------------------------------------------------------
    # RESULT PHOTO
    # --------------------------------------------------------

    finish_order_id = context.user_data.get(
        "finish_order_id"
    )

    if finish_order_id:

        await pool.execute(
            """
            UPDATE orders
            SET
                result_photo=$1,
                status='completed',
                updated_at=CURRENT_TIMESTAMP
            WHERE id=$2
            """,
            file_id,
            finish_order_id,
        )

        row = await pool.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id=$1
            """,
            finish_order_id,
        )

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ ИШ ЯКУНЛАНДИ!\n\n"
            f"🆔 #{finish_order_id}\n"
            f"📸 Натижа расми қабул қилинди.\n"
            f"💵 Тўлов: ФАҚАТ НАҚД\n"
            f"💰 Ишдан кейин 100%"
        )

        try:

            await application.bot.send_photo(
                chat_id=row["customer_id"],
                photo=file_id,
                caption=(
                    f"✅ ИШ ЯКУНЛАНДИ!\n\n"
                    f"🆔 #{finish_order_id}\n"
                    f"👨‍🔧 Уста: {row['master_name']}\n\n"
                    f"📸 Иш натижаси.\n\n"
                    f"💵 Тўлов: Фақат нақд.\n"
                    f"💰 Ишдан кейин 100%."
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⭐ Рейтинг қолдириш",
                                callback_data=f"rate:{finish_order_id}",
                            )
                        ]
                    ]
                ),
            )

        except Exception as e:
            logger.error(e)

        # Admin
        if ADMIN_ID:

            try:

                await application.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=file_id,
                    caption=(
                        f"✅ ИШ ЯКУНЛАНДИ\n\n"
                        f"🆔 #{finish_order_id}\n"
                        f"👨‍🔧 Уста: {row['master_name']}\n"
                        f"👤 Мижоз: {row['customer_name']}"
                    ),
                )

            except Exception as e:
                logger.error(e)

        return


# ============================================================
# TEXT HANDLER
# ============================================================

async def text_handler(update, context):

    if not update.message:
        return

    text = update.message.text or ""

    user = update.effective_user

    role = await get_user_role(user.id)

    # ========================================================
    # CONTACT
    # ========================================================

    if update.message.contact:

        phone = update.message.contact.phone_number

        context.user_data["order_phone"] = phone

        await save_user(
            user,
            role="client",
            phone=phone,
        )

        await update.message.reply_text(
            "✅ Телефон қабул қилинди.\n\n"
            "🛠 Хизмат турини танланг."
        )

        return

    # ========================================================
    # CLIENT ORDER
    # ========================================================

    if text == "🛒 Buyurtma berish":

        await start_order(
            update,
            context,
        )

        return

    # --------------------------------------------------------
    # SERVICE
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "service":

        context.user_data["order_service"] = text

        context.user_data["order_step"] = "description"

        await update.message.reply_text(
            "📝 Муаммони қисқача ёзинг:"
        )

        return

    # --------------------------------------------------------
    # DESCRIPTION
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "description":

        context.user_data["order_description"] = text

        context.user_data["order_step"] = "photo"

        await update.message.reply_text(
            "📸 Муаммо расмини юборинг.\n\n"
            "Агар расм бўлмаса, /skip ёзинг."
        )

        return

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "address":

        context.user_data["order_address"] = text

        context.user_data["order_step"] = "time"

        await update.message.reply_text(
            "🕐 Қачон керак?\n\n"
            "Масалан: Бугун 18:00"
        )

        return

    # --------------------------------------------------------
    # TIME
    # --------------------------------------------------------

    if context.user_data.get("order_step") == "time":

        context.user_data["order_time"] = text

        context.user_data["order_step"] = "phone"

        await ask_phone(
            update,
            context,
        )

        return

    # ========================================================
    # CLIENT MENU
    # ========================================================

    if text == "📋 Mening buyurtmalarim":

        rows = await pool.fetch(
            """
            SELECT id, service, status, created_at
            FROM orders
            WHERE customer_id=$1
            ORDER BY id DESC
            LIMIT 20
            """,
            user.id,
        )

        if not rows:

            await update.message.reply_text(
                "📭 Сизда ҳозирча буюртмалар йўқ."
            )
            return

        msg = "📋 МЕНИНГ БУЮРТМАЛАРИМ\n\n"

        for r in rows:

            msg += (
                f"🆔 #{r['id']}\n"
                f"🛠 {r['service']}\n"
                f"📌 {r['status']}\n"
                f"📅 {r['created_at']}\n\n"
            )

        await update.message.reply_text(msg)

        return

    # --------------------------------------------------------

    if text == "🔍 Buyurtma holati":

        await update.message.reply_text(
            "🔍 Буюртма ҳолатини кўриш учун "
            "буюртма рақамини ёзинг.\n\n"
            "Масалан: 125"
        )

        context.user_data["check_order"] = True

        return

    # --------------------------------------------------------

    if context.user_data.get("check_order"):

        if text.isdigit():

            order_id = int(text)

            row = await pool.fetchrow(
                """
                SELECT *
                FROM orders
                WHERE id=$1
                AND customer_id=$2
                """,
                order_id,
                user.id,
            )

            context.user_data.pop(
                "check_order",
                None,
            )

            if not row:

                await update.message.reply_text(
                    "❌ Бундай буюртма топилмади."
                )
                return

            await update.message.reply_text(
                f"🔍 БУЮРТМА #{row['id']}\n\n"
                f"🛠 Хизмат: {row['service']}\n"
                f"📌 Ҳолат: {row['status']}\n"
                f"👨‍🔧 Уста: {row['master_name'] or 'Ҳали бириктирилмаган'}"
            )

            return

    # ========================================================
    # CANCEL
    # ========================================================

    if text == "❌ Bekor qilish":

        rows = await pool.fetch(
            """
            SELECT id, service
            FROM orders
            WHERE customer_id=$1
            AND status IN ('new','accepted')
            ORDER BY id DESC
            """,
            user.id,
        )

        if not rows:

            await update.message.reply_text(
                "❌ Бекор қилиш мумкин бўлган буюртма йўқ."
            )
            return

        keyboard = []

        for r in rows:

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"❌ #{r['id']} {r['service']}",
                        callback_data=f"cancel:{r['id']}",
                    )
                ]
            )

        await update.message.reply_text(
            "❌ Қайси буюртмани бекор қилмоқчисиз?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return

    # ========================================================
    # MASTER
    # ========================================================

    if text == "👨‍🔧 Usta rejimi":

        if role != "master":

            await update.message.reply_text(
                "❌ Сиз ҳали уста сифатида тасдиқланмагансиз."
            )

            return

        await update.message.reply_text(
            "👨‍🔧 УСТА РЕЖИМИ",
            reply_markup=master_menu(),
        )

        return

    if role == "master":

        if text == "📋 Yangi buyurtmalar":

            rows = await pool.fetch(
                """
                SELECT *
                FROM orders
                WHERE status='new'
                ORDER BY id DESC
                LIMIT 20
                """
            )

            if not rows:

                await update.message.reply_text(
                    "📭 Янги буюртмалар йўқ."
                )
                return

            for row in rows:

                await update.message.reply_text(
                    f"🆕 #{row['id']}\n"
                    f"🛠 {row['service']}\n"
                    f"📍 {row['address']}\n"
                    f"🕐 {row['order_time']}\n",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✅ ҚАБУЛ",
                                    callback_data=f"accept:{row['id']}",
                                ),
                                InlineKeyboardButton(
                                    "❌ РАД",
                                    callback_data=f"reject:{row['id']}",
                                ),
                            ]
                        ]
                    ),
                )

            return

        if text == "🔧 Ishni boshlash":

            await master_start_work(
                update,
                context,
            )

            return

        if text == "✅ Ishni yakunlash":

            await master_finish(
                update,
                context,
            )

            return

        if text == "📊 Ish statistikasi":

            total = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE master_id=$1
                """,
                user.id,
            )

            completed = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE master_id=$1
                AND status='completed'
                """,
                user.id,
            )

            await update.message.reply_text(
                f"📊 ИШ СТАТИСТИКАСИ\n\n"
                f"📋 Жами: {total}\n"
                f"✅ Якунланган: {completed}"
            )

            return

        if text == "⭐ Reytingim va sharhlar":

            row = await pool.fetchrow(
                """
                SELECT rating, rating_count
                FROM masters
                WHERE telegram_id=$1
                """,
                user.id,
            )

            if row:

                await update.message.reply_text(
                    f"⭐ РЕЙТИНГ\n\n"
                    f"⭐ {row['rating']}\n"
                    f"📝 Баҳолар: {row['rating_count']}"
                )

            else:

                await update.message.reply_text(
                    "⭐ Рейтинг ҳали йўқ."
                )

            return

    # ========================================================
    # ADMIN
    # ========================================================

    if role in ("admin", "dispatcher"):

        if text == "👥 Foydalanuvchilar":

            count = await pool.fetchval(
                "SELECT COUNT(*) FROM users"
            )

            await update.message.reply_text(
                f"👥 ФОЙДАЛАНУВЧИЛАР\n\n"
                f"Жами: {count}"
            )

            return

        if text == "🛠 Buyurtmalar":

            count = await pool.fetchval(
                "SELECT COUNT(*) FROM orders"
            )

            new_count = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='new'
                """
            )

            active = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status IN ('accepted','in_progress')
                """
            )

            completed = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='completed'
                """
            )

            await update.message.reply_text(
                f"🛠 БУЮРТМАЛАР\n\n"
                f"📋 Жами: {count}\n"
                f"🆕 Янги: {new_count}\n"
                f"🔧 Жараёнда: {active}\n"
                f"✅ Якунланган: {completed}"
            )

            return

        if text == "👨‍🔧 Ustalar":

            rows = await pool.fetch(
                """
                SELECT telegram_id, full_name,
                       rating, rating_count,
                       approved, active
                FROM masters
                ORDER BY rating DESC
                """
            )

            if not rows:

                await update.message.reply_text(
                    "👨‍🔧 Усталар йўқ."
                )
                return

            msg = "👨‍🔧 УСТАЛАР\n\n"

            for r in rows:

                msg += (
                    f"👤 {r['full_name']}\n"
                    f"⭐ {r['rating']}\n"
                    f"📊 {r['rating_count']} та баҳо\n"
                    f"✅ Тасдиқ: {r['approved']}\n\n"
                )

            await update.message.reply_text(msg)

            return

        if text == "📊 Statistika va hisobot":

            total = await pool.fetchval(
                "SELECT COUNT(*) FROM orders"
            )

            completed = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='completed'
                """
            )

            cancelled = await pool.fetchval(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE status='cancelled'
                """
            )

            await update.message.reply_text(
                f"📊 USTA 24 STATISTIKA\n\n"
                f"📋 Жами буюртма: {total}\n"
                f"✅ Якунланган: {completed}\n"
                f"❌ Бекор қилинган: {cancelled}"
            )

            return

    # ========================================================
    # COMMON
    # ========================================================

    if text == "📞 Dispetcherga qo'ng'iroq":

        await update.message.reply_text(
            f"📞 ДИСПЕТЧЕР\n\n"
            f"☎️ {DISPATCHER_PHONE}\n"
            f"🕐 24/7\n"
            f"📍 Andijon shahar"
        )

        return

    if text == "🚨 24/7 Shosilinch rejim":

        await update.message.reply_text(
            "🚨 24/7 ШОШИЛИНЧ РЕЖИМ\n\n"
            "🚨 ДАРҲОЛ ЁРДАМ КЕРАК!\n"
            "КУТИШ ЙЎҚ!\n\n"
            "🔴 ҲОЗИР — 10-15 дақиқа\n"
            "➕ 20% устама\n\n"
            "🟡 ЯРИМ СОАТДА\n"
            "➕ 10% устама\n\n"
            "🟢 1 СОАТДА\n"
            "Оддий нарх\n\n"
            f"📞 Диспетчер: {DISPATCHER_PHONE}\n\n"
            "💵 Тўлов: Фақат нақд\n"
            "💰 Ишдан кейин"
        )

        return

    if text == "📞 Tez yordam":

        await update.message.reply_text(
            f"🚨 ТЕЗ ЁРДАМ\n\n"
            f"📞 {DISPATCHER_PHONE}\n"
            f"🕐 24/7"
        )

        return

    if text == "🏷️ Chegirmalar va aksiyalar":

        await update.message.reply_text(
            "🏷️ ЧЕГИРМАЛАР ВА АКЦИЯЛАР\n\n"
            "Ҳозирча актив акциялар йўқ."
        )

        return

    if text == "🎁 Loyallik va bonuslar":

        await update.message.reply_text(
            "🎁 ЛОЙАЛЛИК ВА БОНУСЛАР\n\n"
            "Сизнинг бонус тизимингиз тез орада ишга тушади."
        )

        return

    if text == "🗺️ Yaqin atrofdagi ustalar":

        await update.message.reply_text(
            "🗺️ ЯҚИН АТРОФДАГИ УСТАЛАР\n\n"
            "Бу функция геолокация асосида ишлайди."
        )

        return

    if text == "📅 Yozilma (bron)":

        await update.message.reply_text(
            "📅 БРОН\n\n"
            "Брон қилиш учун аввал буюртма беринг."
        )

        return

    if text == "⚙️ Sozlamalar":

        await update.message.reply_text(
            "⚙️ СОЗЛАМАЛАР\n\n"
            "Ҳозирча стандарт созламалар."
        )

        return

    if text == "🤖 AI yordamchi":

        await update.message.reply_text(
            "🤖 AI ЁРДАМЧИ\n\n"
            "Саволингизни ёзинг."
        )

        return

    if text == "🕊️ Do'stga tavsiya qilish":

        await update.message.reply_text(
            "🕊️ Дўстингизга USTA 24 ни тавсия қилинг!"
        )

        return

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    if role == "master":

        await update.message.reply_text(
            "👨‍🔧 Уста менюсидан фойдаланинг.",
            reply_markup=master_menu(),
        )

    elif role in ("admin", "dispatcher"):

        await update.message.reply_text(
            "👑 Бошқарув менюсидан фойдаланинг.",
            reply_markup=admin_menu(),
        )

    else:

        await update.message.reply_text(
            "👤 Мижоз менюсидан фойдаланинг.",
            reply_markup=client_menu(),
        )


# ============================================================
# SKIP PHOTO
# ============================================================

async def skip_photo(update, context):

    if context.user_data.get("order_step") != "photo":
        return

    context.user_data["order_photo"] = None

    context.user_data["order_step"] = "address"

    await update.message.reply_text(
        "📍 Энди манзилингизни ёзинг:"
    )


# ============================================================
# CANCEL CALLBACK
# ============================================================

async def cancel_callback(update, context):

    query = update.callback_query

    await query.answer()

    data = query.data

    order_id = int(data.split(":")[1])

    user = query.from_user

    result = await pool.execute(
        """
        UPDATE orders
        SET
            status='cancelled',
            updated_at=CURRENT_TIMESTAMP
        WHERE id=$1
        AND customer_id=$2
        AND status IN ('new','accepted')
        """,
        order_id,
        user.id,
    )

    if result == "UPDATE 0":

        await query.edit_message_text(
            "❌ Буюртмани бекор қилиб бўлмайди."
        )

        return

    await query.edit_message_text(
        f"❌ #{order_id} буюртма бекор қилинди."
    )


# ============================================================
# RATING
# ============================================================

async def rating_callback(update, context):

    query = update.callback_query

    await query.answer()

    order_id = int(
        query.data.split(":")[1]
    )

    keyboard = []

    for i in range(1, 6):

        keyboard.append(
            InlineKeyboardButton(
                f"{i}⭐",
                callback_data=f"rating:{order_id}:{i}",
            )
        )

    await query.message.reply_text(
        "⭐ Устага баҳо беринг:",
        reply_markup=InlineKeyboardMarkup(
            [keyboard]
        ),
    )


async def rating_save_callback(update, context):

    query = update.callback_query

    await query.answer()

    _, order_id, rating = query.data.split(":")

    order_id = int(order_id)
    rating = int(rating)

    row = await pool.fetchrow(
        """
        SELECT master_id
        FROM orders
        WHERE id=$1
        """,
        order_id,
    )

    if not row or not row["master_id"]:

        await query.edit_message_text(
            "❌ Уста маълумоти топилмади."
        )

        return

    await pool.execute(
        """
        INSERT INTO reviews
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
        row["master_id"],
        rating,
    )

    # MASTER rating update
    await pool.execute(
        """
        UPDATE masters
        SET
            rating =
            (
                rating * rating_count + $1
            )
            /
            (
                rating_count + 1
            ),
            rating_count = rating_count + 1
        WHERE telegram_id=$2
        """,
        rating,
        row["master_id"],
    )

    await query.edit_message_text(
        f"⭐ Раҳмат!\n\n"
        f"Сиз {rating}⭐ баҳо бердингиз."
    )

    try:

        await application.bot.send_message(
            chat_id=row["master_id"],
            text=(
                f"⭐ Мижоз сизга {rating}⭐ баҳо берди!\n"
                f"🆔 Буюртма #{order_id}"
            ),
        )

    except Exception as e:
        logger.error(e)


# ============================================================
# APPLICATION
# ============================================================

application = None


async def post_init(app_instance):

    await init_db()


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    logger.exception(
        "Unhandled exception:",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global application

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN Environment Variable topilmadi!"
        )

    logger.info("USTA 24 ANDIJON STARTING...")

    # Flask
    threading.Thread(
        target=run_flask,
        daemon=True,
    ).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
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
            "skip",
            skip_photo,
        )
    )

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            order_callback,
            pattern=r"^(accept|reject):",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_callback,
            pattern=r"^cancel:",
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
            rating_save_callback,
            pattern=r"^rating:",
        )
    )

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )

    # --------------------------------------------------------
    # CONTACT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            text_handler,
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler,
        )
    )

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "USTA 24 ANDIJON BOT IS RUNNING"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
