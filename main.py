# =====================================================
# USTA 24 PRO BOT
# MAIN.PY — 1/2
# MIJOZ + BUYURTMA + SAQLASH
# =====================================================

import os
import logging
import sqlite3

from datetime import datetime

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


# =====================================================
# CONFIG
# =====================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
DISPATCHER_ID = os.getenv("DISPATCHER_ID")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")

if not DISPATCHER_ID:
    raise RuntimeError("DISPATCHER_ID topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")


ADMIN_ID = int(ADMIN_ID)
DISPATCHER_ID = int(DISPATCHER_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger("USTA24")


# =====================================================
# DATABASE
# =====================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "usta24.db"
)


# Agar Render PostgreSQL URL bersa,
# keyingi qismda ulash mumkin.
# Hozir botning asosiy ishlashi SQLite orqali.


conn = sqlite3.connect(
    "usta24.db",
    check_same_thread=False
)

cursor = conn.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE,
    name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    address TEXT DEFAULT '',
    latitude TEXT DEFAULT '',
    longitude TEXT DEFAULT '',
    created_at TEXT
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    name TEXT,
    phone TEXT,
    service TEXT,
    address TEXT,
    latitude TEXT,
    longitude TEXT,
    comment TEXT,
    status TEXT DEFAULT 'new',
    master_id INTEGER,
    master_name TEXT,
    created_at TEXT
)
""")


conn.commit()


# =====================================================
# BUYURTMA JARAYONI
# =====================================================

user_states = {}


# =====================================================
# XIZMATLAR
# =====================================================

SERVICES = [

    "🪑 Мебель йиғиш",

    "🛠 Мебель таъмирлаш",

    "🍽 Ошхона мебели",

    "🚪 Шкаф купе",

    "🛏 Каравот йиғиш",

    "🪑 Стол стул",

    "📦 Мебель кўчириш",

    "🚚 Уй кўчириш",

    "🚛 Юк ташиш",

    "🔩 Сантехника",

    "⚡ Электр ишлари",

    "🔥 Иситиш тизими",

    "🎨 Бўёқ ишлари",

    "🪟 Эшик дераза",

    "❄️ Кондиционер",

    "📡 Интернет",

    "🧹 Тозалаш",

    "🔨 Пайвандлаш",

    "🏠 Уста чақириш",

    "🔧 Бошқа хизмат"

]


# =====================================================
# STATUS
# =====================================================

STATUS = {

    "new": "🆕 Янги",

    "dispatcher": "👨‍💼 Диспетчер кўриб чиқмоқда",

    "accepted": "🟡 Қабул қилинган",

    "assigned": "👨‍🔧 Уста бириктирилган",

    "process": "🔵 Иш жараёнида",

    "done": "✅ Якунланган",

    "cancel": "❌ Бекор қилинган",

    "reject": "🚫 Рад этилган"

}


# =====================================================
# MIJOZ MENYUSI
# =====================================================

def client_menu():

    return ReplyKeyboardMarkup(

        [

            ["📝 Буюртма бериш"],

            ["📋 Хизматлар", "📦 Буюртмаларим"],

            ["🔁 Қайта буюртма"]

        ],

        resize_keyboard=True
    )


# =====================================================
# XIZMAT MENYUSI
# =====================================================

def service_menu():

    rows = []

    row = []

    for service in SERVICES:

        row.append(service)

        if len(row) == 2:

            rows.append(row)

            row = []


    if row:

        rows.append(row)


    return ReplyKeyboardMarkup(

        rows,

        resize_keyboard=True
    )


# =====================================================
# ORQAGA MENYUSI
# =====================================================

def back_menu():

    return ReplyKeyboardMarkup(

        [

            ["⬅️ Орқага"]

        ],

        resize_keyboard=True
    )


# =====================================================
# START
# =====================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return


    # Бот буюртма жараёнини
    # фақат шахсий чатда ишлатади.

    if update.effective_chat.type != "private":

        await update.message.reply_text(

            "📱 Буюртма бериш учун "
            "ботга шахсий чатда /start босинг."
        )

        return


    user = update.effective_user


    save_user(

        user.id,

        name=user.first_name or ""
    )


    user_states.pop(
        user.id,
        None
    )


    await update.message.reply_text(

        f"👋 Ассалому алайкум, "
        f"{user.first_name or 'ҳурматли мижоз'}!\n\n"

        "🏠 USTA 24\n\n"

        "Уй ва мебель хизматлари.\n"
        "Сизга керакли хизматни танланг:",

        reply_markup=client_menu()
    )


# =====================================================
# USER SAQLASH
# =====================================================

def save_user(
    telegram_id,
    name=None,
    phone=None,
    address=None,
    latitude=None,
    longitude=None
):

    cursor.execute(

        "SELECT id FROM users WHERE telegram_id = ?",

        (telegram_id,)
    )

    exists = cursor.fetchone()


    if exists:

        if name is not None:

            cursor.execute(

                """
                UPDATE users
                SET name = ?
                WHERE telegram_id = ?
                """,

                (name, telegram_id)
            )


        if phone is not None:

            cursor.execute(

                """
                UPDATE users
                SET phone = ?
                WHERE telegram_id = ?
                """,

                (phone, telegram_id)
            )


        if address is not None:

            cursor.execute(

                """
                UPDATE users
                SET address = ?
                WHERE telegram_id = ?
                """,

                (address, telegram_id)
            )


        if latitude is not None:

            cursor.execute(

                """
                UPDATE users
                SET latitude = ?
                WHERE telegram_id = ?
                """,

                (latitude, telegram_id)
            )


        if longitude is not None:

            cursor.execute(

                """
                UPDATE users
                SET longitude = ?
                WHERE telegram_id = ?
                """,

                (longitude, telegram_id)
            )


    else:

        cursor.execute(

            """
            INSERT INTO users (
                telegram_id,
                name,
                phone,
                address,
                latitude,
                longitude,
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,

            (
                telegram_id,
                name or "",
                phone or "",
                address or "",
                latitude or "",
                longitude or "",
                datetime.now().isoformat()
            )
        )


    conn.commit()


# =====================================================
# OLDINGI MIJOZ MA'LUMOTLARI
# =====================================================

def get_user(telegram_id):

    cursor.execute(

        """
        SELECT
            telegram_id,
            name,
            phone,
            address,
            latitude,
            longitude
        FROM users
        WHERE telegram_id = ?
        """,

        (telegram_id,)
    )


    row = cursor.fetchone()


    if not row:

        return None


    return {

        "telegram_id": row[0],

        "name": row[1],

        "phone": row[2],

        "address": row[3],

        "latitude": row[4],

        "longitude": row[5]

    }


# =====================================================
# BUYURTMA BOSHLASH
# =====================================================

