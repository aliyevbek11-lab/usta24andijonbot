# =====================================================
# USTA 24 BOT
# 1-QISM
# MIJOZ + BUYURTMA ASOSI
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


# =====================================================
# CONFIG
# =====================================================

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



# =====================================================
# FLASK RENDER
# =====================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 BOT ISHLAYAPTI"



def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT",10000))
    )



# =====================================================
# 25 TA XIZMAT
# =====================================================


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
"🧱 Qurilish ishlari",
"🎨 Bo‘yoq ishlari",
"🪟 Deraza eshik",
"🔨 Payvandlash",
"🏠 Usta chaqirish",
"🧹 Tozalash",
"❄ Konditsioner",
"📡 Internet o‘rnatish",
"🔧 Boshqa xizmat",
"🛠 Maxsus xizmat"

]



# =====================================================
# DATABASE
# =====================================================


users = {}

orders = {}

masters = {}

reviews = {}

prices = {}


order_id = 0



# =====================================================
# STATUS
# =====================================================


STATUS = {

"new":"🆕 Янги",

"accepted":"🟡 Қабул қилинган",

"process":"🔵 Иш жараёнида",

"done":"✅ Якунланган",

"cancel":"❌ Бекор қилинган",

"reject":"🚫 Рад этилган"

}




# =====================================================
# MENULAR
# =====================================================


def client_menu():

    return ReplyKeyboardMarkup(

        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["📞 Телефон"]
        ],

        resize_keyboard=True

    )





def service_menu():

    rows=[]

    for s in SERVICES:

        rows.append([s])


    return ReplyKeyboardMarkup(

        rows,

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

            ["📈 Ҳисобот"]

        ],

        resize_keyboard=True

    )





# =====================================================
# START
# =====================================================


async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):


    user=update.effective_user


    await update.message.reply_text(

        f"👋 Ассалому алайкум {user.first_name}\n\n"

        "🏠 USTA 24\n"
        "Уй хизматлари",

        reply_markup=client_menu()

    )






# =====================================================
# BUYURTMA BOSHLASH
# =====================================================


async def new_order(update,context):


    uid=update.effective_user.id


    users[uid]={

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
# 2-QISM
# BUYURTMA + USTA + ADMIN
# =====================================================


# ==========================
# BUYURTMA JARAYONI
# ==========================


async def message_handler(update, context):

    if not update.message:
        return


    user = update.effective_user
    text = update.message.text or ""


    uid = user.id



    # BUYURTMA BOSHLASH

    if text == "📝 Буюртма бериш":

        await new_order(update,context)

        return




    if uid not in users:

        return



    data = users[uid]

    step = data["step"]



    if step == "name":

        data["name"] = text

        data["step"] = "phone"


        button = KeyboardButton(
            "📞 Телефон рақамимни юбориш",
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



    elif step=="service":


        data["service"]=text

        data["step"]="address"



        button = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True

        )


        await update.message.reply_text(

            "📍 Манзил юборинг",

            reply_markup=ReplyKeyboardMarkup(

                [[button],
                 ["Манзилни ёзиш"]],

                resize_keyboard=True

            )

        )




    elif step=="address":


        if update.message.location:


            data["address"]=(
                str(update.message.location.latitude)
                + ","
                +
                str(update.message.location.longitude)
            )

        else:

            data["address"]=text



        data["step"]="description"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг"

        )





    elif step=="description":


        data["description"]=text


        await create_order(

            update,
            context,
            data

        )


        users.pop(uid,None)






# ==========================
# BUYURTMA YARATISH
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

        f"✅ Буюртма қабул қилинди\n\n"
        f"🔢 №{oid}\n"
        "👨‍🔧 Усталарга юборилди",

        reply_markup=client_menu()

    )






# ==========================
# USTA TUGMALARI
# ==========================


async def order_callback(update,context):

    query=update.callback_query

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

                ],

                [

                    InlineKeyboardButton(

                        "❌ Бекор қилиш",

                        callback_data=f"cancel_{oid}"

                    )

                ]

            ]

        )



        await query.edit_message_text(

            f"🟡 №{oid} қабул қилинди\n\n"
            f"👨‍🔧 Уста: {master}",

            reply_markup=keyboard

        )





    elif data.startswith("start_"):


        oid=int(data.split("_")[1])


        if oid in orders:

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


        if oid in orders:


            orders[oid]["status"]="done"


            await query.edit_message_text(

                f"✅ №{oid} якунланди"

            )





    elif data.startswith("reject_"):


        oid=int(data.split("_")[1])


        if oid in orders:

            orders[oid]["status"]="reject"


            await query.edit_message_text(

                f"🚫 №{oid} рад этилди"

            )






# ==========================
# BOT START
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

        CallbackQueryHandler(
            order_callback
        )

    )


    bot.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION |
            filters.TEXT,

            message_handler

        )

    )



    bot.run_polling()






if __name__=="__main__":


    Thread(
        target=run_flask,
        daemon=True
    ).start()


    main()
