import os
import asyncio
import logging
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
    filters,
)

# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
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
        "MASTERS_GROUP_ID va ADMIN_ID faqat raqam bo‘lishi kerak!"
    )

# =========================================================
# LOG
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("usta24")

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI!"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)


# =========================================================
# DATABASE
# =========================================================

db_pool = None


async def init_database():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi!")

    try:
        db_pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            command_timeout=30,
        )

        async with db_pool.acquire() as conn:

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_order_at TIMESTAMP
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    customer_id BIGINT NOT NULL,
                    customer_name TEXT,
                    phone TEXT,
                    service TEXT,
                    address TEXT,
                    description TEXT,
                    username TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    master_id BIGINT,
                    master_name TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    accepted_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    rejected_at TIMESTAMP
                )
            """)

        logger.info("PostgreSQL muvaffaqiyatli ulandi.")

    except Exception:
        logger.exception("DATABASE XATOSI!")
        raise


async def db_save_customer(
    telegram_id,
    name,
    phone,
    username,
):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO customers
                (telegram_id, name, phone, username, last_order_at)
            VALUES
                ($1, $2, $3, $4, NOW())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                phone = EXCLUDED.phone,
                username = EXCLUDED.username,
                last_order_at = NOW()
            """,
            telegram_id,
            name,
            phone,
            username,
        )


async def db_get_customer(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT name, phone
            FROM customers
            WHERE telegram_id = $1
            """,
            telegram_id,
        )


async def db_create_order(
    customer_id,
    customer_name,
    phone,
    service,
    address,
    description,
    username,
):
    async with db_pool.acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO orders (
                customer_id,
                customer_name,
                phone,
                service,
                address,
                description,
                username,
                status
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, 'open'
            )
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


async def db_get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )


async def db_update_order(
    order_id,
    status,
    master_id=None,
    master_name=None,
):
    timestamp_column = {
        "accepted": "accepted_at",
        "in_progress": "started_at",
        "completed": "completed_at",
        "cancelled": "cancelled_at",
        "rejected": "rejected_at",
    }.get(status)

    async with db_pool.acquire() as conn:

        if timestamp_column:
            await conn.execute(
                f"""
                UPDATE orders
                SET
                    status = $1,
                    master_id = COALESCE($2, master_id),
                    master_name = COALESCE($3, master_name),
                    {timestamp_column} = NOW()
                WHERE id = $4
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
                SET
                    status = $1,
                    master_id = COALESCE($2, master_id),
                    master_name = COALESCE($3, master_name)
                WHERE id = $4
                """,
                status,
                master_id,
                master_name,
                order_id,
            )


async def db_get_orders(status=None):
    async with db_pool.acquire() as conn:

        if status:
            return await conn.fetch(
                """
                SELECT *
                FROM orders
                WHERE status = $1
                ORDER BY id DESC
                """,
                status,
            )

        return await conn.fetch(
            """
            SELECT *
            FROM orders
            ORDER BY id DESC
            """
        )


async def db_statistics():
    result = {
        "total": 0,
        "open": 0,
        "accepted": 0,
        "in_progress": 0,
        "completed": 0,
        "cancelled": 0,
        "rejected": 0,
    }

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM orders
            GROUP BY status
            """
        )

    for row in rows:
        status = row["status"]
        count = int(row["count"])

        if status in result:
            result[status] = count

        result["total"] += count

    return result


# =========================================================
# MENYULAR
# =========================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Usta chaqirish"],
            ["📋 Xizmatlar", "📞 Aloqa"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar"],
            ["🟡 Qabul qilingan"],
            ["🔵 Ish jarayonida"],
            ["✅ Yakunlangan"],
            ["❌ Bekor qilingan"],
            ["🚫 Rad etilgan"],
            ["📋 Barcha buyurtmalar"],
            ["📊 Statistika"],
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


# =========================================================
# MIJOZ BUYURTMASI
# =========================================================

user_orders = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user

    if user and user.id == ADMIN_ID:
        await update.message.reply_text(
            "👨‍💼 USTA 24 ADMIN PANEL\n\n"
            "Siz administrator sifatida kirdingiz.",
            reply_markup=admin_menu(),
        )
        return

    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "🏠 USTA 24 xizmatiga xush kelibsiz!\n\n"
        "🔧 Uy va ofis uchun ustalar xizmatlari.\n"
        "📍 Andijon shahri\n\n"
        "Kerakli xizmatni tanlang:",
        reply_markup=main_menu(),
    )


