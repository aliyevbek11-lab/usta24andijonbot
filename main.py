# ============================================================
# USTA 24 ANDIJON — CLEAN SINGLE BOT
# Python 3.11+ / python-telegram-bot 22.3 / PostgreSQL asyncpg
#
# Environment:
# BOT_TOKEN
# DATABASE_URL
# ADMIN_ID
# MASTERS_GROUP_ID (optional)
#
# One bot: CLIENT + MASTER + ADMIN
# ============================================================

import os
import csv
import io
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("usta24")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)

SERVICES = [
    "🪑 Mebel",
    "🚚 Ko‘chirish",
    "🔧 Santexnika",
    "⚡ Elektrik",
    "🎨 Ta’mirlash",
    "❄️ Konditsioner",
    "🧹 Tozalash",
    "🔨 Boshqa",
]

STATUS_NEW = "new"
STATUS_ACCEPTED = "accepted"
STATUS_STARTED = "started"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_REJECTED = "rejected"

db_pool = None

# ---------------- DATABASE ----------------

async def db_init():
    global db_pool
    if not DATABASE_URL:
        log.warning("DATABASE_URL not set")
        return

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )

    async with db_pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            phone TEXT,
            role TEXT DEFAULT 'customer',
            language TEXT DEFAULT 'uz',
            notifications BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS masters (
            id BIGSERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            full_name TEXT,
            phone TEXT,
            username TEXT,
            services TEXT,
            work_time TEXT,
            approved BOOLEAN DEFAULT FALSE,
            active BOOLEAN DEFAULT TRUE,
            rating NUMERIC(3,2) DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id BIGSERIAL PRIMARY KEY,
            customer_id BIGINT,
            customer_name TEXT,
            phone TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            service TEXT,
            address TEXT,
            comment TEXT,
            status TEXT DEFAULT 'new',
            master_id BIGINT,
            master_name TEXT,
            price NUMERIC(14,2),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            accepted_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS order_history (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT,
            old_status TEXT,
            new_status TEXT,
            changed_by BIGINT,
            note TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT UNIQUE,
            customer_id BIGINT,
            master_id BIGINT,
            customer_rating INTEGER,
            master_rating INTEGER,
            comment TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            customer_id BIGINT,
            master_id BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY(customer_id, master_id)
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT,
            user_id BIGINT,
            kind TEXT,
            due_at TIMESTAMPTZ,
            sent BOOLEAN DEFAULT FALSE
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id BIGSERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            price NUMERIC(14,2) DEFAULT 0,
            active BOOLEAN DEFAULT TRUE
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id BIGSERIAL PRIMARY KEY,
            code TEXT UNIQUE,
            discount_percent INTEGER DEFAULT 0,
            active BOOLEAN DEFAULT TRUE,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""")
        await c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")

        # --------------------------------------------------------
        # ROBUST MIGRATION FOR OLD INSTALLATIONS
        # --------------------------------------------------------
        async def ensure_column(table, column, definition):
            exists = await c.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name=$1
                      AND column_name=$2
                )
                """,
                table, column
            )
            if not exists:
                try:
                    await c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                    log.info("Migration: added %s.%s", table, column)
                except Exception:
                    exists2 = await c.fetchval(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema='public'
                              AND table_name=$1
                              AND column_name=$2
                        )
                        """,
                        table, column
                    )
                    if not exists2:
                        raise

        migrations = [
            ("users","username","TEXT"),("users","full_name","TEXT"),
            ("users","phone","TEXT"),("users","role","TEXT DEFAULT 'customer'"),
            ("users","language","TEXT DEFAULT 'uz'"),
            ("users","notifications","BOOLEAN DEFAULT TRUE"),

            ("masters","telegram_id","BIGINT"),("masters","full_name","TEXT"),
            ("masters","phone","TEXT"),("masters","username","TEXT"),
            ("masters","services","TEXT"),("masters","work_time","TEXT"),
            ("masters","approved","BOOLEAN DEFAULT FALSE"),
            ("masters","active","BOOLEAN DEFAULT TRUE"),
            ("masters","rating","NUMERIC(3,2) DEFAULT 0"),
            ("masters","rating_count","INTEGER DEFAULT 0"),
            ("masters","created_at","TIMESTAMPTZ DEFAULT NOW()"),

            ("orders","customer_id","BIGINT"),("orders","customer_name","TEXT"),
            ("orders","phone","TEXT"),("orders","latitude","DOUBLE PRECISION"),
            ("orders","longitude","DOUBLE PRECISION"),("orders","service","TEXT"),
            ("orders","address","TEXT"),("orders","comment","TEXT"),
            ("orders","status","TEXT DEFAULT 'new'"),("orders","master_id","BIGINT"),
            ("orders","master_name","TEXT"),("orders","price","NUMERIC(14,2) DEFAULT 0"),
            ("orders","created_at","TIMESTAMPTZ DEFAULT NOW()"),
            ("orders","accepted_at","TIMESTAMPTZ"),("orders","started_at","TIMESTAMPTZ"),
            ("orders","completed_at","TIMESTAMPTZ"),("orders","cancelled_at","TIMESTAMPTZ"),

            ("reminders","order_id","BIGINT"),("reminders","user_id","BIGINT"),
            ("reminders","kind","TEXT"),("reminders","due_at","TIMESTAMPTZ"),
            ("reminders","sent","BOOLEAN DEFAULT FALSE"),

            ("ratings","order_id","BIGINT"),("ratings","customer_id","BIGINT"),
            ("ratings","master_id","BIGINT"),("ratings","customer_rating","INTEGER"),
            ("ratings","master_rating","INTEGER"),("ratings","comment","TEXT"),
        ]

        for table, column, definition in migrations:
            await ensure_column(table, column, definition)

        # Backfill due_at from legacy reminder column names if they exist.
        legacy_due_names = ("due", "due_time", "remind_at", "reminder_at", "scheduled_at")
        due_source = None
        for legacy in legacy_due_names:
            if await c.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public'
                      AND table_name='reminders'
                      AND column_name=$1
                )
                """, legacy
            ):
                due_source = legacy
                break

        if due_source:
            try:
                await c.execute(
                    f"UPDATE reminders SET due_at={due_source} "
                    f"WHERE due_at IS NULL AND {due_source} IS NOT NULL"
                )
            except Exception:
                log.exception("Could not backfill reminders.due_at from %s", due_source)

        await c.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_due_at "
            "ON reminders(due_at) WHERE sent=FALSE"
        )
        await c.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id)"
        )
        await c.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_master ON orders(master_id)"
        )


        for s in SERVICES:
            await c.execute(
                "INSERT INTO services(name) VALUES($1) ON CONFLICT(name) DO NOTHING", s
            )

    log.info("PostgreSQL initialized")


