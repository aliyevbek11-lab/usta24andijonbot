# =====================================================
# USTA 24 BOT
# MAIN.PY 1/2
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
# CONFIG
# ==========================

TOKEN = os.getenv("BOT_TOKEN")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")


MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)
ADMIN_ID = int(ADMIN_ID)



logging.basicConfig(
    level=logging.INFO
)



# ==========================
# RENDER FLASK
# ==========================

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
        port=int(os.getenv("PORT",10000))
    )




# ==========================
# DATABASE
# ==========================

users = {}

orders = {}

masters = {}

reviews = {}

prices = {}


user_state = {}


order_id = 0




# ==========================
# XIZMATLAR
# ==========================

SERVICES = [

"🪑 Mebel yig‘ish",
"🪑 Mebel ta’mirlash",
"🍽 Oshxona mebeli",
"🚪 Shkaf kupe",
"🛏 Krovat yig‘ish",
"🪑 Stol stul",
"📦 Mebel ko‘chirish",
"🚚 Uy ko‘chirish",
"🚛 Yuk tashish",
"🔩 Santexnika",
"🚿 Kran va truba",
"🔥 Isitish tizimi",
"⚡ Elektr ишлари",
"💡 Chiroq o‘rnatish",
"📺 Texnika o‘rnatish",
"🧱 Qurilish",
"🎨 Bo‘yoq ishlari",
"🪟 Eshik deraza",
"🔨 Payvandlash",
"🏠 Usta chaqirish",
"🧹 Tozalash",
"❄ Konditsioner",
"📡 Internet",
"🔧 Boshqa xizmat",
"🛠 Maxsus xizmat"

]




# ==========================
# MENULAR
# ==========================


def client_menu():

    return ReplyKeyboardMarkup(

        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["📞 Телефон"],
            ["🔁 Қайта буюртма"]
        ],

        resize_keyboard=True
    )





def service_menu():

    return ReplyKeyboardMarkup(

        [[x] for x in SERVICES],

        resize_keyboard=True
    )





def admin_menu():

    return ReplyKeyboardMarkup(

        [
            ["🆕 Янги буюртма"],
            ["👤 Мижоз базаси"],
            ["👨‍🔧 Усталар"],
            ["📊 Тўлиқ статистика"],
            ["👨‍🔧 Уста статистикаси"],
            ["📢 Хабар тарқатиш"],
            ["📈 Ҳисобот"],
            ["👑 Админ"]
        ],

        resize_keyboard=True
    )






# ==========================
# START
# ==========================


async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):

    user = update.effective_user


    await update.message.reply_text(

        f"👋 Ассалому алайкум {user.first_name}\n\n"
        "🏠 USTA 24\n"
        "Хизмат танланг:",

        reply_markup=client_menu()

    )






# ==========================
# BUYURTMA BOSHLASH
# ==========================


async def new_order(update,context):


    uid = update.effective_user.id


    user_state[uid] = {

        "step":"name",
        "name":"",
        "phone":"",
        "service":"",
        "address":"",
        "description":""

    }


    await update.message.reply_text(

        "📝 Буюртма бериш\n\n"
        "👤 Исмингизни ёзинг"

)
    
# =====================================================
# USTA 24 BOT
# MAIN.PY 2/2
# =====================================================


# ==========================
# MIJOZ MESSAGE
# ==========================

async def message_handler(update, context):

    if not update.message:
        return


    user = update.effective_user
    text = update.message.text or ""

    uid = user.id



    if text == "📝 Буюртма бериш":

        await new_order(update, context)
        return



    if uid not in user_state:

        return



    data = user_state[uid]
    step = data["step"]



    if step == "name":

        data["name"] = text
        data["step"] = "phone"


        button = KeyboardButton(
            "📞 Телефон юбориш",
            request_contact=True
        )


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг",

            reply_markup=ReplyKeyboardMarkup(
                [[button]],
                resize_keyboard=True
            )

        )



    elif step == "phone":


        if update.message.contact:

            data["phone"] = update.message.contact.phone_number

        else:

            data["phone"] = text


        data["step"]="service"


        await update.message.reply_text(

            "🛠 Хизмат танланг",

            reply_markup=service_menu()

        )




    elif step == "service":


        data["service"]=text
        data["step"]="address"


        button = KeyboardButton(
            "📍 Геолокация",
            request_location=True
        )


        await update.message.reply_text(

            "📍 Манзил юборинг",

            reply_markup=ReplyKeyboardMarkup(

                [
                    [button],
                    ["Манзил ёзиш"]
                ],

                resize_keyboard=True

            )

        )




    elif step == "address":


        if update.message.location:

            data["address"] = (
                f"{update.message.location.latitude},"
                f"{update.message.location.longitude}"
            )

        else:

            data["address"]=text



        data["step"]="description"


        await update.message.reply_text(

            "📝 Изоҳ ёзинг"

        )




    elif step == "description":


        data["description"]=text


        await create_order(
            update,
            context,
            data
        )


        user_state.pop(uid)