async def dispatcher(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Sizda dispetcher paneliga ruxsat yo‘q."
        )
        return

    await update.message.reply_text(
        "👨‍💼 USTA 24 DISPETCHER PANELI\n\n"
        "Kerakli bo‘limni tanlang:",
        reply_markup=admin_menu(),
    )


async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    customer = await db_get_customer(user.id)

    if customer and customer["name"] and customer["phone"]:

        user_orders[user.id] = {
            "step": "service",
            "name": customer["name"],
            "phone": customer["phone"],
        }

        await update.message.reply_text(
            f"👋 Salom, {customer['name']}!\n\n"
            "Sizni esladik. ✅\n"
            "Ism va telefon raqamingiz saqlangan.\n\n"
            "3️⃣ Qanday xizmat kerak?",
            reply_markup=service_menu(),
        )
        return

    user_orders[user.id] = {
        "step": "name"
    }

    await update.message.reply_text(
        "📝 BUYURTMA BERISH\n\n"
        "1️⃣ Ismingizni yozing:"
    )


# =========================================================
# XIZMATLAR
# =========================================================

async def services(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🛠 USTA 24 XIZMATLARI\n\n"
        "🪑 Mebel yig‘ish\n"
        "🔧 Mebel ta’mirlash\n"
        "🍽 Oshxona mebellari\n"
        "🚪 Shkaf yig‘ish va ta’mirlash\n"
        "🛏 Krovat yig‘ish\n"
        "🪑 Stol va stul yig‘ish\n"
        "📦 Mebelni ajratish/yig‘ish\n"
        "🚚 Mebel tashish\n"
        "🏠 Uy ko‘chirish\n"
        "🚛 Yuk tashish\n"
        "🔩 Santexnika\n"
        "⚡ Elektr\n"
        "🔥 Payvandlash\n"
        "🔨 Boshqa xizmat",
        reply_markup=main_menu(),
    )


async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📞 USTA 24\n\n"
        "☎️ +998 77 069 00 03\n"
        "📍 Andijon shahri",
        reply_markup=main_menu(),
    )


# =========================================================
# BUYURTMANI USTALAR GURUHIGA YUBORISH
# =========================================================

async def send_order_to_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order,
):
    user = update.effective_user

    username = (
        f"@{user.username}"
        if user.username
        else "username yo‘q"
    )

    await db_save_customer(
        user.id,
        order["name"],
        order["phone"],
        username,
    )

    order_id = await db_create_order(
        user.id,
        order["name"],
        order["phone"],
        order["service"],
        order["address"],
        order["description"],
        username,
    )

    text = (
        "🆕 YANGI BUYURTMA\n\n"
        f"🔢 Buyurtma: #{order_id}\n"
        f"👤 Mijoz: {order['name']}\n"
        f"📞 Telefon: {order['phone']}\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"📝 Izoh: {order['description']}\n\n"
        f"👤 Telegram: {username}\n\n"
        "🚨 Usta buyurtmani qabul qilishi mumkin."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Qabul qilish",
                    callback_data=f"accept:{order_id}",
                ),
                InlineKeyboardButton(
                    "❌ Rad etish",
                    callback_data=f"reject:{order_id}",
                ),
            ]
        ]
    )

    await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=text,
        reply_markup=keyboard,
    )

    logger.info(
        "✅ Buyurtma #%s ustalar guruhiga yuborildi.",
        order_id,
    )

    return order_id


# =========================================================
# FORMAT
# =========================================================

def format_order(row):
    return (
        f"🔢 Buyurtma: #{row['id']}\n"
        f"👤 Mijoz: {row['customer_name'] or '-'}\n"
        f"📞 Telefon: {row['phone'] or '-'}\n"
        f"🛠 Xizmat: {row['service'] or '-'}\n"
        f"📍 Manzil: {row['address'] or '-'}\n"
        f"📝 Izoh: {row['description'] or '-'}\n"
        f"👨‍🔧 Usta: {row['master_name'] or '-'}\n"
        f"📌 Holat: {row['status']}\n"
        "──────────────\n"
    )


# =========================================================
# ADMIN BUYURTMALAR
# =========================================================

async def show_orders(
    update: Update,
    status=None,
    title="📋 BUYURTMALAR",
):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Ruxsat yo‘q."
        )
        return

    rows = await db_get_orders(status)

    if not rows:
        await update.message.reply_text(
            "📭 Hozircha buyurtmalar yo‘q.",
            reply_markup=admin_menu(),
        )
        return

    text = title + "\n\n"

    for row in rows[:30]:
        text += format_order(row)

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


