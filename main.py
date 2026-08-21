# ============================================================
# USTA 24 ANDIJON — FULL MAIN.PY
# Python 3.11+ / python-telegram-bot 22.3 / PostgreSQL asyncpg
#
# ENV:
# BOT_TOKEN
# DATABASE_URL
# ADMIN_ID
# DISPATCHER_ID
# MASTERS_GROUP_ID
#
# PostgreSQL schema is created automatically on startup.
# No OTP.
# ============================================================

import os
import logging
import asyncio
from datetime import datetime
from contextlib import suppress

import asyncpg
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

# -------------------- CONFIG --------------------

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DISPATCHER_ID = int(os.getenv("DISPATCHER_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

DISPATCHER_PHONE = "+9987706900003"
BUSINESS_NAME = "USTA 24 ANDIJON"

SERVICES = [
    "🔌 Elektr",
    "🚰 Santexnika",
    "🔥 Gaz",
    "🚪 Eshik",
    "🪑 Mebel",
    "🛠 Remont",
    "📦 Ko‘chirish",
    "❓ Boshqa",
]

PAYMENT_TEXT = (
    "💰 To‘lov qoidasi:\n"
    "• Faqat naqd pul\n"
    "• Ish tugagandan keyin 100%\n"
    "• Oldindan to‘lov yo‘q\n"
    "• Click/Payme/Uzcard/Visa/Mastercard qabul qilinmaydi"
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("USTA24")

db_pool: asyncpg.Pool | None = None


# -------------------- DATABASE --------------------

async def db_init():
    global db_pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable topilmadi.")

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )

    async with db_pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            username TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'customer',
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS services (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            price NUMERIC(14,2) DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS orders (
            id BIGSERIAL PRIMARY KEY,
            customer_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            customer_name TEXT NOT NULL DEFAULT '',
            phone TEXT DEFAULT '',
            service TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            address TEXT DEFAULT '',
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            requested_time TEXT DEFAULT '',
            emergency_level TEXT DEFAULT 'normal',
            emergency_markup INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new',
            master_id BIGINT,
            master_name TEXT DEFAULT '',
            price NUMERIC(14,2) DEFAULT 0,
            payment_method TEXT DEFAULT 'cash_after_work',
            problem_photo_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            result_photo_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            group_message_id BIGINT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS order_history (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            actor_id BIGINT,
            old_status TEXT,
            new_status TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS ratings (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            customer_id BIGINT NOT NULL,
            master_id BIGINT NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS favorites (
            customer_id BIGINT NOT NULL,
            master_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(customer_id, master_id)
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id BIGSERIAL PRIMARY KEY,
            customer_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            note TEXT DEFAULT '',
            remind_at TIMESTAMPTZ,
            is_done BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id BIGSERIAL PRIMARY KEY,
            text TEXT NOT NULL,
            created_by BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_master ON orders(master_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        """)

        for service in SERVICES:
            await conn.execute(
                """
                INSERT INTO services(name)
                VALUES($1)
                ON CONFLICT(name) DO NOTHING
                """,
                service,
            )

    logger.info("PostgreSQL tayyor: barcha jadvallar avtomatik yaratildi.")


async def db_user(update: Update, role_hint: str | None = None):
    user = update.effective_user
    if not user:
        return None

    role = role_hint or "customer"
    if user.id == ADMIN_ID:
        role = "admin"
    elif user.id == DISPATCHER_ID:
        role = "dispatcher"

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id=$1",
            user.id,
        )
        if row:
            if role_hint and row["role"] == "customer" and role_hint == "master":
                role = "master"
            await conn.execute(
                """
                UPDATE users
                SET full_name=$2, username=$3, role=$4, updated_at=NOW()
                WHERE telegram_id=$1
                """,
                user.id,
                user.full_name or "",
                user.username or "",
                role,
            )
        else:
            await conn.execute(
                """
                INSERT INTO users(telegram_id, full_name, username, role)
                VALUES($1,$2,$3,$4)
                """,
                user.id,
                user.full_name or "",
                user.username or "",
                role,
            )

        return await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id=$1",
            user.id,
        )


async def set_phone(user_id: int, phone: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET phone=$2, updated_at=NOW() WHERE telegram_id=$1",
            user_id,
            phone,
        )


async def set_location(user_id: int, lat: float, lon: float):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET latitude=$2, longitude=$3, updated_at=NOW()
            WHERE telegram_id=$1
            """,
            user_id, lat, lon,
        )


async def create_order(data: dict):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO orders(
                customer_id, customer_name, phone, service, description,
                address, latitude, longitude, requested_time,
                emergency_level, emergency_markup, payment_method
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'cash_after_work')
            RETURNING *
            """,
            data["customer_id"],
            data["customer_name"],
            data["phone"],
            data["service"],
            data.get("description", ""),
            data.get("address", ""),
            data.get("latitude"),
            data.get("longitude"),
            data.get("requested_time", ""),
            data.get("emergency_level", "normal"),
            data.get("emergency_markup", 0),
        )
        await conn.execute(
            """
            INSERT INTO order_history(order_id, actor_id, old_status, new_status, note)
            VALUES($1,$2,NULL,'new','Yangi buyurtma')
            """,
            row["id"], data["customer_id"],
        )
        return row


async def get_order(order_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM orders WHERE id=$1",
            order_id,
        )


async def update_order_status(
    order_id: int,
    new_status: str,
    actor_id: int,
    note: str = "",
):
    async with db_pool.acquire() as conn:
        old = await conn.fetchval(
            "SELECT status FROM orders WHERE id=$1",
            order_id,
        )
        await conn.execute(
            """
            UPDATE orders
            SET status=$2,
                updated_at=NOW(),
                started_at=CASE WHEN $2='in_progress' THEN COALESCE(started_at,NOW()) ELSE started_at END,
                completed_at=CASE WHEN $2='completed' THEN NOW() ELSE completed_at END,
                cancelled_at=CASE WHEN $2='cancelled' THEN NOW() ELSE cancelled_at END
            WHERE id=$1
            """,
            order_id, new_status,
        )
        await conn.execute(
            """
            INSERT INTO order_history(order_id, actor_id, old_status, new_status, note)
            VALUES($1,$2,$3,$4,$5)
            """,
            order_id, actor_id, old, new_status, note,
        )


async def assign_master(order_id: int, master_id: int, master_name: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET master_id=$2, master_name=$3, status='accepted', updated_at=NOW()
            WHERE id=$1 AND status='new'
            """,
            order_id, master_id, master_name,
        )


async def add_problem_photo(order_id: int, file_id: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET problem_photo_ids = array_append(problem_photo_ids,$2),
                updated_at=NOW()
            WHERE id=$1
            """,
            order_id, file_id,
        )


async def add_result_photo(order_id: int, file_id: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE orders
            SET result_photo_ids = array_append(result_photo_ids,$2),
                updated_at=NOW()
            WHERE id=$1
            """,
            order_id, file_id,
        )


async def set_order_group_message(order_id: int, message_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE orders SET group_message_id=$2 WHERE id=$1",
            order_id, message_id,
        )


# -------------------- MENUS --------------------

def customer_menu():
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
            ["📁 Mening hujjatlarim", "🕊️ Do‘stga tavsiya qilish"],
            ["📞 Dispetcherga qo‘ng‘iroq", "🚨 24/7 Shoshilinch rejim"],
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
            ["🔔 Mijozlar bilan bog‘lanish", "📸 Galereya"],
            ["🛠 Xizmatlarni boshqarish", "📊 Ish statistikasi"],
            ["🏷️ Mening narxlarim", "📍 Ish hududim"],
            ["📅 Dam olish kunlari", "🔔 Bildirishnoma sozlamalari"],
            ["📝 Reytingni oshirish maslahatlari", "🎁 Usta bonuslari"],
            ["🤖 AI yordamchi", "📞 Texnik yordam"],
            ["📢 E’lonlar va yangiliklar", "🏆 Ustalar reytingi"],
            ["📞 Dispetcherga qo‘ng‘iroq", "🚨 24/7 Shoshilinch rejim"],
            ["🚪 Chiqish"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👥 Foydalanuvchilar", "🛠 Buyurtmalar"],
            ["👨‍🔧 Ustalar", "⭐ Reyting va sharhlar"],
            ["🎁 Loyallik va bonuslar", "💰 To‘lovlar"],
            ["🏷️ Chegirmalar va aksiyalar", "🛠 Xizmat turlari"],
            ["📊 Statistika va hisobot", "📢 E’lonlar va yangiliklar"],
            ["📞 Dispetcher", "⚙️ Sozlamalar"],
            ["📸 Rasm galereyasi", "📱 Botni boshqarish"],
            ["📞 Qo‘llab-quvvatlash", "🚨 24/7 Shoshilinch rejim"],
            ["🚪 Chiqish"],
        ],
        resize_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Telefon raqamimni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Geolokatsiyamni yuborish", request_location=True)],
         ["⏭️ O‘tkazib yuborish"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# -------------------- HELPERS --------------------

async def send_main_menu(update: Update, role: str):
    text = (
        f"🏠 <b>{BUSINESS_NAME}</b>\n\n"
        "Kerakli bo‘limni tanlang."
    )
    if role == "master":
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=master_menu())
    elif role == "admin" or role == "dispatcher":
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())
    else:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=customer_menu())


def order_text(row):
    emergency = ""
    if row["emergency_level"] != "normal":
        emergency = f"\n🚨 Shoshilinch: {row['emergency_level']} (+{row['emergency_markup']}%)"

    photos = len(row["problem_photo_ids"] or [])
    return (
        f"🆕 <b>YANGI BUYURTMA #{row['id']}</b>\n\n"
        f"🛠 Xizmat: {row['service']}\n"
        f"👤 Mijoz: {row['customer_name']}\n"
        f"📞 Telefon: {row['phone'] or '—'}\n"
        f"📍 Manzil: {row['address'] or '—'}\n"
        f"📝 Izoh: {row['description'] or '—'}\n"
        f"🕐 Vaqt: {row['requested_time'] or '—'}\n"
        f"📸 Muammo rasmi: {photos} ta"
        f"{emergency}\n\n"
        f"💰 To‘lov: faqat naqd, ish tugagach."
    )


def master_buttons(order_id: int):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ QABUL QILISH", callback_data=f"accept:{order_id}"),
                InlineKeyboardButton("❌ RAD ETISH", callback_data=f"reject:{order_id}"),
            ],
            [
                InlineKeyboardButton("🔧 Ishni boshlash", callback_data=f"start:{order_id}"),
                InlineKeyboardButton("✅ Ishni yakunlash", callback_data=f"complete:{order_id}"),
            ],
        ]
    )


# -------------------- START / ROLE --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db_user(update)

    if update.effective_user.id == ADMIN_ID:
        user_role = "admin"
    elif update.effective_user.id == DISPATCHER_ID:
        user_role = "dispatcher"
    else:
        user_role = user["role"] if user else "customer"

    context.user_data.clear()

    if user_role == "master":
        await update.message.reply_text(
            f"👨‍🔧 <b>{BUSINESS_NAME}</b>\n\nUsta paneliga xush kelibsiz.",
            parse_mode=ParseMode.HTML,
            reply_markup=master_menu(),
        )
    elif user_role in ("admin", "dispatcher"):
        await update.message.reply_text(
            f"👨‍💼 <b>{BUSINESS_NAME}</b>\n\nBoshqaruv paneli.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu(),
        )
    else:
        await update.message.reply_text(
            f"👋 Assalomu alaykum!\n\n"
            f"🏠 <b>{BUSINESS_NAME}</b>\n"
            "24/7 uy xizmatlari.\n\n"
            "Buyurtma berish uchun menyudan foydalaning.",
            parse_mode=ParseMode.HTML,
            reply_markup=customer_menu(),
        )


async def choose_master_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in (ADMIN_ID, DISPATCHER_ID):
        await update.message.reply_text("Siz boshqaruvchi sifatida kirdingiz.")
        return

    await db_user(update, "master")
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET role='master' WHERE telegram_id=$1",
            update.effective_user.id,
        )
    await update.message.reply_text(
        "👨‍🔧 Siz USTA rejimiga o‘tdingiz.",
        reply_markup=master_menu(),
    )


