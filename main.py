
# =====================================================
# USTA 24 PRO BOT
# MAIN.PY 1/5
# MIJOZ + USTA + ADMIN
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
        port=int(os.getenv("PORT",10000))
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

"❄ Кондиционер",

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

            ["🔁 Қайта буюртма"]

        ],

        resize_keyboard=True

    )





def service_menu():


    return ReplyKeyboardMarkup(

        [

            [x]

            for x in SERVICES

        ],

        resize_keyboard=True

    )







# =====================================================
# START
# =====================================================



async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):


    user = update.effective_user



    await update.message.reply_text(

        f"👋 Ассалому алайкум {user.first_name}\n\n"

        "🏠 USTA 24\n\n"

        "Хизмат танланг:",

        reply_markup=client_menu()

    )







# =====================================================
# BUYURTMA BOSHLASH
# =====================================================



async def new_order(update,context):


    uid = update.effective_user.id



    users[uid] = {


        "step":"name",

        "name":"",

        "phone":"",

        "service":"",

        "address":"",

        "comment":""


    }



    await update.message.reply_text(


        "📝 Буюртма бериш\n\n"

        "👤 Исмингизни ёзинг:"

    )

# =====================================================
# MAIN.PY 2/5
# MIJOZ BUYURTMA TIZIMI
# =====================================================



async def client_handler(update, context):


    if not update.message:
        return



    uid = update.effective_user.id


    text = update.message.text or ""




    # БУЮРТМА БОШЛАШ

    if text == "📝 Буюртма бериш":

        await new_order(update,context)

        return




    if uid not in users:

        return



    data = users[uid]



    step = data["step"]





    # =====================
    # ИСМ
    # =====================


    if step == "name":


        data["name"] = text


        data["step"] = "phone"



        button = KeyboardButton(

            "📞 Телефон рақамимни юбориш",

            request_contact=True

        )


        await update.message.reply_text(

            "📞 Телефон рақамингизни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [[button]],

                resize_keyboard=True

            )

        )


        return





    # =====================
    # ТЕЛЕФОН
    # =====================


    if step == "phone":



        if update.message.contact:


            data["phone"] = update.message.contact.phone_number


        else:


            data["phone"] = text




        data["step"] = "service"



        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=service_menu()

        )


        return






    # =====================
    # ХИЗМАТ
    # =====================


    if step == "service":


        data["service"] = text


        data["step"] = "address"



        location = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True

        )



        await update.message.reply_text(

            "📍 Манзилни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [

                    [location],

                    ["✍️ Манзилни ёзиш"]

                ],

                resize_keyboard=True

            )

        )


        return






    # =====================
    # МАНЗИЛ
    # =====================


    if step == "address":


        if update.message.location:


            data["address"] = (

                str(update.message.location.latitude)

                + ","

                + str(update.message.location.longitude)

            )


        else:


            data["address"] = text




        data["step"] = "comment"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг:"

        )


        return







    # =====================
    # ИЗОҲ
    # =====================


    if step == "comment":



        data["comment"] = text



        await send_order(

            update,

            context,

            data

        )



        users.pop(uid,None)


        return







# =====================================================
# BUYURTMA YARATISH
# =====================================================



async def send_order(update,context,data):


    global order_id


    order_id += 1


    oid = order_id



    orders[oid] = {


        "id":oid,

        "customer_id":update.effective_user.id,

        "name":data["name"],

        "phone":data["phone"],

        "service":data["service"],

        "address":data["address"],

        "comment":data["comment"],

        "status":"new",

        "master":None,

        "created":datetime.now()


    }






    keyboard = InlineKeyboardMarkup(

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






    text = (

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{oid}\n"

        f"👤 Мижоз: {data['name']}\n"

        f"📞 Телефон: {data['phone']}\n"

        f"🛠 Хизмат: {data['service']}\n"

        f"📍 Манзил: {data['address']}\n"

        f"📝 Изоҳ: {data['comment']}"

    )






    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=text,

        reply_markup=keyboard

    )






    await update.message.reply_text(

        f"✅ Буюртмангиз қабул қилинди.\n\n"

        f"🔢 Буюртма №{oid}\n\n"

        "👨‍🔧 Уста тез орада боғланади.\n\n"

        "☎️ USTA 24\n"

        "+998 77 069 00 03",

        reply_markup=client_menu()
    
    )
    
