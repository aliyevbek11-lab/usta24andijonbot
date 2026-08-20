# =====================================================
# USTA 24 PRO BOT
# MAIN.PY 1/4
# Мижоз + Буюртма ядроси
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
# СОЗЛАНМАЛАР
# =====================================================

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


logger = logging.getLogger("USTA24")



# =====================================================
# RENDER FLASK
# =====================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "USTA 24 PRO ишлаяпти"


@app.route("/health")
def health():
    return "OK"



def run_flask():

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT",10000))
    )





# =====================================================
# ВАҚТИНЧА БАЗА
# =====================================================

users = {}

orders = {}

masters = {}

reviews = {}

prices = {}


order_id = 0





# =====================================================
# ХИЗМАТЛАР
# =====================================================

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





# =====================================================
# МЕНЮЛАР
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

        [[x] for x in SERVICES],

        resize_keyboard=True

    )





# =====================================================
# START
# =====================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):


    user = update.effective_user


    await update.message.reply_text(

        f"👋 Ассалому алайкум {user.first_name}\n\n"

        "🏠 USTA 24 хизматлари\n\n"

        "Керакли бўлимни танланг:",

        reply_markup=client_menu()

    )






# =====================================================
# БУЮРТМА БОШЛАШ
# =====================================================


async def new_order(update, context):


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


# =====================================================
# MIJOZ BUYURTMA DAVOMI
# MAIN.PY 2/4
# =====================================================



async def client_message(update, context):

    if not update.message:
        return


    uid = update.effective_user.id

    text = update.message.text or ""


    # Буюртма бошлаш

    if text == "📝 Буюртма бериш":

        await new_order(update, context)

        return



    if uid not in users:

        return



    data = users[uid]



    # ==========================
    # ИСМ
    # ==========================

    if data["қадам"] == "исм":


        data["исм"] = text

        data["қадам"] = "телефон"



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





    # ==========================
    # ТЕЛЕФОН
    # ==========================

    if data["қадам"] == "телефон":


        if update.message.contact:

            data["телефон"] = update.message.contact.phone_number

        else:

            data["телефон"] = text



        data["қадам"] = "хизмат"



        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=service_menu()

        )


        return





    # ==========================
    # ХИЗМАТ
    # ==========================

    if data["қадам"] == "хизмат":


        data["хизмат"] = text

        data["қадам"] = "манзил"



        location_button = KeyboardButton(

            "📍 Геолокация юбориш",

            request_location=True

        )



        await update.message.reply_text(

            "📍 Манзилни юборинг:",

            reply_markup=ReplyKeyboardMarkup(

                [

                    [location_button],

                    ["✍️ Манзилни ёзиш"]

                ],

                resize_keyboard=True

            )

        )


        return






    # ==========================
    # МАНЗИЛ
    # ==========================

    if data["қадам"] == "манзил":


        if update.message.location:


            data["манзил"] = (

                f"{update.message.location.latitude},"

                f"{update.message.location.longitude}"

            )

        else:

            data["манзил"] = text



        data["қадам"] = "изоҳ"



        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг:"

        )


        return






    # ==========================
    # ИЗОҲ
    # ==========================

    if data["қадам"] == "изоҳ":


        data["изоҳ"] = text



        await create_order(

            update,

            context,

            data

        )


        users.pop(uid, None)


        return






# =====================================================
# БУЮРТМА ЯРАТИШ
# =====================================================


