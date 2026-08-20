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
# =====================================================
# MAIN.PY — 2/2
# DISPETCHER + USTA + ADMIN
# =====================================================


# =====================================================
# BUYURTMA MATNI
# =====================================================

def order_text(order):

    master = order.get("master") or "Ҳали бириктирилмаган"

    status = STATUS.get(
        order.get("status"),
        order.get("status")
    )

    return (
        "📋 БУЮРТМА\n\n"
        f"🔢 Буюртма: №{order['id']}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"📝 Изоҳ: {order['comment']}\n\n"
        f"👨‍🔧 Уста: {master}\n"
        f"📌 Ҳолат: {status}"
    )


# =====================================================
# DISPETCHER BUYURTMA TUGMALARI
# =====================================================

def dispatcher_order_keyboard(oid):

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🟡 Қабул қилиш",
                callback_data=f"da_{oid}"
            ),
            InlineKeyboardButton(
                "🚫 Рад этиш",
                callback_data=f"dr_{oid}"
            )
        ],

        [
            InlineKeyboardButton(
                "👨‍🔧 Уста танлаш",
                callback_data=f"dm_{oid}"
            )
        ],

        [
            InlineKeyboardButton(
                "📞 Мижоз билан боғланиш",
                callback_data=f"dc_{oid}"
            )
        ]

    ])


# =====================================================
# USTA TUGMALARI
# =====================================================

def master_order_keyboard(oid, status):

    if status == "new":

        return InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🟡 Қабул қилиш",
                    callback_data=f"ua_{oid}"
                ),
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"ur_{oid}"
                )
            ]

        ])


    if status == "accepted":

        return InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔵 Ишни бошлаш",
                    callback_data=f"us_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔄 Бошқа устага бериш",
                    callback_data=f"ub_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "📞 Мижоз билан боғланиш",
                    callback_data=f"uc_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"ux_{oid}"
                )
            ]

        ])


    if status == "process":

        return InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "✅ Ишни якунлаш",
                    callback_data=f"ud_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "📞 Мижоз билан боғланиш",
                    callback_data=f"uc_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"ux_{oid}"
                )
            ]

        ])


    return None


# =====================================================
# CALLBACK
# =====================================================

