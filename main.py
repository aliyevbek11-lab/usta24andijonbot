# ============================================================
# USTA 24 ANDIJON
# FULL MAIN.PY
#
# Python 3.11+
# python-telegram-bot 22.3
# PostgreSQL + asyncpg
#
# 1 BOT = CLIENT + MASTER + ADMIN + GROUP
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
    filters,
)


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0"))

DISPATCHER_PHONE = "+9987706900003"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi")

if ADMIN_ID == 0:
    logging.warning("ADMIN_ID sozlanmagan")

if MASTERS_GROUP_ID == 0:
    logging.warning("MASTERS_GROUP_ID sozlanmagan")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24")


# ============================================================
# GLOBAL DB
# ============================================================

db_pool = None


# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'client',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGINT PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                full_name TEXT,
                phone TEXT,
                services TEXT,
                district TEXT,
                rating DOUBLE PRECISION DEFAULT 5.0,
                rating_count INTEGER DEFAULT 0,
                completed_orders INTEGER DEFAULT 0,
                is_approved BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL,
                client_name TEXT,
                client_phone TEXT,
                service TEXT,
                description TEXT,
                address TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                preferred_time TEXT,
                emergency BOOLEAN DEFAULT FALSE,
                emergency_markup INTEGER DEFAULT 0,
                problem_photo_count INTEGER DEFAULT 0,
                result_photo_count INTEGER DEFAULT 0,
                price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new',
                master_id BIGINT,
                master_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS order_photos (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                photo_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                client_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, client_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                UNIQUE(client_id, master_id)
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS discounts (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                percent INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    logger.info("Database initialized")


# ============================================================
# USER FUNCTIONS
# ============================================================

async def save_user(user):
    if not user:
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users
                (id, username, full_name)
            VALUES
                ($1, $2, $3)
            ON CONFLICT (id)
            DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """,
            user.id,
            user.username or "",
            user.full_name or "",
        )


async def set_phone(user_id, phone):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET phone = $1
            WHERE id = $2
        """, phone, user_id)


async def set_role(user_id, role):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            UPDATE users
            SET role = $1
            WHERE id = $2
        """, role, user_id)


async def get_user(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1",
            user_id,
        )


async def get_master(user_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM masters WHERE user_id = $1",
            user_id,
        )


# ============================================================
# MENUS
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
            ["🚪 Chiqish"],
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
            ["🚪 Chiqish"],
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
            ["🚪 Chiqish"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    await save_user(user)

    if user.id == ADMIN_ID:
        await set_role(user.id, "admin")

        await update.message.reply_text(
            "👨‍💼 <b>USTA 24 ANDIJON</b>\n\n"
            "Админ панелига хуш келибсиз!",
            parse_mode="HTML",
            reply_markup=admin_menu(),
        )
        return

    master = await get_master(user.id)

    if master and master["is_approved"]:
        await set_role(user.id, "master")

        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 ANDIJON</b>\n\n"
            "Уста панелига хуш келибсиз!",
            parse_mode="HTML",
            reply_markup=master_menu(),
        )
        return

    await set_role(user.id, "client")

    await update.message.reply_text(
        "👋 <b>USTA 24 ANDIJON</b>\n\n"
        "🏠 Уйга хизмат кўрсатиш хизмати\n"
        "📍 Andijon shahar\n"
        "🕐 24/7 ишлаймиз\n\n"
        "Хизматларимиздан фойдаланиш учун менюдан танланг.",
        parse_mode="HTML",
        reply_markup=client_menu(),
    )


# ============================================================
# ORDER START
# ============================================================

async def order_start(update, context):

    context.user_data.clear()
    context.user_data["order_step"] = "service"

    services = [
        ["🔌 Elektr"],
        ["🚰 Santexnika"],
        ["🔥 Gaz"],
        ["🪑 Mebel yig'ish"],
        ["🚪 Eshik"],
        ["🧱 Ta'mirlash"],
        ["📦 Ko'chirish"],
        ["🛠 Boshqa xizmat"],
    ]

    await update.message.reply_text(
        "🛒 <b>Yangi buyurtma</b>\n\n"
        "🛠 Қайси хизмат керак?",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            services,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


# ============================================================
# ORDER SERVICE
# ============================================================

async def order_service(update, context):

    text = update.message.text

    if text.startswith("🛒"):
        return

    if context.user_data.get("order_step") != "service":
        return

    context.user_data["service"] = text
    context.user_data["order_step"] = "description"

    await update.message.reply_text(
        "📝 Муаммони қисқача ёзинг.\n\n"
        "Масалан:\n"
        "Розетка ишламаяпти\n"
        "ёки\n"
        "Крандан сув оқяпти"
    )


# ============================================================
# ORDER DESCRIPTION
# ============================================================

async def order_description(update, context):

    if context.user_data.get("order_step") != "description":
        return

    context.user_data["description"] = update.message.text
    context.user_data["order_step"] = "problem_photo"

    await update.message.reply_text(
        "📸 Муаммо расмини юборинг.\n\n"
        "Бу ихтиёрий.\n"
        "Расм бўлмаса, <b>Ўтказиб юбориш</b>ни босинг.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            [["⏭ O'tkazib yuborish"]],
            resize_keyboard=True,
        ),
    )


# ============================================================
# PROBLEM PHOTO
# ============================================================

async def order_problem_photo(update, context):

    if context.user_data.get("order_step") != "problem_photo":
        return

    if update.message.photo:

        file_id = update.message.photo[-1].file_id

        context.user_data.setdefault(
            "problem_photos",
            [],
        ).append(file_id)

        await update.message.reply_text(
            "✅ Расм қабул қилинди.\n\n"
            "Яна расм юборишингиз мумкин.\n"
            "Ёки давом этиш учун <b>📍 Манзил юбориш</b>ни босинг.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton(
                            "📍 Манзил юбориш",
                            request_location=True,
                        )
                    ],
                    ["⏭ O'tkazib yuborish"],
                ],
                resize_keyboard=True,
            ),
        )

        context.user_data["order_step"] = "location"
        return


# ============================================================
# LOCATION
# ============================================================

async def order_location(update, context):

    if context.user_data.get("order_step") != "location":
        return

    if update.message.location:

        location = update.message.location

        context.user_data["latitude"] = location.latitude
        context.user_data["longitude"] = location.longitude

        context.user_data["order_step"] = "address"

        await update.message.reply_text(
            "📍 Геолокация қабул қилинди.\n\n"
            "🏠 Манзилни ҳам ёзинг:"
        )
        return

    if update.message.text == "⏭ O'tkazib yuborish":

        context.user_data["latitude"] = None
        context.user_data["longitude"] = None
        context.user_data["order_step"] = "address"

        await update.message.reply_text(
            "🏠 Манзилни ёзинг:"
        )


# ============================================================
# ADDRESS
# ============================================================

async def order_address(update, context):

    if context.user_data.get("order_step") != "address":
        return

    context.user_data["address"] = update.message.text
    context.user_data["order_step"] = "phone"

    await update.message.reply_text(
        "📞 Телефон рақамингизни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton(
                        "📞 Telefon yuborish",
                        request_contact=True,
                    )
                ]
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# PHONE
# ============================================================

async def order_phone(update, context):

    if context.user_data.get("order_step") != "phone":
        return

    phone = None

    if update.message.contact:
        phone = update.message.contact.phone_number

    elif update.message.text:
        phone = update.message.text

    if not phone:
        await update.message.reply_text(
            "📞 Илтимос телефон рақамингизни юборинг."
        )
        return

    context.user_data["phone"] = phone

    await set_phone(
        update.effective_user.id,
        phone,
    )

    context.user_data["order_step"] = "time"

    await update.message.reply_text(
        "🕐 Қачон уста керак?\n\n"
        "Вақтни ёзинг.\n"
        "Масалан: 10:30",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["🚨 HOZIR"],
                ["⏭ 1 soat ichida"],
                ["⏭ Bugun"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# TIME
# ============================================================

async def order_time(update, context):

    if context.user_data.get("order_step") != "time":
        return

    context.user_data["preferred_time"] = update.message.text

    context.user_data["order_step"] = "confirm"

    service = context.user_data.get("service")
    description = context.user_data.get("description")
    address = context.user_data.get("address")
    phone = context.user_data.get("phone")
    preferred_time = context.user_data.get("preferred_time")

    emergency = preferred_time == "🚨 HOZIR"

    context.user_data["emergency"] = emergency

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Tasdiqlash",
                    callback_data="order_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Bekor qilish",
                    callback_data="order_cancel",
                )
            ],
        ]
    )

    await update.message.reply_text(
        "📋 <b>БУЮРТМА МАЪЛУМОТЛАРИ</b>\n\n"
        f"🛠 Хизмат: {service}\n"
        f"📝 Муаммо: {description}\n"
        f"🏠 Манзил: {address}\n"
        f"📞 Телефон: {phone}\n"
        f"🕐 Вақт: {preferred_time}\n"
        f"🚨 Шошилинч: {'ҲА' if emergency else 'Йўқ'}\n\n"
        "Тўғрими?",
        parse_mode="HTML",
        reply_markup=markup,
    )


# ============================================================
# CREATE ORDER
# ============================================================

async def create_order(user_id, data):

    user = await get_user(user_id)

    client_name = (
        user["full_name"]
        if user
        else "Mijoz"
    )

    emergency = data.get("emergency", False)

    markup_percent = 20 if emergency else 0

    price = 0

    async with db_pool.acquire() as conn:

        order_id = await conn.fetchval("""
            INSERT INTO orders (
                client_id,
                client_name,
                client_phone,
                service,
                description,
                address,
                latitude,
                longitude,
                preferred_time,
                emergency,
                emergency_markup,
                price,
                status
            )
            VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'new'
            )
            RETURNING id
        """,
            user_id,
            client_name,
            data.get("phone"),
            data.get("service"),
            data.get("description"),
            data.get("address"),
            data.get("latitude"),
            data.get("longitude"),
            data.get("preferred_time"),
            emergency,
            markup_percent,
            price,
        )

        for file_id in data.get("problem_photos", []):

            await conn.execute("""
                INSERT INTO order_photos
                    (order_id, file_id, photo_type)
                VALUES
                    ($1,$2,'problem')
            """,
                order_id,
                file_id,
            )

        await conn.execute("""
            UPDATE orders
            SET problem_photo_count = $1
            WHERE id = $2
        """,
            len(data.get("problem_photos", [])),
            order_id,
        )

    return order_id


# ============================================================
# ORDER CONFIRM
# ============================================================

async def order_confirm(update, context):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != update.effective_user.id:
        return

    if context.user_data.get("order_step") != "confirm":
        return

    order_id = await create_order(
        query.from_user.id,
        context.user_data,
    )

    context.user_data["last_order_id"] = order_id

    await query.edit_message_text(
        f"✅ <b>Буюртма қабул қилинди!</b>\n\n"
        f"🆔 Буюртма №{order_id}\n"
        f"🛠 {context.user_data.get('service')}\n"
        f"📍 {context.user_data.get('address')}\n\n"
        "👨‍🔧 Ҳозир усталарга юборилмоқда.",
        parse_mode="HTML",
    )

    await send_order_to_group(
        context.application,
        order_id,
    )

    await send_admin_new_order(
        context.application,
        order_id,
    )

    context.user_data.clear()

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "📋 Асосий менюга қайтишингиз мумкин."
        ),
        reply_markup=client_menu(),
    )


# ============================================================
# CANCEL ORDER
# ============================================================

async def order_cancel(update, context):

    query = update.callback_query

    await query.answer()

    context.user_data.clear()

    await query.edit_message_text(
        "❌ Буюртма бекор қилинди."
    )

    await context.bot.send_message(
        query.from_user.id,
        "Асосий меню:",
        reply_markup=client_menu(),
    )


# ============================================================
# SEND ORDER TO MASTER GROUP
# ============================================================

async def send_order_to_group(application, order_id):

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

        photos = await conn.fetch(
            """
            SELECT file_id
            FROM order_photos
            WHERE order_id = $1
              AND photo_type = 'problem'
            """,
            order_id,
        )

    if not order:
        return

    emergency_text = ""

    if order["emergency"]:
        emergency_text = (
            "\n🚨 <b>SHOSHILINCH BUYURTMA</b>\n"
            f"🔥 Ustama: {order['emergency_markup']}%\n"
        )

    text = (
        f"🆕 <b>YANGI BUYURTMA №{order['id']}</b>\n\n"
        f"🛠 Xizmat: {order['service']}\n"
        f"👤 Mijoz: {order['client_name']}\n"
        f"📞 Telefon: {order['client_phone']}\n"
        f"📍 Manzil: {order['address']}\n"
        f"📝 Muammo: {order['description']}\n"
        f"🕐 Vaqt: {order['preferred_time']}\n"
        f"📸 Muammo rasmi: {len(photos)} ta\n"
        f"{emergency_text}\n"
        "💵 To'lov: FAQAT NAQD + ISHDAN KEYIN"
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
                    callback_data=f"problem_photos:{order_id}",
                )
            ],
        ]
    )

    try:

        message = await application.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        for photo in photos:
            try:
                await application.bot.send_photo(
                    chat_id=MASTERS_GROUP_ID,
                    photo=photo["file_id"],
                )
            except Exception:
                logger.exception("Problem photo send error")

        return message

    except Exception:
        logger.exception("Group order send error")


# ============================================================
# ADMIN NEW ORDER
# ============================================================

async def send_admin_new_order(application, order_id):

    if not ADMIN_ID:
        return

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

    if not order:
        return

    text = (
        f"🆕 <b>YANGI BUYURTMA №{order['id']}</b>\n\n"
        f"👤 {order['client_name']}\n"
        f"📞 {order['client_phone']}\n"
        f"🛠 {order['service']}\n"
        f"📍 {order['address']}\n"
        f"🕐 {order['preferred_time']}"
    )

    await application.bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="HTML",
    )


# ============================================================
# ACCEPT ORDER
# ============================================================

async def accept_order(update, context, order_id):

    query = update.callback_query

    master_id = query.from_user.id
    master_name = query.from_user.full_name

    master = await get_master(master_id)

    if not master or not master["is_approved"]:
        await query.answer(
            "❌ Siz tasdiqlangan usta emassiz.",
            show_alert=True,
        )
        return

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1 FOR UPDATE",
            order_id,
        )

        if not order:
            await query.answer(
                "Buyurtma topilmadi.",
                show_alert=True,
            )
            return

        if order["status"] != "new":
            await query.answer(
                "Bu buyurtmani boshqa usta qabul qilgan.",
                show_alert=True,
            )
            return

        await conn.execute("""
            UPDATE orders
            SET
                status = 'accepted',
                master_id = $1,
                master_name = $2,
                accepted_at = CURRENT_TIMESTAMP
            WHERE id = $3
        """,
            master_id,
            master_name,
            order_id,
        )

    await query.answer(
        "✅ Buyurtma qabul qilindi!"
    )

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔧 ISHNI BOSHLASH",
                        callback_data=f"start_work:{order_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Bekor qilish",
                        callback_data=f"master_cancel:{order_id}",
                    )
                ],
            ]
        )
    )

    await context.bot.send_message(
        order["client_id"],
        (
            f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
            f"🆔 №{order_id}\n"
            f"👨‍🔧 Usta: {master_name}\n"
            f"⭐ Reyting: {master['rating']:.1f}\n\n"
            f"🕐 Vaqt: {order['preferred_time']}"
        ),
        parse_mode="HTML",
    )

    await context.bot.send_message(
        MASTERS_GROUP_ID,
        f"✅ №{order_id} buyurtmani {master_name} qabul qildi.",
    )


# ============================================================
# REJECT ORDER
# ============================================================

async def reject_order(update, context, order_id):

    query = update.callback_query

    master = await get_master(query.from_user.id)

    if not master or not master["is_approved"]:
        await query.answer(
            "❌ Usta tasdiqlanmagan.",
            show_alert=True,
        )
        return

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

        if not order:
            await query.answer(
                "Buyurtma topilmadi.",
                show_alert=True,
            )
            return

        if order["status"] != "new":
            await query.answer(
                "Buyurtma allaqachon olingan.",
                show_alert=True,
            )
            return

        await conn.execute("""
            UPDATE orders
            SET status = 'searching'
            WHERE id = $1
        """,
            order_id,
        )

    await query.answer("❌ Rad etildi")

    await query.edit_message_text(
        f"❌ №{order_id} rad etildi.\n"
        "🔄 Boshqa ustalar ko'rib chiqishi mumkin."
    )

    await context.bot.send_message(
        order["client_id"],
        (
            f"❌ №{order_id} buyurtmani ushbu usta qabul qilmadi.\n\n"
            "🔄 Boshqa ustani qidirmoqdamiz."
        ),
    )


# ============================================================
# START WORK
# ============================================================

async def start_work(update, context, order_id):

    query = update.callback_query

    master_id = query.from_user.id

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

        if not order:
            await query.answer(
                "Buyurtma topilmadi.",
                show_alert=True,
            )
            return

        if order["master_id"] != master_id:
            await query.answer(
                "❌ Bu buyurtma sizniki emas.",
                show_alert=True,
            )
            return

        if order["status"] != "accepted":
            await query.answer(
                "Buyurtmani boshlash mumkin emas.",
                show_alert=True,
            )
            return

        await conn.execute("""
            UPDATE orders
            SET
                status = 'in_progress',
                started_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """,
            order_id,
        )

    await query.answer("🔧 Ish boshlandi")

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📸 ISHNI YAKUNLASH",
                        callback_data=f"complete:{order_id}",
                    )
                ]
            ]
        )
    )

    await context.bot.send_message(
        order["client_id"],
        (
            f"🔧 <b>Ish boshlandi!</b>\n\n"
            f"🆔 Buyurtma №{order_id}\n"
            f"👨‍🔧 Usta: {order['master_name']}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# COMPLETE WORK
# ============================================================

async def complete_work(update, context, order_id):

    query = update.callback_query

    master_id = query.from_user.id

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

    if not order:
        await query.answer(
            "Buyurtma topilmadi.",
            show_alert=True,
        )
        return

    if order["master_id"] != master_id:
        await query.answer(
            "❌ Bu buyurtma sizniki emas.",
            show_alert=True,
        )
        return

    context.user_data["complete_order_id"] = order_id
    context.user_data["complete_step"] = "photos"

    await query.answer()

    await context.bot.send_message(
        master_id,
        (
            f"📸 <b>№{order_id} buyurtmani yakunlash</b>\n\n"
            "Иш натижасининг камида 1 та расмини юборинг.\n"
            "⚠️ Натижа расми мажбурий."
        ),
        parse_mode="HTML",
    )


# ============================================================
# RESULT PHOTO
# ============================================================

async def result_photo(update, context):

    order_id = context.user_data.get("complete_order_id")

    if not order_id:
        return

    if not update.message.photo:
        await update.message.reply_text(
            "📸 Илтимос иш натижаси расмини юборинг."
        )
        return

    file_id = update.message.photo[-1].file_id

    context.user_data.setdefault(
        "result_photos",
        [],
    ).append(file_id)

    async with db_pool.acquire() as conn:

        await conn.execute("""
            INSERT INTO order_photos
                (order_id, file_id, photo_type)
            VALUES
                ($1,$2,'result')
        """,
            order_id,
            file_id,
        )

        count = await conn.fetchval("""
            SELECT COUNT(*)
            FROM order_photos
            WHERE order_id = $1
              AND photo_type = 'result'
        """,
            order_id,
        )

        await conn.execute("""
            UPDATE orders
            SET result_photo_count = $1
            WHERE id = $2
        """,
            count,
            order_id,
        )

    await update.message.reply_text(
        f"✅ Расм қабул қилинди.\n"
        f"📸 Жами: {count} та\n\n"
        "Яна расм юборинг ёки пастдаги тугмани босинг.",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["📸 Yana rasm"],
                ["✅ Ishni yakunlash"],
            ],
            resize_keyboard=True,
        ),
    )

    context.user_data["complete_step"] = "finish"


# ============================================================
# FINISH WORK
# ============================================================

async def finish_work(update, context):

    order_id = context.user_data.get("complete_order_id")

    if not order_id:
        return

    photos = context.user_data.get(
        "result_photos",
        [],
    )

    if not photos:
        await update.message.reply_text(
            "❌ Камида 1 та натижа расми мажбурий."
        )
        return

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

        if not order:
            return

        await conn.execute("""
            UPDATE orders
            SET
                status = 'completed',
                completed_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """,
            order_id,
        )

        await conn.execute("""
            UPDATE masters
            SET completed_orders = completed_orders + 1
            WHERE user_id = $1
        """,
            order["master_id"],
        )

    await update.message.reply_text(
        (
            f"✅ <b>№{order_id} buyurtma yakunlandi!</b>\n\n"
            "💵 To'lov: NAQD\n"
            "📸 Natija rasmi yuborildi.\n"
            "⭐ Mijozdan reyting kutilmoqda."
        ),
        parse_mode="HTML",
        reply_markup=master_menu(),
    )

    # CLIENT
    await context.bot.send_message(
        order["client_id"],
        (
            f"✅ <b>Ish yakunlandi!</b>\n\n"
            f"🆔 №{order_id}\n"
            f"👨‍🔧 Usta: {order['master_name']}\n\n"
            "💵 To'lov: Faqat naqd\n"
            "💰 Ish tugagandan keyin\n\n"
            "⭐ Устага рейтинг қолдиринг:"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐ Reyting qoldirish",
                        callback_data=f"rating:{order_id}",
                    )
                ]
            ]
        ),
    )

    # SEND PHOTOS TO CLIENT
    async with db_pool.acquire() as conn:

        photos_rows = await conn.fetch("""
            SELECT file_id
            FROM order_photos
            WHERE order_id = $1
              AND photo_type = 'result'
        """,
            order_id,
        )

    for photo in photos_rows:
        try:
            await context.bot.send_photo(
                order["client_id"],
                photo["file_id"],
            )
        except Exception:
            logger.exception("Result photo send error")

    # GROUP
    await context.bot.send_message(
        MASTERS_GROUP_ID,
        (
            f"✅ <b>№{order_id} buyurtma yakunlandi!</b>\n\n"
            f"👨‍🔧 Usta: {order['master_name']}\n"
            f"📸 {len(photos_rows)} ta natija rasmi"
        ),
        parse_mode="HTML",
    )

    # ADMIN
    await context.bot.send_message(
        ADMIN_ID,
        (
            f"✅ <b>ISH YAKUNLANDI</b>\n\n"
            f"№{order_id}\n"
            f"👨‍🔧 {order['master_name']}\n"
            f"💰 Narx: {order['price']} so'm\n"
            f"📸 Rasmlar: {len(photos_rows)} ta"
        ),
        parse_mode="HTML",
    )

    context.user_data.clear()


# ============================================================
# RATING
# ============================================================

async def rating_menu(update, context, order_id):

    query = update.callback_query

    await query.answer()

    keyboard = [
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

    await query.edit_message_text(
        "⭐ Устага неча балл берасиз?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# SAVE RATING
# ============================================================

async def save_rating(update, context, order_id, rating):

    query = update.callback_query

    client_id = query.from_user.id

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1",
            order_id,
        )

        if not order:
            await query.answer(
                "Buyurtma topilmadi.",
                show_alert=True,
            )
            return

        if order["client_id"] != client_id:
            await query.answer(
                "❌ Siz bu buyurtma mijozi emassiz.",
                show_alert=True,
            )
            return

        try:

            await conn.execute("""
                INSERT INTO ratings
                    (order_id, client_id, master_id, rating)
                VALUES
                    ($1,$2,$3,$4)
            """,
                order_id,
                client_id,
                order["master_id"],
                rating,
            )

        except asyncpg.UniqueViolationError:

            await query.answer(
                "Siz allaqachon reyting bergansiz.",
                show_alert=True,
            )
            return

        stats = await conn.fetchrow("""
            SELECT
                AVG(rating) AS avg_rating,
                COUNT(*) AS count
            FROM ratings
            WHERE master_id = $1
        """,
            order["master_id"],
        )

        await conn.execute("""
            UPDATE masters
            SET
                rating = $1,
                rating_count = $2
            WHERE user_id = $3
        """,
            float(stats["avg_rating"] or 5),
            int(stats["count"] or 0),
            order["master_id"],
        )

    await query.edit_message_text(
        f"⭐ Раҳмат!\n\n"
        f"Сиз {rating}/5 рейтинг бердингиз."
    )

    await context.bot.send_message(
        order["master_id"],
        (
            f"⭐ <b>Янги рейтинг!</b>\n\n"
            f"№{order_id}\n"
            f"Мижоз: {rating}/5 ⭐"
        ),
        parse_mode="HTML",
    )


# ============================================================
# CLIENT ORDERS
# ============================================================

async def my_orders(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        orders = await conn.fetch("""
            SELECT *
            FROM orders
            WHERE client_id = $1
            ORDER BY id DESC
            LIMIT 20
        """,
            user_id,
        )

    if not orders:
        await update.message.reply_text(
            "📋 Сизда ҳозирча буюртмалар йўқ."
        )
        return

    lines = ["📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n"]

    status_map = {
        "new": "🆕 Янги",
        "searching": "🔎 Уста қидирилмоқда",
        "accepted": "✅ Қабул қилинган",
        "in_progress": "🔧 Жараёнда",
        "completed": "✅ Якунланган",
        "cancelled": "❌ Бекор қилинган",
    }

    for order in orders:

        lines.append(
            f"🆔 №{order['id']} | "
            f"{status_map.get(order['status'], order['status'])}\n"
            f"🛠 {order['service']}\n"
            f"📅 {order['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
    )


# ============================================================
# ACTIVE ORDER STATUS
# ============================================================

async def order_status(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow("""
            SELECT *
            FROM orders
            WHERE client_id = $1
              AND status IN (
                  'new',
                  'searching',
                  'accepted',
                  'in_progress'
              )
            ORDER BY id DESC
            LIMIT 1
        """,
            user_id,
        )

    if not order:

        await update.message.reply_text(
            "🔍 Фаол буюртмангиз йўқ."
        )
        return

    status_map = {
        "new": "🆕 Янги",
        "searching": "🔎 Уста қидирилмоқда",
        "accepted": "✅ Уста қабул қилди",
        "in_progress": "🔧 Иш бажарилмоқда",
    }

    await update.message.reply_text(
        (
            f"🔍 <b>БУЮРТМА ҲОЛАТИ</b>\n\n"
            f"🆔 №{order['id']}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address']}\n"
            f"📊 {status_map.get(order['status'])}\n"
            f"👨‍🔧 {order['master_name'] or 'Уста ҳали танланмаган'}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# CANCEL CLIENT ORDER
# ============================================================

async def cancel_client_order(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        order = await conn.fetchrow("""
            SELECT *
            FROM orders
            WHERE client_id = $1
              AND status IN ('new','searching','accepted')
            ORDER BY id DESC
            LIMIT 1
        """,
            user_id,
        )

        if not order:
            await update.message.reply_text(
                "❌ Бекор қилиш мумкин бўлган буюртма йўқ."
            )
            return

        await conn.execute("""
            UPDATE orders
            SET status = 'cancelled'
            WHERE id = $1
        """,
            order["id"],
        )

    await update.message.reply_text(
        f"❌ №{order['id']} буюртма бекор қилинди.",
        reply_markup=client_menu(),
    )

    if order["master_id"]:

        await context.bot.send_message(
            order["master_id"],
            f"❌ Мижоз №{order['id']} буюртмани бекор қилди."
        )

    await context.bot.send_message(
        MASTERS_GROUP_ID,
        f"❌ №{order['id']} буюртма мижоз томонидан бекор қилинди."
    )


# ============================================================
# MASTER NEW ORDERS
# ============================================================

async def master_new_orders(update, context):

    user_id = update.effective_user.id

    master = await get_master(user_id)

    if not master or not master["is_approved"]:
        await update.message.reply_text(
            "❌ Сиз тасдиқланган уста эмассиз."
        )
        return

    async with db_pool.acquire() as conn:

        orders = await conn.fetch("""
            SELECT *
            FROM orders
            WHERE status IN ('new','searching')
            ORDER BY id DESC
            LIMIT 20
        """)

    if not orders:

        await update.message.reply_text(
            "📋 Ҳозирча янги буюртмалар йўқ."
        )
        return

    for order in orders:

        text = (
            f"🆕 <b>№{order['id']}</b>\n\n"
            f"🛠 {order['service']}\n"
            f"📝 {order['description']}\n"
            f"📍 {order['address']}\n"
            f"🕐 {order['preferred_time']}\n"
            f"💵 Фақат нақд"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Qabul",
                        callback_data=f"accept:{order['id']}",
                    ),
                    InlineKeyboardButton(
                        "❌ Rad",
                        callback_data=f"reject:{order['id']}",
                    ),
                ]
            ]
        )

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# ============================================================
# MASTER ACTIVE
# ============================================================

async def master_active(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        orders = await conn.fetch("""
            SELECT *
            FROM orders
            WHERE master_id = $1
              AND status IN ('accepted','in_progress')
            ORDER BY id DESC
        """,
            user_id,
        )

    if not orders:

        await update.message.reply_text(
            "✅ Фаол буюртмаларингиз йўқ."
        )
        return

    for order in orders:

        buttons = []

        if order["status"] == "accepted":

            buttons.append(
                [
                    InlineKeyboardButton(
                        "🔧 Ishni boshlash",
                        callback_data=f"start_work:{order['id']}",
                    )
                ]
            )

        elif order["status"] == "in_progress":

            buttons.append(
                [
                    InlineKeyboardButton(
                        "📸 Ishni yakunlash",
                        callback_data=f"complete:{order['id']}",
                    )
                ]
            )

        await update.message.reply_text(
            (
                f"🆔 №{order['id']}\n"
                f"🛠 {order['service']}\n"
                f"👤 {order['client_name']}\n"
                f"📍 {order['address']}\n"
                f"📊 {order['status']}"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ============================================================
# MASTER HISTORY
# ============================================================

async def master_history(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        orders = await conn.fetch("""
            SELECT *
            FROM orders
            WHERE master_id = $1
              AND status = 'completed'
            ORDER BY id DESC
            LIMIT 30
        """,
            user_id,
        )

    if not orders:

        await update.message.reply_text(
            "⏳ Ҳали якунланган буюртмалар йўқ."
        )
        return

    text = "⏳ <b>ЯКУНЛАНГАН БУЮРТМАЛАР</b>\n\n"

    for order in orders:

        text += (
            f"🆔 №{order['id']}\n"
            f"🛠 {order['service']}\n"
            f"👤 {order['client_name']}\n"
            f"📅 {order['completed_at']}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# MASTER STATISTICS
# ============================================================

async def master_statistics(update, context):

    user_id = update.effective_user.id

    async with db_pool.acquire() as conn:

        data = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed,

                COUNT(*) FILTER (
                    WHERE status IN ('accepted','in_progress')
                ) AS active,

                COALESCE(SUM(price) FILTER (
                    WHERE status = 'completed'
                ), 0) AS income

            FROM orders
            WHERE master_id = $1
        """,
            user_id,
        )

        master = await get_master(user_id)

    await update.message.reply_text(
        (
            "📊 <b>ИШ СТАТИСТИКАМ</b>\n\n"
            f"✅ Якунланган: {data['completed']}\n"
            f"🔧 Фаол: {data['active']}\n"
            f"💰 Даромад: {data['income']:,} so'm\n"
            f"⭐ Рейтинг: {master['rating']:.1f}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# MASTER RATING
# ============================================================

async def master_rating(update, context):

    master = await get_master(
        update.effective_user.id
    )

    if not master:
        return

    async with db_pool.acquire() as conn:

        ratings = await conn.fetch("""
            SELECT rating, comment, created_at
            FROM ratings
            WHERE master_id = $1
            ORDER BY id DESC
            LIMIT 20
        """,
            update.effective_user.id,
        )

    text = (
        "⭐ <b>МЕНИНГ РЕЙТИНГИМ</b>\n\n"
        f"⭐ Умумий: {master['rating']:.1f}\n"
        f"📝 Баҳолар: {master['rating_count']}\n\n"
    )

    for r in ratings:

        text += (
            f"⭐ {r['rating']}/5\n"
            f"📅 {r['created_at'].strftime('%d.%m.%Y')}\n\n"
        )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(user_id):

    return user_id == ADMIN_ID


# ============================================================
# ADMIN USERS
# ============================================================

async def admin_users(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        clients = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE role = 'client'
        """)

        masters = await conn.fetchval("""
            SELECT COUNT(*)
            FROM users
            WHERE role = 'master'
        """)

    await update.message.reply_text(
        (
            "👥 <b>ФОЙДАЛАНУВЧИЛАР</b>\n\n"
            f"👥 Жами: {count}\n"
            f"👤 Мижозлар: {clients}\n"
            f"👨‍🔧 Усталар: {masters}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# ADMIN ORDERS
# ============================================================

async def admin_orders(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        data = await conn.fetchrow("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE status = 'new'
                ) AS new,
                COUNT(*) FILTER (
                    WHERE status = 'in_progress'
                ) AS active,
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed,
                COUNT(*) FILTER (
                    WHERE status = 'cancelled'
                ) AS cancelled
            FROM orders
        """)

    await update.message.reply_text(
        (
            "🛠 <b>БУЮРТМАЛАР</b>\n\n"
            f"📋 Жами: {data['total']}\n"
            f"🆕 Янги: {data['new']}\n"
            f"🔧 Жараёнда: {data['active']}\n"
            f"✅ Якунланган: {data['completed']}\n"
            f"❌ Бекор қилинган: {data['cancelled']}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# ADMIN MASTERS
# ============================================================

async def admin_masters(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        masters = await conn.fetch("""
            SELECT *
            FROM masters
            ORDER BY rating DESC
        """)

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Усталар базаси бўш."
        )
        return

    for master in masters:

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        (
                            "❌ Bloklash"
                            if master["is_active"]
                            else "✅ Aktivlashtirish"
                        ),
                        callback_data=(
                            f"toggle_master:{master['user_id']}"
                        ),
                    )
                ]
            ]
        )

        await update.message.reply_text(
            (
                f"👨‍🔧 <b>{master['full_name']}</b>\n\n"
                f"🆔 {master['user_id']}\n"
                f"📞 {master['phone'] or '-'}\n"
                f"⭐ {master['rating']:.1f}\n"
                f"📋 Ishlar: {master['completed_orders']}\n"
                f"✅ Tasdiqlangan: "
                f"{'Ha' if master['is_approved'] else 'Yo‘q'}"
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# ============================================================
# ADMIN STATISTICS
# ============================================================

async def admin_statistics(update, context):

    if not is_admin(update.effective_user.id):
        return

    async with db_pool.acquire() as conn:

        data = await conn.fetchrow("""
            SELECT
                COUNT(*) AS total_orders,
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed,
                COUNT(*) FILTER (
                    WHERE status = 'cancelled'
                ) AS cancelled,
                COUNT(*) FILTER (
                    WHERE emergency = TRUE
                ) AS emergency,
                COALESCE(SUM(price) FILTER (
                    WHERE status = 'completed'
                ),0) AS income
            FROM orders
        """)

        users = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )

        masters = await conn.fetchval(
            "SELECT COUNT(*) FROM masters WHERE is_approved = TRUE"
        )

    await update.message.reply_text(
        (
            "📊 <b>USTA 24 STATISTIKA</b>\n\n"
            f"👥 Фойдаланувчилар: {users}\n"
            f"👨‍🔧 Фаол усталар: {masters}\n"
            f"🛠 Буюртмалар: {data['total_orders']}\n"
            f"✅ Якунланган: {data['completed']}\n"
            f"❌ Бекор қилинган: {data['cancelled']}\n"
            f"🚨 Шошилинч: {data['emergency']}\n"
            f"💰 Даромад: {data['income']:,} so'm"
        ),
        parse_mode="HTML",
    )


# ============================================================
# DISPATCHER
# ============================================================

async def dispatcher(update, context):

    await update.message.reply_text(
        (
            "📞 <b>ДИСПЕТЧЕР</b>\n\n"
            f"📞 {DISPATCHER_PHONE}\n"
            "🕐 24/7\n"
            "📍 Andijon shahar\n\n"
            "🚨 Шошилинч ҳолатларда дарҳол қўнғироқ қилинг."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📞 Qo'ng'iroq qilish",
                        url=f"tel:{DISPATCHER_PHONE}",
                    )
                ]
            ]
        ),
    )