async def show_statistics(update: Update):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Ruxsat yo‘q."
        )
        return

    stats = await db_statistics()

    await update.message.reply_text(
        "📊 USTA 24 STATISTIKA\n\n"
        f"📋 Jami: {stats['total']}\n\n"
        f"🆕 Yangi: {stats['open']}\n"
        f"🟡 Qabul qilingan: {stats['accepted']}\n"
        f"🔵 Ish jarayonida: {stats['in_progress']}\n"
        f"✅ Yakunlangan: {stats['completed']}\n"
        f"❌ Bekor qilingan: {stats['cancelled']}\n"
        f"🚫 Rad etilgan: {stats['rejected']}",
        reply_markup=admin_menu(),
    )


# =========================================================
# ADMIN MENU HANDLER
# =========================================================

async def handle_admin_menu(update, text):

    if update.effective_user.id != ADMIN_ID:
        return False

    mapping = {
        "🆕 Yangi buyurtmalar":
            ("open", "🆕 YANGI BUYURTMALAR"),

        "🟡 Qabul qilingan":
            ("accepted", "🟡 QABUL QILINGAN"),

        "🔵 Ish jarayonida":
            ("in_progress", "🔵 ISH JARAYONIDA"),

        "✅ Yakunlangan":
            ("completed", "✅ YAKUNLANGAN"),

        "❌ Bekor qilingan":
            ("cancelled", "❌ BEKOR QILINGAN"),

        "🚫 Rad etilgan":
            ("rejected", "🚫 RAD ETILGAN"),

        "📋 Barcha buyurtmalar":
            (None, "📋 BARCHA BUYURTMALAR"),
    }

    if text in mapping:
        status, title = mapping[text]
        await show_orders(update, status, title)
        return True

    if text == "📊 Statistika":
        await show_statistics(update)
        return True

    return False


