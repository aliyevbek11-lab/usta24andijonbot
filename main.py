#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================
USTA 24 PRO BOT - TO'LIQ VERSION
=============================================
"""

import asyncio
import logging
import json
import random
import re
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

# =====================================================
# TELEGRAM KUTUBXONASI - TO'G'RI VERSION
# =====================================================

# python-telegram-bot v20+ uchun
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery,
    Message,
    User,
    ReplyKeyboardRemove
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

# Agar yuqoridagi ishlamasa, quyidagi eski versiyani sinab ko'ring:
# from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
# from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, Filters

# SQLite uchun
import aiosqlite

# =====================================================
# KONFIGURATSIYA
# =====================================================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789  # Сизнинг Telegram ID
DISPATCHER_IDS = [123456789]  # Диспетчерлар ID

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

# Уста қўшиш
ADD_MASTER_ID, ADD_MASTER_NAME, ADD_MASTER_PHONE, ADD_MASTER_USERNAME, ADD_MASTER_SERVICES = range(5)

# Устани ўзгартириш
EDIT_MASTER_ID, EDIT_MASTER_FIELD, EDIT_MASTER_VALUE = range(5, 8)

# Буюртма бериш
ORDER_SERVICE, ORDER_DESCRIPTION, ORDER_ADDRESS, ORDER_SCHEDULE, ORDER_CONFIRM = range(8, 13)

# Буюртмани қидириш
SEARCH_ORDER_ID = 13

# Баҳо бериш
RATING_ORDER_ID, RATING_VALUE = range(14, 16)

# =====================================================
# DATABASE CLASS
# =====================================================

class Database:
    def __init__(self, db_name="usta24.db"):
        self.db_name = db_name

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            # Усталар
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

            # Мижозлар
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

            # Буюртмалар
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

            # Буюртма тарихи
            await db.execute("""
                CREATE TABLE IF NOT EXISTS order_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    action TEXT,
                    user_id INTEGER,
                    user_type TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id)
                )
            """)

            # Баҳолар
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

            # Тўловлар
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    amount REAL,
                    payment_type TEXT,
                    status TEXT DEFAULT 'kutilmoqda',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id)
                )
            """)

            await db.commit()
            logger.info("База яратилди")

    # ========== УСТАЛАР ==========
    async def add_master(self, master_id: int, name: str, phone: str = "", 
                         username: str = "", services: str = "") -> bool:
        async with aiosqlite.connect(self.db_name) as db:
            try:
                await db.execute("""
                    INSERT OR REPLACE INTO masters (id, name, phone, username, services)
                    VALUES (?, ?, ?, ?, ?)
                """, (master_id, name, phone, username, services))
                await db.commit()
                return True
            except Exception as e:
                logger.error(f"Уста қўшишда хатолик: {e}")
                return False

    async def get_master(self, master_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM masters WHERE id = ?",
                (master_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'phone': row[2],
                    'username': row[3],
                    'services': row[4],
                    'rating': row[5],
                    'orders_count': row[6],
                    'completed_orders': row[7],
                    'balance': row[8],
                    'status': row[9],
                    'blocked': row[10],
                    'block_reason': row[11],
                    'created_at': row[12],
                    'updated_at': row[13]
                }
            return None

    async def get_all_masters(self, active_only: bool = True) -> List[Dict]:
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
                    'id': row[0],
                    'name': row[1],
                    'phone': row[2],
                    'username': row[3],
                    'services': row[4],
                    'rating': row[5],
                    'orders_count': row[6],
                    'completed_orders': row[7],
                    'balance': row[8],
                    'status': row[9],
                    'blocked': row[10],
                    'block_reason': row[11],
                    'created_at': row[12],
                    'updated_at': row[13]
                })
            return masters

    async def get_available_masters(self) -> List[Dict]:
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
                    'id': row[0],
                    'name': row[1],
                    'phone': row[2],
                    'username': row[3],
                    'services': row[4],
                    'rating': row[5],
                    'orders_count': row[6],
                    'status': row[9]
                })
            return masters

    async def update_master(self, master_id: int, **kwargs):
        async with aiosqlite.connect(self.db_name) as db:
            fields = []
            values = []
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            values.append(master_id)
            
            await db.execute(f"""
                UPDATE masters 
                SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            await db.commit()

    async def block_master(self, master_id: int, reason: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE masters 
                SET blocked = TRUE, block_reason = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (reason, master_id))
            await db.commit()

    async def unblock_master(self, master_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE masters 
                SET blocked = FALSE, block_reason = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (master_id,))
            await db.commit()

    async def update_master_status(self, master_id: int, status: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE masters 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, master_id))
            await db.commit()

    async def delete_master(self, master_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("UPDATE masters SET blocked = TRUE WHERE id = ?", (master_id,))
            await db.commit()

    # ========== МИЖОЗЛАР ==========
    async def add_client(self, client_id: int, name: str, phone: str = "", 
                         username: str = "", address: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            try:
                await db.execute("""
                    INSERT OR REPLACE INTO clients (id, name, phone, username, address, last_active)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (client_id, name, phone, username, address))
                await db.commit()
                return True
            except Exception as e:
                logger.error(f"Мижоз қўшишда хатолик: {e}")
                return False

    async def get_client(self, client_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM clients WHERE id = ?",
                (client_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'phone': row[2],
                    'username': row[3],
                    'address': row[4],
                    'orders_count': row[5],
                    'total_spent': row[6],
                    'created_at': row[7],
                    'last_active': row[8]
                }
            return None

    async def get_all_clients(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM clients ORDER BY orders_count DESC"
            )
            rows = await cursor.fetchall()
            
            clients = []
            for row in rows:
                clients.append({
                    'id': row[0],
                    'name': row[1],
                    'phone': row[2],
                    'username': row[3],
                    'address': row[4],
                    'orders_count': row[5],
                    'total_spent': row[6],
                    'created_at': row[7],
                    'last_active': row[8]
                })
            return clients

    # ========== БУЮРТМАЛАР ==========
    async def add_order(self, client_id: int, service: str, 
                        description: str = "", price: float = 0,
                        priority: str = "o'rta", address: str = "",
                        schedule: str = "", client_phone: str = "") -> int:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                INSERT INTO orders (client_id, service, description, 
                                   price, priority, address, schedule, client_phone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (client_id, service, description, price, priority, address, schedule, client_phone))
            await db.commit()
            order_id = cursor.lastrowid
            
            await db.execute(
                "UPDATE clients SET orders_count = orders_count + 1 WHERE id = ?",
                (client_id,)
            )
            await db.commit()
            
            return order_id

    async def get_order(self, order_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'client_id': row[1],
                    'master_id': row[2],
                    'service': row[3],
                    'description': row[4],
                    'price': row[5],
                    'status': row[6],
                    'priority': row[7],
                    'address': row[8],
                    'schedule': row[9],
                    'client_phone': row[10],
                    'created_at': row[11],
                    'updated_at': row[12],
                    'completed_at': row[13],
                    'cancelled_at': row[14],
                    'cancel_reason': row[15]
                }
            return None

    async def get_orders(self, user_id: int, user_type: str = 'client') -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            field = 'client_id' if user_type == 'client' else 'master_id'
            query = f"SELECT * FROM orders WHERE {field} = ? ORDER BY created_at DESC"
            
            cursor = await db.execute(query, (user_id,))
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                orders.append({
                    'id': row[0],
                    'client_id': row[1],
                    'master_id': row[2],
                    'service': row[3],
                    'description': row[4],
                    'price': row[5],
                    'status': row[6],
                    'priority': row[7],
                    'address': row[8],
                    'schedule': row[9],
                    'client_phone': row[10],
                    'created_at': row[11],
                    'updated_at': row[12]
                })
            return orders

    async def get_all_orders(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                orders.append({
                    'id': row[0],
                    'client_id': row[1],
                    'master_id': row[2],
                    'service': row[3],
                    'description': row[4],
                    'price': row[5],
                    'status': row[6],
                    'priority': row[7],
                    'address': row[8],
                    'schedule': row[9],
                    'client_phone': row[10],
                    'created_at': row[11],
                    'updated_at': row[12]
                })
            return orders

    async def get_new_orders(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM orders WHERE status = 'yangi' ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                orders.append({
                    'id': row[0],
                    'client_id': row[1],
                    'master_id': row[2],
                    'service': row[3],
                    'description': row[4],
                    'price': row[5],
                    'status': row[6],
                    'priority': row[7],
                    'address': row[8],
                    'schedule': row[9],
                    'client_phone': row[10],
                    'created_at': row[11],
                    'updated_at': row[12]
                })
            return orders

    async def update_order_status(self, order_id: int, status: str, 
                                  reason: str = "", user_id: int = None, 
                                  user_type: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE orders 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, order_id))
            await db.commit()

    async def assign_master(self, order_id: int, master_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE orders 
                SET master_id = ?, status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (master_id, order_id))
            await db.commit()

    async def search_orders(self, query: str) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM orders 
                WHERE id = ? OR service LIKE ? OR description LIKE ? OR address LIKE ?
            """, (query if query.isdigit() else -1, f"%{query}%", f"%{query}%", f"%{query}%"))
            rows = await cursor.fetchall()
            
            orders = []
            for row in rows:
                orders.append({
                    'id': row[0],
                    'client_id': row[1],
                    'master_id': row[2],
                    'service': row[3],
                    'description': row[4],
                    'price': row[5],
                    'status': row[6],
                    'priority': row[7],
                    'address': row[8],
                    'schedule': row[9],
                    'client_phone': row[10],
                    'created_at': row[11],
                    'updated_at': row[12]
                })
            return orders

    # ========== БАҲОЛАР ==========
    async def add_rating(self, order_id: int, master_id: int, 
                         client_id: int, rating: int, comment: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO ratings (order_id, master_id, client_id, rating, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, master_id, client_id, rating, comment))
            await db.commit()

    async def get_master_rating(self, master_id: int) -> Dict:
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

    # ========== СТАТИСТИКА ==========
    async def get_stats(self) -> Dict:
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

    async def get_daily_stats(self) -> Dict:
        async with aiosqlite.connect(self.db_name) as db:
            today = datetime.now().date().isoformat()
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?",
                (today,)
            )
            today_orders = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(completed_at) = ? AND status = 'yakunlangan'",
                (today,)
            )
            today_completed = await cursor.fetchone()
            
            return {
                'today_orders': today_orders[0],
                'today_completed': today_completed[0]
            }

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
            ["🛠 Хизматлар", "👨‍🔧 Усталар"],
            ["📝 Буюртма бериш", "📋 Менинг буюртмаларим"],
            ["👤 Шахсий маълумот", "ℹ️ Ёрдам"],
            ["👑 Админ панели"]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Мижозлар базаси", "👨‍🔧 Усталар"],
            ["➕ Уста қўшиш", "✏️ Устани ўзгартириш"],
            ["🗑 Устани ўчириш", "🟢 Уста ҳолати"],
            ["🚫 Устани блоклаш", "🔓 Устани фаоллаштириш"],
            ["📋 Барча буюртмалар", "🔎 Буюртма қидириш"],
            ["📊 Статистика", "📈 Ҳисобот"],
            ["📢 Мижозларга хабар", "📢 Усталарга хабар"],
            ["👨‍💼 Диспетчер", "⬅️ Асосий меню"]
        ],
        resize_keyboard=True
    )

def dispatcher_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Янги буюртмалар"],
            ["🟡 Қабул қилиш", "🚫 Рад этиш"],
            ["👨‍🔧 Уста танлаш"],
            ["🔄 Бошқа устага бериш"],
            ["📞 Мижоз билан боғланиш"],
            ["📍 Манзилни кўриш"],
            ["📋 Буюртмалар тарихи"],
            ["🔎 Буюртма қидириш"],
            ["📊 Кунлик статистика"],
            ["⬅️ Админ меню"]
        ],
        resize_keyboard=True
    )

def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🟡 Буюртмани қабул қилиш"],
            ["🚫 Буюртмани рад этиш"],
            ["🔵 Ишни бошлаш"],
            ["📞 Мижоз билан боғланиш"],
            ["📍 Манзил", "🔄 Бошқа устага бериш"],
            ["❌ Буюртмани бекор қилиш"],
            ["✅ Ишни якунлаш"],
            ["⭐ Мижоз баҳоси"],
            ["📋 Ўз буюртмаларим"],
            ["⬅️ Асосий меню"]
        ],
        resize_keyboard=True
    )

def client_menu():
    return ReplyKeyboardMarkup(
        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["🔁 Қайта буюртма"],
            ["📦 Буюртма ҳолати"],
            ["📞 Уста билан боғланиш"],
            ["❌ Буюртмани бекор қилиш"],
            ["⬅️ Асосий меню"]
        ],
        resize_keyboard=True
    )

def services_menu():
    return ReplyKeyboardMarkup(
        [
            ["🏠 Мебель", "🔧 Сантехника"],
            ["⚡ Электр", "❄️ Кондиционер"],
            ["🪚 Дурадгорлик", "🎨 Бўёқчилик"],
            ["🔨 Қурилиш", "🚿 Плитка"],
            ["🔩 Металл", "🪟 Ойна"],
            ["📦 Юк ташиш", "🔊 Овоз"],
            ["⬅️ Орқага"]
        ],
        resize_keyboard=True
    )

def order_status_keyboard(order_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Янги", callback_data=f"os_{order_id}_yangi"),
            InlineKeyboardButton("🟡 Қабул", callback_data=f"os_{order_id}_qabul_qilingan")
        ],
        [
            InlineKeyboardButton("🔵 Жараёнда", callback_data=f"os_{order_id}_jarayonda"),
            InlineKeyboardButton("🔍 Текширувда", callback_data=f"os_{order_id}_tekshiruvda")
        ],
        [
            InlineKeyboardButton("✅ Бажарилди", callback_data=f"os_{order_id}_bajarildi"),
            InlineKeyboardButton("⭐ Якунланди", callback_data=f"os_{order_id}_yakunlangan")
        ],
        [
            InlineKeyboardButton("❌ Бекор қилиш", callback_data=f"os_{order_id}_bekor_qilindi"),
            InlineKeyboardButton("🚫 Рад этиш", callback_data=f"os_{order_id}_rad_etilgan")
        ],
        [
            InlineKeyboardButton("👨‍🔧 Уста танлаш", callback_data=f"assign_{order_id}")
        ]
    ])

def rating_keyboard(order_id: int, master_id: int):
    buttons = []
    for i in range(1, 6):
        buttons.append([
            InlineKeyboardButton(
                f"{'⭐' * i} {i}",
                callback_data=f"rate_{order_id}_{master_id}_{i}"
            )
        ])
    return InlineKeyboardMarkup(buttons)

def master_select_keyboard(order_id: int, masters: List[Dict]):
    keyboard = []
    for master in masters[:10]:
        status_emoji = "🟢" if master['status'] == 'free' else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} {master['name']} ⭐{master['rating']}",
                callback_data=f"ms_{order_id}_{master['id']}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Орқага", callback_data=f"back_{order_id}")
    ])
    return InlineKeyboardMarkup(keyboard)

# =====================================================
# YORDAMCHI FUNKSIYALAR
# =====================================================

def get_status_emoji(status: str) -> str:
    emojis = {
        'yangi': '🆕',
        'qabul_qilingan': '🟡',
        'jarayonda': '🔵',
        'tekshiruvda': '🔍',
        'bajarildi': '✅',
        'yakunlangan': '⭐',
        'bekor_qilindi': '❌',
        'rad_etilgan': '🚫'
    }
    return emojis.get(status, '📋')

def get_status_text(status: str) -> str:
    texts = {
        'yangi': 'Янги',
        'qabul_qilingan': 'Қабул қилинган',
        'jarayonda': 'Жараёнда',
        'tekshiruvda': 'Текширувда',
        'bajarildi': 'Бажарилди',
        'yakunlangan': 'Якунланган',
        'bekor_qilindi': 'Бекор қилинган',
        'rad_etilgan': 'Рад этилган'
    }
    return texts.get(status, status)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_dispatcher(user_id: int) -> bool:
    return user_id in DISPATCHER_IDS

# =====================================================
# MAIN FUNCTION
# =====================================================

async def main():
    try:
        # Базани ишга тушириш
        await db.init_db()
        logger.info("База ишга тушди")
        
        # Application
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        logger.info("Application яратилди")
        
        # Commands
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("admin", admin_panel))
        
        # Message handlers
        application.add_handler(MessageHandler(
            filters.Regex(r'^👤 Мижозлар базаси$') & filters.User(ADMIN_ID),
            clients_list
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👨‍🔧 Усталар$') & filters.User(ADMIN_ID),
            masters_list
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^➕ Уста қўшиш$') & filters.User(ADMIN_ID),
            add_master_start
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📋 Барча буюртмалар$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            all_orders
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📊 Статистика$') & filters.User(ADMIN_ID),
            stats_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📈 Ҳисобот$') & filters.User(ADMIN_ID),
            report_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^🆕 Янги буюртмалар$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            new_orders
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Асосий меню$'),
            back_to_main
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Админ меню$'),
            admin_panel
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^ℹ️ Ёрдам$'),
            help_command
        ))
        
        # Callback
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # Unknown
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_unknown
        ))
        
        # Поллингни бошлаш
        logger.info("Bot ishlayapti...")
        await application.run_polling()
        
    except Exception as e:
        logger.error(f"Bot ishga tushirishda xatolik: {e}")

# =====================================================
# COMMAND HANDLERS
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    await db.init_db()
    
    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"🏠 <b>USTA 24 PRO</b> ботига хуш келибсиз!\n\n"
        f"🛠 Мен сизга турли хизматларни топишга ёрдам бераман.",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>YORDAM</b>\n\n"
        "🛠 Хизматлар - Барча хизматлар\n"
        "👨‍🔧 Усталар - Усталар рўйхати\n"
        "📝 Буюртма бериш - Янги буюртма\n"
        "📋 Менинг буюртмаларим - Буюртма тарихи\n"
        "👤 Шахсий маълумот - Профиль\n\n"
        "👑 Админлар учун махсус панел",
        parse_mode="HTML"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Сиз админ эмассиз!")
        return
    
    await update.message.reply_text(
        "👑 <b>ADMIN PANEL</b>",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    stats = await db.get_stats()
    
    text = f"📊 <b>STATISTIKA</b>\n\n"
    text += f"👨‍🔧 Усталар: {stats['masters']}\n"
    text += f"   🟢 Бўш: {stats['free_masters']}\n"
    text += f"   🔴 Банд: {stats['busy_masters']}\n"
    text += f"👤 Мижозлар: {stats['clients']}\n"
    text += f"📋 Буюртмалар: {stats['orders']}\n"
    text += f"📅 Бугун: {stats['today_orders']}"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    stats = await db.get_stats()
    daily = await db.get_daily_stats()
    
    text = f"📈 <b>HISOBOT</b>\n\n"
    text += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    text += f"👨‍🔧 Усталар: {stats['masters']}\n"
    text += f"👤 Мижозлар: {stats['clients']}\n"
    text += f"📋 Буюртмалар: {stats['orders']}\n"
    text += f"📅 Бугун: {daily['today_orders']}\n"
    text += f"✅ Якунланган: {daily['today_completed']}"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def masters_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    masters = await db.get_all_masters()
    if not masters:
        await update.message.reply_text("👨‍🔧 Ҳозирча усталар йўқ.")
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
        await update.message.reply_text("👤 Мижозлар йўқ.")
        return
    
    text = "👤 <b>MIJOZLAR</b>\n\n"
    for client in clients[:10]:
        text += (
            f"👤 {client['name']}\n"
            f"📞 {client['phone'] or 'йўқ'}\n"
            f"📋 {client['orders_count']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = await db.get_all_orders()
    
    if not orders:
        await update.message.reply_text("📋 Ҳозирча буюртмалар йўқ.")
        return
    
    text = "📋 <b>BARCHA BUYURTMALAR</b>\n\n"
    for order in orders[:10]:
        client = await db.get_client(order['client_id'])
        text += (
            f"№{order['id']} {get_status_emoji(order['status'])}\n"
            f"👤 {client['name'] if client else 'Мижоз'}\n"
            f"🛠 {order['service']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = await db.get_new_orders()
    
    if not orders:
        await update.message.reply_text("🆕 Ҳозирча янги буюртмалар йўқ.")
        return
    
    text = "🆕 <b>YANGI BUYURTMALAR</b>\n\n"
    for order in orders[:10]:
        client = await db.get_client(order['client_id'])
        text += (
            f"№{order['id']}\n"
            f"👤 {client['name'] if client else 'Мижоз'}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address'] or 'йўқ'}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

async def add_master_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "➕ <b>USTA QO'SHISH</b>\n\n"
        "1️⃣ Устанинг Telegram ID рақамини юборинг.",
        parse_mode="HTML"
    )
    return ADD_MASTER_ID

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_admin(user_id):
        await admin_panel(update, context)
    else:
        await update.message.reply_text(
            "🏠 Бош меню",
            reply_markup=main_menu()
        )

# =====================================================
# CALLBACK HANDLER
# =====================================================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("os_"):
        parts = data.split("_")
        if len(parts) == 3:
            order_id = int(parts[1])
            status = parts[2]
            
            await db.update_order_status(order_id, status)
            await query.edit_text(f"✅ Буюртма №{order_id} статуси ўзгартирилди!")
            return
    
    if data.startswith("accept_"):
        order_id = int(data.split("_")[1])
        await db.update_order_status(order_id, 'qabul_qilingan')
        await query.edit_text(f"✅ Буюртма №{order_id} қабул қилинди!")
        return
    
    if data.startswith("reject_"):
        order_id = int(data.split("_")[1])
        await db.update_order_status(order_id, 'rad_etilgan')
        await query.edit_text(f"🚫 Буюртма №{order_id} рад этилди!")
        return
    
    if data.startswith("assign_"):
        order_id = int(data.split("_")[1])
        masters = await db.get_available_masters()
        if not masters:
            await query.edit_text("❌ Бўш усталар йўқ!")
            return
        
        await query.edit_text(
            f"👨‍🔧 Буюртма №{order_id} учун уста танланг:",
            reply_markup=master_select_keyboard(order_id, masters)
        )
        return
    
    if data.startswith("ms_"):
        parts = data.split("_")
        order_id = int(parts[1])
        master_id = int(parts[2])
        
        await db.assign_master(order_id, master_id)
        await query.edit_text(f"✅ Буюртма №{order_id} га уста тайинланди!")
        return

# =====================================================
# UNKNOWN HANDLER
# =====================================================

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Тушунмадим. Илтимос, тугмалардан фойдаланинг!\n"
        "📖 Ёрдам олиш учун /help",
        reply_markup=main_menu()
    )

# =====================================================
# RUN BOT
# =====================================================

if __name__ == "__main__":
    asyncio.run(main())
