    # =====================================================
# USTA 24 BOT
# MAIN.PY 1/2
# Мижоз + Буюртма тизими
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


# ==========================
# СОЗЛАНМАЛАР
# ==========================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN топилмади")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID топилмади")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID топилмади")


ADMIN_ID = int(ADMIN_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)


logging.basicConfig(
    level=logging.INFO
)



# ==========================
# RENDER
# ==========================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 ишлаяпти"


@app.route("/health")
def health():
    return "OK"



def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT",10000))
    )



# ==========================
# БАЗА
# ==========================

users = {}
orders = {}
masters = {}
reviews = {}

order_id = 0



# ==========================
# ХИЗМАТЛАР
# ==========================

SERVICES = [

"🪑 Мебель йиғиш",
"🛠 Мебель таъмирлаш",
"🍽 Ошхона мебели",
"🚪 Шкаф купе",
"🛏 Каравот йиғиш",
"🪑 Стол ва стул",
"📦 Мебель кўчириш",
"🚚 Уй кўчириш",
"🚛 Юк ташиш",
"🔩 Сантехника",
"⚡ Электр ишлари",
"🔥 Иситиш тизими",
"🎨 Бўяш ишлари",
"🪟 Эшик ва дераза",
"❄ Кондиционер",
"📡 Интернет ўрнатиш",
"🧹 Тозалаш",
"🔨 Пайвандлаш",
"🏠 Уста чақириш",
"🔧 Бошқа хизмат"

]



# ==========================
# МЕНЮЛАР
# ==========================


def мижоз_меню():

    return ReplyKeyboardMarkup(

        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["🔁 Қайта буюртма"]
        ],

        resize_keyboard=True

    )



def хизмат_меню():

    return ReplyKeyboardMarkup(

        [[x] for x in SERVICES],

        resize_keyboard=True

    )



# ==========================
# START
# ==========================


async def start(update,context):

    await update.message.reply_text(

        "👋 Ассалому алайкум\n\n"
        "🏠 USTA 24 хизматлари\n\n"
        "Керакли бўлимни танланг:",

        reply_markup=мижоз_меню()

    )



# ==========================
# БУЮРТМА БОШЛАШ
# ==========================


async def янги_буюртма(update,context):

    uid = update.effective_user.id


    users[uid] = {

        "қадам":"исм",
        "исм":"",
        "телефон":"",
        "хизмат":"",
        "манзил":"",
        "изоҳ":""

    }


    await update.message.reply_text(

        "📝 Буюртма бериш\n\n"
        "👤 Исмингизни ёзинг:"

    )




# ==========================
# МИЖОЗ ХАБАРЛАРИ
# ==========================


async def message_handler(update,context):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""



    if text == "📝 Буюртма бериш":

        await янги_буюртма(update,context)

        return



    if uid not in users:

        return



    data = users[uid]



    if data["қадам"]=="исм":

        data["исм"]=text

        data["қадам"]="телефон"


        тугма = KeyboardButton(

            "📞 Телефон рақамимни юбориш",

            request_contact=True

        )


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [[тугма]],

                resize_keyboard=True

            )

        )

        return



    if data["қадам"]=="телефон":

        if update.message.contact:

            data["телефон"] = update.message.contact.phone_number

        else:

            data["телефон"] = text


        data["қадам"]="хизмат"


        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=хизмат_меню()

        )

        return



    if data["қадам"]=="хизмат":

        data["хизмат"]=text

        data["қадам"]="манзил"


        тугма = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True

        )


        await update.message.reply_text(

            "📍 Манзилни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [
                    [тугма],
                    ["Манзилни ёзиш"]
                ],

                resize_keyboard=True

            )

        )

        return

# =====================================================
# USTA 24 BOT
# MAIN.PY 2/2
# Уста + Админ + Ишга тушириш
# =====================================================


# ==========================
# БУЮРТМА ЯРАТИШ
# ==========================


