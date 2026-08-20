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
# ===================================================== # =====================================================
# USTA 24 PRO BOT
# MAIN.PY 2-QISM
# USTALAR BOSHQARUVI
# =====================================================

# Бу қисм 1-қисмдаги:
# ADMIN_ID
# masters
# orders
# users
# ContextTypes
# ReplyKeyboardMarkup
# KeyboardButton
# InlineKeyboardButton
# InlineKeyboardMarkup
# лардан фойдаланади.


# =====================================================
# ADMIN MENU
# =====================================================

def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["👤 Мижозлар"],
            ["👨‍🔧 Усталар"],
            ["➕ Уста қўшиш"],
            ["🗑 Устани ўчириш"],
            ["📊 Статистика"],
            ["📢 Хабар тарқатиш"],
            ["⬅️ Бош меню"]
        ],
        resize_keyboard=True
    )


# =====================================================
# USTALAR MENU
# =====================================================

def masters_menu():

    return ReplyKeyboardMarkup(
        [
            ["➕ Уста қўшиш"],
            ["👨‍🔧 Усталар рўйхати"],
            ["🗑 Устани ўчириш"],
            ["⬅️ Админ меню"]
        ],
        resize_keyboard=True
    )


# =====================================================
# USTA QO'SHISH BOSHLASH
# =====================================================

async def add_master_start(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["master_add"] = {
        "step": "id",
        "id": None,
        "name": "",
        "phone": "",
        "username": "",
        "services": ""
    }

    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "1️⃣ Устанинг Telegram ID рақамини юборинг.\n\n"
        "Масалан:\n"
        "540523038"
    )


# =====================================================
# USTA QO'SHISH JARAYONI
# =====================================================

