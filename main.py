#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
============================================================
USTA 24 PRO - FULL VERSION
============================================================
To'liq funksiyali buyurtma va ustalar boshqaruvi boti
============================================================
"""

import asyncio
import logging
import os
import sys
import json
import re
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import threading
import time

# =====================================================
# TELEGRAM KUTUBXONASI
# =====================================================

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery,
    InputFile,
    Message
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

# =====================================================
# BAZALAR
# =====================================================

import aiosqlite
from flask import Flask, jsonify, request

# =====================================================
# FLASK WEB SERVER
# =====================================================

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'name': 'USTA 24 PRO',
        'version': '3.0.0',
        'timestamp': datetime.now().isoformat()
    })

@flask_app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'uptime': 'running'
    })

@flask_app.route('/stats')
def stats():
    return jsonify({
        'status': 'ok',
        'bot': 'USTA 24 PRO',
        'version': '3.0.0'
    })

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# =====================================================
# ENVIRONMENT VARIABLES
# =====================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL", "usta24.db")
MASTERS_GROUP_ID = int(os.environ.get("MASTERS_GROUP_ID", "0"))

# Dispatcher ID lar
DISPATCHER_IDS = []
extra_dispatchers = os.environ.get("DISPATCHER_IDS", "")
if extra_dispatchers:
    for did in extra_dispatchers.split(","):
        try:
            DISPATCHER_IDS.append(int(did.strip()))
        except:
            pass

# =====================================================
# CHECK ENVIRONMENT
# =====================================================

def check_env():
    errors = []
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN")
    if ADMIN_ID == 0:
        errors.append("ADMIN_ID")
    if not DATABASE_URL:
        errors.append("DATABASE_URL")
    
    if errors:
        print(f"❌ Missing: {', '.join(errors)}")
        print("Please set environment variables:")
        print("  BOT_TOKEN=your_token")
        print("  ADMIN_ID=your_id")
        print("  DATABASE_URL=your_database")
        return False
    
    print("✅ All environment variables set")
    print(f"✅ BOT_TOKEN: {'*' * 10}")
    print(f"✅ ADMIN_ID: {ADMIN_ID}")
    print(f"✅ DATABASE_URL: {DATABASE_URL}")
    print(f"✅ MASTERS_GROUP_ID: {MASTERS_GROUP_ID}")
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
EDIT_MASTER_ID, EDIT_MASTER_FIELD, EDIT_MASTER_VALUE = range(20, 23)
BROADCAST_MESSAGE = 30
SEARCH_ORDER_ID = 40

# =====================================================
# DATABASE CLASS
# =====================================================

class Database:
    def __init__(self, db_name="usta24.db"):
        self.db_name = db_name

    async def init_db(self):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                # ============ MASTERS ============
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
                        experience INTEGER DEFAULT 0,
                        education TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # ============ CLIENTS ============
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        phone TEXT,
                        username TEXT,
                        address TEXT,
                        orders_count INTEGER DEFAULT 0,
                        total_spent REAL DEFAULT 0,
                        bonus INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # ============ ORDERS ============
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
                        master_comment TEXT,
                        client_comment TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        cancelled_at TIMESTAMP,
                        cancel_reason TEXT,
                        FOREIGN KEY (client_id) REFERENCES clients(id),
                        FOREIGN KEY (master_id) REFERENCES masters(id)
                    )
                """)

                # ============ ORDER HISTORY ============
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

                # ============ RATINGS ============
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

                # ============ PAYMENTS ============
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

                # ============ SERVICES ============
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS services (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        description TEXT,
                        price REAL DEFAULT 0,
                        category TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # ============ SUBSCRIPTIONS ============
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        user_type TEXT,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # ============ NOTIFICATIONS ============
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        message TEXT,
                        read BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await db.commit()
                logger.info("✅ Database initialized successfully")
                return True
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            return False

    # ============ MASTER FUNCTIONS ============
    async def add_master(self, master_id: int, name: str, phone: str = "", 
                         username: str = "", services: str = "", 
                         experience: int = 0, education: str = "") -> bool:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO masters 
                    (id, name, phone, username, services, experience, education)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (master_id, name, phone, username, services, experience, education))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Add master error: {e}")
            return False

    async def get_master(self, master_id: int) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("SELECT * FROM masters WHERE id = ?", (master_id,))
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'completed_orders': row[7],
                        'balance': row[8], 'status': row[9], 'blocked': row[10],
                        'block_reason': row[11], 'experience': row[12],
                        'education': row[13], 'created_at': row[14],
                        'updated_at': row[15]
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
                        'block_reason': row[11], 'experience': row[12],
                        'education': row[13], 'created_at': row[14],
                        'updated_at': row[15]
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
                    ORDER BY rating DESC, orders_count DESC
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

    async def update_master(self, master_id: int, **kwargs):
        try:
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
        except Exception as e:
            logger.error(f"Update master error: {e}")

    async def update_master_status(self, master_id: int, status: str):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "UPDATE masters SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (status, master_id)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Update master status error: {e}")

    async def block_master(self, master_id: int, reason: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE masters 
                    SET blocked = TRUE, block_reason = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (reason, master_id))
                await db.commit()
        except Exception as e:
            logger.error(f"Block master error: {e}")

    async def unblock_master(self, master_id: int):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE masters 
                    SET blocked = FALSE, block_reason = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (master_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"Unblock master error: {e}")

    async def search_masters(self, query: str) -> List[Dict]:
        try:
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
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'status': row[9]
                    })
                return masters
        except Exception as e:
            logger.error(f"Search masters error: {e}")
            return []

    # ============ CLIENT FUNCTIONS ============
    async def add_client(self, client_id: int, name: str, phone: str = "", 
                         username: str = "", address: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO clients 
                    (id, name, phone, username, address, last_active)
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
                cursor = await db.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'address': row[4],
                        'orders_count': row[5], 'total_spent': row[6],
                        'bonus': row[7], 'created_at': row[8],
                        'last_active': row[9]
                    }
                return None
        except Exception as e:
            logger.error(f"Get client error: {e}")
            return None

    async def get_all_clients(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM clients ORDER BY orders_count DESC, total_spent DESC"
                )
                rows = await cursor.fetchall()
                
                clients = []
                for row in rows:
                    clients.append({
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'address': row[4],
                        'orders_count': row[5], 'total_spent': row[6],
                        'bonus': row[7], 'created_at': row[8],
                        'last_active': row[9]
                    })
                return clients
        except Exception as e:
            logger.error(f"Get all clients error: {e}")
            return []

    async def update_client(self, client_id: int, **kwargs):
        try:
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
        except Exception as e:
            logger.error(f"Update client error: {e}")

    # ============ ORDER FUNCTIONS ============
    async def add_order(self, client_id: int, service: str, 
                        description: str = "", price: float = 0,
                        priority: str = "o'rta", address: str = "",
                        schedule: str = "", client_phone: str = "") -> int:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("""
                    INSERT INTO orders 
                    (client_id, service, description, price, priority, address, schedule, client_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (client_id, service, description, price, priority, address, schedule, client_phone))
                await db.commit()
                order_id = cursor.lastrowid
                
                await db.execute(
                    "UPDATE clients SET orders_count = orders_count + 1 WHERE id = ?",
                    (client_id,)
                )
                await db.commit()
                
                await self.add_order_history(order_id, "created", client_id, "client", "Buyurtma yaratildi")
                
                return order_id
        except Exception as e:
            logger.error(f"Add order error: {e}")
            return 0

    async def get_order(self, order_id: int) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'master_comment': row[11], 'client_comment': row[12],
                        'created_at': row[13], 'updated_at': row[14],
                        'completed_at': row[15], 'cancelled_at': row[16],
                        'cancel_reason': row[17]
                    }
                return None
        except Exception as e:
            logger.error(f"Get order error: {e}")
            return None

    async def get_orders(self, user_id: int, user_type: str = 'client', 
                         status: str = None, limit: int = 50) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                field = 'client_id' if user_type == 'client' else 'master_id'
                query = f"SELECT * FROM orders WHERE {field} = ?"
                params = [user_id]
                
                if status:
                    query += " AND status = ?"
                    params.append(status)
                
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'master_comment': row[11], 'client_comment': row[12],
                        'created_at': row[13], 'updated_at': row[14],
                        'completed_at': row[15], 'cancelled_at': row[16],
                        'cancel_reason': row[17]
                    })
                return orders
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []

    async def get_all_orders(self, status: str = None, limit: int = 100) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                query = "SELECT * FROM orders"
                params = []
                if status:
                    query += " WHERE status = ?"
                    params.append(status)
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'master_comment': row[11], 'client_comment': row[12],
                        'created_at': row[13], 'updated_at': row[14],
                        'completed_at': row[15], 'cancelled_at': row[16],
                        'cancel_reason': row[17]
                    })
                return orders
        except Exception as e:
            logger.error(f"Get all orders error: {e}")
            return []

    async def get_new_orders(self, limit: int = 50) -> List[Dict]:
        return await self.get_all_orders(status='yangi', limit=limit)

    async def update_order_status(self, order_id: int, status: str, 
                                  reason: str = "", user_id: int = None, 
                                  user_type: str = None):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                status_map = {
                    'qabul_qilingan': "status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP",
                    'rad_etilgan': "status = 'rad_etilgan', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP",
                    'jarayonda': "status = 'jarayonda', updated_at = CURRENT_TIMESTAMP",
                    'bajarildi': "status = 'bajarildi', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                    'yakunlangan': "status = 'yakunlangan', updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP",
                    'bekor_qilindi': f"status = 'bekor_qilindi', updated_at = CURRENT_TIMESTAMP, cancelled_at = CURRENT_TIMESTAMP, cancel_reason = '{reason}'",
                    'tekshiruvda': "status = 'tekshiruvda', updated_at = CURRENT_TIMESTAMP"
                }
                
                if status in status_map:
                    await db.execute(f"UPDATE orders SET {status_map[status]} WHERE id = ?", (order_id,))
                    await db.commit()
                    
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
        except Exception as e:
            logger.error(f"Update order status error: {e}")

    async def assign_master(self, order_id: int, master_id: int, user_id: int = None):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    UPDATE orders 
                    SET master_id = ?, status = 'qabul_qilingan', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (master_id, order_id))
                await db.commit()
                
                await self.update_master_status(master_id, 'busy')
                await self.add_order_history(order_id, 'assigned', user_id or 0, 'admin', f"Usta ID: {master_id}")
        except Exception as e:
            logger.error(f"Assign master error: {e}")

    async def reassign_master(self, order_id: int, new_master_id: int, user_id: int = None):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                order = await self.get_order(order_id)
                if order and order['master_id']:
                    await self.update_master_status(order['master_id'], 'free')
                
                await db.execute("""
                    UPDATE orders 
                    SET master_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_master_id, order_id))
                await db.commit()
                
                await self.update_master_status(new_master_id, 'busy')
                await self.add_order_history(order_id, 'reassigned', user_id or 0, 'admin', f"Yangi usta ID: {new_master_id}")
        except Exception as e:
            logger.error(f"Reassign master error: {e}")

    async def update_order(self, order_id: int, **kwargs):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                fields = []
                values = []
                for key, value in kwargs.items():
                    fields.append(f"{key} = ?")
                    values.append(value)
                values.append(order_id)
                
                await db.execute(f"""
                    UPDATE orders 
                    SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, values)
                await db.commit()
        except Exception as e:
            logger.error(f"Update order error: {e}")

    async def search_orders(self, query: str) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("""
                    SELECT * FROM orders 
                    WHERE id = ? OR service LIKE ? OR description LIKE ? OR address LIKE ?
                    ORDER BY created_at DESC
                """, (query if query.isdigit() else -1, f"%{query}%", f"%{query}%", f"%{query}%"))
                rows = await cursor.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'price': row[5],
                        'status': row[6], 'priority': row[7], 'address': row[8],
                        'schedule': row[9], 'client_phone': row[10],
                        'created_at': row[13], 'updated_at': row[14]
                    })
                return orders
        except Exception as e:
            logger.error(f"Search orders error: {e}")
            return []

    # ============ ORDER HISTORY ============
    async def add_order_history(self, order_id: int, action: str, 
                                user_id: int, user_type: str, 
                                description: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT INTO order_history (order_id, action, user_id, user_type, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, action, user_id, user_type, description))
                await db.commit()
        except Exception as e:
            logger.error(f"Add order history error: {e}")

    async def get_order_history(self, order_id: int) -> List[Dict]:
        try:
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
                        'id': row[0], 'order_id': row[1], 'action': row[2],
                        'user_id': row[3], 'user_type': row[4],
                        'description': row[5], 'created_at': row[6]
                    })
                return history
        except Exception as e:
            logger.error(f"Get order history error: {e}")
            return []

    # ============ RATINGS ============
    async def add_rating(self, order_id: int, master_id: int, 
                         client_id: int, rating: int, comment: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT INTO ratings (order_id, master_id, client_id, rating, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, master_id, client_id, rating, comment))
                await db.commit()
                
                # Update master rating
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

    # ============ STATISTICS ============
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
                
                status_stats = {}
                for status in ['yangi', 'qabul_qilingan', 'jarayonda', 'tekshiruvda', 'bajarildi', 'yakunlangan', 'bekor_qilindi', 'rad_etilgan']:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM orders WHERE status = ?",
                        (status,)
                    )
                    count = await cursor.fetchone()
                    status_stats[status] = count[0]
                
                today = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = DATE('now')"
                )
                today = await today.fetchone()
                
                avg_rating = await db.execute("SELECT AVG(rating) FROM ratings")
                avg_rating = await avg_rating.fetchone()
                
                total_income = await db.execute(
                    "SELECT SUM(price) FROM orders WHERE status = 'yakunlangan' OR status = 'bajarildi'"
                )
                total_income = await total_income.fetchone()
                
                return {
                    'masters': masters_count[0],
                    'free_masters': free_masters[0],
                    'busy_masters': busy_masters[0],
                    'clients': clients_count[0],
                    'orders': orders_count[0],
                    'today_orders': today[0],
                    'statuses': status_stats,
                    'avg_rating': round(avg_rating[0] or 0, 1),
                    'total_income': total_income[0] or 0
                }
        except Exception as e:
            logger.error(f"Get stats error: {e}")
            return {}

    async def get_daily_stats(self) -> Dict:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                today = datetime.now().date().isoformat()
                
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?",
                    (today,)
                )
                today_orders = await cursor.fetchone()
                
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE DATE(completed_at) = ? AND status IN ('yakunlangan', 'bajarildi')",
                    (today,)
                )
                today_completed = await cursor.fetchone()
                
                cursor = await db.execute(
                    "SELECT SUM(price) FROM orders WHERE DATE(completed_at) = ? AND status IN ('yakunlangan', 'bajarildi')",
                    (today,)
                )
                today_income = await cursor.fetchone()
                
                return {
                    'today_orders': today_orders[0],
                    'today_completed': today_completed[0],
                    'today_income': today_income[0] or 0
                }
        except Exception as e:
            logger.error(f"Get daily stats error: {e}")
            return {}

    async def get_master_stats(self, master_id: int) -> Dict:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                master = await self.get_master(master_id)
                if not master:
                    return {}
                
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status IN ('yakunlangan', 'bajarildi')",
                    (master_id,)
                )
                completed = await cursor.fetchone()
                
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE master_id = ? AND status IN ('yangi', 'qabul_qilingan', 'jarayonda', 'tekshiruvda')",
                    (master_id,)
                )
                active = await cursor.fetchone()
                
                cursor = await db.execute(
                    "SELECT AVG(rating) FROM ratings WHERE master_id = ?",
                    (master_id,)
                )
                avg_rating = await cursor.fetchone()
                
                cursor = await db.execute(
                    "SELECT SUM(price) FROM orders WHERE master_id = ? AND status IN ('yakunlangan', 'bajarildi')",
                    (master_id,)
                )
                total_earned = await cursor.fetchone()
                
                return {
                    'total_orders': master['orders_count'],
                    'completed_orders': completed[0] or 0,
                    'active_orders': active[0] or 0,
                    'rating': avg_rating[0] or 0,
                    'total_earned': total_earned[0] or 0
                }
        except Exception as e:
            logger.error(f"Get master stats error: {e}")
            return {}

    # ============ SERVICES ============
    async def add_service(self, name: str, description: str = "", price: float = 0, category: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO services (name, description, price, category)
                    VALUES (?, ?, ?, ?)
                """, (name, description, price, category))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Add service error: {e}")
            return False

    async def get_all_services(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("SELECT * FROM services ORDER BY name")
                rows = await cursor.fetchall()
                
                services = []
                for row in rows:
                    services.append({
                        'id': row[0], 'name': row[1], 'description': row[2],
                        'price': row[3], 'category': row[4], 'created_at': row[5]
                    })
                return services
        except Exception as e:
            logger.error(f"Get all services error: {e}")
            return []

    # ============ SUBSCRIPTIONS ============
    async def subscribe(self, user_id: int, user_type: str = 'client'):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO subscriptions (user_id, user_type, active)
                    VALUES (?, ?, TRUE)
                """, (user_id, user_type))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Subscribe error: {e}")
            return False

    async def unsubscribe(self, user_id: int):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "UPDATE subscriptions SET active = FALSE WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Unsubscribe error: {e}")
            return False

    async def get_subscribers(self, user_type: str = None) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                query = "SELECT * FROM subscriptions WHERE active = TRUE"
                params = []
                if user_type:
                    query += " AND user_type = ?"
                    params.append(user_type)
                
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                
                subscribers = []
                for row in rows:
                    subscribers.append({
                        'id': row[0], 'user_id': row[1], 'user_type': row[2],
                        'active': row[3], 'created_at': row[4]
                    })
                return subscribers
        except Exception as e:
            logger.error(f"Get subscribers error: {e}")
            return []

    # ============ NOTIFICATIONS ============
    async def add_notification(self, user_id: int, message: str):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                    (user_id, message)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Add notification error: {e}")

    async def get_notifications(self, user_id: int, unread_only: bool = True) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                query = "SELECT * FROM notifications WHERE user_id = ?"
                params = [user_id]
                if unread_only:
                    query += " AND read = FALSE"
                query += " ORDER BY created_at DESC"
                
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                
                notifications = []
                for row in rows:
                    notifications.append({
                        'id': row[0], 'user_id': row[1], 'message': row[2],
                        'read': row[3], 'created_at': row[4]
                    })
                return notifications
        except Exception as e:
            logger.error(f"Get notifications error: {e}")
            return []

    async def mark_notification_read(self, notification_id: int):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "UPDATE notifications SET read = TRUE WHERE id = ?",
                    (notification_id,)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Mark notification read error: {e}")

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
            ["👤 Shaxsiy ma'lumot", "⭐ Reyting"],
            ["🔔 Xabarlar", "ℹ️ Yordam"],
            ["👑 Admin paneli"]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["👤 Mijozlar bazasi", "👨‍🔧 Ustalar"],
            ["➕ Usta qo'shish", "✏️ Ustani tahrirlash"],
            ["🗑 Ustani o'chirish", "🟢 Usta holati"],
            ["🚫 Ustani bloklash", "🔓 Ustani faollashtirish"],
            ["📋 Barcha buyurtmalar", "🔎 Buyurtma qidirish"],
            ["📊 Statistika", "📈 Hisobot"],
            ["📢 Xabar tarqatish", "🛠 Xizmatlar"],
            ["👨‍💼 Dispetcher", "⚙️ Sozlamalar"],
            ["⬅️ Asosiy menyu"]
        ],
        resize_keyboard=True
    )

def dispatcher_menu():
    return ReplyKeyboardMarkup(
        [
            ["🆕 Yangi buyurtmalar"],
            ["🟡 Qabul qilish", "🚫 Rad etish"],
            ["👨‍🔧 Usta tanlash"],
            ["🔄 Boshqa ustaga berish"],
            ["📞 Mijoz bilan bog'lanish"],
            ["📍 Manzilni ko'rish"],
            ["📋 Buyurtma tarixi"],
            ["🔎 Buyurtma qidirish"],
            ["📊 Kunlik statistika"],
            ["⬅️ Admin menyu"]
        ],
        resize_keyboard=True
    )

def master_menu():
    return ReplyKeyboardMarkup(
        [
            ["🟡 Buyurtmani qabul qilish"],
            ["🚫 Buyurtmani rad etish"],
            ["🔵 Ishni boshlash"],
            ["📞 Mijoz bilan bog'lanish"],
            ["📍 Manzil", "🔄 Boshqa ustaga berish"],
            ["❌ Buyurtmani bekor qilish"],
            ["✅ Ishni yakunlash"],
            ["⭐ Mijoz bahosi"],
            ["📋 O'z buyurtmalarim"],
            ["📊 Mening statistika"],
            ["⬅️ Asosiy menyu"]
        ],
        resize_keyboard=True
    )

# =====================================================
# HELPERS
# =====================================================

def get_status_emoji(status: str) -> str:
    emojis = {
        'yangi': '🆕', 'qabul_qilingan': '🟡',
        'jarayonda': '🔵', 'tekshiruvda': '🔍',
        'bajarildi': '✅', 'yakunlangan': '⭐',
        'bekor_qilindi': '❌', 'rad_etilgan': '🚫'
    }
    return emojis.get(status, '📋')

def get_status_text(status: str) -> str:
    texts = {
        'yangi': 'Yangi', 'qabul_qilingan': 'Qabul qilingan',
        'jarayonda': 'Jarayonda', 'tekshiruvda': 'Tekshiruvda',
        'bajarildi': 'Bajarildi', 'yakunlangan': 'Yakunlangan',
        'bekor_qilindi': 'Bekor qilingan', 'rad_etilgan': 'Rad etilgan'
    }
    return texts.get(status, status)

def get_priority_emoji(priority: str) -> str:
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

# =====================================================
# BOT HANDLERS - FULL VERSION
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # User rolini aniqlash
    if is_admin(user_id):
        stats = await db.get_stats()
        await update.message.reply_text(
            f"👑 <b>USTA 24 PRO</b>\n\n"
            f"Admin paneliga xush kelibsiz!\n\n"
            f"📊 <b>Statistika</b>\n"
            f"👨‍🔧 Ustalar: {stats.get('masters', 0)}\n"
            f"   🟢 Bo'sh: {stats.get('free_masters', 0)}\n"
            f"   🔴 Band: {stats.get('busy_masters', 0)}\n"
            f"👤 Mijozlar: {stats.get('clients', 0)}\n"
            f"📋 Buyurtmalar: {stats.get('orders', 0)}\n"
            f"📅 Bugun: {stats.get('today_orders', 0)}\n"
            f"⭐ O'rtacha reyting: {stats.get('avg_rating', 0)}\n"
            f"💰 Umumiy daromad: {stats.get('total_income', 0):,} so'm",
            reply_markup=admin_menu(),
            parse_mode="HTML"
        )
        return
    
    if is_dispatcher(user_id):
        await update.message.reply_text(
            f"👨‍💼 <b>Dispetcher paneli</b>\n\n"
            f"Sizga xush kelibsiz!\n"
            f"Yangi buyurtmalarni ko'rish uchun:\n"
            f"🆕 <b>Yangi buyurtmalar</b>",
            reply_markup=dispatcher_menu(),
            parse_mode="HTML"
        )
        return
    
    master = await db.get_master(user_id)
    if master:
        status_text = "🟢 Ishda" if master['status'] == 'free' else "🔴 Band"
        rating = await db.get_master_rating(user_id)
        await update.message.reply_text(
            f"👨‍🔧 <b>Usta paneli</b>\n\n"
            f"👤 {master['name']}\n"
            f"⭐ Reyting: {rating['average']} ({rating['count']} ta baho)\n"
            f"📊 Holat: {status_text}\n"
            f"📋 Buyurtmalar: {master['orders_count']}\n"
            f"✅ Bajargan: {master['completed_orders']}\n"
            f"💰 Balans: {master['balance']:,} so'm",
            reply_markup=master_menu(),
            parse_mode="HTML"
        )
        return
    
    # Oddiy mijoz
    await db.add_client(user_id, user.full_name, username=user.username or "")
    await db.subscribe(user_id, 'client')
    
    services = await db.get_all_services()
    services_text = "🛠 Mavjud xizmatlar:\n"
    for s in services[:5]:
        services_text += f"• {s['name']}" + (f" - {s['price']:,} so'm" if s['price'] else "") + "\n"
    
    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.first_name}!</b>\n\n"
        f"🏠 <b>USTA 24 PRO</b> botiga xush kelibsiz!\n\n"
        f"{services_text}\n\n"
        f"📌 Yordam olish uchun /help",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>YORDAM</b>\n\n"
        "🛠 Xizmatlar - Barcha xizmatlar ro'yxati\n"
        "👨‍🔧 Ustalar - Ustalar ro'yxati va qidirish\n"
        "📝 Buyurtma berish - Yangi buyurtma yaratish\n"
        "📋 Mening buyurtmalarim - Buyurtma tarixi\n"
        "👤 Shaxsiy ma'lumot - Profil ma'lumotlari\n"
        "⭐ Reyting - Ustalar reytingi\n"
        "🔔 Xabarlar - Bildirishnomalar\n\n"
        "<b>🚀 Tezkor buyruqlar:</b>\n"
        "/start - Botni qayta ishga tushirish\n"
        "/help - Yordam\n"
        "/order - Buyurtma berish\n"
        "/masters - Ustalar ro'yxati\n"
        "/myorders - Mening buyurtmalarim\n"
        "/profile - Profil\n"
        "/rate - Ustani baholash\n\n"
        "👑 Adminlar uchun: /admin",
        parse_mode="HTML"
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Siz admin emassiz!")
        return
    
    stats = await db.get_stats()
    await update.message.reply_text(
        f"👑 <b>ADMIN PANEL</b>\n\n"
        f"📊 <b>Qisqa statistika</b>\n"
        f"👨‍🔧 Ustalar: {stats.get('masters', 0)}\n"
        f"👤 Mijozlar: {stats.get('clients', 0)}\n"
        f"📋 Buyurtmalar: {stats.get('orders', 0)}\n"
        f"📅 Bugun: {stats.get('today_orders', 0)}\n"
        f"💰 Daromad: {stats.get('total_income', 0):,} so'm",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )

# =====================================================
# COMMAND HANDLERS
# =====================================================

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 <b>BUYURTMA BERISH</b>\n\n"
        "Buyurtma berish uchun quyidagi ma'lumotlarni yozing:\n\n"
        "1️⃣ Xizmat turi\n"
        "2️⃣ Tavsif\n"
        "3️⃣ Manzil\n\n"
        "Masalan:\n"
        "<code>Mebel yig'ish\n2 xonali mebel yig'ish kerak\nToshkent, Chilonzor 12</code>\n\n"
        "Yoki tugmalardan foydalaning: 📝 Buyurtma berish",
        parse_mode="HTML"
    )
    return ORDER_SERVICE

async def masters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    masters = await db.get_all_masters()
    if not masters:
        await update.message.reply_text("👨‍🔧 Hozircha ustalar yo'q.")
        return
    
    text = "👨‍🔧 <b>USTALAR</b>\n\n"
    for i, master in enumerate(masters[:10], 1):
        status_emoji = "🟢" if master['status'] == 'free' else "🔴"
        text += (
            f"{i}️⃣ {status_emoji} <b>{master['name']}</b>\n"
            f"⭐ {master['rating']} | 📋 {master['orders_count']}\n"
            f"🛠 {master['services']}\n"
            f"📞 {master['phone'] or 'Telefon ko\'rsatilmagan'}\n\n"
        )
    
    if len(masters) > 10:
        text += f"📌 <b>Jami: {len(masters)} ta usta</b>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def myorders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = await db.get_orders(user_id, 'client')
    
    if not orders:
        await update.message.reply_text("📋 Sizda buyurtmalar yo'q.")
        return
    
    text = "📋 <b>Mening buyurtmalarim</b>\n\n"
    for order in orders[:10]:
        master = await db.get_master(order['master_id']) if order['master_id'] else None
        master_name = master['name'] if master else "Tayinlanmagan"
        text += (
            f"№{order['id']} {get_status_emoji(order['status'])}\n"
            f"🛠 {order['service']}\n"
            f"👨‍🔧 {master_name}\n"
            f"📅 {order['created_at'][:10]}\n\n"
        )
    
    if len(orders) > 10:
        text += f"📌 <b>Jami: {len(orders)} ta buyurtma</b>"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    client = await db.get_client(user_id)
    if not client:
        await update.message.reply_text("❌ Profil topilmadi!")
        return
    
    orders = await db.get_orders(user_id, 'client')
    active = len([o for o in orders if o['status'] not in ['yakunlangan', 'bekor_qilindi', 'rad_etilgan']])
    completed = len([o for o in orders if o['status'] in ['yakunlangan', 'bajarildi']])
    
    await update.message.reply_text(
        f"👤 <b>SHAXSIY MA'LUMOTLAR</b>\n\n"
        f"🆔 ID: {client['id']}\n"
        f"👤 Ism: {client['name']}\n"
        f"📞 Telefon: {client['phone'] or 'Yo'q'}\n"
        f"📱 Username: @{client['username'] or 'yo\'q'}\n"
        f"📍 Manzil: {client['address'] or 'Yo\'q'}\n\n"
        f"📊 <b>Statistika</b>\n"
        f"📋 Jami: {client['orders_count']}\n"
        f"🟡 Faol: {active}\n"
        f"✅ Yakunlangan: {completed}\n"
        f"💰 Sarflagan: {client['total_spent'] or 0:,} so'm\n"
        f"🎁 Bonus: {client['bonus'] or 0}",
        parse_mode="HTML"
    )

async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    masters = await db.get_all_masters()
    if not masters:
        await update.message.reply_text("⭐ Hozircha ustalar yo'q.")
        return
    
    text = "⭐ <b>USTALAR REYTINGI</b>\n\n"
    for i, master in enumerate(masters[:10], 1):
        rating = await db.get_master_rating(master['id'])
        text += (
            f"{i}️⃣ <b>{master['name']}</b>\n"
            f"⭐ {rating['average']} ({rating['count']} ta baho)\n"
            f"🛠 {master['services']}\n\n"
        )
    
    await update.message.reply_text(text, parse_mode="HTML")

# =====================================================
# MAIN FUNCTION
# =====================================================

async def main():
    try:
        if not check_env():
            sys.exit(1)
        
        await db.init_db()
        logger.info("✅ Database initialized")
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info(f"✅ Flask server started on port {os.environ.get('PORT', 8080)}")
        
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        logger.info("✅ Application built")
        
        # ============ COMMANDS ============
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("admin", admin_panel))
        application.add_handler(CommandHandler("order", order_command))
        application.add_handler(CommandHandler("masters", masters_command))
        application.add_handler(CommandHandler("myorders", myorders_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("rating", rating_command))
        
        # ============ MESSAGE HANDLERS ============
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Asosiy menyu$'),
            start
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^⬅️ Admin menyu$'),
            admin_panel
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^ℹ️ Yordam$'),
            help_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👑 Admin paneli$') & filters.User(ADMIN_ID),
            admin_panel
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👨‍💼 Dispetcher$') & (filters.User(ADMIN_ID) | filters.User(DISPATCHER_IDS)),
            dispatcher_panel
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👨‍🔧 Ustalar$'),
            masters_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^📋 Mening buyurtmalarim$'),
            myorders_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^👤 Shaxsiy ma\'lumot$'),
            profile_command
        ))
        application.add_handler(MessageHandler(
            filters.Regex(r'^⭐ Reyting$'),
            rating_command
        ))
        
        # ============ CALLBACK ============
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # ============ UNKNOWN ============
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_unknown
        ))
        
        logger.info("🚀 USTA 24 PRO ishlayapti...")
        await application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

# =====================================================
# ADDITIONAL HANDLERS
# =====================================================

async def dispatcher_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👨‍💼 <b>DISPETCHER PANELI</b>",
        reply_markup=dispatcher_menu(),
        parse_mode="HTML"
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_text("✅ Amal bajarildi!")

async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Tushunmadim. Iltimos, tugmalardan foydalaning!\n"
        "📖 Yordam olish uchun /help",
        reply_markup=main_menu()
    )

if __name__ == "__main__":
    asyncio.run(main())