# ============================================================
# EMERGENCY
# ============================================================

async def emergency(update, context):

    await update.message.reply_text(
        (
            "🚨 <b>24/7 ШОШИЛИНЧ РЕЖИМ</b>\n\n"
            "🚨 ДАРҲОЛ ЁРДАМ КЕРАК!\n"
            "💨 24/7 ишлаймиз!\n\n"
            "🔹 Долзарб ҳолатлар:\n"
            "💧 Сув\n"
            "⚡ Электр\n"
            "🔥 Газ\n"
            "🚪 Эшик\n"
            "🚰 Қувур\n\n"
            "🔴 ҲОЗИР — 20% устама\n"
            "🟡 30 дақиқа — 10% устама\n"
            "🟢 1 соат — оддий нарх\n\n"
            "💵 Тўлов: ФАҚАТ НАҚД + ИШДАН КЕЙИН"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🚨 HOZIR USTA CHAQRISH",
                        callback_data="emergency_order",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📞 DISPETCHER",
                        url=f"tel:{DISPATCHER_PHONE}",
                    )
                ],
            ]
        ),
    )


# ============================================================
# OTHER CLIENT MENUS
# ============================================================

async def client_features(update, context):

    text = update.message.text

    answers = {

        "⭐ Reytingim":
            "⭐ Сизнинг шахсий рейтингингиз буюртмалар асосида ҳисобланади.",

        "📝 Sharh qoldirish":
            "📝 Якунланган буюртмангиздан кейин устага шарҳ қолдиришингиз мумкин.",

        "📌 Eslatmalarim":
            "📌 Ҳозирча сақланган эслатмалар йўқ.",

        "🗺️ Yaqin atrofdagi ustalar":
            "🗺️ Яқин усталарни топиш функцияси геолокация асосида ишлайди.",

        "📅 Yozilma (bron)":
            "📅 Брон қилиш учун янги буюртма беринг ва керакли вақтни кўрсатинг.",

        "🎁 Loyallik va bonuslar":
            "🎁 Лояллик дастури: доимий мижозлар учун бонуслар.",

        "🤖 AI yordamchi":
            "🤖 AI ёрдамчи: муаммони ёзинг, хизмат турини танлашда ёрдам беради.",

        "⚙️ Sozlamalar":
            "⚙️ Созламалар ҳозирча асосий режимда ишламоқда.",

        "🏷️ Chegirmalar va aksiyalar":
            "🏷️ Ҳозирги акциялар ҳақида маълумот админ томонидан берилади.",

        "🔔 Bildirishnomalar":
            "🔔 Буюртма ҳолати ўзгарганда автоматик хабар оласиз.",

        "📁 Mening hujjatlarim":
            "📁 Ҳужжатларингиз ҳозирча сақланмаган.",

        "🕊️ Do'stga tavsiya qilish":
            "🕊️ Дўстларингизга USTA 24 ни тавсия қилинг!",

        "📞 Tez yordam":
            f"📞 Тез ёрдам: {DISPATCHER_PHONE}",

    }

    if text in answers:

        await update.message.reply_text(
            answers[text]
        )


