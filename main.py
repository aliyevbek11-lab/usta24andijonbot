#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA24 DISPATCHER – МИНИМАЛ ВЕРСИЯ
Бот фақат /start дан кейин мижоз саҳифасини очиб беради
Усталар бот орқали рўйхатдан ўтади
"""

import os
import logging
from datetime import datetime

import asyncpg

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
MASTERS_GROUP_ID = int(os.getenv("MASTERS_GROUP_ID", "0") or 0)
DISPATCHER_PHONE = os.getenv("DISPATCHER_PHONE", "+9987706900003")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN topilmadi!")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL topilmadi!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("USTA24")

db_pool = None

# ============================================================
# DATABASE
# ============================================================

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                role TEXT DEFAULT 'client',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                full_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                services TEXT DEFAULT '',
                area TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                rating NUMERIC(3,2) DEFAULT 0,
                rating_count INT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL,
                client_name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                service TEXT DEFAULT '',
                address TEXT DEFAULT '',
                description TEXT DEFAULT '',
                order_time TEXT DEFAULT '',
                photo_file_ids TEXT DEFAULT '',
                result_photo_ids TEXT DEFAULT '',
                master_id BIGINT,
                master_name TEXT DEFAULT '',
                status TEXT DEFAULT 'new',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                accepted_at TIMESTAMPTZ,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id BIGSERIAL PRIMARY KEY,
                order_id BIGINT NOT NULL,
                client_id BIGINT NOT NULL,
                master_id BIGINT NOT NULL,
                rating INT CHECK (rating >= 1 AND rating <= 5),
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    logger.info("✅ Database ready")

# ---------- HELPERS ----------
async def db_user(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)

async def db_create_user(telegram_id, full_name):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (telegram_id, full_name) VALUES ($1, $2)
            ON CONFLICT (telegram_id) DO UPDATE SET full_name=$2
        """, telegram_id, full_name)

async def db_set_phone(telegram_id, phone):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET phone=$1 WHERE telegram_id=$2", phone, telegram_id)

async def db_update_role(telegram_id, role):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET role=$1 WHERE telegram_id=$2", role, telegram_id)

async def is_master(telegram_id):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM masters WHERE telegram_id=$1", telegram_id)
        return bool(row and row["status"] == "approved")

async def db_create_master(telegram_id, full_name, phone, services, area):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO masters (telegram_id, full_name, phone, services, area, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT (telegram_id) DO UPDATE SET full_name=$2, phone=$3, services=$4, area=$5, status='pending'
        """, telegram_id, full_name, phone, services, area)
        await db_set_phone(telegram_id, phone)

async def db_approve_master(telegram_id):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE masters SET status='approved' WHERE telegram_id=$1", telegram_id)
        await db_update_role(telegram_id, 'master')

async def db_get_master(telegram_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM masters WHERE telegram_id=$1", telegram_id)

async def db_get_master_by_id(master_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM masters WHERE id=$1", master_id)

# ---------- ORDERS ----------
async def db_create_order(client_id, client_name, phone, service, address, description, order_time, photo_file_ids):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            INSERT INTO orders (client_id, client_name, phone, service, address, description, order_time, photo_file_ids)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *
        """, client_id, client_name, phone, service, address, description, order_time, photo_file_ids)

async def db_get_order(order_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)

async def db_client_orders(client_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM orders WHERE client_id=$1 ORDER BY id DESC LIMIT 10", client_id)

async def db_master_orders(master_id):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM orders WHERE master_id=$1 ORDER BY id DESC LIMIT 10", master_id)

async def db_get_orders_by_status(status):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM orders WHERE status=$1 ORDER BY id DESC", status)

async def db_accept_order(order_id, master_id, master_name):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            UPDATE orders SET master_id=$2, master_name=$3, status='accepted', accepted_at=NOW()
            WHERE id=$1 AND status='new' RETURNING *
        """, order_id, master_id, master_name)

async def db_start_order(order_id, master_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            UPDATE orders SET status='in_progress', started_at=NOW()
            WHERE id=$1 AND master_id=$2 AND status='accepted' RETURNING *
        """, order_id, master_id)