# -------------------- CUSTOMER ORDER FLOW --------------------

async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db_user(update)
    context.user_data["order"] = {
        "customer_id": update.effective_user.id,
        "customer_name": update.effective_user.full_name or "",
        "phone": user["phone"] if user else "",
        "problem_photo_ids": [],
    }
    buttons = [[InlineKeyboardButton(s, callback_data=f"service:{i}")]
               for i, s in enumerate(SERVICES)]
    await update.message.reply_text(
        "🛠 <b>Xizmat turini tanlang:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    context.user_data["state"] = "order_service"


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact:
        return
    await db_user(update)
    await set_phone(update.effective_user.id, contact.phone_number)

    state = context.user_data.get("state")
    if state == "order_phone":
        context.user_data["order"]["phone"] = contact.phone_number
        context.user_data["state"] = "order_description"
        await update.message.reply_text(
            "📝 Муаммони қисқача ёзинг.\n\nМасалан: розетка ишламаяпти."
        )
    else:
        await update.message.reply_text("✅ Telefon raqamingiz saqlandi.")


async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.location
    if not loc:
        return

    await db_user(update)
    await set_location(update.effective_user.id, loc.latitude, loc.longitude)

    if context.user_data.get("state") == "order_location":
        context.user_data["order"]["latitude"] = loc.latitude
        context.user_data["order"]["longitude"] = loc.longitude
        context.user_data["state"] = "order_time"
        await update.message.reply_text(
            "🕐 Qachon borish kerak?\nMasalan: Bugun 18:00 yoki Hozir."
        )


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if state == "order_problem_photo":
        photos = context.user_data["order"].setdefault("problem_photo_ids", [])
        photos.append(update.message.photo[-1].file_id)
        context.user_data["state"] = "order_address"
        await update.message.reply_text(
            "📍 Manzilni yozing.\n\n"
            "Masalan: Andijon shahar, Navoiy ko‘chasi 20."
        )
        return

    if state == "result_photo":
        order_id = context.user_data.get("result_order_id")
        if not order_id:
            return
        file_id = update.message.photo[-1].file_id
        await add_result_photo(order_id, file_id)
        context.user_data.setdefault("result_photos", []).append(file_id)
        count = len(context.user_data["result_photos"])
        if count >= 1:
            await update.message.reply_text(
                "📸 Rasm qabul qilindi.\n"
                "Yana rasm yuborishingiz mumkin yoki «Yakunlash» tugmasini bosing.",
                reply_markup=ReplyKeyboardMarkup(
                    [["✅ Yakunlash"], ["📸 Yana rasm"]],
                    resize_keyboard=True,
                ),
            )


async def order_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")

    if state == "order_description":
        context.user_data["order"]["description"] = text
        context.user_data["state"] = "order_problem_photo"
        await update.message.reply_text(
            "📸 Muammo rasmini yuboring (ixtiyoriy).\n"
            "Agar rasm bo‘lmasa, «O‘tkazib yuborish»ni bosing.",
            reply_markup=ReplyKeyboardMarkup(
                [["⏭️ O‘tkazib yuborish"]],
                resize_keyboard=True,
            ),
        )
        return

    if state == "order_address":
        context.user_data["order"]["address"] = text
        context.user_data["state"] = "order_location"
        await update.message.reply_text(
            "📍 Geolokatsiyangizni yuboring yoki o‘tkazib yuboring.",
            reply_markup=location_keyboard(),
        )
        return

    if state == "order_time":
        context.user_data["order"]["requested_time"] = text
        await show_order_confirmation(update, context)
        return


async def show_order_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data["order"]
    text = (
        "📋 <b>BUYURTMA TEKSHIRUVI</b>\n\n"
        f"🛠 Xizmat: {data.get('service','—')}\n"
        f"👤 Mijoz: {data.get('customer_name','—')}\n"
        f"📞 Telefon: {data.get('phone','—')}\n"
        f"📍 Manzil: {data.get('address','—')}\n"
        f"📝 Muammo: {data.get('description','—')}\n"
        f"🕐 Vaqt: {data.get('requested_time','—')}\n"
        f"📸 Muammo rasmi: {len(data.get('problem_photo_ids', []))} ta\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "Buyurtmani yuboramizmi?"
    )
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Bekor qilish", callback_data="order_cancel"),
            ]]
        ),
    )
    context.user_data["state"] = "order_confirm"


