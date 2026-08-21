import os
import asyncio
import logging
from threading import Thread
from datetime import datetime
import uuid
from typing import Dict, List, Optional, Any

import asyncpg
from asyncpg import Pool

from flask import Flask, jsonify

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = os.getenv("ADMIN_ID")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
DISPATCHER_ID = os.getenv("DISPATCHER_ID")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")


ADMIN_ID = int(ADMIN_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)

if DISPATCHER_ID:
    DISPATCHER_ID = int(DISPATCHER_ID)
else:
    DISPATCHER_ID = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("USTA24")


# ============================================================
# FLASK APP
# ============================================================

flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    return jsonify({
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'service': 'USTA24 Orders Bot'
    })

@flask_app.route('/stats')
async def stats():
    if not Database.pool:
        return jsonify({'error': 'Database not connected'}), 503
    
    async with Database.pool.acquire() as conn:
        total = await conn.fetchval('SELECT COUNT(*) FROM orders')
        new = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'new')
        completed = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'completed')
        masters = await conn.fetchval('SELECT COUNT(*) FROM masters')
    
    return jsonify({
        'total_orders': total,
        'new_orders': new,
        'completed_orders': completed,
        'total_masters': masters
    })


# ============================================================
# DATABASE
# ============================================================

class Database:
    pool: Pool = None

    @classmethod
    async def init(cls):
        try:
            cls.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            await cls.create_tables()
            logger.info("✅ Database connected")
        except Exception as e:
            logger.error(f"❌ Database error: {e}")
            raise

    @classmethod
    async def close(cls):
        if cls.pool:
            await cls.pool.close()
            logger.info("✅ Database disconnected")

    @classmethod
    async def create_tables(cls):
        async with cls.pool.acquire() as conn:
            # Users table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    phone TEXT,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Masters table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS masters (
                    user_id BIGINT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    phone TEXT,
                    is_online BOOLEAN DEFAULT TRUE,
                    is_busy BOOLEAN DEFAULT FALSE,
                    rating FLOAT DEFAULT 0,
                    total_orders INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')
            
            # Dispatchers table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS dispatchers (
                    user_id BIGINT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')
            
            # Orders table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_number TEXT UNIQUE NOT NULL,
                    user_id BIGINT NOT NULL,
                    master_id BIGINT,
                    service TEXT NOT NULL,
                    address TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'new',
                    rating INTEGER DEFAULT 0,
                    review TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP,
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    CONSTRAINT fk_master FOREIGN KEY (master_id) REFERENCES masters(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Order history
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS order_history (
                    id SERIAL PRIMARY KEY,
                    order_number TEXT NOT NULL,
                    status TEXT NOT NULL,
                    changed_by BIGINT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_order FOREIGN KEY (order_number) REFERENCES orders(order_number) ON DELETE CASCADE
                )
            ''')
            
            # Indexes
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_master_id ON orders(master_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_masters_online ON masters(is_online)')
            
            logger.info("✅ Tables created")


# ============================================================
# CONSTANTS
# ============================================================

ORDER_STATUSES = {
    'new': {'emoji': '🆕', 'name': 'Янги'},
    'accepted': {'emoji': '🟡', 'name': 'Қабул қилинган'},
    'in_progress': {'emoji': '🔵', 'name': 'Иш жараёнида'},
    'completed': {'emoji': '✅', 'name': 'Якунланган'},
    'cancelled': {'emoji': '❌', 'name': 'Бекор қилинган'},
    'rejected': {'emoji': '🚫', 'name': 'Рад этилган'}
}

STATUS_FLOW = {
    'new': 'accepted',
    'accepted': 'in_progress',
    'in_progress': 'completed'
}


# ============================================================
# KEYBOARDS
# ============================================================

class Keyboards:
    @staticmethod
    def main(role: str = 'user'):
        keyboard = [
            ['📝 Буюртма бериш', '📋 Менинг буюртмаларим'],
            ['👨‍🔧 Усталар', '📊 Статистика'],
            ['📞 Диспетчерга мурожаат', '👤 Профиль']
        ]
        
        if role in ['dispatcher', 'admin']:
            keyboard.append(['📋 Диспетчер панели'])
        
        if role == 'master':
            keyboard = [
                ['📋 Менинг буюртмаларим', '📊 Менинг статистикам'],
                ['🟢 Онлайн', '🔴 Банд'],
                ['🔙 Орқага']
            ]
        
        if role == 'admin':
            keyboard.append(['👑 Админ панели'])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def dispatcher():
        return ReplyKeyboardMarkup([
            ['📋 Барча буюртмалар', '🆕 Янги буюртмалар'],
            ['🟡 Қабул қилинганлар', '🔵 Ишдаги буюртмалар'],
            ['✅ Якунланганлар', '❌ Бекор қилинганлар'],
            ['📊 Статистика', '👨‍🔧 Усталар статистикаси'],
            ['📢 Хабар юбориш', '🔙 Орқага']
        ], resize_keyboard=True)

    @staticmethod
    def admin():
        return ReplyKeyboardMarkup([
            ['👨‍🔧 Уста қўшиш', '👨‍🔧 Уста ўчириш'],
            ['👤 Диспетчер қўшиш', '👤 Диспетчер ўчириш'],
            ['📊 Умумий статистика', '📢 Хабар юбориш'],
            ['🔙 Орқага']
        ], resize_keyboard=True)

    @staticmethod
    def cancel():
        return ReplyKeyboardMarkup([['🔙 Бекор қилиш']], resize_keyboard=True)

    @staticmethod
    def skip():
        return ReplyKeyboardMarkup([['🔙 Бекор қилиш', '⏩ Ўтказиб юбориш']], resize_keyboard=True)

    @staticmethod
    def order_actions(order_number: str):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Қабул қилиш", callback_data=f"accept_{order_number}")],
            [InlineKeyboardButton("👨‍🔧 Устага юбориш", callback_data=f"assign_{order_number}")],
            [InlineKeyboardButton("🚫 Рад этиш", callback_data=f"reject_{order_number}")]
        ])

    @staticmethod
    def master_actions(order_number: str):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Буюртмани олиш", callback_data=f"take_{order_number}")],
            [InlineKeyboardButton("📞 Мижозга қўнғироқ", callback_data=f"call_{order_number}")]
        ])

    @staticmethod
    def rate_actions(order_number: str):
        buttons = []
        for i in range(1, 6):
            buttons.append([InlineKeyboardButton(f"⭐ {i}", callback_data=f"rate_{order_number}_{i}")])
        return InlineKeyboardMarkup(buttons)


# ============================================================
# DATABASE HELPERS
# ============================================================

class UserDB:
    @staticmethod
    async def get_or_create(user_id: int, username: str = None, full_name: str = None):
        async with Database.pool.acquire() as conn:
            user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            if not user:
                await conn.execute('''
                    INSERT INTO users (user_id, username, full_name)
                    VALUES ($1, $2, $3)
                ''', user_id, username, full_name)
                user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            return dict(user)

    @staticmethod
    async def get_role(user_id: int) -> str:
        if user_id == ADMIN_ID:
            return 'admin'
        
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT user_id FROM masters WHERE user_id = $1', user_id)
            if master:
                return 'master'
            
            if DISPATCHER_ID and user_id == DISPATCHER_ID:
                return 'dispatcher'
            
            dispatcher = await conn.fetchrow('SELECT user_id FROM dispatchers WHERE user_id = $1', user_id)
            if dispatcher:
                return 'dispatcher'
            
            return 'user'


class OrderDB:
    @staticmethod
    async def create(user_id: int, service: str, address: str, phone: str, description: str = "") -> dict:
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        async with Database.pool.acquire() as conn:
            order_id = await conn.fetchval('''
                INSERT INTO orders (order_number, user_id, service, address, phone, description)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            ''', order_number, user_id, service, address, phone, description)
            
            order = await conn.fetchrow('SELECT * FROM orders WHERE id = $1', order_id)
            
            # Add history
            await conn.execute('''
                INSERT INTO order_history (order_number, status, changed_by)
                VALUES ($1, $2, $3)
            ''', order_number, 'new', user_id)
            
            return dict(order)

    @staticmethod
    async def get_by_number(order_number: str) -> Optional[dict]:
        async with Database.pool.acquire() as conn:
            order = await conn.fetchrow('SELECT * FROM orders WHERE order_number = $1', order_number)
            return dict(order) if order else None

    @staticmethod
    async def get_user_orders(user_id: int, limit: int = 10) -> List[dict]:
        async with Database.pool.acquire() as conn:
            orders = await conn.fetch('''
                SELECT o.*, m.full_name as master_name
                FROM orders o
                LEFT JOIN masters m ON o.master_id = m.user_id
                WHERE o.user_id = $1 
                ORDER BY o.created_at DESC 
                LIMIT $2
            ''', user_id, limit)
            return [dict(order) for order in orders]

    @staticmethod
    async def get_master_orders(master_id: int, limit: int = 10) -> List[dict]:
        async with Database.pool.acquire() as conn:
            orders = await conn.fetch('''
                SELECT o.*, u.full_name as user_name, u.phone as user_phone
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.master_id = $1 
                ORDER BY o.created_at DESC 
                LIMIT $2
            ''', master_id, limit)
            return [dict(order) for order in orders]

    @staticmethod
    async def get_by_status(status: str = None, limit: int = 20) -> List[dict]:
        async with Database.pool.acquire() as conn:
            if status:
                orders = await conn.fetch('''
                    SELECT o.*, u.full_name as user_name, m.full_name as master_name
                    FROM orders o
                    LEFT JOIN users u ON o.user_id = u.user_id
                    LEFT JOIN masters m ON o.master_id = m.user_id
                    WHERE o.status = $1 
                    ORDER BY o.created_at DESC 
                    LIMIT $2
                ''', status, limit)
            else:
                orders = await conn.fetch('''
                    SELECT o.*, u.full_name as user_name, m.full_name as master_name
                    FROM orders o
                    LEFT JOIN users u ON o.user_id = u.user_id
                    LEFT JOIN masters m ON o.master_id = m.user_id
                    ORDER BY o.created_at DESC 
                    LIMIT $2
                ''', limit)
            return [dict(order) for order in orders]

    @staticmethod
    async def update_status(order_number: str, status: str, changed_by: int = None):
        async with Database.pool.acquire() as conn:
            await conn.execute('''
                UPDATE orders 
                SET status = $1, updated_at = NOW(),
                    completed_at = CASE WHEN $1 = 'completed' THEN NOW() ELSE completed_at END
                WHERE order_number = $2
            ''', status, order_number)
            
            await conn.execute('''
                INSERT INTO order_history (order_number, status, changed_by)
                VALUES ($1, $2, $3)
            ''', order_number, status, changed_by)

    @staticmethod
    async def assign_master(order_number: str, master_id: int):
        async with Database.pool.acquire() as conn:
            await conn.execute('''
                UPDATE orders 
                SET master_id = $1, status = 'in_progress', updated_at = NOW()
                WHERE order_number = $2
            ''', master_id, order_number)
            
            await conn.execute('''
                UPDATE masters 
                SET is_busy = TRUE, total_orders = total_orders + 1
                WHERE user_id = $1
            ''', master_id)
            
            await conn.execute('''
                INSERT INTO order_history (order_number, status, changed_by)
                VALUES ($1, 'in_progress', $2)
            ''', order_number, master_id)

    @staticmethod
    async def rate(order_number: str, rating: int, review: str = None):
        async with Database.pool.acquire() as conn:
            await conn.execute('''
                UPDATE orders 
                SET rating = $1, review = $2, updated_at = NOW()
                WHERE order_number = $3
            ''', rating, review, order_number)
            
            # Update master rating
            order = await conn.fetchrow('SELECT master_id FROM orders WHERE order_number = $1', order_number)
            if order and order['master_id']:
                avg_rating = await conn.fetchval('''
                    SELECT AVG(rating) FROM orders 
                    WHERE master_id = $1 AND rating > 0
                ''', order['master_id'])
                
                if avg_rating:
                    await conn.execute('''
                        UPDATE masters 
                        SET rating = $1
                        WHERE user_id = $2
                    ''', float(avg_rating), order['master_id'])


class MasterDB:
    @staticmethod
    async def get_by_id(user_id: int) -> Optional[dict]:
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT * FROM masters WHERE user_id = $1', user_id)
            return dict(master) if master else None

    @staticmethod
    async def get_all() -> List[dict]:
        async with Database.pool.acquire() as conn:
            masters = await conn.fetch('''
                SELECT m.*, COUNT(o.id) as active_orders
                FROM masters m
                LEFT JOIN orders o ON m.user_id = o.master_id AND o.status IN ('accepted', 'in_progress')
                GROUP BY m.user_id
                ORDER BY m.rating DESC
            ''')
            return [dict(master) for master in masters]

    @staticmethod
    async def get_available() -> List[dict]:
        async with Database.pool.acquire() as conn:
            masters = await conn.fetch('''
                SELECT m.*, COUNT(o.id) as active_orders
                FROM masters m
                LEFT JOIN orders o ON m.user_id = o.master_id AND o.status IN ('accepted', 'in_progress')
                WHERE m.is_online = TRUE AND m.is_busy = FALSE
                GROUP BY m.user_id
                ORDER BY m.rating DESC
            ''')
            return [dict(master) for master in masters]

    @staticmethod
    async def toggle_online(user_id: int) -> bool:
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT is_online FROM masters WHERE user_id = $1', user_id)
            if not master:
                return False
            new_status = not master['is_online']
            await conn.execute('''
                UPDATE masters SET is_online = $1 WHERE user_id = $2
            ''', new_status, user_id)
            return new_status

    @staticmethod
    async def toggle_busy(user_id: int) -> bool:
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT is_busy FROM masters WHERE user_id = $1', user_id)
            if not master:
                return False
            new_status = not master['is_busy']
            await conn.execute('''
                UPDATE masters SET is_busy = $1 WHERE user_id = $2
            ''', new_status, user_id)
            return new_status

    @staticmethod
    async def add(user_id: int, full_name: str, phone: str = None):
        async with Database.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, full_name, phone, role)
                VALUES ($1, $2, $3, 'master')
                ON CONFLICT (user_id) DO UPDATE
                SET full_name = $2, phone = $3, role = 'master'
            ''', user_id, full_name, phone)
            
            await conn.execute('''
                INSERT INTO masters (user_id, full_name, phone)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO UPDATE
                SET full_name = $2, phone = $3
            ''', user_id, full_name, phone)

    @staticmethod
    async def remove(user_id: int):
        async with Database.pool.acquire() as conn:
            await conn.execute('DELETE FROM masters WHERE user_id = $1', user_id)
            await conn.execute('''
                UPDATE users SET role = 'user' 
                WHERE user_id = $1 AND role = 'master'
            ''', user_id)