async def callback_handler(update, context):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    parts = data.split("_")

    if len(parts) != 2:

        return

    action = parts[0]

    try:

        oid = int(parts[1])

    except:

        return


    if oid not in orders:

        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True
        )

        return


    order = orders[oid]

    uid = query.from_user.id


    # =================================================
    # DISPETCHER QABUL
    # =================================================

    if action == "da":

        if uid != DISPATCHER_ID:

            await query.answer(
                "❌ Бу амал фақат диспетчер учун.",
                show_alert=True
            )

            return


        if order["status"] != "new":

            await query.answer(
                "⚠️ Буюртма аллақачон қабул қилинган.",
                show_alert=True
            )

            return


        order["status"] = "accepted"


        await query.edit_message_text(

            text=(
                "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=dispatcher_order_keyboard(oid)
        )

        return


    # =================================================
    # DISPETCHER RAD
    # =================================================

    if action == "dr":

        if uid != DISPATCHER_ID:

            await query.answer(
                "❌ Бу амал фақат диспетчер учун.",
                show_alert=True
            )

            return


        order["status"] = "reject"


        await query.edit_message_text(

            text=(
                "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
                f"{order_text(order)}"
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"🚫 №{oid} буюртма рад этилди.\n\n"
                "Илтимос, қайта буюртма беришингиз мумкин.\n\n"
                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            ),

            reply_markup=client_menu()
        )

        return


    # =================================================
    # DISPETCHER MIJOZ BILAN BOG'LANISH
    # =================================================

    if action == "dc":

        if uid != DISPATCHER_ID:

            await query.answer(
                "❌ Бу амал фақат диспетчер учун.",
                show_alert=True
            )

            return


        await query.answer(
            f"📞 {order['phone']}",
            show_alert=True
        )

        return


    # =================================================
    # DISPETCHER USTA TANLASH
    # =================================================

    if action == "dm":

        if uid != DISPATCHER_ID:

            await query.answer(
                "❌ Бу амал фақат диспетчер учун.",
                show_alert=True
            )

            return


        if not masters:

            await query.answer(
                "❌ Ҳали уста қўшилмаган.",
                show_alert=True
            )

            return


        buttons = []


        for mid, master in masters.items():

            buttons.append([

                InlineKeyboardButton(

                    f"👨‍🔧 {master['name']}",

                    callback_data=f"assign_{oid}_{mid}"
                )

            ])


        await query.message.reply_text(

            "👨‍🔧 УСТАНИ ТАНЛАНГ:",

            reply_markup=InlineKeyboardMarkup(buttons)
        )

        return


    # =================================================
    # USTA QABUL
    # =================================================

    if action == "ua":

        user = query.from_user


        if order["status"] not in [
            "new",
            "accepted"
        ]:

            await query.answer(
                "⚠️ Бу буюртмани қабул қилиб бўлмайди.",
                show_alert=True
            )

            return


        if order.get("master_id"):

            if order["master_id"] != user.id:

                await query.answer(
                    "❌ Бу буюртма бошқа устага берилган.",
                    show_alert=True
                )

                return


        master_name = (

            f"@{user.username}"

            if user.username

            else user.first_name
        )


        order["status"] = "accepted"

        order["master"] = master_name

        order["master_id"] = user.id


        await query.edit_message_text(

            text=(
                "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=master_order_keyboard(
                oid,
                "accepted"
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"
                f"👨‍🔧 Уста: {master_name}\n\n"
                "Тез орада уста ишни бошлайди.\n\n"
                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # USTA RAD
    # =================================================

    if action == "ur":

        order["status"] = "reject"


        await query.edit_message_text(

            text=(
                "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
                f"{order_text(order)}"
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"🚫 №{oid} буюртма рад этилди.\n\n"
                "Бошқа уста бириктирилади."
            )
        )

        return


    # =================================================
    # USTA ISHNI BOSHLASH
    # =================================================

    if action == "us":

        if order.get("master_id") != uid:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True
            )

            return


        order["status"] = "process"


        await query.edit_message_text(

            text=(
                "🔵 ИШ ЖАРАЁНИДА\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=master_order_keyboard(
                oid,
                "process"
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"
                f"👨‍🔧 Уста: {order['master']}\n\n"
                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # USTA MIJOZ BILAN BOG'LANISH
    # =================================================

    if action == "uc":

        if order.get("master_id") != uid:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True
            )

            return


        await query.answer(
            f"📞 {order['phone']}",
            show_alert=True
        )

        return


    # =================================================
    # USTA BOSHQA USTAGA BERISH
    # =================================================

    if action == "ub":

        if order.get("master_id") != uid:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True
            )

            return


        old_master = order.get("master")


        order["status"] = "new"

        order["master"] = None

        order["master_id"] = None


        keyboard = master_order_keyboard(
            oid,
            "new"
        )


        await query.edit_message_text(

            text=(
                "🔄 БОШҚА УСТАГА БЕРИЛДИ\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=keyboard
        )


        await context.bot.send_message(

            chat_id=MASTERS_GROUP_ID,

            text=(
                "🔄 БОШҚА УСТАГА БЕРИЛГАН БУЮРТМА\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=keyboard
        )

        return


    # =================================================
    # USTA YAKUNLASH
    # =================================================

    if action == "ud":

        if order.get("master_id") != uid:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True
            )

            return


        order["status"] = "done"


        await query.edit_message_text(

            text=(
                "✅ БУЮРТМА ЯКУНЛАНДИ\n\n"
                f"{order_text(order)}"
            )
        )


        keyboard = InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "⭐ Баҳо бериш",
                    callback_data=f"rate_{oid}"
                )
            ]

        ])


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"✅ №{oid} буюртмангиз якунланди.\n\n"
                f"👨‍🔧 Уста: {order['master']}\n\n"
                "Хизматимизга баҳо беринг:"
            ),

            reply_markup=keyboard
        )

        return


    # =================================================
    # USTA BEKOR QILISH
    # =================================================

    if action == "ux":

        if order.get("master_id") != uid:

            await query.answer(
                "❌ Бу буюртма сизга бириктирилмаган.",
                show_alert=True
            )

            return


        order["status"] = "cancel"


        await query.edit_message_text(

            text=(
                "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"
                f"{order_text(order)}"
            )
        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(
                f"❌ №{oid} буюртма бекор қилинди.\n\n"
                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            ),

            reply_markup=client_menu()
        )

        return


    # =================================================
    # RATING
    # =================================================

    if action == "rate":

        if order["status"] != "done":

            await query.answer(
                "⚠️ Буюртма ҳали якунланмаган.",
                show_alert=True
            )

            return


        keyboard = InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "⭐",
                    callback_data=f"rating_1_{oid}"
                ),

                InlineKeyboardButton(
                    "⭐⭐",
                    callback_data=f"rating_2_{oid}"
                ),

                InlineKeyboardButton(
                    "⭐⭐⭐",
                    callback_data=f"rating_3_{oid}"
                )
            ],

            [
                InlineKeyboardButton(
                    "⭐⭐⭐⭐",
                    callback_data=f"rating_4_{oid}"
                ),

                InlineKeyboardButton(
                    "⭐⭐⭐⭐⭐",
                    callback_data=f"rating_5_{oid}"
                )
            ]

        ])


        await query.message.reply_text(

            "⭐ Устага баҳо беринг:",

            reply_markup=keyboard
        )

        return


    # =================================================
    # RATING QABUL
    # =================================================

    if action == "rating":

        if len(parts) != 3:

            return


        rating = int(parts[1])

        rating_oid = int(parts[2])


        if rating_oid not in orders:

            return


        rating_order = orders[rating_oid]


        reviews[rating_oid] = {

            "customer_id":
                rating_order["customer_id"],

            "master_id":
                rating_order.get("master_id"),

            "rating":
                rating,

            "created":
                datetime.now(),

        }


        await query.edit_message_text(

            f"⭐ Раҳмат!\n\n"
            f"Сизнинг баҳонгиз: {rating}/5\n\n"
            "USTA 24 хизматидан фойдаланганингиз учун раҳмат."
        )

        return


