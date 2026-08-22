import asyncio
import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

# ============================================================
# USTA 24 ANDIJON — CLEAN MAIN.PY
# aiogram 3.x
# SQLite
#
# ENV:
# BOT_TOKEN=...
# ADMIN_IDS=123,456
# DISPATCHER_IDS=123,456        # optional
# DISPATCHER_ID=123             # optional, supported
# MASTERS_GROUP_ID=-100...      # optional
# DATABASE=usta24.db            # optional
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("USTA24")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE = os.getenv("DATABASE", "usta24.db")

def env_ids(name: str) -> List[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    result = []
    for value in raw.split(","):
        value = value.strip()
        if value:
            try:
                result.append(int(value))
            except ValueError:
                logger.warning("Noto'g'ri ID: %s", value)
    return result

ADMIN_IDS = env_ids("ADMIN_IDS")
DISPATCHER_IDS = env_ids("DISPATCHER_IDS")
single_dispatcher = os.getenv("DISPATCHER_ID", "").strip()
if single_dispatcher:
    try:
        DISPATCHER_IDS.append(int(single_dispatcher))
    except ValueError:
        logger.warning("DISPATCHER_ID noto'g'ri")

DISPATCHER_IDS = list(dict.fromkeys(DISPATCHER_IDS))
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID", "").strip()
try:
    MASTERS_GROUP_ID = int(MASTERS_GROUP_ID) if MASTERS_GROUP_ID else None
except ValueError:
    MASTERS_GROUP_ID = None

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable topilmadi!")

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ============================================================
# DATABASE
# ============================================================

def db_connect():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'mijoz',
                language TEXT NOT NULL DEFAULT 'uz',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_blocked INTEGER DEFAULT 0,
                block_reason TEXT,
                block_until TEXT
            );

            CREATE TABLE IF NOT EXISTS masters (
                user_id INTEGER PRIMARY KEY,
                rating REAL DEFAULT 0,
                rating_count INTEGER DEFAULT 0,
                total_orders INTEGER DEFAULT 0,
                total_earnings INTEGER DEFAULT 0,
                services TEXT DEFAULT '',
                work_days TEXT DEFAULT '1,2,3,4,5',
                work_start TEXT DEFAULT '08:00',
                work_end TEXT DEFAULT '20:00',
                lunch_start TEXT DEFAULT '13:00',
                lunch_end TEXT DEFAULT '14:00',
                max_orders_per_day INTEGER DEFAULT 5,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                service_type TEXT NOT NULL DEFAULT '',
                service_name TEXT NOT NULL DEFAULT '',
                client_name TEXT NOT NULL DEFAULT '',
                client_phone TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                latitude REAL,
                longitude REAL,
                photo_ids TEXT DEFAULT '[]',
                description TEXT DEFAULT '',
                preferred_time TEXT DEFAULT '',
                price INTEGER DEFAULT 0,
                status TEXT DEFAULT 'yangi',
                master_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                started_at TEXT,
                completed_at TEXT,
                rating INTEGER,
                review TEXT,
                cancel_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                from_user_id INTEGER,
                to_user_id INTEGER,
                rating INTEGER,
                review TEXT,
                photo_ids TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                master_id INTEGER,
                service_name TEXT,
                booking_date TEXT,
                booking_time TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                discount INTEGER DEFAULT 0,
                used_by INTEGER,
                is_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    logger.info("SQLite database tayyor: %s", DATABASE)


USER_COLUMNS = [
    "user_id", "full_name", "phone", "role", "language",
    "created_at", "is_blocked", "block_reason", "block_until"
]

ORDER_COLUMNS = [
    "id", "order_number", "user_id", "service_type", "service_name",
    "client_name", "client_phone", "address", "latitude", "longitude",
    "photo_ids", "description", "preferred_time", "price", "status",
    "master_id", "created_at", "started_at", "completed_at",
    "rating", "review", "cancel_reason"
]


def row_to_dict(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row_to_dict(row)


def save_user(
    user_id: int,
    full_name: str,
    phone: str,
    role: str = "mijoz",
    language: str = "uz",
):
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, full_name, phone, role, language)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                phone=excluded.phone,
                role=excluded.role,
                language=excluded.language
            """,
            (user_id, full_name, phone, role, language),
        )
        if role == "usta":
            conn.execute(
                "INSERT OR IGNORE INTO masters(user_id) VALUES (?)",
                (user_id,),
            )


def create_order(data: Dict[str, Any]) -> int:
    now = datetime.now()
    order_number = f"U24-{now.strftime('%y%m%d%H%M%S')}-{now.microsecond // 1000:03d}"

    photo_ids = data.get("photo_ids", [])
    if isinstance(photo_ids, str):
        try:
            json.loads(photo_ids)
        except Exception:
            photo_ids = []
    else:
        photo_ids = json.dumps(photo_ids or [], ensure_ascii=False)

    with db_connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders(
                order_number, user_id, service_type, service_name,
                client_name, client_phone, address, latitude, longitude,
                photo_ids, description, preferred_time, price, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'yangi')
            """,
            (
                order_number,
                data["user_id"],
                data.get("service_type", ""),
                data.get("service_name", ""),
                data.get("client_name", ""),
                data.get("client_phone", ""),
                data.get("address", ""),
                data.get("latitude"),
                data.get("longitude"),
                photo_ids,
                data.get("description", ""),
                data.get("preferred_time", ""),
                int(data.get("price") or 0),
            ),
        )
        return cur.lastrowid


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
    return row_to_dict(row)