async def add_master_handler(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if "master_add" not in context.user_data:
        return

    data = context.user_data["master_add"]

    text = (update.message.text or "").strip()

    # -------------------------------------------------
    # 1. ID
    # -------------------------------------------------

    if data["step"] == "id":

        try:
            master_id = int(text)
        except ValueError:

            await update.message.reply_text(
                "❌ Telegram ID фақат рақам бўлиши керак.\n\n"
                "Масалан:\n"
                "540523038"
            )

            return

        if master_id in masters:

            await update.message.reply_text(
                "⚠️ Бу ID билан уста аллақачон қўшилган."
            )

            context.user_data.pop("master_add", None)

            return

        data["id"] = master_id
        data["step"] = "name"

        await update.message.reply_text(
            "2️⃣ Устанинг исмини ёзинг:"
        )

        return

    # -------------------------------------------------
    # 2. ISM
    # -------------------------------------------------

    if data["step"] == "name":

        if len(text) < 2:

            await update.message.reply_text(
                "❌ Исмни тўғри киритинг."
            )

            return

        data["name"] = text
        data["step"] = "phone"

        await update.message.reply_text(
            "3️⃣ Устанинг телефон рақамини юборинг.\n\n"
            "Масалан:\n"
            "+998901234567"
        )

        return

    # -------------------------------------------------
    # 3. TELEFON
    # -------------------------------------------------

    if data["step"] == "phone":

        data["phone"] = text
        data["step"] = "username"

        await update.message.reply_text(
            "4️⃣ Устанинг Telegram username'ини ёзинг.\n\n"
            "Масалан:\n"
            "@ali_usta\n\n"
            "Агар username бўлмаса:\n"
            "йўқ"
        )

        return

    # -------------------------------------------------
    # 4. USERNAME
    # -------------------------------------------------

    if data["step"] == "username":

        if text.lower() == "йўқ":

            data["username"] = ""

        else:

            if not text.startswith("@"):
                text = "@" + text

            data["username"] = text

        data["step"] = "services"

        await update.message.reply_text(
            "5️⃣ Уста қайси хизматларни бажаради?\n\n"
            "Масалан:\n"
            "Мебель, Сантехника, Электр, Кондиционер\n\n"
            "Хизматларни вергул билан ажратиб ёзинг."
        )

        return

    # -------------------------------------------------
    # 5. XIZMATLAR
    # -------------------------------------------------

    if data["step"] == "services":

        if len(text) < 2:

            await update.message.reply_text(
                "❌ Камида битта хизмат киритинг."
            )

            return

        data["services"] = text

        master_id = data["id"]

        masters[master_id] = {

            "id": master_id,

            "name": data["name"],

            "phone": data["phone"],

            "username": data["username"],

            "services": data["services"],

            "orders": 0,

            "active": True

        }

        master = masters[master_id]

        context.user_data.pop("master_add", None)

        await update.message.reply_text(

            "✅ УСТА МУВАФФАҚИЯТЛИ ҚЎШИЛДИ!\n\n"

            f"🆔 ID: {master['id']}\n"
            f"👨‍🔧 Исм: {master['name']}\n"
            f"📞 Телефон: {master['phone']}\n"
            f"📱 Username: "
            f"{master['username'] or 'йўқ'}\n"
            f"🛠 Хизматлар: {master['services']}\n"
            f"📋 Буюртмалар: {master['orders']}\n\n"

            "✅ Уста базага сақланди.",

            reply_markup=masters_menu()
        )

        return


# =====================================================
# USTALAR RO'YXATI
# =====================================================

async def masters_list(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"
            "Ҳозирча уста қўшилмаган.",
            reply_markup=masters_menu()
        )

        return

    text = "👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"

    for number, master in enumerate(
        masters.values(),
        start=1
    ):

        text += (
            f"{number}️⃣ "
            f"{master['name']}\n"
            f"🆔 ID: {master['id']}\n"
            f"📞 {master['phone']}\n"
            f"📱 {master.get('username') or 'йўқ'}\n"
            f"🛠 {master.get('services') or 'кўрсатилмаган'}\n"
            f"📋 Буюртмалар: "
            f"{master.get('orders', 0)}\n"
            "──────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=masters_menu()
    )


# =====================================================
# USTA O'CHIRISH BOSHLASH
# =====================================================

async def delete_master_start(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if not masters:

        await update.message.reply_text(
            "❌ Ўчириш учун уста йўқ."
        )

        return

    text = (
        "🗑 УСТАНИ ЎЧИРИШ\n\n"
        "Ўчирмоқчи бўлган устанинг ID рақамини юборинг.\n\n"
    )

    for master in masters.values():

        text += (
            f"👨‍🔧 {master['name']}\n"
            f"🆔 {master['id']}\n\n"
        )

    await update.message.reply_text(text)

    context.user_data["delete_master"] = True


# =====================================================
# USTA O'CHIRISH
# =====================================================

async def delete_master_handler(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.user_data.get("delete_master"):
        return

    text = (update.message.text or "").strip()

    try:

        master_id = int(text)

    except ValueError:

        await update.message.reply_text(
            "❌ ID фақат рақам бўлиши керак."
        )

        return

    if master_id not in masters:

        await update.message.reply_text(
            "❌ Бундай ID билан уста топилмади."
        )

        return

    master = masters[master_id]

    del masters[master_id]

    context.user_data.pop("delete_master", None)

    await update.message.reply_text(

        "✅ Уста ўчирилди.\n\n"

        f"👨‍🔧 {master['name']}\n"
        f"🆔 {master_id}",

        reply_markup=masters_menu()
    )


# =====================================================
# USTA MA'LUMOTI
# =====================================================

async def master_info(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    text = (update.message.text or "").strip()

    try:

        master_id = int(text)

    except ValueError:

        return

    if master_id not in masters:

        return

    master = masters[master_id]

    await update.message.reply_text(

        "👨‍🔧 УСТА МАЪЛУМОТЛАРИ\n\n"

        f"🆔 ID: {master['id']}\n"
        f"👤 Исм: {master['name']}\n"
        f"📞 Телефон: {master['phone']}\n"
        f"📱 Username: "
        f"{master.get('username') or 'йўқ'}\n"
        f"🛠 Хизматлар: "
        f"{master.get('services') or 'йўқ'}\n"
        f"📋 Буюртмалар: "
        f"{master.get('orders', 0)}\n"
    )


# =====================================================
# USTA BUYURTMALAR SONINI OSHIRISH
# =====================================================

def increase_master_orders(master_id):

    if master_id not in masters:
        return

    masters[master_id]["orders"] = (
        masters[master_id].get("orders", 0) + 1
    )


# =====================================================
# USTA TOPISH
# =====================================================

def find_master(master_id):

    return masters.get(master_id)


# =====================================================
# XIZMAT BO'YICHA USTA TOPISH
# =====================================================

def find_masters_by_service(service):

    result = []

    service_lower = service.lower()

    for master in masters.values():

        services = master.get(
            "services",
            ""
        ).lower()

        if service_lower in services:

            result.append(master)

    return result


# =====================================================
# ADMIN BUTTON HANDLER
# =====================================================

async def admin_master_buttons(update, context):

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text or ""

    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
            reply_markup=masters_menu()
        )

        return True

    if text == "➕ Уста қўшиш":

        await add_master_start(
            update,
            context
        )

        return True

    if text == "👨‍🔧 Усталар рўйхати":

        await masters_list(
            update,
            context
        )

        return True

    if text == "🗑 Устани ўчириш":

        await delete_master_start(
            update,
            context
        )

        return True

    if text == "⬅️ Админ меню":

        await update.message.reply_text(
            "👑 АДМИН МЕНЮ",
            reply_markup=admin_menu()
        )

        return True

    return False


# =====================================================
# USTA ADD / DELETE STATE HANDLER
# =====================================================

async def master_state_handler(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("master_add"):

        await add_master_handler(
            update,
            context
        )

        return

    if context.user_data.get("delete_master"):

        await delete_master_handler(
            update,
            context
        )

        return# =====================================================
# USTA 24 PRO BOT
# MAIN.PY 3-QISM
# BUYURTMALAR + DISPETCHER + USTA BOSHQARUVI
# =====================================================


# =====================================================
# BUYURTMA HOLATINI O'ZGARTIRISH
# =====================================================

async def order_action(update, context):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    try:
        action, oid = data.split("_", 1)
        oid = int(oid)
    except:
        return

    if oid not in orders:

        await query.answer(
            "❌ Буюртма топилмади",
            show_alert=True
        )

        return

    order = orders[oid]


    # =================================================
    # QABUL QILISH
    # =================================================

    if action == "accept":

        user = query.from_user

        master_name = user.first_name or "Уста"

        if user.username:
            master_name = f"@{user.username}"

        order["status"] = "accepted"
        order["master_id"] = user.id
        order["master"] = master_name

        if user.id in masters:
            increase_master_orders(user.id)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔵 Ишни бошлаш",
                    callback_data=f"start_{oid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"cancel_{oid}"
                )
            ]
        ])

        await query.edit_message_text(

            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            f"🔢 Буюртма: №{oid}\n"
            f"👨‍🔧 Уста: {master_name}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"📞 Телефон: {order['phone']}\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n\n"

            "Ишни бошлаш учун тугмани босинг.",

            reply_markup=keyboard
        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"

                f"👨‍🔧 Уста: {master_name}\n"
                f"📞 Уста билан боғланиш мумкин.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"

            )
        )

        return


    # =================================================
    # RAD ETISH
    # =================================================

    if action == "reject":

        order["status"] = "reject"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔁 Бошқа устага бериш",
                    callback_data=f"redispatch_{oid}"
                )
            ]
        ])

        await query.edit_message_text(

            "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"

            f"🔢 Буюртма: №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"🛠 Хизмат: {order['service']}\n\n"

            "Бошқа устага бериш мумкин.",

            reply_markup=keyboard
        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🚫 №{oid} буюртмани танланган уста қабул қилмади.\n\n"

                "🔁 Бошқа уста қидирилмоқда.\n"
                "Илтимос, бироз кутинг."

            )
        )

        return


    # =================================================
    # ISHNI BOSHLASH
    # =================================================

    if action == "start":

        order["status"] = "process"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Ишни якунлаш",
                    callback_data=f"done_{oid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Буюртмани бекор қилиш",
                    callback_data=f"cancel_{oid}"
                )
            ]
        ])

        await query.edit_message_text(

            "🔵 ИШ ЖАРАЁНИДА\n\n"

            f"🔢 Буюртма: №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"📞 Телефон: {order['phone']}\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n\n"

            "Иш якунланганда тугмани босинг.",

            reply_markup=keyboard
        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"

                f"👨‍🔧 Уста: "
                f"{order.get('master', 'Уста')}\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"

            )
        )

        return


    # =================================================
    # YAKUNLASH
    # =================================================

    if action == "done":

        order["status"] = "done"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⭐ Баҳо бериш",
                    callback_data=f"review_{oid}"
                )
            ]
        ])

        await query.edit_message_text(

            "✅ БУЮРТМА ЯКУНЛАНДИ\n\n"

            f"🔢 Буюртма: №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"👨‍🔧 Уста: "
            f"{order.get('master', 'Уста')}\n\n"

            "Буюртма муваффақиятли якунланди.",

            reply_markup=keyboard
        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"✅ №{oid} буюртмангиз якунланди.\n\n"

                "⭐ Устага баҳо беришингиз мумкин.\n\n"

                "Раҳмат! USTA 24"

            ),

            reply_markup=keyboard
        )

        return


    # =================================================
    # BEKOR QILISH
    # =================================================

    if action == "cancel":

        order["status"] = "cancel"

        await query.edit_message_text(

            "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"

            f"🔢 №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"👨‍🔧 Уста: "
            f"{order.get('master', 'Уста')}"

        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"❌ №{oid} буюртмангиз бекор қилинди.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"

            )
        )

        return


    # =================================================
    # BOSHQA USTAGA BERISH
    # =================================================

    if action == "redispatch":

        order["status"] = "new"
        order["master"] = None
        order["master_id"] = None

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🟡 Қабул қилиш",
                    callback_data=f"accept_{oid}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"reject_{oid}"
                )
            ]
        ])

        text = (

            "🔁 БОШҚА УСТАГА БЕРИЛДИ\n\n"

            f"🔢 Буюртма: №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"📞 Телефон: {order['phone']}\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n"
            f"📝 Изоҳ: {order['comment']}\n\n"

            "👨‍🔧 Бошқа уста қабул қилиши мумкин."

        )

        await context.bot.send_message(

            chat_id=MASTERS_GROUP_ID,

            text=text,

            reply_markup=keyboard
        )

        await query.edit_message_text(

            f"🔁 №{oid} буюртма бошқа устага берилди."
        )

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🔁 №{oid} буюртмангиз бошқа устага берилмоқда.\n\n"
                "Илтимос, бироз кутинг."

            )
        )

        return


    # =================================================
    # REVIEW
    # =================================================

    if action == "review":

        await query.answer()

        keyboard = InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "⭐",
                    callback_data=f"rate_1_{oid}"
                ),
                InlineKeyboardButton(
                    "⭐⭐",
                    callback_data=f"rate_2_{oid}"
                ),
                InlineKeyboardButton(
                    "⭐⭐⭐",
                    callback_data=f"rate_3_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "⭐⭐⭐⭐",
                    callback_data=f"rate_4_{oid}"
                ),
                InlineKeyboardButton(
                    "⭐⭐⭐⭐⭐",
                    callback_data=f"rate_5_{oid}"
                )
            ]

        ])

        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"⭐ №{oid} буюртма учун устага баҳо беринг:"
            ),

            reply_markup=keyboard
        )

        return


    # =================================================
    # RATING
    # =================================================

    if action == "rate":

        parts = data.split("_")

        if len(parts) != 3:
            return

        rating = int(parts[1])

        oid = int(parts[2])

        if oid not in orders:
            return

        order = orders[oid]

        customer_id = query.from_user.id

        if customer_id != order["customer_id"]:

            await query.answer(
                "❌ Бу буюртма сизники эмас.",
                show_alert=True
            )

            return

        order["rating"] = rating

        if oid not in reviews:
            reviews[oid] = []

        reviews[oid].append({
            "customer_id": customer_id,
            "rating": rating,
            "master_id": order.get("master_id")
        })

        await query.edit_message_text(

            f"⭐ РАҲМАТ!\n\n"
            f"№{oid} буюртмага "
            f"{rating} балл бердингиз.\n\n"
            "USTA 24 хизматидан фойдаланганингиз учун раҳмат!"
        )

        return