class DispatcherDB:
    @staticmethod
    async def add(user_id: int, full_name: str):
        async with Database.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, full_name, role)
                VALUES ($1, $2, 'dispatcher')
                ON CONFLICT (user_id) DO UPDATE
                SET full_name = $2, role = 'dispatcher'
            ''', user_id, full_name)
            
            await conn.execute('''
                INSERT INTO dispatchers (user_id, full_name)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE
                SET full_name = $2
            ''', user_id, full_name)

    @staticmethod
    async def remove(user_id: int):
        async with Database.pool.acquire() as conn:
            await conn.execute('DELETE FROM dispatchers WHERE user_id = $1', user_id)
            await conn.execute('''
                UPDATE users SET role = 'user' 
                WHERE user_id = $1 AND role = 'dispatcher'
            ''', user_id)


# ============================================================
# MESSAGE HELPER
# ============================================================

class MessageHelper:
    @staticmethod
    def order_info(order: dict) -> str:
        status = ORDER_STATUSES.get(order['status'], {'emoji': '📌', 'name': order['status']})
        
        text = f"""
{status['emoji']} **Буюртма маълумотлари**

🆔 Рақам: `{order['order_number']}`
🛠 Хизмат: {order['service']}
📍 Манзил: {order['address']}
📞 Телефон: {order['phone']}
📌 Ҳолат: {status['name']}
"""
        
        if order.get('description'):
            text += f"\n📝 Изоҳ: {order['description']}"
        
        if order.get('master_name'):
            text += f"\n👨‍🔧 Уста: {order['master_name']}"
        
        if order.get('user_name'):
            text += f"\n👤 Мижоз: {order['user_name']}"
        
        if order.get('rating', 0) > 0:
            text += f"\n⭐ Рейтинг: {'⭐' * order['rating']}"
            if order.get('review'):
                text += f"\n💬 Фикр: {order['review']}"
        
        text += f"\n\n📅 {order['created_at'].strftime('%d.%m.%Y %H:%M')}"
        
        return text

    @staticmethod
    def order_short(order: dict) -> str:
        status = ORDER_STATUSES.get(order['status'], {'emoji': '📌'})
        return f"{status['emoji']} {order['order_number']} | {order['service'][:20]}"


# ============================================================
# BOT HANDLERS
# ============================================================

class BotHandlers:
    def __init__(self, application: Application):
        self.app = application
        self.setup_handlers()

    def setup_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("back", self.back))
        self.app.add_handler(CommandHandler("stats", self.stats))
        
        # Order conversation
        order_conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex('^📝 Буюртма бериш$'), self.order_start)],
            states={
                1: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_service)],
                2: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_address)],
                3: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_phone)],
                4: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.order_description)],
            },
            fallbacks=[MessageHandler(filters.Regex('^🔙 Бекор қилиш$'), self.order_cancel)]
        )
        self.app.add_handler(order_conv)
        
        # Main menu
        self.app.add_handler(MessageHandler(filters.Regex('^📋 Менинг буюртмаларим$'), self.my_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^👨‍🔧 Усталар$'), self.masters_list))
        self.app.add_handler(MessageHandler(filters.Regex('^📊 Статистика$'), self.stats))
        self.app.add_handler(MessageHandler(filters.Regex('^📞 Диспетчерга мурожаат$'), self.contact_dispatcher))
        self.app.add_handler(MessageHandler(filters.Regex('^👤 Профиль$'), self.profile))
        
        # Dispatcher panel
        self.app.add_handler(MessageHandler(filters.Regex('^📋 Диспетчер панели$'), self.dispatcher_panel))
        self.app.add_handler(MessageHandler(filters.Regex('^📋 Барча буюртмалар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^🆕 Янги буюртмалар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^🟡 Қабул қилинганлар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^🔵 Ишдаги буюртмалар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^✅ Якунланганлар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^❌ Бекор қилинганлар$'), self.show_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^👨‍🔧 Усталар статистикаси$'), self.masters_stats))
        self.app.add_handler(MessageHandler(filters.Regex('^📢 Хабар юбориш$'), self.broadcast))
        
        # Master mode
        self.app.add_handler(MessageHandler(filters.Regex('^📋 Менинг буюртмаларим$'), self.master_orders))
        self.app.add_handler(MessageHandler(filters.Regex('^📊 Менинг статистикам$'), self.master_stats))
        self.app.add_handler(MessageHandler(filters.Regex('^🟢 Онлайн$'), self.toggle_online))
        self.app.add_handler(MessageHandler(filters.Regex('^🔴 Банд$'), self.toggle_busy))
        
        # Admin panel
        self.app.add_handler(MessageHandler(filters.Regex('^👑 Админ панели$'), self.admin_panel))
        self.app.add_handler(MessageHandler(filters.Regex('^👨‍🔧 Уста қўшиш$'), self.add_master))
        self.app.add_handler(MessageHandler(filters.Regex('^👨‍🔧 Уста ўчириш$'), self.remove_master))
        self.app.add_handler(MessageHandler(filters.Regex('^👤 Диспетчер қўшиш$'), self.add_dispatcher))
        self.app.add_handler(MessageHandler(filters.Regex('^👤 Диспетчер ўчириш$'), self.remove_dispatcher))
        self.app.add_handler(MessageHandler(filters.Regex('^📊 Умумий статистика$'), self.admin_stats))
        
        # Back
        self.app.add_handler(MessageHandler(filters.Regex('^🔙 Орқага$'), self.back))
        
        # Callbacks
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Unknown
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown))
        
        # Error
        self.app.add_error_handler(self.error_handler)

    # ==================== COMMANDS ====================
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        
        # Get or create user
        await UserDB.get_or_create(user_id, user.username, user.full_name)
        
        # Get role
        role = await UserDB.get_role(user_id)
        context.user_data['role'] = role
        
        text = f"""
👋 Ассалому алейкум, {user.full_name}!

📝 USTA24 буюртма тизимига хуш келибсиз.
🎭 Ролингиз: {role}

🔽 Менюдан танланг:
"""
        await update.message.reply_text(
            text,
            reply_markup=Keyboards.main(role)
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = """
📚 **USTA24 Ёрдам**

**🤵 Мижоз:**
• 📝 Буюртма бериш
• 📋 Буюртмаларни кузатиш
• 👤 Профиль

**👨‍🔧 Уста:**
• 📋 Буюртма олиш
• 🟢 Онлайн/Банд ҳолати
• 📊 Статистика

**📞 Диспетчер:**
• 📋 Барча буюртмалар
• 👨‍🔧 Усталарга юбориш
• 📊 Статистика

**👑 Админ:**
• 👨‍🔧 Усталарни бошқариш
• 👤 Диспетчерларни бошқариш
• 📢 Хабар юбориш

❓ Саволлар: @admin
"""
        await update.message.reply_text(text, parse_mode='Markdown')

    async def back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        role = context.user_data.get('role', 'user')
        await update.message.reply_text(
            "🏠 Асосий меню",
            reply_markup=Keyboards.main(role)
        )

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with Database.pool.acquire() as conn:
            total = await conn.fetchval('SELECT COUNT(*) FROM orders')
            new = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'new')
            accepted = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'accepted')
            in_progress = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'in_progress')
            completed = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'completed')
            cancelled = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'cancelled')
            rejected = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'rejected')
            
            today = datetime.now().date()
            today_orders = await conn.fetchval(
                'SELECT COUNT(*) FROM orders WHERE created_at::date = $1',
                today
            )
            
            masters_count = await conn.fetchval('SELECT COUNT(*) FROM masters')
            users_count = await conn.fetchval('SELECT COUNT(*) FROM users WHERE role = $1', 'user')
        
        text = f"""
📊 **Буюртма статистикаси**

📋 Жами: {total}
🆕 Янги: {new}
🟡 Қабул қилинган: {accepted}
🔵 Иш жараёнида: {in_progress}
✅ Якунланган: {completed}
❌ Бекор қилинган: {cancelled}
🚫 Рад этилган: {rejected}

👤 Мижозлар: {users_count}
👨‍🔧 Усталар: {masters_count}

📅 Бугун: {today_orders} та буюртма
"""
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== ORDER ====================
    
    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['order_data'] = {}
        await update.message.reply_text(
            "🛠 **Хизмат турини киритинг:**\n"
            "Мисол: Smartfon таъмирлаш",
            parse_mode='Markdown',
            reply_markup=Keyboards.cancel()
        )
        return 1

    async def order_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        
        context.user_data['order_data']['service'] = text
        await update.message.reply_text(
            "📍 **Манзилингизни киритинг:**",
            parse_mode='Markdown',
            reply_markup=Keyboards.cancel()
        )
        return 2

    async def order_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        
        context.user_data['order_data']['address'] = text
        await update.message.reply_text(
            "📞 **Телефон рақамингизни киритинг:**",
            parse_mode='Markdown',
            reply_markup=Keyboards.cancel()
        )
        return 3

    async def order_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        
        context.user_data['order_data']['phone'] = text
        await update.message.reply_text(
            "📝 **Қўшимча маълумотлар:**\n"
            "(Ўтказиб юбориш мумкин)",
            parse_mode='Markdown',
            reply_markup=Keyboards.skip()
        )
        return 4

    async def order_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        
        description = '' if text == '⏩ Ўтказиб юбориш' else text
        data = context.user_data['order_data']
        
        # Create order
        order = await OrderDB.create(
            update.effective_user.id,
            data['service'],
            data['address'],
            data['phone'],
            description
        )
        
        # Notify user
        await update.message.reply_text(
            f"✅ Буюртмангиз қабул қилинди!\n"
            f"🆔 Рақами: {order['order_number']}\n\n"
            f"📝 Ҳолатни «Менинг буюртмаларим» орқали кузатинг.",
            reply_markup=Keyboards.main(context.user_data.get('role', 'user'))
        )
        
        # Notify dispatcher
        order_info = MessageHelper.order_info(order)
        await update.message.bot.send_message(
            DISPATCHER_ID or ADMIN_ID,
            f"📝 **ЯНГИ БУЮРТМА!**\n{order_info}",
            parse_mode='Markdown',
            reply_markup=Keyboards.order_actions(order['order_number'])
        )
        
        # Notify masters group
        await update.message.bot.send_message(
            MASTERS_GROUP_ID,
            f"🆕 **Янги буюртма!**\n"
            f"🆔 {order['order_number']}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address']}\n\n"
            f"✅ Буюртмани олиш учун /take_{order['order_number']}",
            parse_mode='Markdown',
            reply_markup=Keyboards.master_actions(order['order_number'])
        )
        
        context.user_data['order_data'] = {}
        return ConversationHandler.END

    async def order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❌ Буюртма бекор қилинди.",
            reply_markup=Keyboards.main(context.user_data.get('role', 'user'))
        )
        context.user_data['order_data'] = {}
        return ConversationHandler.END

    # ==================== MY ORDERS ====================
    
    async def my_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        orders = await OrderDB.get_user_orders(user_id)
        
        if not orders:
            await update.message.reply_text(
                "📭 Сизда буюртмалар йўқ.\n"
                "📝 Янги буюртма бериш учун «Буюртма бериш» тугмасини босинг.",
                reply_markup=Keyboards.main(context.user_data.get('role', 'user'))
            )
            return
        
        text = "📋 **Сизнинг буюртмаларингиз:**\n\n"
        for order in orders[:5]:
            text += f"{MessageHelper.order_short(order)}\n"
        
        if len(orders) > 5:
            text += f"\n📊 Жами: {len(orders)} та буюртма"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== MASTERS ====================
    
    async def masters_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        masters = await MasterDB.get_all()
        
        if not masters:
            await update.message.reply_text("👨‍🔧 Ҳозирча усталар мавжуд эмас.")
            return
        
        text = "👨‍🔧 **Усталар рўйхати:**\n\n"
        for master in masters[:10]:
            status = "🟢 Онлайн" if master['is_online'] else "🔴 Офлайн"
            busy = "🔴 Банд" if master['is_busy'] else "🟢 Бўш"
            text += f"👤 {master['full_name']}\n"
            text += f"⭐ Рейтинг: {master['rating']:.1f}\n"
            text += f"📊 Буюртмалар: {master['total_orders']}\n"
            text += f"📌 {status} | {busy}\n"
            text += "-" * 30 + "\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== PROFILE ====================
    
    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        role = context.user_data.get('role', 'user')
        
        text = f"""
👤 **Профиль**

🆔 ID: `{user.id}`
👤 Исм: {user.full_name}
📛 Юзернейм: @{user.username or 'Йўқ'}
🎭 Рол: {role}
"""
        
        if role == 'master':
            master = await MasterDB.get_by_id(user.id)
            if master:
                text += f"""
👨‍🔧 **Уста маълумотлари**
⭐ Рейтинг: {master['rating']:.1f}
📊 Буюртмалар: {master['total_orders']}
🟢 Ҳолат: {'Онлайн' if master['is_online'] else 'Офлайн'}
{'🔴 Банд' if master['is_busy'] else '🟢 Бўш'}
"""
        
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== DISPATCHER PANEL ====================
    
    async def dispatcher_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        role = context.user_data.get('role', 'user')
        if role not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "📋 Диспетчер панели",
            reply_markup=Keyboards.dispatcher()
        )

    async def show_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        role = context.user_data.get('role', 'user')
        if role not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        text = update.message.text
        status_map = {
            '📋 Барча буюртмалар': None,
            '🆕 Янги буюртмалар': 'new',
            '🟡 Қабул қилинганлар': 'accepted',
            '🔵 Ишдаги буюртмалар': 'in_progress',
            '✅ Якунланганлар': 'completed',
            '❌ Бекор қилинганлар': 'cancelled'
        }
        
        status = status_map.get(text)
        orders = await OrderDB.get_by_status(status)
        
        if not orders:
            await update.message.reply_text("📭 Буюртмалар топилмади.")
            return
        
        result = f"📋 **{text}**\n\n"
        for order in orders[:10]:
            result += f"{MessageHelper.order_short(order)}\n"
        
        if len(orders) > 10:
            result += f"\n📊 Жами: {len(orders)} та буюртма"
        
        await update.message.reply_text(result, parse_mode='Markdown')

    # ==================== MASTER MODE ====================
    
    async def master_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        orders = await OrderDB.get_master_orders(user_id)
        
        if not orders:
            await update.message.reply_text("📭 Сизга буюртмалар бириктирилмаган.")
            return
        
        text = "📋 **Менинг буюртмаларим:**\n\n"
        for order in orders[:5]:
            text += f"{MessageHelper.order_short(order)}\n"
        
        if len(orders) > 5:
            text += f"\n📊 Жами: {len(orders)} та буюртма"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    async def master_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        master = await MasterDB.get_by_id(user_id)
        
        if not master:
            await update.message.reply_text("❌ Сиз уста эмассиз!")
            return
        
        async with Database.pool.acquire() as conn:
            completed = await conn.fetchval(
                'SELECT COUNT(*) FROM orders WHERE master_id = $1 AND status = $1',
                user_id, 'completed'
            )
            active = await conn.fetchval(
                'SELECT COUNT(*) FROM orders WHERE master_id = $1 AND status IN ($1, $2)',
                user_id, 'accepted', 'in_progress'
            )
        
        text = f"""
📊 **Менинг статистикам**

👤 Уста: {master['full_name']}
⭐ Рейтинг: {master['rating']:.1f}
📊 Жами буюртмалар: {master['total_orders']}
✅ Якунланган: {completed}
🔵 Фаол буюртмалар: {active}
🟢 Ҳолат: {'Онлайн' if master['is_online'] else 'Офлайн'}
{'🔴 Банд' if master['is_busy'] else '🟢 Бўш'}
"""
        await update.message.reply_text(text, parse_mode='Markdown')

    async def toggle_online(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        new_status = await MasterDB.toggle_online(user_id)
        
        status = "🟢 Онлайн" if new_status else "🔴 Офлайн"
        await update.message.reply_text(f"✅ Ҳолат ўзгартирилди: {status}")

    async def toggle_busy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        new_status = await MasterDB.toggle_busy(user_id)
        
        status = "🔴 Банд" if new_status else "🟢 Бўш"
        await update.message.reply_text(f"✅ Ҳолат ўзгартирилди: {status}")

    # ==================== ADMIN PANEL ====================
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "👑 Админ панели",
            reply_markup=Keyboards.admin()
        )

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        async with Database.pool.acquire() as conn:
            total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
            total_masters = await conn.fetchval('SELECT COUNT(*) FROM masters')
            total_dispatchers = await conn.fetchval('SELECT COUNT(*) FROM dispatchers')
            total_orders = await conn.fetchval('SELECT COUNT(*) FROM orders')
            completed_orders = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'completed')
            
            today = datetime.now().date()
            today_orders = await conn.fetchval(
                'SELECT COUNT(*) FROM orders WHERE created_at::date = $1',
                today
            )
            
            avg_rating = await conn.fetchval(
                'SELECT AVG(rating) FROM orders WHERE rating > 0'
            )
        
        text = f"""
👑 **Умумий статистика**

👤 Фойдаланувчилар: {total_users}
👨‍🔧 Усталар: {total_masters}
📞 Диспетчерлар: {total_dispatchers}

📋 Буюртмалар: {total_orders}
✅ Якунланган: {completed_orders}
📅 Бугун: {today_orders}

⭐ Ўртача рейтинг: {avg_rating or 0:.1f}
"""
        await update.message.reply_text(text, parse_mode='Markdown')

    async def add_master(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "👨‍🔧 **Уста қўшиш**\n\n"
            "Устанинг ID сини ва тўлиқ исмини киритинг:\n"
            "Мисол: `123456789 Алишер Алиев`",
            parse_mode='Markdown'
        )
        context.user_data['admin_action'] = 'add_master'

    async def remove_master(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "👨‍🔧 **Уста ўчириш**\n\n"
            "Устанинг ID сини киритинг:\n"
            "Мисол: `123456789`",
            parse_mode='Markdown'
        )
        context.user_data['admin_action'] = 'remove_master'

    async def add_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "👤 **Диспетчер қўшиш**\n\n"
            "Диспетчернинг ID сини ва тўлиқ исмини киритинг:\n"
            "Мисол: `987654321 Дилафрўз Исмоилова`",
            parse_mode='Markdown'
        )
        context.user_data['admin_action'] = 'add_dispatcher'

    async def remove_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "👤 **Диспетчер ўчириш**\n\n"
            "Диспетчернинг ID сини киритинг:\n"
            "Мисол: `987654321`",
            parse_mode='Markdown'
        )
        context.user_data['admin_action'] = 'remove_dispatcher'

    # ==================== BROADCAST ====================
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        role = context.user_data.get('role', 'user')
        
        if role not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Сизда ҳуқуқ йўқ!")
            return
        
        await update.message.reply_text(
            "📢 **Хабар юбориш**\n\n"
            "Юбормоқчи бўлган хабарингизни киритинг:",
            parse_mode='Markdown'
        )
        context.user_data['broadcast'] = True

    # ==================== CONTACT ====================
    
    async def contact_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📞 **Диспетчер билан боғланиш**\n\n"
            "Савол ёки мурожаатингизни ёзинг. Диспетчер сизга жавоб беради.",
            reply_markup=Keyboards.cancel()
        )
        context.user_data['contact_dispatcher'] = True

    # ==================== CALLBACKS ====================
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        parts = data.split('_')
        action = parts[0]
        order_number = parts[1] if len(parts) > 1 else None
        
        if action == 'accept':
            await OrderDB.update_status(order_number, 'accepted', query.from_user.id)
            await query.edit_message_text(f"✅ Буюртма {order_number} қабул қилинди!")
            
            # Notify user
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(
                    order['user_id'],
                    f"✅ Буюртмангиз {order_number} қабул қилинди!\n📌 Ҳолат: Қабул қилинган"
                )
        
        elif action == 'reject':
            await OrderDB.update_status(order_number, 'rejected', query.from_user.id)
            await query.edit_message_text(f"🚫 Буюртма {order_number} рад этилди!")
            
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(
                    order['user_id'],
                    f"🚫 Буюртмангиз {order_number} рад этилди.\n📞 Диспетчер билан боғланинг."
                )
        
        elif action == 'take':
            master_id = query.from_user.id
            
            # Check if master exists and is available
            master = await MasterDB.get_by_id(master_id)
            if not master:
                await query.edit_message_text("❌ Сиз уста эмассиз!")
                return
            
            if master['is_busy']:
                await query.edit_message_text("❌ Сиз бандсиз! Аввал буюртмангизни тугатинг.")
                return
            
            if not master['is_online']:
                await query.edit_message_text("❌ Сиз офлайнсиз! Аввал онлайн режимга ўтинг.")
                return
            
            # Assign order
            await OrderDB.assign_master(order_number, master_id)
            await query.edit_message_text(f"✅ Буюртма {order_number} сизга бириктирилди!")
            
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(
                    order['user_id'],
                    f"👨‍🔧 Буюртмангиз {order_number} устага бириктирилди!\n📌 Ҳолат: Иш жараёнида"
                )
        
        elif action == 'complete':
            await OrderDB.update_status(order_number, 'completed', query.from_user.id)
            await query.edit_message_text(f"✅ Буюртма {order_number} якунланди!")
            
            order = await OrderDB.get_by_number(order_number)
            if order:
                # Free master
                if order['master_id']:
                    await MasterDB.toggle_busy(order['master_id'])
                
                # Ask for rating
                await query.message.bot.send_message(
                    order['user_id'],
                    f"✅ Буюртмангиз {order_number} якунланди!\n\n"
                    f"⭐ Устани баҳолаш учун тугмани босинг:",
                    reply_markup=Keyboards.rate_actions(order_number)
                )
        
        elif action == 'rate':
            rating = int(parts[2])
            await OrderDB.rate(order_number, rating)
            await query.edit_message_text(f"⭐ Баҳоланди! Рейтинг: {rating}")
        
        elif action == 'call':
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.edit_message_text(
                    f"📞 Мижоз билан боғланиш\n"
                    f"Телефон: {order['phone']}\n"
                    f"Манзил: {order['address']}"
                )

    # ==================== BROADCAST MESSAGES ====================
    
    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if context.user_data.get('broadcast'):
            # Send to all users
            async with Database.pool.acquire() as conn:
                users = await conn.fetch('SELECT user_id FROM users')
            
            sent = 0
            for user in users:
                try:
                    await update.message.bot.send_message(user['user_id'], text)
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Failed to send to {user['user_id']}: {e}")
            
            await update.message.reply_text(
                f"✅ Хабар юборилди!\n"
                f"📊 Жами: {sent} та фойдаланувчига"
            )
            context.user_data['broadcast'] = False
            return
        
        if context.user_data.get('contact_dispatcher'):
            # Send to dispatcher
            msg = f"📞 **Мижоздан хабар**\n\n{text}"
            
            if DISPATCHER_ID:
                await update.message.bot.send_message(DISPATCHER_ID, msg, parse_mode='Markdown')
                await update.message.reply_text(
                    "✅ Хабарингиз диспетчерга юборилди!",
                    reply_markup=Keyboards.main(context.user_data.get('role', 'user'))
                )
            else:
                await update.message.reply_text(
                    "❌ Диспетчер мавжуд эмас. Админга хабар берилди."
                )
                await update.message.bot.send_message(ADMIN_ID, msg, parse_mode='Markdown')
            
            context.user_data['contact_dispatcher'] = False
            return
        
        if context.user_data.get('admin_action'):
            action = context.user_data['admin_action']
            parts = text.strip().split()
            
            if len(parts) < 2 and action not in ['remove_master', 'remove_dispatcher']:
                await update.message.reply_text("❌ ID ва исм киритинг! Мисол: `123456789 Алишер`", parse_mode='Markdown')
                return
            
            try:
                target_id = int(parts[0])
            except ValueError:
                await update.message.reply_text("❌ ID сон бўлиши керак!")
                return
            
            if action == 'add_master':
                full_name = ' '.join(parts[1:])
                await MasterDB.add(target_id, full_name)
                await update.message.reply_text(f"✅ Уста қўшилди: {full_name}")
            
            elif action == 'remove_master':
                await MasterDB.remove(target_id)
                await update.message.reply_text(f"✅ Уста ўчирилди: {target_id}")
            
            elif action == 'add_dispatcher':
                full_name = ' '.join(parts[1:])
                await DispatcherDB.add(target_id, full_name)
                await update.message.reply_text(f"✅ Диспетчер қўшилди: {full_name}")
            
            elif action == 'remove_dispatcher':
                await DispatcherDB.remove(target_id)
                await update.message.reply_text(f"✅ Диспетчер ўчирилди: {target_id}")
            
            context.user_data['admin_action'] = None
            return

    # ==================== UNKNOWN ====================
    
    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Check for admin actions
        if context.user_data.get('admin_action'):
            await self.broadcast_message(update, context)
            return
        
        if context.user_data.get('broadcast'):
            await self.broadcast_message(update, context)
            return
        
        if context.user_data.get('contact_dispatcher'):
            await self.broadcast_message(update, context)
            return
        
        await update.message.reply_text(
            "❌ Тушунарсиз команда.\n"
            "📋 Менюдан танланг ёки /start босинг."
        )

    # ==================== ERROR HANDLER ====================
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Хатолик: {context.error}")
        
        try:
            await update.message.reply_text(
                "❌ Техник хатолик юз берди.\n"
                "Администраторга хабар берилди."
            )
        except:
            pass


# ============================================================
# MAIN
# ============================================================

async def main():
    # Initialize database
    await Database.init()
    
    # Create bot application
    application = Application.builder().token(TOKEN).build()
    
    # Setup handlers
    BotHandlers(application)
    
    # Start bot
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    logger.info("🚀 BOT ISHGA TUSHDI!")
    
    # Start Flask in background
    def run_flask():
        flask_app.run(host="0.0.0.0", port=PORT, debug=False)
    
    Thread(target=run_flask, daemon=True).start()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("🛑 Bot to'xtatilmoqda...")
    finally:
        await Database.close()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