async def db_exec(sql, *args):
    if not db_pool:
        return None
    async with db_pool.acquire() as c:
        return await c.execute(sql, *args)


async def db_fetch(sql, *args):
    if not db_pool:
        return []
    async with db_pool.acquire() as c:
        return await c.fetch(sql, *args)


async def db_fetchrow(sql, *args):
    if not db_pool:
        return None
    async with db_pool.acquire() as c:
        return await c.fetchrow(sql, *args)


async def save_user(user, phone=None):
    if not db_pool:
        return
    await db_exec("""
        INSERT INTO users(id,username,full_name,phone)
        VALUES($1,$2,$3,$4)
        ON CONFLICT(id) DO UPDATE SET
            username=EXCLUDED.username,
            full_name=EXCLUDED.full_name,
            phone=COALESCE(EXCLUDED.phone,users.phone)
    """, user.id, user.username, user.full_name, phone)


async def log_status(order_id, old, new, user_id, note=""):
    await db_exec("""
        INSERT INTO order_history(order_id,old_status,new_status,changed_by,note)
        VALUES($1,$2,$3,$4,$5)
    """, order_id, old, new, user_id, note)


# ---------------- KEYBOARDS ----------------

def client_menu():
    return ReplyKeyboardMarkup([
        ["📝 Buyurtma berish", "📋 Buyurtmalarim"],
        ["🔎 Buyurtma holati", "❌ Buyurtmani bekor qilish"],
        ["🔄 Qayta buyurtma", "👨‍🔧 Mening ustalarim"],
        ["⭐ Reytingim", "💬 Sharh qoldirish"],
        ["🔔 Eslatmalarim", "⚙️ Sozlamalar"],
        ["👨‍🔧 Usta bo‘lish"],
    ], resize_keyboard=True)


def master_menu():
    return ReplyKeyboardMarkup([
        ["📝 Yangi buyurtmalar", "📋 Mening buyurtmalarim"],
        ["👤 Mijozlarim", "📊 Mening statistikam"],
        ["💰 Kunlik daromad", "⭐ Reytingim"],
        ["👤 Profil", "⚙️ Sozlamalar"],
    ], resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup([
        ["👨‍🔧 Ustalar", "📦 Buyurtmalar"],
        ["👤 Mijozlar", "📊 Statistika"],
        ["📈 Hisobot", "💰 Narxlar"],
        ["📢 Xabarlar", "🎟 Kuponlar"],
        ["⚙️ Sozlamalar"],
    ], resize_keyboard=True)


def back_menu():
    return ReplyKeyboardMarkup([["⬅️ Orqaga"]], resize_keyboard=True)


# ---------------- START / ROLE ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await save_user(u)

    if u.id == ADMIN_ID:
        await update.message.reply_text(
            "👑 <b>USTA 24 ANDIJON — ADMIN</b>\n\nKerakli bo‘limni tanlang.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_menu(),
        )
        return

    master = await db_fetchrow(
        "SELECT * FROM masters WHERE telegram_id=$1 AND approved=TRUE AND active=TRUE",
        u.id,
    )
    if master:
        await update.message.reply_text(
            "👨‍🔧 <b>USTA 24 ANDIJON — USTA</b>\n\nXush kelibsiz!",
            parse_mode=ParseMode.HTML,
            reply_markup=master_menu(),
        )
        return

    await update.message.reply_text(
        "👤 <b>USTA 24 ANDIJON</b>\n\nXush kelibsiz! Buyurtma berish uchun menyudan foydalaning.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )


# ---------------- CLIENT ORDER ----------------

C_NAME, C_PHONE, C_LOCATION, C_SERVICE, C_ADDRESS, C_COMMENT = range(6)

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👤 Ismingizni kiriting:", reply_markup=back_menu())
    return C_NAME


async def order_name(update, context):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text(
        "📞 Telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)],
             ["⬅️ Orqaga"]], resize_keyboard=True
        ),
    )
    return C_PHONE


async def order_phone(update, context):
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    context.user_data["phone"] = phone
    await update.message.reply_text(
        "📍 Геолокацияни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Geolokatsiyani yuborish", request_location=True)],
             ["⏭ Manzilni qo‘lda kiritaman"], ["⬅️ Orqaga"]], resize_keyboard=True
        ),
    )
    return C_LOCATION


async def order_location(update, context):
    if update.message.location:
        loc = update.message.location
        context.user_data["lat"] = loc.latitude
        context.user_data["lon"] = loc.longitude
        await update.message.reply_text(
            "🛠 Xizmat turini tanlang:",
            reply_markup=ReplyKeyboardMarkup([[s] for s in SERVICES] + [["⬅️ Orqaga"]], resize_keyboard=True),
        )
        return C_SERVICE
    if update.message.text == "⏭ Manzilni qo‘lda kiritaman":
        context.user_data["lat"] = None
        context.user_data["lon"] = None
        await update.message.reply_text("📍 Manzilni kiriting:")
        return C_ADDRESS
    await update.message.reply_text("📍 Iltimos, geolokatsiyani yuboring yoki qo‘lda kiritish tugmasini bosing.")
    return C_LOCATION


async def order_service(update, context):
    if update.message.text == "⬅️ Orqaga":
        return C_LOCATION
    context.user_data["service"] = update.message.text
    await update.message.reply_text("📍 Манзилни киритинг:")
    return C_ADDRESS


async def order_address(update, context):
    context.user_data["address"] = update.message.text.strip()
    await update.message.reply_text("📝 Izoh / bajariladigan ishni yozing:")
    return C_COMMENT