# ============================================================
# MASTER FEATURES
# ============================================================

async def master_features(update, context):

    text = update.message.text

    answers = {

        "💰 Ish haqi va hisobot":
            "💰 Иш ҳақи ва ҳисобот маълумотларингиз статистика бўлимида.",

        "📅 Kunlik ish jadvalim":
            "📅 Бугунги иш жадвали: фаол буюртмаларингиз.",

        "🔔 Mijozlar bilan bog'lanish":
            "🔔 Мижоз телефон рақами қабул қилинган буюртмада кўрсатилади.",

        "📸 Galereya":
            "📸 Якунланган ишларингиз расмлари базада сақланади.",

        "🛠 Xizmatlarni boshqarish":
            "🛠 Хизматларингизни админ билан келишиб ўзгартиришингиз мумкин.",

        "🏷️ Mening narxlarim":
            "🏷️ Нархлар админ томонидан назорат қилинади.",

        "📍 Ish hududim":
            "📍 Иш ҳудуди: Andijon shahar.",

        "📅 Dam olish kunlari":
            "📅 Дам олиш кунларингизни диспетчер/админга хабар қилинг.",

        "🔔 Bildirishnoma sozlamalari":
            "🔔 Билдиришномалар автоматик ёқилган.",

        "📝 Reytingni oshirish":
            "📝 Вақтида бориш, сифатли иш ва мижоз билан хушмуомалалик рейтингни оширади.",

        "🎁 Usta bonuslari":
            "🎁 Бонуслар якунланган буюртмалар ва рейтинг асосида ҳисобланади.",

        "🤖 AI yordamchi":
            "🤖 Уста учун AI ёрдамчи режими.",

        "📞 Texnik yordam":
            f"📞 Техник ёрдам: {DISPATCHER_PHONE}",

        "📢 E'lonlar va yangiliklar":
            "📢 Янги эълонлар шу ерда чиқади.",

        "🏆 Ustalar reytingi":
            "🏆 TOP усталар рейтингини кўриш учун админ маълумотларини олиш мумкин.",

        "🚨 24/7 Shosilinch rejim":
            "🚨 Шошилинч буюртмаларда 20% гача устама бўлиши мумкин.",

    }

    if text in answers:

        await update.message.reply_text(
            answers[text]
        )