async def new_order(
    update,
    context
):

    if not update.message:
        return


    # Телефон тугмаси фақат private chatда
    if update.effective_chat.type != "private":

        await update.message.reply_text(

            "📱 Буюртма бериш учун "
            "ботга шахсий чатда мурожаат қилинг."
        )

        return


    uid = update.effective_user.id


    old_user = get_user(uid)


    user_states[uid] = {

        "step": "name",

        "name": "",

        "phone": "",

        "service": "",

        "address": "",

        "latitude": "",

        "longitude": "",

        "comment": ""

    }


    # Агар олдинги маълумот бор бўлса,
    # мижозга осонлаштириш учун кўрсатамиз.

    if old_user and old_user["name"]:

        keyboard = InlineKeyboardMarkup([

            [

                InlineKeyboardButton(

                    "✅ Олдинги маълумотдан фойдаланиш",

                    callback_data="reuse_info"
                )

            ],

            [

                InlineKeyboardButton(

                    "✏️ Янги маълумот киритиш",

                    callback_data="new_info"
                )

            ]

        ])


        await update.message.reply_text(

            "🔁 Сиз аввал буюртма бергансиз.\n\n"

            f"👤 Исм: {old_user['name']}\n"
            f"📞 Телефон: {old_user['phone']}\n"
            f"📍 Манзил: {old_user['address'] or 'киритилмаган'}\n\n"

            "Шу маълумотлардан фойдаланасизми?",

            reply_markup=keyboard
        )

        return


    await update.message.reply_text(

        "📝 ЯНГИ БУЮРТМА\n\n"

        "1️⃣ Исмингизни ёзинг:"
    )


# =====================================================
# CALLBACK — OLDINGI MA'LUMOT
# =====================================================

async def reuse_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()


    uid = query.from_user.id


    old_user = get_user(uid)


    if not old_user:

        await query.edit_message_text(

            "❌ Олдинги маълумот топилмади."
        )

        return


    user_states[uid] = {

        "step": "service",

        "name": old_user["name"],

        "phone": old_user["phone"],

        "service": "",

        "address": old_user["address"],

        "latitude": old_user["latitude"],

        "longitude": old_user["longitude"],

        "comment": ""

    }


    await query.edit_message_text(

        "✅ Олдинги маълумотлар қабул қилинди.\n\n"

        "🛠 Энди хизматни танланг:"
    )


    await context.bot.send_message(

        chat_id=uid,

        text="🛠 Хизматни танланг:",

        reply_markup=service_menu()
    )


# =====================================================
# CALLBACK — YANGI MA'LUMOT
# =====================================================

async def new_info_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()


    uid = query.from_user.id


    user_states[uid] = {

        "step": "name",

        "name": "",

        "phone": "",

        "service": "",

        "address": "",

        "latitude": "",

        "longitude": "",

        "comment": ""

    }


    await query.edit_message_text(

        "✏️ Янги маълумот киритамиз.\n\n"

        "👤 Исмингизни ёзинг:"
    )


# =====================================================
# TELEFON TUGMASI
# =====================================================

def phone_keyboard():

    button = KeyboardButton(

        "📞 Телефон рақамимни юбориш",

        request_contact=True
    )


    return ReplyKeyboardMarkup(

        [

            [button],

            ["✍️ Рақамни қўлда ёзиш"]

        ],

        resize_keyboard=True,

        one_time_keyboard=True
    )


# =====================================================
# MANZIL TUGMASI
# =====================================================

def location_keyboard():

    button = KeyboardButton(

        "📍 Геолокация юбориш",

        request_location=True
    )


    return ReplyKeyboardMarkup(

        [

            [button],

            ["✍️ Манзилни ёзиш"]

        ],

        resize_keyboard=True
    )


# =====================================================
# CLIENT MESSAGE
# =====================================================

async def client_handler(
    update,
    context
):

    if not update.message:
        return


    # Буюртма жараёни фақат private chatда
    if update.effective_chat.type != "private":
        return


    uid = update.effective_user.id

    text = update.message.text or ""


    # =================================================
    # BUYURTMA BOSHLASH
    # =================================================

    if text == "📝 Буюртма бериш":

        await new_order(
            update,
            context
        )

        return


    # =================================================
    # XIZMATLAR
    # =================================================

    if text == "📋 Хизматлар":

        await update.message.reply_text(

            "🛠 USTA 24 ХИЗМАТЛАРИ\n\n"

            + "\n".join(
                f"• {x}"
                for x in SERVICES
            ),

            reply_markup=client_menu()
        )

        return


    # =================================================
    # BUYURTMALARIM
    # =================================================

    if text == "📦 Буюртмаларим":

        await my_orders(
            update,
            context
        )

        return


    # =================================================
    # QAYTA BUYURTMA
    # =================================================

    if text == "🔁 Қайта буюртма":

        await new_order(
            update,
            context
        )

        return


    # =================================================
    # USER STATE YO'Q
    # =================================================

    if uid not in user_states:

        return


    data = user_states[uid]

    step = data["step"]


    # =================================================
    # ISM
    # =================================================

    if step == "name":

        if len(text.strip()) < 2:

            await update.message.reply_text(

                "❌ Исмни тўғри ёзинг."
            )

            return


        data["name"] = text.strip()

        data["step"] = "phone"


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг:\n\n"

            "Тугма орқали юборишингиз мумкин.",

            reply_markup=phone_keyboard()
        )

        return


    # =================================================
    # TELEFON
    # =================================================

    if step == "phone":

        phone = ""


        if update.message.contact:

            phone = (
                update.message.contact.phone_number
            )


        elif text == "✍️ Рақамни қўлда ёзиш":

            await update.message.reply_text(

                "📞 Телефон рақамингизни ёзинг:\n\n"
                "Масалан:\n"
                "+998901234567"
            )

            return


        else:

            phone = text.strip()


        if len(phone) < 7:

            await update.message.reply_text(

                "❌ Телефон рақами нотўғри.\n"
                "Қайта киритинг."
            )

            return


        data["phone"] = phone


        save_user(

            uid,

            name=data["name"],

            phone=phone
        )


        data["step"] = "service"


        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=service_menu()
        )

        return


    # =================================================
    # XIZMAT
    # =================================================

    if step == "service":

        if text not in SERVICES:

            await update.message.reply_text(

                "🛠 Илтимос, хизматни тугмалардан танланг.",

                reply_markup=service_menu()
            )

            return


        data["service"] = text

        data["step"] = "address"


        await update.message.reply_text(

            "📍 Манзилни юборинг.\n\n"

            "Геолокация юборишингиз ёки "
            "манзилни матн кўринишида ёзишингиз мумкин.",

            reply_markup=location_keyboard()
        )

        return


    # =================================================
    # MANZIL
    # =================================================

    if step == "address":

        if update.message.location:

            latitude = str(
                update.message.location.latitude
            )

            longitude = str(
                update.message.location.longitude
            )


            data["latitude"] = latitude

            data["longitude"] = longitude

            data["address"] = (
                f"{latitude}, {longitude}"
            )


        elif text == "✍️ Манзилни ёзиш":

            await update.message.reply_text(

                "📍 Манзилингизни ёзинг:\n\n"

                "Масалан:\n"
                "Андижон шаҳар, Бобуршоҳ кўчаси, 25-уй"
            )

            return


        else:

            if len(text.strip()) < 3:

                await update.message.reply_text(

                    "❌ Манзилни тўғри киритинг."
                )

                return


            data["address"] = text.strip()


        save_user(

            uid,

            address=data["address"],

            latitude=data["latitude"],

            longitude=data["longitude"]
        )


        data["step"] = "comment"


        await update.message.reply_text(

            "📝 Буюртма ҳақида қўшимча маълумот ёзинг.\n\n"

            "Масалан:\n"
            "«Шкафни йиғиш керак»\n\n"

            "Агар қўшимча изоҳ бўлмаса:\n"
            "«Йўқ» деб ёзинг.",

            reply_markup=back_menu()
        )

        return


    # =================================================
    # IZOHLAR
    # =================================================

    if step == "comment":

        if text == "⬅️ Орқага":

            data["step"] = "address"

            await update.message.reply_text(

                "📍 Манзилни қайта киритинг:",

                reply_markup=location_keyboard()
            )

            return


        data["comment"] = text.strip()


        # Буюртмани кейинги қисмда
        # диспетчерга юбориш учун тайёрлаймиз.

        await show_order_confirmation(
            update,
            context,
            data
        )

        return