# ==========================
# CREATE ORDER
# ==========================


async def create_order(update,context,data):

    global order_id


    order_id += 1

    oid = order_id



    orders[oid]={

        "id":oid,
        "customer_id":update.effective_user.id,
        "name":data["name"],
        "phone":data["phone"],
        "service":data["service"],
        "address":data["address"],
        "description":data["description"],
        "status":"new",
        "master":None,
        "master_id":None,
        "created":datetime.now()

    }



    keyboard = InlineKeyboardMarkup(

        [

            [

                InlineKeyboardButton(

                    "✅ Қабул қилиш",

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



    text=(

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{oid}\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}\n"
        f"🛠 {data['service']}\n"
        f"📍 {data['address']}\n"
        f"📝 {data['description']}"

    )



    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=text,

        reply_markup=keyboard

    )



    await update.message.reply_text(

        f"✅ Буюртма қабул қилинди\n"
        f"🔢 №{oid}",

        reply_markup=client_menu()

    )






# ==========================
# USTA BUTTONS
# ==========================


async def order_callback(update,context):

    query = update.callback_query

    await query.answer()


    data=query.data



    if data.startswith("accept_"):


        oid=int(data.split("_")[1])

        order=orders.get(oid)


        if not order:
            return


        user=query.from_user


        master = (
            f"@{user.username}"
            if user.username
            else user.first_name
        )


        order["status"]="accepted"

        order["master"]=master

        order["master_id"]=user.id



        keyboard=InlineKeyboardMarkup(

            [

                [

                    InlineKeyboardButton(

                        "🔵 Иш бошлаш",

                        callback_data=f"start_{oid}"

                    )

                ]

            ]

        )



        await query.edit_message_text(

            f"🟡 ҚАБУЛ ҚИЛИНДИ\n\n"
            f"№{oid}\n"
            f"👨‍🔧 {master}",

            reply_markup=keyboard

        )



        await context.bot.send_message(

            order["customer_id"],

            f"🟡 №{oid} қабул қилинди\n"
            f"👨‍🔧 Уста: {master}"

        )




    elif data.startswith("start_"):


        oid=int(data.split("_")[1])


        orders[oid]["status"]="process"


        await query.edit_message_text(

            f"🔵 №{oid} иш жараёнида",

            reply_markup=InlineKeyboardMarkup(

                [[

                    InlineKeyboardButton(

                        "✅ Якунлаш",

                        callback_data=f"done_{oid}"

                    )

                ]]

            )

        )





    elif data.startswith("done_"):


        oid=int(data.split("_")[1])


        orders[oid]["status"]="done"


        await query.edit_message_text(

            f"✅ №{oid} якунланди"

        )





    elif data.startswith("reject_"):


        oid=int(data.split("_")[1])


        orders[oid]["status"]="reject"


        await query.edit_message_text(

            f"🚫 №{oid} рад этилди"

        )






# ==========================
# STATISTIKA
# ==========================


async def statistics(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    text="📊 USTA 24\n\n"


    text+=f"Жами: {len(orders)}\n"


    await update.message.reply_text(text)






# ==========================
# BOT START
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

        CallbackQueryHandler(
            order_callback
        )

    )


    application.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION |
            filters.TEXT,

            message_handler

        )

    )



    application.run_polling()





if __name__=="__main__":


    Thread(
        target=run_flask,
        daemon=True
    ).start()


    main()
