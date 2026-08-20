# =====================================================
# USTA 24 BOT
# MAIN.PY
# 1-QISM
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


# =========================
# CONFIG
# =========================

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



# =========================
# FLASK
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 ISHLAAYAPTI"



@app.route("/health")
def health():
    return "OK"



def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT",10000))
    )



# =========================
# DATABASE
# =========================

users = {}

orders = {}

masters = {}

reviews = {}

prices = {}

order_id = 0




# =========================
# XIZMATLAR
# =========================

SERVICES = [

"🪑 Mebel yig‘ish",
"🪑 Mebel ta’mirlash",
"🍽 Oshxona mebeli",
"🚪 Shkaf kupe",
"🛏 Krovat",
"🪑 Stol stul",
"📦 Mebel ko‘chirish",
"🚚 Uy ko‘chirish",
"🚛 Yuk tashish",
"🔩 Santexnika",
"⚡ Elektr",
"🔥 Isitish",
"🎨 Bo‘yoq",
"🪟 Eshik deraza",
"❄ Konditsioner",
"📡 Internet",
"🧹 Tozalash",
"🔨 Payvandlash",
"🏠 Usta chaqirish",
"🔧 Boshqa xizmat"

]



# =========================
# MENULAR
# =========================

def client_menu():

    return ReplyKeyboardMarkup(

        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["🔁 Қайта буюртма"]
        ],

        resize_keyboard=True
    )



def service_menu():

    return ReplyKeyboardMarkup(

        [[x] for x in SERVICES],

        resize_keyboard=True
    )



# =========================
# START
# =========================

async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "🏠 USTA 24\n\n"
        "Хизмат танланг:",

        reply_markup=client_menu()

    )



# =========================
# BUYURTMA BOSHLASH
# =========================

async def new_order(update,context):

    uid = update.effective_user.id


    users[uid] = {

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



# =========================
# MESSAGE
# =========================

async def message_handler(update,context):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""



    if text == "📝 Буюртма бериш":

        await new_order(update,context)

        return



    if uid not in users:
        return



    data = users[uid]


    if data["step"]=="name":


        data["name"]=text

        data["step"]="phone"



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


        return



    if data["step"]=="phone":


        if update.message.contact:

            data["phone"] = update.message.contact.phone_number

        else:

            data["phone"]=text



        data["step"]="service"



        await update.message.reply_text(

            "🛠 Хизмат танланг",

            reply_markup=service_menu()

        )


        return



    if data["step"]=="service":


        data["service"]=text

        data["step"]="address"


        button = KeyboardButton(

            "📍 Геолокация",

            request_location=True

        )


        await update.message.reply_text(

            "📍 Манзил юборинг",

            reply_markup=ReplyKeyboardMarkup(

                [[button],
                 ["Манзил ёзиш"]],

                resize_keyboard=True

            )

        )


        return
# =========================
# ADDRESS + CREATE ORDER
# 2-QISM BOSHI
# =========================


async def continue_order(update,context):

    uid = update.effective_user.id

    data = users[uid]

    if data["step"]=="address":


        if update.message.location:

            data["address"] = (
                f"{update.message.location.latitude},"
                f"{update.message.location.longitude}"
            )

        else:

            data["address"] = update.message.text



        data["step"]="description"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг"

        )


        return



    if data["step"]=="description":


        data["description"]=update.message.text


        await create_order(

            update,
            context,
            data

        )


        users.pop(uid,None)





# =========================
# CREATE ORDER
# =========================


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

        f"👤 Мижоз: {data['name']}\n"

        f"📞 Телефон: {data['phone']}\n"

        f"🛠 Хизмат: {data['service']}\n"

        f"📍 Манзил: {data['address']}\n"

        f"📝 Изоҳ: {data['description']}"

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
# =========================
# USTA CALLBACK
# 3-QISM
# =========================