async def publish_order(context: ContextTypes.DEFAULT_TYPE, order_id: int):
    if not MASTERS_GROUP_ID:
        logger.warning("MASTERS_GROUP_ID berilmagan.")
        return

    row = await get_order(order_id)
    if not row:
        return

    message = await context.bot.send_message(
        chat_id=MASTERS_GROUP_ID,
        text=order_text(row),
        parse_mode=ParseMode.HTML,
        reply_markup=master_buttons(order_id),
    )
    await set_order_group_message(order_id, message.message_id)

    for file_id in row["problem_photo_ids"] or []:
        with suppress(Exception):
            await context.bot.send_photo(
                chat_id=MASTERS_GROUP_ID,
                photo=file_id,
                caption=f"📸 Buyurtma #{order_id} — muammo rasmi",
            )


# -------------------- CALLBACKS --------------------

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Service selection
    if data.startswith("service:"):
        idx = int(data.split(":")[1])
        service = SERVICES[idx]
        context.user_data["order"]["service"] = service

        user = await db_user(update)
        phone = user["phone"] if user else ""

        if phone:
            context.user_data["order"]["phone"] = phone
            context.user_data["state"] = "order_description"
            await query.message.reply_text(
                f"✅ Xizmat: {service}\n\n"
                "📝 Muammoni qisqacha yozing."
            )
        else:
            context.user_data["state"] = "order_phone"
            await query.message.reply_text(
                f"✅ Xizmat: {service}\n\n"
                "📞 Telefon raqamingizni yuboring:",
                reply_markup=phone_keyboard(),
            )
        return

    if data == "order_cancel":
        context.user_data.clear()
        await query.message.reply_text(
            "❌ Buyurtma bekor qilindi.",
            reply_markup=customer_menu(),
        )
        return

    if data == "order_confirm":
        order = context.user_data.get("order")
        if not order:
            await query.message.reply_text("Buyurtma ma’lumotlari topilmadi.")
            return

        row = await create_order(order)
        context.user_data.clear()

        await query.message.reply_text(
            f"✅ <b>Buyurtma #{row['id']} qabul qilindi!</b>\n\n"
            "Ustalar guruhiga yuborildi. Usta qabul qilgach sizga xabar beramiz.",
            parse_mode=ParseMode.HTML,
            reply_markup=customer_menu(),
        )

        await publish_order(context, row["id"])

        if ADMIN_ID:
            with suppress(Exception):
                await context.bot.send_message(
                    ADMIN_ID,
                    f"🆕 Yangi buyurtma #{row['id']}\n"
                    f"🛠 {row['service']}\n"
                    f"👤 {row['customer_name']}\n"
                    f"📞 {row['phone']}\n"
                    f"📍 {row['address']}",
                )
        return

    # Master accepts
    if data.startswith("accept:"):
        order_id = int(data.split(":")[1])
        row = await get_order(order_id)

        if not row:
            await query.message.reply_text("Buyurtma topilmadi.")
            return

        if row["status"] != "new":
            await query.answer("Bu buyurtma allaqachon qabul qilingan yoki yopilgan.", show_alert=True)
            return

        user = await db_user(update, "master")
        master_name = update.effective_user.full_name

        await assign_master(order_id, update.effective_user.id, master_name)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ #{order_id} ni {master_name} qabul qildi."
        )

        with suppress(Exception):
            await context.bot.send_message(
                row["customer_id"],
                f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                f"👨‍🔧 Usta: {master_name}\n"
                f"📋 Buyurtma: #{order_id}\n"
                "Usta ishni boshlaganda sizga xabar beramiz.",
                parse_mode=ParseMode.HTML,
            )
        return

    # Master rejects
    if data.startswith("reject:"):
        order_id = int(data.split(":")[1])
        row = await get_order(order_id)
        if not row:
            return

        await update_order_status(
            order_id, "new", update.effective_user.id, "Usta rad etdi"
        )
        await query.message.reply_text(
            f"❌ #{order_id} rad etildi. Boshqa ustalar ko‘rib chiqishi mumkin."
        )
        with suppress(Exception):
            await context.bot.send_message(
                row["customer_id"],
                f"❌ Buyurtma #{order_id}ni ushbu usta qabul qilmadi.\n"
                "🔄 Boshqa ustani qidiryapmiz.",
            )
        return

    # Start
    if data.startswith("start:"):
        order_id = int(data.split(":")[1])
        row = await get_order(order_id)

        if not row:
            return
        if row["master_id"] != update.effective_user.id:
            await query.answer("Bu buyurtma sizga biriktirilmagan.", show_alert=True)
            return

        await update_order_status(
            order_id, "in_progress", update.effective_user.id, "Ish boshlandi"
        )
        await query.message.reply_text(f"🔧 #{order_id} ish boshlandi!")

        with suppress(Exception):
            await context.bot.send_message(
                row["customer_id"],
                f"🔧 <b>Ish boshlandi!</b>\n\n"
                f"Buyurtma #{order_id}\n"
                f"👨‍🔧 Usta: {row['master_name']}",
                parse_mode=ParseMode.HTML,
            )
        return

    # Complete: result photo is mandatory
    if data.startswith("complete:"):
        order_id = int(data.split(":")[1])
        row = await get_order(order_id)

        if not row:
            return
        if row["master_id"] != update.effective_user.id:
            await query.answer("Bu buyurtma sizga biriktirilmagan.", show_alert=True)
            return

        context.user_data["result_order_id"] = order_id
        context.user_data["result_photos"] = []
        context.user_data["state"] = "result_photo"

        await query.message.reply_text(
            f"📸 <b>Buyurtma #{order_id}</b>\n\n"
            "Ish natijasi rasmini yuboring.\n"
            "Kamida 1 ta natija rasmi majburiy.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Rating
    if data.startswith("rate:"):
        order_id = int(data.split(":")[1])
        await query.message.reply_text(
            "⭐ Bahoni tanlang:",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("⭐", callback_data=f"rating:{order_id}:1"),
                    InlineKeyboardButton("⭐⭐", callback_data=f"rating:{order_id}:2"),
                    InlineKeyboardButton("⭐⭐⭐", callback_data=f"rating:{order_id}:3"),
                    InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rating:{order_id}:4"),
                    InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rating:{order_id}:5"),
                ]]
            ),
        )
        return

    if data.startswith("rating:"):
        _, order_id, rating = data.split(":")
        order_id = int(order_id)
        rating = int(rating)
        row = await get_order(order_id)

        if not row or not row["master_id"]:
            await query.message.reply_text("Buyurtma topilmadi.")
            return

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ratings(order_id, customer_id, master_id, rating)
                VALUES($1,$2,$3,$4)
                ON CONFLICT(order_id)
                DO UPDATE SET rating=EXCLUDED.rating
                """,
                order_id,
                update.effective_user.id,
                row["master_id"],
                rating,
            )

        await query.message.reply_text(f"⭐ Rahmat! Siz {rating}/5 baho berdingiz.")

        with suppress(Exception):
            await context.bot.send_message(
                row["master_id"],
                f"⭐ Mijoz sizga {rating}/5 baho qoldirdi! #{order_id}",
            )
        return


# -------------------- CUSTOMER FEATURES --------------------

async def my_orders(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, service, status, master_name, created_at
            FROM orders
            WHERE customer_id=$1
            ORDER BY id DESC
            LIMIT 10
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text("📋 Hozircha buyurtmalaringiz yo‘q.")
        return

    status_map = {
        "new": "🆕 Yangi",
        "accepted": "✅ Qabul qilingan",
        "in_progress": "🔧 Jarayonda",
        "completed": "🏁 Tugallangan",
        "cancelled": "❌ Bekor qilingan",
    }

    lines = ["📋 <b>Mening buyurtmalarim</b>\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} — {r['service']}\n"
            f"Holat: {status_map.get(r['status'], r['status'])}\n"
            f"Usta: {r['master_name'] or 'Hali biriktirilmagan'}\n"
        )

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def customer_statistics(update: Update):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER(WHERE status='completed') AS completed,
                COUNT(*) FILTER(WHERE status='cancelled') AS cancelled
            FROM orders WHERE customer_id=$1
            """,
            update.effective_user.id,
        )
    await update.message.reply_text(
        "📊 <b>Mening statistikam</b>\n\n"
        f"📋 Jami: {row['total']}\n"
        f"✅ Tugallangan: {row['completed']}\n"
        f"❌ Bekor qilingan: {row['cancelled']}",
        parse_mode=ParseMode.HTML,
    )