# =========================================================
# ASOSIY MESSAGE HANDLER
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

    text = (update.message.text or "").strip()

    # ADMIN
    if await handle_admin_menu(update, text):
        return

    # MAIN MENU
    if text == "🛠 Usta chaqirish":
        await start_order(update, context)
        return

    if text == "📋 Xizmatlar":
        await services(update, context)
        return

    if text == "📞 Aloqa":
        await contact(update, context)
        return

    # ORDER STATE
    if user.id not in user_orders:
        await update.message.reply_text(
            "Iltimos, menyudan kerakli xizmatni tanlang.",
            reply_markup=main_menu(),
        )
        return

    order = user_orders[user.id]
    step = order["step"]

    # NAME
    if step == "name":
        if not text:
            await update.message.reply_text(
                "📝 Ismingizni yozing:"
            )
            return

        order["name"] = text
        order["step"] = "phone"

        phone_button = KeyboardButton(
            "📱 Telefon raqamimni yuborish",
            request_contact=True,
        )

        await update.message.reply_text(
            "2️⃣ Telefon raqamingizni yuboring:",
            reply_markup=ReplyKeyboardMarkup(
                [[phone_button]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return

    # PHONE
    if step == "phone":

        if update.message.contact:
            phone = update.message.contact.phone_number
        else:
            phone = text

        if not phone:
            await update.message.reply_text(
                "📱 Telefon raqamingizni yuboring."
            )
            return

        order["phone"] = phone
        order["step"] = "service"

        await update.message.reply_text(
            "3️⃣ Qanday xizmat kerak?",
            reply_markup=service_menu(),
        )
        return

    # SERVICE
    if step == "service":

        order["service"] = text
        order["step"] = "address"

        await update.message.reply_text(
            "4️⃣ Manzilingizni yozing.\n\n"
            "Masalan:\n"
            "Andijon shahar, Boburshoh ko‘chasi, 15-uy"
        )
        return

    # ADDRESS
    if step == "address":

        if not text:
            await update.message.reply_text(
                "📍 Manzilingizni yozing."
            )
            return

        order["address"] = text
        order["step"] = "description"

        await update.message.reply_text(
            "5️⃣ Buyurtma haqida qisqacha ma’lumot yozing.\n\n"
            "Masalan:\n"
            "Shkaf yig‘ish kerak."
        )
        return

    # DESCRIPTION
    if step == "description":

        if not text:
            await update.message.reply_text(
                "📝 Buyurtma haqida ma’lumot yozing."
            )
            return

        order["description"] = text

        try:
            order_id = await send_order_to_masters(
                update,
                context,
                order,
            )

        except Exception:
            logger.exception(
                "USTALAR GURUHIGA YUBORISHDA XATO!"
            )

            await update.message.reply_text(
                "❌ Buyurtmani ustalar guruhiga "
                "yuborishda xatolik yuz berdi.\n\n"
                "Texnik xatolik qayd etildi.\n"
                "☎️ +998 77 069 00 03",
                reply_markup=main_menu(),
            )
            return

        del user_orders[user.id]

        await update.message.reply_text(
            f"✅ Buyurtmangiz qabul qilindi!\n\n"
            f"🔢 Buyurtma №{order_id}\n\n"
            "👨‍🔧 Buyurtma ustalar guruhiga yuborildi.\n"
            "📞 Tez orada siz bilan bog‘lanishadi.\n\n"
            "☎️ +998 77 069 00 03",
            reply_markup=main_menu(),
        )


# =========================================================
# CALLBACK — USTALAR
# =========================================================

async def order_callback(
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

    action, order_id_text = data.split(":", 1)

    try:
        order_id = int(order_id_text)
    except ValueError:
        return

    row = await db_get_order(order_id)

    if not row:
        await query.answer(
            "❌ Buyurtma topilmadi.",
            show_alert=True,
        )
        return

    master = query.from_user

    master_name = (
        f"@{master.username}"
        if master.username
        else master.full_name
    )

    # ACCEPT
    if action == "accept":

        if row["status"] != "open":
            await query.answer(
                "⚠️ Bu buyurtma allaqachon qabul qilingan.",
                show_alert=True,
            )
            return

        await db_update_order(
            order_id,
            "accepted",
            master.id,
            master_name,
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔵 Ishni boshlash",
                        callback_data=f"startjob:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Bekor qilish",
                        callback_data=f"cancel:{order_id}",
                    ),
                ]
            ]
        )

        await query.edit_message_text(
            "🟡 BUYURTMA QABUL QILINDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n"
            f"👤 Mijoz: {row['customer_name']}\n"
            f"📞 Telefon: {row['phone']}\n"
            f"🛠 Xizmat: {row['service']}\n"
            f"📍 Manzil: {row['address']}\n"
            f"📝 Izoh: {row['description']}\n\n"
            f"👨‍🔧 Usta: {master_name}\n\n"
            "🔵 Ishni boshlash uchun tugmani bosing.",
            reply_markup=keyboard,
        )

        try:
            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"🟡 Buyurtmangiz №{order_id} qabul qilindi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception("Mijozga xabar yuborilmadi.")

        return

    # START JOB
    if action == "startjob":

        if row["status"] != "accepted":
            await query.answer(
                "⚠️ Buyurtma ish boshlash holatida emas.",
                show_alert=True,
            )
            return

        if row["master_id"] != master.id:
            await query.answer(
                "❌ Bu buyurtma sizga biriktirilmagan.",
                show_alert=True,
            )
            return

        await db_update_order(
            order_id,
            "in_progress",
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ishni yakunlash",
                        callback_data=f"complete:{order_id}",
                    ),
                    InlineKeyboardButton(
                        "❌ Bekor qilish",
                        callback_data=f"cancel:{order_id}",
                    ),
                ]
            ]
        )

        await query.edit_message_text(
            "🔵 ISH JARAYONIDA\n\n"
            f"🔢 Buyurtma: #{order_id}\n"
            f"👤 Mijoz: {row['customer_name']}\n"
            f"📞 Telefon: {row['phone']}\n"
            f"🛠 Xizmat: {row['service']}\n"
            f"📍 Manzil: {row['address']}\n"
            f"📝 Izoh: {row['description']}\n\n"
            f"👨‍🔧 Usta: {master_name}\n\n"
            "Иш тугагач, «✅ Ишни якунлаш»ни босинг.",
            reply_markup=keyboard,
        )

        try:
            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"🔵 Buyurtmangiz №{order_id} bo‘yicha "
                    "ish boshlandi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception("Mijozga ish xabari yuborilmadi.")

        return

    # COMPLETE
    if action == "complete":

        if row["status"] != "in_progress":
            await query.answer(
                "⚠️ Buyurtma ish jarayonida emas.",
                show_alert=True,
            )
            return

        if row["master_id"] != master.id:
            await query.answer(
                "❌ Bu buyurtma sizga biriktirilmagan.",
                show_alert=True,
            )
            return

        await db_update_order(
            order_id,
            "completed",
        )

        await query.edit_message_text(
            "✅ ISH YAKUNLANDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n"
            f"👤 Mijoz: {row['customer_name']}\n"
            f"📞 Telefon: {row['phone']}\n"
            f"🛠 Xizmat: {row['service']}\n"
            f"📍 Manzil: {row['address']}\n"
            f"📝 Izoh: {row['description']}\n\n"
            f"👨‍🔧 Usta: {master_name}\n"
            "📌 Holat: Yakunlandi\n\n"
            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )

        try:
            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"✅ Buyurtmangiz №{order_id} yakunlandi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "Rahmat! USTA 24 xizmatidan "
                    "foydalanganingiz uchun.\n\n"
                    "☎️ +998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception("Mijozga yakun xabari yuborilmadi.")

        return

    # CANCEL
    if action == "cancel":

        if row["status"] not in ("accepted", "in_progress"):
            await query.answer(
                "⚠️ Bu buyurtmani hozir bekor qilib bo‘lmaydi.",
                show_alert=True,
            )
            return

        if row["master_id"] != master.id:
            await query.answer(
                "❌ Bu buyurtma sizga biriktirilmagan.",
                show_alert=True,
            )
            return

        await db_update_order(
            order_id,
            "cancelled",
        )

        await query.edit_message_text(
            "❌ BUYURTMA BEKOR QILINDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n"
            f"👤 Mijoz: {row['customer_name']}\n"
            f"📞 Telefon: {row['phone']}\n"
            f"🛠 Xizmat: {row['service']}\n"
            f"📍 Manzil: {row['address']}\n"
            f"📝 Izoh: {row['description']}\n\n"
            f"👨‍🔧 Usta: {master_name}\n"
            "📌 Holat: Bekor qilindi",
        )

        try:
            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"❌ Buyurtmangiz №{order_id} bekor qilindi.\n\n"
                    f"👨‍🔧 Usta: {master_name}\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception("Mijozga bekor xabari yuborilmadi.")

        return

    # REJECT
    if action == "reject":

        if row["status"] != "open":
            await query.answer(
                "⚠️ Bu buyurtma allaqachon o‘zgargan.",
                show_alert=True,
            )
            return

        await db_update_order(
            order_id,
            "rejected",
            master.id,
            master_name,
        )

        await query.edit_message_text(
            "🚫 BUYURTMA RAD ETILDI\n\n"
            f"🔢 Buyurtma: #{order_id}\n"
            f"👤 Mijoz: {row['customer_name']}\n"
            f"📞 Telefon: {row['phone']}\n"
            f"🛠 Xizmat: {row['service']}\n"
            f"📍 Manzil: {row['address']}\n"
            f"📝 Izoh: {row['description']}\n\n"
            f"🚫 Rad etgan usta: {master_name}",
        )

        try:
            await context.bot.send_message(
                chat_id=row["customer_id"],
                text=(
                    f"⚠️ Buyurtmangiz №{order_id} "
                    "ushbu usta tomonidan qabul qilinmadi.\n\n"
                    "Boshqa usta topish uchun "
                    "USTA 24 bilan bog‘laning.\n\n"
                    "☎️ +998 77 069 00 03"
                ),
            )
        except Exception:
            logger.exception("Mijozga rad xabari yuborilmadi.")

        return


