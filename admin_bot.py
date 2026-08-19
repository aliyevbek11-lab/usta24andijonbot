print("===== ADMIN_BOT.PY LOADED =====")

import asyncio
import logging
import os

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from database import connect_db, pool


# ==============================
# SETTINGS
# ==============================

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")


if not BOT_TOKEN:
    raise RuntimeError(
        "ADMIN_BOT_TOKEN topilmadi!"
    )


if not ADMIN_ID:
    raise RuntimeError(
        "ADMIN_ID topilmadi!"
    )


ADMIN_ID = int(ADMIN_ID)



# ==============================
# LOG
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "USTA24_ADMIN"
)



# ==============================
# ACCESS
# ==============================

async def is_allowed(
    user_id
):

    if user_id == ADMIN_ID:
        return True


    async with pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT telegram_id
            FROM dispatchers
            WHERE telegram_id=$1
            AND active=true
            """,
            user_id
        )


    return row is not None



# ==============================
# MENU
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

        ["📞 Диспетчерлар"]

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

    user = update.effective_user


    if not await is_allowed(
        user.id
    ):

        await update.message.reply_text(
            "⛔ Кириш мумкин эмас."
        )

        return



    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Керакли бўлимни танланг:",

        reply_markup=admin_menu()

    )# ==============================
# ORDERS
# ==============================

async def show_orders(
    update: Update,
    status=None
):

    async with pool.acquire() as conn:

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
            "📭 Буюртмалар йўқ.",
            reply_markup=admin_menu()
        )

        return


    text = "📋 БУЮРТМАЛАР\n\n"


    for row in rows:

        text += (
            f"🔢 #{row['id']}\n"
            f"👤 {row['customer_name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🛠 {row['service'] or '-'}\n"
            f"📍 {row['address'] or '-'}\n"
            f"📝 {row['description'] or '-'}\n"
            f"📌 {row['status']}\n"
            "────────────\n"
        )


    await update.message.reply_text(
        text[:4000],
        reply_markup=admin_menu()
    )



# ==============================
# STATISTICS
# ==============================

async def statistics(
    update: Update
):

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT status, COUNT(*)
            FROM orders
            GROUP BY status
            """
        )


    result = {
        "open":0,
        "accepted":0,
        "in_progress":0,
        "completed":0,
        "cancelled":0
    }


    total = 0


    for row in rows:

        status = row["status"]
        count = row["count"]

        total += count

        if status in result:
            result[status] = count



    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n\n"

        f"🆕 Янги: {result['open']}\n"
        f"🟡 Қабул қилинган: {result['accepted']}\n"
        f"🔵 Иш жараёнида: {result['in_progress']}\n"
        f"✅ Якунланган: {result['completed']}\n"
        f"❌ Бекор қилинган: {result['cancelled']}",

        reply_markup=admin_menu()

    )



# ==============================
# MASTERS
# ==============================

async def show_masters(
    update: Update
):

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM masters
            ORDER BY id DESC
            """
        )


    text = "👨‍🔧 УСТАЛАР\n\n"


    for row in rows:

        text += (
            f"👤 {row['name'] or '-'}\n"
            f"📞 {row['phone'] or '-'}\n"
            f"🔗 {row['username'] or '-'}\n"
            f"🆔 {row['telegram_id']}\n"
            "────────────\n"
        )


    await update.message.reply_text(
        text,
        reply_markup=admin_menu()
    )# ==============================
# DISPATCHERS
# ==============================

async def show_dispatchers(
    update: Update
):

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT *
            FROM dispatchers
            ORDER BY id DESC
            """
        )


    text = "📞 ДИСПЕТЧЕРЛАР\n\n"


    for row in rows:

        text += (
            f"👤 {row['name'] or '-'}\n"
            f"🔗 {row['username'] or '-'}\n"
            f"🆔 {row['telegram_id']}\n"
            "────────────\n"
        )


    await update.message.reply_text(
        text,
        reply_markup=admin_menu()
    )



# ==============================
# MESSAGE HANDLER
# ==============================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user


    if not await is_allowed(
        user.id
    ):

        await update.message.reply_text(
            "⛔ Кириш мумкин эмас."
        )

        return


    text = update.message.text



    if text == "📊 Статистика":

        await statistics(update)
        return



    if text == "📋 Барча буюртмалар":

        await show_orders(update)
        return



    if text == "🆕 Янги буюртмалар":

        await show_orders(
            update,
            "open"
        )

        return



    if text == "🟡 Қабул қилинган":

        await show_orders(
            update,
            "accepted"
        )

        return



    if text == "🔵 Иш жараёнида":

        await show_orders(
            update,
            "in_progress"
        )

        return



    if text == "✅ Якунланган":

        await show_orders(
            update,
            "completed"
        )

        return



    if text == "❌ Бекор қилинган":

        await show_orders(
            update,
            "cancelled"
        )

        return



    if text == "👨‍🔧 Усталар":

        await show_masters(update)
        return



    if text == "📞 Диспетчерлар":

        await show_dispatchers(update)
        return



    await update.message.reply_text(
        "Менюдан танланг.",
        reply_markup=admin_menu()
    )



# ==============================
# ERROR
# ==============================

async def error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "ERROR:",
        exc_info=context.error
    )



# ==============================
# RUN
# ==============================

async def run():

    await connect_db()


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


    print(
        "🚀 USTA 24 ADMIN BOT START"
    )


    await app.run_polling(
        drop_pending_updates=True
    )



if __name__ == "__main__":

    asyncio.run(run())
