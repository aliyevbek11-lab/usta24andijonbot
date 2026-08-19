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