# =====================================================
# ADMIN START
# =====================================================

async def admin_start(update, context):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return


    await update.message.reply_text(

        "👑 USTA 24 АДМИН\n\n"
        "Бўлимни танланг:",

        reply_markup=admin_menu()
    )


# =====================================================
# DISPETCHER START
# =====================================================

async def dispatcher_start(update, context):

    if update.effective_user.id != DISPATCHER_ID:

        await update.message.reply_text(
            "❌ Сиз диспетчер эмассиз."
        )

        return


    await update.message.reply_text(

        "👨‍💼 USTA 24 ДИСПЕТЧЕР\n\n"
        "Буюртмаларни бошқариш панели:",

        reply_markup=dispatcher_menu()
    )


# =====================================================
# MIJOZ BAZASI
# =====================================================

async def customer_base(update, context):

    if update.effective_user.id != ADMIN_ID:

        return


    if not orders:

        await update.message.reply_text(
            "👤 Мижозлар базаси ҳозирча бўш."
        )

        return


    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"


    seen = set()


    for order in orders.values():

        cid = order["customer_id"]

        if cid in seen:
            continue

        seen.add(cid)


        text += (

            f"👤 {order['name']}\n"
            f"📞 {order['phone']}\n"
            f"📍 {order['address']}\n"
            "────────────\n"
        )


    await update.message.reply_text(text)


# =====================================================
# USTALAR
# =====================================================

async def masters_list(update, context):

    if update.effective_user.id not in [
        ADMIN_ID,
        DISPATCHER_ID
    ]:

        return


    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Ҳали усталар қўшилмаган."
        )

        return


    text = "👨‍🔧 УСТАЛАР\n\n"


    for mid, master in masters.items():

        text += (

            f"🆔 {mid}\n"
            f"👨‍🔧 {master['name']}\n"
            f"📞 {master['phone']}\n"
            f"📊 Буюртмалар: "
            f"{master.get('orders', 0)}\n"
            "────────────\n"
        )


    await update.message.reply_text(text)


# =====================================================
# STATISTIKA
# =====================================================

async def statistics(update, context):

    if update.effective_user.id not in [
        ADMIN_ID,
        DISPATCHER_ID
    ]:

        return


    total = len(orders)

    new = 0
    accepted = 0
    process = 0
    done = 0
    cancel = 0
    reject = 0


    for order in orders.values():

        status = order["status"]


        if status == "new":
            new += 1

        elif status == "accepted":
            accepted += 1

        elif status == "process":
            process += 1

        elif status == "done":
            done += 1

        elif status == "cancel":
            cancel += 1

        elif status == "reject":
            reject += 1


    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n"
        f"🆕 Янги: {new}\n"
        f"🟡 Қабул қилинган: {accepted}\n"
        f"🔵 Иш жараёнида: {process}\n"
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор қилинган: {cancel}\n"
        f"🚫 Рад этилган: {reject}"
    )


# =====================================================
# ADMIN BUTTON
# =====================================================

