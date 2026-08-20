
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


def master_keyboard(oid, status):

    buttons = []

    if status == "new":

        buttons.append([
            InlineKeyboardButton(
                "🟡 Қабул қилиш",
                callback_data=f"accept_{oid}"
            ),
            InlineKeyboardButton(
                "🚫 Рад этиш",
                callback_data=f"reject_{oid}"
            )
        ])

    elif status == "accepted":

        buttons.append([
            InlineKeyboardButton(
                "🔵 Ишни бошлаш",
                callback_data=f"start_{oid}"
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "🔄 Бошқа устага бериш",
                callback_data=f"reassign_{oid}"
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "📞 Мижоз билан боғланиш",
                callback_data=f"contact_{oid}"
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "❌ Бекор қилиш",
                callback_data=f"cancel_{oid}"
            )
        ])

    elif status == "process":

        buttons.append([
            InlineKeyboardButton(
                "✅ Ишни якунлаш",
                callback_data=f"done_{oid}"
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "📞 Мижоз билан боғланиш",
                callback_data=f"contact_{oid}"
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "❌ Бекор қилиш",
                callback_data=f"cancel_{oid}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


# =====================================================
# BUYURTMA MATNI
# =====================================================


def order_text(order):

    oid = order["id"]

    status = STATUS.get(
        order["status"],
        order["status"]
    )

    master = order.get("master")

    if not master:
        master = "Ҳали бириктирилмаган"

    return (

        "📋 БУЮРТМА\n\n"

        f"🔢 Буюртма: №{oid}\n"

        f"👤 Мижоз: {order['name']}\n"

        f"📞 Телефон: {order['phone']}\n"

        f"🛠 Хизмат: {order['service']}\n"

        f"📍 Манзил: {order['address']}\n"

        f"📝 Изоҳ: {order['comment']}\n\n"

        f"👨‍🔧 Уста: {master}\n"

        f"📌 Ҳолат: {status}"

    )


# =====================================================
# USTA CALLBACK
# =====================================================


async def order_callback(update, context):

    query = update.callback_query

    await query.answer()

    data = query.data or ""

    if "_" not in data:
        return

    try:

        action, oid_text = data.split("_", 1)

        oid = int(oid_text)

    except ValueError:

        await query.answer(
            "❌ Буюртма рақами нотўғри.",
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

    customer_id = order["customer_id"]


    # =================================================
    # ҚАБУЛ ҚИЛИШ
    # =================================================

    if action == "accept":

        if order["status"] != "new":

            await query.answer(
                "⚠️ Бу буюртма аллақачон бошқарилмоқда.",
                show_alert=True
            )

            return


        user = query.from_user

        if user.username:

            master = f"@{user.username}"

        else:

            master = user.first_name


        order["status"] = "accepted"

        order["master"] = master

        order["master_id"] = user.id


        await query.edit_message_text(

            text=(
                "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=master_keyboard(
                oid,
                "accepted"
            )
        )


        await context.bot.send_message(

            chat_id=customer_id,

            text=(

                f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"

                f"👨‍🔧 Уста: {master}\n\n"

                "Тез орада уста ишни бошлайди.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # РАД ЭТИШ
    # =================================================

    if action == "reject":

        if order["status"] != "new":

            await query.answer(
                "⚠️ Бу буюртма аллақачон қабул қилинган.",
                show_alert=True
            )

            return


        order["status"] = "reject"

        order["master"] = None


        await query.edit_message_text(

            text=(
                "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
                f"{order_text(order)}"
            )
        )


        await context.bot.send_message(

            chat_id=customer_id,

            text=(

                f"🚫 №{oid} буюртма рад этилди.\n\n"

                "Бошқа уста бириктирилади.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # ИШНИ БОШЛАШ
    # =================================================

    if action == "start":

        if order["status"] != "accepted":

            await query.answer(
                "⚠️ Аввал буюртмани қабул қилиш керак.",
                show_alert=True
            )

            return


        order["status"] = "process"


        await query.edit_message_text(

            text=(
                "🔵 ИШ ЖАРАЁНИДА\n\n"
                f"{order_text(order)}"
            ),

            reply_markup=master_keyboard(
                oid,
                "process"
            )
        )


        await context.bot.send_message(

            chat_id=customer_id,

            text=(

                f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"

                f"👨‍🔧 Уста: {order['master']}\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # МИЖОЗ БИЛАН БОҒЛАНИШ
    # =================================================

    if action == "contact":

        phone = order["phone"]

        await query.answer(
            f"📞 {phone}",
            show_alert=True
        )

        return


    # =================================================
    # БОШҚА УСТАГА БЕРИШ
    # =================================================

    if action == "reassign":

        old_master = order.get("master")

        order["status"] = "new"

        order["master"] = None

        order["master_id"] = None


        keyboard = master_keyboard(
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


        await context.bot.send_message(

            chat_id=customer_id,

            text=(

                f"🔄 №{oid} буюртмангиз бошқа устага берилди.\n\n"

                "Яқин вақтда янги уста бириктирилади.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            )
        )

        return


    # =================================================
    # ИШНИ ЯКУНЛАШ
    # =================================================

    if action == "done":

        if order["status"] != "process":

            await query.answer(
                "⚠️ Буюртма ҳозир иш жараёнида эмас.",
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


        await context.bot.send_message(

            chat_id=customer_id,

            text=(

                f"✅ №{oid} буюртмангиз якунланди.\n\n"

                f"👨‍🔧 Уста: {order['master']}\n\n"

                "⭐ Устага баҳо беришингиз мумкин.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            ),

            reply_markup=InlineKeyboardMarkup(

                [[

                    InlineKeyboardButton(
                        "⭐ Баҳо бериш",
                        callback_data=f"rate_{oid}"
                    )

                ]]

            )
        )

        return


    # =================================================
    # БЕКОР ҚИЛИШ
    # =================================================

    if action == "cancel":

        if order["status"] == "done":

            await query.answer(
                "❌ Якунланган буюртмани бекор қилиб бўлмайди.",
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

            chat_id=customer_id,

            text=(

                f"❌ №{oid} буюртма бекор қилинди.\n\n"

                "Агар яна хизмат керак бўлса, янги буюртма беришингиз мумкин.\n\n"

                "☎️ USTA 24\n"
                "+998 77 069 00 03"
            ),

            reply_markup=client_menu()
        )

        return


    # =================================================
    # БАҲО БЕРИШ
    # =================================================

    if action == "rate":

        if order["status"] != "done":

            await query.answer(
                "⚠️ Буюртма ҳали якунланмаган.",
                show_alert=True
            )

            return


        keyboard = InlineKeyboardMarkup(

            [

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

            ]

        )


        await query.message.reply_text(

            "⭐ Устага баҳо беринг:\n\n"
            "1 дан 5 гача танланг.",

            reply_markup=keyboard
        )

        return


    # =================================================
    # РЕЙТИНГ
    # =================================================

    if action == "rating":

        parts = data.split("_")

        if len(parts) != 3:

            return


        rating = int(parts[1])

        oid = int(parts[2])


        if oid not in orders:

            return


        order = orders[oid]

        customer_id = order["customer_id"]


        reviews[oid] = {

            "customer_id": customer_id,

            "master_id": order.get("master_id"),

            "rating": rating,

            "created": datetime.now()

        }


        await query.edit_message_text(

            "⭐ Раҳмат!\n\n"

            f"Сизнинг баҳонгиз: {rating}/5\n\n"

            "USTA 24 хизматидан фойдаланганингиз учун раҳмат."
        )

        return

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


# =====================================================
# SEND COMMAND
# =====================================================

async def send_command(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )
        return

    if not context.args:

        await update.message.reply_text(
            "📢 Хабар тарқатиш\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return

    message = " ".join(context.args)

    count = 0

    users_sent = set()

    for order in orders.values():

        customer_id = order.get("customer_id")

        if not customer_id:
            continue

        if customer_id in users_sent:
            continue

        users_sent.add(customer_id)

        try:

            await context.bot.send_message(
                chat_id=customer_id,
                text=message
            )

            count += 1

        except Exception as e:

            logger.warning(
                f"Хабар юборилмади {customer_id}: {e}"
            )

    await update.message.reply_text(

        "📢 Хабар тарқатиш якунланди.\n\n"

        f"👥 Юборилди: {count} та мижоз"
    )


# =====================================================
# BUTTON HANDLER
# =====================================================

async def button_handler(update, context):

    if not update.message:
        return

    text = update.message.text or ""

    user_id = update.effective_user.id


    # =================================================
    # ADMIN
    # =================================================

    if user_id == ADMIN_ID:

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


        if text == "📊 Статистика":

            await statistics(
                update,
                context
            )

            return


        if text == "📢 Хабар тарқатиш":

            await update.message.reply_text(

                "📢 Хабар тарқатиш\n\n"

                "Хабар матнини қуйидагича юборинг:\n\n"

                "/send Бугун соат 18:00 гача буюртмалар қабул қилинади."
            )

            return


    # =================================================
    # MIJOZ
    # =================================================

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


    # =================================================
    # START
    # =================================================

    application.add_handler(

        CommandHandler(
            "start",
            start
        )
    )


    # =================================================
    # ADMIN
    # =================================================

    application.add_handler(

        CommandHandler(
            "admin",
            admin_start
        )
    )


    # =================================================
    # SEND
    # =================================================

    application.add_handler(

        CommandHandler(
            "send",
            send_command
        )
    )


    # =================================================
    # INLINE BUTTONS
    # =================================================

    application.add_handler(

        CallbackQueryHandler(
            order_callback
        )
    )


    # =================================================
    # TEXT / CONTACT / LOCATION
    # =================================================

    application.add_handler(

        MessageHandler(

            filters.CONTACT
            | filters.LOCATION
            | filters.TEXT,

            button_handler
        )
    )


    # =================================================
    # FLASK
    # =================================================

    Thread(

        target=run_flask,

        daemon=True

    ).start()


    print(
        "USTA 24 BOT ISHLADI"
    )


    # =================================================
    # POLLING
    # =================================================

    application.run_polling()


# =====================================================
# START BOT
# =====================================================

if __name__ == "__main__":

    main()
