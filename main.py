#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================
USTA 24 PRO BOT - MEGA FULL VERSION
=============================================
Барча вазифалар билан тўлиқ бот
=============================================
"""

import asyncio
import logging
import json
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    PicklePersistence
)
import aiosqlite
import os

# =====================================================
# KONFIGURATSIYA
# =====================================================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789
DISPATCHER_IDS = [123456789, 987654321]  # Диспетчерлар ID

# Логгинг
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

# Хабар тарқатиш
BROADCAST_MESSAGE = 14

# Устани блоклаш
BLOCK_MASTER_ID = 15

# Баҳо бериш
RATING_VALUE = 16

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

            # Хабарлар
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    message TEXT,
                    recipients INTEGER,
                    user_type TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Ҳисоботлар
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        """Бўш усталар"""
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
        """status: 'free' yoki 'busy'"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE masters 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, master_id))
            await db.commit()

    async def search_masters(self, query: str) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM masters 
                WHERE blocked = FALSE AND (
                    name LIKE ? OR 
                    services LIKE ? OR 
                    phone LIKE ? OR 
                    username LIKE ?
                )
                ORDER BY rating DESC
            """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
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

    async def update_client(self, client_id: int, **kwargs):
        async with aiosqlite.connect(self.db_name) as db:
            fields = []
            values = []
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            values.append(client_id)
            
            await db.execute(f"""
                UPDATE clients 
                SET {', '.join(fields)}, last_active = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            await db.commit()

    async def get_client_by_phone(self, phone: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM clients WHERE phone = ?",
                (phone,)
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
                    'total_spent': row[6]
                }
            return None

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
            
            # Мижознинг буюртмалар сонини ошириш
            await db.execute(
                "UPDATE clients SET orders_count = orders_count + 1 WHERE id = ?",
                (client_id,)
            )
            await db.commit()
            
            # Тарихга ёзиш
            await self.add_order_history(order_id, "created", client_id, "client", "Буюртма яратилди")
            
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

    async def get_orders(self, user_id: int, user_type: str = 'client', 
                         status: str = None) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            field = 'client_id' if user_type == 'client' else 'master_id'
            query = f"SELECT * FROM orders WHERE {field} = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            
            cursor = await db.execute(query, params)
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
                    'updated_at': row[12],
                    'completed_at': row[13],
                    'cancelled_at': row[14],
                    'cancel_reason': row[15]
                })
            return orders

    async def get_all_orders(self, status: str = None) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            query = "SELECT * FROM orders"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            
            cursor = await db.execute(query, params)
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
                    'updated_at': row[12],
                    'completed_at': row[13],
                    'cancelled_at': row[14],
                    'cancel_reason': row[15]
                })
            return orders

    async def get_new_orders(self) -> List[Dict]:
        """Янги буюртмалар"""
        return await self.get_all_orders(status='yangi')

    async def update_order_status(self, order_id: int, status: str, 
                                  reason: str = "", user_id: int = None, 
                                  user_type: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            updates = {
                'yangi': "status = 'yangi', updated_at = CURRENT_TIMESTAMP",
                'qabul_qilingan': "status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP",
                'rad_etilgan': "status = 'rad_etilgan', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP",
                'jarayonda': "status = 'jarayonda', updated_at = CURRENT_TIMESTAMP",
                'bajarildi': "status = 'bajarildi', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                'yakunlangan': "status = 'yakunlangan', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                'bekor_qilindi': f"status = 'bekor_qilindi', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP, cancel_reason = '{reason}'",
                'tekshiruvda': "status = 'tekshiruvda', updated_at = CURRENT_TIMESTAMP"
            }
            
            if status in updates:
                await db.execute(f"""
                    UPDATE orders SET {updates[status]}
                    WHERE id = ?
                """, (order_id,))
                await db.commit()
                
                # Тарихга ёзиш
                action_map = {
                    'qabul_qilingan': 'accepted',
                    'rad_etilgan': 'rejected',
                    'jarayonda': 'started',
                    'bajarildi': 'completed',
                    'yakunlangan': 'finalized',
                    'bekor_qilindi': 'cancelled',
                    'tekshiruvda': 'under_review'
                }
                action = action_map.get(status, status)
                await self.add_order_history(order_id, action, user_id or 0, user_type or 'system', reason or status)

    async def assign_master(self, order_id: int, master_id: int, user_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE orders 
                SET master_id = ?, status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (master_id, order_id))
            await db.commit()
            
            # Устани банд қилиш
            await self.update_master_status(master_id, 'busy')
            
            # Тарихга ёзиш
            await self.add_order_history(order_id, 'assigned', user_id or 0, 'admin', f"Уста ID: {master_id}")

    async def reassign_master(self, order_id: int, new_master_id: int, user_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            # Эски устани бўшатиш
            order = await self.get_order(order_id)
            if order and order['master_id']:
                await self.update_master_status(order['master_id'], 'free')
            
            # Янги устани тайинлаш
            await db.execute("""
                UPDATE orders 
                SET master_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_master_id, order_id))
            await db.commit()
            
            await self.update_master_status(new_master_id, 'busy')
            await self.add_order_history(order_id, 'reassigned', user_id or 0, 'admin', f"Янги уста ID: {new_master_id}")

    async def get_order_by_id(self, order_id: int) -> Optional[Dict]:
        return await self.get_order(order_id)

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

    # ========== БУЮРТМА ТАРИХИ ==========
    async def add_order_history(self, order_id: int, action: str, 
                                user_id: int, user_type: str, 
                                description: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO order_history (order_id, action, user_id, user_type, description)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, action, user_id, user_type, description))
            await db.commit()

    async def get_order_history(self, order_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM order_history 
                WHERE order_id = ? 
                ORDER BY created_at ASC
            """, (order_id,))
            rows = await cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'order_id': row[1],
                    'action': row[2],
                    'user_id': row[3],
                    'user_type': row[4],
                    'description': row[5],
                    'created_at': row[6]
                })
            return history

    # ========== БАҲОЛАР ==========
    async def add_rating(self, order_id: int, master_id: int, 
                         client_id: int, rating: int, comment: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO ratings (order_id, master_id, client_id, rating, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, master_id, client_id, rating, comment))
            await db.commit()
            
            # Устанинг ўртача рейтингини ҳисоблаш
            cursor = await db.execute(
                "SELECT AVG(rating) FROM ratings WHERE master_id = ?",
                (master_id,)
            )
            avg_rating = await cursor.fetchone()
            if avg_rating and avg_rating[0]:
                await db.execute(
                    "UPDATE masters SET rating = ? WHERE id = ?",
                    (round(avg_rating[0], 1), master_id)
                )
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
            # Умумий статистика
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
            
            # Статуслар бўйича
            status_stats = {}
            for status in ['yangi', 'qabul_qilingan', 'jarayonda', 'tekshiruvda', 'bajarildi', 'yakunlangan', 'bekor_qilindi', 'rad_etilgan']:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE status = ?",
                    (status,)
                )
                count = await cursor.fetchone()
                status_stats[status] = count[0]
            
            # Бугунги
            today = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"
            )
            today = await today.fetchone()
            
            # Тўловлар
            payments = await db.execute(
                "SELECT SUM(amount) FROM payments WHERE status = 'tugallandi'"
            )
            total_income = await payments.fetchone()
            
            # Ўртача баҳо
            avg_rating = await db.execute("SELECT AVG(rating) FROM ratings")
            avg_rating = await avg_rating.fetchone()
            
            return {
                'masters': masters_count[0],
                'free_masters': free_masters[0],
                'busy_masters': busy_masters[0],
                'clients': clients_count[0],
                'orders': orders_count[0],
                'today_orders': today[0],
                'statuses': status_stats,
                'total_income': total_income[0] or 0,
                'avg_rating': round(avg_rating[0] or 0, 1)
            }

    async def get_daily_stats(self) -> Dict:
        """Кунлик статистика"""
        async with aiosqlite.connect(self.db_name) as db:
            today = datetime.now().date()
            today_str = today.isoformat()
            
            # Бугунги буюртмалар
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?",
                (today_str,)
            )
            today_orders = await cursor.fetchone()
            
            # Бугунги якунланганлар
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(completed_at) = ? AND status = 'yakunlangan'",
                (today_str,)
            )
            today_completed = await cursor.fetchone()
            
            # Бугунги даромад
            cursor = await db.execute(
                "SELECT SUM(amount) FROM payments WHERE DATE(created_at) = ? AND status = 'tugallandi'",
                (today_str,)
            )
            today_income = await cursor.fetchone()
            
            return {
                'today_orders': today_orders[0],
                'today_completed': today_completed[0],
                'today_income': today_income[0] or 0
            }

    async def get_master_stats(self, master_id: int) -> Dict:
        """Уста статистикаси"""
        async with aiosqlite.connect(self.db_name) as db:
            master = await self.get_master(master_id)
            if not master:
                return {}
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status = 'yakunlangan'",
                (master_id,)
            )
            completed = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status IN ('yangi', 'qabul_qilingan', 'jarayonda')",
                (master_id,)
            )
            active = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT AVG(rating) FROM ratings WHERE master_id = ?",
                (master_id,)
            )
            avg_rating = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT SUM(price) FROM orders WHERE master_id = ? AND status = 'yakunlangan'",
                (master_id,)
            )
            total_earned = await cursor.fetchone()
            
            return {
                'total_orders': master['orders_count'],
                'completed_orders': completed[0],
                'active_orders': active[0],
                'rating': avg_rating[0] or 0,
                'total_earned': total_earned[0] or 0
            }