async def schedule_order_reminders(order_id, user_id):
    """Create automatic 2h, 6h and 24h reminders."""
    if not db_pool:
        return
    now = datetime.now(timezone.utc)
    try:
        await db_exec(
            """
            INSERT INTO reminders(order_id,user_id,kind,due_at,sent)
            VALUES($1,$2,'2 soat',$3,FALSE),
                  ($1,$2,'6 soat',$4,FALSE),
                  ($1,$2,'24 soat',$5,FALSE)
            """,
            order_id, user_id,
            now + timedelta(hours=2),
            now + timedelta(hours=6),
            now + timedelta(hours=24),
        )
    except Exception:
        log.exception("Could not create reminders for order #%s", order_id)


async def order_comment(update, context):
    context.user_data["comment"] = update.message.text.strip()
    d = context.user_data

    if not db_pool:
        await update.message.reply_text("❌ PostgreSQL ulanmagan.", reply_markup=client_menu())
        return ConversationHandler.END

    row = await db_fetchrow("""
        INSERT INTO orders(
            customer_id,customer_name,phone,latitude,longitude,service,address,comment,status
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,'new')
        RETURNING id
    """, update.effective_user.id, d["name"], d["phone"], d.get("lat"), d.get("lon"),
        d["service"], d["address"], d["comment"])

    order_id = row["id"]
    await schedule_order_reminders(order_id, update.effective_user.id)

    await update.message.reply_text(
        f"✅ <b>Buyurtma qabul qilindi!</b>\n\n"
        f"🔢 ID: <b>#{order_id}</b>\n"
        f"🛠 Xizmat: {d['service']}\n"
        f"📍 Manzil: {d['address']}\n\n"
        "👨‍🔧 Ustaga yuborilmoqda.",
        parse_mode=ParseMode.HTML,
        reply_markup=client_menu(),
    )

    if MASTERS_GROUP_ID:
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Qabul qilish", callback_data=f"take:{order_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{order_id}")
            ]])
            await context.bot.send_message(
                MASTERS_GROUP_ID,
                f"🆕 <b>YANGI BUYURTMA #{order_id}</b>\n\n"
                f"👤 {d['name']}\n📞 {d['phone']}\n🛠 {d['service']}\n"
                f"📍 {d['address']}\n📝 {d['comment']}",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception:
            log.exception("Cannot send order to masters group")

    return ConversationHandler.END


async def order_cancel(update, context):
    await update.message.reply_text("❌ Buyurtma berish bekor qilindi.", reply_markup=client_menu())
    return ConversationHandler.END


order_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📝 Buyurtma berish$"), order_start)],
    states={
        C_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_name)],
        C_PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), order_phone)],
        C_LOCATION: [MessageHandler(filters.LOCATION | (filters.TEXT & ~filters.COMMAND), order_location)],
        C_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_service)],
        C_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_address)],
        C_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_comment)],
    },
    fallbacks=[MessageHandler(filters.Regex("^⬅️ Orqaga$"), order_cancel)],
    allow_reentry=True,
)


# ---------------- CLIENT PAGES ----------------

async def my_orders(update, context):
    rows = await db_fetch("""
        SELECT id,service,address,status,created_at,master_name
        FROM orders WHERE customer_id=$1 ORDER BY id DESC LIMIT 30
    """, update.effective_user.id)
    if not rows:
        await update.message.reply_text("📋 Sizda hozircha buyurtmalar yo‘q.", reply_markup=client_menu())
        return
    text = "📋 <b>BUYURTMALARIM</b>\n\n"
    for r in rows:
        text += f"#{r['id']} | {r['service']} | {r['status']} | {r['address']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=client_menu())


async def order_status_prompt(update, context):
    await update.message.reply_text("🔎 Buyurtma ID sini yuboring:", reply_markup=back_menu())
    context.user_data["await_order_status"] = True


async def order_status_text(update, context):
    if context.user_data.pop("await_order_status", False):
        try:
            oid = int(update.message.text.strip().replace("#", ""))
        except ValueError:
            await update.message.reply_text("❌ ID raqam bo‘lishi kerak.")
            return
        r = await db_fetchrow("SELECT * FROM orders WHERE id=$1 AND customer_id=$2", oid, update.effective_user.id)
        if not r:
            await update.message.reply_text("❌ Buyurtma topilmadi.", reply_markup=client_menu())
            return
        await update.message.reply_text(
            f"🔎 <b>#{r['id']}</b>\n🛠 {r['service']}\n📍 {r['address']}\n"
            f"📌 Holat: <b>{r['status']}</b>\n👨‍🔧 Usta: {r['master_name'] or 'Hali biriktirilmagan'}",
            parse_mode=ParseMode.HTML, reply_markup=client_menu()
        )


async def cancel_order_prompt(update, context):
    rows = await db_fetch("""
        SELECT id,service,status FROM orders
        WHERE customer_id=$1 AND status IN ('new','accepted','started')
        ORDER BY id DESC
    """, update.effective_user.id)
    if not rows:
        await update.message.reply_text("❌ Bekor qilish mumkin bo‘lgan faol buyurtma yo‘q.", reply_markup=client_menu())
        return
    kb = [[InlineKeyboardButton(f"#{r['id']} — {r['service']}", callback_data=f"ccancel:{r['id']}")] for r in rows]
    await update.message.reply_text("❌ Buyurtmani tanlang:", reply_markup=InlineKeyboardMarkup(kb))


async def reorder(update, context):
    rows = await db_fetchrow("""
        SELECT * FROM orders WHERE customer_id=$1 ORDER BY id DESC LIMIT 1
    """, update.effective_user.id)
    if not rows:
        await update.message.reply_text("🔄 Qayta buyurtma qilish uchun eski buyurtma yo‘q.", reply_markup=client_menu())
        return
    context.user_data.update({
        "name": rows["customer_name"], "phone": rows["phone"],
        "lat": rows["latitude"], "lon": rows["longitude"],
        "service": rows["service"], "address": rows["address"],
        "comment": rows["comment"] or "",
    })
    await update.message.reply_text("🔄 Oldingi buyurtma ma’lumotlari topildi. Yangi buyurtma yaratish uchun izohni yuboring:")
    context.user_data["reorder"] = True