# =====================================================
# BUYURTMA TASDIQLASH
# =====================================================

async def show_order_confirmation(
    update,
    context,
    data
):

    text = (

        "📋 БУЮРТМА МАЪЛУМОТЛАРИ\n\n"

        f"👤 Исм: {data['name']}\n"

        f"📞 Телефон: {data['phone']}\n"

        f"🛠 Хизмат: {data['service']}\n"

        f"📍 Манзил: {data['address']}\n"

        f"📝 Изоҳ: {data['comment']}\n\n"

        "Маълумотлар тўғрими?"
    )


    keyboard = InlineKeyboardMarkup([

        [

            InlineKeyboardButton(

                "✅ Тасдиқлаш",

                callback_data="confirm_order"
            )

        ],

        [

            InlineKeyboardButton(

                "✏️ Қайта киритиш",

                callback_data="edit_order"
            )

        ],

        [

            InlineKeyboardButton(

                "❌ Бекор қилиш",

                callback_data="cancel_order"
            )

        ]

    ])


    await update.message.reply_text(

        text,

        reply_markup=keyboard,

        # Телефон сўраш тугмаси энди
        # керак эмас.
        # Одатий клавиатурага қайтамиз.

        # parse_mode бермаймиз:
        # кирилл белгиларда хато бўлмаслиги учун.
    )


# =====================================================
# BUYURTMA TASDIQLASH CALLBACK
# =====================================================

async def order_confirm_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()


    uid = query.from_user.id


    if query.data == "confirm_order":

        if uid not in user_states:

            await query.edit_message_text(

                "❌ Буюртма маълумотлари топилмади."
            )

            return


        data = user_states[uid]


        # Бу ерда буюртмани базага
        # сақлаш қисми 2-қисмда давом этади.

        await query.edit_message_text(

            "⏳ Буюртмангиз қабул қилинмоқда..."
        )


        # Маълумотни йўқотиб қўймаслик учун
        # вақтинча stateда қолдирамиз.


        return


    # =================================================
    # QAYTA KIRITISH
    # =================================================

    if query.data == "edit_order":

        user_states[uid] = {

            "step": "name",

            "name": "",

            "phone": "",

            "service": "",

            "address": "",

            "latitude": "",

            "longitude": "",

            "comment": ""

        }


        await query.edit_message_text(

            "✏️ Маълумотларни қайта киритамиз.\n\n"
            "👤 Исмингизни ёзинг:"
        )

        return


    # =================================================
    # BEKOR QILISH
    # =================================================

    if query.data == "cancel_order":

        user_states.pop(
            uid,
            None
        )


        await query.edit_message_text(

            "❌ Буюртма бекор қилинди."
        )


        await context.bot.send_message(

            chat_id=uid,

            text="Асосий меню:",

            reply_markup=client_menu()
        )

        return


# =====================================================
# MIJOZ BUYURTMALARI
# =====================================================

async def my_orders(
    update,
    context
):

    uid = update.effective_user.id


    cursor.execute(

        """
        SELECT
            id,
            service,
            address,
            status,
            master_name,
            created_at
        FROM orders
        WHERE customer_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,

        (uid,)
    )


    rows = cursor.fetchall()


    if not rows:

        await update.message.reply_text(

            "📦 Сизда ҳали буюртмалар йўқ.",

            reply_markup=client_menu()
        )

        return


    text = "📦 СИЗНИНГ БУЮРТМАЛАРИНГИЗ\n\n"


    for row in rows:

        oid = row[0]

        service = row[1]

        address = row[2]

        status = STATUS.get(
            row[3],
            row[3]
        )

        master = (
            row[4]
            or "Бириктирилмаган"
        )


        text += (

            f"🔢 №{oid}\n"
            f"🛠 {service}\n"
            f"📍 {address}\n"
            f"📌 {status}\n"
            f"👨‍🔧 Уста: {master}\n"
            "────────────\n"
        )


    await update.message.reply_text(

        text,

        reply_markup=client_menu()
    )


# =====================================================
# 1-QISM TUGADI
#
# MUHIM:
# BU YERDA main() YO'Q.
#
# 2-QISMDA:
# - DISPETCHER
# - USTA
# - USTA QO'SHISH
# - USTA O'CHIRISH
# - ADMIN
# - BUYURTMA YUBORISH
# - QABUL / RAD
# - ISH BOSHLASH
# - YAKUNLASH
# - REYTING
# - STATISTIKA
# - XABAR TARQATISH
# - main()
# QO'SHILADI.
# =====================================================
# =====================================================
# USTA 24 PRO BOT
# MAIN.PY — 2/2
# DISPETCHER + USTA + ADMIN + BUYURTMA
# =====================================================


# =====================================================
# USTA DATABASE
# =====================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS masters (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE,
    name TEXT,
    phone TEXT DEFAULT '',
    username TEXT DEFAULT '',
    services TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    created_at TEXT
)
""")

conn.commit()


# =====================================================
# USTA YORDAMCHI FUNKSIYALAR
# =====================================================

def get_master(telegram_id):

    cursor.execute(
        """
        SELECT
            id,
            telegram_id,
            name,
            phone,
            username,
            services,
            active
        FROM masters
        WHERE telegram_id = ?
        """,
        (telegram_id,)
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "telegram_id": row[1],
        "name": row[2],
        "phone": row[3],
        "username": row[4],
        "services": row[5],
        "active": row[6]
    }


def get_active_masters():

    cursor.execute(
        """
        SELECT
            id,
            telegram_id,
            name,
            phone,
            username,
            services
        FROM masters
        WHERE active = 1
        ORDER BY id
        """
    )

    return cursor.fetchall()


# =====================================================
# DISPETCHER MENYU
# =====================================================

def dispatcher_menu():

    return ReplyKeyboardMarkup(

        [
            ["🆕 Янги буюртмалар"],

            ["📋 Барча буюртмалар"],

            ["👨‍🔧 Усталар"],

            ["🔎 Буюртма қидириш"],

            ["📊 Статистика"],

            ["⬅️ Асосий меню"]
        ],

        resize_keyboard=True
    )


# =====================================================
# ADMIN MENYU
# =====================================================

def admin_menu_full():

    return ReplyKeyboardMarkup(

        [
            ["👨‍🔧 Уста қўшиш", "👨‍🔧 Усталар"],

            ["✏️ Устани ўзгартириш", "🗑 Устани ўчириш"],

            ["👤 Мижозлар базаси"],

            ["📋 Барча буюртмалар"],

            ["🔎 Буюртма қидириш"],

            ["📊 Статистика"],

            ["📢 Хабар тарқатиш"],

            ["🔄 Бот ҳолати"]
        ],

        resize_keyboard=True
    )


# =====================================================
# USTA MENYU
# =====================================================

def master_menu():

    return ReplyKeyboardMarkup(

        [
            ["🆕 Янги буюртмалар"],

            ["📋 Менинг буюртмаларим"],

            ["📊 Менинг статистикам"],

            ["🟢 Ишдаман", "🔴 Бўшман"]
        ],

        resize_keyboard=True
    )


# =====================================================
# ADMIN TEKSHIRUV
# =====================================================

def is_admin(user_id):

    return user_id == ADMIN_ID


# =====================================================
# DISPETCHER TEKSHIRUV
# =====================================================

