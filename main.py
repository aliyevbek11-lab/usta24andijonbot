# =====================================================
# USTA 24 PRO BOT
# FULL MAIN.PY
# MIJOZ + DISPETCHER + USTA + ADMIN
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
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")


ADMIN_ID = int(ADMIN_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)


# =====================================================
# LOGGING
# =====================================================

logging.basicConfig(
    level=logging.INFO
)

logger = logging.getLogger("USTA24")


# =====================================================
# FLASK / RENDER
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
        port=int(os.getenv("PORT", 10000))
    )


# =====================================================
# DATA
# =====================================================

users = {}

orders = {}

masters = {}

reviews = {}

order_id = 0


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
    "accepted": "🟡 Қабул қилинган",
    "process": "🔵 Иш жараёнида",
    "done": "✅ Якунланган",
    "cancel": "❌ Бекор қилинган",
    "reject": "🚫 Рад этилган"

}


# =====================================================
# CLIENT MENU
# =====================================================

def client_menu():

    return ReplyKeyboardMarkup(

        [

            ["📝 Буюртма бериш"],

            ["📋 Хизматлар"],

            ["🔁 Қайта буюртма"]

        ],

        resize_keyboard=True

    )


# =====================================================
# SERVICE MENU
# =====================================================

def service_menu():

    return ReplyKeyboardMarkup(

        [

            [service]

            for service in SERVICES

        ],

        resize_keyboard=True

    )


# =====================================================
# ADMIN MENU
# =====================================================

def admin_menu():

    return ReplyKeyboardMarkup(

        [

            ["👤 Мижозлар"],

            ["👨‍🔧 Усталар"],

            ["📊 Статистика"],

            ["📢 Хабар тарқатиш"],

            ["⬅️ Бош меню"]

        ],

        resize_keyboard=True

    )


# =====================================================
# MASTERS MENU
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
# START
# =====================================================

async def start(update, context):

    if not update.message:
        return

    user = update.effective_user

    await update.message.reply_text(

        f"👋 Ассалому алайкум, "
        f"{user.first_name}!\n\n"

        "🏠 USTA 24\n\n"

        "🛠 Уйингиз учун ишончли уста хизмати.\n\n"

        "Хизмат танланг:",

        reply_markup=client_menu()

    )


# =====================================================
# ADMIN START
# =====================================================

async def admin_start(update, context):

    if not update.message:
        return

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
# NEW ORDER
# =====================================================

async def new_order(update, context):

    if not update.message:
        return

    uid = update.effective_user.id

    users[uid] = {

        "step": "name",

        "name": "",

        "phone": "",

        "service": "",

        "address": "",

        "comment": ""

    }


    await update.message.reply_text(

        "📝 БУЮРТМА БЕРИШ\n\n"

        "👤 Исмингизни ёзинг:"

    )


# =====================================================
# CLIENT HANDLER
# =====================================================