# =====================================================
# DISPETCHER UCHUN BUYURTMA
# =====================================================

async def send_order_to_dispatcher(
    update,
    context,
    oid
):

    if oid not in orders:
        return

    order = orders[oid]

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "👨‍🔧 Устага бериш",
                callback_data=f"assign_{oid}"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Бекор қилиш",
                callback_data=f"cancel_{oid}"
            )
        ]

    ])

    text = (

        "📢 ДИСПЕТЧЕРГА ЯНГИ БУЮРТМА\n\n"

        f"🔢 Буюртма: №{oid}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"📝 Изоҳ: {order['comment']}\n\n"

        "📌 Ҳолат: 🆕 Янги"

    )

    await context.bot.send_message(

        chat_id=ADMIN_ID,

        text=text,

        reply_markup=keyboard
    )


# =====================================================
# USTANI TANLASH
# =====================================================

async def assign_master(update, context):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    if not data.startswith("assign_"):
        return

    try:
        oid = int(data.split("_")[1])
    except:
        return

    if oid not in orders:
        return

    if not masters:

        await query.answer(
            "❌ Ҳали уста қўшилмаган.",
            show_alert=True
        )

        return

    buttons = []

    for master in masters.values():

        if not master.get("active", True):
            continue

        buttons.append([

            InlineKeyboardButton(

                f"👨‍🔧 {master['name']}",

                callback_data=(
                    f"master_{master['id']}_{oid}"
                )
            )

        ])

    buttons.append([

        InlineKeyboardButton(
            "❌ Бекор қилиш",
            callback_data=f"cancel_{oid}"
        )

    ])

    await query.edit_message_text(

        f"👨‍🔧 №{oid} БУЮРТМА УЧУН УСТА ТАНЛАНГ:",

        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =====================================================
# TANLANGAN USTAGA BUYURTMA
# =====================================================

async def assign_master_confirm(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    parts = data.split("_")

    if len(parts) != 3:
        return

    try:

        master_id = int(parts[1])
        oid = int(parts[2])

    except:

        return

    if oid not in orders:
        return

    if master_id not in masters:

        await query.answer(
            "❌ Уста топилмади.",
            show_alert=True
        )

        return

    order = orders[oid]

    master = masters[master_id]

    order["assigned_master_id"] = master_id

    order["status"] = "assigned"

    order["master"] = (
        master.get("username")
        or master["name"]
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🟡 Қабул қилиш",
                callback_data=f"accept_{oid}"
            )
        ],

        [
            InlineKeyboardButton(
                "🚫 Рад этиш",
                callback_data=f"reject_{oid}"
            )
        ]

    ])

    master_text = (

        "🔔 СИЗГА ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{oid}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"📝 Изоҳ: {order['comment']}\n\n"

        "Буюртмани қабул қилиш ёки рад этиш мумкин."

    )

    # Устанинг шахсий Telegram аккаунтига юбориш
    try:

        await context.bot.send_message(

            chat_id=master_id,

            text=master_text,

            reply_markup=keyboard
        )

    except Exception as e:

        logger.error(
            f"Ustaga xabar yuborilmadi: {e}"
        )

        await query.answer(

            "⚠️ Устага хабар юборилмади. "
            "Уста ботни аввал /start қилиши керак.",

            show_alert=True
        )

        return

    await query.edit_message_text(

        "✅ БУЮРТМА УСТАГА БЕРИЛДИ\n\n"

        f"🔢 №{oid}\n"
        f"👨‍🔧 Уста: {master['name']}\n\n"

        "Устанинг жавоби кутилмоқда."
    )

    await context.bot.send_message(

        chat_id=order["customer_id"],

        text=(

            f"👨‍🔧 №{oid} буюртмангиз "
            "устага бириктирилди.\n\n"

            f"Уста: {master['name']}\n\n"

            "Тез орада буюртмани қабул қилиш "
            "ҳақида хабар берамиз."

        )
    )