async def admin_button(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    text = update.message.text or ""


    if text == "👤 Мижоз базаси":

        await customer_base(
            update,
            context
        )

        return


    if text == "👨‍🔧 Усталар":

        await masters_list(
            update,
            context
        )

        return


    if text == "📊 Тўлиқ статистика":

        await statistics(
            update,
            context
        )

        return


    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(

            "📢 Хабар тарқатиш учун:\n\n"
            "/send Хабар матни"
        )

        return


    if text == "📈 Ҳисобот":

        await statistics(
            update,
            context
        )

        return


# =====================================================
# DISPETCHER BUTTON
# =====================================================

async def dispatcher_button(update, context):

    if not update.message:
        return


    if update.effective_user.id != DISPATCHER_ID:
        return


    text = update.message.text or ""


    if text == "👨‍🔧 Усталар":

        await masters_list(
            update,
            context
        )

        return


    if text == "📊 Статистика":

        await statistics(
            update,
            context
        )

        return


    if text == "📋 Барча буюртмалар":

        if not orders:

            await update.message.reply_text(
                "📋 Буюртмалар ҳозирча йўқ."
            )

            return


        text_out = "📋 БАРЧА БУЮРТМАЛАР\n\n"


        for order in orders.values():

            text_out += (

                f"🔢 №{order['id']}\n"
                f"👤 {order['name']}\n"
                f"🛠 {order['service']}\n"
                f"📌 {STATUS.get(order['status'])}\n"
                "────────────\n"
            )


        await update.message.reply_text(
            text_out
        )

        return


# =====================================================
# SEND
# =====================================================

async def send_command(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    message = " ".join(context.args)


    if not message:

        await update.message.reply_text(

            "❌ Хабар матни йўқ.\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return


    customer_ids = set(

        order["customer_id"]

        for order in orders.values()
    )


    count = 0


    for customer_id in customer_ids:

        try:

            await context.bot.send_message(

                chat_id=customer_id,

                text=message
            )

            count += 1

        except Exception as e:

            logger.warning(
                f"Хабар юборилмади: {e}"
            )


    await update.message.reply_text(

        "📢 ХАБАР ТАРҚАТИЛДИ\n\n"
        f"👥 Юборилди: {count} та мижоз"
    )


# =====================================================
# MASTER ASSIGN
# =====================================================

async def assign_master_callback(update, context):

    query = update.callback_query

    await query.answer()


    parts = query.data.split("_")


    if len(parts) != 3:

        return


    oid = int(parts[1])

    mid = int(parts[2])


    if query.from_user.id != DISPATCHER_ID:

        await query.answer(
            "❌ Фақат диспетчер.",
            show_alert=True
        )

        return


    if oid not in orders or mid not in masters:

        return


    order = orders[oid]

    master = masters[mid]


    order["status"] = "assigned"

    order["master_id"] = mid

    order["master"] = master["name"]


    master["orders"] = master.get(
        "orders",
        0
    ) + 1


    await query.message.reply_text(

        "👨‍🔧 УСТА БИРИКТИРИЛДИ\n\n"

        f"{order_text(order)}"
    )


    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=(
            "🆕 СИЗГА ЯНГИ БУЮРТМА БЕРИЛДИ\n\n"
            f"{order_text(order)}"
        ),

        reply_markup=master_order_keyboard(
            oid,
            "new"
        )
    )


    await context.bot.send_message(

        chat_id=order["customer_id"],

        text=(
            f"👨‍🔧 №{oid} буюртмангизга уста бириктирилди.\n\n"
            f"👨‍🔧 Уста: {master['name']}\n\n"
            "Тез орада сиз билан боғланади.\n\n"
            "☎️ USTA 24\n"
            "+998 77 069 00 03"
        )
    )


# =====================================================
# GENERAL MESSAGE ROUTER
# =====================================================

async def message_router(update, context):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""


    # ADMIN

    if uid == ADMIN_ID:

        await admin_button(
            update,
            context
        )

        return


    # DISPETCHER

    if uid == DISPATCHER_ID:

        await dispatcher_button(
            update,
            context
        )

        return


    # CLIENT

    await client_handler(
        update,
        context
    )


# =====================================================
# MAIN
# =====================================================

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )


    # START

    application.add_handler(

        CommandHandler(
            "start",
            start
        )
    )


    # ADMIN

    application.add_handler(

        CommandHandler(
            "admin",
            admin_start
        )
    )


    # DISPETCHER

    application.add_handler(

        CommandHandler(
            "dispatcher",
            dispatcher_start
        )
    )


    # SEND

    application.add_handler(

        CommandHandler(
            "send",
            send_command
        )
    )


    # MASTER ASSIGN

    application.add_handler(

        CallbackQueryHandler(
            assign_master_callback,
            pattern=r"^assign_\d+_\d+$"
        )
    )


    # ALL OTHER CALLBACKS

    application.add_handler(

        CallbackQueryHandler(
            callback_handler
        )
    )


    # MESSAGES

    application.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION |
            filters.TEXT,

            message_router
        )
    )


    # FLASK

    Thread(
        target=run_flask,
        daemon=True
    ).start()


    print(
        "USTA 24 BOT ISHLADI"
    )


    application.run_polling()


# =====================================================
# START
# =====================================================

if __name__ == "__main__":

    main()