async def client_handler(update, context):

    if not update.message:
        return

    uid = update.effective_user.id

    text = update.message.text or ""


    # -------------------------------------------------
    # BUYURTMA
    # -------------------------------------------------

    if text == "📝 Буюртма бериш":

        await new_order(update, context)

        return


    # -------------------------------------------------
    # XIZMATLAR
    # -------------------------------------------------

    if text == "📋 Хизматлар":

        service_text = (
            "📋 USTA 24 ХИЗМАТЛАРИ\n\n"
        )

        for service in SERVICES:

            service_text += (
                f"{service}\n"
            )

        await update.message.reply_text(

            service_text,

            reply_markup=client_menu()

        )

        return


    # -------------------------------------------------
    # QAYTA BUYURTMA
    # -------------------------------------------------

    if text == "🔁 Қайта буюртма":

        await new_order(update, context)

        return


    # -------------------------------------------------
    # USER JARAYONDA EMAS
    # -------------------------------------------------

    if uid not in users:
        return


    data = users[uid]

    step = data.get("step")


    # =================================================
    # NAME
    # =================================================

    if step == "name":

        if not text.strip():

            await update.message.reply_text(
                "❌ Исмингизни ёзинг."
            )

            return


        data["name"] = text.strip()

        data["step"] = "phone"


        phone_button = KeyboardButton(

            "📞 Телефон рақамимни юбориш",

            request_contact=True

        )


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [[phone_button]],

                resize_keyboard=True,

                one_time_keyboard=True

            )

        )

        return


    # =================================================
    # PHONE
    # =================================================

    if step == "phone":

        if update.message.contact:

            data["phone"] = (
                update.message.contact.phone_number
            )

        else:

            if not text.strip():

                await update.message.reply_text(
                    "❌ Телефон рақамингизни юборинг."
                )

                return

            data["phone"] = text.strip()


        data["step"] = "service"


        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=service_menu()

        )

        return


    # =================================================
    # SERVICE
    # =================================================

    if step == "service":

        if text not in SERVICES:

            await update.message.reply_text(

                "❌ Илтимос, рўйхатдан хизмат танланг.",

                reply_markup=service_menu()

            )

            return


        data["service"] = text

        data["step"] = "address"


        location_button = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True

        )


        await update.message.reply_text(

            "📍 Манзилингизни юборинг.",

            reply_markup=ReplyKeyboardMarkup(

                [

                    [location_button],

                    ["✍️ Манзилни ёзиш"]

                ],

                resize_keyboard=True

            )

        )

        return


    # =================================================
    # ADDRESS
    # =================================================

    if step == "address":

        if update.message.location:

            latitude = (
                update.message.location.latitude
            )

            longitude = (
                update.message.location.longitude
            )

            data["address"] = (

                f"📍 Геолокация: "
                f"{latitude}, {longitude}"

            )


        elif text == "✍️ Манзилни ёзиш":

            data["step"] = "address_text"


            await update.message.reply_text(

                "📍 Манзилни тўлиқ ёзинг.\n\n"

                "Масалан:\n"

                "Андижон шаҳар, Сой кўчаси 77-уй",

                reply_markup=ReplyKeyboardMarkup(

                    [["⬅️ Бош меню"]],

                    resize_keyboard=True

                )

            )

            return


        else:

            data["address"] = text.strip()


        data["step"] = "comment"


        await update.message.reply_text(

            "📝 Буюртма ҳақида қўшимча маълумот ёзинг.\n\n"

            "Ёки:",

            reply_markup=ReplyKeyboardMarkup(

                [["➡️ Изоҳ йўқ"]],

                resize_keyboard=True

            )

        )

        return


    # =================================================
    # ADDRESS TEXT
    # =================================================

    if step == "address_text":

        if text == "⬅️ Бош меню":

            users.pop(uid, None)

            await update.message.reply_text(

                "🏠 Асосий меню:",

                reply_markup=client_menu()

            )

            return


        if not text.strip():

            await update.message.reply_text(
                "❌ Манзилни ёзинг."
            )

            return


        data["address"] = text.strip()

        data["step"] = "comment"


        await update.message.reply_text(

            "📝 Буюртма ҳақида маълумот ёзинг.\n\n"

            "Ёки:",

            reply_markup=ReplyKeyboardMarkup(

                [["➡️ Изоҳ йўқ"]],

                resize_keyboard=True

            )

        )

        return


    # =================================================
    # COMMENT
    # =================================================

    if step == "comment":

        if text == "➡️ Изоҳ йўқ":

            data["comment"] = "Изоҳ йўқ"

        else:

            data["comment"] = text.strip()


        await send_order(
            update,
            context,
            data
        )


        users.pop(uid, None)

        return


# =====================================================
# SEND ORDER
# =====================================================

