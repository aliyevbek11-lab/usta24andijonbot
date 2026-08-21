import os
import asyncio
import logging
from threading import Thread
from datetime import datetime
import uuid
from typing import Dict, List, Optional, Any

import asyncpg
from asyncpg import Pool

from flask import Flask, jsonify, request

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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Optional - agar bo'lmasa polling ishlaydi
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

# Webhook URL optional
if WEBHOOK_URL:
    logger.info(f"✅ Webhook URL: {WEBHOOK_URL}")
else:
    logger.info("ℹ️ WEBHOOK_URL topilmadi, polling rejimida ishlaydi")


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
_application = None

@flask_app.route('/')
def health():
    return jsonify({
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'service': 'USTA24 Orders Bot',
        'mode': 'webhook' if WEBHOOK_URL else 'polling'
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

@flask_app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    """Telegram webhook endpoint"""
    global _application
    
    if not _application:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data'}), 400
        
        update = Update.de_json(data, _application.bot)
        await _application.process_update(update)
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500

@flask_app.route('/set_webhook', methods=['GET', 'POST'])
async def set_webhook():
    """Manually set webhook"""
    global _application
    
    if not _application:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    if not WEBHOOK_URL:
        return jsonify({'error': 'WEBHOOK_URL not set'}), 400
    
    try:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        await _application.bot.set_webhook(webhook_url)
        return jsonify({
            'status': 'ok',
            'webhook_url': webhook_url,
            'webhook_info': await _application.bot.get_webhook_info()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/delete_webhook', methods=['GET', 'POST'])
async def delete_webhook():
    """Delete webhook"""
    global _application
    
    if not _application:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        await _application.bot.delete_webhook()
        return jsonify({'status': 'ok', 'message': 'Webhook deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@flask_app.route('/webhook_info')
async def webhook_info():
    """Get webhook info"""
    global _application
    
    if not _application:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        info = await _application.bot.get_webhook_info()
        return jsonify({
            'url': info.url,
            'has_custom_certificate': info.has_custom_certificate,
            'pending_update_count': info.pending_update_count,
            'last_error_date': info.last_error_date,
            'last_error_message': info.last_error_message
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# DATABASE (qisqa versiya)
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
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS dispatchers (
                    user_id BIGINT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')
            
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
            
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_master_id ON orders(master_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_masters_online ON masters(is_online)')
            
            logger.info("✅ Tables created")


# ============================================================
# DATABASE HELPERS (qisqa)
# ============================================================

ORDER_STATUSES = {
    'new': {'emoji': '🆕', 'name': 'Янги'},
    'accepted': {'emoji': '🟡', 'name': 'Қабул қилинган'},
    'in_progress': {'emoji': '🔵', 'name': 'Иш жараёнида'},
    'completed': {'emoji': '✅', 'name': 'Якунланган'},
    'cancelled': {'emoji': '❌', 'name': 'Бекор қилинган'},
    'rejected': {'emoji': '🚫', 'name': 'Рад этилган'}
}

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
            
            order = await conn.fetchrow('SELECT master_id FROM orders WHERE order_number = $1', order_number)
            if order and order['master_id']:
                avg_rating = await conn.fetchval('''
                    SELECT AVG(rating) FROM orders 
                    WHERE master_id = $1 AND rating > 0
                ''', order['master_id'])
                
                if avg_rating:
                    await conn.execute('''
                        UPDATE masters SET rating = $1 WHERE user_id = $2
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
    async def toggle_online(user_id: int) -> bool:
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT is_online FROM masters WHERE user_id = $1', user_id)
            if not master:
                return False
            new_status = not master['is_online']
            await conn.execute('UPDATE masters SET is_online = $1 WHERE user_id = $2', new_status, user_id)
            return new_status

    @staticmethod
    async def toggle_busy(user_id: int) -> bool:
        async with Database.pool.acquire() as conn:
            master = await conn.fetchrow('SELECT is_busy FROM masters WHERE user_id = $1', user_id)
            if not master:
                return False
            new_status = not master['is_busy']
            await conn.execute('UPDATE masters SET is_busy = $1 WHERE user_id = $2', new_status, user_id)
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
            await conn.execute('UPDATE users SET role = "user" WHERE user_id = $1 AND role = "master"', user_id)


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
            await conn.execute('UPDATE users SET role = "user" WHERE user_id = $1 AND role = "dispatcher"', user_id)


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
# BOT HANDLERS (to'liq)
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
        await UserDB.get_or_create(user.id, user.username, user.full_name)
        
        role = await UserDB.get_role(user.id)
        context.user_data['role'] = role
        
        await update.message.reply_text(
            f"👋 Ассалому алейкум, {user.full_name}!\n\n📝 USTA24 тизимига хуш келибсиз.\n🎭 Рол: {role}",
            reply_markup=Keyboards.main(role)
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 **Ёрдам**\n\n🤵 Мижоз: Буюртма бериш, кузатиш\n👨‍🔧 Уста: Буюртма олиш, ҳолат\n📞 Диспетчер: Бошқариш\n👑 Админ: Тўлиқ бошқарув",
            parse_mode='Markdown'
        )

    async def back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        role = context.user_data.get('role', 'user')
        await update.message.reply_text("🏠 Асосий меню", reply_markup=Keyboards.main(role))

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with Database.pool.acquire() as conn:
            total = await conn.fetchval('SELECT COUNT(*) FROM orders')
            new = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'new')
            completed = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'completed')
            today = datetime.now().date()
            today_orders = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE created_at::date = $1', today)
        
        await update.message.reply_text(
            f"📊 **Статистика**\n\n📋 Жами: {total}\n🆕 Янги: {new}\n✅ Якунланган: {completed}\n📅 Бугун: {today_orders}",
            parse_mode='Markdown'
        )

    # ==================== ORDER ====================
    
    async def order_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['order_data'] = {}
        await update.message.reply_text("🛠 **Хизмат тури:**", parse_mode='Markdown', reply_markup=Keyboards.cancel())
        return 1

    async def order_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        context.user_data['order_data']['service'] = update.message.text
        await update.message.reply_text("📍 **Манзил:**", parse_mode='Markdown')
        return 2

    async def order_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        context.user_data['order_data']['address'] = update.message.text
        await update.message.reply_text("📞 **Телефон:**", parse_mode='Markdown')
        return 3

    async def order_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        context.user_data['order_data']['phone'] = update.message.text
        await update.message.reply_text("📝 **Изоҳ:** (Ўтказиб юбориш)", reply_markup=Keyboards.skip())
        return 4

    async def order_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text == '🔙 Бекор қилиш':
            return await self.order_cancel(update, context)
        
        description = '' if update.message.text == '⏩ Ўтказиб юбориш' else update.message.text
        data = context.user_data['order_data']
        
        order = await OrderDB.create(
            update.effective_user.id,
            data['service'], data['address'], data['phone'], description
        )
        
        await update.message.reply_text(
            f"✅ Буюртма қабул қилинди!\n🆔 {order['order_number']}",
            reply_markup=Keyboards.main(context.user_data.get('role', 'user'))
        )
        
        # Notify dispatcher and masters
        order_info = MessageHelper.order_info(order)
        await update.message.bot.send_message(
            DISPATCHER_ID or ADMIN_ID,
            f"📝 **ЯНГИ БУЮРТМА!**\n{order_info}",
            parse_mode='Markdown',
            reply_markup=Keyboards.order_actions(order['order_number'])
        )
        
        await update.message.bot.send_message(
            MASTERS_GROUP_ID,
            f"🆕 **Янги буюртма!**\n🆔 {order['order_number']}\n🛠 {order['service']}\n📍 {order['address']}",
            parse_mode='Markdown',
            reply_markup=Keyboards.master_actions(order['order_number'])
        )
        
        context.user_data['order_data'] = {}
        return ConversationHandler.END

    async def order_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Бекор қилинди.", reply_markup=Keyboards.main(context.user_data.get('role', 'user')))
        context.user_data['order_data'] = {}
        return ConversationHandler.END

    # ==================== MY ORDERS ====================
    
    async def my_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        orders = await OrderDB.get_user_orders(update.effective_user.id)
        if not orders:
            await update.message.reply_text("📭 Буюртмалар йўқ.")
            return
        
        text = "📋 **Буюртмаларим**\n\n"
        for order in orders[:5]:
            text += f"{MessageHelper.order_short(order)}\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== MASTERS ====================
    
    async def masters_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        masters = await MasterDB.get_all()
        if not masters:
            await update.message.reply_text("👨‍🔧 Усталар йўқ.")
            return
        
        text = "👨‍🔧 **Усталар**\n\n"
        for m in masters[:10]:
            text += f"👤 {m['full_name']}\n⭐ {m['rating']:.1f}\n🟢 {'Онлайн' if m['is_online'] else 'Офлайн'}\n---\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== PROFILE ====================
    
    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        role = context.user_data.get('role', 'user')
        text = f"👤 **Профиль**\n\n🆔 {user.id}\n👤 {user.full_name}\n🎭 Рол: {role}"
        
        if role == 'master':
            master = await MasterDB.get_by_id(user.id)
            if master:
                text += f"\n\n⭐ Рейтинг: {master['rating']:.1f}\n📊 Буюртмалар: {master['total_orders']}"
        
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== DISPATCHER PANEL ====================
    
    async def dispatcher_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('role') not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("📋 Диспетчер панели", reply_markup=Keyboards.dispatcher())

    async def show_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('role') not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        
        status_map = {
            '📋 Барча буюртмалар': None,
            '🆕 Янги буюртмалар': 'new',
            '🟡 Қабул қилинганлар': 'accepted',
            '🔵 Ишдаги буюртмалар': 'in_progress',
            '✅ Якунланганлар': 'completed',
        }
        
        status = status_map.get(update.message.text)
        orders = await OrderDB.get_by_status(status)
        
        if not orders:
            await update.message.reply_text("📭 Буюртмалар йўқ.")
            return
        
        text = f"📋 **{update.message.text}**\n\n"
        for order in orders[:10]:
            text += f"{MessageHelper.order_short(order)}\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== MASTER MODE ====================
    
    async def master_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        orders = await OrderDB.get_master_orders(update.effective_user.id)
        if not orders:
            await update.message.reply_text("📭 Буюртмалар йўқ.")
            return
        
        text = "📋 **Менинг буюртмаларим**\n\n"
        for order in orders[:5]:
            text += f"{MessageHelper.order_short(order)}\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    async def master_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        master = await MasterDB.get_by_id(update.effective_user.id)
        if not master:
            await update.message.reply_text("❌ Уста эмассиз!")
            return
        
        await update.message.reply_text(
            f"📊 **Менинг статистикам**\n\n⭐ Рейтинг: {master['rating']:.1f}\n📊 Жами: {master['total_orders']}\n🟢 {'Онлайн' if master['is_online'] else 'Офлайн'}",
            parse_mode='Markdown'
        )

    async def toggle_online(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status = await MasterDB.toggle_online(update.effective_user.id)
        await update.message.reply_text(f"✅ {'🟢 Онлайн' if status else '🔴 Офлайн'}")

    async def toggle_busy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status = await MasterDB.toggle_busy(update.effective_user.id)
        await update.message.reply_text(f"✅ {'🔴 Банд' if status else '🟢 Бўш'}")

    # ==================== ADMIN PANEL ====================
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("👑 Админ панели", reply_markup=Keyboards.admin())

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        
        async with Database.pool.acquire() as conn:
            users = await conn.fetchval('SELECT COUNT(*) FROM users')
            masters = await conn.fetchval('SELECT COUNT(*) FROM masters')
            orders = await conn.fetchval('SELECT COUNT(*) FROM orders')
            completed = await conn.fetchval('SELECT COUNT(*) FROM orders WHERE status = $1', 'completed')
        
        await update.message.reply_text(
            f"👑 **Умумий**\n\n👤 Фойдаланувчилар: {users}\n👨‍🔧 Усталар: {masters}\n📋 Буюртмалар: {orders}\n✅ Якунланган: {completed}",
            parse_mode='Markdown'
        )

    async def add_master(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("👨‍🔧 **Уста қўшиш**\nID ва исм: `123456789 Алишер`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_master'

    async def remove_master(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("👨‍🔧 **Уста ўчириш**\nID: `123456789`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'remove_master'

    async def add_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("👤 **Диспетчер қўшиш**\nID ва исм: `987654321 Дилафрўз`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'add_dispatcher'

    async def remove_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("👤 **Диспетчер ўчириш**\nID: `987654321`", parse_mode='Markdown')
        context.user_data['admin_action'] = 'remove_dispatcher'

    # ==================== BROADCAST ====================
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('role') not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        await update.message.reply_text("📢 **Хабар юбориш**\nХабарни киритинг:")
        context.user_data['broadcast'] = True

    # ==================== CONTACT ====================
    
    async def contact_dispatcher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("📞 **Диспетчерга ёзинг**", reply_markup=Keyboards.cancel())
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
            await query.edit_message_text(f"✅ {order_number} қабул қилинди!")
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(order['user_id'], f"✅ Буюртмангиз {order_number} қабул қилинди!")
        
        elif action == 'reject':
            await OrderDB.update_status(order_number, 'rejected', query.from_user.id)
            await query.edit_message_text(f"🚫 {order_number} рад этилди!")
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(order['user_id'], f"🚫 Буюртмангиз {order_number} рад этилди.")
        
        elif action == 'take':
            master = await MasterDB.get_by_id(query.from_user.id)
            if not master or master['is_busy'] or not master['is_online']:
                await query.edit_message_text("❌ Банд ёки офлайн!")
                return
            
            await OrderDB.assign_master(order_number, query.from_user.id)
            await query.edit_message_text(f"✅ {order_number} сизга бириктирилди!")
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.message.bot.send_message(order['user_id'], f"👨‍🔧 Буюртмангиз {order_number} устага бириктирилди!")
        
        elif action == 'complete':
            await OrderDB.update_status(order_number, 'completed', query.from_user.id)
            await query.edit_message_text(f"✅ {order_number} якунланди!")
            order = await OrderDB.get_by_number(order_number)
            if order and order['master_id']:
                await MasterDB.toggle_busy(order['master_id'])
                await query.message.bot.send_message(
                    order['user_id'],
                    f"✅ Буюртмангиз {order_number} якунланди!\n⭐ Баҳолаш:",
                    reply_markup=Keyboards.rate_actions(order_number)
                )
        
        elif action == 'rate':
            rating = int(parts[2])
            await OrderDB.rate(order_number, rating)
            await query.edit_message_text(f"⭐ Баҳоланди! {rating}")
        
        elif action == 'call':
            order = await OrderDB.get_by_number(order_number)
            if order:
                await query.edit_message_text(f"📞 Телефон: {order['phone']}\n📍 Манзил: {order['address']}")

    # ==================== UNKNOWN ====================
    
    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Admin actions
        if context.user_data.get('admin_action'):
            action = context.user_data['admin_action']
            parts = update.message.text.strip().split()
            
            if len(parts) < 1:
                await update.message.reply_text("❌ ID киритинг!")
                return
            
            try:
                target_id = int(parts[0])
            except ValueError:
                await update.message.reply_text("❌ ID сон бўлиши керак!")
                return
            
            if action == 'add_master':
                if len(parts) < 2:
                    await update.message.reply_text("❌ Исм киритинг!")
                    return
                await MasterDB.add(target_id, ' '.join(parts[1:]))
                await update.message.reply_text(f"✅ Уста қўшилди!")
            
            elif action == 'remove_master':
                await MasterDB.remove(target_id)
                await update.message.reply_text(f"✅ Уста ўчирилди!")
            
            elif action == 'add_dispatcher':
                if len(parts) < 2:
                    await update.message.reply_text("❌ Исм киритинг!")
                    return
                await DispatcherDB.add(target_id, ' '.join(parts[1:]))
                await update.message.reply_text(f"✅ Диспетчер қўшилди!")
            
            elif action == 'remove_dispatcher':
                await DispatcherDB.remove(target_id)
                await update.message.reply_text(f"✅ Диспетчер ўчирилди!")
            
            context.user_data['admin_action'] = None
            return
        
        # Broadcast
        if context.user_data.get('broadcast'):
            text = update.message.text
            async with Database.pool.acquire() as conn:
                users = await conn.fetch('SELECT user_id FROM users')
            
            sent = 0
            for user in users:
                try:
                    await update.message.bot.send_message(user['user_id'], text)
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
            
            await update.message.reply_text(f"✅ {sent} та фойдаланувчига юборилди!")
            context.user_data['broadcast'] = False
            return
        
        # Contact dispatcher
        if context.user_data.get('contact_dispatcher'):
            target = DISPATCHER_ID or ADMIN_ID
            await update.message.bot.send_message(
                target,
                f"📞 **Мижоздан хабар**\n\n{update.message.text}",
                parse_mode='Markdown'
            )
            await update.message.reply_text("✅ Юборилди!", reply_markup=Keyboards.main(context.user_data.get('role', 'user')))
            context.user_data['contact_dispatcher'] = False
            return
        
        await update.message.reply_text("❌ Тушунарсиз. /start босинг.")

    # ==================== MASTERS STATS ====================
    
    async def masters_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('role') not in ['dispatcher', 'admin']:
            await update.message.reply_text("❌ Ҳуқуқ йўқ!")
            return
        
        masters = await MasterDB.get_all()
        if not masters:
            await update.message.reply_text("👨‍🔧 Усталар йўқ.")
            return
        
        text = "👨‍🔧 **Усталар статистикаси**\n\n"
        for m in masters:
            text += f"👤 {m['full_name']}\n⭐ {m['rating']:.1f}\n📊 {m['total_orders']}\n---\n"
        await update.message.reply_text(text, parse_mode='Markdown')

    # ==================== ERROR ====================
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error: {context.error}")


# ============================================================
# MAIN
# ============================================================

async def main():
    global _application
    
    await Database.init()
    
    application = Application.builder().token(TOKEN).build()
    _application = application
    
    BotHandlers(application)
    
    await application.initialize()
    await application.start()
    
    # WEBHOOK or POLLING
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook: {webhook_url}")
        
        def run_flask():
            flask_app.run(host="0.0.0.0", port=PORT, debug=False)
        Thread(target=run_flask, daemon=True).start()
        logger.info(f"🚀 Flask: {PORT}")
    else:
        await application.updater.start_polling()
        logger.info("🚀 Polling rejimida ishga tushdi")
    
    logger.info("✅ BOT ISHGA TUSHDI!")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("🛑 To'xtatilmoqda...")
    finally:
        await Database.close()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