db = Database()

# =====================================================
# KEYBOARDS
# =====================================================

def main_menu():
    """Асосий меню"""
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
    """Админ менюси"""
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
    """Диспетчер менюси"""
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
    """Уста менюси"""
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
    """Мижоз менюси"""
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
    """Хизматлар менюси"""
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
    """Буюртма статусини ўзгартириш"""
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
    """Баҳо бериш"""
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
    """Уста танлаш"""
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
# BOSHQA YORDAMCHI FUNKSIYALAR
# =====================================================

def get_status_emoji(status: str) -> str:
    """Статус эмоджиси"""
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
    """Статус матни"""
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

def get_priority_emoji(priority: str) -> str:
    """Приоритет эмоджиси"""
    emojis = {
        'yuqori': '🔴',
        "o'rta": '🟡',
        'past': '🟢'
    }
    return emojis.get(priority, '⚪')

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_dispatcher(user_id: int) -> bool:
    return user_id in DISPATCHER_IDS

async def send_order_notification(context: ContextTypes.DEFAULT_TYPE, order_id: int):
    """Буюртма ҳақида хабарнома юбориш"""
    order = await db.get_order(order_id)
    if not order:
        return
    
    client = await db.get_client(order['client_id'])
    if not client:
        return
    
    # Диспетчерларга хабар
    for dispatcher_id in DISPATCHER_IDS:
        try:
            await context.bot.send_message(
                dispatcher_id,
                f"🆕 <b>ЯНГИ БУЮРТМА!</b>\n\n"
                f"📋 №{order_id}\n"
                f"🛠 Хизмат: {order['service']}\n"
                f"👤 Мижоз: {client['name']}\n"
                f"📞 Телефон: {client['phone'] or order['client_phone'] or 'йўқ'}\n"
                f"📍 Манзил: {order['address'] or 'кўрсатилмаган'}\n"
                f"📝 Изоҳ: {order['description'] or 'йўқ'}\n\n"
                f"📅 {order['created_at']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🟡 Қабул қилиш", callback_data=f"accept_{order_id}"),
                        InlineKeyboardButton("🚫 Рад этиш", callback_data=f"reject_{order_id}")
                    ],
                    [InlineKeyboardButton("👨‍🔧 Уста танлаш", callback_data=f"assign_{order_id}")]
                ])
            )
        except Exception as e:
            logger.error(f"Хабарнома юборишда хатолик: {e}")