async def send_order(update, context, data):

    global order_id

    order_id += 1

    oid = order_id


    username = None


    if update.effective_user.username:

        username = (
            "@"
            + update.effective_user.username
        )

    else:

        username = "Username йўқ"


    orders[oid] = {

        "id": oid,

        "customer_id":
            update.effective_user.id,

        "name":
            data["name"],

        "phone":
            data["phone"],

        "service":
            data["service"],

        "address":
            data["address"],

        "comment":
            data["comment"],

        "username":
            username,

        "status":
            "new",

        "master_id":
            None,

        "master":
            None,

        "created":
            datetime.now()

    }


    keyboard = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton(

                    "🟡 Қабул қилиш",

                    callback_data=f"accept_{oid}"

                ),

                InlineKeyboardButton(

                    "🚫 Рад этиш",

                    callback_data=f"reject_{oid}"

                )

            ]

        ]

    )


    order_text = (

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 Буюртма №{oid}\n"

        f"👤 Мижоз: {data['name']}\n"

        f"📞 Телефон: {data['phone']}\n"

        f"🔗 Username: {username}\n"

        f"🛠 Хизмат: {data['service']}\n"

        f"📍 Манзил: {data['address']}\n"

        f"📝 Изоҳ: {data['comment']}\n\n"

        "📌 Ҳолат: 🆕 Янги"

    )


    # =================================================
    # GURUHGA YUBORISH
    # =================================================

    try:

        await context.bot.send_message(

            chat_id=MASTERS_GROUP_ID,

            text=order_text,

            reply_markup=keyboard

        )

    except Exception as e:

        logger.exception(
            f"Guruhga buyurtma yuborilmadi: {e}"
        )

        await update.message.reply_text(

            "❌ Буюртмани усталар гуруҳига "
            "юборишда хатолик юз берди.\n\n"

            "Администраторга хабар беринг.",

            reply_markup=client_menu()

        )

        return


    # =================================================
    # CLIENT RESPONSE
    # =================================================

    await update.message.reply_text(

        "✅ БУЮРТМАНГИЗ ҚАБУЛ ҚИЛИНДИ!\n\n"

        f"🔢 Буюртма №{oid}\n\n"

        "👨‍🔧 Диспетчер буюртмани кўриб чиқади "
        "ва сизга уста бириктиради.\n\n"

        "☎️ USTA 24\n"

        "+998 77 069 00 03",

        reply_markup=client_menu()

    )


# =====================================================
# DISPATCHER CALLBACK
# =====================================================