# ============================================================
# ADMIN FEATURES
# ============================================================

async def admin_features(update, context):

    if not is_admin(update.effective_user.id):
        return

    text = update.message.text

    if text == "👥 Foydalanuvchilar":
        await admin_users(update, context)
        return

    if text == "🛠 Buyurtmalar":
        await admin_orders(update, context)
        return

    if text == "👨‍🔧 Ustalar":
        await admin_masters(update, context)
        return

    if text == "📊 Statistika va hisobot":
        await admin_statistics(update, context)
        return

    answers = {

        "⭐ Reyting va sharhlar":
            "⭐ Барча рейтинг ва шарҳлар база орқали сақланади.",

        "🎁 Loyallik va bonuslar":
            "🎁 Лояллик ва бонуслар админ томонидан бошқарилади.",

        "💰 To'lovlar":
            "💰 Тўлов тури: ФАҚАТ НАҚД, ИШДАН КЕЙИН.",

        "🏷️ Chegirmalar va aksiyalar":
            "🏷️ Акциялар ва чегирмаларни шу бўлим орқали бошқариш мумкин.",

        "🛠 Xizmat turlari":
            "🛠 Электр, сантехника, газ, мебель, эшик, таъмирлаш, кўчириш ва бошқа хизматлар.",

        "📢 E'lonlar va yangiliklar":
            "📢 Эълонлар модули тайёр.",

        "📞 Dispetcher":
            f"📞 Диспетчер: {DISPATCHER_PHONE}\n🕐 24/7",

        "⚙️ Sozlamalar":
            "⚙️ Бот созламалари ENV орқали бошқарилади.",

        "📸 Rasm galereyasi":
            "📸 Буюртма расмлари базага сақланади.",

        "📱 Botni boshqarish":
            "📱 Бот: USTA 24 ANDIJON\nСтатус: ишлаяпти.",

        "📞 Qo'llab-quvvatlash":
            f"📞 Қўллаб-қувватлаш: {DISPATCHER_PHONE}",

        "🚨 24/7 Shosilinch rejim":
            "🚨 24/7 режим актив.\n20% гача устама.",

    }

    if text in answers:

        await update.message.reply_text(
            answers[text]
        )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def callback_router(update, context):

    query = update.callback_query

    data = query.data or ""

    if data == "order_confirm":
        await order_confirm(update, context)
        return

    if data == "order_cancel":
        await order_cancel(update, context)
        return

    if data == "emergency_order":

        await query.answer()

        await context.bot.send_message(
            query.from_user.id,
            "🚨 Шошилинч буюртма бериш:",
            reply_markup=client_menu(),
        )

        context.user_data.clear()
        context.user_data["order_step"] = "service"
        context.user_data["emergency"] = True

        await context.bot.send_message(
            query.from_user.id,
            "🛠 Қайси хизмат керак?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["🔌 Elektr", "🚰 Santexnika"],
                    ["🔥 Gaz", "🚪 Eshik"],
                    ["🧱 Ta'mirlash", "🛠 Boshqa xizmat"],
                ],
                resize_keyboard=True,
            ),
        )

        return

    if data.startswith("accept:"):

        order_id = int(data.split(":")[1])

        await accept_order(
            update,
            context,
            order_id,
        )
        return

    if data.startswith("reject:"):

        order_id = int(data.split(":")[1])

        await reject_order(
            update,
            context,
            order_id,
        )
        return

    if data.startswith("start_work:"):

        order_id = int(data.split(":")[1])

        await start_work(
            update,
            context,
            order_id,
        )
        return

    if data.startswith("complete:"):

        order_id = int(data.split(":")[1])

        await complete_work(
            update,
            context,
            order_id,
        )
        return

    if data.startswith("rating:"):

        order_id = int(data.split(":")[1])

        await rating_menu(
            update,
            context,
            order_id,
        )
        return

    if data.startswith("rate:"):

        parts = data.split(":")

        order_id = int(parts[1])
        rating = int(parts[2])

        await save_rating(
            update,
            context,
            order_id,
            rating,
        )
        return

    if data.startswith("problem_photos:"):

        order_id = int(data.split(":")[1])

        await query.answer()

        async with db_pool.acquire() as conn:

            photos = await conn.fetch("""
                SELECT file_id
                FROM order_photos
                WHERE order_id = $1
                  AND photo_type = 'problem'
            """,
                order_id,
            )

        if not photos:

            await query.message.reply_text(
                "📸 Муаммо расмлари йўқ."
            )
            return

        for photo in photos:

            await context.bot.send_photo(
                query.message.chat_id,
                photo["file_id"],
            )

        return

    if data.startswith("toggle_master:"):

        if query.from_user.id != ADMIN_ID:
            await query.answer(
                "❌ Фақат админ.",
                show_alert=True,
            )
            return

        master_id = int(data.split(":")[1])

        async with db_pool.acquire() as conn:

            await conn.execute("""
                UPDATE masters
                SET is_active = NOT is_active
                WHERE user_id = $1
            """,
                master_id,
            )

        await query.answer(
            "✅ Holat o'zgartirildi"
        )

        return

    await query.answer()


