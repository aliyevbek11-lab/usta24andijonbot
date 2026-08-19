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

import database


# ==========================================
# SETTINGS
# ==========================================

BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")


if not BOT_TOKEN:
    raise RuntimeError("ADMIN_BOT_TOKEN topilmadi!")


if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi!")


try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise RuntimeError("ADMIN_ID raqam bo'lishi kerak!")


# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("USTA24_ADMIN")


# ==========================================
# ACCESS
# ==========================================

async def is_allowed(user_id: int) -> bool:

    if user_id == ADMIN_ID:
        return True

    try:

        async with database.pool.acquire() as conn:

            row = await conn.fetchrow(
                """
                SELECT telegram_id
                FROM dispatchers
                WHERE telegram_id = $1
                AND active = TRUE
                """,
                user_id
            )

        return row is not None

    except Exception:

        logger.exception("ACCESS CHECK ERROR")

        return False


# ==========================================
# MENU
# ==========================================

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

    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )


# ==========================================
# DENIED
# ==========================================

async def denied(update: Update):

    if update.message:

        await update.message.reply_text(
            "⛔ Кириш тақиқланган.\n\n"
            "Бу бот фақат USTA 24 админи "
            "ва фаол диспетчерлар учун."
        )


# ==========================================
# START
# ==========================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:

        return

    allowed = await is_allowed(
        update.effective_user.id
    )

    if not allowed:

        await denied(update)

        return

    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Керакли бўлимни танланг:",

        reply_markup=admin_menu()
    )


# ==========================================
# STATISTICS
# ==========================================

async def statistics(
    update: Update
):

    try:

        async with database.pool.acquire() as conn:

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

        text = (

            "📊 USTA 24 СТАТИСТИКА\n\n"

            f"📋 Жами: {total}\n\n"

            f"🆕 Янги: {data['open']}\n"

            f"🟡 Қабул қилинган: "
            f"{data['accepted']}\n"

            f"🔵 Иш жараёнида: "
            f"{data['in_progress']}\n"

            f"✅ Якунланган: "
            f"{data['completed']}\n"

            f"❌ Бекор қилинган: "
            f"{data['cancelled']}"
        )

        await update.message.reply_text(
            text,
            reply_markup=admin_menu()
        )

    except Exception:

        logger.exception("STATISTICS ERROR")

        await update.message.reply_text(
            "❌ Статистикани олишда хатолик.",
            reply_markup=admin_menu()
        )


# ==========================================
# SHOW ORDERS
# ==========================================

async def show_orders(
    update: Update,
    status=None
):

    try:

        async with database.pool.acquire() as conn:

            if status:

                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM orders
                    WHERE status = $1
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

        for row in rows:

            text = (

                f"🔢 Буюртма #{row['id']}\n\n"

                f"👤 Мижоз: "
                f"{row['customer_name'] or '-'}\n"

                f"📞 Телефон: "
                f"{row['phone'] or '-'}\n"

                f"🛠 Хизмат: "
                f"{row['service'] or '-'}\n"

                f"📍 Манзил: "
                f"{row['address'] or '-'}\n"

                f"📝 Изоҳ: "
                f"{row['description'] or '-'}\n"

                f"👨‍🔧 Уста: "
                f"{row['master_name'] or '-'}\n"

                f"📌 Ҳолат: "
                f"{row['status'] or '-'}\n"

                "────────────"
            )

            await update.message.reply_text(
                text
            )

        await update.message.reply_text(
            "👑 Меню:",
            reply_markup=admin_menu()
        )

    except Exception:

        logger.exception("SHOW ORDERS ERROR")

        await update.message.reply_text(
            "❌ Буюртмаларни олишда хатолик.",
            reply_markup=admin_menu()
        )


# ==========================================
# SHOW MASTERS
# ==========================================

async def show_masters(
    update: Update
):

    try:

        async with database.pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT *
                FROM masters
                ORDER BY id DESC
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

            active = "🟢 Фаол" if row["active"] else "🔴 Нофаол"

            text += (

                f"{active}\n"

                f"👤 Исм: "
                f"{row['name'] or '-'}\n"

                f"🆔 Telegram ID: "
                f"{row['telegram_id']}\n"

                f"📞 Телефон: "
                f"{row['phone'] or '-'}\n"

                f"🔗 Username: "
                f"{row['username'] or '-'}\n"

                "────────────\n"
            )

        await update.message.reply_text(
            text[:4000],
            reply_markup=admin_menu()
        )

    except Exception:

        logger.exception("MASTERS ERROR")

        await update.message.reply_text(
            "❌ Усталарни олишда хатолик.",
            reply_markup=admin_menu()
        )


# ==========================================
# SHOW DISPATCHERS
# ==========================================

async def show_dispatchers(
    update: Update
):

    try:

        async with database.pool.acquire() as conn:

            rows = await conn.fetch(
                """
                SELECT *
                FROM dispatchers
                ORDER BY id DESC
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

            active = "🟢 Фаол" if row["active"] else "🔴 Нофаол"

            text += (

                f"{active}\n"

                f"👤 Исм: "
                f"{row['name'] or '-'}\n"

                f"🆔 Telegram ID: "
                f"{row['telegram_id']}\n"

                f"🔗 Username: "
                f"{row['username'] or '-'}\n"

                "────────────\n"
            )

        await update.message.reply_text(
            text[:4000],
            reply_markup=admin_menu()
        )

    except Exception:

        logger.exception("DISPATCHERS ERROR")

        await update.message.reply_text(
            "❌ Диспетчерларни олишда хатолик.",
            reply_markup=admin_menu()
        )


# ==========================================
# MESSAGE HANDLER
# ==========================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:

        return

    allowed = await is_allowed(
        update.effective_user.id
    )

    if not allowed:

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

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Менюдан танланг:",

        reply_markup=admin_menu()
    )


# ==========================================
# ERROR HANDLER
# ==========================================

async def error_handler(
    update,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "BOT ERROR",
        exc_info=context.error
    )


# ==========================================
# MAIN
# ==========================================

async def main():

    print("===== ADMIN BOT STARTING =====")

    print("Connecting to database...")

    await database.connect_db()

    print("===== DATABASE CONNECTED =====")

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    application.add_error_handler(
        error_handler
    )

    print("===== ADMIN BOT IS READY =====")

    await application.initialize()

    await application.start()

    await application.updater.start_polling(
        drop_pending_updates=True
    )

    print("===== POLLING STARTED =====")

    try:

        while True:

            await asyncio.sleep(3600)

    except (KeyboardInterrupt, SystemExit):

        pass

    finally:

        if application.updater.running:

            await application.updater.stop()

        await application.stop()

        await application.shutdown()


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    asyncio.run(main())