async def dispatcher_callback(update, context):

    query = update.callback_query

    if not query:
        return


    data = query.data or ""


    try:

        parts = data.split("_")

        action = parts[0]

        oid = int(parts[-1])

    except Exception:

        await query.answer(

            "❌ Маълумот нотўғри.",

            show_alert=True

        )

        return


    if oid not in orders:

        await query.answer(

            "❌ Буюртма топилмади.",

            show_alert=True

        )

        return


    order = orders[oid]


    # =================================================
    # ACCEPT
    # =================================================

    if action == "accept":

        user = query.from_user


        if user.username:

            master_name = (
                "@"
                + user.username
            )

        else:

            master_name = user.first_name


        order["status"] = "accepted"

        order["master_id"] = user.id

        order["master"] = master_name


        # Уста статистикаси
        if user.id in masters:

            masters[user.id]["orders"] += 1


        await query.answer(
            "✅ Буюртма қабул қилинди."
        )


        try:

            await query.edit_message_text(

                "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

                f"🔢 №{oid}\n"

                f"👨‍🔧 Уста: {master_name}\n"

                f"🛠 Хизмат: {order['service']}\n"

                f"📍 Манзил: {order['address']}\n\n"

                "📌 Ҳолат: 🟡 Қабул қилинган"

            )

        except Exception as e:

            logger.error(
                f"Accept edit error: {e}"
            )


        try:

            await context.bot.send_message(

                chat_id=order["customer_id"],

                text=(

                    f"🟡 Буюртмангиз №{oid} "
                    "қабул қилинди.\n\n"

                    f"👨‍🔧 Уста: {master_name}\n\n"

                    "Тез орада уста сиз билан "
                    "боғланади.\n\n"

                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"

                )

            )

        except Exception as e:

            logger.error(
                f"Customer accept error: {e}"
            )

        return


    # =================================================
    # REJECT
    # =================================================

    if action == "reject":

        order["status"] = "reject"


        await query.answer(
            "🚫 Буюртма рад этилди."
        )


        try:

            await query.edit_message_text(

                "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"

                f"🔢 №{oid}\n\n"

                "📌 Ҳолат: 🚫 Рад этилган"

            )

        except Exception as e:

            logger.error(
                f"Reject edit error: {e}"
            )


        try:

            await context.bot.send_message(

                chat_id=order["customer_id"],

                text=(

                    f"🚫 №{oid} буюртма рад этилди.\n\n"

                    "Бошқа уста бириктирилади."

                )

            )

        except Exception as e:

            logger.error(
                f"Reject customer error: {e}"
            )

        return


    # =================================================
    # START
    # =================================================

    if action == "start":

        order["status"] = "process"


        await query.answer(
            "🔵 Иш бошланди."
        )


        try:

            await query.edit_message_text(

                "🔵 БУЮРТМА ИШ ЖАРАЁНИДА\n\n"

                f"🔢 №{oid}\n"

                f"👨‍🔧 Уста: "
                f"{order.get('master', 'Уста')}\n\n"

                "📌 Ҳолат: 🔵 Иш жараёнида"

            )

        except Exception as e:

            logger.error(
                f"Start edit error: {e}"
            )


        try:

            await context.bot.send_message(

                chat_id=order["customer_id"],

                text=(

                    f"🔵 №{oid} буюртма бўйича "
                    "иш бошланди."

                )

            )

        except Exception as e:

            logger.error(
                f"Start customer error: {e}"
            )

        return


    # =================================================
    # DONE
    # =================================================

    if action == "done":

        order["status"] = "done"


        await query.answer(
            "✅ Буюртма якунланди."
        )


        try:

            await query.edit_message_text(

                "✅ БУЮРТМА ЯКУНЛАНДИ\n\n"

                f"🔢 №{oid}\n"

                f"👨‍🔧 Уста: "
                f"{order.get('master', 'Уста')}\n\n"

                "📌 Ҳолат: ✅ Якунланган"

            )

        except Exception as e:

            logger.error(
                f"Done edit error: {e}"
            )


        try:

            await context.bot.send_message(

                chat_id=order["customer_id"],

                text=(

                    f"✅ №{oid} буюртма якунланди.\n\n"

                    "⭐ Уста хизматини баҳолашингиз мумкин."

                )

            )

        except Exception as e:

            logger.error(
                f"Done customer error: {e}"
            )

        return


    # =================================================
    # CANCEL
    # =================================================

    if action == "cancel":

        order["status"] = "cancel"


        await query.answer(
            "❌ Буюртма бекор қилинди."
        )


        try:

            await query.edit_message_text(

                "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"

                f"🔢 №{oid}\n\n"

                "📌 Ҳолат: ❌ Бекор қилинган"

            )

        except Exception as e:

            logger.error(
                f"Cancel edit error: {e}"
            )


        try:

            await context.bot.send_message(

                chat_id=order["customer_id"],

                text=(
                    f"❌ №{oid} буюртма бекор қилинди."
                )

            )

        except Exception as e:

            logger.error(
                f"Cancel customer error: {e}"
            )

        return


    await query.answer(
        "❌ Номаълум буйруқ.",
        show_alert=True
    )


# =====================================================
# /SEND
# =====================================================

async def send_command(update, context):

    if not update.message:
        return


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


    customer_ids = set()


    for order in orders.values():

        customer_id = order.get(
            "customer_id"
        )

        if customer_id:

            customer_ids.add(
                customer_id
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
                f"Send error {customer_id}: {e}"
            )


    await update.message.reply_text(

        "📢 ХАБАР ЮБОРИЛДИ\n\n"

        f"👥 {count} та мижозга юборилди."

    )


# =====================================================
# CUSTOMER BASE
# =====================================================