# ============================================================
# MASTER REGISTRATION COMMAND
# ============================================================

async def become_master(update, context):

    user = update.effective_user

    await save_user(user)

    master = await get_master(user.id)

    if master:

        await update.message.reply_text(
            "👨‍🔧 Сизнинг уста профилингиз аллақачон мавжуд."
        )
        return

    async with db_pool.acquire() as conn:

        await conn.execute("""
            INSERT INTO masters (
                user_id,
                full_name
            )
            VALUES ($1,$2)
        """,
            user.id,
            user.full_name,
        )

    await update.message.reply_text(
        (
            "👨‍🔧 <b>УСТА РЎЙХАТДАН ЎТИШ</b>\n\n"
            "Аризангиз қабул қилинди.\n"
            "👨‍💼 Админ текширгандан кейин аккаунтингиз активлаштирилади."
        ),
        parse_mode="HTML",
    )

    await context.bot.send_message(
        ADMIN_ID,
        (
            "👨‍🔧 <b>ЯНГИ УСТА АРИЗАСИ</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 {user.id}\n"
            f"👤 @{user.username or '-'}"
        ),
        parse_mode="HTML",
    )


# ============================================================
# ADMIN APPROVE MASTER
# ============================================================

async def approve_master_command(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:

        await update.message.reply_text(
            "Формат:\n/approve_master USER_ID"
        )
        return

    try:
        master_id = int(context.args[0])
    except ValueError:

        await update.message.reply_text(
            "❌ USER_ID нотўғри."
        )
        return

    async with db_pool.acquire() as conn:

        master = await conn.fetchrow("""
            SELECT *
            FROM masters
            WHERE user_id = $1
        """,
            master_id,
        )

        if not master:

            await update.message.reply_text(
                "❌ Уста топилмади."
            )
            return

        await conn.execute("""
            UPDATE masters
            SET
                is_approved = TRUE,
                is_active = TRUE
            WHERE user_id = $1
        """,
            master_id,
        )

        await conn.execute("""
            UPDATE users
            SET role = 'master'
            WHERE id = $1
        """,
            master_id,
        )

    await update.message.reply_text(
        f"✅ {master_id} рақамли уста тасдиқланди."
    )

    try:

        await context.bot.send_message(
            master_id,
            (
                "🎉 <b>Табриклаймиз!</b>\n\n"
                "Сиз USTA 24 устаси сифатида тасдиқландингиз.\n"
                "👨‍🔧 Уста менюси актив."
            ),
            parse_mode="HTML",
            reply_markup=master_menu(),
        )

    except Exception:
        logger.exception("Master notification error")


# ============================================================
# TEXT ROUTER
# ============================================================

async def text_router(update, context):

    if not update.message:
        return

    text = update.message.text or ""

    user = update.effective_user

    await save_user(user)

    # ORDER FLOW
    step = context.user_data.get("order_step")

    if step == "service":
        await order_service(update, context)
        return

    if step == "description":
        await order_description(update, context)
        return

    if step == "problem_photo":

        if text == "⏭ O'tkazib yuborish":

            context.user_data["problem_photos"] = []
            context.user_data["order_step"] = "location"

            await update.message.reply_text(
                "📍 Манзилни юборинг:",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        [
                            KeyboardButton(
                                "📍 Manzil yuborish",
                                request_location=True,
                            )
                        ],
                        ["⏭ O'tkazib yuborish"],
                    ],
                    resize_keyboard=True,
                ),
            )
            return

        await order_problem_photo(
            update,
            context,
        )
        return

    if step == "location":

        await order_location(
            update,
            context,
        )
        return

    if step == "address":

        await order_address(
            update,
            context,
        )
        return

    if step == "phone":

        await order_phone(
            update,
            context,
        )
        return

    if step == "time":

        await order_time(
            update,
            context,
        )
        return

    if context.user_data.get("complete_order_id"):

        if text == "📸 Yana rasm":
            await update.message.reply_text(
                "📸 Натижа расмини юборинг."
            )
            return

        if text == "✅ Ishni yakunlash":

            await finish_work(
                update,
                context,
            )
            return

    # CLIENT
    if text == "🛒 Buyurtma berish":
        await order_start(update, context)
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

    if text == "📞 Dispetcherga qo'ng'iroq":
        await dispatcher(update, context)
        return

    if text == "📞 Tez yordam":
        await dispatcher(update, context)
        return

    if text == "🚨 24/7 Shosilinch rejim":
        await emergency(update, context)
        return

    # MASTER
    if text == "📋 Yangi buyurtmalar":
        await master_new_orders(update, context)
        return

    if text == "✅ Mening faol buyurtmalarim":
        await master_active(update, context)
        return

    if text == "⏳ Tarix":
        await master_history(update, context)
        return

    if text == "📊 Ish statistikasi":
        await master_statistics(update, context)
        return

    if text == "⭐ Reytingim va sharhlar":
        await master_rating(update, context)
        return

    if text == "📞 Dispetcherga qo'ng'iroq":
        await dispatcher(update, context)
        return

    if text == "🚨 24/7 Shosilinch rejim":
        await emergency(update, context)
        return

    # ADMIN
    if is_admin(user.id):

        await admin_features(
            update,
            context,
        )
        return

    # OTHER CLIENT FEATURES
    await client_features(
        update,
        context,
    )

    # OTHER MASTER FEATURES
    await master_features(
        update,
        context,
    )