async def customer_text_router(update, context):
    """Handle text entered after a client menu asks for an ID/comment."""
    text = (update.message.text or "").strip()

    if context.user_data.get("await_order_status"):
        context.user_data.pop("await_order_status", None)
        try:
            oid = int(text.replace("#", ""))
        except ValueError:
            await update.message.reply_text(
                "❌ ID raqam bo‘lishi kerak. Masalan: 25",
                reply_markup=client_menu()
            )
            return
        r = await db_fetchrow(
            "SELECT * FROM orders WHERE id=$1 AND customer_id=$2",
            oid, update.effective_user.id
        )
        if not r:
            await update.message.reply_text(
                "❌ Bu ID bo‘yicha buyurtma topilmadi.",
                reply_markup=client_menu()
            )
            return
        await update.message.reply_text(
            f"🔎 <b>BUYURTMA #{r['id']}</b>\n\n"
            f"🛠 Xizmat: {r['service'] or '-'}\n"
            f"📍 Manzil: {r['address'] or '-'}\n"
            f"📌 Holat: <b>{r['status']}</b>\n"
            f"👨‍🔧 Usta: {r['master_name'] or 'Hali biriktirilmagan'}",
            parse_mode=ParseMode.HTML,
            reply_markup=client_menu()
        )
        return

    if context.user_data.get("reorder"):
        context.user_data.pop("reorder", None)
        d = context.user_data
        r = await db_fetchrow(
            """
            INSERT INTO orders(
                customer_id,customer_name,phone,latitude,longitude,
                service,address,comment,status
            )
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,'new')
            RETURNING id
            """,
            update.effective_user.id,
            d.get("name", update.effective_user.full_name),
            d.get("phone"),
            d.get("lat"),
            d.get("lon"),
            d.get("service"),
            d.get("address"),
            text,
        )
        await schedule_order_reminders(r["id"], update.effective_user.id)
        await update.message.reply_text(
            f"✅ <b>Qayta buyurtma yaratildi!</b>\n🔢 ID: #{r['id']}",
            parse_mode=ParseMode.HTML,
            reply_markup=client_menu()
        )
        if MASTERS_GROUP_ID:
            try:
                await context.bot.send_message(
                    MASTERS_GROUP_ID,
                    f"🆕 <b>QAYTA BUYURTMA #{r['id']}</b>\n"
                    f"👤 {d.get('name','-')}\n📞 {d.get('phone','-')}\n"
                    f"🛠 {d.get('service','-')}\n📍 {d.get('address','-')}\n"
                    f"📝 {text}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Qabul qilish", callback_data=f"take:{r['id']}"),
                        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{r['id']}")
                    ]])
                )
            except Exception:
                log.exception("Could not send reordered job to masters group")
        return

    if context.user_data.get("await_review"):
        context.user_data.pop("await_review", None)
        try:
            oid = int(text.replace("#", ""))
        except ValueError:
            await update.message.reply_text(
                "❌ Buyurtma ID sini raqam bilan yuboring.",
                reply_markup=client_menu()
            )
            return
        r = await db_fetchrow(
            "SELECT id,master_id,status FROM orders WHERE id=$1 AND customer_id=$2",
            oid, update.effective_user.id
        )
        if not r or r["status"] != STATUS_COMPLETED or not r["master_id"]:
            await update.message.reply_text(
                "❌ Faqat tugallangan, usta biriktirilgan buyurtmaga sharh/baho beriladi.",
                reply_markup=client_menu()
            )
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("1 ⭐", callback_data=f"rate:{oid}:1"),
            InlineKeyboardButton("2 ⭐", callback_data=f"rate:{oid}:2"),
            InlineKeyboardButton("3 ⭐", callback_data=f"rate:{oid}:3"),
            InlineKeyboardButton("4 ⭐", callback_data=f"rate:{oid}:4"),
            InlineKeyboardButton("5 ⭐", callback_data=f"rate:{oid}:5"),
        ]])
        context.user_data["review_order_id"] = oid
        await update.message.reply_text(
            f"⭐ #{oid} uchun bahoni tanlang:",
            reply_markup=kb
        )
        return

    await customer_menu(update, context)


async def customer_menu(update, context):
    t = update.message.text
    if t == "📋 Buyurtmalarim":
        await my_orders(update, context)
    elif t == "🔎 Buyurtma holati":
        await order_status_prompt(update, context)
    elif t == "❌ Buyurtmani bekor qilish":
        await cancel_order_prompt(update, context)
    elif t == "🔄 Qayta buyurtma":
        await reorder(update, context)
    elif t == "👨‍🔧 Mening ustalarim":
        rows = await db_fetch("""
            SELECT m.telegram_id,m.full_name,m.phone,m.rating
            FROM favorites f JOIN masters m ON m.telegram_id=f.master_id
            WHERE f.customer_id=$1
        """, update.effective_user.id)
        if not rows:
            await update.message.reply_text("👨‍🔧 Sevimli ustalar yo‘q.", reply_markup=client_menu())
        else:
            await update.message.reply_text(
                "👨‍🔧 <b>Mening ustalarim</b>\n\n" +
                "\n".join(f"• {r['full_name']} ⭐ {r['rating']}" for r in rows),
                parse_mode=ParseMode.HTML, reply_markup=client_menu()
            )
    elif t == "⭐ Reytingim":
        r = await db_fetchrow("""
            SELECT COALESCE(AVG(customer_rating),0) avg, COUNT(*) cnt
            FROM ratings WHERE customer_id=$1
        """, update.effective_user.id)
        await update.message.reply_text(f"⭐ Reytingim: {float(r['avg'] or 0):.1f}/5\n📊 Baholar: {r['cnt']}", reply_markup=client_menu())
    elif t == "💬 Sharh qoldirish":
        await update.message.reply_text("💬 Avval tugallangan buyurtmangiz ID sini yuboring.")
        context.user_data["await_review"] = True
    elif t == "🔔 Eslatmalarim":
        rows = await db_fetch("""
            SELECT kind,due_at,sent FROM reminders WHERE user_id=$1 ORDER BY due_at DESC LIMIT 20
        """, update.effective_user.id)
        await update.message.reply_text(
            "🔔 <b>Eslatmalarim</b>\n\n" + (
                "\n".join(f"• {r['kind']} — {r['due_at']} — {'✅' if r['sent'] else '⏳'}" for r in rows)
                if rows else "Hozircha eslatmalar yo‘q."
            ), parse_mode=ParseMode.HTML, reply_markup=client_menu()
        )
    elif t == "⚙️ Sozlamalar":
        await update.message.reply_text(
            "⚙️ Sozlamalar\n\n🌐 Til: O‘zbek\n🔔 Xabarlar: Yoqilgan",
            reply_markup=client_menu()
        )
    elif t == "👨‍🔧 Usta bo‘lish":
        await master_apply(update, context)