async def db_complete_order(order_id, master_id, result_photo_ids):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            UPDATE orders SET status='completed', result_photo_ids=$3, completed_at=NOW()
            WHERE id=$1 AND master_id=$2 AND status='in_progress' RETURNING *
        """, order_id, master_id, result_photo_ids)

async def db_cancel_order(order_id, client_id):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            UPDATE orders SET status='cancelled' WHERE id=$1 AND client_id=$2 AND status IN ('new','accepted') RETURNING *
        """, order_id, client_id)

async def db_stats():
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status='new') AS new,
                   COUNT(*) FILTER (WHERE status='accepted') AS accepted,
                   COUNT(*) FILTER (WHERE status='in_progress') AS progress,
                   COUNT(*) FILTER (WHERE status='completed') AS completed
            FROM orders
        """)

# ============================================================
# KEYBOARDS
# ============================================================

# MIJOZ SAHIFASI – 7 TA TUGMA
def client_menu():
    return ReplyKeyboardMarkup([
        ["🛒 Buyurtma berish", "📋 Mening buyurtmalarim"],
        ["🔍 Buyurtma holati", "❌ Bekor qilish"],
        ["👨‍🔧 Usta bo'lish", "📞 Dispetcher"],
        ["🚨 24/7"],
    ], resize_keyboard=True)

# USTA MENYUSI – 7 TA TUGMA
def master_menu():
    return ReplyKeyboardMarkup([
        ["🆕 Yangi buyurtmalar", "📋 Mening buyurtmalarim"],
        ["✅ Qabul qilish", "🔧 Ishni boshlash"],
        ["✅ Ishni yakunlash", "📊 Statistika"],
        ["📞 Dispetcher"],
    ], resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["👨‍🔧 Ustalar", "📋 Barcha buyurtmalar"],
        ["📊 Statistika", "📞 Dispetcher"],
    ], resize_keyboard=True)

def service_keyboard():
    return ReplyKeyboardMarkup([
        ["🛠 Sanitariya", "⚡ Elektr"],
        ["🔧 Mexanik", "🧹 Tozalash"],
        ["📦 Yuk tashish", "🔨 Boshqa"],
        ["⬅️ Orqaga"]
    ], resize_keyboard=True)

def time_keyboard():
    return ReplyKeyboardMarkup([
        ["🔴 Hozir", "🟡 Bugun kechqurun"],
        ["🟢 Ertaga ertalab"],
        ["⬅️ Orqaga"]
    ], resize_keyboard=True)

def confirm_keyboard():
    return ReplyKeyboardMarkup([
        ["✅ BUYURTMA YUBORISH", "❌ Bekor qilish"]
    ], resize_keyboard=True)

def skip_keyboard():
    return ReplyKeyboardMarkup([
        ["⏭ O'tkazib yuborish"]
    ], resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup([
        ["⬅️ Orqaga"]
    ], resize_keyboard=True)

# ============================================================
# ORDER STATES
# ============================================================

SERVICE, SERVICE_SUB, ORDER_NAME, ORDER_PHONE, ORDER_ADDRESS, ORDER_DESCRIPTION, ORDER_TIME, ORDER_PHOTO, ORDER_CONFIRM = range(9)

# ============================================================
# START
# ============================================================

async def start(update, context):
    user = update.effective_user
    await db_create_user(user.id, user.full_name or "")

    if user.id == ADMIN_ID:
        await update.message.reply_text("👑 Admin paneli", reply_markup=admin_menu())
        return

    if await is_master(user.id):
        await update.message.reply_text("👨‍🔧 Usta paneli", reply_markup=master_menu())
        return

    await update.message.reply_text(
        "👋 <b>USTA24 DISPATCHER</b>\n\n"
        "Хуш келибсиз!\n"
        "Хизмат керак бўлса, буюртма беринг.",
        parse_mode="HTML",
        reply_markup=client_menu()
    )

# ============================================================
# ORDER CONVERSATION
# ============================================================

async def order_start(update, context):
    context.user_data['order'] = {'step': 'service', 'photos': []}
    await update.message.reply_text("🛒 Хизмат турини танланг:", reply_markup=service_keyboard())
    return SERVICE

async def order_service(update, context):
    text = update.message.text
    if text == "⬅️ Orqaga":
        await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
        return ConversationHandler.END

    context.user_data['order']['service'] = text
    await update.message.reply_text("👤 Исмингизни киритинг:", reply_markup=ReplyKeyboardRemove())
    return ORDER_NAME

async def order_name(update, context):
    context.user_data['order']['name'] = update.message.text
    await update.message.reply_text("📞 Телефон рақамингиз:", reply_markup=ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Telefon yuborish", request_contact=True)]], resize_keyboard=True
    ))
    return ORDER_PHONE

async def order_phone(update, context):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text
    context.user_data['order']['phone'] = phone
    await db_set_phone(update.effective_user.id, phone)
    await update.message.reply_text("📍 Манзилингиз:", reply_markup=ReplyKeyboardRemove())
    return ORDER_ADDRESS

async def order_address(update, context):
    context.user_data['order']['address'] = update.message.text
    await update.message.reply_text("📝 Муаммони ёзинг:", reply_markup=ReplyKeyboardRemove())
    return ORDER_DESCRIPTION

async def order_description(update, context):
    context.user_data['order']['description'] = update.message.text
    await update.message.reply_text("🕐 Қачон керак?", reply_markup=time_keyboard())
    return ORDER_TIME

async def order_time(update, context):
    if update.message.text == "⬅️ Orqaga":
        await update.message.reply_text("📝 Муаммони ёзинг:", reply_markup=ReplyKeyboardRemove())
        return ORDER_DESCRIPTION
    context.user_data['order']['time'] = update.message.text
    await update.message.reply_text("📸 Муаммо расми (ихтиёрий):", reply_markup=skip_keyboard())
    return ORDER_PHOTO

async def order_photo(update, context):
    if update.message.text == "⏭ O'tkazib yuborish":
        context.user_data['order']['photos'] = []
        return await order_confirm(update, context)

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['order']['photos'].append(file_id)
        await update.message.reply_text(f"✅ Расм қабул қилинди! ({len(context.user_data['order']['photos'])} та)\nЯна расм ёки '✅ BUYURTMA YUBORISH'", 
            reply_markup=ReplyKeyboardMarkup([["✅ BUYURTMA YUBORISH"], ["⏭ O'tkazib yuborish"]], resize_keyboard=True))
        return ORDER_PHOTO

    return await order_confirm(update, context)

async def order_confirm(update, context):
    data = context.user_data.get('order', {})
    text = f"📋 <b>БУЮРТМА</b>\n\n👤 {data.get('name')}\n📞 {data.get('phone')}\n🛠 {data.get('service')}\n📍 {data.get('address')}\n📝 {data.get('description')}\n🕐 {data.get('time')}\n📸 {len(data.get('photos', []))} та расм\n\n✅ Тасдиқлайсизми?"
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=confirm_keyboard())
    return ORDER_CONFIRM

async def order_submit(update, context):
    if update.message.text == "❌ Bekor qilish":
        await update.message.reply_text("❌ Бекор қилинди.", reply_markup=client_menu())
        return ConversationHandler.END

    data = context.user_data.get('order', {})
    user = update.effective_user

    order = await db_create_order(
        client_id=user.id,
        client_name=user.full_name or "",
        phone=data.get('phone', ''),
        service=data.get('service', ''),
        address=data.get('address', ''),
        description=data.get('description', ''),
        order_time=data.get('time', ''),
        photo_file_ids=",".join(data.get('photos', []))
    )

    order_id = order['id']

    await update.message.reply_text(f"✅ <b>Буюртма №{order_id} юборилди!</b>", parse_mode="HTML", reply_markup=client_menu())

    # Guruhga xabar
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Қабул қилиш", callback_data=f"accept_{order_id}"),
         InlineKeyboardButton("❌ Рад этиш", callback_data=f"reject_{order_id}")]
    ])

    text = f"🆕 <b>Янги буюртма!</b>\n🆔 №{order_id}\n👤 {order['client_name']}\n🛠 {order['service']}\n📍 {order['address']}"
    if MASTERS_GROUP_ID:
        await context.bot.send_message(MASTERS_GROUP_ID, text, parse_mode="HTML", reply_markup=keyboard)

        if order['photo_file_ids']:
            for fid in order['photo_file_ids'].split(','):
                try:
                    await context.bot.send_photo(MASTERS_GROUP_ID, fid.strip())
                except:
                    pass

    if ADMIN_ID:
        await context.bot.send_message(ADMIN_ID, f"🆕 Янги буюртма №{order_id}", parse_mode="HTML")

    context.user_data.pop('order', None)
    return ConversationHandler.END

# ============================================================
# CALLBACKS
# ============================================================

async def handle_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # Usta bo'lish – admin tasdiqlash
    if data.startswith("master_approve:"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Фақат админ!", show_alert=True)
            return
        master_id = int(data.split(":")[1])
        await db_approve_master(master_id)
        master = await db_get_master(master_id)
        await query.edit_message_text(f"✅ Уста тасдиқланди: {master['full_name']}")
        try:
            await context.bot.send_message(master_id, "🎉 Табриклаймиз! Уста сифатида тасдиқландингиз.\n/start", parse_mode="HTML", reply_markup=master_menu())
        except:
            pass
        return

    if data.startswith("master_reject:"):
        if user.id != ADMIN_ID:
            await query.answer("❌ Фақат админ!", show_alert=True)
            return
        master_id = int(data.split(":")[1])
        await query.edit_message_text("❌ Уста ради этилди.")
        return

    # Buyurtma – qabul / rad
    if data.startswith("accept_"):
        order_id = int(data.split("_")[1])
        if not await is_master(user.id):
            await query.answer("❌ Фақат уста!", show_alert=True)
            return

        master = await db_get_master(user.id)
        accepted = await db_accept_order(order_id, user.id, master['full_name'])
        if accepted:
            await query.edit_message_text(f"✅ №{order_id} қабул қилинди!", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔧 Бошлаш", callback_data=f"start_{order_id}")]
            ]))
            try:
                await context.bot.send_message(accepted['client_id'], f"✅ Буюртмангиз №{order_id} қабул қилинди!")
            except:
                pass
        return

    if data.startswith("reject_"):
        order_id = int(data.split("_")[1])
        await query.edit_message_text(f"❌ №{order_id} рад этилди.")
        # Qayta yuborish
        order = await db_get_order(order_id)
        if order and MASTERS_GROUP_ID:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Қабул қилиш", callback_data=f"accept_{order_id}"),
                 InlineKeyboardButton("❌ Рад этиш", callback_data=f"reject_{order_id}")]
            ])
            await context.bot.send_message(MASTERS_GROUP_ID, f"🔄 Буюртма №{order_id} қайта очилди!", reply_markup=keyboard)
        return

    # Ishni boshlash
    if data.startswith("start_"):
        order_id = int(data.split("_")[1])
        started = await db_start_order(order_id, user.id)
        if started:
            await query.edit_message_text(f"🔧 №{order_id} иш бошланди!", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Якунлаш", callback_data=f"finish_{order_id}")]
            ]))
            try:
                await context.bot.send_message(started['client_id'], f"🔧 №{order_id} иш бошланди!")
            except:
                pass
        return

    # Ishni yakunlash
    if data.startswith("finish_"):
        order_id = int(data.split("_")[1])
        await query.edit_message_text("📸 Иш натижаси расмини юборинг!", reply_markup=ReplyKeyboardRemove())
        context.user_data['finish_order'] = {'order_id': order_id, 'photos': []}
        return

# ============================================================
# MASTER RESULT PHOTO
# ============================================================

async def handle_result_photo(update, context):
    if 'finish_order' not in context.user_data:
        return False

    order_id = context.user_data['finish_order']['order_id']

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['finish_order']['photos'].append(file_id)
        await update.message.reply_text(f"✅ Расм қабул қилинди! ({len(context.user_data['finish_order']['photos'])} та)\nЯна расм ёки '✅ Yakunlash'", 
            reply_markup=ReplyKeyboardMarkup([["✅ Yakunlash"]], resize_keyboard=True))
        return True

    if update.message.text == "✅ Yakunlash":
        photos = context.user_data['finish_order']['photos']
        if not photos:
            await update.message.reply_text("❌ Камида 1 та расм керак!")
            return True

        completed = await db_complete_order(order_id, update.effective_user.id, ",".join(photos))
        if completed:
            await update.message.reply_text(f"✅ №{order_id} якунланди!", reply_markup=master_menu())
            try:
                await context.bot.send_message(completed['client_id'], f"✅ №{order_id} якунланди! ⭐ Рейтинг қолдиринг!")
            except:
                pass
            context.user_data.pop('finish_order', None)
        return True

    return False

# ============================================================
# MASTER REGISTRATION
# ============================================================

async def master_register_start(update, context):
    user = update.effective_user
    if await is_master(user.id):
        await update.message.reply_text("✅ Сиз аллақачон устасиз!", reply_markup=master_menu())
        return

    context.user_data['master_reg'] = {'step': 'phone'}
    await update.message.reply_text(
        "👨‍🔧 <b>УСТА БЎЛИШ</b>\n\n📞 Телефон рақамингизни юборинг:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📞 Telefon yuborish", request_contact=True)]], resize_keyboard=True)
    )

async def master_register_phone(update, context):
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text
    context.user_data['master_reg']['phone'] = phone
    await db_set_phone(update.effective_user.id, phone)
    await update.message.reply_text("🛠 Қайси хизматларни бажарасиз?\nМасалан: Электр, сантехника", reply_markup=ReplyKeyboardRemove())
    context.user_data['master_reg']['step'] = 'services'
    return

async def master_register_services(update, context):
    context.user_data['master_reg']['services'] = update.message.text
    await update.message.reply_text("📍 Иш ҳудудингизни ёзинг:\nМасалан: Andijon shahar")
    context.user_data['master_reg']['step'] = 'area'
    return

async def master_register_area(update, context):
    data = context.user_data['master_reg']
    user = update.effective_user

    await db_create_master(user.id, user.full_name or "", data['phone'], data['services'], update.message.text)

    await update.message.reply_text("✅ <b>Ариза юборилди!</b>\n⏳ Админ тасдиғи кутилмоқда.", parse_mode="HTML", reply_markup=client_menu())

    # Adminga xabar
    if ADMIN_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ TASDIQLASH", callback_data=f"master_approve:{user.id}"),
             InlineKeyboardButton("❌ RAD ETISH", callback_data=f"master_reject:{user.id}")]
        ])
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 <b>Янги уста аризаси!</b>\n👤 {user.full_name}\n📞 {data['phone']}\n🛠 {data['services']}\n📍 {update.message.text}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    context.user_data.pop('master_reg', None)

# ============================================================
# CLIENT HANDLER
# ============================================================

async def client_handler(update, context):
    user = update.effective_user
    text = update.message.text or ""

    if text == "🛒 Buyurtma berish":
        await order_start(update, context)
        return

    if text == "📋 Mening buyurtmalarim":
        orders = await db_client_orders(user.id)
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=client_menu())
            return
        out = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"
        for o in orders:
            status_emoji = {"new": "🆕", "accepted": "✅", "in_progress": "🔧", "completed": "✅", "cancelled": "❌"}.get(o['status'], "🆕")
            out += f"{status_emoji} №{o['id']} – {o['service']} – {o['status']}\n"
        await update.message.reply_text(out, parse_mode="HTML", reply_markup=client_menu())
        return

    if text == "🔍 Buyurtma holati":
        await update.message.reply_text("🔍 Буюртма ID рақамини киритинг:", reply_markup=back_keyboard())
        return

    if text.isdigit():
        order = await db_get_order(int(text))
        if order:
            status_text = {"new": "🆕 Янги", "accepted": "✅ Қабул", "in_progress": "🔧 Жараёнда", "completed": "✅ Тугатилди", "cancelled": "❌ Бекор"}.get(order['status'], "🆕 Янги")
            await update.message.reply_text(
                f"🔍 <b>Буюртма №{order['id']}</b>\n\n📌 {status_text}\n🛠 {order['service']}\n📍 {order['address']}\n👨‍🔧 {order['master_name'] or 'Кутилмоқда'}",
                parse_mode="HTML"
            )
        return

    if text == "❌ Bekor qilish":
        await update.message.reply_text("❌ Бекор қилиш учун буюртма ID рақамини киритинг:", reply_markup=back_keyboard())
        return

    if text == "👨‍🔧 Usta bo'lish":
        await master_register_start(update, context)
        return

    if text == "📞 Dispetcher" or text == "🚨 24/7":
        await update.message.reply_text(f"📞 <b>Диспетчер</b>\n\n{DISPATCHER_PHONE}\n🕐 24/7", parse_mode="HTML", reply_markup=client_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=client_menu())

# ============================================================
# MASTER HANDLER
# ============================================================

async def master_handler(update, context):
    user = update.effective_user
    text = update.message.text or ""

    if text == "🆕 Yangi buyurtmalar":
        orders = await db_get_orders_by_status("new")
        if not orders:
            await update.message.reply_text("🆕 Янги буюртмалар йўқ.", reply_markup=master_menu())
            return
        out = "🆕 <b>ЯНГИ БУЮРТМАЛАР</b>\n\n"
        for o in orders:
            out += f"№{o['id']} – {o['service']} – {o['client_name']}\n"
        await update.message.reply_text(out, parse_mode="HTML", reply_markup=master_menu())
        return

    if text == "📋 Mening buyurtmalarim":
        orders = await db_master_orders(user.id)
        if not orders:
            await update.message.reply_text("📋 Буюртмалар йўқ.", reply_markup=master_menu())
            return
        out = "📋 <b>МЕНИНГ БУЮРТМАЛАРИМ</b>\n\n"
        for o in orders:
            out += f"№{o['id']} – {o['service']} – {o['status']}\n"
        await update.message.reply_text(out, parse_mode="HTML", reply_markup=master_menu())
        return

    if text == "✅ Qabul qilish":
        await update.message.reply_text("✅ Қабул қилиш учун буюртма ID рақамини киритинг:", reply_markup=back_keyboard())
        return

    if text == "🔧 Ishni boshlash":
        await update.message.reply_text("🔧 Ишни бошлаш учун буюртма ID рақамини киритинг:", reply_markup=back_keyboard())
        return

    if text == "✅ Ishni yakunlash":
        await update.message.reply_text("✅ Ишни якунлаш учун буюртма ID рақамини киритинг:", reply_markup=back_keyboard())
        return

    if text.isdigit():
        order_id = int(text)
        order = await db_get_order(order_id)
        if not order:
            await update.message.reply_text("❌ Буюртма топилмади.", reply_markup=master_menu())
            return

        if order['status'] == 'new':
            master = await db_get_master(user.id)
            accepted = await db_accept_order(order_id, user.id, master['full_name'])
            if accepted:
                await update.message.reply_text(f"✅ №{order_id} қабул қилинди!", reply_markup=master_menu())
                try:
                    await context.bot.send_message(order['client_id'], f"✅ Буюртмангиз №{order_id} қабул қилинди!")
                except:
                    pass
            return

        if order['status'] == 'accepted' and order['master_id'] == user.id:
            started = await db_start_order(order_id, user.id)
            if started:
                await update.message.reply_text(f"🔧 №{order_id} иш бошланди!", reply_markup=master_menu())
                try:
                    await context.bot.send_message(order['client_id'], f"🔧 №{order_id} иш бошланди!")
                except:
                    pass
            return

        if order['status'] == 'in_progress' and order['master_id'] == user.id:
            await update.message.reply_text("📸 Иш натижаси расмини юборинг!", reply_markup=ReplyKeyboardRemove())
            context.user_data['finish_order'] = {'order_id': order_id, 'photos': []}
            return

        await update.message.reply_text("❌ Бу буюртмани якунлаш мумкин эмас.", reply_markup=master_menu())
        return

    if text == "📊 Statistika":
        orders = await db_master_orders(user.id)
        total = len(orders)
        completed = len([o for o in orders if o["status"] == "completed"])
        await update.message.reply_text(f"📊 <b>СТАТИСТИКА</b>\n\n📋 Жами: {total}\n✅ Якунланган: {completed}", parse_mode="HTML", reply_markup=master_menu())
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(f"📞 Диспетчер: {DISPATCHER_PHONE}", reply_markup=master_menu())
        return

    await update.message.reply_text("Илтимос, менюдан танланг.", reply_markup=master_menu())

# ============================================================
# ADMIN HANDLER
# ============================================================

async def admin_handler(update, context):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    if text == "👨‍🔧 Ustalar":
        await update.message.reply_text("👨‍🔧 Усталар бўлими.", reply_markup=admin_menu())
        return

    if text == "📋 Barcha buyurtmalar":
        await update.message.reply_text("📋 Барча буюртмалар.", reply_markup=admin_menu())
        return

    if text == "📊 Statistika":
        stats = await db_stats()
        if stats:
            await update.message.reply_text(
                f"📊 <b>СТАТИСТИКА</b>\n\n"
                f"📋 Жами: {stats['total']}\n"
                f"🆕 Янги: {stats['new']}\n"
                f"✅ Қабул: {stats['accepted']}\n"
                f"🔧 Жараёнда: {stats['progress']}\n"
                f"✅ Якунланган: {stats['completed']}",
                parse_mode="HTML",
                reply_markup=admin_menu()
            )
        return

    if text == "📞 Dispetcher":
        await update.message.reply_text(f"📞 Диспетчер: {DISPATCHER_PHONE}", reply_markup=admin_menu())
        return

# ============================================================
# MESSAGE ROUTER
# ============================================================

async def message_router(update, context):
    if not update.message:
        return

    user = update.effective_user
    text = update.message.text or ""

    # Master result photo
    if await handle_result_photo(update, context):
        return

    # Master registration
    if 'master_reg' in context.user_data:
        step = context.user_data['master_reg'].get('step')
        if step == 'phone':
            await master_register_phone(update, context)
            return
        if step == 'services':
            await master_register_services(update, context)
            return
        if step == 'area':
            await master_register_area(update, context)
            return

    # Admin
    if user.id == ADMIN_ID:
        await admin_handler(update, context)
        return

    # Master
    if await is_master(user.id):
        await master_handler(update, context)
        return

    # Client
    await client_handler(update, context)

# ============================================================
# MAIN
# ============================================================

async def post_init(app):
    await init_db()
    logger.info("🚀 USTA24 DISPATCHER STARTED")

async def post_shutdown(app):
    if db_pool:
        await db_pool.close()
    logger.info("Database closed")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    app.add_handler(CommandHandler("start", start))

    # Buyurtma Conversation
    order_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🛒 Buyurtma berish$"), order_start)],
        states={
            SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_service)],
            ORDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_name)],
            ORDER_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, order_phone)],
            ORDER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_address)],
            ORDER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_description)],
            ORDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_time)],
            ORDER_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, order_photo)],
            ORDER_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_submit)],
        },
        fallbacks=[CommandHandler("cancel", start)],
        allow_reentry=True
    )
    app.add_handler(order_conv)

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, message_router))

    logger.info("Bot polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