# ============================================================
# PHOTO ROUTER
# ============================================================

async def photo_router(update, context):

    if context.user_data.get("order_step") == "problem_photo":

        await order_problem_photo(
            update,
            context,
        )
        return

    if context.user_data.get("complete_order_id"):

        await result_photo(
            update,
            context,
        )
        return


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update, context):

    logger.error(
        "Unhandled error:",
        exc_info=context.error,
    )


# ============================================================
# POST INIT
# ============================================================

async def post_init(application):

    await init_db()

    logger.info("USTA 24 started")


# ============================================================
# POST SHUTDOWN
# ============================================================

async def post_shutdown(application):

    global db_pool

    if db_pool:

        await db_pool.close()

        logger.info("Database pool closed")


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

    # COMMANDS
    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "usta",
            become_master,
        )
    )

    application.add_handler(
        CommandHandler(
            "approve_master",
            approve_master_command,
        )
    )

    # CALLBACKS
    application.add_handler(
        CallbackQueryHandler(
            callback_router,
        )
    )

    # PHOTOS
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_router,
        )
    )

    # CONTACT
    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            text_router,
        )
    )

    # LOCATION
    application.add_handler(
        MessageHandler(
            filters.LOCATION,
            text_router,
        )
    )

    # TEXT
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_router,
        )
    )

    # ERRORS
    application.add_error_handler(
        error_handler
    )

    logger.info(
        "🚀 USTA 24 ANDIJON BOT STARTING..."
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
