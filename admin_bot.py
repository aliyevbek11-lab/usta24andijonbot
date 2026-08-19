import os
import logging
import asyncio

import asyncpg

from telegram import (
    Update,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")


if not BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")


try:
    ADMIN_ID = int(ADMIN_ID.strip())
except ValueError:
    raise RuntimeError("ADMIN_ID raqam bo‘lishi kerak!")


# =========================================================
# LOG
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("USTA24_ADMIN")


# =========================================================
# DATABASE
# =========================================================

db_pool = None


async def init_database():
    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=5,
    )

    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS masters (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT,
                username TEXT,
                phone TEXT,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dispatchers (
                telegram_id BIGINT PRIMARY KEY,
                name TEXT,
                username TEXT,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

    logger.info("PostgreSQL ulandi.")


# =========================================================
# SECURITY
# =========================================================

def is_admin(update: Update) -> bool:

    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID


async def access_denied(update: Update):

    if update.message:

        await update.message.reply_text(
            "⛔ Кириш тақиқланган.\n\n"
            "Бу бот фақат USTA 24 администратори учун."
        )


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():

    keyboard = [
        ["📊 Статистика"],
        ["📋 Барча буюртмалар"],
        ["🆕 Янги буюртмалар"],
        ["🟡 Қабул қилинган"],
        ["🔵 Иш жараёнида"],
        ["✅ Якунланган"],
        ["❌ Бекор қилинган"],
        ["🚫 Рад этилган"],
        ["👨‍🔧 Усталар"],
        ["📞 Диспетчерлар"],
        ["🔎 Буюртма қидириш"],
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):

        await access_denied(update)
        return

    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"

        "Хуш келибсиз, админ.\n\n"

        "Керакли бўлимни танланг:",

        reply_markup=admin_menu(),
    )


# =========================================================
# STATISTICS
# =========================================================

async def statistics(update: Update):

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM orders
            GROUP BY status
            """
        )

    stats = {
        "open": 0,
        "accepted": 0,
        "in_progress": 0,
        "completed": 0,
        "cancelled": 0,
        "rejected": 0,
    }

    total = 0

    for row in rows:

        status = row["status"]
        count = int(row["count"])

        if status in stats:
            stats[status] = count

        total += count

    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n\n"

        f"🆕 Янги: {stats['open']}\n"

        f"🟡 Қабул қилинган: {stats['accepted']}\n"

        f"🔵 Иш жараёнида: {stats['in_progress']}\n"

        f"✅ Якунланган: {stats['completed']}\n"

        f"❌ Бекор қилинган: {stats['cancelled']}\n"

        f"🚫 Рад этилган: {stats['rejected']}",

        reply_markup=admin_menu(),
    )


# =========================================================
# ORDERS
# =========================================================

async def show_orders(
    update: Update,
    status=None,
):

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

    title = "📋 БАРЧА БУЮРТМАЛАР"

    if status == "open":
        title = "🆕 ЯНГИ БУЮРТМАЛАР"

    elif status == "accepted":
        title = "🟡 ҚАБУЛ ҚИЛИНГАН"

    elif status == "in_progress":
        title = "🔵 ИШ ЖАРАЁНИДА"

    elif status == "completed":
        title = "✅ ЯКУНЛАНГАН"

    elif status == "cancelled":
        title = "❌ БЕКОР ҚИЛИНГАН"

    elif status == "rejected":
        title = "🚫 РАД ЭТИЛГАН"

    text = f"{title}\n\n"

    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['customer_name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🛠 {row['service'] or '-'}\n"
            f"📍 {row['address'] or '-'}\n"
            f"👨‍🔧 {row['master_name'] or '-'}\n"
            f"📌 {row['status']}\n"
            "──────────────\n"
        )

    # Telegram 4096 limit
    chunks = [
        text[i:i + 3900]
        for i in range(0, len(text), 3900)
    ]

    for chunk in chunks:

        await update.message.reply_text(
            chunk,
            reply_markup=admin_menu(),
        )


# =========================================================
# MASTERS
# =========================================================

async def show_masters(update: Update):

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM masters
            ORDER BY created_at DESC
            """
        )

    if not rows:

        await update.message.reply_text(
            "👨‍🔧 Ҳозирча усталар рўйхати бўш.",
            reply_markup=admin_menu(),
        )
        return

    text = "👨‍🔧 УСТАЛАР\n\n"

    for row in rows:

        active = "🟢 Фаол" if row["active"] else "🔴 Нофаол"

        text += (
            f"👤 {row['name'] or '-'}\n"
            f"🆔 ID: {row['telegram_id']}\n"
            f"📱 {row['phone'] or '-'}\n"
            f"🔗 {row['username'] or '-'}\n"
            f"{active}\n"
            "──────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# DISPATCHERS
# =========================================================

async def show_dispatchers(update: Update):

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM dispatchers
            ORDER BY created_at DESC
            """
        )

    if not rows:

        await update.message.reply_text(
            "📞 Ҳозирча диспетчерлар рўйхати бўш.",
            reply_markup=admin_menu(),
        )
        return

    text = "📞 ДИСПЕТЧЕРЛАР\n\n"

    for row in rows:

        active = "🟢 Фаол" if row["active"] else "🔴 Нофаол"

        text += (
            f"👤 {row['name'] or '-'}\n"
            f"🆔 ID: {row['telegram_id']}\n"
            f"🔗 {row['username'] or '-'}\n"
            f"{active}\n"
            "──────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# SEARCH MODE
# =========================================================

search_users = set()


async def search_order(update: Update):

    search_users.add(update.effective_user.id)

    await update.message.reply_text(
        "🔎 Буюртма қидириш\n\n"
        "Буюртма рақамини ёзинг.\n\n"
        "Масалан:\n"
        "25"
    )


# =========================================================
# SEARCH RESULT
# =========================================================

async def search_order_by_id(
    update: Update,
    order_id: int,
):

    async with db_pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT *
            FROM orders
            WHERE id = $1
            """,
            order_id,
        )

    if not row:

        await update.message.reply_text(
            "❌ Бундай буюртма топилмади.",
            reply_markup=admin_menu(),
        )
        return

    text = (

        f"🔎 БУЮРТМА #{row['id']}\n\n"

        f"👤 Мижоз: {row['customer_name'] or '-'}\n"

        f"📞 Телефон: {row['phone'] or '-'}\n"

        f"🛠 Хизмат: {row['service'] or '-'}\n"

        f"📍 Манзил: {row['address'] or '-'}\n"

        f"📝 Изоҳ: {row['description'] or '-'}\n"

        f"👨‍🔧 Уста: {row['master_name'] or '-'}\n"

        f"📌 Ҳолат: {row['status']}\n"

        f"👤 Telegram: {row['username'] or '-'}\n"

        f"🆔 User ID: {row['customer_id']}"
    )

    await update.message.reply_text(
        text,
        reply_markup=admin_menu(),
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):

        await access_denied(update)
        return

    text = (update.message.text or "").strip()

    # SEARCH
    if update.effective_user.id in search_users:

        try:

            order_id = int(text)

            search_users.discard(
                update.effective_user.id
            )

            await search_order_by_id(
                update,
                order_id,
            )

        except ValueError:

            await update.message.reply_text(
                "❌ Фақат буюртма рақамини ёзинг.\n\n"
                "Масалан: 25"
            )

        return

    # MENU

    if text == "📊 Статистика":

        await statistics(update)
        return

    if text == "📋 Барча буюртмалар":

        await show_orders(update)
        return

    if text == "🆕 Янги буюртмалар":

        await show_orders(update, "open")
        return

    if text == "🟡 Қабул қилинган":

        await show_orders(update, "accepted")
        return

    if text == "🔵 Иш жараёнида":

        await show_orders(update, "in_progress")
        return

    if text == "✅ Якунланган":

        await show_orders(update, "completed")
        return

    if text == "❌ Бекор қилинган":

        await show_orders(update, "cancelled")
        return

    if text == "🚫 Рад этилган":

        await show_orders(update, "rejected")
        return

    if text == "👨‍🔧 Усталар":

        await show_masters(update)
        return

    if text == "📞 Диспетчерлар":

        await show_dispatchers(update)
        return

    if text == "🔎 Буюртма қидириш":

        await search_order(update)
        return

    await update.message.reply_text(
        "👑 USTA 24 Admin Panel\n\n"
        "Менюдан керакли бўлимни танланг.",
        reply_markup=admin_menu(),
    )


# =========================================================
# ERROR
# =========================================================

async def error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "ADMIN BOT ERROR",
        exc_info=context.error,
    )


# =========================================================
# MAIN
# =========================================================

async def run():

    global db_pool

    await init_database()

    # Admin'ni DB ga qo‘shish
    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO admins (
                telegram_id,
                name
            )
            VALUES ($1, $2)
            ON CONFLICT (telegram_id)
            DO NOTHING
            """,
            ADMIN_ID,
            "USTA 24 Admin",
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start,
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

    await application.initialize()

    await application.start()

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

    logger.info(
        "👑 USTA 24 ADMIN BOT ISHLADI."
    )

    
        while True:

            await asyncio.sleep(3600)

    finally:

        await application.updater.stop()
        await application.stop()
        await application.shutdown()

        if db_pool:
            await db_pool.close()


if __name__ == "__main__":

    asyncio.run(run())