def is_dispatcher(user_id):

    return (
        user_id == DISPATCHER_ID
        or user_id == ADMIN_ID
    )


# =====================================================
# USTA TEKSHIRUV
# =====================================================

def is_master(user_id):

    return get_master(user_id) is not None


# =====================================================
# BUYURTMA SAQLASH
# =====================================================

def create_order(
    customer_id,
    data
):

    cursor.execute(
        """
        INSERT INTO orders (
            customer_id,
            name,
            phone,
            service,
            address,
            latitude,
            longitude,
            comment,
            status,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,

        (
            customer_id,
            data["name"],
            data["phone"],
            data["service"],
            data["address"],
            data["latitude"],
            data["longitude"],
            data["comment"],
            "new",
            datetime.now().isoformat()
        )
    )

    conn.commit()

    return cursor.lastrowid


# =====================================================
# BUYURTMA MA'LUMOTI
# =====================================================

def get_order(order_id):

    cursor.execute(
        """
        SELECT
            id,
            customer_id,
            name,
            phone,
            service,
            address,
            latitude,
            longitude,
            comment,
            status,
            master_id,
            master_name,
            created_at
        FROM orders
        WHERE id = ?
        """,
        (order_id,)
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "customer_id": row[1],
        "name": row[2],
        "phone": row[3],
        "service": row[4],
        "address": row[5],
        "latitude": row[6],
        "longitude": row[7],
        "comment": row[8],
        "status": row[9],
        "master_id": row[10],
        "master_name": row[11],
        "created_at": row[12]
    }


# =====================================================
# BUYURTMA MATNI
# =====================================================

def order_text(order):

    status = STATUS.get(
        order["status"],
        order["status"]
    )

    master = (
        order["master_name"]
        or "Бириктирилмаган"
    )

    return (

        f"🔢 Буюртма №{order['id']}\n\n"

        f"👤 Мижоз: {order['name']}\n"

        f"📞 Телефон: {order['phone']}\n"

        f"🛠 Хизмат: {order['service']}\n"

        f"📍 Манзил: {order['address']}\n"

        f"📝 Изоҳ: {order['comment']}\n\n"

        f"📌 Ҳолат: {status}\n"

        f"👨‍🔧 Уста: {master}"
    )


# =====================================================
# DISPETCHERGA YANGI BUYURTMA
# =====================================================

async def send_order_to_dispatcher(
    context,
    order
):

    keyboard = InlineKeyboardMarkup(

        [
            [
                InlineKeyboardButton(
                    "🟡 Қабул қилиш",
                    callback_data=f"dispatch_accept_{order['id']}"
                )
            ],

            [
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"dispatch_reject_{order['id']}"
                )
            ],

            [
                InlineKeyboardButton(
                    "📞 Мижозга қўнғироқ",
                    url=f"tel:{order['phone']}"
                )
            ]
        ]
    )


    await context.bot.send_message(

        chat_id=DISPATCHER_ID,

        text=(
            "🆕 ЯНГИ БУЮРТМА\n\n"
            + order_text(order)
            + "\n\n"
            "👨‍💼 Диспетчер, буюртмани кўриб чиқинг."
        ),

        reply_markup=keyboard
    )


# =====================================================
# BUYURTMA TASDIQLASH
# =====================================================

async def confirm_order_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    uid = query.from_user.id


    if query.data == "confirm_order":

        if uid not in user_states:

            await query.edit_message_text(
                "❌ Буюртма маълумотлари топилмади."
            )

            return


        data = user_states[uid]


        order_id = create_order(
            uid,
            data
        )


        order = get_order(order_id)


        user_states.pop(
            uid,
            None
        )


        try:

            await send_order_to_dispatcher(
                context,
                order
            )

        except Exception as e:

            logger.exception(
                "Dispatcherga buyurtma yuborishda xato"
            )

            await query.edit_message_text(

                "❌ Буюртмани диспетчерга юборишда "
                "хатолик юз берди.\n\n"
                "Илтимос, кейинроқ қайта уриниб кўринг."
            )

            return


        await query.edit_message_text(

            f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n\n"

            "👨‍💼 Диспетчер буюртмани кўриб чиқмоқда.\n"

            "Тез орада сиз билан боғланишади.\n\n"

            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )


        await context.bot.send_message(

            chat_id=uid,

            text="Асосий меню:",

            reply_markup=client_menu()
        )

        return


# =====================================================
# DISPETCHER CALLBACK
# =====================================================

async def dispatcher_callback(
    update,
    context
):

    query = update.callback_query

    uid = query.from_user.id


    if not is_dispatcher(uid):

        await query.answer(
            "❌ Сизда бу вазифа учун рухсат йўқ.",
            show_alert=True
        )

        return


    await query.answer()


    data = query.data


    parts = data.split("_")


    if len(parts) < 3:
        return


    action = parts[1]

    try:

        order_id = int(parts[2])

    except:

        return


    order = get_order(order_id)


    if not order:

        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True
        )

        return


    # =================================================
    # DISPETCHER QABUL
    # =================================================

    if action == "accept":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            """,

            (
                "dispatcher",
                order_id
            )
        )

        conn.commit()


        await query.edit_message_text(

            "👨‍💼 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            + order_text(
                get_order(order_id)
            )
            + "\n\n"

            "👨‍🔧 Энди уста танланг."
        )


        await show_master_selection(
            context,
            order_id,
            order["customer_id"]
        )

        return


    # =================================================
    # DISPETCHER RAD
    # =================================================

    if action == "reject":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            """,

            (
                "reject",
                order_id
            )
        )

        conn.commit()


        await query.edit_message_text(

            "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"

            + order_text(
                get_order(order_id)
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🚫 Буюртмангиз №{order_id} "
                "рад этилди.\n\n"

                "Бошқа уста топиш учун "
                "диспетчер билан боғланамиз.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


# =====================================================
# USTANI TANLASH
# =====================================================

async def show_master_selection(
    context,
    order_id,
    customer_id
):

    masters_list = get_active_masters()


    if not masters_list:

        await context.bot.send_message(

            chat_id=DISPATCHER_ID,

            text=(
                f"⚠️ №{order_id} буюртма учун "
                "фаол уста топилмади.\n\n"
                "Аввал 👨‍🔧 Уста қўшинг."
            )
        )

        return


    buttons = []


    for master in masters_list:

        mid = master[0]

        name = master[2]


        buttons.append([

            InlineKeyboardButton(

                f"👨‍🔧 {name}",

                callback_data=(
                    f"assign_{order_id}_{mid}"
                )
            )

        ])


    buttons.append([

        InlineKeyboardButton(

            "❌ Бекор қилиш",

            callback_data=(
                f"assign_cancel_{order_id}"
            )
        )

    ])


    await context.bot.send_message(

        chat_id=DISPATCHER_ID,

        text=(
            f"👨‍🔧 №{order_id} буюртма учун "
            "уста танланг:"
        ),

        reply_markup=InlineKeyboardMarkup(
            buttons
        )
    )


# =====================================================
# USTA BIRIKTIRISH
# =====================================================

async def assign_callback(
    update,
    context
):

    query = update.callback_query

    uid = query.from_user.id


    if not is_dispatcher(uid):

        await query.answer(
            "❌ Рухсат йўқ.",
            show_alert=True
        )

        return


    await query.answer()


    parts = query.data.split("_")


    if len(parts) < 3:
        return


    try:

        order_id = int(parts[1])

    except:

        return


    if parts[2] == "cancel":

        await query.edit_message_text(
            "❌ Уста танлаш бекор қилинди."
        )

        return


    try:

        master_id = int(parts[2])

    except:

        return


    order = get_order(order_id)


    if not order:

        await query.edit_message_text(
            "❌ Буюртма топилмади."
        )

        return


    cursor.execute(

        """
        SELECT
            id,
            telegram_id,
            name,
            phone,
            username,
            services
        FROM masters
        WHERE id = ?
        """,

        (master_id,)
    )


    master = cursor.fetchone()


    if not master:

        await query.edit_message_text(
            "❌ Уста топилмади."
        )

        return


    master_name = master[2]

    master_telegram_id = master[1]

    master_phone = master[3]

    master_username = master[4]


    cursor.execute(

        """
        UPDATE orders

        SET
            status = ?,
            master_id = ?,
            master_name = ?

        WHERE id = ?
        """,

        (
            "assigned",
            master_id,
            master_name,
            order_id
        )
    )

    conn.commit()


    order = get_order(order_id)


    await query.edit_message_text(

        "👨‍🔧 УСТА БИРИКТИРИЛДИ\n\n"

        + order_text(order)
    )


    # =================================================
    # USTAGA YUBORISH
    # =================================================

    master_keyboard = InlineKeyboardMarkup(

        [
            [
                InlineKeyboardButton(
                    "🟡 Қабул қилиш",
                    callback_data=f"master_accept_{order_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"master_reject_{order_id}"
                )
            ]
        ]
    )


    try:

        await context.bot.send_message(

            chat_id=master_telegram_id,

            text=(
                "🆕 СИЗГА ЯНГИ БУЮРТМА БЕРИЛДИ\n\n"
                + order_text(order)
                + "\n\n"
                "Буюртмани қабул қилиш ёки рад этишингиз мумкин."
            ),

            reply_markup=master_keyboard
        )

    except Exception:

        logger.exception(
            "Ustaga buyurtma yuborishda xato"
        )

        await context.bot.send_message(

            chat_id=DISPATCHER_ID,

            text=(
                f"⚠️ №{order_id} буюртмани "
                f"{master_name}га юбориб бўлмади.\n\n"
                "Уста ботни аввал /start қилиши керак."
            )
        )


# =====================================================
# USTA CALLBACK
# =====================================================

async def master_callback(
    update,
    context
):

    query = update.callback_query

    uid = query.from_user.id


    master = get_master(uid)


    if not master:

        await query.answer(

            "❌ Сиз уста сифатида рўйхатдан ўтмагансиз.",

            show_alert=True
        )

        return


    await query.answer()


    parts = query.data.split("_")


    if len(parts) < 3:
        return


    action = parts[1]


    try:

        order_id = int(parts[2])

    except:

        return


    order = get_order(order_id)


    if not order:

        await query.answer(

            "❌ Буюртма топилмади.",

            show_alert=True
        )

        return


    # =================================================
    # USTA QABUL
    # =================================================

    if action == "accept":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            AND master_id = ?
            """,

            (
                "accepted",
                order_id,
                master["id"]
            )
        )

        conn.commit()


        keyboard = InlineKeyboardMarkup(

            [
                [
                    InlineKeyboardButton(
                        "🔵 Ишни бошлаш",
                        callback_data=f"work_start_{order_id}"
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"work_cancel_{order_id}"
                    )
                ]
            ]
        )


        await query.edit_message_text(

            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            + order_text(
                get_order(order_id)
            ),

            reply_markup=keyboard
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🟡 Буюртмангиз №{order_id} қабул қилинди.\n\n"

                f"👨‍🔧 Уста: {master['name']}\n\n"

                "Тез орада уста ишни бошлайди.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # USTA RAD
    # =================================================

    if action == "reject":

        cursor.execute(

            """
            UPDATE orders

            SET
                status = ?,
                master_id = NULL,
                master_name = NULL

            WHERE id = ?
            """,

            (
                "dispatcher",
                order_id
            )
        )

        conn.commit()


        await query.edit_message_text(

            f"🚫 №{order_id} буюртмани қабул қилмадингиз."
        )


        await context.bot.send_message(

            chat_id=DISPATCHER_ID,

            text=(

                f"🚫 Уста {master['name']} "
                f"№{order_id} буюртмани рад этди.\n\n"

                "🔄 Бошқа уста танланг."
            )
        )


        await show_master_selection(

            context,

            order_id,

            order["customer_id"]
        )

        return


# =====================================================
# ISH BOSHLASH
# =====================================================

async def work_callback(
    update,
    context
):

    query = update.callback_query

    uid = query.from_user.id


    master = get_master(uid)


    if not master:

        await query.answer(
            "❌ Рухсат йўқ.",
            show_alert=True
        )

        return


    await query.answer()


    parts = query.data.split("_")


    if len(parts) < 3:
        return


    action = parts[1]


    try:

        order_id = int(parts[2])

    except:

        return


    order = get_order(order_id)


    if not order:

        return


    if order["master_id"] != master["id"]:

        await query.answer(

            "❌ Бу буюртма сизга тегишли эмас.",

            show_alert=True
        )

        return


    # =================================================
    # ISH BOSHLASH
    # =================================================

    if action == "start":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            """,

            (
                "process",
                order_id
            )
        )

        conn.commit()


        keyboard = InlineKeyboardMarkup(

            [
                [
                    InlineKeyboardButton(
                        "✅ Ишни якунлаш",
                        callback_data=f"work_done_{order_id}"
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"work_cancel_{order_id}"
                    )
                ]
            ]
        )


        await query.edit_message_text(

            "🔵 ИШ БОШЛАНДИ\n\n"

            + order_text(
                get_order(order_id)
            ),

            reply_markup=keyboard
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🔵 №{order_id} буюртма бўйича "
                "иш бошланди.\n\n"

                f"👨‍🔧 Уста: {master['name']}"
            )
        )

        return


    # =================================================
    # ISH YAKUNLASH
    # =================================================

    if action == "done":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            """,

            (
                "done",
                order_id
            )
        )

        conn.commit()


        await query.edit_message_text(

            "✅ ИШ ЯКУНЛАНДИ\n\n"

            + order_text(
                get_order(order_id)
            )
        )


        rating_keyboard = InlineKeyboardMarkup(

            [
                [
                    InlineKeyboardButton(
                        "⭐ 1",
                        callback_data=f"rating_{order_id}_1"
                    ),
                    InlineKeyboardButton(
                        "⭐ 2",
                        callback_data=f"rating_{order_id}_2"
                    ),
                    InlineKeyboardButton(
                        "⭐ 3",
                        callback_data=f"rating_{order_id}_3"
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⭐ 4",
                        callback_data=f"rating_{order_id}_4"
                    ),
                    InlineKeyboardButton(
                        "⭐ 5",
                        callback_data=f"rating_{order_id}_5"
                    )
                ]
            ]
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"✅ №{order_id} буюртмангиз якунланди.\n\n"

                "⭐ Уста хизматини баҳоланг:"
            ),

            reply_markup=rating_keyboard
        )

        return


    # =================================================
    # BEKOR QILISH
    # =================================================

    if action == "cancel":

        cursor.execute(

            """
            UPDATE orders
            SET status = ?
            WHERE id = ?
            """,

            (
                "cancel",
                order_id
            )
        )

        conn.commit()


        await query.edit_message_text(

            "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"

            + order_text(
                get_order(order_id)
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"❌ №{order_id} буюртма бекор қилинди.\n\n"
                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )


# =====================================================
# RATING
# =====================================================

cursor.execute("""
CREATE TABLE IF NOT EXISTS ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    customer_id INTEGER,
    master_id INTEGER,
    rating INTEGER,
    created_at TEXT
)
""")

conn.commit()


async def rating_callback(
    update,
    context
):

    query = update.callback_query

    await query.answer()


    parts = query.data.split("_")


    if len(parts) != 3:
        return


    try:

        order_id = int(parts[1])

        rating = int(parts[2])

    except:

        return


    if rating < 1 or rating > 5:

        return


    order = get_order(order_id)


    if not order:

        await query.edit_message_text(
            "❌ Буюртма топилмади."
        )

        return


    if order["customer_id"] != query.from_user.id:

        await query.answer(

            "❌ Бу буюртма сизники эмас.",

            show_alert=True
        )

        return


    cursor.execute(

        """
        SELECT id
        FROM ratings
        WHERE order_id = ?
        """,

        (order_id,)
    )


    if cursor.fetchone():

        await query.edit_message_text(

            "⭐ Сиз бу буюртмага баҳо бергансиз."
        )

        return


    cursor.execute(

        """
        INSERT INTO ratings (
            order_id,
            customer_id,
            master_id,
            rating,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,

        (
            order_id,
            query.from_user.id,
            order["master_id"],
            rating,
            datetime.now().isoformat()
        )
    )

    conn.commit()


    await query.edit_message_text(

        f"⭐ Раҳмат!\n\n"
        f"Сиз {rating}/5 баҳо бердингиз.\n\n"
        "USTA 24 учун фикрингиз муҳим."
    )


    # Админга рейтинг хабарини юбориш

    try:

        await context.bot.send_message(

            chat_id=ADMIN_ID,

            text=(

                "⭐ ЯНГИ БАҲО\n\n"

                f"🔢 Буюртма: №{order_id}\n"

                f"👤 Мижоз: {order['name']}\n"

                f"👨‍🔧 Уста: "
                f"{order['master_name'] or 'номаълум'}\n"

                f"⭐ Баҳо: {rating}/5"
            )
        )

    except Exception:

        logger.exception(
            "Adminga rating yuborishda xato"
        )


# =====================================================
# ADMIN — USTA QO'SHISH
# =====================================================

async def add_master_start(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return


    context.user_data["admin_action"] = (
        "add_master"
    )


    await update.message.reply_text(

        "👨‍🔧 УСТА ҚЎШИШ\n\n"

        "Қуйидаги тартибда юборинг:\n\n"

        "Telegram ID | Исм | Телефон | Username | Хизматлар\n\n"

        "Мисол:\n"

        "123456789 | Али | +998901234567 | "
        "@ali | Мебель, Сантехника"
    )


# =====================================================
# USTA QO'SHISH SAQLASH
# =====================================================

async def add_master_save(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    text = update.message.text.strip()


    parts = [
        x.strip()
        for x in text.split("|")
    ]


    if len(parts) < 3:

        await update.message.reply_text(

            "❌ Формат нотўғри.\n\n"

            "ID | Исм | Телефон | Username | Хизматлар"
        )

        return


    try:

        telegram_id = int(parts[0])

    except:

        await update.message.reply_text(

            "❌ Telegram ID рақам бўлиши керак."
        )

        return


    name = parts[1]

    phone = parts[2]

    username = (
        parts[3]
        if len(parts) >= 4
        else ""
    )

    services = (
        parts[4]
        if len(parts) >= 5
        else ""
    )


    try:

        cursor.execute(

            """
            INSERT INTO masters (
                telegram_id,
                name,
                phone,
                username,
                services,
                active,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,

            (
                telegram_id,
                name,
                phone,
                username,
                services,
                datetime.now().isoformat()
            )
        )

        conn.commit()


    except sqlite3.IntegrityError:

        await update.message.reply_text(

            "❌ Бу Telegram ID билан уста "
            "аллақачон қўшилган."
        )

        return


    context.user_data.pop(
        "admin_action",
        None
    )


    await update.message.reply_text(

        "✅ УСТА ҚЎШИЛДИ\n\n"

        f"👨‍🔧 Исм: {name}\n"

        f"📞 Телефон: {phone}\n"

        f"🆔 Telegram ID: {telegram_id}\n"

        f"🛠 Хизматлар: {services or 'Кўрсатилмаган'}",

        reply_markup=admin_menu_full()
    )


# =====================================================
# USTALAR RO'YXATI
# =====================================================

async def masters_list_admin(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    rows = get_active_masters()


    if not rows:

        await update.message.reply_text(

            "👨‍🔧 Ҳозирча усталар йўқ.",

            reply_markup=admin_menu_full()
        )

        return


    text = "👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"


    for row in rows:

        mid = row[0]

        tid = row[1]

        name = row[2]

        phone = row[3]

        username = row[4]

        services = row[5]


        text += (

            f"🆔 ID: {mid}\n"

            f"👨‍🔧 {name}\n"

            f"📱 Telegram ID: {tid}\n"

            f"📞 {phone}\n"

            f"👤 {username or 'йўқ'}\n"

            f"🛠 {services or 'кўрсатилмаган'}\n"

            "────────────\n"
        )


    await update.message.reply_text(

        text,

        reply_markup=admin_menu_full()
    )


# =====================================================
# USTA O'CHIRISH
# =====================================================

async def delete_master_start(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    context.user_data["admin_action"] = (
        "delete_master"
    )


    await update.message.reply_text(

        "🗑 УСТАНИ ЎЧИРИШ\n\n"

        "Устанинг Telegram ID рақамини юборинг."
    )


async def delete_master_save(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    try:

        telegram_id = int(
            update.message.text.strip()
        )

    except:

        await update.message.reply_text(
            "❌ ID рақам бўлиши керак."
        )

        return


    cursor.execute(

        """
        UPDATE masters
        SET active = 0
        WHERE telegram_id = ?
        """,

        (telegram_id,)
    )

    conn.commit()


    if cursor.rowcount == 0:

        await update.message.reply_text(

            "❌ Бундай уста топилмади."
        )

        return


    context.user_data.pop(
        "admin_action",
        None
    )


    await update.message.reply_text(

        "🗑 Уста ўчирилди.",

        reply_markup=admin_menu_full()
    )


# =====================================================
# ADMIN — MIJOZLAR
# =====================================================

async def customer_base_admin(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    cursor.execute(

        """
        SELECT
            telegram_id,
            name,
            phone,
            address
        FROM users
        ORDER BY id DESC
        LIMIT 100
        """
    )


    rows = cursor.fetchall()


    if not rows:

        await update.message.reply_text(
            "👤 Мижозлар базаси бўш."
        )

        return


    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"


    for row in rows:

        text += (

            f"👤 {row[1] or 'Номаълум'}\n"

            f"📞 {row[2] or 'Номаълум'}\n"

            f"📍 {row[3] or 'Номаълум'}\n"

            f"🆔 {row[0]}\n"

            "────────────\n"
        )


    await update.message.reply_text(
        text
    )


# =====================================================
# ADMIN — BUYURTMALAR
# =====================================================

async def all_orders_admin(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    cursor.execute(

        """
        SELECT id
        FROM orders
        ORDER BY id DESC
        LIMIT 30
        """
    )


    rows = cursor.fetchall()


    if not rows:

        await update.message.reply_text(
            "📋 Буюртмалар йўқ."
        )

        return


    text = "📋 ОХИРГИ БУЮРТМАЛАР\n\n"


    for row in rows:

        order = get_order(
            row[0]
        )


        if order:

            text += (

                f"🔢 №{order['id']}\n"

                f"👤 {order['name']}\n"

                f"🛠 {order['service']}\n"

                f"📌 {STATUS.get(order['status'], order['status'])}\n"

                f"👨‍🔧 {order['master_name'] or 'Йўқ'}\n"

                "────────────\n"
            )


    await update.message.reply_text(
        text
    )


# =====================================================
# BUYURTMA QIDIRISH
# =====================================================

async def search_order_start(
    update,
    context
):

    if not (
        is_admin(update.effective_user.id)
        or is_dispatcher(update.effective_user.id)
    ):

        return


    context.user_data["admin_action"] = (
        "search_order"
    )


    await update.message.reply_text(

        "🔎 Буюртма қидириш\n\n"

        "Буюртма рақамини юборинг."
    )


async def search_order_save(
    update,
    context
):

    if not (
        is_admin(update.effective_user.id)
        or is_dispatcher(update.effective_user.id)
    ):

        return


    try:

        order_id = int(
            update.message.text.strip()
        )

    except:

        await update.message.reply_text(
            "❌ Буюртма рақами нотўғри."
        )

        return


    order = get_order(
        order_id
    )


    context.user_data.pop(
        "admin_action",
        None
    )


    if not order:

        await update.message.reply_text(
            "❌ Буюртма топилмади."
        )

        return


    await update.message.reply_text(
        order_text(order)
    )


# =====================================================
# STATISTIKA
# =====================================================

async def statistics_admin(
    update,
    context
):

    if not (
        is_admin(update.effective_user.id)
        or is_dispatcher(update.effective_user.id)
    ):

        return


    cursor.execute(
        "SELECT COUNT(*) FROM orders"
    )

    total = cursor.fetchone()[0]


    counts = {}


    for status in STATUS.keys():

        cursor.execute(

            """
            SELECT COUNT(*)
            FROM orders
            WHERE status = ?
            """,

            (status,)
        )

        counts[status] = cursor.fetchone()[0]


    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )

    users_count = cursor.fetchone()[0]


    cursor.execute(
        """
        SELECT COUNT(*)
        FROM masters
        WHERE active = 1
        """
    )

    masters_count = cursor.fetchone()[0]


    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"👤 Мижозлар: {users_count}\n"

        f"👨‍🔧 Фаол усталар: {masters_count}\n\n"

        f"📋 Жами буюртма: {total}\n"

        f"🆕 Янги: {counts['new']}\n"

        f"👨‍💼 Диспетчерда: {counts['dispatcher']}\n"

        f"🟡 Қабул қилинган: {counts['accepted']}\n"

        f"👨‍🔧 Уста бириктирилган: {counts['assigned']}\n"

        f"🔵 Ишда: {counts['process']}\n"

        f"✅ Якунланган: {counts['done']}\n"

        f"❌ Бекор: {counts['cancel']}\n"

        f"🚫 Рад этилган: {counts['reject']}"
    )


# =====================================================
# MASTER — BUYURTMALARIM
# =====================================================

async def master_orders(
    update,
    context
):

    master = get_master(
        update.effective_user.id
    )


    if not master:

        return


    cursor.execute(

        """
        SELECT id
        FROM orders
        WHERE master_id = ?
        ORDER BY id DESC
        LIMIT 30
        """,

        (master["id"],)
    )


    rows = cursor.fetchall()


    if not rows:

        await update.message.reply_text(
            "📋 Сизга ҳали буюртма берилмаган."
        )

        return


    text = "📋 МЕНИНГ БУЮРТМАЛАРИМ\n\n"


    for row in rows:

        order = get_order(
            row[0]
        )


        if order:

            text += (

                f"🔢 №{order['id']}\n"

                f"🛠 {order['service']}\n"

                f"👤 {order['name']}\n"

                f"📌 {STATUS.get(order['status'], order['status'])}\n"

                "────────────\n"
            )


    await update.message.reply_text(
        text,
        reply_markup=master_menu()
    )


# =====================================================
# MASTER STATISTIKA
# =====================================================

async def master_statistics(
    update,
    context
):

    master = get_master(
        update.effective_user.id
    )


    if not master:

        return


    cursor.execute(

        """
        SELECT COUNT(*)
        FROM orders
        WHERE master_id = ?
        """,

        (master["id"],)
    )

    total = cursor.fetchone()[0]


    cursor.execute(

        """
        SELECT COUNT(*)
        FROM orders
        WHERE master_id = ?
        AND status = 'done'
        """,

        (master["id"],)
    )

    done = cursor.fetchone()[0]


    cursor.execute(

        """
        SELECT
            AVG(rating)
        FROM ratings
        WHERE master_id = ?
        """,

        (master["id"],)
    )

    avg = cursor.fetchone()[0]


    avg_text = (
        f"{avg:.1f}/5"
        if avg is not None
        else "Ҳали баҳо йўқ"
    )


    await update.message.reply_text(

        "📊 МЕНИНГ СТАТИСТИКАМ\n\n"

        f"📋 Жами буюртма: {total}\n"

        f"✅ Якунланган: {done}\n"

        f"⭐ Ўртача баҳо: {avg_text}"
    )


# =====================================================
# MASTER HOLATI
# =====================================================

async def master_status(
    update,
    context,
    active
):

    master = get_master(
        update.effective_user.id
    )


    if not master:

        return


    cursor.execute(

        """
        UPDATE masters
        SET active = ?
        WHERE telegram_id = ?
        """,

        (
            1 if active else 0,
            update.effective_user.id
        )
    )

    conn.commit()


    if active:

        await update.message.reply_text(

            "🟢 Сиз энди ишдаман ҳолатидасиз.",
            reply_markup=master_menu()
        )

    else:

        await update.message.reply_text(

            "🔴 Сиз ҳозирча бўшман ҳолатидасиз.",
            reply_markup=master_menu()
        )


# =====================================================
# BROADCAST
# =====================================================

async def broadcast_start(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Рухсат йўқ."
        )

        return


    context.user_data["admin_action"] = (
        "broadcast"
    )


    await update.message.reply_text(

        "📢 ХАБАР ТАРҚАТИШ\n\n"

        "Мижозларга юбориладиган хабарни ёзинг."
    )


async def broadcast_save(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        return


    message = update.message.text.strip()


    context.user_data.pop(
        "admin_action",
        None
    )


    cursor.execute(
        "SELECT telegram_id FROM users"
    )

    users_rows = cursor.fetchall()


    count = 0


    for row in users_rows:

        try:

            await context.bot.send_message(

                chat_id=row[0],

                text=message
            )

            count += 1

        except Exception:

            logger.exception(
                "Broadcast error"
            )


    await update.message.reply_text(

        f"📢 Хабар юборилди.\n\n"
        f"👥 {count} та мижозга.",

        reply_markup=admin_menu_full()
    )


# =====================================================
# ADMIN / DISPETCHER / USTA MESSAGE HANDLER
# =====================================================

async def control_handler(
    update,
    context
):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""


    # =================================================
    # ADMIN
    # =================================================

    if is_admin(uid):

        action = context.user_data.get(
            "admin_action"
        )


        if action == "add_master":

            await add_master_save(
                update,
                context
            )

            return


        if action == "delete_master":

            await delete_master_save(
                update,
                context
            )

            return


        if action == "search_order":

            await search_order_save(
                update,
                context
            )

            return


        if action == "broadcast":

            await broadcast_save(
                update,
                context
            )

            return


        if text == "👨‍🔧 Уста қўшиш":

            await add_master_start(
                update,
                context
            )

            return


        if text == "👨‍🔧 Усталар":

            await masters_list_admin(
                update,
                context
            )

            return


        if text == "🗑 Устани ўчириш":

            await delete_master_start(
                update,
                context
            )

            return


        if text == "👤 Мижозлар базаси":

            await customer_base_admin(
                update,
                context
            )

            return


        if text == "📋 Барча буюртмалар":

            await all_orders_admin(
                update,
                context
            )

            return


        if text == "🔎 Буюртма қидириш":

            await search_order_start(
                update,
                context
            )

            return


        if text == "📊 Статистика":

            await statistics_admin(
                update,
                context
            )

            return


        if text == "📢 Хабар тарқатиш":

            await broadcast_start(
                update,
                context
            )

            return


    # =================================================
    # DISPETCHER
    # =================================================

    if is_dispatcher(uid):

        if text == "🆕 Янги буюртмалар":

            await new_dispatcher_orders(
                update,
                context
            )

            return


        if text == "📋 Барча буюртмалар":

            await all_orders_admin(
                update,
                context
            )

            return


        if text == "👨‍🔧 Усталар":

            if is_admin(uid):

                await masters_list_admin(
                    update,
                    context
                )

            else:

                await dispatcher_masters(
                    update,
                    context
                )

            return


        if text == "🔎 Буюртма қидириш":

            await search_order_start(
                update,
                context
            )

            return


        if text == "📊 Статистика":

            await statistics_admin(
                update,
                context
            )

            return


    # =================================================
    # USTA
    # =================================================

    if is_master(uid):

        if text == "🆕 Янги буюртмалар":

            await master_orders(
                update,
                context
            )

            return


        if text == "📋 Менинг буюртмаларим":

            await master_orders(
                update,
                context
            )

            return


        if text == "📊 Менинг статистикам":

            await master_statistics(
                update,
                context
            )

            return


        if text == "🟢 Ишдаман":

            await master_status(
                update,
                context,
                True
            )

            return


        if text == "🔴 Бўшман":

            await master_status(
                update,
                context,
                False
            )

            return


# =====================================================
# DISPETCHER BUYURTMALARI
# =====================================================

async def new_dispatcher_orders(
    update,
    context
):

    if not is_dispatcher(
        update.effective_user.id
    ):

        return


    cursor.execute(

        """
        SELECT id
        FROM orders
        WHERE status IN ('new', 'dispatcher')
        ORDER BY id DESC
        LIMIT 30
        """
    )


    rows = cursor.fetchall()


    if not rows:

        await update.message.reply_text(

            "🆕 Янги буюртмалар йўқ.",

            reply_markup=dispatcher_menu()
        )

        return


    for row in rows:

        order = get_order(
            row[0]
        )


        if not order:
            continue


        keyboard = InlineKeyboardMarkup(

            [
                [
                    InlineKeyboardButton(
                        "🟡 Қабул қилиш",
                        callback_data=f"dispatch_accept_{order['id']}"
                    )
                ],

                [
                    InlineKeyboardButton(
                        "🚫 Рад этиш",
                        callback_data=f"dispatch_reject_{order['id']}"
                    )
                ]
            ]
        )


        await update.message.reply_text(

            order_text(order),

            reply_markup=keyboard
        )


# =====================================================
# DISPETCHER USTALAR
# =====================================================

async def dispatcher_masters(
    update,
    context
):

    if not is_dispatcher(
        update.effective_user.id
    ):

        return


    rows = get_active_masters()


    if not rows:

        await update.message.reply_text(
            "👨‍🔧 Фаол усталар йўқ."
        )

        return


    text = "👨‍🔧 ФАОЛ УСТАЛАР\n\n"


    for row in rows:

        text += (

            f"👨‍🔧 {row[2]}\n"

            f"📞 {row[3]}\n"

            f"👤 {row[4] or 'йўқ'}\n"

            f"🛠 {row[5] or 'кўрсатилмаган'}\n"

            "────────────\n"
        )


    await update.message.reply_text(
        text,
        reply_markup=dispatcher_menu()
    )


# =====================================================
# ADMIN / DISPATCHER COMMANDS
# =====================================================

async def admin_start_full(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return


    await update.message.reply_text(

        "👑 USTA 24 АДМИН\n\n"
        "Бошқарув бўлимини танланг:",

        reply_markup=admin_menu_full()
    )


async def dispatcher_start(
    update,
    context
):

    if not is_dispatcher(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "❌ Сиз диспетчер эмассиз."
        )

        return


    await update.message.reply_text(

        "👨‍💼 USTA 24 ДИСПЕТЧЕР\n\n"
        "Бўлимни танланг:",

        reply_markup=dispatcher_menu()
    )


# =====================================================
# STARTDAN KEYIN TO'G'RI ROL MENYUSI
# =====================================================

async def role_start(
    update,
    context
):

    if not update.message:
        return


    uid = update.effective_user.id


    if is_admin(uid):

        await admin_start_full(
            update,
            context
        )

        return


    if uid == DISPATCHER_ID:

        await dispatcher_start(
            update,
            context
        )

        return


    if is_master(uid):

        await update.message.reply_text(

            "👨‍🔧 USTA 24\n\n"
            "Уста кабинети:",

            reply_markup=master_menu()
        )

        return


    await start(
        update,
        context
    )


# =====================================================
# CALLBACK ROUTER
# =====================================================

async def callback_router(
    update,
    context
):

    query = update.callback_query


    data = query.data or ""


    # Oldingi ma'lumot

    if data in (
        "reuse_info",
        "new_info"
    ):

        if data == "reuse_info":

            await reuse_callback(
                update,
                context
            )

        else:

            await new_info_callback(
                update,
                context
            )

        return


    # Buyurtma tasdiqlash

    if data in (
        "confirm_order",
        "edit_order",
        "cancel_order"
    ):

        await confirm_order_callback(
            update,
            context
        )

        return


    # Dispatcher

    if data.startswith(
        "dispatch_"
    ):

        await dispatcher_callback(
            update,
            context
        )

        return


    # Usta tanlash

    if data.startswith(
        "assign_"
    ):

        await assign_callback(
            update,
            context
        )

        return


    # Usta

    if data.startswith(
        "master_"
    ):

        await master_callback(
            update,
            context
        )

        return


    # Ish

    if data.startswith(
        "work_"
    ):

        await work_callback(
            update,
            context
        )

        return


    # Rating

    if data.startswith(
        "rating_"
    ):

        await rating_callback(
            update,
            context
        )

        return


# =====================================================
# MAIN
# =====================================================

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )


    # /start

    application.add_handler(

        CommandHandler(
            "start",
            role_start
        )
    )


    # /admin

    application.add_handler(

        CommandHandler(
            "admin",
            admin_start_full
        )
    )


    # /dispatcher

    application.add_handler(

        CommandHandler(
            "dispatcher",
            dispatcher_start
        )
    )


    # CALLBACK

    application.add_handler(

        CallbackQueryHandler(
            callback_router
        )
    )


    # TEXT + CONTACT + LOCATION

    application.add_handler(

        MessageHandler(

            filters.CONTACT
            | filters.LOCATION
            | filters.TEXT,

            control_handler
        )
    )


    application.add_handler(

        MessageHandler(

            filters.CONTACT
            | filters.LOCATION
            | filters.TEXT,

            client_handler
        )
    )


    print(
        "USTA 24 PRO BOT ISHLADI"
    )


    application.run_polling()


# =====================================================
# START
# =====================================================

if __name__ == "__main__":

    main()