# ---------------- MASTER ----------------

async def master_apply(update, context):
    u = update.effective_user
    await save_user(u)
    await db_exec("""
        INSERT INTO masters(telegram_id,full_name,username,approved,active)
        VALUES($1,$2,$3,FALSE,TRUE)
        ON CONFLICT(telegram_id) DO UPDATE SET full_name=EXCLUDED.full_name,username=EXCLUDED.username
    """, u.id, u.full_name, u.username)
    await update.message.reply_text("👨‍🔧 Usta ro‘yxatdan o‘tish so‘rovi yuborildi. Admin tasdiqlashini kuting.")


async def master_check(update, context):
    m = await db_fetchrow("SELECT * FROM masters WHERE telegram_id=$1", update.effective_user.id)
    if not m:
        await update.message.reply_text("👨‍🔧 Siz hali usta sifatida ro‘yxatdan o‘tmagansiz.")
        return
    await update.message.reply_text(
        f"👨‍🔧 <b>Profil</b>\n\n👤 {m['full_name']}\n📞 {m['phone'] or '-'}\n"
        f"🛠 {m['services'] or '-'}\n⭐ {m['rating']}\n📌 {'Tasdiqlangan' if m['approved'] else 'Kutilmoqda'}",
        parse_mode=ParseMode.HTML, reply_markup=master_menu()
    )


async def master_new_orders(update, context):
    m = await db_fetchrow("SELECT * FROM masters WHERE telegram_id=$1 AND approved=TRUE AND active=TRUE", update.effective_user.id)
    if not m:
        await update.message.reply_text("❌ Usta profilingiz tasdiqlanmagan.", reply_markup=client_menu())
        return
    rows = await db_fetch("""
        SELECT * FROM orders WHERE status='new' AND master_id IS NULL ORDER BY id DESC LIMIT 30
    """)
    if not rows:
        await update.message.reply_text("📝 Yangi buyurtmalar hozircha yo‘q.", reply_markup=master_menu())
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Qabul qilish", callback_data=f"take:{r['id']}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{r['id']}")
        ]])
        await update.message.reply_text(
            f"🆕 <b>#{r['id']}</b>\n👤 {r['customer_name']}\n📞 {r['phone']}\n"
            f"🛠 {r['service']}\n📍 {r['address']}\n📝 {r['comment'] or '-'}",
            parse_mode=ParseMode.HTML, reply_markup=kb
        )


async def master_orders(update, context):
    rows = await db_fetch("""
        SELECT * FROM orders WHERE master_id=$1 ORDER BY id DESC LIMIT 50
    """, update.effective_user.id)
    if not rows:
        await update.message.reply_text("📋 Sizda hali buyurtmalar yo‘q.", reply_markup=master_menu())
        return
    for r in rows:
        buttons = []
        if r["status"] == STATUS_ACCEPTED:
            buttons.append(InlineKeyboardButton("🔧 Ishni boshlash", callback_data=f"start:{r['id']}"))
        if r["status"] == STATUS_STARTED:
            buttons.append(InlineKeyboardButton("🏁 Ishni yakunlash", callback_data=f"done:{r['id']}"))
        if buttons:
            kb = InlineKeyboardMarkup([buttons])
        else:
            kb = None
        await update.message.reply_text(
            f"#{r['id']} | {r['service']}\n📍 {r['address']}\n📌 {r['status']}\n💰 {r['price'] or '-'}",
            reply_markup=kb
        )


async def master_customers(update, context):
    rows = await db_fetch("""
        SELECT DISTINCT customer_id,customer_name,phone,COUNT(*) cnt
        FROM orders WHERE master_id=$1 GROUP BY customer_id,customer_name,phone
        ORDER BY cnt DESC LIMIT 50
    """, update.effective_user.id)
    if not rows:
        await update.message.reply_text("👤 Mijozlaringiz hozircha yo‘q.", reply_markup=master_menu())
        return
    await update.message.reply_text(
        "👤 <b>Mijozlarim</b>\n\n" + "\n".join(
            f"• {r['customer_name']} | {r['phone']} | {r['cnt']} ta" for r in rows
        ), parse_mode=ParseMode.HTML, reply_markup=master_menu()
    )


async def master_stats(update, context):
    r = await db_fetchrow("""
        SELECT
          COUNT(*) total,
          COUNT(*) FILTER(WHERE status='completed') completed,
          COUNT(*) FILTER(WHERE status='started') started,
          COALESCE(SUM(price) FILTER(WHERE status='completed'),0) income
        FROM orders WHERE master_id=$1
    """, update.effective_user.id)
    await update.message.reply_text(
        f"📊 <b>Mening statistikam</b>\n\n"
        f"📦 Jami: {r['total']}\n✅ Tugallangan: {r['completed']}\n"
        f"🔧 Jarayonda: {r['started']}\n💰 Daromad: {r['income']}",
        parse_mode=ParseMode.HTML, reply_markup=master_menu()
    )


async def master_daily_income(update, context):
    r = await db_fetchrow("""
        SELECT COALESCE(SUM(price),0) income, COUNT(*) cnt
        FROM orders
        WHERE master_id=$1 AND status='completed'
          AND completed_at::date=CURRENT_DATE
    """, update.effective_user.id)
    await update.message.reply_text(
        f"💰 <b>Bugungi daromad</b>\n\n💵 {r['income']}\n📦 {r['cnt']} ta buyurtma",
        parse_mode=ParseMode.HTML, reply_markup=master_menu()
    )


