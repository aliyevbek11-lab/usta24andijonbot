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
# USTA 24 BOT
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

logger = logging.getLogger("USTA24")



# =====================================================
# FLASK RENDER
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
        port=int(os.getenv("PORT",5000))
    )



# =====================================================
# XIZMATLAR 25 TA
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
"⚡ Elektr ishlari",
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
"🔧 Бошқа хизмат",
"🛠 Махсус хизмат"

]



# =====================================================
# DATABASE
# =====================================================


users = {}

orders = {}

masters = {}

reviews = {}

user_state = {}


order_id = 0



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

    return ReplyKeyboardMarkup(
        [[x] for x in SERVICES],
        resize_keyboard=True
    )



def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["📊 Статистика"],
            ["👤 Мижоз базаси"],
            ["👨‍🔧 Усталар"],
            ["📢 Хабар тарқатиш"],
            ["👑 Админ"]
        ],
        resize_keyboard=True
    )



# =====================================================
# START
# =====================================================


async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):

    user = update.effective_user


    users[user.id] = {

        "name": user.first_name

    }


    await update.message.reply_text(

        f"👋 Ассалому алайкум {user.first_name}\n\n"
        "🏠 USTA 24\n"
        "Хизмат танланг:",

        reply_markup=client_menu()

    )


# =====================================================
# MIJOZ BUYURTMA TIZIMI
# 2-QISM
# =====================================================


async def start_order(update, context):

    user = update.effective_user


    user_state[user.id] = {

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



async def message_handler(update, context):

    if not update.message:
        return


    user = update.effective_user

    text = update.message.text or ""


    # Буюртма бошлаш

    if text == "📝 Буюртма бериш":

        await start_order(update,context)

        return



    if user.id not in user_state:
        return



    data = user_state[user.id]
    step = data["step"]



    # ИСМ

    if step=="name":


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



    # ТЕЛЕФОН

    elif step=="phone":


        if update.message.contact:

            data["phone"] = update.message.contact.phone_number

        else:

            data["phone"] = text



        data["step"]="service"



        await update.message.reply_text(

            "🛠 Хизмат танланг",

            reply_markup=service_menu()

        )



    # ХИЗМАТ

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

                [[button]],

                resize_keyboard=True

            )

        )



    # МАНЗИЛ

    elif step=="address":


        if update.message.location:

            data["address"] = (

                str(update.message.location.latitude)
                +
                ","
                +
                str(update.message.location.longitude)

            )

        else:

            data["address"]=text



        data["step"]="description"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг"

        )



    # ИЗОҲ

    elif step=="description":


        data["description"]=text


        await create_order(

            update,

            context,

            data

        )



        user_state.pop(user.id)





async def create_order(update, context, data):

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



    text=(

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{oid}\n"
        f"👤 {data['name']}\n"
        f"📞 {data['phone']}\n"
        f"🛠 {data['service']}\n"
        f"📍 {data['address']}\n"
        f"📝 {data['description']}"

    )



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
# =====================================================
# USTA TIZIMI
# 3-QISM
# =====================================================