def update_order(order_id: int, **fields):
    if not fields:
        return
    allowed = {
        "status", "master_id", "started_at", "completed_at",
        "rating", "review", "cancel_reason", "preferred_time", "price"
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return

    sql = ", ".join(f"{key} = ?" for key in clean)
    values = list(clean.values()) + [order_id]

    with db_connect() as conn:
        conn.execute(f"UPDATE orders SET {sql} WHERE id = ?", values)


def get_user_orders(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM orders
            WHERE user_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(x) for x in rows]


def get_master_orders(master_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM orders
            WHERE master_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (master_id, limit),
        ).fetchall()
    return [dict(x) for x in rows]


def get_masters(service_type: Optional[str] = None) -> List[Dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT u.user_id, u.full_name, u.phone,
                   m.rating, m.rating_count, m.total_orders,
                   m.total_earnings, m.services, m.is_active
            FROM users u
            JOIN masters m ON m.user_id = u.user_id
            WHERE u.role = 'usta' AND m.is_active = 1
            ORDER BY m.rating DESC, m.total_orders DESC
            """
        ).fetchall()

    result = [dict(x) for x in rows]
    if not service_type:
        return result

    filtered = []
    for master in result:
        services = (master.get("services") or "").lower()
        if not services or service_type.lower() in services:
            filtered.append(master)
    return filtered


def get_all_orders(limit: int = 50) -> List[Dict[str, Any]]:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(x) for x in rows]


# ============================================================
# HELPERS
# ============================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_dispatcher(user_id: int) -> bool:
    return user_id in DISPATCHER_IDS or user_id in ADMIN_IDS


def is_master(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and user.get("role") == "usta")


def money(value: Any) -> str:
    try:
        return f"{int(value or 0):,}".replace(",", " ")
    except Exception:
        return "0"


def normalize_phone(text: str) -> str:
    phone = re.sub(r"[^\d+]", "", text or "")
    if phone.startswith("998"):
        return "+" + phone
    if phone.startswith("0") and len(phone) >= 9:
        return "+998" + phone[1:]
    if phone.startswith("+998"):
        return phone
    if phone.isdigit():
        return "+998" + phone
    return phone


async def notify(user_id: int, text: str, reply_markup=None):
    try:
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO notifications(user_id, message) VALUES (?, ?)",
                (user_id, text),
            )
        await bot.send_message(
            user_id, text, reply_markup=reply_markup, parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Notify %s xato: %s", user_id, e)


# ============================================================
# KEYBOARDS
# ============================================================

def main_menu(role: str) -> ReplyKeyboardMarkup:
    if role == "usta":
        rows = [
            ["👤 Mening profilim", "🆕 Yangi buyurtmalar"],
            ["📋 Mening buyurtmalarim", "📊 Mening statistikam"],
            ["💰 Kunlik daromad", "⭐ Reytingim"],
            ["🔧 Ishni boshlash", "✅ Ishni yakunlash"],
            ["❌ Buyurtma rad etish", "📞 Dispetcher bilan bog'lanish"],
            ["🏠 Bosh menyu", "🚪 Chiqish"],
        ]
    elif role == "dispetcher":
        rows = [
            ["📨 Yangi buyurtmalar", "📋 Barcha buyurtmalar"],
            ["👨‍🔧 Ustalar ro'yxati", "🔗 Ustaga biriktirish"],
            ["📊 Statistika", "📄 Hisobotlar"],
            ["🏠 Bosh menyu", "🚪 Chiqish"],
        ]
    elif role == "admin":
        rows = [
            ["👨‍🔧 Ustalar", "📋 Barcha buyurtmalar"],
            ["👥 Mijozlar", "📊 Statistika"],
            ["💰 Narxlar", "💬 Xabar tarqatish"],
            ["🚫 Bloklash", "📞 Dispetcher"],
            ["🏠 Bosh menyu", "🚪 Chiqish"],
        ]
    else:
        rows = [
            ["🛒 Buyurtma berish"],
            ["📋 Mening buyurtmalarim", "🔍 Buyurtma holati"],
            ["❌ Buyurtmani bekor qilish", "🔁 Qayta buyurtma"],
            ["⭐ Reytingim", "📝 Sharh qoldirish"],
            ["📞 Dispetcher bilan bog'lanish"],
            ["🏠 Bosh menyu", "🚪 Chiqish"],
        ]

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x) for x in row] for row in rows],
        resize_keyboard=True,
    )


def service_type_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛠 Sanitariya"), KeyboardButton(text="⚡ Elektr")],
            [KeyboardButton(text="🔧 Mexanik"), KeyboardButton(text="🧹 Tozalash")],
            [KeyboardButton(text="📦 Yuk tashish"), KeyboardButton(text="❓ Boshqa")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


SERVICE_MAP = {
    "🛠 Sanitariya": "sanitariya",
    "⚡ Elektr": "elektr",
    "🔧 Mexanik": "mexanik",
    "🧹 Tozalash": "tozalash",
    "📦 Yuk tashish": "yuk_tashish",
    "❓ Boshqa": "boshqa",
}

SERVICES = {
    "sanitariya": {
        "🚽 Hojatxona o'rnatish": 80000,
        "🚿 Lavabo o'rnatish": 70000,
        "🔧 Quvur ta'miri": 90000,
        "🧹 Kanalizatsiya tozalash": 100000,
        "🚰 Suv o'rnatish": 85000,
    },
    "elektr": {
        "💡 Chiroq o'rnatish": 50000,
        "🔌 Rozetka o'rnatish": 60000,
        "🔧 Sim almashtirish": 80000,
        "⚡ Avtomat o'chirgich": 70000,
        "📹 Kamera o'rnatish": 90000,
    },
    "mexanik": {
        "🚪 Eshik ta'miri": 70000,
        "🪟 Deraza ta'miri": 65000,
        "🪑 Mebel yig'ish": 75000,
        "❄️ Konditsioner o'rnatish": 150000,
        "🔒 Qulf almashtirish": 60000,
    },
    "tozalash": {
        "🏠 Uy tozalash": 50000,
        "🏢 Ofis tozalash": 60000,
        "🧶 Gilam tozalash": 70000,
        "🪟 Deraza tozalash": 55000,
        "🧹 Umumiy tozalash": 65000,
    },
    "yuk_tashish": {
        "📦 Kichik yuk": 30000,
        "📦 O'rta yuk": 50000,
        "📦 Katta yuk": 80000,
        "🏠 Ko'chirish": 200000,
        "🚛 Yuk tashish": 150000,
    },
}


def service_kb(service_type: str):
    names = list(SERVICES.get(service_type, {}).keys()) or ["📋 Boshqa"]
    rows = []
    for i in range(0, len(names), 2):
        rows.append([KeyboardButton(text=x) for x in names[i:i + 2]])
    rows.append([KeyboardButton(text="🔙 Orqaga")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def back_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Orqaga")]],
        resize_keyboard=True,
    )


def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Kontakt yuborish", request_contact=True)],
            [KeyboardButton(text="✏️ O'zim yozaman")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


# ============================================================
# FSM
# ============================================================

class StartStates(StatesGroup):
    name = State()
    phone = State()


class OrderStates(StatesGroup):
    service_type = State()
    service_name = State()
    client_name = State()
    client_phone = State()
    address = State()
    photo = State()
    description = State()
    time = State()
    confirm = State()


class MasterStates(StatesGroup):
    waiting_time = State()
    custom_time = State()


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)

    if user:
        if user.get("is_blocked"):
            await message.answer(
                "⛔ Siz bloklangansiz.\n"
                f"Sabab: {user.get('block_reason') or 'Ko‘rsatilmagan'}"
            )
            return

        role = user.get("role", "mijoz")
        if role == "admin" and not is_admin(message.from_user.id):
            role = "mijoz"
        if role == "dispetcher" and not is_dispatcher(message.from_user.id):
            role = "mijoz"

        await message.answer(
            f"👋 Xush kelibsiz, <b>{user.get('full_name') or message.from_user.first_name}</b>!",
            reply_markup=main_menu(role),
            parse_mode="HTML",
        )
        await state.clear()
        return

    await message.answer(
        "🕌 <b>USTA 24 ANDIJON</b>\n\n"
        "Xush kelibsiz!\n"
        "Avval ismingizni kiriting:",
        reply_markup=back_kb(),
        parse_mode="HTML",
    )
    await state.set_state(StartStates.name)


@dp.message(StartStates.name)
async def start_name(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer("🏠 /start orqali qayta kiring.")
        return

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("❌ Ism kamida 2 harf bo‘lsin.")
        return

    await state.update_data(full_name=name)
    await message.answer(
        "📞 Telefon raqamingizni yuboring:",
        reply_markup=phone_kb(),
    )
    await state.set_state(StartStates.phone)


@dp.message(StartStates.phone)
async def start_phone(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(StartStates.name)
        await message.answer("👤 Ismingizni kiriting:", reply_markup=back_kb())
        return

    if message.contact:
        phone = normalize_phone(message.contact.phone_number)
    else:
        phone = normalize_phone(message.text or "")

    if len(re.sub(r"\D", "", phone)) < 9:
        await message.answer("❌ Telefon raqami noto‘g‘ri.")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    # Рольни фойдаланувчи танламайди.
    # Admin/dispatcher роли ENV орқали берилади.
    if is_admin(user_id):
        role = "admin"
    elif is_dispatcher(user_id):
        role = "dispetcher"
    else:
        role = "mijoz"

    save_user(user_id, data["full_name"], phone, role)
    await state.clear()

    await message.answer(
        f"✅ Xush kelibsiz, <b>{data['full_name']}</b>!\n\n"
        f"🏠 <b>{role.upper()} MENYUSI</b>",
        reply_markup=main_menu(role),
        parse_mode="HTML",
    )


# ============================================================
# CLIENT — ORDER
# ============================================================

@dp.message(F.text == "🛒 Buyurtma berish")
async def order_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Avval /start bosing.")
        return
    if user.get("is_blocked"):
        await message.answer("⛔ Siz bloklangansiz.")
        return

    await state.update_data(user_id=message.from_user.id)
    await message.answer(
        "📌 <b>1-qadam: xizmat turini tanlang</b>",
        reply_markup=service_type_kb(),
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.service_type)


@dp.message(OrderStates.service_type)
async def order_service_type(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.clear()
        await message.answer(
            "🏠 Bosh menyu",
            reply_markup=main_menu("mijoz"),
        )
        return

    service_type = SERVICE_MAP.get(message.text)
    if not service_type:
        await message.answer("❌ Tugmalardan birini tanlang.")
        return

    await state.update_data(service_type=service_type)

    if service_type == "boshqa":
        await message.answer(
            "❓ Qaysi xizmat kerakligini yozing:",
            reply_markup=back_kb(),
        )
    else:
        await message.answer(
            "📌 <b>2-qadam: xizmatni tanlang</b>",
            reply_markup=service_kb(service_type),
            parse_mode="HTML",
        )

    await state.set_state(OrderStates.service_name)


@dp.message(OrderStates.service_name)
async def order_service_name(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await message.answer(
            "📌 Xizmat turini tanlang:",
            reply_markup=service_type_kb(),
        )
        await state.set_state(OrderStates.service_type)
        return

    data = await state.get_data()
    service_type = data.get("service_type")

    service_name = (message.text or "").strip()
    if not service_name:
        await message.answer("❌ Xizmat nomini yozing.")
        return

    price = SERVICES.get(service_type, {}).get(service_name, 0)

    await state.update_data(
        service_name=service_name,
        price=price,
    )

    await message.answer(
        f"🛠 <b>{service_name}</b>\n"
        f"💰 Boshlang‘ich narx: <b>{money(price)} so‘m</b>\n\n"
        "👤 Buyurtma uchun ismni kiriting:",
        reply_markup=back_kb(),
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.client_name)


@dp.message(OrderStates.client_name)
async def order_client_name(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        data = await state.get_data()
        await message.answer(
            "📌 Xizmatni tanlang:",
            reply_markup=service_kb(data.get("service_type", "sanitariya")),
        )
        await state.set_state(OrderStates.service_name)
        return

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("❌ Ism kamida 2 harf bo‘lsin.")
        return

    await state.update_data(client_name=name)
    await message.answer(
        "📞 Telefon raqamingiz:",
        reply_markup=phone_kb(),
    )
    await state.set_state(OrderStates.client_phone)


@dp.message(OrderStates.client_phone)
async def order_client_phone(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(OrderStates.client_name)
        await message.answer("👤 Ismingizni kiriting:", reply_markup=back_kb())
        return

    phone = (
        normalize_phone(message.contact.phone_number)
        if message.contact
        else normalize_phone(message.text or "")
    )

    if len(re.sub(r"\D", "", phone)) < 9:
        await message.answer("❌ Telefon raqami noto‘g‘ri.")
        return

    await state.update_data(client_phone=phone)

    await message.answer(
        "📍 <b>Manzil</b>\n\n"
        "Lokatsiyani yuboring yoki manzilni matn bilan yozing.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(
                    text="📍 Geolokatsiya yuborish",
                    request_location=True
                )],
                [KeyboardButton(text="✏️ Matn bilan yozish")],
                [KeyboardButton(text="🔙 Orqaga")],
            ],
            resize_keyboard=True,
        ),
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.address)


@dp.message(OrderStates.address)
async def order_address(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(OrderStates.client_phone)
        await message.answer("📞 Telefon:", reply_markup=phone_kb())
        return

    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        address = f"📍 Lokatsiya: {lat}, {lon}"
        await state.update_data(
            address=address,
            latitude=lat,
            longitude=lon,
        )
    elif message.text == "✏️ Matn bilan yozish":
        await message.answer(
            "🏠 To‘liq manzilni yozing:",
            reply_markup=back_kb(),
        )
        return
    else:
        address = (message.text or "").strip()
        if len(address) < 3:
            await message.answer("❌ Manzilni aniqroq yozing.")
            return
        await state.update_data(address=address, latitude=None, longitude=None)

    await message.answer(
        "📸 Muammo joyining rasmini yuboring.\n\n"
        "1–5 ta rasm yuborishingiz mumkin.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ O‘tkazib yuborish")],
                [KeyboardButton(text="🔙 Orqaga")],
            ],
            resize_keyboard=True,
        ),
    )
    await state.update_data(photo_ids=[])
    await state.set_state(OrderStates.photo)


@dp.message(OrderStates.photo)
async def order_photo(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(OrderStates.address)
        await message.answer(
            "📍 Manzilni yuboring:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(
                        text="📍 Geolokatsiya yuborish",
                        request_location=True
                    )],
                    [KeyboardButton(text="✏️ Matn bilan yozish")],
                    [KeyboardButton(text="🔙 Orqaga")],
                ],
                resize_keyboard=True,
            ),
        )
        return

    if message.text == "⏭ O‘tkazib yuborish":
        await state.update_data(photo_ids=[])
        await ask_description(message, state)
        return

    if message.photo:
        data = await state.get_data()
        photos = data.get("photo_ids", [])
        photos.append(message.photo[-1].file_id)
        photos = photos[:5]
        await state.update_data(photo_ids=photos)

        if len(photos) >= 5:
            await ask_description(message, state)
        else:
            await message.answer(
                f"✅ Rasm saqlandi: {len(photos)}/5\n"
                "Yana rasm yuboring yoki «O‘tkazib yuborish» bosing."
            )
        return

    await message.answer("📸 Rasm yuboring yoki «O‘tkazib yuborish» bosing.")


async def ask_description(message: Message, state: FSMContext):
    await message.answer(
        "📝 Qo‘shimcha izoh yozing yoki o‘tkazib yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏭ O‘tkazib yuborish")],
                [KeyboardButton(text="🔙 Orqaga")],
            ],
            resize_keyboard=True,
        ),
    )
    await state.set_state(OrderStates.description)


@dp.message(OrderStates.description)
async def order_description(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(OrderStates.photo)
        await message.answer("📸 Rasm yuboring:")
        return

    description = "" if message.text == "⏭ O‘tkazib yuborish" else (message.text or "")
    await state.update_data(description=description)

    await message.answer(
        "🕐 <b>Qachon kerak?</b>",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔴 Hozir")],
                [KeyboardButton(text="🟡 Bugun kechqurun")],
                [KeyboardButton(text="🟢 Ertaga ertalab")],
                [KeyboardButton(text="📆 Aniq vaqt")],
                [KeyboardButton(text="🔙 Orqaga")],
            ],
            resize_keyboard=True,
        ),
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.time)


@dp.message(OrderStates.time)
async def order_time(message: Message, state: FSMContext):
    if message.text == "🔙 Orqaga":
        await state.set_state(OrderStates.description)
        await message.answer("📝 Izoh:", reply_markup=back_kb())
        return

    if message.text == "📆 Aniq vaqt":
        now = datetime.now()
        rows = []
        for i in range(0, 5):
            d = now + timedelta(days=i)
            rows.append([
                KeyboardButton(text=d.strftime("%d-%m-%Y"))
            ])
        rows.append([KeyboardButton(text="🔙 Orqaga")])
        await message.answer(
            "📅 Sanani tanlang:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=rows,
                resize_keyboard=True,
            ),
        )
        return

    # Date selection: only valid YYYY-MM-DD-ish DD-MM-YYYY values.
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", message.text or ""):
        await state.update_data(selected_date=message.text)
        await message.answer(
            "🕐 Soatni tanlang (masalan, 14:00):",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="08:00"), KeyboardButton(text="09:00")],
                    [KeyboardButton(text="10:00"), KeyboardButton(text="11:00")],
                    [KeyboardButton(text="12:00"), KeyboardButton(text="13:00")],
                    [KeyboardButton(text="14:00"), KeyboardButton(text="15:00")],
                    [KeyboardButton(text="16:00"), KeyboardButton(text="17:00")],
                    [KeyboardButton(text="18:00"), KeyboardButton(text="19:00")],
                    [KeyboardButton(text="20:00"), KeyboardButton(text="21:00")],
                    [KeyboardButton(text="🔙 Orqaga")],
                ],
                resize_keyboard=True,
            ),
        )
        return

    data = await state.get_data()
    selected_date = data.get("selected_date")

    if selected_date and re.fullmatch(r"\d{2}:\d{2}", message.text or ""):
        preferred = f"{selected_date} {message.text}"
    else:
        preferred = message.text

    await state.update_data(preferred_time=preferred)
    await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photo_ids", [])

    text = (
        "📋 <b>BUYURTMA TEKSHIRUVI</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🛠 Xizmat: {data.get('service_name', '-')}\n"
        f"👤 Ism: {data.get('client_name', '-')}\n"
        f"📞 Telefon: {data.get('client_phone', '-')}\n"
        f"📍 Manzil: {data.get('address', '-')}\n"
        f"📸 Rasmlar: {len(photos)} ta\n"
        f"📝 Izoh: {data.get('description') or 'Yo‘q'}\n"
        f"🕐 Vaqt: {data.get('preferred_time', '-')}\n"
        f"💰 Narx: {money(data.get('price'))} so‘m\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    await message.answer(
        text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Tasdiqlash")],
                [KeyboardButton(text="✏️ Tahrirlash")],
                [KeyboardButton(text="❌ Bekor qilish")],
            ],
            resize_keyboard=True,
        ),
        parse_mode="HTML",
    )
    await state.set_state(OrderStates.confirm)


@dp.message(OrderStates.confirm)
async def order_confirm(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer(
            "❌ Buyurtma bekor qilindi.",
            reply_markup=main_menu("mijoz"),
        )
        return

    if message.text == "✏️ Tahrirlash":
        await state.set_state(OrderStates.service_type)
        await message.answer(
            "📌 Xizmat turini qaytadan tanlang:",
            reply_markup=service_type_kb(),
        )
        return

    if message.text != "✅ Tasdiqlash":
        await message.answer("❌ Tugmalardan birini tanlang.")
        return

    data = await state.get_data()
    order_id = create_order(data)
    order = get_order(order_id)

    await message.answer(
        "🎉 <b>BUYURTMA QABUL QILINDI!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 {order['order_number']}\n"
        "⏳ Holat: Dispetcher tekshirmoqda.\n"
        "📨 Sizga keyingi holat haqida xabar beriladi.",
        reply_markup=main_menu("mijoz"),
        parse_mode="HTML",
    )

    await send_order_to_dispatchers(order)
    await state.clear()


# ============================================================
# SEND ORDER TO DISPATCHERS
# ============================================================

def order_text(order: Dict[str, Any]) -> str:
    return (
        "🆕 <b>YANGI BUYURTMA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 {order['order_number']}\n"
        f"🛠 {order['service_name']}\n"
        f"💰 {money(order['price'])} so‘m\n"
        f"🕐 {order['preferred_time'] or '-'}\n\n"
        f"👤 Mijoz: {order['client_name']}\n"
        f"📞 {order['client_phone']}\n"
        f"📍 {order['address']}\n"
        f"📝 {order['description'] or 'Izoh yo‘q'}\n"
        f"📸 Rasmlar: {len(json.loads(order['photo_ids'] or '[]'))} ta"
    )


def dispatcher_order_kb(order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📨 USTALARGA YUBORISH",
                    callback_data=f"disp_send_{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ BEKOR QILISH",
                    callback_data=f"disp_cancel_{order_id}",
                )
            ],
        ]
    )


async def send_order_to_dispatchers(order: Dict[str, Any]):
    targets = list(dict.fromkeys(ADMIN_IDS + DISPATCHER_IDS))
    if not targets:
        logger.warning("ADMIN_IDS/DISPATCHER_IDS bo‘sh!")
        return

    text = order_text(order)
    photos = json.loads(order.get("photo_ids") or "[]")

    for user_id in targets:
        await notify(
            user_id,
            text,
            dispatcher_order_kb(order["id"]),
        )
        for photo_id in photos[:5]:
            try:
                await bot.send_photo(user_id, photo_id)
            except Exception:
                pass


# ============================================================
# DISPATCHER — SEND TO MASTERS
# ============================================================

@dp.callback_query(F.data.startswith("disp_send_"))
async def dispatcher_send_masters(callback: CallbackQuery):
    if not is_dispatcher(callback.from_user.id):
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return

    order_id = int(callback.data.rsplit("_", 1)[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi.", show_alert=True)
        return

    masters = get_masters(order["service_type"])
    if not masters:
        await callback.answer(
            "❌ Faol usta topilmadi.",
            show_alert=True,
        )
        return

    update_order(order_id, status="taklif_yuborildi")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ QABUL QILAMAN",
                    callback_data=f"accept_order_{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ RAD ETAMAN",
                    callback_data=f"reject_order_{order_id}",
                ),
            ]
        ]
    )

    text = (
        "🆕 <b>USTA UCHUN YANGI BUYURTMA</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 {order['order_number']}\n"
        f"🛠 {order['service_name']}\n"
        f"💰 {money(order['price'])} so‘m\n"
        f"🕐 {order['preferred_time']}\n"
        f"👤 {order['client_name']}\n"
        f"📞 {order['client_phone']}\n"
        f"📍 {order['address']}\n"
    )

    # Agar guruh ko‘rsatilgan bo‘lsa, avval guruhga yuboriladi.
    if MASTERS_GROUP_ID:
        try:
            await bot.send_message(
                MASTERS_GROUP_ID,
                text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            for photo_id in json.loads(order.get("photo_ids") or "[]")[:5]:
                try:
                    await bot.send_photo(MASTERS_GROUP_ID, photo_id)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Masters group xato: %s", e)

    # Guruh bo‘lmasa yoki qo‘shimcha ravishda individual ustalarga.
    for master in masters:
        await notify(master["user_id"], text, kb)

    await callback.answer(
        f"✅ {len(masters)} ta ustaga yuborildi.",
        show_alert=True,
    )


# ============================================================
# MASTER — ACCEPT / REJECT
# ============================================================

@dp.callback_query(F.data.startswith("accept_order_"))
async def master_accept(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if not is_master(user_id):
        await callback.answer("⛔ Siz usta sifatida ro‘yxatdan o‘tmagansiz.", show_alert=True)
        return

    order_id = int(callback.data.rsplit("_", 1)[1])
    order = get_order(order_id)

    if not order:
        await callback.answer("❌ Buyurtma topilmadi.", show_alert=True)
        return

    if order["status"] in {"qabul_qilindi", "ish_boshlandi", "yakunlandi", "bekor"}:
        await callback.answer("⚠️ Bu buyurtma allaqachon band.", show_alert=True)
        return

    await state.update_data(order_id=order_id)

    await callback.message.answer(
        f"🆔 {order['order_number']}\n"
        "⏱ Mijoz oldiga qachon bora olasiz?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🔴 Hozir")],
                [KeyboardButton(text="🟡 15 daqiqa")],
                [KeyboardButton(text="🟢 30 daqiqa")],
                [KeyboardButton(text="📝 Boshqa vaqt")],
            ],
            resize_keyboard=True,
        ),
    )
    await state.set_state(MasterStates.waiting_time)
    await callback.answer()


@dp.callback_query(F.data.startswith("reject_order_"))
async def master_reject(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_master(user_id):
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return

    order_id = int(callback.data.rsplit("_", 1)[1])
    order = get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi.", show_alert=True)
        return

    await callback.answer("❌ Buyurtma rad etildi.")
    await notify(
        user_id,
        f"❌ {order['order_number']} buyurtmasini rad etdingiz.",
        main_menu("usta"),
    )


@dp.message(MasterStates.waiting_time)
async def master_time(message: Message, state: FSMContext):
    if message.text == "📝 Boshqa vaqt":
        await message.answer("🕐 Vaqtni yozing. Masalan: 18:30")
        await state.set_state(MasterStates.custom_time)
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        await message.answer("❌ Buyurtma topilmadi.")
        return

    await finish_master_accept(message, state, order_id, message.text)


@dp.message(MasterStates.custom_time)
async def master_custom_time(message: Message, state: FSMContext):
    if not re.fullmatch(r"\d{1,2}:\d{2}", message.text or ""):
        await message.answer("❌ Vaqt noto‘g‘ri. Masalan: 18:30")
        return

    data = await state.get_data()
    order_id = data.get("order_id")
    if not order_id:
        await state.clear()
        await message.answer("❌ Buyurtma topilmadi.")
        return

    await finish_master_accept(message, state, order_id, message.text)


async def finish_master_accept(
    message: Message,
    state: FSMContext,
    order_id: int,
    arrival_time: str,
):
    order = get_order(order_id)
    if not order:
        await state.clear()
        await message.answer("❌ Buyurtma topilmadi.")
        return

    master_id = message.from_user.id
    update_order(
        order_id,
        status="qabul_qilindi",
        master_id=master_id,
    )

    master_name = message.from_user.full_name or "Usta"

    await notify(
        order["user_id"],
        "✅ <b>Buyurtmangiz qabul qilindi!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 {order['order_number']}\n"
        f"👨‍🔧 Usta: {master_name}\n"
        f"⏱ Kelish vaqti: {arrival_time}\n"
        f"📞 Telefon: {order['client_phone']}",
        main_menu("mijoz"),
    )

    for user_id in list(dict.fromkeys(ADMIN_IDS + DISPATCHER_IDS)):
        await notify(
            user_id,
            "✅ <b>Usta buyurtmani qabul qildi</b>\n"
            f"🆔 {order['order_number']}\n"
            f"👨‍🔧 Usta: {master_name}\n"
            f"⏱ {arrival_time}",
        )

    await message.answer(
        f"✅ {order['order_number']} qabul qilindi.\n"
        f"⏱ Kelish vaqti: {arrival_time}",
        reply_markup=main_menu("usta"),
    )
    await state.clear()


# ============================================================
# CLIENT — MY ORDERS / STATUS / CANCEL
# ============================================================

STATUS_UZ = {
    "yangi": "⏳ Yangi",
    "taklif_yuborildi": "📨 Ustalarga yuborildi",
    "qabul_qilindi": "✅ Usta qabul qildi",
    "ish_boshlandi": "🔧 Ish boshlandi",
    "yakunlandi": "🏁 Yakunlandi",
    "bekor": "❌ Bekor qilindi",
}


@dp.message(F.text == "📋 Mening buyurtmalarim")
async def my_orders(message: Message):
    orders = get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("📭 Sizda hali buyurtmalar yo‘q.")
        return

    lines = ["📋 <b>BUYURTMALARIM</b>\n"]
    for o in orders[:15]:
        lines.append(
            f"🆔 <b>{o['order_number']}</b>\n"
            f"🛠 {o['service_name']}\n"
            f"📌 {STATUS_UZ.get(o['status'], o['status'])}\n"
            f"💰 {money(o['price'])} so‘m\n"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(F.text == "🔍 Buyurtma holati")
async def order_status(message: Message):
    orders = get_user_orders(message.from_user.id, 1)
    if not orders:
        await message.answer("📭 Buyurtma topilmadi.")
        return
    o = orders[0]
    await message.answer(
        f"🔍 <b>BUYURTMA HOLATI</b>\n"
        f"🆔 {o['order_number']}\n"
        f"🛠 {o['service_name']}\n"
        f"📌 {STATUS_UZ.get(o['status'], o['status'])}\n"
        f"👨‍🔧 Usta ID: {o['master_id'] or 'Hali biriktirilmagan'}",
        parse_mode="HTML",
    )


@dp.message(F.text == "❌ Buyurtmani bekor qilish")
async def cancel_order_menu(message: Message):
    orders = get_user_orders(message.from_user.id)
    active = [o for o in orders if o["status"] in {
        "yangi", "taklif_yuborildi", "qabul_qilindi"
    }]
    if not active:
        await message.answer("📭 Bekor qilinadigan faol buyurtma yo‘q.")
        return

    buttons = [
        [
            InlineKeyboardButton(
                text=f"❌ {o['order_number']}",
                callback_data=f"client_cancel_{o['id']}",
            )
        ]
        for o in active[:10]
    ]
    await message.answer(
        "❌ Qaysi buyurtmani bekor qilasiz?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.callback_query(F.data.startswith("client_cancel_"))
async def client_cancel(callback: CallbackQuery):
    order_id = int(callback.data.rsplit("_", 1)[1])
    order = get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("❌ Ruxsat yo‘q.", show_alert=True)
        return

    if order["status"] not in {"yangi", "taklif_yuborildi", "qabul_qilindi"}:
        await callback.answer("⚠️ Bu buyurtmani bekor qilib bo‘lmaydi.", show_alert=True)
        return

    update_order(order_id, status="bekor", cancel_reason="Mijoz bekor qildi")
    await callback.message.edit_text(
        f"❌ {order['order_number']} bekor qilindi."
    )
    await callback.answer("Bekor qilindi.")


# ============================================================
# MASTER MENUS
# ============================================================

@dp.message(F.text == "🆕 Yangi buyurtmalar")
async def master_new_orders(message: Message):
    if not is_master(message.from_user.id):
        return

    orders = get_all_orders(30)
    orders = [o for o in orders if o["status"] in {"taklif_yuborildi", "yangi"}]

    if not orders:
        await message.answer("📭 Yangi buyurtmalar yo‘q.")
        return

    for o in orders[:10]:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="✅ QABUL",
                    callback_data=f"accept_order_{o['id']}",
                ),
                InlineKeyboardButton(
                    text="❌ RAD",
                    callback_data=f"reject_order_{o['id']}",
                ),
            ]]
        )
        await message.answer(order_text(o), reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "📋 Mening buyurtmalarim")
async def shared_my_orders(message: Message):
    user = get_user(message.from_user.id)
    if user and user.get("role") == "usta":
        orders = get_master_orders(message.from_user.id)
        if not orders:
            await message.answer("📭 Sizga biriktirilgan buyurtmalar yo‘q.")
            return
        text = ["📋 <b>MENING BUYURTMALARIM</b>\n"]
        for o in orders[:15]:
            text.append(
                f"🆔 {o['order_number']}\n"
                f"🛠 {o['service_name']}\n"
                f"📌 {STATUS_UZ.get(o['status'], o['status'])}\n"
            )
        await message.answer("\n".join(text), parse_mode="HTML")
    else:
        # Client handler is already registered earlier; this handler is
        # intentionally only reached according to router ordering if needed.
        await my_orders(message)


@dp.message(F.text == "🔧 Ishni boshlash")
async def master_start_work(message: Message):
    if not is_master(message.from_user.id):
        return
    orders = get_master_orders(message.from_user.id)
    active = [o for o in orders if o["status"] == "qabul_qilindi"]
    if not active:
        await message.answer("📭 Boshlash uchun buyurtma yo‘q.")
        return

    o = active[0]
    update_order(
        o["id"],
        status="ish_boshlandi",
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    await notify(
        o["user_id"],
        f"🔧 <b>{o['order_number']}</b> bo‘yicha ish boshlandi.",
        main_menu("mijoz"),
    )
    await message.answer(
        f"🔧 {o['order_number']} bo‘yicha ish boshlandi.",
        reply_markup=main_menu("usta"),
    )


@dp.message(F.text == "✅ Ishni yakunlash")
async def master_finish_work(message: Message):
    if not is_master(message.from_user.id):
        return
    orders = get_master_orders(message.from_user.id)
    active = [o for o in orders if o["status"] == "ish_boshlandi"]
    if not active:
        await message.answer("📭 Yakunlanadigan ish yo‘q.")
        return

    o = active[0]
    update_order(
        o["id"],
        status="yakunlandi",
        completed_at=datetime.now().isoformat(timespec="seconds"),
    )
    await notify(
        o["user_id"],
        f"🏁 <b>{o['order_number']}</b> buyurtma yakunlandi.\n"
        "⭐ Ustaga baho berishingiz mumkin.",
        main_menu("mijoz"),
    )
    await message.answer(
        f"🏁 {o['order_number']} yakunlandi.",
        reply_markup=main_menu("usta"),
    )


@dp.message(F.text == "📊 Mening statistikam")
async def master_stats(message: Message):
    if not is_master(message.from_user.id):
        return
    orders = get_master_orders(message.from_user.id, 10000)
    done = [o for o in orders if o["status"] == "yakunlandi"]
    earnings = sum(int(o["price"] or 0) for o in done)
    await message.answer(
        "📊 <b>MENING STATISTIKAM</b>\n"
        f"📦 Jami: {len(orders)}\n"
        f"🏁 Yakunlangan: {len(done)}\n"
        f"💰 Daromad: {money(earnings)} so‘m",
        parse_mode="HTML",
    )


@dp.message(F.text == "💰 Kunlik daromad")
async def daily_income(message: Message):
    if not is_master(message.from_user.id):
        return
    today = datetime.now().strftime("%Y-%m-%d")
    orders = get_master_orders(message.from_user.id, 10000)
    total = 0
    for o in orders:
        if o["status"] == "yakunlandi" and str(o["completed_at"] or "").startswith(today):
            total += int(o["price"] or 0)
    await message.answer(f"💰 Bugungi daromad: <b>{money(total)} so‘m</b>", parse_mode="HTML")


# ============================================================
# ADMIN / DISPATCHER
# ============================================================

@dp.message(F.text.in_({
    "📨 Yangi buyurtmalar",
    "📋 Barcha buyurtmalar",
}))
async def staff_orders(message: Message):
    if not is_dispatcher(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return

    orders = get_all_orders(50)
    if not orders:
        await message.answer("📭 Buyurtmalar yo‘q.")
        return

    for o in orders[:20]:
        await message.answer(
            order_text(o),
            reply_markup=dispatcher_order_kb(o["id"]),
            parse_mode="HTML",
        )


@dp.message(F.text.in_({"👨‍🔧 Ustalar ro'yxati", "👨‍🔧 Ustalar"}))
async def staff_masters(message: Message):
    if not is_dispatcher(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return

    masters = get_masters()
    if not masters:
        await message.answer("📭 Ustalar ro‘yxati bo‘sh.")
        return

    text = ["👨‍🔧 <b>USTALAR</b>\n"]
    for m in masters:
        text.append(
            f"👤 {m['full_name'] or '-'}\n"
            f"🆔 {m['user_id']}\n"
            f"⭐ {m['rating']:.1f}\n"
            f"📦 {m['total_orders']}\n"
        )
    await message.answer("\n".join(text), parse_mode="HTML")


@dp.message(F.text == "📊 Statistika")
async def staff_statistics(message: Message):
    if not is_dispatcher(message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return

    orders = get_all_orders(100000)
    counts = {}
    for o in orders:
        counts[o["status"]] = counts.get(o["status"], 0) + 1

    await message.answer(
        "📊 <b>STATISTIKA</b>\n"
        f"📦 Jami: {len(orders)}\n"
        f"⏳ Yangi: {counts.get('yangi', 0)}\n"
        f"📨 Taklif: {counts.get('taklif_yuborildi', 0)}\n"
        f"✅ Qabul: {counts.get('qabul_qilindi', 0)}\n"
        f"🔧 Ishda: {counts.get('ish_boshlandi', 0)}\n"
        f"🏁 Yakun: {counts.get('yakunlandi', 0)}\n"
        f"❌ Bekor: {counts.get('bekor', 0)}",
        parse_mode="HTML",
    )


# ============================================================
# SIMPLE MENUS
# ============================================================

@dp.message(F.text == "📞 Dispetcher bilan bog'lanish")
async def contact_dispatcher(message: Message):
    if not DISPATCHER_IDS:
        await message.answer("⚠️ Dispetcher ID sozlanmagan.")
        return
    await message.answer("📞 Dispetcherga xabaringizni yozing. U siz bilan bog‘lanadi.")


@dp.message(F.text == "📞 Dispetcher")
async def admin_dispatcher(message: Message):
    if not is_admin(message.from_user.id):
        return
    if not DISPATCHER_IDS:
        await message.answer("⚠️ DISPATCHER_ID sozlanmagan.")
        return
    await message.answer(
        "📞 Dispetcher ID:\n" +
        "\n".join(str(x) for x in DISPATCHER_IDS)
    )


@dp.message(F.text == "🏠 Bosh menyu")
async def home(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    role = user.get("role", "mijoz") if user else "mijoz"
    if role == "admin" and not is_admin(message.from_user.id):
        role = "mijoz"
    if role == "dispetcher" and not is_dispatcher(message.from_user.id):
        role = "mijoz"
    await message.answer(
        "🏠 Bosh menyu",
        reply_markup=main_menu(role),
    )


@dp.message(F.text == "🚪 Chiqish")
async def logout(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Chiqdingiz.\nQayta kirish uchun /start bosing.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="/start")]],
            resize_keyboard=True,
        ),
    )


# ============================================================
# FALLBACK
# ============================================================

@dp.message()
async def fallback(message: Message):
    user = get_user(message.from_user.id)
    role = user.get("role", "mijoz") if user else "mijoz"

    if role == "admin" and not is_admin(message.from_user.id):
        role = "mijoz"
    if role == "dispetcher" and not is_dispatcher(message.from_user.id):
        role = "mijoz"

    await message.answer(
        "❌ Tushunmadim. Menyudan foydalaning.",
        reply_markup=main_menu(role),
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    init_db()

    me = await bot.get_me()
    logger.info("Bot ishga tushdi: @%s", me.username)
    logger.info("ADMIN_IDS=%s", ADMIN_IDS)
    logger.info("DISPATCHER_IDS=%s", DISPATCHER_IDS)
    logger.info("MASTERS_GROUP_ID=%s", MASTERS_GROUP_ID)

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to‘xtatildi.")