async def master_rating(update, context):
    r = await db_fetchrow("""
        SELECT rating,rating_count FROM masters WHERE telegram_id=$1
    """, update.effective_user.id)
    await update.message.reply_text(
        f"⭐ Reytingim: {r['rating'] if r else 0}/5\n📊 Baholar: {r['rating_count'] if r else 0}",
        reply_markup=master_menu()
    )


async def master_menu_router(update, context):
    t = update.message.text
    if t == "👨‍🔧 Usta bo‘lish":
        await master_apply(update, context)
    elif t == "📝 Yangi buyurtmalar":
        await master_new_orders(update, context)
    elif t == "📋 Mening buyurtmalarim":
        await master_orders(update, context)
    elif t == "👤 Mijozlarim":
        await master_customers(update, context)
    elif t == "📊 Mening statistikam":
        await master_stats(update, context)
    elif t == "💰 Kunlik daromad":
        await master_daily_income(update, context)
    elif t == "⭐ Reytingim":
        await master_rating(update, context)
    elif t == "👤 Profil":
        await master_check(update, context)
    elif t == "⚙️ Sozlamalar":
        await update.message.reply_text("⚙️ Usta sozlamalari", reply_markup=master_menu())


# ---------------- CALLBACKS ----------------

async def callback_router(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = update.effective_user.id

    try:
        if data.startswith("rate:"):
            _, oid_s, score_s = data.split(":")
            oid = int(oid_s)
            score = int(score_s)
            if score not in (1,2,3,4,5):
                await q.answer("Noto‘g‘ri baho", show_alert=True)
                return
            r = await db_fetchrow(
                "SELECT id,master_id,status FROM orders WHERE id=$1 AND customer_id=$2",
                oid, uid
            )
            if not r or r["status"] != STATUS_COMPLETED or not r["master_id"]:
                await q.answer("Buyurtma topilmadi", show_alert=True)
                return
            await db_exec(
                """
                INSERT INTO ratings(order_id,customer_id,master_id,customer_rating)
                VALUES($1,$2,$3,$4)
                ON CONFLICT(order_id) DO UPDATE
                SET customer_rating=EXCLUDED.customer_rating
                """,
                oid, uid, r["master_id"], score
            )
            avg = await db_fetchrow(
                """
                SELECT COALESCE(AVG(customer_rating),0) avg_rating,
                       COUNT(*) cnt
                FROM ratings
                WHERE master_id=$1 AND customer_rating IS NOT NULL
                """,
                r["master_id"]
            )
            await db_exec(
                "UPDATE masters SET rating=$1,rating_count=$2 WHERE telegram_id=$3",
                round(float(avg["avg_rating"] or 0), 2),
                int(avg["cnt"] or 0),
                r["master_id"]
            )
            await q.edit_message_text(
                f"⭐ Раҳмат! #{oid} учун {score}/5 baho saqlandi."
            )
            return

        if data.startswith("admin_approve:"):
            if uid != ADMIN_ID:
                await q.answer("Faqat admin", show_alert=True)
                return
            mid = int(data.split(":")[1])
            await db_exec(
                "UPDATE masters SET approved=TRUE,active=TRUE WHERE telegram_id=$1",
                mid
            )
            await db_exec(
                "UPDATE users SET role='master' WHERE id=$1",
                mid
            )
            await q.edit_message_reply_markup(reply_markup=None)
            try:
                await context.bot.send_message(
                    mid,
                    "✅ Usta so‘rovingiz tasdiqlandi! /start ni bosing."
                )
            except Exception:
                pass
            return

        if data.startswith("take:"):
            oid = int(data.split(":")[1])
            m = await db_fetchrow("SELECT * FROM masters WHERE telegram_id=$1 AND approved=TRUE AND active=TRUE", uid)
            if not m:
                await q.answer("Usta tasdiqlanmagan", show_alert=True)
                return
            r = await db_fetchrow("SELECT * FROM orders WHERE id=$1", oid)
            if not r or r["status"] != "new":
                await q.answer("Buyurtma allaqachon olingan", show_alert=True)
                return
            await db_exec("""
                UPDATE orders SET status='accepted',master_id=$1,master_name=$2,accepted_at=NOW()
                WHERE id=$3 AND status='new'
            """, uid, m["full_name"], oid)
            await log_status(oid, "new", "accepted", uid)
            await context.bot.send_message(
                r["customer_id"],
                f"✅ Buyurtma #{oid} qabul qilindi.\n👨‍🔧 Usta: {m['full_name']}"
            )
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"✅ Usta {m['full_name']} #{oid} buyurtmani qabul qildi.")
        elif data.startswith("reject:"):
            oid = int(data.split(":")[1])
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"❌ #{oid} buyurtma rad etildi.")
        elif data.startswith("start:"):
            oid = int(data.split(":")[1])
            r = await db_fetchrow("SELECT * FROM orders WHERE id=$1 AND master_id=$2", oid, uid)
            if not r:
                return
            await db_exec("UPDATE orders SET status='started',started_at=NOW() WHERE id=$1", oid)
            await log_status(oid, "accepted", "started", uid)
            await context.bot.send_message(r["customer_id"], f"🔧 Buyurtma #{oid}: ish boshlandi.")
            await q.edit_message_text(f"🔧 #{oid} — ish boshlandi.")
        elif data.startswith("done:"):
            oid = int(data.split(":")[1])
            r = await db_fetchrow("SELECT * FROM orders WHERE id=$1 AND master_id=$2", oid, uid)
            if not r:
                return
            await db_exec("UPDATE orders SET status='completed',completed_at=NOW() WHERE id=$1", oid)
            await log_status(oid, "started", "completed", uid)
            await context.bot.send_message(
                r["customer_id"],
                f"🏁 Buyurtma #{oid} tugallandi.\n⭐ Ustaga baho berishingiz mumkin."
            )
            await q.edit_message_text(f"🏁 #{oid} — ish tugallandi.")
        elif data.startswith("ccancel:"):
            oid = int(data.split(":")[1])
            r = await db_fetchrow("SELECT * FROM orders WHERE id=$1 AND customer_id=$2", oid, uid)
            if not r:
                return
            await db_exec("""
                UPDATE orders SET status='cancelled',cancelled_at=NOW()
                WHERE id=$1 AND customer_id=$2
            """, oid, uid)
            await log_status(oid, r["status"], "cancelled", uid)
            await q.edit_message_text(f"❌ #{oid} bekor qilindi.")
        elif data.startswith("admin_approve:"):
            if uid != ADMIN_ID:
                return
            mid = int(data.split(":")[1])
            await db_exec("UPDATE masters SET approved=TRUE,active=TRUE WHERE telegram_id=$1", mid)
            await context.bot.send_message(mid, "🎉 Sizning usta so‘rovingiz tasdiqlandi!")
            await q.edit_message_text(f"✅ Usta #{mid} tasdiqlandi.")
    except Exception:
        log.exception("callback error")
        await q.message.reply_text("❌ Amalni bajarishda xatolik yuz berdi.")