# =====================================================
# MAIN.PY 3/5
# USTA BUYURTMA BOSHQARUVI
# =====================================================


async def order_callback(update, context):

    query = update.callback_query

    await query.answer()


    data = query.data


    if "_" not in data:
        return



    action, oid = data.split("_")

    oid = int(oid)



    if oid not in orders:

        await query.answer(
            "Буюртма топилмади",
            show_alert=True
        )

        return



    order = orders[oid]





    # ==========================
    # ҚАБУЛ ҚИЛИШ
    # ==========================


    if action == "accept":


        user = query.from_user


        master = (

            f"@{user.username}"

            if user.username

            else user.first_name

        )



        order["status"] = "accepted"

        order["master"] = master

        order["master_id"] = user.id




        await query.edit_message_text(

            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            f"🔢 №{oid}\n"

            f"👨‍🔧 Уста: {master}\n\n"

            "Ишни бошлаш мумкин."

        )




        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"

                f"👨‍🔧 Уста: {master}\n\n"

                "Тез орада уста ишни бошлайди.\n\n"

                "☎️ USTA 24\n"

                "+998 77 069 00 03"

            )

        )







    # ==========================
    # РАД ЭТИШ
    # ==========================


    elif action == "reject":


        order["status"] = "reject"



        await query.edit_message_text(

            f"🚫 №{oid} буюртма рад этилди"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"🚫 №{oid} буюртма рад этилди.\n\n"

            "Бошқа уста бириктирилади."

        )








    # ==========================
    # ИШ БОШЛАШ
    # ==========================


    elif action == "start":


        order["status"] = "process"



        await query.edit_message_text(

            f"🔵 №{oid} иш жараёнида"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"🔵 №{oid} буюртма бўйича иш бошланди."

        )







    # ==========================
    # ЯКУНЛАШ
    # ==========================


    elif action == "done":


        order["status"] = "done"



        await query.edit_message_text(

            f"✅ №{oid} буюртма якунланди"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"✅ №{oid} буюртма якунланди.\n\n"

            "⭐ Устага баҳо беришингиз мумкин."

        )







    # ==========================
    # БЕКОР ҚИЛИШ
    # ==========================


    elif action == "cancel":


        order["status"] = "cancel"



        await query.edit_message_text(

            f"❌ №{oid} буюртма бекор қилинди"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"❌ №{oid} буюртма бекор қилинди."

        )

# =====================================================
# MAIN.PY 4/5
# ADMIN TIZIMI
# =====================================================



def admin_menu():


    return ReplyKeyboardMarkup(

        [

            ["👤 Мижоз базаси"],

            ["👨‍🔧 Усталар"],

            ["📊 Статистика"],

            ["📢 Хабар тарқатиш"]

        ],

        resize_keyboard=True

    )







async def admin_start(update,context):


    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз"
        )

        return



    await update.message.reply_text(

        "👑 USTA 24 АДМИН\n\n"

        "Бўлимни танланг:",

        reply_markup=admin_menu()

    )







# ==========================
# MIJOZ BAZASI
# ==========================