# =========================================================
# CHAT ID
# =========================================================

async def chat_id_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat = update.effective_chat

    await update.message.reply_text(
        f"🆔 Chat ID: {chat.id}\n"
        f"📌 Turi: {chat.type}\n"
        f"📌 Nomi: {chat.title or '-'}"
    )


# =========================================================
# ERROR
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "BOT XATOSI:",
        exc_info=context.error,
    )


# =========================================================
# RUN
# =========================================================

async def run_bot(application):

    await application.initialize()

    await init_database()

    await application.start()

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    logger.info("✅ TELEGRAM POLLING ISHLADI!")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


def main():

    logger.info("==============================")
    logger.info("USTA 24 BOT START")
    logger.info("ADMIN_ID = %s", ADMIN_ID)
    logger.info(
        "MASTERS_GROUP_ID = %s",
        MASTERS_GROUP_ID,
    )
    logger.info(
        "DATABASE_URL mavjud = %s",
        bool(DATABASE_URL),
    )
    logger.info("==============================")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("dispatcher", dispatcher)
    )

    application.add_handler(
        CommandHandler("id", chat_id_command)
    )

    application.add_handler(
        CallbackQueryHandler(order_callback)
    )

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
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

    logger.info("✅ Flask server ishga tushdi.")

    asyncio.run(
        run_bot(application)
    )


if __name__ == "__main__":
    main()
