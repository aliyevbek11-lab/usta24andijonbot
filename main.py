#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================
USTA 24 ANDIJON BOT - SODDA VERSIYA
=============================================
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
import threading

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

import aiosqlite
from flask import Flask, jsonify

# =====================================================
# FLASK WEB SERVER
# =====================================================

flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return jsonify({'status': 'ok', 'name': 'USTA 24 ANDIJON BOT', 'version': '1.0.0'})

@flask_app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# =====================================================
# ENVIRONMENT VARIABLES
# =====================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DISPATCHER_ID = int(os.environ.get("DISPATCHER_ID", "0"))

DISPATCHER_IDS = []
if DISPATCHER_ID:
    DISPATCHER_IDS.append(DISPATCHER_ID)

# =====================================================
# CHECK ENVIRONMENT
# =====================================================

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set!")
    sys.exit(1)

if ADMIN_ID == 0:
    print("❌ ADMIN_ID not set!")
    sys.exit(1)

print("✅ BOT_TOKEN: OK")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ DISPATCHER_ID: {DISPATCHER_ID}")

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

# =====================================================
# DATABASE CLASS
# =====================================================

class Database:
    def __init__(self, db_name="usta24.db"):
        self.db_name = db_name

    async def init_db(self):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS masters (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        phone TEXT,
                        username TEXT,
                        services TEXT,
                        rating REAL DEFAULT 0,
                        orders_count INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'busy',
                        blocked BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS clients (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        phone TEXT,
                        username TEXT,
                        address TEXT,
                        orders_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER,
                        master_id INTEGER,
                        service TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'yangi',
                        address TEXT,
                        client_phone TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                await db.execute("""
                    CREATE TABLE IF NOT EXISTS ratings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER,
                        master_id INTEGER,
                        client_id INTEGER,
                        rating INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                cursor = await db.execute("SELECT * FROM masters WHERE id = ?", (master_id,))
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'phone': row[2],
                        'username': row[3], 'services': row[4], 'rating': row[5],
                        'orders_count': row[6], 'status': row[7], 'blocked': row[8]
                    }
                return None
        except Exception as e:
            logger.error(f"Get master error: {e}")
            return None

    async def get_all_masters(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM masters WHERE blocked = FALSE ORDER BY rating DESC"
                )
                rows = await cursor.fetchall()
                return [{
                    'id': r[0], 'name': r[1], 'phone': r[2],
                    'username': r[3], 'services': r[4], 'rating': r[5],
                    'orders_count': r[6], 'status': r[7]
                } for r in rows]
        except Exception as e:
            logger.error(f"Get all masters error: {e}")
            return []

    async def get_available_masters(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute(
                    "SELECT * FROM masters WHERE status = 'free' AND blocked = FALSE ORDER BY rating DESC"
                )
                rows = await cursor.fetchall()
                return [{
                    'id': r[0], 'name': r[1], 'phone': r[2],
                    'username': r[3], 'services': r[4], 'rating': r[5],
                    'orders_count': r[6], 'status': r[7]
                } for r in rows]
        except Exception as e:
            logger.error(f"Get available masters error: {e}")
            return []

    async def update_master_status(self, master_id: int, status: str):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute(
                    "UPDATE masters SET status = ? WHERE id = ?",
                    (status, master_id)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Update master status error: {e}")

    # ========== CLIENTS ==========
    async def add_client(self, client_id: int, name: str, phone: str = "", username: str = ""):
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO clients (id, name, phone, username)
                    VALUES (?, ?, ?, ?)
                """, (client_id, name, phone, username))
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
                        'username': row[3], 'address': row[4], 'orders_count': row[5]
                    }
                return None
        except Exception as e:
            logger.error(f"Get client error: {e}")
            return None

    async def get_all_clients(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("SELECT * FROM clients ORDER BY orders_count DESC")
                rows = await cursor.fetchall()
                return [{
                    'id': r[0], 'name': r[1], 'phone': r[2],
                    'username': r[3], 'address': r[4], 'orders_count': r[5]
                } for r in rows]
        except Exception as e:
            logger.error(f"Get all clients error: {e}")
            return []

    # ========== ORDERS ==========
    async def add_order(self, client_id: int, service: str, description: str = "", 
                        address: str = "", client_phone: str = "") -> int:
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
                cursor = await db.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
                row = await cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'client_id': row[1], 'master_id': row[2],
                        'service': row[3], 'description': row[4], 'status': row[5],
                        'address': row[6], 'client_phone': row[7],
                        'created_at': row[8], 'updated_at': row[9]
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
                return [{
                    'id': r[0], 'client_id': r[1], 'master_id': r[2],
                    'service': r[3], 'description': r[4], 'status': r[5],
                    'address': r[6], 'client_phone': r[7],
                    'created_at': r[8], 'updated_at': r[9]
                } for r in rows]
        except Exception as e:
            logger.error(f"Get orders error: {e}")
            return []

    async def get_all_orders(self) -> List[Dict]:
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("SELECT * FROM orders ORDER BY created_at DESC")
                rows = await cursor.fetchall()
                return [{
                    'id': r[0], 'client_id': r[1], 'master_id': r[2],
                    'service': r[3], 'description': r[4], 'status': r[5],
                    'address': r[6], 'client_phone': r[7],
                    'created_at': r[8], 'updated_at': r[9]
                } for r in rows]
        except Exception as e:
            logger.error(f"Get all orders error: {e}")
            return []

    async def get_new_orders(self) -> List[Dict]:
        try:
            async with