# ---------------- ADMIN ----------------

async def admin_masters(update, context):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Usta so‘rovlari", callback_data="admin_requests")],
        [InlineKeyboardButton("👨‍🔧 Tasdiqlangan ustalar", callback_data="admin_masters")],
    ])
    await update.message.reply_text("👨‍🔧 <b>USTALAR</b>", parse_mode=ParseMode.HTML, reply_markup=kb)


async def admin_orders(update, context):
    rows = await db_fetch("""
        SELECT id,customer_name,phone,service,status,master_name,created_at
        FROM orders ORDER BY id DESC LIMIT 50
    """)
    if not rows:
        await update.message.reply_text("📦 Hozircha buyurtmalar yo‘q.", reply_markup=admin_menu())
        return
    text = "📦 <b>BUYURTMALAR</b>\n\n"
    for r in rows:
        text += f"#{r['id']} | {r['customer_name']} | {r['service']} | {r['status']} | {r['master_name'] or '-'}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_customers(update, context):
    rows = await db_fetch("""
        SELECT u.id,u.full_name,u.username,u.phone,COUNT(o.id) orders_count
        FROM users u LEFT JOIN orders o ON o.customer_id=u.id
        WHERE COALESCE(u.role,'customer')='customer'
        GROUP BY u.id,u.full_name,u.username,u.phone
        ORDER BY orders_count DESC LIMIT 100
    """)
    if not rows:
        await update.message.reply_text("👤 Mijozlar yo‘q.", reply_markup=admin_menu())
        return
    text = "👤 <b>MIJOZLAR</b>\n\n"
    for r in rows:
        text += f"• {r['full_name'] or '-'} | {r['phone'] or '-'} | {r['orders_count']} ta\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_stats(update, context):
    r = await db_fetchrow("""
        SELECT COUNT(*) total,
        COUNT(*) FILTER(WHERE status='new') new,
        COUNT(*) FILTER(WHERE status='accepted') accepted,
        COUNT(*) FILTER(WHERE status='started') started,
        COUNT(*) FILTER(WHERE status='completed') completed,
        COUNT(*) FILTER(WHERE status='cancelled') cancelled,
        COALESCE(SUM(price) FILTER(WHERE status='completed'),0) income
        FROM orders
    """)
    m = await db_fetchrow("SELECT COUNT(*) total, COUNT(*) FILTER(WHERE approved=TRUE) approved FROM masters")
    c = await db_fetchrow("SELECT COUNT(*) total FROM users WHERE COALESCE(role,'customer')='customer'")
    await update.message.reply_text(
        f"📊 <b>UMUMIY STATISTIKA</b>\n\n"
        f"📦 Buyurtmalar: {r['total']}\n🆕 Yangi: {r['new']}\n"
        f"✅ Qabul: {r['accepted']}\n🔧 Jarayonda: {r['started']}\n"
        f"🏁 Tugallangan: {r['completed']}\n❌ Bekor: {r['cancelled']}\n"
        f"💰 Daromad: {r['income']}\n\n"
        f"👨‍🔧 Ustalar: {m['total']} | Tasdiqlangan: {m['approved']}\n"
        f"👤 Mijozlar: {c['total']}",
        parse_mode=ParseMode.HTML, reply_markup=admin_menu()
    )


async def admin_requests(update, context):
    rows = await db_fetch("""
        SELECT telegram_id,full_name,username,phone,services,created_at
        FROM masters WHERE approved=FALSE ORDER BY created_at DESC
    """)
    if not rows:
        await update.message.reply_text("📨 Usta so‘rovlari yo‘q.", reply_markup=admin_menu())
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"admin_approve:{r['telegram_id']}")
        ]])
        await update.message.reply_text(
            f"📨 <b>USTA SO‘ROVI</b>\n\n"
            f"👤 {r['full_name']}\n🆔 {r['telegram_id']}\n"
            f"👤 @{r['username'] or '-'}\n📞 {r['phone'] or '-'}\n"
            f"🛠 {r['services'] or '-'}",
            parse_mode=ParseMode.HTML, reply_markup=kb
        )