async def nearby_masters(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT full_name, phone, latitude, longitude
            FROM users
            WHERE role='master' AND is_active=TRUE
            ORDER BY full_name
            LIMIT 20
            """
        )

    if not rows:
        await update.message.reply_text("👨‍🔧 Hozircha ro‘yxatdan o‘tgan ustalar yo‘q.")
        return

    text = "🗺️ <b>Ustalar</b>\n\n"
    for r in rows:
        text += f"👨‍🔧 {r['full_name']} — {r['phone'] or 'Telefon yo‘q'}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# -------------------- MASTER FEATURES --------------------

async def master_new_orders(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM orders
            WHERE status='new'
            ORDER BY id DESC
            LIMIT 10
            """
        )

    if not rows:
        await update.message.reply_text("📋 Yangi buyurtmalar yo‘q.")
        return

    for row in rows:
        await update.message.reply_text(
            order_text(row),
            parse_mode=ParseMode.HTML,
            reply_markup=master_buttons(row["id"]),
        )


async def master_active(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM orders
            WHERE master_id=$1 AND status IN ('accepted','in_progress')
            ORDER BY id DESC
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text("✅ Faol buyurtmalar yo‘q.")
        return

    for row in rows:
        await update.message.reply_text(
            order_text(row),
            parse_mode=ParseMode.HTML,
            reply_markup=master_buttons(row["id"]),
        )


async def master_history(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, service, status, price, completed_at
            FROM orders
            WHERE master_id=$1 AND status='completed'
            ORDER BY id DESC
            LIMIT 20
            """,
            update.effective_user.id,
        )

    if not rows:
        await update.message.reply_text("⏳ Tugallangan ishlar yo‘q.")
        return

    text = "⏳ <b>Tugallangan ishlar</b>\n\n"
    for r in rows:
        text += f"#{r['id']} — {r['service']} — 💰 {r['price'] or 0}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def master_stats(update: Update):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER(WHERE status='completed') AS completed,
                COALESCE(SUM(price) FILTER(WHERE status='completed'),0) AS income
            FROM orders
            WHERE master_id=$1
            """,
            update.effective_user.id,
        )
        rating = await conn.fetchval(
            """
            SELECT COALESCE(AVG(rating),0)
            FROM ratings
            WHERE master_id=$1
            """,
            update.effective_user.id,
        )

    await update.message.reply_text(
        "📊 <b>Usta statistikasi</b>\n\n"
        f"📋 Jami ishlar: {row['total']}\n"
        f"✅ Tugallangan: {row['completed']}\n"
        f"💰 Daromad: {row['income']}\n"
        f"⭐ Reyting: {float(rating):.2f}",
        parse_mode=ParseMode.HTML,
    )


async def master_rating(update: Update):
    async with db_pool.acquire() as conn:
        rating = await conn.fetchval(
            "SELECT COALESCE(AVG(rating),0) FROM ratings WHERE master_id=$1",
            update.effective_user.id,
        )
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM ratings WHERE master_id=$1",
            update.effective_user.id,
        )

    await update.message.reply_text(
        f"⭐ <b>Reytingim</b>\n\n"
        f"⭐ O‘rtacha: {float(rating):.2f}\n"
        f"📝 Baholar: {count} ta",
        parse_mode=ParseMode.HTML,
    )


