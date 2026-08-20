# =====================================================
# USTA 24 PRO BOT
# MAIN.PY — 1/2
# MIJOZ + DISPETCHER ASOSI
# =====================================================

import os
import logging
from datetime import datetime
from threading import Thread

from flask import Flask

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
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


# =====================================================
# LOG
# =====================================================

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("USTA24")


# =====================================================
# RENDER
# =====================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI"


@app.route("/health")
def health():
    return "OK"


def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "10000"))
    )


# =====================================================
# DATABASE
# =====================================================

users = {}

orders = {}

masters = {}

reviews = {}

order_id = 0


# =====================================================
# BUYURTMA BOSQICHLARI
# =====================================================

ORDER_STEPS = {
    "name": "name",
    "phone": "phone",
    "service": "service",
    "address": "address",
    "comment": "comment",
}


# =====================================================
# STATUS
# =====================================================

STATUS = {

    "new": "🆕 Янги",

    "accepted": "🟡 Қабул қилинган",

    "assigned": "👨‍🔧 Устага бириктирилган",

    "process": "🔵 Иш жараёнида",

    "done": "✅ Якунланган",

    "cancel": "❌ Бекор қилинган",

    "reject": "🚫 Рад этилган",
}


# =====================================================
# XIZMATLAR
# =====================================================

SERVICES = [

    "🪑 Мебель йиғиш",

    "🛠 Мебель таъмирлаш",

    "🍽 Ошхона мебели",

    "🚪 Шкаф купе",

    "🛏 Каравот йиғиш",

    "🪑 Стол-стул",

    "📦 Мебель кўчириш",

    "🚚 Уй кўчириш",

    "🚛 Юк ташиш",

    "🔩 Сантехника",

    "⚡ Электр ишлари",

    "🔥 Иситиш тизими",

    "🎨 Бўёқ ишлари",

    "🪟 Эшик-дераза",

    "❄️ Кондиционер",

    "📡 Интернет",

    "🧹 Тозалаш",

    "🔨 Пайвандлаш",

    "🏠 Уста чақириш",

    "🔧 Бошқа хизмат",
]


# =====================================================
# MIJOZ MENYU
# =====================================================

def client_menu():

    return ReplyKeyboardMarkup(

        [

            ["📝 Буюртма бериш"],

            ["📋 Хизматлар"],

            ["🔁 Қайта буюртма"],

        ],

        resize_keyboard=True,
    )


# =====================================================
# DISPETCHER MENYU
# =====================================================

def dispatcher_menu():

    return ReplyKeyboardMarkup(

        [

            ["🆕 Янги буюртмалар"],

            ["📋 Барча буюртмалар"],

            ["👨‍🔧 Усталар"],

            ["📊 Статистика"],

        ],

        resize_keyboard=True,
    )


# =====================================================
# ADMIN MENYU
# =====================================================

def admin_menu():

    return ReplyKeyboardMarkup(

        [

            ["👤 Мижоз базаси"],

            ["👨‍🔧 Усталар"],

            ["📊 Тўлиқ статистика"],

            ["📢 Хабар тарқатиш"],

            ["📈 Ҳисобот"],

        ],

        resize_keyboard=True,
    )


# =====================================================
# XIZMAT MENYU
# =====================================================

