import os
import logging
import asyncio

import asyncpg

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ==============================
# SETTINGS
# ==============================

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
DATABASE_URL = os.getenv("DATABASE_URL")


if not BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN topilmadi!")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi!")


ADMIN_ID = int(ADMIN_ID)


# ==============================
# LOG
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("USTA24_ADMIN")


# ==============================
# DATABASE
# ==============================

db_pool = None


async def init_database():

    global db_pool

    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10
    )

    async with db_pool.acquire() as conn:

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            telegram_id BIGINT PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS dispatchers(
            telegram_id BIGINT PRIMARY KEY,
            name TEXT,
            username TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


        await conn.execute("""
        CREATE TABLE IF NOT EXISTS masters(
            telegram_id BIGINT PRIMARY KEY,
            name TEXT,
            username TEXT,
            phone TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)


    logger.info("DATABASE CONNECTED")


# ==============================
# SECURITY
# ==============================

def is_admin(update: Update):

    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID



async def denied(update):

    await update.message.reply_text(
        "⛔ Кириш мумкин эмас.\n"
        "Фақат USTA 24 админлари учун."
    )


# ==============================
# MENU
# ==============================

def admin_menu():

    buttons = [

        ["📊 Статистика"],

        ["📋 Барча буюртмалар"],

        ["🆕 Янги буюртмалар"],

        ["🟡 Қабул қилинган"],

        ["🔵 Иш жараёнида"],

        ["✅ Якунланган"],

        ["❌ Бекор қилинган"],

        ["👨‍🔧 Усталар"],

        ["📞 Диспетчерлар"],

        ["🔎 Қидириш"]

    ]


    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True
    )


# ==============================
# START
# ==============================

async def start(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):

        await denied(update)
        return


    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Керакли бўлимни танланг:",

        reply_markup=admin_menu()

    )
# ==============================
# SECURITY
# ==============================

def is_admin(update: Update):

    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID



async def denied(update: Update):

    if update.message:

        await update.message.reply_text(
            "⛔ Кириш тақиқланган.\n\n"
            "Бу бот фақат USTA 24 админи учун."
        )



# ==============================
# ADMIN MENU
# ==============================

def admin_menu():

    keyboard = [

        ["📊 Статистика"],

        ["📋 Барча буюртмалар"],

        ["🆕 Янги буюртмалар"],

        ["🟡 Қабул қилинган"],

        ["🔵 Иш жараёнида"],

        ["✅ Якунланган"],

        ["❌ Бекор қилинган"],

        ["👨‍🔧 Усталар"],

        ["📞 Диспетчерлар"],

        ["🔎 Буюртма қидириш"]

    ]


    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )



# ==============================
# START
# ==============================

async def start(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):

        await denied(update)
        return


    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Керакли бўлимни танланг:",

        reply_markup=admin_menu()

    )# ==============================
# STATISTICS
# ==============================

async def statistics(update: Update):

    async with db_pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS count
            FROM orders
            GROUP BY status
            """
        )


    data = {
        "open": 0,
        "accepted": 0,
        "in_progress": 0,
        "completed": 0,
        "cancelled": 0
    }


    total = 0


    for row in rows:

        status = row["status"]

        count = int(row["count"])

        total += count


        if status in data:

            data[status] = count



    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n\n"

        f"🆕 Янги: {data['open']}\n"

        f"🟡 Қабул қилинган: {data['accepted']}\n"

        f"🔵 Иш жараёнида: {data['in_progress']}\n"

        f"✅ Якунланган: {data['completed']}\n"

        f"❌ Бекор қилинган: {data['cancelled']}",

        reply_markup=admin_menu()

    )



# ==============================
# ORDERS
# ==============================


async def show_orders(
        update: Update,
        status=None
):


    async with db_pool.acquire() as conn:


        if status:


            rows = await conn.fetch(
                """
                SELECT *
                FROM orders
                WHERE status=$1
                ORDER BY id DESC
                LIMIT 50
                """,
                status
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
            reply_markup=admin_menu()
        )

        return



    text = "📋 БУЮРТМАЛАР\n\n"



    for row in rows:


        text += (

            f"🔢 #{row['id']}\n"

            f"👤 {row.get('customer_name','-')}\n"

            f"📞 {row.get('phone','-')}\n"

            f"🛠 {row.get('service','-')}\n"

            f"📍 {row.get('address','-')}\n"

            f"📌 {row.get('status','-')}\n"

            "────────────\n"

        )



    await update.message.reply_text(

        text[:4000],

        reply_markup=admin_menu()

)# ==============================
# MASTERS
# ==============================

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
            "👨‍🔧 Усталар топилмади.",
            reply_markup=admin_menu()
        )

        return



    text = "👨‍🔧 УСТАЛАР\n\n"



    for row in rows:

        status = "🟢" if row["active"] else "🔴"


        text += (

            f"{status} {row['name'] or '-'}\n"

            f"🆔 ID: {row['telegram_id']}\n"

            f"📞 {row['phone'] or '-'}\n"

            f"🔗 {row['username'] or '-'}\n"

            "────────────\n"

        )



    await update.message.reply_text(

        text[:4000],

        reply_markup=admin_menu()

    )



# ==============================
# DISPATCHERS
# ==============================


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

            "📞 Диспетчерлар топилмади.",

            reply_markup=admin_menu()

        )

        return



    text = "📞 ДИСПЕТЧЕРЛАР\n\n"



    for row in rows:


        status = "🟢" if row["active"] else "🔴"


        text += (

            f"{status} {row['name'] or '-'}\n"

            f"🆔 ID: {row['telegram_id']}\n"

            f"🔗 {row['username'] or '-'}\n"

            "────────────\n"

        )



    await update.message.reply_text(

        text[:4000],

        reply_markup=admin_menu()

    )# ==============================
# MESSAGE HANDLER
# ==============================

async def handle_message(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):


    if not is_admin(update):

        await denied(update)
        return



    text = update.message.text



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



    if text == "👨‍🔧 Усталар":

        await show_masters(update)
        return



    if text == "📞 Диспетчерлар":

        await show_dispatchers(update)
        return



    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Менюдан танланг:",

        reply_markup=admin_menu()

    )



# ==============================
# ERROR HANDLER
# ==============================


async def error_handler(
        update,
        context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "BOT ERROR",
        exc_info=context.error
    )# ==============================
# RUN BOT
# ==============================

async def run():

    global db_pool


    await init_database()


    async with db_pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO admins(
                telegram_id,
                name
            )
            VALUES($1,$2)
            ON CONFLICT(telegram_id)
            DO NOTHING
            """,
            ADMIN_ID,
            "USTA 24 Admin"
        )



    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )



    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )



    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )



    app.add_error_handler(
        error_handler
    )



    print("🚀 USTA 24 ADMIN BOT START")



    await app.initialize()

    await app.start()



    await app.updater.start_polling(
        drop_pending_updates=True
    )



    print("✅ USTA 24 ADMIN BOT ISHLADI")



    while True:

        await asyncio.sleep(3600)





if __name__ == "__main__":

    asyncio.run(run())
