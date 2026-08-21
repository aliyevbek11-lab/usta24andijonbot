#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📱 USTA 24 ANDIJON - To'liq Telegram Bot
🤖 1 Bot = 3 Rol (Mijoz + Usta + Admin)
📞 Dispetcher: +9987706900003
🚨 24/7 Shosilinch rejim
"""

import asyncio
import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    FSInputFile, InputMediaPhoto
)
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# ======================== KONFIGURATSIYA ========================

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # O'z tokeningizni qo'ying
ADMIN_IDS = [123456789, 987654321]  # Admin Telegram ID'lari
DISPETCHER_PHONE = "+9987706900003"
GROUP_ID = -1001234567890  # Guruh ID'si (manfiy son)
CHANNEL_ID = -1001234567891  # Kanal ID'si (ixtiyoriy)

# ======================== LOGING ========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ======================== DATABASE ========================

class Database:
    def __init__(self, db_path="usta24.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Foydalanuvchilar
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'mijoz',
                lang TEXT DEFAULT 'uz',
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Buyurtmalar
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_num TEXT UNIQUE,
                user_id INTEGER,
                service TEXT,
                sub_service TEXT,
                description TEXT,
                address TEXT,
                latitude REAL,
                longitude REAL,
                time_slot TEXT,
                price INTEGER,
                status TEXT DEFAULT 'yangi',
                usta_id INTEGER,
                usta_name TEXT,
                problem_photo TEXT,
                result_photo TEXT,
                video TEXT,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                duration INTEGER,
                rating INTEGER,
                review TEXT,
                is_urgent INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Ustalar
        c.execute('''
            CREATE TABLE IF NOT EXISTS masters (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                services TEXT,
                price_per_hour INTEGER,
                work_area TEXT,
                work_start TEXT,
                work_end TEXT,
                is_24_7 INTEGER DEFAULT 0,
                rating REAL DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                latitude REAL,
                longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Sharhlar
        c.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                user_id INTEGER,
                master_id INTEGER,
                rating INTEGER,
                review TEXT,
                photo TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (master_id) REFERENCES users(user_id)
            )
        ''')

        # Bonuslar
        c.execute('''
            CREATE TABLE IF NOT EXISTS bonuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_id INTEGER,
                amount INTEGER,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        ''')

        # Eslatmalar
        c.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                remind_at TIMESTAMP,
                is_done INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Xizmat turlari
        c.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                description TEXT,
                price INTEGER,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # E'lonlar
        c.execute('''
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT,
                photo TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 24/7 shosilinch so'rovlar
        c.execute('''
            CREATE TABLE IF NOT EXISTS urgent_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                user_id INTEGER,
                issue_type TEXT,
                description TEXT,
                latitude REAL,
                longitude REAL,
                status TEXT DEFAULT 'kutilmoqda',
                master_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    def get_conn(self):
        return sqlite3.connect(self.db_path)

    # ========== USER METHODS ==========

    def add_user(self, user_id: int, full_name: str, phone: str = "", role: str = "mijoz", lang: str = "uz", username: str = ""):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO users (user_id, full_name, phone, role, lang, username)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, full_name, phone, role, lang, username))
        conn.commit()
        conn.close()

    def get_user(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result

    def get_user_role(self, user_id: int):
        user = self.get_user(user_id)
        return user[3] if user else None

    def get_all_users(self, role: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        if role:
            c.execute('SELECT * FROM users WHERE role = ?', (role,))
        else:
            c.execute('SELECT * FROM users')
        result = c.fetchall()
        conn.close()
        return result

    # ========== ORDER METHODS ==========

    def create_order(self, user_id: int, service: str, sub_service: str, description: str,
                     address: str, lat: float, lon: float, time_slot: str, price: int,
                     photo: str = "", video: str = "", comment: str = "", is_urgent: int = 0):
        conn = self.get_conn()
        c = conn.cursor()

        # Order number generation
        c.execute("SELECT COUNT(*) FROM orders")
        count = c.fetchone()[0]
        order_num = f"#{1000 + count + 1}"

        c.execute('''
            INSERT INTO orders (order_num, user_id, service, sub_service, description,
                address, latitude, longitude, time_slot, price, problem_photo, video,
                comment, status, is_urgent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'yangi', ?)
        ''', (order_num, user_id, service, sub_service, description, address, lat, lon,
              time_slot, price, photo, video, comment, is_urgent))

        order_id = c.lastrowid
        conn.commit()
        conn.close()
        return order_id, order_num

    def get_order(self, order_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        result = c.fetchone()
        conn.close()
        return result

    def get_order_by_num(self, order_num: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE order_num = ?', (order_num,))
        result = c.fetchone()
        conn.close()
        return result

    def get_user_orders(self, user_id: int, status: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        if status:
            c.execute('SELECT * FROM orders WHERE user_id = ? AND status = ? ORDER BY id DESC',
                      (user_id, status))
        else:
            c.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC', (user_id,))
        result = c.fetchall()
        conn.close()
        return result

    def get_master_orders(self, master_id: int, status: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        if status:
            c.execute('SELECT * FROM orders WHERE usta_id = ? AND status = ? ORDER BY id DESC',
                      (master_id, status))
        else:
            c.execute('SELECT * FROM orders WHERE usta_id = ? ORDER BY id DESC', (master_id,))
        result = c.fetchall()
        conn.close()
        return result

    def update_order_status(self, order_id: int, status: str, master_id: int = None,
                            master_name: str = None, duration: int = None, price: int = None,
                            result_photo: str = ""):
        conn = self.get_conn()
        c = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "qabul_qilingan":
                updates.append("started_at = ?")
                params.append(datetime.now().isoformat())
            elif status == "tugallangan":
                updates.append("finished_at = ?")
                params.append(datetime.now().isoformat())

        if master_id:
            updates.append("usta_id = ?")
            params.append(master_id)
        if master_name:
            updates.append("usta_name = ?")
            params.append(master_name)
        if duration is not None:
            updates.append("duration = ?")
            params.append(duration)
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        if result_photo:
            updates.append("result_photo = ?")
            params.append(result_photo)

        if updates:
            query = f"UPDATE orders SET {', '.join(updates)} WHERE id = ?"
            params.append(order_id)
            c.execute(query, params)

        conn.commit()
        conn.close()

    def get_all_orders(self, status: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        if status:
            c.execute('SELECT * FROM orders WHERE status = ? ORDER BY id DESC', (status,))
        else:
            c.execute('SELECT * FROM orders ORDER BY id DESC')
        result = c.fetchall()
        conn.close()
        return result

    def get_orders_stats(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'yangi' THEN 1 ELSE 0 END) as new,
                SUM(CASE WHEN status = 'qabul_qilingan' THEN 1 ELSE 0 END) as accepted,
                SUM(CASE WHEN status = 'jarayonda' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'tugallangan' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'bekor_qilingan' THEN 1 ELSE 0 END) as cancelled,
                SUM(price) as total_price
            FROM orders
        ''')
        result = c.fetchone()
        conn.close()
        return result

    # ========== MASTER METHODS ==========

    def add_master(self, user_id: int, full_name: str, phone: str, services: str,
                   price: int, work_area: str, work_start: str, work_end: str,
                   is_24_7: int = 0, lat: float = None, lon: float = None):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO masters (user_id, full_name, phone, services,
                price_per_hour, work_area, work_start, work_end, is_24_7, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, full_name, phone, services, price, work_area, work_start, work_end,
              is_24_7, lat, lon))
        conn.commit()
        conn.close()
        # Update user role
        self.add_user(user_id, full_name, phone, "usta")

    def get_master(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM masters WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result

    def get_all_masters(self, is_active: int = 1):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM masters WHERE is_active = ?', (is_active,))
        result = c.fetchall()
        conn.close()
        return result

    def update_master_rating(self, master_id: int, rating: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            UPDATE masters
            SET rating = (rating * total_orders + ?) / (total_orders + 1),
                total_orders = total_orders + 1
            WHERE user_id = ?
        ''', (rating, master_id))
        conn.commit()
        conn.close()

    # ========== REVIEW METHODS ==========

    def add_review(self, order_id: int, user_id: int, master_id: int, rating: int, review: str, photo: str = ""):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO reviews (order_id, user_id, master_id, rating, review, photo)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (order_id, user_id, master_id, rating, review, photo))
        conn.commit()
        conn.close()
        self.update_master_rating(master_id, rating)

    def get_master_reviews(self, master_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM reviews WHERE master_id = ? ORDER BY id DESC', (master_id,))
        result = c.fetchall()
        conn.close()
        return result

    # ========== BONUS METHODS ==========

    def add_bonus(self, user_id: int, order_id: int, amount: int, bonus_type: str):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO bonuses (user_id, order_id, amount, type)
            VALUES (?, ?, ?, ?)
        ''', (user_id, order_id, amount, bonus_type))
        conn.commit()
        conn.close()

    def get_user_bonuses(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT SUM(amount) FROM bonuses WHERE user_id = ?', (user_id,))
        total = c.fetchone()[0] or 0
        conn.close()
        return total

    # ========== REMINDER METHODS ==========

    def add_reminder(self, user_id: int, text: str, remind_at: datetime):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO reminders (user_id, text, remind_at)
            VALUES (?, ?, ?)
        ''', (user_id, text, remind_at.isoformat()))
        conn.commit()
        conn.close()

    def get_reminders(self, user_id: int):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM reminders WHERE user_id = ? AND is_done = 0 ORDER BY remind_at',
                  (user_id,))
        result = c.fetchall()
        conn.close()
        return result

    # ========== ANNOUNCEMENT METHODS ==========

    def add_announcement(self, title: str, content: str, photo: str = ""):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO announcements (title, content, photo)
            VALUES (?, ?, ?)
        ''', (title, content, photo))
        conn.commit()
        conn.close()

    def get_active_announcements(self):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('SELECT * FROM announcements WHERE is_active = 1 ORDER BY id DESC')
        result = c.fetchall()
        conn.close()
        return result

    # ========== URGENT REQUEST METHODS ==========

    def add_urgent_request(self, user_id: int, order_id: int, issue_type: str,
                           description: str, lat: float, lon: float):
        conn = self.get_conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO urgent_requests (user_id, order_id, issue_type, description,
                latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, order_id, issue_type, description, lat, lon))
        conn.commit()
        conn.close()

    def get_urgent_requests(self, status: str = None):
        conn = self.get_conn()
        c = conn.cursor()
        if status:
            c.execute('SELECT * FROM urgent_requests WHERE status = ? ORDER BY id DESC',
                      (status,))
        else:
            c.execute('SELECT * FROM urgent_requests ORDER BY id DESC')
        result = c.fetchall()
        conn.close()
        return result

# ======================== STATES ========================

class RegistrationState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_role = State()

class OrderState(StatesGroup):
    waiting_service = State()
    waiting_sub_service = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_address = State()
    waiting_photo = State()
    waiting_video = State()
    waiting_comment = State()
    waiting_time = State()
    waiting_confirm = State()

class MasterState(StatesGroup):
    waiting_order_action = State()
    waiting_start_work = State()
    waiting_finish_work = State()
    waiting_result_photo = State()
    waiting_price = State()
    waiting_duration = State()

class AdminState(StatesGroup):
    waiting_add_master_name = State()
    waiting_add_master_phone = State()
    waiting_add_master_services = State()
    waiting_add_master_price = State()
    waiting_add_master_area = State()
    waiting_add_master_time = State()
    waiting_announcement_title = State()
    waiting_announcement_content = State()
    waiting_announcement_photo = State()
    waiting_broadcast = State()

class UrgentState(StatesGroup):
    waiting_issue_type = State()
    waiting_description = State()
    waiting_location = State()
    waiting_photo = State()

class ReviewState(StatesGroup):
    waiting_master = State()
    waiting_rating = State()
    waiting_review = State()
    waiting_photo = State()

class ReminderState(StatesGroup):
    waiting_text = State()
    waiting_time = State()

# ======================== KEYBOARDS ========================

def get_main_keyboard(role: str):
    kb = []

    if role == "mijoz":
        kb = [
            [KeyboardButton(text="🛒 Buyurtma berish")],
            [KeyboardButton(text="📋 Mening buyurtmalarim"), KeyboardButton(text="🔍 Buyurtma holati")],
            [KeyboardButton(text="❌ Bekor qilish"), KeyboardButton(text="🔁 Qayta buyurtma")],
            [KeyboardButton(text="👨‍🔧 Mening ustalarim"), KeyboardButton(text="⭐ Reytingim")],
            [KeyboardButton(text="📝 Sharh qoldirish"), KeyboardButton(text="📌 Eslatmalarim")],
            [KeyboardButton(text="🗺️ Yaqin atrofdagi ustalar"), KeyboardButton(text="📅 Yozilma")],
            [KeyboardButton(text="🎁 Loyallik va bonuslar"), KeyboardButton(text="🤖 AI yordamchi")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="📊 Mening statistika")],
            [KeyboardButton(text="🏷️ Chegirmalar"), KeyboardButton(text="📞 Tez yordam")],
            [KeyboardButton(text="🔔 Bildirishnomalar"), KeyboardButton(text="📁 Mening hujjatlarim")],
            [KeyboardButton(text="🕊️ Do'stga tavsiya qilish"), KeyboardButton(text="📞 Dispetcher")],
            [KeyboardButton(text="🚨 24/7 Shosilinch rejim")],
            [KeyboardButton(text="🚪 Chiqish")]
        ]
    elif role == "usta":
        kb = [
            [KeyboardButton(text="📋 Yangi buyurtmalar"), KeyboardButton(text="✅ Mening buyurtmalarim")],
            [KeyboardButton(text="⏳ Tarix"), KeyboardButton(text="💰 Ish haqi va hisobot")],
            [KeyboardButton(text="⭐ Reytingim"), KeyboardButton(text="📅 Kunlik jadval")],
            [KeyboardButton(text="🔔 Mijozlar bilan bog'lanish"), KeyboardButton(text="📸 Galereya")],
            [KeyboardButton(text="🛠 Xizmatlarni boshqarish"), KeyboardButton(text="📊 Ish statistikasi")],
            [KeyboardButton(text="🏷️ Mening narxlarim"), KeyboardButton(text="📍 Ish hududim")],
            [KeyboardButton(text="📅 Dam olish kunlari"), KeyboardButton(text="🔔 Sozlamalar")],
            [KeyboardButton(text="📝 Reytingni oshirish"), KeyboardButton(text="🎁 Usta bonuslari")],
            [KeyboardButton(text="🤖 AI yordamchi"), KeyboardButton(text="📞 Texnik yordam")],
            [KeyboardButton(text="📢 E'lonlar"), KeyboardButton(text="🏆 TOP 10")],
            [KeyboardButton(text="📞 Dispetcher"), KeyboardButton(text="🚨 24/7 Shosilinch rejim")],
            [KeyboardButton(text="🚪 Chiqish")]
        ]
    elif role == "admin":
        kb = [
            [KeyboardButton(text="👥 Foydalanuvchilar"), KeyboardButton(text="🛠 Buyurtmalar")],
            [KeyboardButton(text="👨‍🔧 Ustalar"), KeyboardButton(text="⭐ Reyting va sharhlar")],
            [KeyboardButton(text="🎁 Loyallik"), KeyboardButton(text="💰 To'lovlar")],
            [KeyboardButton(text="🏷️ Chegirmalar"), KeyboardButton(text="🛠 Xizmat turlari")],
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 E'lonlar")],
            [KeyboardButton(text="📞 Dispetcher"), KeyboardButton(text="⚙️ Sozlamalar")],
            [KeyboardButton(text="📸 Galereya"), KeyboardButton(text="📱 Botni boshqarish")],
            [KeyboardButton(text="🚨 24/7 Shosilinch rejim")],
            [KeyboardButton(text="🚪 Chiqish")]
        ]

    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_inline_keyboard(buttons: List[Tuple[str, str]], row_width: int = 2):
    kb = []
    row = []
    for text, callback in buttons:
        row.append(InlineKeyboardButton(text=text, callback_data=callback))
        if len(row) >= row_width:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_keyboard():
    return get_inline_keyboard([
        ("⬅️ Orqaga", "back"),
        ("🏠 Bosh menyu", "home")
    ])

def get_order_status_keyboard(order_id: int):
    return get_inline_keyboard([
        ("✅ Qabul qilish", f"accept_{order_id}"),
        ("❌ Rad etish", f"reject_{order_id}"),
        ("📸 Rasmlarni ko'rish", f"view_photos_{order_id}")
    ])

def get_master_order_keyboard(order_id: int):
    return get_inline_keyboard([
        ("🔧 Ishni boshlash", f"start_work_{order_id}"),
        ("✅ Ishni yakunlash", f"finish_work_{order_id}"),
        ("📞 Qo'ng'iroq", f"call_{order_id}"),
        ("💬 Xabar", f"chat_{order_id}")
    ])

# ======================== MESSAGES ========================

TEXTS = {
    "uz": {
        "welcome": "👋 Assalomu alaykum! USTA 24 ANDIJON botiga xush kelibsiz!",
        "ask_name": "📌 Iltimos, ismingizni kiriting (Familiya kerak emas!):",
        "ask_phone": "📱 Telefon raqamingizni kiriting (+998901234567):",
        "ask_role": "👤 Kim sifatida ro'yxatdan o'tasiz?",
        "role_mijoz": "👤 Mijoz",
        "role_usta": "👨‍🔧 Usta",
        "role_admin": "👨‍💼 Admin",
        "registered": "✅ Ro'yxatdan o'tdingiz!",
        "main_menu": "🏠 Bosh menyu",
        "order_created": "✅ Buyurtma yaratildi!",
        "order_accepted": "✅ Buyurtma qabul qilindi!",
        "order_rejected": "❌ Buyurtma rad etildi",
        "order_completed": "✅ Buyurtma yakunlandi!",
        "no_orders": "📭 Sizda buyurtmalar yo'q",
        "choose_service": "🛠 Xizmat turini tanlang:",
        "choose_sub_service": "📋 Xizmat turini tanlang:",
        "enter_address": "📍 Manzilingizni kiriting yoki geolokatsiya yuboring:",
        "send_photo": "📸 Muammo rasmini yuboring (ixtiyoriy):",
        "send_video": "🎥 Video yuboring (ixtiyoriy):",
        "enter_comment": "📝 Izoh qoldiring (ixtiyoriy):",
        "choose_time": "🕐 Vaqtni tanlang:",
        "confirm_order": "✅ Buyurtmani tasdiqlaysizmi?",
        "order_confirmed": "✅ Buyurtma tasdiqlandi!",
        "order_cancelled": "❌ Buyurtma bekor qilindi",
        "enter_review": "📝 Sharhingizni yozing:",
        "choose_rating": "⭐ Baho bering:",
        "review_sent": "✅ Sharhingiz yuborildi!",
        "urgent_help": "🚨 Shosilingch yordam!",
        "choose_issue": "⚡ Muammo turini tanlang:",
        "urgent_sent": "🚨 Shosilingch so'rov yuborildi!",
        "dispetcher_call": f"📞 Dispetcher: {DISPETCHER_PHONE}",
        "dispetcher_working": "🕐 24/7 ishlaydi! Kutish yo'q!",
        "back": "⬅️ Orqaga",
        "home": "🏠 Bosh menyu",
        "logout": "🚪 Chiqish",
        "settings": "⚙️ Sozlamalar",
        "language": "🌐 Til: 🇺🇿 O'zbek",
        "stats": "📊 Statistika",
        "bonus": "🎁 Bonuslar",
        "no_bonus": "🎁 Sizda bonuslar yo'q",
        "error": "❌ Xatolik yuz berdi. Qayta urinib ko'ring.",
        "not_found": "❌ Ma'lumot topilmadi",
    },
    "ru": {
        "welcome": "👋 Добро пожаловать в USTA 24 ANDIJON!",
        "ask_name": "📌 Введите ваше имя (Фамилия не нужна!):",
        "ask_phone": "📱 Введите номер телефона (+998901234567):",
        "ask_role": "👤 Кем вы хотите зарегистрироваться?",
        "role_mijoz": "👤 Клиент",
        "role_usta": "👨‍🔧 Мастер",
        "role_admin": "👨‍💼 Админ",
        # ... other translations
    },
    "en": {
        "welcome": "👋 Welcome to USTA 24 ANDIJON!",
        "ask_name": "📌 Please enter your name (No surname!):",
        "ask_phone": "📱 Enter your phone number (+998901234567):",
        "ask_role": "👤 Who are you?",
        "role_mijoz": "👤 Client",
        "role_usta": "👨‍🔧 Master",
        "role_admin": "👨‍💼 Admin",
        # ... other translations
    }
}

# ======================== BOT INIT ========================

storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
db = Database()

# ======================== HANDLERS ========================

# ---------- START ----------

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = db.get_user(user_id)

    if user:
        # User exists
        role = user[3]
        await message.answer(
            TEXTS["uz"]["welcome"],
            reply_markup=get_main_keyboard(role)
        )
        await state.clear()
        return

    await message.answer(TEXTS["uz"]["welcome"])
    await message.answer(TEXTS["uz"]["ask_name"])
    await state.set_state(RegistrationState.waiting_name)

# ---------- REGISTRATION ----------

@dp.message(RegistrationState.waiting_name)
async def reg_name(message: Message, state: FSMContext):
    if len(message.text) < 2:
        await message.answer("❌ Iltimos, ismingizni to'g'ri kiriting (kamida 2 harf):")
        return

    await state.update_data(full_name=message.text)
    await message.answer(TEXTS["uz"]["ask_phone"])
    await state.set_state(RegistrationState.waiting_phone)

@dp.message(RegistrationState.waiting_phone)
async def reg_phone(message: Message, state: FSMContext):
    phone = message.text
    # Simple phone validation
    if len(phone) < 10:
        await message.answer("❌ Telefon raqam noto'g'ri. Masalan: +998901234567")
        return

    await state.update_data(phone=phone)
    await message.answer(
        TEXTS["uz"]["ask_role"],
        reply_markup=get_inline_keyboard([
            ("👤 Mijoz", "role_mijoz"),
            ("👨‍🔧 Usta", "role_usta"),
            ("👨‍💼 Admin", "role_admin")
        ])
    )
    await state.set_state(RegistrationState.waiting_role)

@dp.callback_query(RegistrationState.waiting_role)
async def reg_role(callback: CallbackQuery, state: FSMContext):
    role = callback.data.replace("role_", "")
    data = await state.get_data()
    user_id = callback.from_user.id
    full_name = data.get("full_name")
    phone = data.get("phone")
    username = callback.from_user.username or ""

    # Save to database
    db.add_user(user_id, full_name, phone, role, "uz", username)

    await callback.message.edit_text(TEXTS["uz"]["registered"])
    await callback.message.answer(
        TEXTS["uz"]["main_menu"],
        reply_markup=get_main_keyboard(role)
    )
    await state.clear()
    await callback.answer()

    # If role is "usta", add to masters table
    if role == "usta":
        db.add_master(user_id, full_name, phone, "Elektr", 50000, "Andijon shahar", "08:00", "18:00", 0)

    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Yangi foydalanuvchi ro'yxatdan o'tdi!\n"
                f"👤 {full_name}\n"
                f"📞 {phone}\n"
                f"🎭 Rol: {role}\n"
                f"🆔 {user_id}"
            )
        except:
            pass

# ---------- MAIN MENU HANDLERS ----------

@dp.message(F.text == "🚪 Chiqish")
async def logout_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🚪 Siz chiqdingiz. Qayta boshlash uchun /start bosing.",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "🏠 Bosh menyu")
async def home_cmd(message: Message):
    user_id = message.from_user.id
    role = db.get_user_role(user_id) or "mijoz"
    await message.answer(
        TEXTS["uz"]["main_menu"],
        reply_markup=get_main_keyboard(role)
    )

@dp.message(F.text == "⬅️ Orqaga")
async def back_cmd(message: Message):
    user_id = message.from_user.id
    role = db.get_user_role(user_id) or "mijoz"
    await message.answer(
        TEXTS["uz"]["main_menu"],
        reply_markup=get_main_keyboard(role)
    )

# ---------- DISPETCHER ----------

@dp.message(F.text == "📞 Dispetcher")
async def dispetcher_cmd(message: Message):
    user_id = message.from_user.id

    # Save contact to user
    db.add_user(user_id, message.from_user.first_name, "", "mijoz")

    await message.answer(
        f"📞 <b>DISPETCHER:</b>\n"
        f"📱 <code>{DISPETCHER_PHONE}</code>\n\n"
        f"🕐 <b>Ish vaqti:</b> 24/7 – KUTISH YO'Q!\n"
        f"🚨 <b>Shosilingch holatda:</b> Daro'x yordam!\n\n"
        f"📋 <b>Dispetcher vazifalari:</b>\n"
        f"├── 📞 Mijoz va ustalarni bog'lash\n"
        f"├── 🚨 24/7 shosilingch holatlarni boshqarish\n"
        f"├── 📋 Zakazlarni nazorat qilish\n"
        f"└── 👨‍🔧 Yangi ustalarni qabul qilish\n\n"
        f"[📞 Qo'ng'iroq qilish] – telefonda bosing!\n"
        f"[💬 Xabar yuborish] – @usta24_bot orqali yozing!",
        reply_markup=get_inline_keyboard([
            ("📞 Qo'ng'iroq", "call_dispetcher"),
            ("💬 Xabar", "chat_dispetcher")
        ])
    )

@dp.callback_query(F.data == "call_dispetcher")
async def call_dispetcher(callback: CallbackQuery):
    await callback.answer(f"📞 {DISPETCHER_PHONE} raqamiga qo'ng'iroq qilish...")
    # Telegram does not support direct calls, but we show the number
    await callback.message.answer(
        f"📞 <b>Dispetcher raqami:</b>\n<code>{DISPETCHER_PHONE}</code>\n\n"
        f"🕐 24/7 ishlaydi! KUTISH YO'Q!"
    )

@dp.callback_query(F.data == "chat_dispetcher")
async def chat_dispetcher(callback: CallbackQuery):
    await callback.message.answer(
        f"💬 <b>Dispetcher bilan bog'lanish:</b>\n\n"
        f"📱 <code>{DISPETCHER_PHONE}</code>\n\n"
        f"📨 Xabaringizni yozing, men Dispetcherga yetkazaman!\n"
        f"(Yoki bevosita telefonga yozing: @usta24_bot)"
    )
    await callback.answer()

# ---------- 24/7 URGENT REJIM ----------

@dp.message(F.text == "🚨 24/7 Shosilinch rejim")
async def urgent_cmd(message: Message, state: FSMContext):
    await message.answer(
        "🚨 <b>24/7 SHOSILINCH REJIM – KUTISH YO'Q!</b>\n\n"
        "⚡ <b>Dolzarb holatni tanlang:</b>",
        reply_markup=get_inline_keyboard([
            ("💧 Suv tўхtab qoldi", "urgent_water"),
            ("⚡ Elektr ўчиб қолди", "urgent_electric"),
            ("🔥 Газ оқаётган", "urgent_gas"),
            ("🚪 Эшик синиб қолди", "urgent_door"),
            ("🚰 Қувур ёрилган", "urgent_pipe"),
            ("❓ Бошқа", "urgent_other")
        ])
    )
    await state.set_state(UrgentState.waiting_issue_type)

@dp.callback_query(UrgentState.waiting_issue_type)
async def urgent_issue(callback: CallbackQuery, state: FSMContext):
    issue_map = {
        "urgent_water": "💧 Suv tўхtab qoldi",
        "urgent_electric": "⚡ Elektr ўчиб қолди",
        "urgent_gas": "🔥 Газ оқаётган",
        "urgent_door": "🚪 Эшик синиб қолди",
        "urgent_pipe": "🚰 Қувур ёрилган",
        "urgent_other": "❓ Бошқа"
    }

    issue = issue_map.get(callback.data, "❓ Бошқа")
    await state.update_data(issue_type=issue)

    await callback.message.edit_text(
        f"📝 <b>Muammo haqida qo'shimcha ma'lumot:</b>\n\n"
        f"⚡ {issue}\n\n"
        f"📝 Iltimos, muammoni batafsil tasvirlang:"
    )
    await state.set_state(UrgentState.waiting_description)
    await callback.answer()

@dp.message(UrgentState.waiting_description)
async def urgent_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer(
        "📍 Iltimos, joylashuvingizni yuboring:\n\n"
        "📤 Geolokatsiya yuborish tugmasini bosing!\n"
        "✏️ Yoki manzilni matn bilan yozing.",
        reply_markup=get_inline_keyboard([
            ("📍 Geolokatsiya", "urgent_location"),
            ("✏️ Matn bilan", "urgent_text")
        ])
    )
    await state.set_state(UrgentState.waiting_location)

@dp.callback_query(UrgentState.waiting_location)
async def urgent_location_type(callback: CallbackQuery, state: FSMContext):
    if callback.data == "urgent_location":
        await callback.message.edit_text(
            "📍 <b>Geolokatsiyangizni yuboring!</b>\n\n"
            "📎 Ilovadagi 📍 tugmasini bosing!"
        )
        await state.set_state(UrgentState.waiting_location)
    else:
        await callback.message.edit_text(
            "✏️ <b>Manzilingizni yozing:</b>"
        )
        await state.set_state(UrgentState.waiting_location)
    await callback.answer()

@dp.message(UrgentState.waiting_location)
async def urgent_location_photo(message: Message, state: FSMContext):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        await state.update_data(latitude=lat, longitude=lon, address="")
    else:
        await state.update_data(address=message.text, latitude=0, longitude=0)

    await message.answer(
        "📸 <b>Muammo rasmini yuboring (ixtiyoriy):</b>\n\n"
        "🖼 Rasm yuborish yoki ⏭ O'tkazib yuborish",
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "urgent_skip_photo")
        ])
    )
    await state.set_state(UrgentState.waiting_photo)

@dp.message(UrgentState.waiting_photo)
async def urgent_photo(message: Message, state: FSMContext):
    photo_id = ""
    if message.photo:
        photo_id = message.photo[-1].file_id

    await state.update_data(photo=photo_id)
    await complete_urgent_request(message, state)

@dp.callback_query(F.data == "urgent_skip_photo")
async def urgent_skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo="")
    await callback.message.edit_text("⏭ Rasm o'tkazib yuborildi")
    await complete_urgent_request(callback.message, state)
    await callback.answer()

async def complete_urgent_request(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    user = db.get_user(user_id)

    # Create order
    order_id, order_num = db.create_order(
        user_id=user_id,
        service="24/7 Shosilingch",
        sub_service=data.get("issue_type", "Boshqa"),
        description=data.get("description", ""),
        address=data.get("address", "Geolokatsiya orqali"),
        lat=data.get("latitude", 0),
        lon=data.get("longitude", 0),
        time_slot="Hozir",
        price=0,
        photo=data.get("photo", ""),
        comment="🚨 24/7 SHOSILINCH!",
        is_urgent=1
    )

    # Add urgent request
    db.add_urgent_request(
        user_id=user_id,
        order_id=order_id,
        issue_type=data.get("issue_type", "Boshqa"),
        description=data.get("description", ""),
        lat=data.get("latitude", 0),
        lon=data.get("longitude", 0)
    )

    # Send to group
    try:
        await bot.send_message(
            GROUP_ID,
            f"🚨 <b>24/7 SHOSILINCH BUYURTMA!</b>\n\n"
            f"🆔 {order_num}\n"
            f"⚡ Muammo: {data.get('issue_type', 'Boshqa')}\n"
            f"👤 Mijoz: {user[1] if user else 'Noma'lum'}\n"
            f"📞 {user[2] if user else ''}\n"
            f"📍 {data.get('address', 'Geolokatsiya orqali')}\n"
            f"📝 {data.get('description', '')}\n"
            f"🚨 <b>KUTISH YO'Q! DARO'X YORDAM!</b>\n\n"
            f"[✅ QABUL QILISH]  [❌ RAD ETISH]",
            reply_markup=get_order_status_keyboard(order_id)
        )
    except:
        pass

    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🚨 <b>24/7 SHOSILINCH BUYURTMA!</b>\n"
                f"🆔 {order_num}\n"
                f"⚡ {data.get('issue_type', 'Boshqa')}\n"
                f"👤 {user[1] if user else 'Noma'lum'}\n"
                f"📞 {user[2] if user else ''}\n"
                f"📍 {data.get('address', 'Geolokatsiya orqali')}"
            )
        except:
            pass

    await message.answer(
        f"🚨 <b>SHOSILINCH SO'ROV YUBORILDI!</b>\n\n"
        f"🆔 {order_num}\n"
        f"⚡ <b>Tez orada usta keladi!</b>\n"
        f"🕐 Kutilgan vaqt: 10-15 daqiqa\n"
        f"💸 <b>Tўlov:</b> Faqat naqd pul! Ishdan keyin!\n"
        f"🔴 <b>Kechki vaqt:</b> 20% ustama\n\n"
        f"📞 Dispetcher: <code>{DISPETCHER_PHONE}</code>"
    )

    await state.clear()

# ---------- ORDER CREATION ----------

@dp.message(F.text == "🛒 Buyurtma berish")
async def order_start(message: Message, state: FSMContext):
    await message.answer(
        TEXTS["uz"]["choose_service"],
        reply_markup=get_inline_keyboard([
            ("🛠 Sanitariya", "service_sanitariya"),
            ("⚡ Elektr", "service_elektr"),
            ("🔧 Mexanik", "service_mexanik"),
            ("🧹 Tozalash", "service_tozalash"),
            ("📦 Yuk", "service_yuk"),
            ("❓ Boshqa", "service_boshqa")
        ])
    )
    await state.set_state(OrderState.waiting_service)

@dp.callback_query(OrderState.waiting_service)
async def order_service(callback: CallbackQuery, state: FSMContext):
    service = callback.data.replace("service_", "")
    await state.update_data(service=service)

    sub_services = {
        "sanitariya": ["🚽 Hojatxona", "🚿 Lavabo", "🔧 Quvur", "🧹 Kanalizatsiya", "📋 Boshqa"],
        "elektr": ["💡 Chiroq", "🔌 Rozetka", "🔧 Sim", "⚡ Avtomat", "📋 Boshqa"],
        "mexanik": ["🚪 Eshik", "🪟 Deraza", "🪑 Mebel", "❄️ Konditsioner", "📋 Boshqa"],
        "tozalash": ["🏠 Uy", "🏢 Ofis", "🧶 Gilam", "🪟 Deraza", "📋 Boshqa"],
        "yuk": ["📦 Kichik", "📦 O'rta", "📦 Katta", "📋 Boshqa"],
        "boshqa": ["📋 Boshqa xizmat"]
    }

    buttons = [(item, f"sub_{item}") for item in sub_services.get(service, ["📋 Boshqa"])]

    await callback.message.edit_text(
        f"📋 <b>{service.title()} xizmatini tanlang:</b>",
        reply_markup=get_inline_keyboard(buttons)
    )
    await state.set_state(OrderState.waiting_sub_service)
    await callback.answer()

@dp.callback_query(OrderState.waiting_sub_service)
async def order_sub_service(callback: CallbackQuery, state: FSMContext):
    sub_service = callback.data.replace("sub_", "")
    await state.update_data(sub_service=sub_service)

    await callback.message.edit_text(TEXTS["uz"]["ask_name"])
    await state.set_state(OrderState.waiting_name)
    await callback.answer()

@dp.message(OrderState.waiting_name)
async def order_name(message: Message, state: FSMContext):
    if len(message.text) < 2:
        await message.answer("❌ Iltimos, ismingizni to'g'ri kiriting:")
        return
    await state.update_data(name=message.text)
    await message.answer(TEXTS["uz"]["ask_phone"])
    await state.set_state(OrderState.waiting_phone)

@dp.message(OrderState.waiting_phone)
async def order_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer(
        TEXTS["uz"]["enter_address"],
        reply_markup=get_inline_keyboard([
            ("📍 Geolokatsiya", "address_location"),
            ("✏️ Matn bilan", "address_text")
        ])
    )
    await state.set_state(OrderState.waiting_address)

@dp.callback_query(OrderState.waiting_address)
async def order_address_type(callback: CallbackQuery, state: FSMContext):
    if callback.data == "address_location":
        await callback.message.edit_text(
            "📍 <b>Geolokatsiyangizni yuboring!</b>\n\n"
            "📎 Ilovadagi 📍 tugmasini bosing!"
        )
        await state.set_state(OrderState.waiting_address)
    else:
        await callback.message.edit_text(
            "✏️ <b>Manzilingizni yozing:</b>"
        )
        await state.set_state(OrderState.waiting_address)
    await callback.answer()

@dp.message(OrderState.waiting_address)
async def order_address(message: Message, state: FSMContext):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        await state.update_data(latitude=lat, longitude=lon, address="Geolokatsiya orqali")
    else:
        await state.update_data(address=message.text, latitude=0, longitude=0)

    await message.answer(
        TEXTS["uz"]["send_photo"],
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "order_skip_photo")
        ])
    )
    await state.set_state(OrderState.waiting_photo)

@dp.message(OrderState.waiting_photo)
async def order_photo(message: Message, state: FSMContext):
    photo_id = ""
    if message.photo:
        photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)

    await message.answer(
        TEXTS["uz"]["send_video"],
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "order_skip_video")
        ])
    )
    await state.set_state(OrderState.waiting_video)

@dp.callback_query(F.data == "order_skip_photo")
async def order_skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo="")
    await callback.message.edit_text("⏭ Rasm o'tkazib yuborildi")

    await callback.message.answer(
        TEXTS["uz"]["send_video"],
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "order_skip_video")
        ])
    )
    await state.set_state(OrderState.waiting_video)
    await callback.answer()

@dp.message(OrderState.waiting_video)
async def order_video(message: Message, state: FSMContext):
    video_id = ""
    if message.video:
        video_id = message.video.file_id
    await state.update_data(video=video_id)

    await message.answer(
        TEXTS["uz"]["enter_comment"],
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "order_skip_comment")
        ])
    )
    await state.set_state(OrderState.waiting_comment)

@dp.callback_query(F.data == "order_skip_video")
async def order_skip_video(callback: CallbackQuery, state: FSMContext):
    await state.update_data(video="")
    await callback.message.edit_text("⏭ Video o'tkazib yuborildi")

    await callback.message.answer(
        TEXTS["uz"]["enter_comment"],
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "order_skip_comment")
        ])
    )
    await state.set_state(OrderState.waiting_comment)
    await callback.answer()

@dp.message(OrderState.waiting_comment)
async def order_comment(message: Message, state: FSMContext):
    await state.update_data(comment=message.text)

    await message.answer(
        TEXTS["uz"]["choose_time"],
        reply_markup=get_inline_keyboard([
            ("🔴 Hozir", "time_now"),
            ("🟡 Bugun kechqurun", "time_evening"),
            ("🟢 Ertaga ertalab", "time_morning"),
            ("📆 Boshqa vaqt", "time_other")
        ])
    )
    await state.set_state(OrderState.waiting_time)

@dp.callback_query(F.data == "order_skip_comment")
async def order_skip_comment(callback: CallbackQuery, state: FSMContext):
    await state.update_data(comment="")
    await callback.message.edit_text("⏭ Izoh o'tkazib yuborildi")

    await callback.message.answer(
        TEXTS["uz"]["choose_time"],
        reply_markup=get_inline_keyboard([
            ("🔴 Hozir", "time_now"),
            ("🟡 Bugun kechqurun", "time_evening"),
            ("🟢 Ertaga ertalab", "time_morning"),
            ("📆 Boshqa vaqt", "time_other")
        ])
    )
    await state.set_state(OrderState.waiting_time)
    await callback.answer()

@dp.callback_query(OrderState.waiting_time)
async def order_time(callback: CallbackQuery, state: FSMContext):
    time_map = {
        "time_now": "Hozir",
        "time_evening": "Bugun kechqurun (18:00-22:00)",
        "time_morning": "Ertaga ertalab (08:00-12:00)",
        "time_other": "Boshqa vaqt"
    }
    time_slot = time_map.get(callback.data, "Hozir")
    await state.update_data(time_slot=time_slot)

    data = await state.get_data()

    # Calculate price
    price = 50000  # Default price per hour
    if data.get("service") == "sanitariya":
        price = 80000
    elif data.get("service") == "elektr":
        price = 50000
    elif data.get("service") == "mexanik":
        price = 60000
    elif data.get("service") == "tozalash":
        price = 40000
    elif data.get("service") == "yuk":
        price = 70000

    # Is it urgent? (Check from state)
    is_urgent = data.get("is_urgent", 0)
    if is_urgent:
        price = int(price * 1.2)  # 20% extra for urgent

    await state.update_data(price=price)

    # Show confirmation
    confirm_text = (
        f"📋 <b>Buyurtma ma'lumotlari:</b>\n\n"
        f"├── 🛠 Xizmat: {data.get('service', '').title()} – {data.get('sub_service', '')}\n"
        f"├── 👤 Ism: {data.get('name', '')}\n"
        f"├── 📞 Telefon: {data.get('phone', '')}\n"
        f"├── 📍 Manzil: {data.get('address', '')}\n"
        f"├── 📸 Rasm: {'✅' if data.get('photo') else '❌'}\n"
        f"├── 🎥 Video: {'✅' if data.get('video') else '❌'}\n"
        f"├── 📝 Izoh: {data.get('comment', "Yo'q")}\n"
        f"├── 🕐 Vaqt: {time_slot}\n"
        f"└── 💰 Narx: {price:,} so'm/soat\n\n"
        f"✅ <b>Tasdiqlaysizmi?</b>"
    )

    if is_urgent:
        confirm_text += "\n\n🚨 <b>24/7 SHOSILINCH REJIM!</b>"

    await callback.message.edit_text(
        confirm_text,
        reply_markup=get_inline_keyboard([
            ("✅ Tasdiqlash", "confirm_order"),
            ("❌ Bekor qilish", "cancel_order")
        ])
    )
    await state.set_state(OrderState.waiting_confirm)
    await callback.answer()

@dp.callback_query(OrderState.waiting_confirm)
async def order_confirm(callback: CallbackQuery, state: FSMContext):
    if callback.data == "cancel_order":
        await callback.message.edit_text("❌ Buyurtma bekor qilindi")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    user_id = callback.from_user.id
    user = db.get_user(user_id)

    # Create order
    order_id, order_num = db.create_order(
        user_id=user_id,
        service=data.get("service", "Boshqa"),
        sub_service=data.get("sub_service", ""),
        description=f"{data.get('service', '')} – {data.get('sub_service', '')}",
        address=data.get("address", ""),
        lat=data.get("latitude", 0),
        lon=data.get("longitude", 0),
        time_slot=data.get("time_slot", "Hozir"),
        price=data.get("price", 50000),
        photo=data.get("photo", ""),
        video=data.get("video", ""),
        comment=data.get("comment", ""),
        is_urgent=data.get("is_urgent", 0)
    )

    await callback.message.edit_text(
        f"✅ <b>Buyurtma yuborildi!</b>\n\n"
        f"🆔 {order_num}\n"
        f"🛠 {data.get('service', '').title()} – {data.get('sub_service', '')}\n"
        f"💰 Narx: {data.get('price', 50000):,} so'm/soat\n"
        f"📸 Rasm: {'✅' if data.get('photo') else '❌'}\n\n"
        f"⏳ Tez orada usta bog'lanadi!"
    )

    # Send to group
    try:
        urgent_text = "🚨 24/7 SHOSILINCH! " if data.get("is_urgent", 0) else ""
        await bot.send_message(
            GROUP_ID,
            f"🆕 {urgent_text}<b>YANGI BUYURTMA!</b>\n\n"
            f"🆔 {order_num}\n"
            f"🛠 Xizmat: {data.get('service', '').title()} – {data.get('sub_service', '')}\n"
            f"👤 Mijoz: {user[1] if user else 'Noma'lum'}\n"
            f"📞 {user[2] if user else ''}\n"
            f"📍 {data.get('address', '')}\n"
            f"📸 Rasm: {'✅' if data.get('photo') else '❌'}\n"
            f"💰 Narx: {data.get('price', 50000):,} so'm/soat\n"
            f"🕐 Vaqt: {data.get('time_slot', 'Hozir')}\n"
            f"📝 {data.get('comment', '')}\n\n"
            f"[✅ QABUL QILISH]  [❌ RAD ETISH]",
            reply_markup=get_order_status_keyboard(order_id)
        )
    except Exception as e:
        logger.error(f"Error sending to group: {e}")

    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🆕 Yangi buyurtma!\n"
                f"🆔 {order_num}\n"
                f"👤 {user[1] if user else 'Noma'lum'}\n"
                f"📞 {user[2] if user else ''}"
            )
        except:
            pass

    await state.clear()
    await callback.answer()

# ---------- ORDER STATUS (USTA) ----------

@dp.message(F.text == "📋 Yangi buyurtmalar")
async def new_orders_cmd(message: Message):
    orders = db.get_all_orders(status="yangi")
    if not orders:
        await message.answer("📭 Hozircha yangi buyurtmalar yo'q")
        return

    for order in orders[:5]:  # Show last 5
        await message.answer(
            f"🆕 <b>Yangi buyurtma</b>\n"
            f"🆔 {order[1]}\n"
            f"🛠 {order[3]}\n"
            f"👤 Mijoz: {db.get_user(order[2])[1] if db.get_user(order[2]) else 'Noma'lum'}\n"
            f"📍 {order[5]}\n"
            f"💰 {order[8]:,} so'm/soat\n"
            f"📸 {'✅ Rasm bor' if order[11] else '❌ Rasm yoq'}\n"
            f"🕐 {order[9]}\n\n"
            f"[✅ QABUL QILISH]  [❌ RAD ETISH]",
            reply_markup=get_order_status_keyboard(order[0])
        )

# ---------- ORDER ACCEPT/REJECT ----------

@dp.callback_query(F.data.startswith("accept_"))
async def accept_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    master_id = callback.from_user.id
    master = db.get_master(master_id)

    if not master:
        await callback.answer("❌ Siz usta sifatida ro'yxatdan o'tmaganiz!")
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi!")
        return

    # Update order
    db.update_order_status(
        order_id=order_id,
        status="qabul_qilingan",
        master_id=master_id,
        master_name=master[1]
    )

    # Notify client
    user_id = order[2]
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
            f"🆔 {order[1]}\n"
            f"🛠 {order[3]} – {order[4]}\n"
            f"👨‍🔧 Usta: {master[1]} (⭐{master[7]:.1f})\n"
            f"📞 {master[2]}\n"
            f"⏳ Ish vaqti: {order[9]}\n"
            f"💰 {order[8]:,} so'm/soat\n\n"
            f"[📞 Qo'ng'iroq]  [💬 Xabar]",
            reply_markup=get_inline_keyboard([
                ("📞 Qo'ng'iroq", f"call_master_{master_id}"),
                ("💬 Xabar", f"chat_master_{master_id}")
            ])
        )
    except:
        pass

    # Notify group
    try:
        await bot.send_message(
            GROUP_ID,
            f"✅ <b>#{order[1]} buyurtmani Usta {master[1]} qabul qildi!</b>"
        )
    except:
        pass

    await callback.message.edit_text(
        f"✅ <b>Buyurtma qabul qilindi!</b>\n"
        f"🆔 {order[1]}\n"
        f"👨‍🔧 {master[1]}"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    master_id = callback.from_user.id
    master = db.get_master(master_id)

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi!")
        return

    # Update order status back to 'yangi' for other masters
    db.update_order_status(order_id=order_id, status="yangi")

    # Notify client
    user_id = order[2]
    try:
        await bot.send_message(
            user_id,
            f"❌ <b>Buyurtmangiz rad etildi</b>\n\n"
            f"🆔 {order[1]}\n"
            f"👨‍🔧 Usta: {master[1]}\n"
            f"🔄 Biz boshqa ustani qidiramiz!\n\n"
            f"⏳ Iltimos kuting..."
        )
    except:
        pass

    # Notify group - automatic re-posting
    try:
        user = db.get_user(order[2])
        await bot.send_message(
            GROUP_ID,
            f"❌ <b>#{order[1]} buyurtmani Usta {master[1]} rad etdi!</b>\n"
            f"🔄 Boshqa ustalar ko'rib chiqsin!\n\n"
            f"🆕 <b>YANGI BUYURTMA!</b>\n"
            f"🆔 {order[1]}\n"
            f"🛠 {order[3]} – {order[4]}\n"
            f"👤 Mijoz: {user[1] if user else 'Noma'lum'}\n"
            f"📍 {order[5]}\n"
            f"💰 {order[8]:,} so'm/soat\n\n"
            f"[✅ QABUL QILISH]  [❌ RAD ETISH]",
            reply_markup=get_order_status_keyboard(order_id)
        )
    except:
        pass

    await callback.message.edit_text(
        f"❌ <b>Buyurtma rad etildi</b>\n"
        f"🔄 Boshqa ustalar ko'rib chiqadi..."
    )
    await callback.answer()

# ---------- MASTER START WORK ----------

@dp.message(F.text == "✅ Mening faol buyurtmalarim")
async def my_active_orders(message: Message):
    user_id = message.from_user.id
    orders = db.get_master_orders(user_id, "qabul_qilingan")
    orders += db.get_master_orders(user_id, "jarayonda")

    if not orders:
        await message.answer("📭 Sizda faol buyurtmalar yo'q")
        return

    for order in orders:
        await message.answer(
            f"🔧 <b>Faol buyurtma</b>\n"
            f"🆔 {order[1]}\n"
            f"🛠 {order[3]} – {order[4]}\n"
            f"👤 {db.get_user(order[2])[1] if db.get_user(order[2]) else 'Noma'lum'}\n"
            f"📍 {order[5]}\n"
            f"💰 {order[8]:,} so'm/soat\n"
            f"📊 Holat: {order[10]}\n\n"
            f"📸 {'✅ Rasm bor' if order[11] else '❌ Rasm yoq'}",
            reply_markup=get_master_order_keyboard(order[0])
        )

@dp.callback_query(F.data.startswith("start_work_"))
async def start_work(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = db.get_order(order_id)

    if not order:
        await callback.answer("❌ Buyurtma topilmadi!")
        return

    db.update_order_status(order_id=order_id, status="jarayonda")

    # Notify client
    user_id = order[2]
    try:
        await bot.send_message(
            user_id,
            f"🔧 <b>Ish boshlandi!</b>\n\n"
            f"🆔 {order[1]}\n"
            f"👨‍🔧 Usta: {order[13]}\n"
            f"⏳ Taxminiy vaqt: 1.5 soat\n\n"
            f"📞 Savollar bo'lsa, ustaga bog'lanishingiz mumkin!"
        )
    except:
        pass

    # Notify group
    try:
        await bot.send_message(
            GROUP_ID,
            f"🔧 #{order[1]} ish boshlandi! Usta: {order[13]}"
        )
    except:
        pass

    await callback.message.edit_text(
        f"🔧 <b>Ish boshlandi!</b>\n"
        f"🆔 {order[1]}"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("finish_work_"))
async def finish_work(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    await state.update_data(finish_order_id=order_id)

    await callback.message.answer(
        "📸 <b>Ish natijasi rasmini yuboring!</b>\n\n"
        "📸 Rasm yuborish MAJBURIY!\n"
        "🖼 1-5 ta rasm yuborishingiz mumkin\n\n"
        "⏱ Keyin ish vaqtini va narxni kiritasiz\n\n"
        "📸 <b>Rasm yuboring:</b>"
    )
    await state.set_state(MasterState.waiting_result_photo)
    await callback.answer()

@dp.message(MasterState.waiting_result_photo)
async def finish_work_photo(message: Message, state: FSMContext):
    photo_ids = []
    if message.photo:
        photo_ids.append(message.photo[-1].file_id)

    # If user sends multiple photos, collect them
    # We'll use a simple approach - store last photo
    await state.update_data(result_photo=",".join(photo_ids))

    await message.answer(
        "⏱ <b>Ish davomiyligini kiriting (soatlarda):</b>\n\n"
        "Masalan: 1.5 (1.5 soat)"
    )
    await state.set_state(MasterState.waiting_duration)

@dp.message(MasterState.waiting_duration)
async def finish_work_duration(message: Message, state: FSMContext):
    try:
        duration = float(message.text.replace(",", "."))
    except:
        await message.answer("❌ Iltimos, to'g'ri vaqt kiriting (masalan: 1.5):")
        return

    await state.update_data(duration=duration)

    await message.answer(
        "💰 <b>Ish narxini kiriting (so'mda):</b>\n\n"
        "Masalan: 120000"
    )
    await state.set_state(MasterState.waiting_price)

@dp.message(MasterState.waiting_price)
async def finish_work_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.replace(" ", "").replace(",", ""))
    except:
        await message.answer("❌ Iltimos, to'g'ri narx kiriting (masalan: 120000):")
        return

    data = await state.get_data()
    order_id = data.get("finish_order_id")
    result_photo = data.get("result_photo", "")
    duration = data.get("duration", 1)

    order = db.get_order(order_id)
    if not order:
        await message.answer("❌ Buyurtma topilmadi!")
        await state.clear()
        return

    # Update order
    db.update_order_status(
        order_id=order_id,
        status="tugallangan",
        duration=int(duration),
        price=price,
        result_photo=result_photo
    )

    # Add bonus for client (if order completed)
    user_id = order[2]
    db.add_bonus(user_id, order_id, int(price * 0.05), "order_complete")

    # Notify client
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Ish yakunlandi!</b>\n\n"
            f"🆔 {order[1]}\n"
            f"🛠 {order[3]} – {order[4]}\n"
            f"👨‍🔧 Usta: {order[13]}\n"
            f"⏱ Davomiyligi: {duration} soat\n"
            f"💰 To'lov: {price:,} so'm\n\n"
            f"📸 <b>Ish natijasi rasmi:</b>\n"
            f"✅ {result_photo.count(',') + 1 if result_photo else 0} ta rasm\n\n"
            f"💵 <b>To'lov:</b> Faqat naqd pul!\n"
            f"⭐ <b>Reyting qoldirishni unutmang!</b>"
        )
    except:
        pass

    # Notify group
    try:
        await bot.send_message(
            GROUP_ID,
            f"✅ #{order[1]} buyurtma yakunlandi!\n"
            f"👨‍🔧 Usta: {order[13]} (⭐4.8)\n"
            f"⏱ {duration} soat\n"
            f"💰 {price:,} so'm\n"
            f"📸 {result_photo.count(',') + 1 if result_photo else 0} ta rasm"
        )
    except:
        pass

    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"✅ <b>Ish yakunlandi!</b>\n"
                f"🆔 {order[1]}\n"
                f"👤 Mijoz: {db.get_user(order[2])[1] if db.get_user(order[2]) else 'Noma'lum'}\n"
                f"👨‍🔧 Usta: {order[13]}\n"
                f"⏱ {duration} soat\n"
                f"💰 {price:,} so'm\n"
                f"📸 Rasm: {'✅' if result_photo else '❌'}\n\n"
                f"[✅ Tasdiqlash]  [❌ Rad etish]",
                reply_markup=get_inline_keyboard([
                    ("✅ Tasdiqlash", f"admin_confirm_{order_id}"),
                    ("❌ Rad etish", f"admin_reject_{order_id}")
                ])
            )
        except:
            pass

    await message.answer(
        f"✅ <b>Buyurtma yakunlandi!</b>\n\n"
        f"🆔 {order[1]}\n"
        f"⏱ {duration} soat\n"
        f"💰 {price:,} so'm\n"
        f"📸 Rasm: {'✅' if result_photo else '❌'}\n\n"
        f"📨 Mijozga xabar yuborildi!\n"
        f"📨 Adminga xabar yuborildi!"
    )

    await state.clear()

# ---------- REVIEW ----------

@dp.message(F.text == "⭐ Reytingim")
async def my_rating(message: Message):
    user_id = message.from_user.id
    master = db.get_master(user_id)

    if not master:
        # Show user's rating as client
        orders = db.get_user_orders(user_id, "tugallangan")
        total_orders = len(orders)
        await message.answer(
            f"⭐ <b>Mening reytingim</b>\n\n"
            f"📋 Jami buyurtmalar: {total_orders}\n"
            f"⭐ Siz hali reyting qoldirmagansiz\n\n"
            f"📝 Buyurtmalaringizni yakunlang va reyting qoldiring!"
        )
        return

    reviews = db.get_master_reviews(user_id)

    rating_text = f"⭐ <b>Mening reytingim</b>\n\n"
    rating_text += f"⭐ {master[7]:.1f} ({master[8]} ta baho)\n\n"

    if reviews:
        rating_text += "📝 <b>Oxirgi sharhlar:</b>\n"
        for review in reviews[:3]:
            rating_text += f"├── ⭐ {review[3]} – {review[4][:50]}...\n"

    rating_text += f"\n📊 <b>Statistika:</b>\n"
    rating_text += f"├── Jami ish: {master[8]} ta\n"
    rating_text += f"├── 24/7: {'✅' if master[8] == 1 else '❌'}\n"
    rating_text += f"└── Narx: {master[4]:,} so'm/soat"

    await message.answer(rating_text)

@dp.message(F.text == "📝 Sharh qoldirish")
async def review_cmd(message: Message, state: FSMContext):
    orders = db.get_user_orders(message.from_user.id, "tugallangan")

    if not orders:
        await message.answer("📭 Sizda yakunlangan buyurtmalar yo'q")
        return

    buttons = []
    for order in orders[:5]:
        master_name = order[13] or "Noma'lum"
        buttons.append((f"#{order[1]} – {master_name}", f"review_order_{order[0]}"))

    if not buttons:
        await message.answer("📭 Sharh qoldirish uchun buyurtma topilmadi")
        return

    await message.answer(
        "⭐ <b>Kimga sharh qoldirmoqchisiz?</b>",
        reply_markup=get_inline_keyboard(buttons)
    )
    await state.set_state(ReviewState.waiting_master)

@dp.callback_query(ReviewState.waiting_master)
async def review_select_master(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    order = db.get_order(order_id)

    if not order:
        await callback.answer("❌ Buyurtma topilmadi!")
        return

    await state.update_data(review_order_id=order_id, master_id=order[12])

    await callback.message.edit_text(
        "⭐ <b>Baho bering:</b>",
        reply_markup=get_inline_keyboard([
            ("⭐", "rating_1"),
            ("⭐⭐", "rating_2"),
            ("⭐⭐⭐", "rating_3"),
            ("⭐⭐⭐⭐", "rating_4"),
            ("⭐⭐⭐⭐⭐", "rating_5")
        ])
    )
    await state.set_state(ReviewState.waiting_rating)
    await callback.answer()

@dp.callback_query(ReviewState.waiting_rating)
async def review_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)

    await callback.message.edit_text(
        "📝 <b>Sharhingizni yozing:</b>\n\n"
        "Fikringizni yozib qoldiring..."
    )
    await state.set_state(ReviewState.waiting_review)
    await callback.answer()

@dp.message(ReviewState.waiting_review)
async def review_text(message: Message, state: FSMContext):
    await state.update_data(review=message.text)

    await message.answer(
        "📸 <b>Rasm yuboring (ixtiyoriy):</b>\n\n"
        "🖼 Rasm yuborish yoki ⏭ O'tkazib yuborish",
        reply_markup=get_inline_keyboard([
            ("⏭ O'tkazib yuborish", "review_skip_photo")
        ])
    )
    await state.set_state(ReviewState.waiting_photo)

@dp.message(ReviewState.waiting_photo)
async def review_photo(message: Message, state: FSMContext):
    photo_id = ""
    if message.photo:
        photo_id = message.photo[-1].file_id

    await state.update_data(photo=photo_id)
    await save_review(message, state)

@dp.callback_query(F.data == "review_skip_photo")
async def review_skip_photo(callback: CallbackQuery, state: FSMContext):
    await state.update_data(photo="")
    await callback.message.edit_text("⏭ Rasm o'tkazib yuborildi")
    await save_review(callback.message, state)
    await callback.answer()

async def save_review(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("review_order_id")
    master_id = data.get("master_id")
    rating = data.get("rating")
    review_text = data.get("review")
    photo = data.get("photo", "")

    if not all([order_id, master_id, rating, review_text]):
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
        await state.clear()
        return

    # Save review
    db.add_review(order_id, message.from_user.id, master_id, rating, review_text, photo)

    # Update order status
    db.update_order_status(order_id, "tugallangan")

    # Add bonus
    db.add_bonus(message.from_user.id, order_id, 100, "review")

    await message.answer(
        f"✅ <b>Sharhingiz yuborildi!</b>\n\n"
        f"⭐ {rating} yulduz\n"
        f"📝 {review_text[:100]}...\n\n"
        f"🎁 Sizga 100 bonus ball qo'shildi!"
    )

    # Notify master
    try:
        await bot.send_message(
            master_id,
            f"⭐ <b>Sizga yangi sharh qoldirildi!</b>\n"
            f"⭐ {rating} yulduz\n"
            f"📝 {review_text[:100]}..."
        )
    except:
        pass

    await state.clear()

# ---------- HELP AND OTHER ----------

@dp.message(F.text == "📞 Tez yordam")
async def help_cmd(message: Message):
    await message.answer(
        "📞 <b>Tez yordam</b>\n\n"
        "1️⃣ 📞 Dispetcher: +9987706900003\n"
        "2️⃣ 💬 Bot orqali yozing: @usta24_bot\n"
        "3️⃣ ❓ Ko'p so'raladigan savollar:\n\n"
        "Q: Qanday buyurtma berish mumkin?\n"
        "A: '🛒 Buyurtma berish' tugmasini bosing!\n\n"
        "Q: Narx qanday hisoblanadi?\n"
        "A: Xizmat turiga qarab 40,000-80,000 so'm/soat\n\n"
        "Q: Ustani qanday tanlash mumkin?\n"
        "A: Sizga eng yaqin usta avtomatik tanlanadi!\n\n"
        "Q: To'lov qanday amalga oshiriladi?\n"
        "A: Faqat naqd pul! Ishdan keyin to'lov!\n\n"
        "Q: 24/7 rejim qanday ishlaydi?\n"
        "A: Shosilingch holatda 10-15 daqiqada yetib boramiz!",
        reply_markup=get_inline_keyboard([
            ("📞 Dispetcher", "call_dispetcher"),
            ("🚨 24/7", "urgent_help")
        ])
    )

@dp.callback_query(F.data == "urgent_help")
async def urgent_help_callback(callback: CallbackQuery):
    await callback.message.answer(
        "🚨 <b>24/7 SHOSILINCH YORDAM</b>\n\n"
        "📞 Dispetcher: +9987706900003\n"
        "🕐 24/7 ishlaydi! KUTISH YO'Q!\n\n"
        "⚡ <b>Dolzarb holatlar:</b>\n"
        "├── 💧 Suv tўхtab qoldi\n"
        "├── ⚡ Elektr ўчиб қолди\n"
        "├── 🔥 Газ оқаётган\n"
        "├── 🚪 Эшик синиб қолди\n"
        "└── 🚰 Қувур ёрилган\n\n"
        "💰 <b>Narx:</b>\n"
        "├── 20% ustama (kechki vaqt)\n"
        "├── Faqat naqd pul!\n"
        "└── Ishdan keyin to'lov!\n\n"
        "📞 Dispetcherga hoziroq qo'ng'iroq qiling!"
    )
    await callback.answer()

# ---------- ADMIN HANDLERS ----------

@dp.message(F.text == "👥 Foydalanuvchilar")
async def admin_users(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return

    users = db.get_all_users()
    mijozlar = len([u for u in users if u[3] == "mijoz"])
    ustalar = len([u for u in users if u[3] == "usta"])

    await message.answer(
        f"👥 <b>Foydalanuvchilar statistikasi</b>\n\n"
        f"📊 Jami: {len(users)} ta\n"
        f"├── 👤 Mijozlar: {mijozlar} ta\n"
        f"├── 👨‍🔧 Ustalar: {ustalar} ta\n"
        f"└── 👨‍💼 Adminlar: {len(ADMIN_IDS)} ta\n\n"
        f"📊 <b>So'nggi 5 ta foydalanuvchi:</b>"
    )

    for user in users[-5:]:
        await message.answer(
            f"🆔 {user[0]}\n"
            f"👤 {user[1]}\n"
            f"📞 {user[2]}\n"
            f"🎭 {user[3]}\n"
            f"📅 {user[5]}"
        )

@dp.message(F.text == "🛠 Buyurtmalar")
async def admin_orders(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return

    stats = db.get_orders_stats()

    await message.answer(
        f"📊 <b>Buyurtma statistikasi</b>\n\n"
        f"📋 Jami: {stats[0]} ta\n"
        f"├── 🆕 Yangi: {stats[1]} ta\n"
        f"├── ✅ Qabul qilingan: {stats[2]} ta\n"
        f"├── 🔧 Jarayonda: {stats[3]} ta\n"
        f"├── ✅ Tugallangan: {stats[4]} ta\n"
        f"└── ❌ Bekor: {stats[5]} ta\n\n"
        f"💰 Jami daromad: {stats[6] or 0:,} so'm"
    )

@dp.message(F.text == "👨‍🔧 Ustalar")
async def admin_masters(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz!")
        return

    masters = db.get_all_masters()

    if not masters:
        await message.answer("📭 Hozircha ustalar yo'q")
        return

    await message.answer(
        f"👨‍🔧 <b>Ustalar ({len(masters)} ta):</b>"
    )

    for master in masters[:5]:
        await message.answer(
            f"👨‍🔧 {master[1]}\n"
            f"📞 {master[2]}\n"
            f"🛠 {master[3]}\n"
            f"💰 {master[4]:,} so'm/soat\n"
            f"⭐ {master[7]:.1f} ({master[8]} ta ish)\n"
            f"🕐 {master[9]}\n"
            f"24/7: {'✅' if master[8] else '❌'}"
        )

# ---------- ADMIN ORDER CONFIRM/REJECT ----------

@dp.callback_query(F.data.startswith("admin_confirm_"))
async def admin_confirm(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Siz admin emassiz!")
        return

    await callback.message.edit_text(
        f"✅ <b>Buyurtma admin tomonidan tasdiqlandi!</b>\n"
        f"🆔 #{order_id}"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_reject_"))
async def admin_reject(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Siz admin emassiz!")
        return

    db.update_order_status(order_id, "bekor_qilingan")

    await callback.message.edit_text(
        f"❌ <b>Buyurtma admin tomonidan rad etildi!</b>\n"
        f"🆔 #{order_id}"
    )
    await callback.answer()

# ---------- CALLBACK FOR VIEWING PHOTOS ----------

@dp.callback_query(F.data.startswith("view_photos_"))
async def view_photos(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    order = db.get_order(order_id)

    if not order:
        await callback.answer("❌ Buyurtma topilmadi!")
        return

    photos = []
    if order[11]:  # problem_photo
        photos.extend(order[11].split(","))
    if order[12]:  # result_photo
        photos.extend(order[12].split(","))

    if not photos:
        await callback.answer("📸 Bu buyurtmada rasmlar yo'q")
        return

    # Send first photo
    try:
        for photo_id in photos[:5]:
            if photo_id:
                await callback.message.answer_photo(photo_id)
    except:
        pass

    await callback.answer()

# ---------- STATISTICS ----------

@dp.message(F.text == "📊 Mening statistika")
async def my_stats(message: Message):
    user_id = message.from_user.id
    orders = db.get_user_orders(user_id)

    total = len(orders)
    completed = len([o for o in orders if o[10] == "tugallangan"])
    cancelled = len([o for o in orders if o[10] == "bekor_qilingan"])
    in_progress = len([o for o in orders if o[10] not in ["tugallangan", "bekor_qilingan"]])

    bonuses = db.get_user_bonuses(user_id)

    await message.answer(
        f"📊 <b>Mening statistika</b>\n\n"
        f"📋 Jami buyurtmalar: {total}\n"
        f"├── ✅ Tugallangan: {completed}\n"
        f"├── 🔧 Jarayonda: {in_progress}\n"
        f"└── ❌ Bekor: {cancelled}\n\n"
        f"🎁 Bonuslar: {bonuses:,} ball\n"
        f"💰 1 ball = 100 so'm\n"
        f"💵 Jami: {bonuses * 100:,} so'm"
    )

@dp.message(F.text == "📊 Ish statistikasi")
async def master_stats(message: Message):
    user_id = message.from_user.id
    master = db.get_master(user_id)

    if not master:
        await message.answer("❌ Siz usta emassiz!")
        return

    orders = db.get_master_orders(user_id)

    total = len(orders)
    completed = len([o for o in orders if o[10] == "tugallangan"])
    total_price = sum([o[8] for o in orders if o[10] == "tugallangan"])

    await message.answer(
        f"📊 <b>Ish statistikasi</b>\n\n"
        f"👨‍🔧 {master[1]}\n"
        f"⭐ {master[7]:.1f} ({master[8]} ta ish)\n\n"
        f"📋 Jami buyurtmalar: {total}\n"
        f"├── ✅ Tugallangan: {completed}\n"
        f"└── ⏳ Jarayonda: {total - completed}\n\n"
        f"💰 Jami daromad: {total_price:,} so'm\n"
        f"💰 O'rtacha: {total_price // max(completed, 1):,} so'm"
    )

# ---------- BONUS ----------

@dp.message(F.text == "🎁 Loyallik va bonuslar")
async def bonus_cmd(message: Message):
    user_id = message.from_user.id
    bonuses = db.get_user_bonuses(user_id)

    orders = db.get_user_orders(user_id)
    completed = len([o for o in orders if o[10] == "tugallangan"])

    # Level calculation
    if bonuses < 500:
        level = "🥉 Mis"
    elif bonuses < 1000:
        level = "🥈 Kumush"
    elif bonuses < 3000:
        level = "🥇 Oltin"
    elif bonuses < 5000:
        level = "💎 Platina"
    else:
        level = "👑 Olmos"

    await message.answer(
        f"🎁 <b>Loyallik va bonuslar</b>\n\n"
        f"💰 Bonus ball: {bonuses:,}\n"
        f"💵 1 ball = 100 so'm\n"
        f"💰 Jami: {bonuses * 100:,} so'm\n\n"
        f"🏆 <b>Darajangiz:</b> {level}\n\n"
        f"📋 <b>Darajalar:</b>\n"
        f"├── 🥉 Mis: 0-500 ball\n"
        f"├── 🥈 Kumush: 501-1000 ball\n"
        f"├── 🥇 Oltin: 1001-3000 ball\n"
        f"├── 💎 Platina: 3001-5000 ball\n"
        f"└── 👑 Olmos: 5000+ ball\n\n"
        f"📊 Jami buyurtmalar: {completed} ta"
    )

# ---------- SETTINGS ----------

@dp.message(F.text == "⚙️ Sozlamalar")
async def settings_cmd(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)

    await message.answer(
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"👤 {user[1] if user else ''}\n"
        f"📞 {user[2] if user else ''}\n"
        f"🎭 {user[3] if user else ''}\n"
        f"🌐 Til: 🇺🇿 O'zbek\n\n"
        f"🔔 Bildirishnomalar: ✅ Yoqilgan\n"
        f"🔊 Ovoz: 🔊 Yoqilgan\n\n"
        f"📱 <b>Telefon:</b>\n"
        f"├── 📞 Dispetcher: {DISPETCHER_PHONE}\n"
        f"└── 🤖 Bot: @usta24_bot",
        reply_markup=get_inline_keyboard([
            ("🌐 Tilni o'zgartirish", "settings_lang"),
            ("🔔 Bildirishnomalar", "settings_notif"),
            ("📞 Telefon o'zgartirish", "settings_phone"),
            ("⬅️ Orqaga", "back")
        ])
    )

# ---------- ERROR HANDLER ----------

@dp.errors()
async def error_handler(event, error):
    logger.error(f"Error: {error}")
    try:
        if event.message:
            await event.message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.")
    except:
        pass

# ---------- MAIN ----------

async def main():
    logger.info("🚀 Starting USTA 24 ANDIJON bot...")
    logger.info(f"📞 Dispetcher: {DISPETCHER_PHONE}")
    logger.info(f"👥 Admins: {ADMIN_IDS}")
    logger.info(f"📨 Group ID: {GROUP_ID}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