async def admin_masters_list(update, context):
    rows = await db_fetch("""
        SELECT telegram_id,full_name,phone,services,rating,approved,active
        FROM masters ORDER BY approved DESC,full_name
    """)
    if not rows:
        await update.message.reply_text("👨‍🔧 Ustalar yo‘q.", reply_markup=admin_menu())
        return
    text = "👨‍🔧 <b>USTALAR</b>\n\n"
    for r in rows:
        text += f"• {r['full_name']} | {'✅' if r['approved'] else '⏳'} | ⭐ {r['rating']} | {'🟢' if r['active'] else '🔴'}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_report(update, context):
    rows = await db_fetch("""
        SELECT status,COUNT(*) cnt,COALESCE(SUM(price),0) sum
        FROM orders GROUP BY status ORDER BY status
    """)
    text = "📈 <b>HISOBOT</b>\n\n"
    for r in rows:
        text += f"• {r['status']}: {r['cnt']} ta | {r['sum']}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_prices(update, context):
    rows = await db_fetch("SELECT name,price,active FROM services ORDER BY id")
    text = "💰 <b>NARXLAR</b>\n\n"
    text += "\n".join(f"• {r['name']} — {r['price']} so‘m {'🟢' if r['active'] else '🔴'}" for r in rows)
    await update.message.reply_text(text or "Narxlar yo‘q.", parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_coupons(update, context):
    rows = await db_fetch("SELECT code,discount_percent,active,usage_count FROM coupons ORDER BY id DESC")
    text = "🎟 <b>KUPONLAR</b>\n\n"
    text += "\n".join(f"• {r['code']} — {r['discount_percent']}% — {r['usage_count']} marta" for r in rows)
    await update.message.reply_text(text or "Kuponlar yo‘q.", parse_mode=ParseMode.HTML, reply_markup=admin_menu())


async def admin_messages(update, context):
    await update.message.reply_text(
        "📢 Xabarlar bo‘limi\n\nTarqatma xabar yuborish uchun /broadcast matn",
        reply_markup=admin_menu()
    )


async def broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    msg = " ".join(context.args).strip()
    if not msg:
        await update.message.reply_text("Foydalanish: /broadcast Xabar matni")
        return
    rows = await db_fetch("SELECT id FROM users WHERE notifications=TRUE")
    ok = 0
    for r in rows:
        try:
            await context.bot.send_message(r["id"], msg)
            ok += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Yuborildi: {ok}/{len(rows)}")


async def admin_settings(update, context):
    await update.message.reply_text(
        f"⚙️ <b>SOZLAMALAR</b>\n\n"
        f"👑 Admin ID: {ADMIN_ID}\n"
        f"👨‍🔧 Masters Group ID: {MASTERS_GROUP_ID}\n"
        f"🗄 PostgreSQL: {'🟢 Ulangan' if db_pool else '🔴 Ulanmagan'}",
        parse_mode=ParseMode.HTML, reply_markup=admin_menu()
    )


async def admin_callback(update, context):
    q = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await q.answer("Faqat admin", show_alert=True)
        return
    await q.answer()
    if q.data == "admin_requests":
        rows = await db_fetch("SELECT telegram_id,full_name,username,phone,services FROM masters WHERE approved=FALSE ORDER BY created_at DESC")
        if not rows:
            await q.edit_message_text("📨 Usta so‘rovlari yo‘q.")
            return
        for r in rows:
            await q.message.reply_text(
                f"📨 {r['full_name']} | {r['phone'] or '-'} | @{r['username'] or '-'}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"admin_approve:{r['telegram_id']}")
                ]])
            )
        await q.edit_message_text("📨 Usta so‘rovlari")
    elif q.data == "admin_masters":
        rows = await db_fetch("SELECT full_name,rating,approved,active FROM masters ORDER BY full_name")
        await q.edit_message_text(
            "👨‍🔧 <b>USTALAR</b>\n\n" + (
                "\n".join(f"• {r['full_name']} | ⭐ {r['rating']} | {'✅' if r['approved'] else '⏳'}" for r in rows)
                if rows else "Ustalar yo‘q."
            ), parse_mode=ParseMode.HTML
        )


async def health(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        r = await db_fetchrow("SELECT NOW() now")
        await update.message.reply_text(f"🟢 PostgreSQL ishlayapti.\n🕒 {r['now']}")
    except Exception as e:
        await update.message.reply_text(f"🔴 PostgreSQL xato:\n{type(e).__name__}: {e}")


# ---------------- ROUTER ----------------

async def message_router(update, context):
    if not update.message or not update.message.text:
        return

    t = update.message.text
    uid = update.effective_user.id

    # Process pending client inputs before treating the message as a menu button.
    if (
        context.user_data.get("await_order_status")
        or context.user_data.get("reorder")
        or context.user_data.get("await_review")
    ):
        await customer_text_router(update, context)
        return

    if uid == ADMIN_ID:
        mapping = {
            "👨‍🔧 Ustalar": admin_masters,
            "📦 Buyurtmalar": admin_orders,
            "👤 Mijozlar": admin_customers,
            "📊 Statistika": admin_stats,
            "📈 Hisobot": admin_report,
            "💰 Narxlar": admin_prices,
            "📢 Xabarlar": admin_messages,
            "🎟 Kuponlar": admin_coupons,
            "⚙️ Sozlamalar": admin_settings,
        }
        if t in mapping:
            await mapping[t](update, context)
            return

    m = await db_fetchrow(
        "SELECT * FROM masters WHERE telegram_id=$1 AND approved=TRUE AND active=TRUE",
        uid
    )
    if m and t in {
        "📝 Yangi buyurtmalar", "📋 Mening buyurtmalarim",
        "👤 Mijozlarim", "📊 Mening statistikam",
        "💰 Kunlik daromad", "⭐ Reytingim", "👤 Profil",
        "⚙️ Sozlamalar"
    }:
        await master_menu_router(update, context)
        return

    await customer_menu(update, context)


async def error_handler(update, context):
    log.exception("Unhandled error", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ Техник хато юз берди. Илтимос қайта уриниб кўринг.")
    except Exception:
        pass


# ---------------- REMINDERS ----------------

async def reminder_worker(app):
    while True:
        try:
            if db_pool:
                async with db_pool.acquire() as c:
                    rows = await c.fetch("""
                        SELECT r.id,r.order_id,r.user_id,r.kind,o.customer_name,o.status
                        FROM reminders r
                        LEFT JOIN orders o ON o.id=r.order_id
                        WHERE COALESCE(r.sent,FALSE)=FALSE
                          AND r.due_at IS NOT NULL
                          AND r.due_at <= NOW()
                        LIMIT 50
                    """)
                    for r in rows:
                        try:
                            await app.bot.send_message(
                                r["user_id"],
                                f"🔔 Eslatma: #{r['order_id']} buyurtma holati — {r['status'] or '-'}"
                            )
                        except Exception:
                            pass
                        await c.execute("UPDATE reminders SET sent=TRUE WHERE id=$1", r["id"])
        except Exception:
            log.exception("Reminder worker error")
        await asyncio.sleep(60)


async def post_init(app):
    await db_init()
    app.create_task(reminder_worker(app))


# ---------------- MAIN ----------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing")

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("health", health))
    application.add_handler(CommandHandler("broadcast", broadcast))

    application.add_handler(order_conv)

    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^(take|reject|start|done|ccancel|rate|admin_approve):"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_(requests|masters)$"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_router))
    application.add_error_handler(error_handler)

    log.info("USTA 24 ANDIJON bot started")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