# =====================================================
# START COMMAND
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Базани ишга тушириш
    await db.init_db()
    
    # Фойдаланувчини текшириш
    client = await db.get_client(user_id)
    if not client:
        await db.add_client(
            user_id,
            user.full_name,
            username=user.username or "",
            phone=""
        )
    
    # Админ
    if is_admin(user_id):
        stats = await db.get_stats()
        await update.message.reply_text(
            f"👑 <b>USTA 24 PRO</b>\n"
            f"Админ панелига хуш келибсиз!\n\n"
            f"📊 Статистика:\n"
            f"👨‍🔧 Усталар: {stats['masters']}\n"
            f"   🟢 Бўш: {stats['free_masters']}\n"
            f"   🔴 Банд: {stats['busy_masters']}\n"
            f"👤 Мижозлар: {stats['clients']}\n"
            f"📋 Буюртмалар: {stats['orders']}\n"
            f"📅 Бугун: {stats['today_orders']}\n"
            f"⭐ Ўртача рейтинг: {stats['avg_rating']}\n"
            f"💰 Умумий даромад: {stats['total_income']:,} сўм",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    # Диспетчер
    if is_dispatcher(user_id):
        await update.message.reply_text(
            f"👨‍💼 <b>Диспетчер панели</b>\n\n"
            f"Сизга хуш келибсиз!\n"
            f"Янги буюртмаларни кўриш учун:\n"
            f"🆕 Янги буюртмалар",
            reply_markup=dispatcher_menu(),
            parse_mode="HTML"
        )
        return
    
    # Уста
    master = await db.get_master(user_id)
    if master:
        status_text = "🟢 Ишда" if master['status'] == 'free' else "🔴 Банд"
        await update.message.reply_text(
            f"👨‍🔧 <b>Уста панели</b>\n\n"
            f"👤 {master['name']}\n"
            f"⭐ Рейтинг: {master['rating']}\n"
            f"📊 Ҳолат: {status_text}\n"
            f"📋 Буюртмалар: {master['orders_count']}\n"
            f"✅ Бажарган: {master['completed_orders']}\n\n"
            f"📋 Буюртмалар билан ишлаш учун менюдан фойдаланинг.",
            reply_markup=master_menu(),
            parse_mode="HTML"
        )
        return
    
    # Мижоз
    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"🏠 <b>USTA 24 PRO</b> ботига хуш келибсиз!\n\n"
        f"🛠 Мен сизга турли хизматларни топишга ёрдам бераман:\n\n"
        f"✅ Усталарни қидириш\n"
        f"✅ Буюртма бериш\n"
        f"✅ Буюртмаларни кузатиш\n"
        f"✅ Усталарни баҳолаш\n\n"
        f"🚀 Бошлаш учун тугмалардан фойдаланинг!",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

# =====================================================
# MAIN FUNCTION
# =====================================================

async def main():
    # Приложение яратиш
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Командаларни рўйхатга олиш
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # Бу ерга барча хэндлерлар қўшилади...
    # (Код жуда узун бўлгани учун давоми кейинги хабарда)
    
    # Поллингни бошлаш
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================
USTA 24 PRO BOT - MEGA FULL VERSION
=============================================
Барча вазифалар билан тўлиқ бот
=============================================
"""

import asyncio
import logging
import json
import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
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
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    PicklePersistence
)
import aiosqlite
import os

# =====================================================
# KONFIGURATSIYA
# =====================================================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = 123456789
DISPATCHER_IDS = [123456789, 987654321]  # Диспетчерлар ID

# Логгинг
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
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

# Хабар тарқатиш
BROADCAST_MESSAGE = 14

# Устани блоклаш
BLOCK_MASTER_ID = 15

# Баҳо бериш
RATING_VALUE = 16

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

            # Хабарлар
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    message TEXT,
                    recipients INTEGER,
                    user_type TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Ҳисоботлар
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_type TEXT,
                    data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        """Бўш усталар"""
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
        """status: 'free' yoki 'busy'"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE masters 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, master_id))
            await db.commit()

    async def search_masters(self, query: str) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM masters 
                WHERE blocked = FALSE AND (
                    name LIKE ? OR 
                    services LIKE ? OR 
                    phone LIKE ? OR 
                    username LIKE ?
                )
                ORDER BY rating DESC
            """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"))
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

    async def update_client(self, client_id: int, **kwargs):
        async with aiosqlite.connect(self.db_name) as db:
            fields = []
            values = []
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            values.append(client_id)
            
            await db.execute(f"""
                UPDATE clients 
                SET {', '.join(fields)}, last_active = CURRENT_TIMESTAMP
                WHERE id = ?
            """, values)
            await db.commit()

    async def get_client_by_phone(self, phone: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT * FROM clients WHERE phone = ?",
                (phone,)
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
                    'total_spent': row[6]
                }
            return None

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
            
            # Мижознинг буюртмалар сонини ошириш
            await db.execute(
                "UPDATE clients SET orders_count = orders_count + 1 WHERE id = ?",
                (client_id,)
            )
            await db.commit()
            
            # Тарихга ёзиш
            await self.add_order_history(order_id, "created", client_id, "client", "Буюртма яратилди")
            
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

    async def get_orders(self, user_id: int, user_type: str = 'client', 
                         status: str = None) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            field = 'client_id' if user_type == 'client' else 'master_id'
            query = f"SELECT * FROM orders WHERE {field} = ?"
            params = [user_id]
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            
            cursor = await db.execute(query, params)
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
                    'updated_at': row[12],
                    'completed_at': row[13],
                    'cancelled_at': row[14],
                    'cancel_reason': row[15]
                })
            return orders

    async def get_all_orders(self, status: str = None) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            query = "SELECT * FROM orders"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            
            cursor = await db.execute(query, params)
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
                    'updated_at': row[12],
                    'completed_at': row[13],
                    'cancelled_at': row[14],
                    'cancel_reason': row[15]
                })
            return orders

    async def get_new_orders(self) -> List[Dict]:
        """Янги буюртмалар"""
        return await self.get_all_orders(status='yangi')

    async def update_order_status(self, order_id: int, status: str, 
                                  reason: str = "", user_id: int = None, 
                                  user_type: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            updates = {
                'yangi': "status = 'yangi', updated_at = CURRENT_TIMESTAMP",
                'qabul_qilingan': "status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP",
                'rad_etilgan': "status = 'rad_etilgan', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP",
                'jarayonda': "status = 'jarayonda', updated_at = CURRENT_TIMESTAMP",
                'bajarildi': "status = 'bajarildi', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                'yakunlangan': "status = 'yakunlangan', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                'bekor_qilindi': f"status = 'bekor_qilindi', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP, cancel_reason = '{reason}'",
                'tekshiruvda': "status = 'tekshiruvda', updated_at = CURRENT_TIMESTAMP"
            }
            
            if status in updates:
                await db.execute(f"""
                    UPDATE orders SET {updates[status]}
                    WHERE id = ?
                """, (order_id,))
                await db.commit()
                
                # Тарихга ёзиш
                action_map = {
                    'qabul_qilingan': 'accepted',
                    'rad_etilgan': 'rejected',
                    'jarayonda': 'started',
                    'bajarildi': 'completed',
                    'yakunlangan': 'finalized',
                    'bekor_qilindi': 'cancelled',
                    'tekshiruvda': 'under_review'
                }
                action = action_map.get(status, status)
                await self.add_order_history(order_id, action, user_id or 0, user_type or 'system', reason or status)

    async def assign_master(self, order_id: int, master_id: int, user_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE orders 
                SET master_id = ?, status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (master_id, order_id))
            await db.commit()
            
            # Устани банд қилиш
            await self.update_master_status(master_id, 'busy')
            
            # Тарихга ёзиш
            await self.add_order_history(order_id, 'assigned', user_id or 0, 'admin', f"Уста ID: {master_id}")

    async def reassign_master(self, order_id: int, new_master_id: int, user_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            # Эски устани бўшатиш
            order = await self.get_order(order_id)
            if order and order['master_id']:
                await self.update_master_status(order['master_id'], 'free')
            
            # Янги устани тайинлаш
            await db.execute("""
                UPDATE orders 
                SET master_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_master_id, order_id))
            await db.commit()
            
            await self.update_master_status(new_master_id, 'busy')
            await self.add_order_history(order_id, 'reassigned', user_id or 0, 'admin', f"Янги уста ID: {new_master_id}")

    async def get_order_by_id(self, order_id: int) -> Optional[Dict]:
        return await self.get_order(order_id)

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

    # ========== БУЮРТМА ТАРИХИ ==========
    async def add_order_history(self, order_id: int, action: str, 
                                user_id: int, user_type: str, 
                                description: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO order_history (order_id, action, user_id, user_type, description)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, action, user_id, user_type, description))
            await db.commit()

    async def get_order_history(self, order_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("""
                SELECT * FROM order_history 
                WHERE order_id = ? 
                ORDER BY created_at ASC
            """, (order_id,))
            rows = await cursor.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'order_id': row[1],
                    'action': row[2],
                    'user_id': row[3],
                    'user_type': row[4],
                    'description': row[5],
                    'created_at': row[6]
                })
            return history

    # ========== БАҲОЛАР ==========
    async def add_rating(self, order_id: int, master_id: int, 
                         client_id: int, rating: int, comment: str = ""):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT INTO ratings (order_id, master_id, client_id, rating, comment)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, master_id, client_id, rating, comment))
            await db.commit()
            
            # Устанинг ўртача рейтингини ҳисоблаш
            cursor = await db.execute(
                "SELECT AVG(rating) FROM ratings WHERE master_id = ?",
                (master_id,)
            )
            avg_rating = await cursor.fetchone()
            if avg_rating and avg_rating[0]:
                await db.execute(
                    "UPDATE masters SET rating = ? WHERE id = ?",
                    (round(avg_rating[0], 1), master_id)
                )
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
            # Умумий статистика
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
            
            # Статуслар бўйича
            status_stats = {}
            for status in ['yangi', 'qabul_qilingan', 'jarayonda', 'tekshiruvda', 'bajarildi', 'yakunlangan', 'bekor_qilindi', 'rad_etilgan']:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE status = ?",
                    (status,)
                )
                count = await cursor.fetchone()
                status_stats[status] = count[0]
            
            # Бугунги
            today = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"
            )
            today = await today.fetchone()
            
            # Тўловлар
            payments = await db.execute(
                "SELECT SUM(amount) FROM payments WHERE status = 'tugallandi'"
            )
            total_income = await payments.fetchone()
            
            # Ўртача баҳо
            avg_rating = await db.execute("SELECT AVG(rating) FROM ratings")
            avg_rating = await avg_rating.fetchone()
            
            return {
                'masters': masters_count[0],
                'free_masters': free_masters[0],
                'busy_masters': busy_masters[0],
                'clients': clients_count[0],
                'orders': orders_count[0],
                'today_orders': today[0],
                'statuses': status_stats,
                'total_income': total_income[0] or 0,
                'avg_rating': round(avg_rating[0] or 0, 1)
            }

    async def get_daily_stats(self) -> Dict:
        """Кунлик статистика"""
        async with aiosqlite.connect(self.db_name) as db:
            today = datetime.now().date()
            today_str = today.isoformat()
            
            # Бугунги буюртмалар
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?",
                (today_str,)
            )
            today_orders = await cursor.fetchone()
            
            # Бугунги якунланганлар
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE DATE(completed_at) = ? AND status = 'yakunlangan'",
                (today_str,)
            )
            today_completed = await cursor.fetchone()
            
            # Бугунги даромад
            cursor = await db.execute(
                "SELECT SUM(amount) FROM payments WHERE DATE(created_at) = ? AND status = 'tugallandi'",
                (today_str,)
            )
            today_income = await cursor.fetchone()
            
            return {
                'today_orders': today_orders[0],
                'today_completed': today_completed[0],
                'today_income': today_income[0] or 0
            }

    async def get_master_stats(self, master_id: int) -> Dict:
        """Уста статистикаси"""
        async with aiosqlite.connect(self.db_name) as db:
            master = await self.get_master(master_id)
            if not master:
                return {}
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status = 'yakunlangan'",
                (master_id,)
            )
            completed = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status IN ('yangi', 'qabul_qilingan', 'jarayonda')",
                (master_id,)
            )
            active = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT AVG(rating) FROM ratings WHERE master_id = ?",
                (master_id,)
            )
            avg_rating = await cursor.fetchone()
            
            cursor = await db.execute(
                "SELECT SUM(price) FROM orders WHERE master_id = ? AND status = 'yakunlangan'",
                (master_id,)
            )
            total_earned = await cursor.fetchone()
            
            return {
                'total_orders': master['orders_count'],
                'completed_orders': completed[0],
                'active_orders': active[0],
                'rating': avg_rating[0] or 0,
                'total_earned': total_earned[0] or 0
            }