async def create_order(update, context, data):

    global order_id


    order_id += 1


    oid = order_id



    orders[oid] = {


        "id": oid,


        "мижоз": update.effective_user.id,


        "исм": data["исм"],


        "телефон": data["телефон"],


        "хизмат": data["хизмат"],


        "манзил": data["манзил"],


        "изоҳ": data["изоҳ"],


        "ҳолат": "янги",


        "уста": None,


        "вақт": datetime.now()

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





    message = (

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 Буюртма №{oid}\n\n"

        f"👤 Мижоз: {data['исм']}\n"

        f"📞 Телефон: {data['телефон']}\n"

        f"🛠 Хизмат: {data['хизмат']}\n"

        f"📍 Манзил: {data['манзил']}\n"

        f"📝 Изоҳ: {data['изоҳ']}\n\n"

        "👨‍🔧 Уста қабул қилиши мумкин"

    )





    await context.bot.send_message(

        chat_id=MASTERS_GROUP_ID,

        text=message,

        reply_markup=keyboard

    )





    await update.message.reply_text(

        "✅ Буюртмангиз қабул қилинди\n\n"

        f"🔢 Буюртма №{oid}\n\n"

        "👨‍🔧 Уста тез орада боғланади.\n\n"

        "☎️ USTA 24\n"

        "+998 77 069 00 03",

        reply_markup=client_menu()

        )

# =====================================================
# USTA TIZIMI
# MAIN.PY 3/4
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



        order["ҳолат"] = "қабул қилинган"

        order["уста"] = master

        order["уста_id"] = user.id




        await query.edit_message_text(

            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"

            f"🔢 №{oid}\n"

            f"👤 Мижоз: {order['исм']}\n"

            f"📞 Телефон: {order['телефон']}\n"

            f"🛠 Хизмат: {order['хизмат']}\n"

            f"📍 Манзил: {order['манзил']}\n\n"

            f"👨‍🔧 Уста: {master}"

        )





        await context.bot.send_message(

            chat_id=order["мижоз"],


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


        order["ҳолат"] = "рад этилган"



        await query.edit_message_text(

            f"🚫 №{oid} буюртма рад этилди"

        )



        await context.bot.send_message(

            order["мижоз"],


            f"🚫 №{oid} буюртма рад этилди.\n\n"

            "☎️ USTA 24\n"

            "+998 77 069 00 03"

        )








    # ==========================
    # ИШ БОШЛАШ
    # ==========================


    elif action == "start":


        order["ҳолат"] = "иш жараёнида"



        await query.edit_message_text(

            f"🔵 №{oid} иш жараёнида"

        )



        await context.bot.send_message(

            order["мижоз"],


            f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"

            "☎️ USTA 24\n"

            "+998 77 069 00 03"

        )







    # ==========================
    # ЯКУНЛАШ
    # ==========================


    elif action == "done":


        order["ҳолат"] = "якунланган"



        await query.edit_message_text(

            f"✅ №{oid} буюртма якунланди"

        )



        await context.bot.send_message(

            order["мижоз"],


            f"✅ №{oid} буюртма якунланди.\n\n"

            "⭐ Устага баҳо беринг.\n\n"

            "☎️ USTA 24\n"

            "+998 77 069 00 03"

        )








    # ==========================
    # БЕКОР ҚИЛИШ
    # ==========================


    elif action == "cancel":


        order["ҳолат"] = "бекор қилинган"



        await query.edit_message_text(

            f"❌ №{oid} бекор қилинди"

        )



        await context.bot.send_message(

            order["мижоз"],


            f"❌ №{oid} буюртма бекор қилинди.\n\n"

            "☎️ USTA 24\n"

            "+998 77 069 00 03"

        )


# =====================================================
# ADMIN TIZIMI
# MAIN.PY 4/4
# =====================================================


async def admin_panel(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    await update.message.reply_text(

        "👑 USTA 24 АДМИН\n\n"

        "/stat - 📊 Статистика\n"
        "/mijoz - 👤 Мижозлар\n"
        "/ustalar - 👨‍🔧 Усталар\n"
        "/hisobot - 📈 Ҳисобот\n"
        "/excel - 📥 Excel маълумот\n"

    )




# ==========================
# МИЖОЗ БАЗАСИ
# ==========================


async def mijozlar(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"


    seen=set()


    for order in orders.values():

        uid=order["мижоз"]


        if uid not in seen:

            seen.add(uid)


            text += (

                f"👤 {order['исм']}\n"

                f"📞 {order['телефон']}\n"

                "──────────\n"

            )


    await update.message.reply_text(text)





# ==========================
# УСТАЛАР
# ==========================


async def add_master(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    try:

        data=update.message.text.split("|")


        mid=int(data[0])

        name=data[1]

        phone=data[2]


        masters[mid]={

            "исм":name,

            "телефон":phone,

            "буюртма":0

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






async def ustalar(update,context):


    text="👨‍🔧 УСТАЛАР\n\n"



    for mid,m in masters.items():

        text += (

            f"🆔 {mid}\n"

            f"👨‍🔧 {m['исм']}\n"

            f"📞 {m['телефон']}\n"

            "────────\n"

        )


    await update.message.reply_text(text)






# ==========================
# СТАТИСТИКА
# ==========================


async def statistics(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    yangi=0
    qabul=0
    ish=0
    done=0



    for o in orders.values():

        if o["ҳолат"]=="янги":
            yangi+=1

        elif o["ҳолат"]=="қабул қилинган":
            qabul+=1

        elif o["ҳолат"]=="иш жараёнида":
            ish+=1

        elif o["ҳолат"]=="якунланган":
            done+=1



    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"🆕 Янги: {yangi}\n"

        f"🟡 Қабул қилинган: {qabul}\n"

        f"🔵 Ишда: {ish}\n"

        f"✅ Якунланган: {done}"

    )





# ==========================
# РЕЙТИНГ
# ==========================


async def rating(update,context):


    await update.message.reply_text(

        "⭐ Устага баҳо беринг\n"

        "1 дан 5 гача рақам ёзинг"

    )


    reviews[update.effective_user.id]={

        "active":True

    }







# ==========================
# ХАБАР ТАРҚАТИШ
# ==========================


async def send_all(update,context):


    if update.effective_user.id != ADMIN_ID:
        return


    msg=" ".join(context.args)


    if not msg:
        return



    users_list=set()


    for o in orders.values():

        users_list.add(o["мижоз"])



    count=0


    for uid in users_list:

        try:

            await context.bot.send_message(

                uid,

                msg

            )

            count+=1


        except:

            pass



    await update.message.reply_text(

        f"📢 Хабар юборилди\n"

        f"👥 {count}"

    )






# ==========================
# EXCEL УЧУН
# ==========================


async def excel(update,context):


    if update.effective_user.id != ADMIN_ID:
        return



    text="№ | Мижоз | Телефон | Хизмат\n\n"



    for oid,o in orders.items():

        text += (

            f"{oid} | "

            f"{o['исм']} | "

            f"{o['телефон']} | "

            f"{o['хизмат']}\n"

        )



    await update.message.reply_text(

        "📥 Excel учун маълумот:\n\n"

        + text[:3500]

    )







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

        CommandHandler(
            "admin",
            admin_panel
        )

    )


    application.add_handler(

        CommandHandler(
            "stat",
            statistics
        )

    )


    application.add_handler(

        CommandHandler(
            "mijoz",
            mijozlar
        )

    )


    application.add_handler(

        CommandHandler(
            "ustalar",
            ustalar
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

            client_message

        )

    )



    Thread(

        target=run_flask,

        daemon=True

    ).start()



    application.run_polling()






if __name__=="__main__":

    main()

    )