async def order_callback(update,context):

    query = update.callback_query

    await query.answer()


    data = query.data




    # =====================
    # QABUL QILISH
    # =====================


    if data.startswith("accept_"):


        oid = int(data.split("_")[1])


        order = orders.get(oid)


        if not order:

            return



        user = query.from_user


        master = (

            f"@{user.username}"

            if user.username

            else user.first_name

        )



        order["status"]="accepted"

        order["master"]=master

        order["master_id"]=user.id





        keyboard = InlineKeyboardMarkup(

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

            "🟡 ҚАБУЛ ҚИЛИНДИ\n\n"

            f"🔢 №{oid}\n"

            f"👨‍🔧 Уста: {master}",

            reply_markup=keyboard

        )




        await context.bot.send_message(

            order["customer_id"],

            "🟡 Буюртмангиз қабул қилинди\n\n"

            f"👨‍🔧 Уста: {master}"

        )






    # =====================
    # ISH BOSHLASH
    # =====================


    elif data.startswith("start_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="process"



            await query.edit_message_text(

                f"🔵 №{oid} иш жараёнида",

                reply_markup=InlineKeyboardMarkup(

                    [

                        [

                            InlineKeyboardButton(

                                "✅ Якунлаш",

                                callback_data=f"done_{oid}"

                            )

                        ]

                    ]

                )

            )



            await context.bot.send_message(

                orders[oid]["customer_id"],

                f"🔵 №{oid} иш бошланди"

            )






    # =====================
    # YAKUNLASH
    # =====================


    elif data.startswith("done_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="done"



            await query.edit_message_text(

                f"✅ №{oid} якунланди"

            )



            await context.bot.send_message(

                orders[oid]["customer_id"],

                f"✅ №{oid} буюртма якунланди"

            )







    # =====================
    # RAD ETISH
    # =====================


    elif data.startswith("reject_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="reject"



            await query.edit_message_text(

                f"🚫 №{oid} рад этилди"

            )






    # =====================
    # BEKOR QILISH
    # =====================


    elif data.startswith("cancel_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="cancel"



            await query.edit_message_text(

                f"❌ №{oid} бекор қилинди"

            )



            await context.bot.send_message(

                orders[oid]["customer_id"],

                f"❌ №{oid} буюртма бекор қилинди"

            )
    # =====================================================
# ADMIN PANEL + STATISTIKA
# 4-QISM
# =====================================================


async def admin(update,context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз"
        )
        return


    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL",

        reply_markup=ReplyKeyboardMarkup(

            [
                ["📊 Статистика"],
                ["👤 Мижозлар"],
                ["👨‍🔧 Усталар"],
                ["📢 Хабар"]
            ],

            resize_keyboard=True

        )

    )





# =========================
# USTA QO'SHISH
# =========================


async def add_master(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    text = update.message.text.split("|")


    try:

        mid=int(text[0])

        masters[mid]={

            "name":text[1],

            "phone":text[2]

        }


        await update.message.reply_text(

            "✅ Уста қўшилди"

        )


    except:

        await update.message.reply_text(

            "Формат:\nID | Исм | Телефон"

        )






# =========================
# MIJOZLAR
# =========================


async def customers(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    text="👤 МИЖОЗЛАР\n\n"


    for o in orders.values():

        text+=(
            f"👤 {o['name']}\n"
            f"📞 {o['phone']}\n"
            "────────\n"
        )


    await update.message.reply_text(text)







# =========================
# STATISTIKA
# =========================


async def statistics(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    total=len(orders)

    done=0

    process=0


    for o in orders.values():

        if o["status"]=="done":
            done+=1

        if o["status"]=="process":
            process+=1



    await update.message.reply_text(

        "📊 USTA 24\n\n"

        f"📋 Жами: {total}\n"
        f"🔵 Ишда: {process}\n"
        f"✅ Якунланган: {done}"

    )







# =========================
# XABAR TARQATISH
# =========================


async def broadcast(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    msg=" ".join(context.args)


    for o in orders.values():

        try:

            await context.bot.send_message(

                o["customer_id"],

                msg

            )

        except:

            pass



    await update.message.reply_text(

        "📢 Хабар юборилди"

    )







# =========================
# MAIN
# =========================


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