db = Database()

# =====================================================
# KEYBOARDS
# =====================================================

def main_menu():
    """Асосий меню"""
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
    """Админ менюси"""
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
    """Диспетчер менюси"""
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
    """Уста менюси"""
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
    """Мижоз менюси"""
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
    """Хизматлар менюси"""
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
    """Буюртма статусини ўзгартириш"""
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
    """Баҳо бериш"""
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
    """Уста танлаш"""
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
# BOSHQA YORDAMCHI FUNKSIYALAR
# =====================================================

def get_status_emoji(status: str) -> str:
    """Статус эмоджиси"""
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
    """Статус матни"""
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

def get_priority_emoji(priority: str) -> str:
    """Приоритет эмоджиси"""
    emojis = {
        'yuqori': '🔴',
        "o'rta": '🟡',
        'past': '🟢'
    }
    return emojis.get(priority, '⚪')

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_dispatcher(user_id: int) -> bool:
    return user_id in DISPATCHER_IDS

async def send_order_notification(context: ContextTypes.DEFAULT_TYPE, order_id: int):
    """Буюртма ҳақида хабарнома юбориш"""
    order = await db.get_order(order_id)
    if not order:
        return
    
    client = await db.get_client(order['client_id'])
    if not client:
        return
    
    # Диспетчерларга хабар
    for dispatcher_id in DISPATCHER_IDS:
        try:
            await context.bot.send_message(
                dispatcher_id,
                f"🆕 <b>ЯНГИ БУЮРТМА!</b>\n\n"
                f"📋 №{order_id}\n"
                f"🛠 Хизмат: {order['service']}\n"
                f"👤 Мижоз: {client['name']}\n"
                f"📞 Телефон: {client['phone'] or order['client_phone'] or 'йўқ'}\n"
                f"📍 Манзил: {order['address'] or 'кўрсатилмаган'}\n"
                f"📝 Изоҳ: {order['description'] or 'йўқ'}\n\n"
                f"📅 {order['created_at']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🟡 Қабул қилиш", callback_data=f"accept_{order_id}"),
                        InlineKeyboardButton("🚫 Рад этиш", callback_data=f"reject_{order_id}")
                    ],
                    [InlineKeyboardButton("👨‍🔧 Уста танлаш", callback_data=f"assign_{order_id}")]
                ])
            )
        except Exception as e:
            logger.error(f"Хабарнома юборишда хатолик: {e}")

