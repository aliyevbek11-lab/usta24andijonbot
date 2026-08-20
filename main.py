#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================
USTA 24 ANDIJON BOT
=============================================
Telegram bot for managing masters and orders
=============================================
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
import threading

# Telegram kutubxonasi
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)

# SQLite
import aiosqlite

# Flask (Railway web server uchun)
from flask import Flask, jsonify

# =====================================================
# FLASK WEB SERVER (Railway Health Check uchun)
# =====================================================

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'name': 'USTA 24 ANDIJON BOT',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@flask_app.route('/stats')
def stats():
    return jsonify({
        'status': 'ok',
        'uptime': 'Running',
        'bot': 'USTA 24 ANDIJON BOT'
    })

def run_flask():
    """Flask serverni alohida thread da ishga tushirish"""
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# =====================================================
# ENVIRONMENT VARIABLES
# =====================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DISPATCHER_ID = int(os.environ.get("DISPATCHER_ID", "0"))
MASTERS_GROUP_ID = int(os.environ.get("MASTERS_GROUP_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL", "usta24.db")

# Dispatcher ID lar ro'yxati
DISPATCHER_IDS = []
if DISPATCHER_ID:
    DISPATCHER_IDS.append(DISPATCHER_ID)

# =====================================================
# CHECK ENVIRONMENT
# =====================================================

def check_env():
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN")
    if ADMIN_ID == 0:
        errors.append("ADMIN_ID")
    
    if errors:
        print(f"❌ Missing: {', '.join(errors)}")
        print("Please set environment variables:")
        print("  BOT_TOKEN=your_token")
        print("  ADMIN_ID=your_id")
        return False
    
    print("✅ All environment variables set")
    print(f"✅ BOT_TOKEN: {'*' * 10}")
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
    print(f"✅ DISPATCHER_ID: {DISPATCHER_ID}")
    print(f"✅ MASTERS_GROUP_ID: {MASTERS_GROUP_ID}")
    print(f"✅ DATABASE_URL: {DATABASE_URL}")
    return True

# =====================================================
# LOGGING
# =====================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================================
# CONVERSATION STATES
# =====================================================

ADD_MASTER_ID, ADD_MASTER_NAME, ADD_MASTER_PHONE, ADD_MASTER_USERNAME, ADD_MASTER_SERVICES = range(5)
ORDER_SERVICE, ORDER_DESCRIPTION, ORDER_ADDRESS, ORDER_CONFIRM = range(10, 14)

# =====================================================
# DATABASE CLASS
# =====================================================

class Database:
    def __init__(self, db_name="usta24.db"):
        self.db_name = db_name

    async def init_db(self):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # Masters table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS masters (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        phone TEXT,
                        username TEXT,
                        services TEXT,
                        rating REAL DEFAULT 0,
                        orders_count INTEGER DEFAULT 0,
                        completed_orders INTEGER DEFAULT 0,
                        balance REAL DEFAULT 0,
                        status TEXT DEFAULT 'busy',
                        blocked BOOLEAN DEFAULT FALSE,
                        block_reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Clients table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        phone TEXT,
                        username TEXT,
                        address TEXT,
                        orders_count INTEGER DEFAULT 0,
                        total_spent REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Orders table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER,
                        master_id INTEGER,
                        service TEXT,
                        description TEXT,
                        price REAL DEFAULT 0,
                        status TEXT DEFAULT 'yangi',
                        priority TEXT DEFAULT 'o\'rta',
                        address TEXT,
                        schedule TEXT,
                        client_phone TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        cancelled_at TIMESTAMP,
                        cancel_reason TEXT,
                        FOREIGN KEY (client_id) REFERENCES clients(id),
                        FOREIGN KEY (master_id) REFERENCES masters(id)
                    )
                """)

                # Ratings table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS ratings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER,
                        master_id INTEGER,
                        client_id INTEGER,
                        rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                        comment TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (order_id) REFERENCES orders(id),
                        FOREIGN KEY (master_id) REFERENCES masters(id),
                        FOREIGN KEY (client_id) REFERENCES clients(id)
                    )
                """)

                await db.commit()
                logger.info("✅ Database initialized")
                return True
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            return False

    # ========== MASTERS ==========
    async def add_master(self, master_id: int, name: str, phone: str = "", 
                         username: str = "", services: str = "") -> bool:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO masters (id, name, phone, username, services)
                    VALUES (?, ?, ?, ?, ?)
                """, (master_id, name, phone, username, services))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Add master error: {e}")
            return False

    async def get_master(self, master_id: int) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM masters WHERE id = ?",
                    (master_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'completed_orders': row[7],
                        'balance': row[8], 'status': row[9], 'blocked': row[10],
                        'block_reason': row[11], 'created_at': row[12],
                        'updated_at': row[13]
                    }
                return None
        except Exception as e:
            logger.error(f"Get master error: {e}")
            return None

    async def get_all_masters(self, active_only: bool = True) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                query = "SELECT * FROM masters"
                if active_only:
                    query += " WHERE blocked = FALSE"
                query += " ORDER BY rating DESC, orders_count DESC"
                
                cursor = await db.execute(query)
                rows = await cursor.fetchall()
                
                masters = []
                for row in rows:
                    masters.append({
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'completed_orders': row[7],
                        'balance': row[8], 'status': row[9], 'blocked': row[10],
                        'block_reason': row[11], 'created_at': row[12],
                        'updated_at': row[13]
                    })
                return masters
        except Exception as e:
            logger.error(f"Get all masters error: {e}")
            return []

    async def get_available_masters(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("""
                    SELECT * FROM masters 
                    WHERE status = 'free' AND blocked = FALSE
                    ORDER BY rating DESC
                """)
                rows = await cursor.fetchall()
                
                masters = []
                for row in rows:
                    masters.append({
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'status': row[9]
                    })
                return masters
        except Exception as e:
            logger.error(f"Get available masters error: {e}")
            return []

    async def update_master_status(self, master_id: int, status: str):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE masters 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, master_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Update master status error: {e}")

    async def delete_master(self, master_id: int):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("UPDATE masters SET blocked = TRUE WHERE id = ?", (master_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"Delete master error: {e}")

    # ========== CLIENTS ==========
    async def add_client(self, client_id: int, name: str, phone: str = "", 
                         username: str = "", address: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO clients (id, name, phone, username, address, last_active)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (client_id, name, phone, username, address))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Add client error: {e}")
            return False

    async def get_client(self, client_id: int) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM clients WHERE id = ?",
                    (client_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'address': row[4],
                        'orders_count': row[5], 'total_spent': row[6],
                        'created_at': row[7], 'last_active': row[8]
                    }
                return None
        except Exception as e:
            logger.error(f"Get client error: {e}")
            return None

    async def get_all_clients(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM clients ORDER BY orders_count DESC"
                )
                rows = await cursor.fetchall()
                
                clients = []
                for row in rows:
                    clients.append({
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'address': row[4],
                        'orders_count': row[5], 'total_spent': row[6],
                        'created_at': row[7], 'last_active': row[8]
                    })
                return clients
        except Exception as e:
            logger.error(f"Get all clients error: {e}")
            return []

    # ========== ORDERS ==========
    async def add_order(self, client_id: int, service: str, 
                        description: str = "", address: str = "",
                        client_phone: str = "") -> int:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("""
                    INSERT INTO orders (client_id, service, description, address, client_phone)
                    VALUES (?, ?, ?, ?, ?)
                """, (client_id, service, description, address, client_phone))
                await db.commit()
                order_id = cursor.lastrowid
                
                await db.execute(
                    "UPDATE clients SET orders_count = orders_count + 1 WHERE id = ?",
                    (client_id,)
                )
                await db.commit()
                
                return order_id
        except Exception as e:
            logger.error(f"Add order error: {e}")
            return 0

    async def get_order(self, order_id: int) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM orders WHERE id = ?",
                    (order_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'created_at': row[11], 'updated_at': row[12],
                        'completed_at': row[13], 'cancelled_at': row[14],
                        'cancel_reason': row[15]
                    }
                return None
        except Exception as e:
            logger.error(f"Get order error: {e}")
            return None

    async def get_orders(self, user_id: int, user_type: str = 'client') -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                field = 'client_id' if user_type == 'client' else 'master_id'
                cursor = await db.execute(
                    f"SELECT * FROM orders WHERE {field} = ? ORDER BY created_at DESC",
                    (user_id,)
                )
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'created_at': row[11], 'updated_at': row[12]
                    })
                return orders
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []

    async def get_all_orders(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM orders ORDER BY created_at DESC"
                )
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'created_at': row[11], 'updated_at': row[12]
                    })
                return orders
        except Exception as e:
            logger.error(f"Get all orders error: {e}")
            return []

    async def get_new_orders(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM orders WHERE status = 'yangi' ORDER BY created_at DESC"
                )
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'created_at': row[11], 'updated_at': row[12]
                    })
                return orders
        except Exception as e:
            logger.error(f"Get new orders error: {e}")
            return []

    async def update_order_status(self, order_id: int, status: str):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE orders 
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (status, order_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Update order status error: {e}")

    async def assign_master(self, order_id: int, master_id: int):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE orders 
                    SET master_id = ?, status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (master_id, order_id))
                await db.commit()
                
                await db.execute(
                    "UPDATE masters SET status = 'busy' WHERE id = ?",
                    (master_id,)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Assign master error: {e}")

    # ========== STATISTICS ==========
    async def get_stats(self) -> Dict:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                masters_count = await db.execute("SELECT COUNT(*) FROM masters WHERE blocked = FALSE")
                masters_count = await masters_count.fetchone()
                
                free_masters = await db.execute("SELECT COUNT(*) FROM masters WHERE status = 'free' AND blocked = FALSE")
                free_masters = await free_masters.fetchone()
                
                busy_masters = await db.execute("SELECT COUNT(*) FROM masters WHERE status = 'busy' AND blocked = FALSE")
                busy_masters = await busy_masters.fetchone()
                
                clients_count = await db.execute("SELECT COUNT(*) FROM clients")
                clients_count = await clients_count.fetchone()
                
                orders_count = await db.execute("SELECT COUNT(*) FROM orders")
                orders_count = await orders_count.fetchone()
                
                today = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"
                )
                today = await today.fetchone()
                
                return {
                    'masters': masters_count[0],
                    'free_masters': free_masters[0],
                    'busy_masters': busy_masters[0],
                    'clients': clients_count[0],
                    'orders': orders_count[0],
                    'today_orders': today[0]
                }
        except Exception as e:
            logger.error(f"Get stats error: {e}")
            return {}

    async def add_rating(self, order_id: int, master_id: int, 
                         client_id: int, rating: int, comment: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT INTO ratings (order_id, master_id, client_id, rating, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, master_id, client_id, rating, comment))
                await db.commit()
        except Exception as e:
            logger.error(f"Add rating error: {e}")

    async def get_master_rating(self, master_id: int) -> Dict:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*), AVG(rating) FROM ratings WHERE master_id = ?",
                    (master_id,)
                )
                row = await cursor.fetchone()
                return {
                    'count': row[0] or 0,
                    'average': round(row[1] or 0, 1)
                }
        except Exception as e:
            logger.error(f"Get master rating error: {e}")
            return {'count': 0, 'average': 0}

# =====================================================
# DATABASE OBJECT
# =====================================================

db = Database()

# =====================================================
# KEYBOARDS
# =====================================================

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛠 Xizmatlar", "👨‍🔧 Ustalar"],
            ["📝 Buyurtma berish", "📋 Mening buyurtmalarim"],
            ["👤 Shaxsiy ma'lumot", "ℹ️ Yordam"],
            ["👑 Admin paneli"]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Mijozlar bazasi", "👨‍🔧 Ustalar"],
            ["➕ Usta qo'shish", "📋 Barcha buyurtmalar"],
            ["📊 Statistika", "⬅️ Asosiy menyu"]
        ],
        resize_keyboard=True
    )

def dispatcher_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar"],
            ["🟡 Qabul qilish", "🚫 Rad etish"],
            ["👨‍🔧 Usta tanlash"],
            ["⬅️ Admin menyu"]
        ],
        resize_keyboard=True
    )

def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🟡 Buyurtmani qabul qilish"],
            ["🔵 Ishni boshlash"],
            ["✅ Ishni yakunlash"],
            ["📋 O'z buyurtmalarim"],
            ["⬅️ Asosiy menyu"]
        ],
        resize_keyboard=True
    )

def order_status_keyboard(order_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Yangi", callback_data=f"os_{order_id}_yangi"),
            InlineKeyboardButton("🟡 Qabul", callback_data=f"os_{order_id}_qabul_qilingan")
        ],
        [
            InlineKeyboardButton("🔵 Jarayonda", callback_data=f"os_{order_id}_jarayonda"),
            InlineKeyboardButton("✅ Bajarildi", callback_data=f"os_{order_id}_bajarildi")
        ],
        [
            InlineKeyboardButton("⭐ Yakunlandi", callback_data=f"os_{order_id}_yakunlangan"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"os_{order_id}_bekor_qilindi")
        ]
    ])

def master_select_keyboard(order_id: int, masters: List[Dict]):
    keyboard = []
    for master in masters[:10]:
        keyboard.append([
            InlineKeyboardButton(
                f"{master['name']} ⭐{master['rating']}",
                callback_data=f"ms_{order_id}_{master['id']}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)

# =====================================================
# HELPERS
# =====================================================

def get_status_emoji(status: str) -> str:
    emojis = {
        'yangi': '🆕', 'qabul_qilingan': '🟡',
        'jarayonda': '🔵', 'bajarildi': '✅',
        'yakunlangan': '⭐', 'bekor_qilindi': '❌',
        'rad_etilgan': '🚫'
    }
    return emojis.get(status, '📋')

def get_status_text(status: str) -> str:
    texts = {
        'yangi': 'Yangi', 'qabul_qilingan': 'Qabul qilingan',
        'jarayonda': 'Jarayonda', 'bajarildi': 'Bajarildi',
        'yakunlangan': 'Yakunlangan', 'bekor_qilindi': 'Bekor qilingan',
        'rad_etilgan': 'Rad etilgan'
    }
    return texts.get(status, status)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_dispatcher(user_id: int) -> bool:
    return user_id in DISPATCHER_IDS

# =====================================================
# BOT HANDLERS
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if is_admin(user_id):
        stats = await db.get_stats()
        await update.message.reply_text(
            f"👑 <b>USTA 24 ANDIJON</b>\n"
            f"Admin paneliga xush kelibsiz!\n\n"
            f"📊 Statistika:\n"
            f"👨‍🔧 Ustalar: {stats.get('masters', 0)}\n"
            f"👤 Mijozlar: {stats.get('clients', 0)}\n"
            f"📋 Buyurtmalar: {stats.get('orders', 0)}\n"
            f"📅 Bugun: {stats.get('today_orders', 0)}",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    if is_dispatcher(user_id):
        await update.message.reply_text(
            f"👨‍💼 <b>Dispetcher paneli</b>",
            reply_markup=dispatcher_menu(),
            parse_mode="HTML"
        )
        return
    
    master = await db.get_master(user_id)
    if master:
        status_text = "🟢 Ishda" if master['status'] == 'free' else "🔴 Band"
        await update.message.reply_text(
            f"👨‍🔧 <b>Usta paneli</b>\n\n"
            f"👤 {master['name']}\n"
            f"⭐ Reyting: {master['rating']}\n"
            f"📊 Holat: {status_text}",
            reply_markup=master_menu(),
            parse_mode="HTML"
        )
        return
    
    await db.add_client(user_id, user.full_name, username=user.username or "")
    
    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"🏠 <b>USTA 24 ANDIJON</b> botiga xush kelibsiz!\n\n"
        f"📌 Yordam olish uchun /help",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>YORDAM</b>\n\n"
        "🛠 Xizmatlar - Barcha xizmatlar\n"
        "👨‍🔧 Ustalar - Ustalar ro'yxati\n"
        "📝 Buyurtma berish - Yangi buyurtma\n"
        "📋 Mening buyurtmalarim - Buyurtma tarixi\n"
        "👤 Shaxsiy ma'lumot - Profil\n\n"
        "👑 Adminlar uchun maxsus panel",
        parse_mode="HTML"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    await update.message.reply_text(
        "👑 <b>ADMIN PANEL</b>",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )

async def masters_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    masters = await db.get_all_masters()
    if not masters:
        await update.message.reply_text("👨‍🔧 Hozircha ustalar yo'q.")
        return
    
    text = "👨‍🔧 <b>USTALAR</b>\n\n"
    for i, master in enumerate(masters[:10], 1):
        status_emoji = "🟢" if master['status'] == 'free' else "🔴"
        text += (
            f"{i}️⃣ {status_emoji} <b>{master['name']}</b>\n"
            f"⭐ {master['rating']}\n"
            f"🛠 {master['services']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def clients_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    clients = await db.get_all_clients()
    if not clients:
        await update.message.reply_text("👤 Mijozlar yo'q.")
        return
    
    text = "👤 <b>MIJOZLAR</b>\n\n"
    for client in clients[:10]:
        text += (
            f"👤 {client['name']}\n"
            f"📞 {client['phone'] or 'yo'q'}\n"
            f"📋 {client['orders_count']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = await db.get_all_orders()
    
    if not orders:
        await update.message.reply_text("📋 Hozircha buyurtmalar yo'q.")
        return
    
    text = "📋 <b>BARCHA BUYURTMALAR</b>\n\n"
    for order in orders[:10]:
        client = await db.get_client(order['client_id'])
        text += (
            f"№{order['id']} {get_status_emoji(order['status'])}\n"
            f"👤 {client['name'] if client else 'Mijoz'}\n"
            f"🛠 {order['service']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = await db.get_new_orders()
    
    if not orders:
        await update.message.reply_text("🆕 Hozircha yangi buyurtmalar yo'q.")
        return
    
    text = "🆕 <b>YANGI BUYURTMALAR</b>\n\n"
    for order in orders[:10]:
        client = await db.get_client(order['client_id'])
        text += (
            f"№{order['id']}\n"
            f"👤 {client['name'] if client else 'Mijoz'}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address'] or 'yo'q'}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    stats = await db.get_stats()
    
    text = f"📊 <b>STATISTIKA</b>\n\n"
    text += f"👨‍🔧 Ustalar: {stats.get('masters', 0)}\n"
    text += f"   🟢 Bo'sh: {stats.get('free_masters', 0)}\n"
    text += f"   🔴 Band: {stats.get('busy_masters', 0)}\n"
    text += f"👤 Mijozlar: {stats.get('clients', 0)}\n"
    text += f"📋 Buyurtmalar: {stats.get('orders', 0)}\n"
    text += f"📅 Bugun: {stats.get('today_orders', 0)}"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        await admin_panel(update, context)
    elif is_dispatcher(user_id):
        await update.message.reply_text(
            "👨‍💼 Dispetcher paneli",
            reply_markup=dispatcher_menu()
        )
    else:
        master = await db.get_master(user_id)
        if master:
            await update.message.reply_text(
                "👨‍🔧 Usta paneli",
                reply_markup=master_menu()
            )
        else:
            await update.message.reply_text(
                "🏠 Bosh menyu",
                reply_markup=main_menu()
            )

async def add_master_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "➕ <b>USTA QO'SHISH</b>\n\n"
        "1️⃣ Ustaning Telegram ID raqamini yuboring.\n\n"
        "Masalan: 123456789",
        parse_mode="HTML"
    )
    return ADD_MASTER_ID

async def add_master_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    if "master_add" not in context.user_data:
        context.user_data["master_add"] = {"step": "id"}
    
    data = context.user_data["master_add"]
    text = update.message.text.strip()
    
    if data["step"] == "id":
        try:
            master_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ ID faqat raqam bo'lishi kerak!")
            return ADD_MASTER_ID
        
        existing = await db.get_master(master_id)
        if existing:
            await update.message.reply_text(f"⚠️ Bu ID ({master_id}) bilan usta allaqachon qo'shilgan.")
            return ADD_MASTER_ID
        
        data["id"] = master_id
        data["step"] = "name"
        
        await update.message.reply_text(
            "✅ ID qabul qilindi!\n\n"
            "2️⃣ Ustaning to'liq ismini yozing:"
        )
        return ADD_MASTER_NAME
    
    if data["step"] == "name":
        if len(text) < 2:
            await update.message.reply_text("❌ Ism kamida 2 harf bo'lishi kerak!")
            return ADD_MASTER_NAME
        
        data["name"] = text
        data["step"] = "phone"
        
        await update.message.reply_text(
            "✅ Ism qabul qilindi!\n\n"
            "3️⃣ Ustaning telefon raqamini yuboring.\n\n"
            "Masalan: +998901234567"
        )
        return ADD_MASTER_PHONE
    
    if data["step"] == "phone":
        data["phone"] = text
        data["step"] = "username"
        
        await update.message.reply_text(
            "✅ Telefon qabul qilindi!\n\n"
            "4️⃣ Ustaning Telegram username'ini yozing.\n\n"
            "Masalan: @usta24\n"
            "Agar yo'q bo'lsa: yo'q"
        )
        return ADD_MASTER_USERNAME
    
    if data["step"] == "username":
        if text.lower() == "yo'q":
            data["username"] = ""
        else:
            if not text.startswith("@"):
                text = "@" + text
            data["username"] = text
        
        data["step"] = "services"
        
        await update.message.reply_text(
            "✅ Username qabul qilindi!\n\n"
            "5️⃣ Usta qaysi xizmatlarni bajaradi?\n\n"
            "Masalan: Mebel, Santexnika, Elektr"
        )
        return ADD_MASTER_SERVICES
    
    if data["step"] == "services":
        if len(text) < 2:
            await update.message.reply_text("❌ Kamida bitta xizmat kiriting!")
            return ADD_MASTER_SERVICES
        
        data["services"] = text
        
        success = await db.add_master(
            data["id"], data["name"], data["phone"],
            data["username"], data["services"]
        )
        
        context.user_data.pop("master_add", None)
        
        if success:
            await update.message.reply_text(
                f"✅ <b>USTA QO'SHILDI!</b>\n\n"
                f"👨‍🔧 {data['name']}\n"
                f"🆔 ID: {data['id']}\n"
                f"📞 {data['phone']}\n"
                f"🛠 {data['services']}",
                reply_markup=admin_menu(),
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ Xatolik yuz berdi!", reply_markup=admin_menu())
        
        return ConversationHandler.END

async def cancel_add_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("master_add", None)
    await update.message.reply_text("❌ Bekor qilindi.", reply_markup=admin_menu())
    return ConversationHandler.END

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = await db.get_orders(user_id, 'client')
    
    if not orders:
        await update.message.reply_text("📋 Sizda buyurtmalar yo'q.")
        return
    
    text = "📋 <b>MENING BUYURTMALARIM</b>\n\n"
    for order in orders[:10]:
        master = await db.get_master(order['master_id']) if order['master_id'] else None
        master_name = master['name'] if master else "Tayinlanmagan"
        text += (
            f"№{order['id']} {get_status_emoji(order['status'])}\n"
            f"🛠 {order['service']}\n"
            f"👨‍🔧 {master_name}\n"
            f"📅 {order['created_at'][:10]}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def master_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = await db.get_orders(user_id, 'master')
    
    if not orders:
        await update.message.reply_text("📋 Sizda buyurtmalar yo'q.")
        return
    
    text = "📋 <b>O'Z BUYURTMALARIM</b>\n\n"
    for order in orders[:10]:
        client = await db.get_client(order['client_id'])
        text += (
            f"№{order['id']} {get_status_emoji(order['status'])}\n"
            f"👤 {client['name'] if client else 'Mijoz'}\n"
            f"🛠 {order['service']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def master_accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    orders = await db.get_orders(user_id, 'master')
    pending = [o for o in orders if o['status'] == 'qabul_qilingan']
    
    if not pending:
        await update.message.reply_text("❌ Qabul qilingan buyurtmalar yo'q!")
        return
    
    text = "🟡 <b>BUYURTMA QABUL QILISH</b>\n\n"
    text += "Buyurtma raqamini yozing:\n\n"
    for order in pending[:5]:
        client = await db.get_client(order['client_id'])
        text += f"№{order['id']} - {order['service']} - {client['name'] if client else 'Mijoz'}\n"
    
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['master_accept'] = True

async def master_accept_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('master_accept'):
        return
    
    try:
        order_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Buyurtma raqami faqat raqam bo'lishi kerak!")
        return
    
    order = await db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Buyurtma topilmadi!")
        return
    
    if order['master_id'] != user_id:
        await update.message.reply_text("❌ Bu buyurtma sizga tegishli emas!")
        return
    
    if order['status'] != 'qabul_qilingan':
        await update.message.reply_text(f"❌ Buyurtma {get_status_text(order['status'])} holatida!")
        return
    
    await db.update_order_status(order_id, 'jarayonda')
    context.user_data.pop('master_accept', None)
    
    await update.message.reply_text(
        f"✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n"
        f"№{order_id}\n"
        f"🔵 Ishni boshlang!",
        reply_markup=master_menu(),
        parse_mode="HTML"
    )

async def master_start_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    orders = await db.get_orders(user_id, 'master')
    pending = [o for o in orders if o['status'] == 'jarayonda']
    
    if not pending:
        await update.message.reply_text("❌ Jarayondagi buyurtmalar yo'q!")
        return
    
    text = "🔵 <b>ISHNI BOSHLASH</b>\n\n"
    text += "Buyurtma raqamini yozing:\n\n"
    for order in pending[:5]:
        client = await db.get_client(order['client_id'])
        text += f"№{order['id']} - {order['service']} - {client['name'] if client else 'Mijoz'}\n"
    
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['master_start'] = True

async def master_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('master_start'):
        return
    
    try:
        order_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Buyurtma raqami faqat raqam bo'lishi kerak!")
        return
    
    order = await db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Buyurtma topilmadi!")
        return
    
    if order['master_id'] != user_id:
        await update.message.reply_text("❌ Bu buyurtma sizga tegishli emas!")
        return
    
    if order['status'] != 'jarayonda':
        await update.message.reply_text(f"❌ Buyurtma {get_status_text(order['status'])} holatida!")
        return
    
    await db.update_order_status(order_id, 'bajarildi')
    context.user_data.pop('master_start', None)
    
    await update.message.reply_text(
        f"✅ <b>ISH BAJARILDI!</b>\n\n"
        f"№{order_id}\n"
        f"⭐ Yakunlash uchun /finish {order_id}",
        reply_markup=master_menu(),
        parse_mode="HTML"
    )

async def master_finish_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    orders = await db.get_orders(user_id, 'master')
    completed = [o for o in orders if o['status'] == 'bajarildi']
    
    if not completed:
        await update.message.reply_text("❌ Bajarilgan buyurtmalar yo'q!")
        return
    
    text = "⭐ <b>ISHNI YAKUNLASH</b>\n\n"
    text += "Buyurtma raqamini yozing:\n\n"
    for order in completed[:5]:
        client = await db.get_client(order['client_id'])
        text += f"№{order['id']} - {order['service']} - {client['name'] if client else 'Mijoz'}\n"
    
    await update.message.reply_text(text, parse_mode="HTML")
    context.user_data['master_finish'] = True

async def master_finish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.user_data.get('master_finish'):
        return
    
    try:
        order_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Buyurtma raqami faqat raqam bo'lishi kerak!")
        return
    
    order = await db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Buyurtma topilmadi!")
        return
    
    if order['master_id'] != user_id:
        await update.message.reply_text("❌ Bu buyurtma sizga tegishli emas!")
        return
    
    if order['status'] != 'bajarildi':
        await update.message.reply_text(f"❌ Buyurtma {get_status_text(order['status'])} holatida!")
        return
    
    await db.update_order_status(order_id, 'yakunlangan')
    context.user_data.pop('master_finish', None)
    
    # Mijozga rating so'rash
    try:
        await context.bot.send_message(
            order['client_id'],
            f"⭐ <b>BUYURTMA YAKUNLANDI!</b>\n\n"
            f"№{order_id}\n"
            f"🛠 {order['service']}\n\n"
            f"📊 Ustani baholang: /rate {order_id}",
            parse_mode="HTML"
        )
    except:
        pass
    
    await update.message.reply_text(
        f"✅ <b>BUYURTMA YAKUNLANDI!</b>\n\n"
        f"№{order_id}\n"
        f"⭐ Mijoz bahosini kuting...",
        reply_markup=master_menu(),
        parse_mode="HTML"
    )

async def rate_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ /rate order_id - buyurtma raqamini yozing!")
        return
    
    try:
        order_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Buyurtma raqami faqat raqam bo'lishi kerak!")
        return
    
    order = await db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Buyurtma topilmadi!")
        return
    
    if order['client_id'] != user_id:
        await update.message.reply_text("❌ Bu buyurtma sizga tegishli emas!")
        return
    
    if order['status'] != 'yakunlangan':
        await update.message.reply_text(f"❌ Buyurtma hali yakunlanmagan!")
        return
    
    master = await db.get_master(order['master_id'])
    if not master:
        await update.message.reply_text("❌ Usta topilmadi!")
        return
    
    # Rating keyboard
    keyboard = []
    for i in range(1, 6):
        keyboard.append([
            InlineKeyboardButton(f"{'⭐' * i} {i}", callback_data=f"rate_{order_id}_{order['master_id']}_{i}")
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back")])
    
    await update.message.reply_text(
        f"⭐ <b>USTANI BAHOLASH</b>\n\n"
        f"№{order_id}\n"
        f"👨‍🔧 Usta: {master['name']}\n\n"
        f"Bahoni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

# =====================================================
# CALLBACK HANDLER
# =====================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "back":
        await query.edit_text("⬅️ Orqaga qaytdingiz.")
        return
    
    if data.startswith("os_"):
        parts = data.split("_")
        if len(parts) == 3:
            order_id = int(parts[1])
            status = parts[2]
            await db.update_order_status(order_id, status)
            await query.edit_text(f"✅ Buyurtma №{order_id} statusi o'zgartirildi!")
            return
    
    if data.startswith("assign_"):
        order_id = int(data.split("_")[1])
        masters = await db.get_available_masters()
        if not masters:
            await query.edit_text("❌ Bo'sh ustalar yo'q!")
            return
        
        await query.edit_text(
            f"👨‍🔧 Buyurtma №{order_id} uchun ustani tanlang:",
            reply_markup=master_select_keyboard(order_id, masters)
        )
        return
    
    if data.startswith("ms_"):
        parts = data.split("_")
        order_id = int(parts[1])
        master_id = int(parts[2])
        
        await db.assign_master(order_id, master_id)
        
        # Mijozga xabar
        order = await db.get_order(order_id)
        if order:
            try:
                await context.bot.send_message(
                    order['client_id'],
                    f"✅ <b>USTA TAYINLANDI!</b>\n\n"
                    f"№{order_id}\n"
                    f"👨‍🔧 Usta tez orada bog'lanadi!",
                    parse_mode="HTML"
                )
            except:
                pass
        
        await query.edit_text(f"✅ Buyurtma №{order_id} ga usta tayinlandi!")
        return
    
    if data.startswith("rate_"):
        parts = data.split("_")
        order_id = int(parts[1])
        master_id = int(parts[2])
        rating = int(parts[3])
        
        await db.add_rating(order_id, master_id, user_id, rating)
        await db.update_master_rating(master_id)
        
        await query.edit_text(f"⭐ Rahmat! Usta {rating} ga baholandi! ✅")
        return

# =====================================================
# UNKNOWN HANDLER
# =====================================================

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Tushunmadim. Iltimos, tugmalardan foydalaning!\n"
        "📖 Yordam olish uchun /help",
        reply_markup=main_menu()
    )

# =====================================================
# MAIN FUNCTION
# =====================================================

async def main():
    try:
        if not check_env():
            sys.exit(1)
        
        await db.init_db()
        logger.info("✅ Database initialized")
        
        # Flask serverni alohida thread da ishga tushirish
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info(f"✅ Flask server started on port {os.environ.get('PORT', 8080)}")
        
        # Application
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        logger.info("✅ Application built")
        
        # Commands
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("admin", admin_panel))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("rate", rate_order))
        application.add_handler(CommandHandler("finish", master_finish_order))
        
        # Add master conversation
        add_master_conv = ConversationHandler(
            entry_points=[CommandHandler("add_master", add_master_start)],
            states={
                ADD_MASTER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_master_handler)],
                ADD_MASTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_master_handler)],
                ADD_MASTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_master_handler)],
                ADD_MASTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_master_handler)],
                ADD_MASTER_SERVICES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_master_handler)],
            },
            fallbacks=[CommandHandler("cancel", cancel_add_master)]
        )
        application.add_handler(add_master_conv)
        
        # Message handlers - Admin
        application.add_handler(MessageHandler(
            filters.Regex(r'^👤 Mijozlar bazasi$') & filters.User(ADMIN_ID),
            clients_list
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👨‍🔧 Ustalar$') & filters.User(ADMIN_ID),
            masters_list
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^➕ Usta qo\'shish$') & filters.User(ADMIN_ID),
            add_master_start
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📋 Barcha buyurtmalar$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            all_orders
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📊 Statistika$') & filters.User(ADMIN_ID),
            stats_command
        ))
        
        # Dispatcher handlers
        application.add_handler(MessageHandler(
            filters.Regex(r'^🆕 Yangi buyurtmalar$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            new_orders
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^🟡 Qabul qilish$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            accept_order
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^🚫 Rad etish$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            reject_order
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👨‍🔧 Usta tanlash$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            assign_master_order
        ))
        
        # Master handlers
        application.add_handler(MessageHandler(
            filters.Regex(r'^🟡 Buyurtmani qabul qilish$'),
            master_accept_order
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^🔵 Ishni boshlash$'),
            master_start_work
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^✅ Ishni yakunlash$'),
            master_finish_order
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📋 O\'z buyurtmalarim$'),
            master_my_orders
        ))
        
        # Client handlers
        application.add_handler(MessageHandler(
            filters.Regex(r'^📋 Mening buyurtmalarim$'),
            my_orders
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📝 Buyurtma berish$'),
            order_start
        ))
        
        # Navigation
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Asosiy menyu$'),
            back_to_main
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Admin menyu$'),
            admin_panel
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^ℹ️ Yordam$'),
            help_command
        ))
        
        # Callback
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # Unknown
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_unknown
        ))
        
        logger.info("🚀 Bot ishlayapti...")
        await application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

# =====================================================
# DISPATCHER FUNCTIONS
# =====================================================

async def accept_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_dispatcher(user_id) and not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "🟡 <b>BUYURTMA QABUL QILISH</b>\n\n"
        "Buyurtma raqamini yozing:",
        parse_mode="HTML"
    )
    context.user_data['accept_order'] = True

async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_dispatcher(user_id) and not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "🚫 <b>BUYURTMA RAD ETISH</b>\n\n"
        "Buyurtma raqamini yozing:",
        parse_mode="HTML"
    )
    context.user_data['reject_order'] = True

async def assign_master_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_dispatcher(user_id) and not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "👨‍🔧 <b>USTA TANLASH</b>\n\n"
        "Buyurtma raqamini yozing:",
        parse_mode="HTML"
    )
    context.user_data['assign_master'] = True

async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    await update.message.reply_text(
        "📝 <b>BUYURTMA BERISH</b>\n\n"
        "Qaysi xizmat bo'yicha buyurtma bermoqchisiz?\n"
        "Xizmat nomini yozing:",
        parse_mode="HTML"
    )
    return ORDER_SERVICE

# =====================================================
# HANDLE ORDERS WITH CONVERSATION
# =====================================================

async def order_service_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    service = update.message.text.strip()
    
    context.user_data['order'] = {'service': service}
    
    await update.message.reply_text(
        f"🛠 <b>Xizmat:</b> {service}\n\n"
        f"📝 Buyurtma tavsifini yozing:",
        parse_mode="HTML"
    )
    return ORDER_DESCRIPTION

async def order_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    description = update.message.text.strip()
    
    context.user_data['order']['description'] = description
    
    await update.message.reply_text(
        f"📝 <b>Tavsif:</b> {description[:100]}{'...' if len(description) > 100 else ''}\n\n"
        f"📍 Manzilingizni yozing:",
        parse_mode="HTML"
    )
    return ORDER_ADDRESS

async def order_address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    address = update.message.text.strip()
    
    context.user_data['order']['address'] = address
    
    # Client phone
    client = await db.get_client(user_id)
    phone = client['phone'] if client and client['phone'] else ""
    
    if not phone:
        await update.message.reply_text(
            "📞 Telefon raqamingizni yozing:",
            parse_mode="HTML"
        )
        return ORDER_CONFIRM
    
    context.user_data['order']['phone'] = phone
    
    data = context.user_data['order']
    
    await update.message.reply_text(
        f"✅ <b>BUYURTMA TAYYOR!</b>\n\n"
        f"🛠 Xizmat: {data['service']}\n"
        f"📝 Tavsif: {data['description']}\n"
        f"📍 Manzil: {data['address']}\n"
        f"📞 Telefon: {phone}\n\n"
        f"📌 Buyurtmani tasdiqlash uchun 'Ha' yoki 'Yo'q' deb yozing:",
        parse_mode="HTML"
    )
    return ORDER_CONFIRM

async def order_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    
    if text in ['yo\'q', 'no', 'нет']:
        context.user_data.pop('order', None)
        await update.message.reply_text(
            "❌ Buyurtma bekor qilindi!",
            reply_markup=main_menu()
        )
        return ConversationHandler.END
    
    if text not in ['ha', 'yes', 'да', 'ҳа']:
        await update.message.reply_text(
            "❌ 'Ha' yoki 'Yo'q' deb yozing!"
        )
        return ORDER_CONFIRM
    
    data = context.user_data['order']
    
    order_id = await db.add_order(
        client_id=user_id,
        service=data['service'],
        description=data['description'],
        address=data['address'],
        client_phone=data.get('phone', '')
    )
    
    context.user_data.pop('order', None)
    
    await update.message.reply_text(
        f"✅ <b>BUYURTMA QABUL QILINDI!</b>\n\n"
        f"📋 №{order_id}\n"
        f"🛠 {data['service']}\n"
        f"📍 {data['address']}\n\n"
        f"🔄 Hozir usta tayinlanadi. Yaqinda siz bilan bog'lanishadi!",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    
    # Dispetcherlarga xabar
    for dispatcher in DISPATCHER_IDS:
        try:
            await context.bot.send_message(
                dispatcher,
                f"🆕 <b>YANGI BUYURTMA!</b>\n\n"
                f"📋 №{order_id}\n"
                f"👤 Mijoz: {update.effective_user.first_name}\n"
                f"🛠 Xizmat: {data['service']}\n"
                f"📍 Manzil: {data['address']}\n\n"
                f"🔽 Usta tayinlang!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👨‍🔧 Usta tayinlash", callback_data=f"assign_{order_id}")]
                ])
            )
        except:
            pass
    
    return ConversationHandler.END

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('order', None)
    await update.message.reply_text(
        "❌ Buyurtma bekor qilindi.",
        reply_markup=main_menu()
    )
    return ConversationHandler.END

# =====================================================
# RUN BOT
# =====================================================

if __name__ == "__main__":
    asyncio.run(main())