# -------------------- ADMIN --------------------

async def admin_statistics(update: Update):
    if update.effective_user.id not in (ADMIN_ID, DISPATCHER_ID):
        return

    async with db_pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        masters = await conn.fetchval("SELECT COUNT(*) FROM users WHERE role='master'")
        orders = await conn.fetchval("SELECT COUNT(*) FROM orders")
        new = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status='new'")
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE status IN ('accepted','in_progress')"
        )
        completed = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE status='completed'"
        )

    await update.message.reply_text(
        "📊 <b>USTA 24 HISOBOT</b>\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"👨‍🔧 Ustalar: {masters}\n"
        f"🛠 Jami buyurtmalar: {orders}\n"
        f"🆕 Yangi: {new}\n"
        f"🔧 Jarayonda: {active}\n"
        f"✅ Tugallangan: {completed}",
        parse_mode=ParseMode.HTML,
    )


async def admin_users(update: Update):
    if update.effective_user.id not in (ADMIN_ID, DISPATCHER_ID):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT telegram_id, full_name, username, phone, role, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 30
            """
        )

    if not rows:
        await update.message.reply_text("Foydalanuvchilar yo‘q.")
        return

    text = "👥 <b>Foydalanuvchilar</b>\n\n"
    for r in rows:
        text += (
            f"👤 {r['full_name'] or '—'}\n"
            f"ID: {r['telegram_id']}\n"
            f"Role: {r['role']}\n"
            f"📞 {r['phone'] or '—'}\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_orders(update: Update):
    if update.effective_user.id not in (ADMIN_ID, DISPATCHER_ID):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, customer_name, service, status, master_name, created_at
            FROM orders
            ORDER BY id DESC
            LIMIT 30
            """
        )

    text = "🛠 <b>Oxirgi buyurtmalar</b>\n\n"
    for r in rows:
        text += (
            f"#{r['id']} — {r['service']}\n"
            f"👤 {r['customer_name']}\n"
            f"Holat: {r['status']}\n"
            f"👨‍🔧 {r['master_name'] or '—'}\n\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def admin_masters(update: Update):
    if update.effective_user.id not in (ADMIN_ID, DISPATCHER_ID):
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT telegram_id, full_name, phone
            FROM users
            WHERE role='master'
            ORDER BY full_name
            """
        )

    if not rows:
        await update.message.reply_text("👨‍🔧 Ustalar yo‘q.")
        return

    text = "👨‍🔧 <b>Ustalar</b>\n\n"
    for r in rows:
        text += f"👨‍🔧 {r['full_name']} | ID: {r['telegram_id']} | {r['phone'] or '—'}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# -------------------- COMMON MENU ROUTER --------------------

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # Active order state has priority
    if context.user_data.get("state") in {
        "order_description",
        "order_address",
        "order_time",
    }:
        await order_text_input(update, context)
        return

    user = await db_user(update)
    role = user["role"] if user else "customer"

    if update.effective_user.id == ADMIN_ID:
        role = "admin"
    elif update.effective_user.id == DISPATCHER_ID:
        role = "dispatcher"

    # Universal
    if text == "🚪 Chiqish":
        context.user_data.clear()
        await update.message.reply_text("🏠 Bosh menyu.", reply_markup=customer_menu() if role == "customer" else master_menu() if role == "master" else admin_menu())
        return

    # Customer
    if role == "customer":
        if text == "🛒 Buyurtma berish":
            await start_order(update, context)
        elif text == "📋 Mening buyurtmalarim":
            await my_orders(update)
        elif text == "📊 Mening statistika":
            await customer_statistics(update)
        elif text == "🗺️ Yaqin atrofdagi ustalar":
            await nearby_masters(update)
        elif text == "📞 Dispetcherga qo‘ng‘iroq" or text == "📞 Tez yordam":
            await update.message.reply_text(
                f"📞 Dispetcher: {DISPATCHER_PHONE}\n"
                "🕐 24/7 ishlaydi."
            )
        elif text == "🚨 24/7 Shoshilinch rejim":
            await emergency_menu(update)
        elif text == "⭐ Reytingim":
            await update.message.reply_text("⭐ Sizning baholaringiz buyurtma tugagach ko‘rinadi.")
        elif text == "📝 Sharh qoldirish":
            await update.message.reply_text("📝 Tugallangan buyurtmadan keyin sharh qoldirishingiz mumkin.")
        elif text == "🔍 Buyurtma holati":
            await my_orders(update)
        elif text == "❌ Bekor qilish":
            await cancel_latest_order(update)
        elif text == "🔁 Qayta buyurtma":
            await start_order(update, context)
        elif text == "👨‍🔧 Mening ustalarim":
            await update.message.reply_text("👨‍🔧 Sizga xizmat ko‘rsatgan ustalar shu yerda ko‘rsatiladi.")
        elif text == "🎁 Loyallik va bonuslar":
            await update.message.reply_text("🎁 Hozircha bonus dasturi ishga tushirilmoqda.")
        elif text == "🏷️ Chegirmalar va aksiyalar":
            await update.message.reply_text("🏷️ Faol aksiyalar hozircha yo‘q.")
        elif text == "🔔 Bildirishnomalar":
            await update.message.reply_text("🔔 Bildirishnomalar yoqilgan.")
        elif text == "📌 Eslatmalarim":
            await update.message.reply_text("📌 Eslatmalar hozircha bo‘sh.")
        elif text == "📅 Yozilma (bron)":
            await update.message.reply_text("📅 Bron qilish buyurtma berish jarayonida amalga oshiriladi.")
        elif text == "🤖 AI yordamchi":
            await update.message.reply_text("🤖 AI yordamchi moduli tayyorlanmoqda.")
        elif text == "⚙️ Sozlamalar":
            await update.message.reply_text("⚙️ Sozlamalar: telefon va geolokatsiyani yangilashingiz mumkin.")
        elif text == "📁 Mening hujjatlarim":
            await update.message.reply_text("📁 Hujjatlar bo‘limi.")
        elif text == "🕊️ Do‘stga tavsiya qilish":
            await update.message.reply_text("🕊️ USTA 24 ni do‘stlaringizga tavsiya qiling!")
        return

    # Master
    if role == "master":
        if text == "📋 Yangi buyurtmalar":
            await master_new_orders(update)
        elif text == "✅ Mening faol buyurtmalarim":
            await master_active(update)
        elif text == "⏳ Tarix":
            await master_history(update)
        elif text == "📊 Ish statistikasi" or text == "💰 Ish haqi va hisobot":
            await master_stats(update)
        elif text == "⭐ Reytingim va sharhlar":
            await master_rating(update)
        elif text == "🏆 Ustalar reytingi":
            await top_masters(update)
        elif text == "📞 Dispetcherga qo‘ng‘iroq" or text == "📞 Texnik yordam":
            await update.message.reply_text(f"📞 Dispetcher: {DISPATCHER_PHONE}")
        elif text == "🚨 24/7 Shoshilinch rejim":
            await emergency_menu(update)
        elif text == "📍 Ish hududim":
            await update.message.reply_text("📍 Ish hududingiz: Andijon shahar.")
        elif text == "📅 Dam olish kunlari":
            await update.message.reply_text("📅 Dam olish kunlarini dispetcher bilan kelishib oling.")
        elif text == "🔔 Bildirishnoma sozlamalari":
            await update.message.reply_text("🔔 Yangi buyurtma bildirishnomalari yoqilgan.")
        elif text == "🎁 Usta bonuslari":
            await update.message.reply_text("🎁 Bonuslar faol ishlar va reyting asosida hisoblanadi.")
        elif text == "🛠 Xizmatlarni boshqarish":
            await update.message.reply_text("🛠 Xizmatlar ro‘yxati:\n" + "\n".join(SERVICES))
        elif text == "🏷️ Mening narxlarim":
            await update.message.reply_text("🏷️ Narxlarni dispetcher/admin bilan kelishib belgilang.")
        elif text == "📸 Galereya":
            await update.message.reply_text("📸 Tugallangan ish rasmlari buyurtmalar ichida saqlanadi.")
        elif text == "📢 E’lonlar va yangiliklar":
            await update.message.reply_text("📢 Hozircha yangi e’lon yo‘q.")
        elif text == "👨‍🔧 Ustalar reytingi":
            await top_masters(update)
        elif text == "🤖 AI yordamchi":
            await update.message.reply_text("🤖 AI yordamchi moduli tayyorlanmoqda.")
        return

    # Admin / dispatcher
    if role in ("admin", "dispatcher"):
        if text == "👥 Foydalanuvchilar":
            await admin_users(update)
        elif text == "🛠 Buyurtmalar":
            await admin_orders(update)
        elif text == "👨‍🔧 Ustalar":
            await admin_masters(update)
        elif text == "📊 Statistika va hisobot":
            await admin_statistics(update)
        elif text == "📞 Dispetchер" or text == "📞 Dispetcher":
            await update.message.reply_text(f"📞 {DISPATCHER_PHONE}\n24/7")
        elif text == "💰 To‘lovlar":
            await update.message.reply_text(PAYMENT_TEXT)
        elif text == "🛠 Xizmat turlari":
            await update.message.reply_text("\n".join(SERVICES))
        elif text == "🚨 24/7 Shoshilinch rejim":
            await emergency_menu(update)
        elif text == "📢 E’lonlar va yangiliklar":
            await update.message.reply_text("📢 E’lonlar moduli.")
        elif text == "⚙️ Sozlamalar":
            await update.message.reply_text("⚙️ Bot sozlamalari.")
        elif text == "📱 Botni boshqarish":
            await update.message.reply_text("📱 Bot ishlayapti.")
        elif text == "📸 Rasm galereyasi":
            await update.message.reply_text("📸 Galereya buyurtma natija rasmlaridan tuziladi.")
        elif text == "⭐ Reyting va sharhlar":
            await update.message.reply_text("⭐ Reytinglar PostgreSQL bazasida saqlanadi.")
        elif text == "🎁 Loyallik va bonuslar":
            await update.message.reply_text("🎁 Bonus moduli.")
        elif text == "🏷️ Chegirmalar va aksiyalar":
            await update.message.reply_text("🏷️ Aksiyalar moduli.")
        elif text == "📞 Qo‘llab-quvvatlash":
            await update.message.reply_text(f"📞 Qo‘llab-quvvatlash: {DISPATCHER_PHONE}")
        return


async def cancel_latest_order(update: Update):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM orders
            WHERE customer_id=$1 AND status IN ('new','accepted')
            ORDER BY id DESC LIMIT 1
            """,
            update.effective_user.id,
        )

    if not row:
        await update.message.reply_text("❌ Bekor qilish mumkin bo‘lgan buyurtma yo‘q.")
        return

    await update_order_status(
        row["id"], "cancelled", update.effective_user.id, "Mijoz bekor qildi"
    )
    await update.message.reply_text(f"❌ Buyurtma #{row['id']} bekor qilindi.")

    if row["master_id"]:
        with suppress(Exception):
            await update.effective_message.reply_text(
                f"📨 Ustaga: buyurtma #{row['id']} mijoz tomonidan bekor qilindi."
            )