# =====================================================
# START COMMAND
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Базани ишга тушириш
    await db.init_db()
    
    # Фойдаланувчини текшириш
    client = await db.get_client(user_id)
    if not client:
        await db.add_client(
            user_id,
            user.full_name,
            username=user.username or "",
            phone=""
        )
    
    # Админ
    if is_admin(user_id):
        stats = await db.get_stats()
        await update.message.reply_text(
            f"👑 <b>USTA 24 PRO</b>\n"
            f"Админ панелига хуш келибсиз!\n\n"
            f"📊 Статистика:\n"
            f"👨‍🔧 Усталар: {stats['masters']}\n"
            f"   🟢 Бўш: {stats['free_masters']}\n"
            f"   🔴 Банд: {stats['busy_masters']}\n"
            f"👤 Мижозлар: {stats['clients']}\n"
            f"📋 Буюртмалар: {stats['orders']}\n"
            f"📅 Бугун: {stats['today_orders']}\n"
            f"⭐ Ўртача рейтинг: {stats['avg_rating']}\n"
            f"💰 Умумий даромад: {stats['total_income']:,} сўм",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    # Диспетчер
    if is_dispatcher(user_id):
        await update.message.reply_text(
            f"👨‍💼 <b>Диспетчер панели</b>\n\n"
            f"Сизга хуш келибсиз!\n"
            f"Янги буюртмаларни кўриш учун:\n"
            f"🆕 Янги буюртмалар",
            reply_markup=dispatcher_menu(),
            parse_mode="HTML"
        )
        return
    
    # Уста
    master = await db.get_master(user_id)
    if master:
        status_text = "🟢 Ишда" if master['status'] == 'free' else "🔴 Банд"
        await update.message.reply_text(
            f"👨‍🔧 <b>Уста панели</b>\n\n"
            f"👤 {master['name']}\n"
            f"⭐ Рейтинг: {master['rating']}\n"
            f"📊 Ҳолат: {status_text}\n"
            f"📋 Буюртмалар: {master['orders_count']}\n"
            f"✅ Бажарган: {master['completed_orders']}\n\n"
            f"📋 Буюртмалар билан ишлаш учун менюдан фойдаланинг.",
            reply_markup=master_menu(),
            parse_mode="HTML"
        )
        return
    
    # Мижоз
    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"🏠 <b>USTA 24 PRO</b> ботига хуш келибсиз!\n\n"
        f"🛠 Мен сизга турли хизматларни топишга ёрдам бераман:\n\n"
        f"✅ Усталарни қидириш\n"
        f"✅ Буюртма бериш\n"
        f"✅ Буюртмаларни кузатиш\n"
        f"✅ Усталарни баҳолаш\n\n"
        f"🚀 Бошлаш учун тугмалардан фойдаланинг!",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

# =====================================================
# MAIN FUNCTION
# =====================================================

async def main():
    # Приложение яратиш
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Командаларни рўйхатга олиш
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # Бу ерга барча хэндлерлар қўшилади...
    # (Код жуда узун бўлгани учун давоми кейинги хабарда)
    
    # Поллингни бошлаш
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