async def customer_base(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    if not orders:

        await update.message.reply_text(

            "👤 МИЖОЗЛАР БАЗАСИ\n\n"

            "Ҳозирча мижозлар йўқ."

        )

        return


    customers = {}


    for order in orders.values():

        uid = order.get(
            "customer_id"
        )

        if uid:

            customers[uid] = order


    text = (
        "👤 USTA 24 МИЖОЗЛАР БАЗАСИ\n\n"
    )


    for customer in customers.values():

        text += (

            f"👤 {customer.get('name', '-')}\n"

            f"📞 {customer.get('phone', '-')}\n"

            f"🔗 {customer.get('username', '-')}\n"

            f"🛠 {customer.get('service', '-')}\n"

            "────────────────\n"

        )


    if len(text) > 4000:

        text = text[:3900]

        text += "\n\n⚠️ Рўйхат узун."


    await update.message.reply_text(text)


# =====================================================
# ADD MASTER START
# =====================================================

async def add_master_start(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    context.user_data["master_add"] = True


    await update.message.reply_text(

        "➕ УСТА ҚЎШИШ\n\n"

        "Қуйидаги форматда юборинг:\n\n"

        "ID | Исм | Телефон | Username | Хизматлар\n\n"

        "Масалан:\n"

        "123456789 | Али | +998901234567 | "
        "@ali_usta | Мебель, Шкаф, Кўчириш"

    )


# =====================================================
# ADD MASTER
# =====================================================

async def add_master_handler(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    text = update.message.text or ""


    if text == "⬅️ Админ меню":

        context.user_data.pop(
            "master_add",
            None
        )


        await update.message.reply_text(

            "👑 USTA 24 АДМИН\n\n"

            "Бўлимни танланг:",

            reply_markup=admin_menu()

        )

        return


    parts = [
        x.strip()
        for x in text.split("|")
    ]


    if len(parts) != 5:

        await update.message.reply_text(

            "❌ Формат нотўғри.\n\n"

            "Тўғри формат:\n"

            "ID | Исм | Телефон | "
            "Username | Хизматлар"

        )

        return


    try:

        master_id = int(parts[0])

    except ValueError:

        await update.message.reply_text(

            "❌ ID рақам бўлиши керак."

        )

        return


    name = parts[1]
    phone = parts[2]
    username = parts[3]
    services = parts[4]


    if not username:

        username = "Username йўқ"


    if not services:

        services = "Барча хизматлар"


    masters[master_id] = {

        "id": master_id,

        "name": name,

        "phone": phone,

        "username": username,

        "services": services,

        "orders": 0,

        "active": True

    }


    context.user_data.pop(
        "master_add",
        None
    )


    await update.message.reply_text(

        "✅ УСТА ҚЎШИЛДИ\n\n"

        f"🆔 ID: {master_id}\n"

        f"👨‍🔧 Исм: {name}\n"

        f"📞 Телефон: {phone}\n"

        f"🔗 Username: {username}\n"

        f"🛠 Хизматлар: {services}",

        reply_markup=masters_menu()

    )


# =====================================================
# MASTERS LIST
# =====================================================

async def masters_list(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    if not masters:

        await update.message.reply_text(

            "👨‍🔧 УСТАЛАР\n\n"

            "Ҳозирча усталар қўшилмаган.",

            reply_markup=masters_menu()

        )

        return


    text = (
        "👨‍🔧 USTA 24 УСТАЛАРИ\n\n"
    )


    for master_id, master in masters.items():

        status = (

            "🟢 Фаол"

            if master.get("active", True)

            else "🔴 Нофаол"

        )


        text += (

            f"🆔 ID: {master_id}\n"

            f"👨‍🔧 Исм: "
            f"{master.get('name', '-')}\n"

            f"📞 Телефон: "
            f"{master.get('phone', '-')}\n"

            f"🔗 Username: "
            f"{master.get('username', '-')}\n"

            f"🛠 Хизматлар: "
            f"{master.get('services', '-')}\n"

            f"📋 Буюртмалар: "
            f"{master.get('orders', 0)}\n"

            f"📌 Ҳолат: {status}\n"

            "────────────────\n"

        )


    if len(text) > 4000:

        text = text[:3900]

        text += "\n\n⚠️ Рўйхат узун."


    await update.message.reply_text(

        text,

        reply_markup=masters_menu()

    )


# =====================================================
# DELETE MASTER START
# =====================================================

async def delete_master_start(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    if not masters:

        await update.message.reply_text(

            "🗑 Ўчириш учун уста йўқ.",

            reply_markup=masters_menu()

        )

        return


    context.user_data["delete_master"] = True


    await update.message.reply_text(

        "🗑 УСТАНИ ЎЧИРИШ\n\n"

        "Устанинг ID рақамини юборинг.\n\n"

        "Масалан:\n"

        "123456789"

    )


# =====================================================
# DELETE MASTER
# =====================================================

async def delete_master_handler(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    text = update.message.text or ""


    if text == "⬅️ Админ меню":

        context.user_data.pop(
            "delete_master",
            None
        )


        await update.message.reply_text(

            "👑 USTA 24 АДМИН\n\n"

            "Бўлимни танланг:",

            reply_markup=admin_menu()

        )

        return


    try:

        master_id = int(
            text.strip()
        )

    except ValueError:

        await update.message.reply_text(

            "❌ ID рақам бўлиши керак."

        )

        return


    if master_id not in masters:

        await update.message.reply_text(

            "❌ Бундай ID билан уста топилмади."

        )

        return


    master = masters[master_id]


    del masters[master_id]


    context.user_data.pop(
        "delete_master",
        None
    )


    await update.message.reply_text(

        "✅ УСТА ЎЧИРИЛДИ\n\n"

        f"👨‍🔧 {master.get('name', '-')}\n"

        f"🆔 ID: {master_id}",

        reply_markup=masters_menu()

    )


# =====================================================
# STATISTICS
# =====================================================

async def statistics(update, context):

    if not update.message:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    total = len(orders)

    new_count = 0
    accepted = 0
    process = 0
    done = 0
    cancel = 0
    reject = 0


    for order in orders.values():

        status = order.get(
            "status"
        )


        if status == "new":

            new_count += 1

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

        f"📋 Жами: {total}\n\n"

        f"🆕 Янги: {new_count}\n"

        f"🟡 Қабул қилинган: {accepted}\n"

        f"🔵 Иш жараёнида: {process}\n"

        f"✅ Якунланган: {done}\n"

        f"❌ Бекор қилинган: {cancel}\n"

        f"🚫 Рад этилган: {reject}\n\n"

        f"👨‍🔧 Усталар: {len(masters)}"

    )


# =====================================================
# ADMIN BUTTON HANDLER
# =====================================================

async def admin_button_handler(update, context):

    if not update.message:
        return False


    if update.effective_user.id != ADMIN_ID:
        return False


    text = update.message.text or ""


    if text == "👤 Мижозлар":

        await customer_base(
            update,
            context
        )

        return True


    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(

            "👨‍🔧 УСТАЛАР БОШҚАРУВИ\n\n"

            "Бўлимни танланг:",

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


    if text == "📊 Статистика":

        await statistics(
            update,
            context
        )

        return True


    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(

            "📢 ХАБАР ТАРҚАТИШ\n\n"

            "Формат:\n"

            "/send Хабар матни"

        )

        return True


    if text == "⬅️ Админ меню":

        await update.message.reply_text(

            "👑 USTA 24 АДМИН\n\n"

            "Бўлимни танланг:",

            reply_markup=admin_menu()

        )

        return True


    if text == "⬅️ Бош меню":

        context.user_data.pop(
            "master_add",
            None
        )

        context.user_data.pop(
            "delete_master",
            None
        )


        await update.message.reply_text(

            "🏠 USTA 24\n\n"

            "Асосий меню:",

            reply_markup=client_menu()

        )

        return True


    return False


# =====================================================
# ALL TEXT HANDLER
# =====================================================

async def all_text_handler(update, context):

    if not update.message:
        return


    uid = update.effective_user.id


    # =================================================
    # ADMIN
    # =================================================

    if uid == ADMIN_ID:


        if context.user_data.get(
            "master_add"
        ):

            await add_master_handler(
                update,
                context
            )

            return


        if context.user_data.get(
            "delete_master"
        ):

            await delete_master_handler(
                update,
                context
            )

            return


        handled = await admin_button_handler(
            update,
            context
        )


        if handled:
            return


    # =================================================
    # CLIENT
    # =================================================

    await client_handler(
        update,
        context
    )


# =====================================================
# CONTACT / LOCATION
# =====================================================

async def contact_location_handler(update, context):

    if not update.message:
        return


    await client_handler(
        update,
        context
    )


# =====================================================
# CALLBACK ROUTER
# =====================================================

async def callback_router(update, context):

    query = update.callback_query

    if not query:
        return


    data = query.data or ""


    if (

        data.startswith("accept_")

        or data.startswith("reject_")

        or data.startswith("start_")

        or data.startswith("done_")

        or data.startswith("cancel_")

    ):

        await dispatcher_callback(
            update,
            context
        )

        return


    await query.answer()


# =====================================================
# ERROR HANDLER
# =====================================================

async def error_handler(update, context):

    logger.error(

        "USTA24 BOT ERROR",

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
    # FLASK
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