# =====================================================
# DISPETCHER CALLBACK
# =====================================================

async def dispatcher_callback(update, context):

    query = update.callback_query

    data = query.data or ""

    if data.startswith("assign_"):

        if query.from_user.id != ADMIN_ID:
            await query.answer(
                "❌ Фақат диспетчер.",
                show_alert=True
            )
            return

        await assign_master(
            update,
            context
        )

        return

    if data.startswith("master_"):

        if query.from_user.id != ADMIN_ID:
            await query.answer(
                "❌ Фақат диспетчер.",
                show_alert=True
            )
            return

        await assign_master_confirm(
            update,
            context
        )

        return

    if data.startswith("accept_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("reject_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("start_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("done_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("cancel_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("redispatch_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("review_"):

        await order_action(
            update,
            context
        )

        return

    if data.startswith("rate_"):

        await order_action(
            update,
            context
        )

        return # =====================================================
# USTA 24 PRO BOT
# MAIN.PY 4-QISM
# HANDLERS + ADMIN + START
# =====================================================


# =====================================================
# /SEND — XABAR TARQATISH
# =====================================================

async def send_command(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )
        return

    if not context.args:

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return

    msg = " ".join(context.args)

    # orders ичидаги уникал мижозлар
    customer_ids = set()

    for order in orders.values():

        if order.get("customer_id"):
            customer_ids.add(
                order["customer_id"]
            )

    count = 0

    for customer_id in customer_ids:

        try:

            await context.bot.send_message(
                chat_id=customer_id,
                text=msg
            )

            count += 1

        except Exception as e:

            logger.error(
                f"Xabar yuborilmadi {customer_id}: {e}"
            )

    await update.message.reply_text(

        "📢 ХАБАР ЮБОРИЛДИ\n\n"
        f"👥 {count} та мижозга юборилди."

    )


# =====================================================
# ADMIN BUTTONLARI
# =====================================================

async def admin_button_handler(
    update,
    context
):

    if not update.message:
        return False

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text or ""

    # -------------------------------------------------
    # MIJOZLAR
    # -------------------------------------------------

    if text == "👤 Мижозлар":

        await customer_base(
            update,
            context
        )

        return True


    # -------------------------------------------------
    # USTALAR
    # -------------------------------------------------

    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
            reply_markup=masters_menu()
        )

        return True


    # -------------------------------------------------
    # USTA QO'SHISH
    # -------------------------------------------------

    if text == "➕ Уста қўшиш":

        await add_master_start(
            update,
            context
        )

        return True


    # -------------------------------------------------
    # USTALAR RO'YXATI
    # -------------------------------------------------

    if text == "👨‍🔧 Усталар рўйхати":

        await masters_list(
            update,
            context
        )

        return True


    # -------------------------------------------------
    # USTA O'CHIRISH
    # -------------------------------------------------

    if text == "🗑 Устани ўчириш":

        await delete_master_start(
            update,
            context
        )

        return True


    # -------------------------------------------------
    # STATISTIKA
    # -------------------------------------------------

    if text == "📊 Статистика":

        await statistics(
            update,
            context
        )

        return True


    # -------------------------------------------------
    # XABAR
    # -------------------------------------------------

    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(

            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"

        )

        return True


    # -------------------------------------------------
    # ADMIN MENUGA QAYTISH
    # -------------------------------------------------

    if text == "⬅️ Админ меню":

        await update.message.reply_text(

            "👑 USTA 24 АДМИН\n\n"
            "Бўлимни танланг:",

            reply_markup=admin_menu()
        )

        return True


    # -------------------------------------------------
    # BOSH MENU
    # -------------------------------------------------

    if text == "⬅️ Бош меню":

        await update.message.reply_text(

            "🏠 USTA 24\n\n"
            "Асосий меню:",

            reply_markup=client_menu()
        )

        return True


    return False


# =====================================================
# USTA / ADMIN / CLIENT TEXT HANDLER
# =====================================================

async def all_text_handler(
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

    if uid == ADMIN_ID:

        # Уста қўшиш жараёни
        if context.user_data.get(
            "master_add"
        ):

            await add_master_handler(
                update,
                context
            )

            return


        # Уста ўчириш жараёни
        if context.user_data.get(
            "delete_master"
        ):

            await delete_master_handler(
                update,
                context
            )

            return


        # Admin tugmalari
        handled = await admin_button_handler(
            update,
            context
        )

        if handled:
            return


    # =================================================
    # CLIENT BUYURTMA
    # =================================================

    await client_handler(
        update,
        context
    )


# =====================================================
# CONTACT / LOCATION
# =====================================================

async def contact_location_handler(
    update,
    context
):

    if not update.message:
        return

    # Фақат мижоз буюртма жараёнига бериш
    await client_handler(
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

    if not query:
        return

    data = query.data or ""


    # -------------------------------------------------
    # DISPETCHER
    # -------------------------------------------------

    if data.startswith("assign_"):

        await dispatcher_callback(
            update,
            context
        )

        return


    if data.startswith("master_"):

        await dispatcher_callback(
            update,
            context
        )

        return


    # -------------------------------------------------
    # BUYURTMA
    # -------------------------------------------------

    if data.startswith("accept_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("reject_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("start_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("done_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("cancel_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("redispatch_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    # -------------------------------------------------
    # REVIEW
    # -------------------------------------------------

    if data.startswith("review_"):
        await dispatcher_callback(
            update,
            context
        )
        return


    if data.startswith("rate_"):
        await dispatcher_callback(
            update,
            context
        )
        return


# =====================================================
# ERROR HANDLER
# =====================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "Bot error:",
        exc_info=context.error
    )


# =====================================================
# MAIN
# =====================================================

def main():

    application = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )


    # =================================================
    # /START
    # =================================================

    application.add_handler(

        CommandHandler(
            "start",
            start
        )

    )


    # =================================================
    # /ADMIN
    # =================================================

    application.add_handler(

        CommandHandler(
            "admin",
            admin_start
        )

    )


    # =================================================
    # /SEND
    # =================================================

    application.add_handler(

        CommandHandler(
            "send",
            send_command
        )

    )


    # =================================================
    # CALLBACK
    # =================================================

    application.add_handler(

        CallbackQueryHandler(
            callback_router
        )

    )


    # =================================================
    # CONTACT
    # =================================================

    application.add_handler(

        MessageHandler(

            filters.CONTACT,
            contact_location_handler

        )

    )


    # =================================================
    # LOCATION
    # =================================================

    application.add_handler(

        MessageHandler(

            filters.LOCATION,
            contact_location_handler

        )

    )


    # =================================================
    # TEXT
    # =================================================

    application.add_handler(

        MessageHandler(

            filters.TEXT
            & ~filters.COMMAND,

            all_text_handler

        )

    )


    # =================================================
    # ERROR
    # =================================================

    application.add_error_handler(
        error_handler
    )


    # =================================================
    # FLASK / RENDER
    # =================================================

    Thread(

        target=run_flask,
        daemon=True

    ).start()


    # =================================================
    # START BOT
    # =================================================

    print(
        "===================================="
    )

    print(
        "USTA 24 BOT ISHLADI"
    )

    print(
        "===================================="
    )


    application.run_polling(
        drop_pending_updates=True
    )


# =====================================================
# START
# =====================================================

if __name__ == "__main__":

    main()