async def create_order(update, context):

    global order_id


    uid = update.effective_user.id

    data = users[uid]


    order_id += 1

    oid = order_id



    orders[oid] = {

        "id": oid,

        "мижоз": uid,

        "исм": data["исм"],

        "телефон": data["телефон"],

        "хизмат": data["хизмат"],

        "манзил": data["манзил"],

        "изоҳ": data["изоҳ"],

        "ҳолат": "янги",

        "уста": None,

        "вақт": datetime.now()

    }



    тугма = InlineKeyboardMarkup(

        [

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

        ]

    )



    хабар=(

        "🆕 Янги буюртма\n\n"

        f"🔢 №{oid}\n"

        f"👤 Мижоз: {data['исм']}\n"

        f"📞 Телефон: {data['телефон']}\n"

        f"🛠 Хизмат: {data['хизмат']}\n"

        f"📍 Манзил: {data['манзил']}\n"

        f"📝 Изоҳ: {data['изоҳ']}"

    )



    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=хабар,

        reply_markup=тугма

    )



    await update.message.reply_text(

        f"✅ Буюртма қабул қилинди\n\n"
        f"🔢 №{oid}\n"
        "👨‍🔧 Усталарга юборилди",

        reply_markup=мижоз_меню()

    )



    users.pop(uid)



# ==========================
# МАНЗИЛ ВА ИЗОҲ
# ==========================


async def extra_handler(update,context):


    uid = update.effective_user.id


    if uid not in users:
        return



    data = users[uid]

    text = update.message.text or ""



    if data["қадам"]=="манзил":


        if update.message.location:

            data["манзил"] = (

                f"{update.message.location.latitude},"
                f"{update.message.location.longitude}"

            )

        else:

            data["манзил"] = text



        data["қадам"]="изоҳ"


        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг:"

        )

        return




    if data["қадам"]=="изоҳ":


        data["изоҳ"]=text


        await create_order(

            update,

            context

        )

        return





# ==========================
# УСТА ТУГМАЛАРИ
# ==========================


async def order_button(update,context):


    query = update.callback_query

    await query.answer()


    data=query.data



    oid=int(data.split("_")[1])


    order=orders.get(oid)


    if not order:
        return



    if data.startswith("accept_"):


        user=query.from_user


        master=(

            f"@{user.username}"

            if user.username

            else user.first_name

        )



        order["ҳолат"]="қабул қилинган"

        order["уста"]=master



        await query.edit_message_text(

            "🟡 Қабул қилинди\n\n"

            f"№{oid}\n"
            f"👨‍🔧 Уста: {master}"

        )


        await context.bot.send_message(

            order["мижоз"],

            f"🟡 №{oid} буюртмангиз қабул қилинди\n"
            f"👨‍🔧 Уста: {master}"

        )




    elif data.startswith("reject_"):


        order["ҳолат"]="рад этилган"


        await query.edit_message_text(

            f"🚫 №{oid} буюртма рад этилди"

        )





# ==========================
# АДМИН
# ==========================


async def admin(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    await update.message.reply_text(

        "👑 USTA 24 АДМИН\n\n"
        "/stat - статистика\n"
        "/mijoz - мижозлар\n"
        "/ustalar - усталар"

    )





async def statistic(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    await update.message.reply_text(

        "📊 ТЎЛИҚ СТАТИСТИКА\n\n"

        f"📋 Жами буюртма: {len(orders)}"

    )





async def customers(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="👤 МИЖОЗЛАР\n\n"


    for o in orders.values():

        text += (

            f"👤 {o['исм']}\n"
            f"📞 {o['телефон']}\n"
            "────────\n"

        )


    await update.message.reply_text(text)





# ==========================
# ИШГА ТУШИРИШ
# ==========================


def main():


    application = Application.builder()\
        .token(TOKEN)\
        .build()



    application.add_handler(

        CommandHandler(

            "start",

            start

        )

    )


    application.add_handler(

        CommandHandler(

            "admin",

            admin

        )

    )


    application.add_handler(

        CommandHandler(

            "stat",

            statistic

        )

    )


    application.add_handler(

        CommandHandler(

            "mijoz",

            customers

        )

    )



    application.add_handler(

        CallbackQueryHandler(

            order_button

        )

    )


    application.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION,

            message_handler

        )

    )


    application.add_handler(

        MessageHandler(

            filters.TEXT,

            message_handler

        )

    )


    application.add_handler(

        MessageHandler(

            filters.TEXT,

            extra_handler

        )

    )



    application.run_polling()





if __name__=="__main__":


    Thread(

        target=run_flask,

        daemon=True

    ).start()


    main()