async def customer_base(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"



    for o in orders.values():


        text += (

            f"👤 {o['name']}\n"

            f"📞 {o['phone']}\n"

            f"🛠 {o['service']}\n"

            "────────────\n"

        )



    if len(text) < 30:

        text += "Мижозлар йўқ"



    await update.message.reply_text(text)








# ==========================
# USTALAR
# ==========================


async def masters_list(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="👨‍🔧 УСТАЛАР\n\n"



    if not masters:


        text+="Усталар қўшилмаган"



    else:


        for mid,m in masters.items():


            text += (

                f"🆔 {mid}\n"

                f"👨‍🔧 {m['name']}\n"

                f"📞 {m['phone']}\n"

                "────────\n"

            )



    await update.message.reply_text(text)







# ==========================
# USTA QO'SHISH
# ==========================


async def add_master(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    try:


        parts = update.message.text.split("|")



        mid = int(parts[0].strip())


        name = parts[1].strip()


        phone = parts[2].strip()



        masters[mid]={


            "name":name,

            "phone":phone,

            "orders":0

        }




        await update.message.reply_text(

            "✅ Уста қўшилди\n\n"

            f"👨‍🔧 {name}"

        )



    except:


        await update.message.reply_text(

            "Формат:\n"

            "ID | Исм | Телефон"

        )









# ==========================
# STATISTIKA
# ==========================


async def statistics(update,context):


    if update.effective_user.id != ADMIN_ID:
        return




    total=len(orders)


    accepted=0

    process=0

    done=0

    cancel=0




    for o in orders.values():


        if o["status"]=="accepted":

            accepted+=1


        elif o["status"]=="process":

            process+=1


        elif o["status"]=="done":

            done+=1


        elif o["status"]=="cancel":

            cancel+=1





    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами: {total}\n"

        f"🟡 Қабул: {accepted}\n"

        f"🔵 Ишда: {process}\n"

        f"✅ Якунланган: {done}\n"

        f"❌ Бекор: {cancel}"

    )








# ==========================
# XABAR TARQATISH
# ==========================


async def broadcast(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    msg=" ".join(context.args)



    if not msg:


        await update.message.reply_text(

            "Формат:\n/send Хабар"

        )

        return




    count=0



    for o in orders.values():


        try:


            await context.bot.send_message(

                o["customer_id"],

                msg

            )


            count+=1


        except:


            pass





    await update.message.reply_text(

        f"📢 Хабар юборилди\n"

        f"👥 {count} та мижоз"

    )  
# =====================================================
# MAIN.PY 5/5
# HANDLERS + START
# =====================================================



async def button_handler(update,context):


    text = update.message.text


    if text == "👤 Мижоз базаси":

        await customer_base(update,context)


    elif text == "👨‍🔧 Усталар":

        await masters_list(update,context)


    elif text == "📊 Статистика":

        await statistics(update,context)


    elif text == "📢 Хабар тарқатиш":

        await update.message.reply_text(

            "Хабар юбориш:\n"
            "/send матн"

        )



    else:

        await client_handler(update,context)







async def button_handler(update,context):

    if not update.message:
        return


    text = update.message.text or ""


    # АДМИН БЎЛИМЛАРИ

    if update.effective_user.id == ADMIN_ID:


        if text == "👤 Мижоз базаси":
            await customer_base(update,context)
            return


        if text == "👨‍🔧 Усталар":
            await masters_list(update,context)
            return


        if text == "📊 Статистика":
            await statistics(update,context)
            return


        if text == "📢 Хабар тарқатиш":
            await update.message.reply_text(
                "Формат:\n/send матн"
            )
            return



    # МИЖОЗ БУЮРТМАСИ

    await client_handler(update,context)


    await broadcast(update,context)







# =====================================================
# BOT ISHGA TUSHISH
# =====================================================



def main():


    application = Application.builder()\
        .token(TOKEN)\
        .build()





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



    application.add_handler(

        CommandHandler(

            "send",

            send_command

        )

    )



    # USTA BUTTON

    application.add_handler(

        CallbackQueryHandler(

            order_callback

        )

    )



    # TEXT

    application.add_handler(

        MessageHandler(

            filters.CONTACT |
            filters.LOCATION |
            filters.TEXT,

            button_handler

        )

    )





    Thread(

        target=run_flask,

        daemon=True

    ).start()




    print(
        "USTA 24 BOT ISHLADI"
    )



    application.run_polling()







if __name__ == "__main__":

    main()