async def order_callback(update, context):

    query = update.callback_query

    await query.answer()


    data = query.data



    # ==========================
    # QABUL QILISH
    # ==========================


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



        await query.edit_message_text(

            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            f"🔢 №{oid}\n"
            f"👨‍🔧 Уста: {master}"

        )



        await context.bot.send_message(

            order["customer_id"],

            "🟡 Буюртмангиз қабул қилинди\n\n"

            f"👨‍🔧 Уста: {master}"

        )




    # ==========================
    # RAD ETISH
    # ==========================


    elif data.startswith("reject_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="reject"



            await query.edit_message_text(

                "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"

                f"№{oid}"

            )





    # ==========================
    # ISH BOSHLASH
    # ==========================


    elif data.startswith("start_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="process"



            await query.edit_message_text(

                "🔵 ИШ ЖАРАЁНИДА\n\n"

                f"№{oid}"

            )



            await context.bot.send_message(

                orders[oid]["customer_id"],

                f"🔵 №{oid} иш бошланди"

            )





    # ==========================
    # YAKUNLASH
    # ==========================


    elif data.startswith("done_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="done"



            await query.edit_message_text(

                "✅ ЯКУНЛАНДИ\n\n"

                f"№{oid}"

            )


            await context.bot.send_message(

                orders[oid]["customer_id"],

                f"✅ №{oid} буюртма якунланди\n"
                "⭐ Устага баҳо беринг"

            )





    # ==========================
    # BEKOR QILISH
    # ==========================


    elif data.startswith("cancel_"):


        oid=int(data.split("_")[1])


        if oid in orders:


            orders[oid]["status"]="cancel"



            await query.edit_message_text(

                "❌ БЕКОР ҚИЛИНДИ\n\n"

                f"№{oid}"

            )
# =====================================================
# ADMIN BOSHQARUVI
# 4-QISM
# =====================================================


async def admin_panel(update, context):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз"
        )

        return



    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL",

        reply_markup=admin_menu()

    )





# ==========================
# USTA QO'SHISH
# ==========================


async def add_master(update, context):


    if update.effective_user.id != ADMIN_ID:
        return



    await update.message.reply_text(

        "👨‍🔧 Уста қўшиш\n\n"
        "Формат:\n"
        "ID | Исм | Телефон"

    )





async def save_master(update, context):


    if update.effective_user.id != ADMIN_ID:
        return



    try:

        data = update.message.text.split("|")


        mid = int(data[0].strip())


        masters[mid] = {

            "id":mid,

            "name":data[1].strip(),

            "phone":data[2].strip()

        }



        await update.message.reply_text(

            "✅ Уста қўшилди\n\n"

            f"👨‍🔧 {masters[mid]['name']}"

        )



    except:


        await update.message.reply_text(

            "❌ Формат хато\n"
            "ID | Исм | Телефон"

        )







# ==========================
# USTALAR RO'YXATI
# ==========================


async def masters_list(update, context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="👨‍🔧 УСТАЛАР\n\n"



    if not masters:

        text+="Уста йўқ"


    else:

        for m in masters.values():

            text += (

                f"🆔 {m['id']}\n"
                f"👨‍🔧 {m['name']}\n"
                f"📞 {m['phone']}\n"
                "────────\n"

            )



    await update.message.reply_text(text)







# ==========================
# USTA O'CHIRISH
# ==========================


async def delete_master(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    try:

        mid=int(update.message.text)



        if mid in masters:


            masters.pop(mid)


            await update.message.reply_text(

                "✅ Уста ўчирилди"

            )


        else:


            await update.message.reply_text(

                "❌ Уста топилмади"

            )


    except:

        pass







# ==========================
# STATISTIKA
# ==========================


async def statistics(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    total=len(orders)

    done=0

    process=0

    cancel=0



    for o in orders.values():


        if o["status"]=="done":

            done+=1


        elif o["status"]=="process":

            process+=1


        elif o["status"]=="cancel":

            cancel+=1





    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n"
        f"🔵 Ишда: {process}\n"
        f"✅ Тайёр: {done}\n"
        f"❌ Бекор: {cancel}"

    )






# ==========================
# MIJOZ BAZASI
# ==========================


async def customer_base(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="👤 МИЖОЗЛАР БАЗАСИ\n\n"



    seen=set()



    for o in orders.values():


        if o["customer_id"] not in seen:


            seen.add(o["customer_id"])


            text += (

                f"👤 {o['name']}\n"
                f"📞 {o['phone']}\n"
                "────────\n"

            )



    await update.message.reply_text(text)
# =====================================================
# HISOBOT + REYTING + START
# 5-QISM
# =====================================================


prices = {}



# ==========================
# XABAR TARQATISH
# ==========================


async def broadcast(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    msg=" ".join(context.args)


    if not msg:

        await update.message.reply_text(

            "📢 Хабар ёзинг:\n"
            "/send матн"

        )

        return



    sent=0


    for o in orders.values():

        try:

            await context.bot.send_message(

                o["customer_id"],

                msg

            )

            sent+=1


        except:

            pass



    await update.message.reply_text(

        f"📢 Хабар юборилди\n"
        f"👥 {sent} та"

    )






# ==========================
# NARX ASOSI
# ==========================


async def set_price(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    try:

        data=update.message.text.split("|")


        service=data[0].strip()

        price=data[1].strip()



        prices[service]=price



        await update.message.reply_text(

            "✅ Нарх сақланди\n\n"

            f"🛠 {service}\n"
            f"💰 {price}"

        )


    except:


        await update.message.reply_text(

            "Формат:\n"
            "Хизмат | Нарх"

        )






# ==========================
# REYTING
# ==========================


async def rating(update,context):


    await update.message.reply_text(

        "⭐ Устага баҳо беринг\n"
        "1 дан 5 гача рақам ёзинг"

    )



    user_state[update.effective_user.id]={

        "rating":True

    }





async def save_rating(update,context):


    uid=update.effective_user.id


    if uid in user_state:


        reviews[uid]=update.message.text


        user_state.pop(uid)


        await update.message.reply_text(

            "⭐ Раҳмат! Баҳонгиз сақланди"

        )






# ==========================
# HISOBOT
# ==========================


async def report(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    total=len(orders)


    done=0

    accepted=0



    for o in orders.values():


        if o["status"]=="done":

            done+=1


        if o["status"]=="accepted":

            accepted+=1





    await update.message.reply_text(

        "📈 USTA 24 ҲИСОБОТИ\n\n"

        f"📋 Жами: {total}\n"
        f"🟡 Қабул қилинган: {accepted}\n"
        f"✅ Якунланган: {done}"

    )







# ==========================
# EXCEL UCHUN ASOS
# ==========================


async def excel_export(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="№ | Мижоз | Телефон | Хизмат\n\n"



    for oid,o in orders.items():


        text += (

            f"{oid} | "
            f"{o['name']} | "
            f"{o['phone']} | "
            f"{o['service']}\n"

        )



    await update.message.reply_text(

        text[:4000]

    )







# ==========================
# BOT ISHGA TUSHIRISH
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
            admin_panel
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
