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
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN топилмади")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID топилмади")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID топилмади")


MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)
ADMIN_ID = int(ADMIN_ID)


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
prices = {}

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
# МЕНЮ
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

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):


    await update.message.reply_text(

        "👋 Ассалому алайкум!\n\n"
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


async def мижоз_хабар(update,context):


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



    if data["қадам"] == "исм":


        data["исм"] = text

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
    # =====================================================
# USTA 24 BOT
# MAIN.PY 2/2
# Уста + Админ + Ишга тушириш
# =====================================================



# ==========================
# МИЖОЗ БУЮРТМА ДАВОМИ
# ==========================


async def давомий_буюртма(update,context):

    uid = update.effective_user.id


    if uid not in users:
        return


    data = users[uid]


    if data["қадам"] == "телефон":


        if update.message.contact:

            data["телефон"] = update.message.contact.phone_number

        else:

            data["телефон"] = update.message.text



        data["қадам"]="хизмат"



        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=хизмат_меню()

        )


        return



    if data["қадам"] == "хизмат":


        data["хизмат"]=update.message.text

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




    if data["қадам"] == "манзил":


        if update.message.location:

            data["манзил"]=(

                f"{update.message.location.latitude}, "
                f"{update.message.location.longitude}"

            )

        else:

            data["манзил"]=update.message.text



        data["қадам"]="изоҳ"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг:"

        )


        return





    if data["қадам"] == "изоҳ":


        data["изоҳ"]=update.message.text


        await яратиш(

            update,

            context,

            data

        )


        users.pop(uid)







# ==========================
# БУЮРТМА ЯРАТИШ
# ==========================


async def яратиш(update,context,data):

    global order_id


    order_id += 1


    oid = order_id



    orders[oid]={

        "id":oid,

        "мижоз":update.effective_user.id,

        "исм":data["исм"],

        "телефон":data["телефон"],

        "хизмат":data["хизмат"],

        "манзил":data["манзил"],

        "изоҳ":data["изоҳ"],

        "ҳолат":"янги",

        "уста":None,

        "вақт":datetime.now()

    }



    тугмалар = InlineKeyboardMarkup(

        [

            [

            InlineKeyboardButton(

                "✅ Қабул қилиш",

                callback_data=f"qabul_{oid}"

            )

            ],

            [

            InlineKeyboardButton(

                "🚫 Рад этиш",

                callback_data=f"rad_{oid}"

            )

            ]

        ]

    )



    хабар=(

        "🆕 Янги буюртма\n\n"

        f"🔢 Рақам: №{oid}\n"

        f"👤 Мижоз: {data['исм']}\n"

        f"📞 Телефон: {data['телефон']}\n"

        f"🛠 Хизмат: {data['хизмат']}\n"

        f"📍 Манзил: {data['манзил']}\n"

        f"📝 Изоҳ: {data['изоҳ']}"

    )



    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=хабар,

        reply_markup=тугмалар

    )



    await update.message.reply_text(

        f"✅ Буюртмангиз қабул қилинди\n"
        f"🔢 №{oid}",

        reply_markup=мижоз_меню()

    )








# ==========================
# УСТА ТУГМАЛАРИ
# ==========================


async def уста_тугма(update,context):


    query=update.callback_query

    await query.answer()


    data=query.data



    if data.startswith("qabul_"):


        oid=int(data.split("_")[1])


        if oid not in orders:
            return



        user=query.from_user


        уста=(

            f"@{user.username}"

            if user.username

            else user.first_name

        )


        orders[oid]["ҳолат"]="қабул қилинган"

        orders[oid]["уста"]=уста



        await query.edit_message_text(

            "🟡 Қабул қилинди\n\n"

            f"№{oid}\n"
            f"👨‍🔧 Уста: {уста}"

        )


        await context.bot.send_message(

            orders[oid]["мижоз"],

            f"🟡 №{oid} буюртмангиз қабул қилинди\n"
            f"👨‍🔧 Уста: {уста}"

        )





    elif data.startswith("rad_"):


        oid=int(data.split("_")[1])


        orders[oid]["ҳолат"]="рад этилди"


        await query.edit_message_text(

            f"🚫 №{oid} рад этилди"

        )






# ==========================
# ADMIN
# ==========================


async def админ(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    await update.message.reply_text(

        "👑 USTA 24 Админ\n\n"
        "📊 /stat\n"
        "👨‍🔧 /ustalar"

    )





async def stat(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    await update.message.reply_text(

        "📊 Статистика\n\n"
        f"Жами буюртмалар: {len(orders)}"

    )






# ==========================
# MAIN
# ==========================


def main():


    bot = Application.builder()\
        .token(TOKEN)\
        .build()



    bot.add_handler(

        CommandHandler(

            "start",

            start

        )

    )


    bot.add_handler(

        CommandHandler(

            "admin",

            админ

        )

    )


    bot.add_handler(

        CommandHandler(

            "stat",

            stat

        )

    )


    bot.add_handler(

        CallbackQueryHandler(

            уста_тугма

        )

    )


    bot.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION,

            давомий_буюртма

        )

    )


    bot.add_handler(

        MessageHandler(

            filters.TEXT,

            мижоз_хабар

        )

    )


    bot.add_handler(

        MessageHandler(

            filters.TEXT,

            давомий_буюртма

        )

    )



    bot.run_polling()





if __name__=="__main__":


    Thread(

        target=run_flask,

        daemon=True

    ).start()


    main()