def service_menu():

    return ReplyKeyboardMarkup(

        [

            [service]

            for service in SERVICES

        ],

        resize_keyboard=True,
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

    user = update.effective_user

    if user.id == ADMIN_ID:

        await update.message.reply_text(

            "👑 USTA 24 АДМИН\n\n"
            "Админ бошқарув панели очилди.",

            reply_markup=admin_menu(),
        )

        return


    if user.id == DISPATCHER_ID:

        await update.message.reply_text(

            "👨‍💼 USTA 24 ДИСПЕТЧЕР\n\n"
            "Диспетчер панели очилди.",

            reply_markup=dispatcher_menu(),
        )

        return


    await update.message.reply_text(

        f"👋 Ассалому алайкум, "
        f"{user.first_name}!\n\n"

        "🏠 USTA 24\n\n"

        "Уй ва мебель хизматлари.\n"
        "Буюртма бериш учун тугмани босинг.",

        reply_markup=client_menu(),
    )


# =====================================================
# BUYURTMA BOSHLASH
# =====================================================

async def new_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    uid = update.effective_user.id

    users[uid] = {

        "step": "name",

        "name": "",

        "phone": "",

        "service": "",

        "address": "",

        "comment": "",

    }


    await update.message.reply_text(

        "📝 БУЮРТМА БЕРИШ\n\n"

        "👤 Исмингизни ёзинг:",

    )


# =====================================================
# MIJOZ BUYURTMA QABUL QILISH
# =====================================================

async def client_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""


    # BUYURTMA BOSHLASH

    if text == "📝 Буюртма бериш":

        await new_order(
            update,
            context
        )

        return


    if uid not in users:
        return


    data = users[uid]

    step = data.get("step")


    # =================================================
    # ISM
    # =================================================

    if step == "name":

        if not text.strip():

            await update.message.reply_text(
                "❌ Илтимос, исмингизни ёзинг."
            )

            return


        data["name"] = text.strip()

        data["step"] = "phone"


        phone_button = KeyboardButton(

            "📞 Телефон рақамимни юбориш",

            request_contact=True,
        )


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [[phone_button]],

                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

        return


    # =================================================
    # TELEFON
    # =================================================

    if step == "phone":

        if update.message.contact:

            data["phone"] = (
                update.message.contact.phone_number
            )

        elif text.strip():

            data["phone"] = text.strip()

        else:

            await update.message.reply_text(
                "❌ Телефон рақамини юборинг."
            )

            return


        data["step"] = "service"


        await update.message.reply_text(

            "🛠 ХИЗМАТНИ ТАНЛАНГ:",

            reply_markup=service_menu(),
        )

        return


    # =================================================
    # XIZMAT
    # =================================================

    if step == "service":

        if text not in SERVICES:

            await update.message.reply_text(

                "❌ Илтимос, хизматлар рўйхатидан "
                "танланг.",

                reply_markup=service_menu(),
            )

            return


        data["service"] = text

        data["step"] = "address"


        location_button = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True,
        )


        await update.message.reply_text(

            "📍 МАНЗИЛНИ ЮБОРИНГ:\n\n"
            "1️⃣ Геолокация юборинг\n"
            "ёки\n"
            "2️⃣ Манзилни матн кўринишида ёзинг.",

            reply_markup=ReplyKeyboardMarkup(

                [

                    [location_button],

                    ["✍️ Манзилни ёзиш"],

                ],

                resize_keyboard=True,
            ),
        )

        return


    # =================================================
    # MANZIL
    # =================================================

    if step == "address":

        if update.message.location:

            latitude = update.message.location.latitude

            longitude = update.message.location.longitude

            data["address"] = (
                f"{latitude}, {longitude}"
            )


        elif text == "✍️ Манзилни ёзиш":

            await update.message.reply_text(

                "📍 Манзилингизни тўлиқ ёзинг:\n\n"
                "Масалан:\n"
                "Андижон шаҳар, Навоий кўчаси, 25-уй"
            )

            return


        elif text.strip():

            data["address"] = text.strip()


        else:

            await update.message.reply_text(

                "❌ Илтимос, геолокация юборинг "
                "ёки манзилни ёзинг."
            )

            return


        data["step"] = "comment"


        await update.message.reply_text(

            "📝 БУЮРТМА ҲАҚИДА ҚЎШИМЧА ИЗОҲ ЁЗИНГ.\n\n"

            "Масалан:\n"
            "«Шкафни йиғиш керак»\n\n"

            "Агар изоҳ бўлмаса, «Йўқ» деб ёзинг."
        )

        return


    # =================================================
    # IZOH
    # =================================================

    if step == "comment":

        data["comment"] = text.strip()

        await create_order(
            update,
            context,
            data
        )

        users.pop(uid, None)

        return


# =====================================================
# BUYURTMA YARATISH
# =====================================================

async def create_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: dict
):

    global order_id

    order_id += 1

    oid = order_id


    order = {

        "id": oid,

        "customer_id": update.effective_user.id,

        "name": data["name"],

        "phone": data["phone"],

        "service": data["service"],

        "address": data["address"],

        "comment": data["comment"],

        "status": "new",

        "master_id": None,

        "master": None,

        "created": datetime.now(),

    }


    orders[oid] = order


    # =================================================
    # DISPETCHER TUGMALARI
    # =================================================

    keyboard = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton(

                    "🟡 Қабул қилиш",

                    callback_data=f"dispatcher_accept_{oid}",
                ),

                InlineKeyboardButton(

                    "🚫 Рад этиш",

                    callback_data=f"dispatcher_reject_{oid}",
                ),

            ],

        ]

    )


    text = (

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 Буюртма: №{oid}\n"

        f"👤 Мижоз: {order['name']}\n"

        f"📞 Телефон: {order['phone']}\n"

        f"🛠 Хизмат: {order['service']}\n"

        f"📍 Манзил: {order['address']}\n"

        f"📝 Изоҳ: {order['comment']}\n\n"

        "📌 Ҳолат: 🆕 Янги"
    )


    # =================================================
    # DISPETCHERGA YUBORISH
    # =================================================

    try:

        await context.bot.send_message(

            chat_id=DISPATCHER_ID,

            text=text,

            reply_markup=keyboard,
        )

    except Exception as e:

        logger.error(
            f"Диспетчерга юборишда хато: {e}"
        )


    # =================================================
    # MIJOZGA TASDIQ
    # =================================================

    await update.message.reply_text(

        f"✅ Буюртмангиз №{oid} қабул қилинди.\n\n"

        "👨‍💼 Диспетчер буюртмани кўриб чиқади.\n"
        "Тез орада сиз билан боғланамиз.\n\n"

        "☎️ USTA 24\n"
        "+998 77 069 00 03",

        reply_markup=client_menu(),
            )