async def top_masters(update: Update):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.full_name,
                   COALESCE(AVG(r.rating),0) AS rating,
                   COUNT(r.id) AS votes
            FROM users u
            LEFT JOIN ratings r ON r.master_id=u.telegram_id
            WHERE u.role='master'
            GROUP BY u.telegram_id, u.full_name
            ORDER BY rating DESC, votes DESC
            LIMIT 10
            """
        )

    if not rows:
        await update.message.reply_text("🏆 Reyting uchun ma’lumot yetarli emas.")
        return

    text = "🏆 <b>TOP 10 USTALAR</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. 👨‍🔧 {r['full_name']} — ⭐ {float(r['rating']):.2f} ({r['votes']} ta)\n"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def emergency_menu(update: Update):
    await update.message.reply_text(
        "🚨 <b>24/7 SHOSHILINCH REJIM</b>\n\n"
        "🚨 Darhol yordam kerak — kutish yo‘q!\n\n"
        "🔴 HOZIR (10–15 daqiqa) — +20%\n"
        "🟡 YARIM SOATDA — +10%\n"
        "🟢 1 SOATDA — oddiy narx\n\n"
        "💵 To‘lov: faqat naqd, ish tugagandan keyin.\n\n"
        "📞 Dispetcher: " + DISPATCHER_PHONE,
        parse_mode=ParseMode.HTML,
    )


# -------------------- PHOTO / SKIP --------------------

async def skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "⏭️ O‘tkazib yuborish":
        state = context.user_data.get("state")

        if state == "order_problem_photo":
            context.user_data["state"] = "order_address"
            await update.message.reply_text(
                "📍 Manzilni yozing.",
                reply_markup=ReplyKeyboardMarkup([["📍 Geolokatsiyani yuborish"]], resize_keyboard=True),
            )
        elif state == "order_location":
            context.user_data["state"] = "order_time"
            await update.message.reply_text(
                "🕐 Qachon borish kerak?\nMasalan: Bugun 18:00."
            )


# -------------------- ERROR / LIFECYCLE --------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("USTA24 update error", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        with suppress(Exception):
            await update.effective_message.reply_text(
                "⚠️ Texnik xatolik yuz berdi. Iltimos, qayta urinib ko‘ring."
            )


async def post_init(application: Application):
    await db_init()
    logger.info("USTA 24 ishga tushdi.")


async def post_shutdown(application: Application):
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
    logger.info("PostgreSQL connection pool yopildi.")


# -------------------- MAIN --------------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable topilmadi.")

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable topilmadi.")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("master", choose_master_role))
    application.add_handler(CallbackQueryHandler(callbacks))

    application.add_handler(
        MessageHandler(filters.CONTACT, receive_contact)
    )
    application.add_handler(
        MessageHandler(filters.LOCATION, receive_location)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO, receive_photo)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^⏭️ O‘tkazib yuborish$"),
            skip_handler,
        )
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_router)
    )

    application.add_error_handler(error_handler)

    logger.info("Bot polling boshlandi.")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
