import os
import asyncio
import logging
from datetime import datetime, timedelta
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
# USTA 24 BOT
# Мижоз + Уста + Админ тизими
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
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("USTA24")


# =====================================================
# FLASK (Render uchun)
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
"⚡ Elektr ishlari",
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
# HOLATLAR
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
# ВАҚТИНЧА ХОТИРА
# =====================================================

users = {}
orders = {}
masters = {}

order_id = 0


# =====================================================
# МЕНЮЛАР
# =====================================================

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
            ["👑 Админ бошқаруви"]
        ],
        resize_keyboard=True
    )



def service_menu():

    rows=[]

    for x in SERVICES:
        rows.append([x])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True
    )



# =====================================================
# START
# =====================================================


async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user=update.effective_user

    await update.message.reply_text(
        f"👋 Ассалому алайкум {user.first_name}\n\n"
        "🏠 USTA 24 хизматлари\n\n"
        "Керакли бўлимни танланг:",
        reply_markup=client_menu()
    )


# =====================================================
# ADMIN START
# =====================================================


async def dispatcher(update,context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз"
        )
        return


    await update.message.reply_text(
        "👑 USTA 24 АДМИН",
        reply_markup=admin_menu()
    )
# =====================================================
# MIJOZ BUYURTMA TIZIMI
# 2-QISM
# =====================================================


async def start_order(update, context):

    user = update.effective_user

    users[user.id] = {
        "step": "name",
        "name": None,
        "phone": None,
        "service": None,
        "address": None,
        "description": None
    }


    await update.message.reply_text(
        "📝 Буюртма бериш\n\n"
        "1️⃣ Исмингизни ёзинг:"
    )



async def send_location_button(update, context):

    button = KeyboardButton(
        "📍 Геолокациямни юбориш",
        request_location=True
    )


    await update.message.reply_text(
        "📍 Манзилни юборинг:",
        reply_markup=ReplyKeyboardMarkup(
            [
                [button],
                ["Манзилни матн билан ёзиш"]
            ],
            resize_keyboard=True
        )
    )



async def create_order(update, context):

    global order_id


    user = update.effective_user
    data = users.get(user.id)


    order_id += 1


    orders[order_id] = {

        "id": order_id,

        "customer_id": user.id,

        "name": data["name"],

        "phone": data["phone"],

        "service": data["service"],

        "address": data["address"],

        "description": data["description"],

        "status": "new",

        "master": None,

        "created": datetime.now()

    }



    text = (

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{order_id}\n"

        f"👤 Мижоз: {data['name']}\n"

        f"📞 Телефон: {data['phone']}\n"

        f"🛠 Хизмат: {data['service']}\n"

        f"📍 Манзил: {data['address']}\n"

        f"📝 Изоҳ: {data['description']}\n"

    )



    keyboard = InlineKeyboardMarkup(

        [

            [

            InlineKeyboardButton(
                "✅ Қабул қилиш",
                callback_data=f"accept_{order_id}"
            ),

            InlineKeyboardButton(
                "🚫 Рад этиш",
                callback_data=f"reject_{order_id}"
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

        f"✅ Буюртмангиз қабул қилинди\n\n"
        f"🔢 Буюртма №{order_id}\n"
        "👨‍🔧 Уста тез орада боғланади.",

        reply_markup=client_menu()

    )


    users.pop(user.id,None)





async def client_handler(update,context):

    user = update.effective_user

    text = update.message.text or ""



    if user.id not in users:
        return



    data = users[user.id]

    step=data["step"]



    if step=="name":

        data["name"]=text

        data["step"]="phone"



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



    elif step=="phone":


        if update.message.contact:

            data["phone"] = update.message.contact.phone_number

        else:

            data["phone"] = text



        data["step"]="service"



        await update.message.reply_text(

            "🛠 Хизматни танланг:",

            reply_markup=service_menu()

        )




    elif step=="service":


        data["service"]=text

        data["step"]="address"



        await send_location_button(update,context)




    elif step=="address":


        if update.message.location:

            data["address"]=(

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

            "📝 Буюртма ҳақида ёзинг:"

        )




    elif step=="description":


        data["description"]=text

        await create_order(update,context)
# =====================================================
# USTALAR TIZIMI
# 3-QISM
# =====================================================


async def order_callback(update, context):

    query = update.callback_query
    await query.answer()

    data = query.data


    # ==========================
    # USTA QABUL QILISH
    # ==========================

    if data.startswith("accept_"):

        oid = int(data.split("_")[1])

        if oid not in orders:
            await query.answer(
                "❌ Buyurtma topilmadi",
                show_alert=True
            )
            return


        order = orders[oid]


        if order["status"] != "new":

            await query.answer(
                "⚠️ Buyurtma band qilingan",
                show_alert=True
            )
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

            "🟡 BUYURTMA QABUL QILINDI\n\n"

            f"🔢 №{oid}\n"
            f"👤 Mijoz: {order['name']}\n"
            f"📞 Telefon: {order['phone']}\n"
            f"🛠 Xizmat: {order['service']}\n"
            f"👨‍🔧 Usta: {master}\n"

        )


        await context.bot.send_message(

            chat_id=order["customer_id"],

            text=(

                f"🟡 Буюртмангиз №{oid} қабул қилинди\n\n"

                f"👨‍🔧 Уста: {master}\n"

                "Тез орада сиз билан боғланади."

            )

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

        order=orders.get(oid)


        if not order:
            return



        order["status"]="process"



        await query.edit_message_text(

            "🔵 ИШ ЖАРАЁНИДА\n\n"

            f"Буюртма №{oid}"

        )


        await context.bot.send_message(

            order["customer_id"],

            f"🔵 №{oid} буюртма бўйича иш бошланди."

        )




    # ==========================
    # YAKUNLASH
    # ==========================


    elif data.startswith("done_"):


        oid=int(data.split("_")[1])


        order=orders.get(oid)


        if not order:
            return



        order["status"]="done"



        await query.edit_message_text(

            "✅ ИШ ЯКУНЛАНДИ\n\n"

            f"№{oid}"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"✅ №{oid} буюртма якунланди.\n\n"
            "⭐ Устага баҳо беришингиз мумкин."

        )




    # ==========================
    # BEKOR QILISH
    # ==========================


    elif data.startswith("cancel_"):


        oid=int(data.split("_")[1])


        order=orders.get(oid)


        if order:

            order["status"]="cancel"



            await query.edit_message_text(

                "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"

                f"№{oid}"

            )


            await context.bot.send_message(

                order["customer_id"],

                f"❌ №{oid} буюртма бекор қилинди."

)
# =====================================================
# ADMIN BOSHQARUVI
# 4-QISM
# =====================================================


async def add_master(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    user_state = {
        "step": "add_master"
    }


    await update.message.reply_text(
        "👨‍🔧 Уста қўшиш\n\n"
        "Формат:\n"
        "ID | Исм | Телефон\n\n"
        "Масалан:\n"
        "123456789 | Али | 998901234567"
    )



async def save_master(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    try:

        parts = update.message.text.split("|")

        mid = int(parts[0].strip())

        name = parts[1].strip()

        phone = parts[2].strip()



        masters[mid] = {

            "id": mid,

            "name": name,

            "phone": phone,

            "active": True

        }



        await update.message.reply_text(

            f"✅ Уста қўшилди\n\n"
            f"👨‍🔧 {name}\n"
            f"📞 {phone}"

        )


    except:

        await update.message.reply_text(

            "❌ Формат хато\n"
            "ID | Исм | Телефон"

        )





async def masters_list(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Усталар йўқ"
        )

        return



    text="👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"


    for m in masters.values():

        text += (

            f"🆔 {m['id']}\n"
            f"👨‍🔧 {m['name']}\n"
            f"📞 {m['phone']}\n"
            "────────\n"

        )


    await update.message.reply_text(text)





async def delete_master(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    await update.message.reply_text(

        "🗑 Ўчириш учун устанинг ID рақамини ёзинг"

    )





async def remove_master(update,context):

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






# =====================================================
# STATISTIKA
# =====================================================


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

        if o["status"]=="process":
            process+=1

        if o["status"]=="cancel":
            cancel+=1



    await update.message.reply_text(

        "📊 USTA 24 СТАТИСТИКА\n\n"

        f"📋 Жами буюртма: {total}\n"
        f"🔵 Ишда: {process}\n"
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор: {cancel}"

    )







async def master_statistics(update,context):

    if update.effective_user.id != ADMIN_ID:
        return



    result="👨‍🔧 УСТА СТАТИСТИКАСИ\n\n"



    for m in masters.values():

        count=0


        for o in orders.values():

            if o.get("master_id")==m["id"]:
                count+=1



        result += (

            f"👨‍🔧 {m['name']}\n"
            f"📋 Буюртма: {count}\n\n"

        )



    await update.message.reply_text(result)





async def customer_base(update,context):

    if update.effective_user.id != ADMIN_ID:
        return



    result="👤 МИЖОЗЛАР БАЗАСИ\n\n"


    seen=set()


    for o in orders.values():

        if o["customer_id"] not in seen:

            seen.add(o["customer_id"])

            result += (

                f"👤 {o['name']}\n"
                f"📞 {o['phone']}\n"
                "────────\n"

            )


# =====================================================
# 5-QISM
# HISOBOT - REYTING - XABAR - NARX
# =====================================================


reviews = {}
prices = {
    "🪑 Mebel":0,
    "🚚 Yuk tashish":0,
    "🔩 Santexnika":0,
    "⚡ Elektr":0,
    "🔥 Payvandlash":0,
    "🔨 Boshqa":0
}


# ==============================
# NARXLAR
# ==============================

async def set_price(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    try:

        data=update.message.text.split("|")

        service=data[0].strip()

        price=int(data[1].strip())


        prices[service]=price


        await update.message.reply_text(
            f"✅ Narx saqlandi\n\n"
            f"🛠 {service}\n"
            f"💰 {price} so'm"
        )

    except:

        await update.message.reply_text(
            "Format:\n"
            "Xizmat | Narx"
        )




# ==============================
# XABAR TARQATISH
# ==============================


async def broadcast(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    msg=" ".join(context.args)


    if not msg:

        await update.message.reply_text(
            "📢 Xabar yozing:\n"
            "/send Salom mijozlar"
        )

        return



    users=set()


    for o in orders.values():

        users.add(o["customer_id"])



    count=0


    for uid in users:

        try:

            await context.bot.send_message(
                uid,
                msg
            )

            count+=1

        except:
            pass



    await update.message.reply_text(

        f"📢 Xabar yuborildi\n"
        f"👥 {count} ta mijoz"

    )





# ==============================
# HISOBOT
# ==============================


async def report(update,context):

    if update.effective_user.id != ADMIN_ID:
        return


    today=0
    week=0
    month=0


    from datetime import datetime,timedelta


    now=datetime.now()


    for o in orders.values():

        created=o.get("created")


        if created:

            diff=now-created


            if diff.days==0:
                today+=1

            if diff.days<=7:
                week+=1

            if diff.days<=30:
                month+=1



    await update.message.reply_text(

        "📈 HISOBOT\n\n"

        f"📅 Bugun: {today}\n"
        f"📅 7 kun: {week}\n"
        f"📅 30 kun: {month}"

    )





# ==============================
# REYTING
# ==============================


async def rating(update,context):


    await update.message.reply_text(

        "⭐ Ustaga baho bering\n\n"
        "1 dan 5 gacha raqam yozing"

    )


    user_state[update.effective_user.id]={
        "rating":True
    }





async def save_rating(update,context):


    uid=update.effective_user.id


    if uid in user_state and user_state[uid].get("rating"):


        reviews[uid]=update.message.text


        user_state.pop(uid)


        await update.message.reply_text(

            "⭐ Rahmat!\n"
            "Bahongiz saqlandi"

        )






# ==============================
# AVTOMATIK ESLATMA
# ==============================


async def reminder(context):


    for oid,o in orders.items():


        if o["status"]=="accepted":


            try:

                await context.bot.send_message(

                    o["customer_id"],

                    "🔔 Eslatma\n"
                    f"№{oid} buyurtma holati tekshirilmoqda"

                )

            except:
                pass




# ==============================
# EXCEL UCHUN TAYYOR
# ==============================


async def excel_export(update,context):


    if update.effective_user.id != ADMIN_ID:
        return


    text="№ | Mijoz | Telefon | Xizmat\n\n"


    for oid,o in orders.items():

        text += (

            f"{oid} | "
            f"{o['name']} | "
            f"{o['phone']} | "
            f"{o['service']}\n"

        )


    await update.message.reply_text(

        "📥 Excel uchun ma'lumot tayyor:\n\n"
        + text[:3500]

                )
    await update.message.reply_text(result)
# =====================================================
# 2-QISM
# BUYURTMA + USTALAR TIZIMI
# =====================================================


# ==========================
# BUYURTMA YUBORISH
# ==========================

async def send_order_to_masters(update, context, data):

    global order_id


    order_id += 1

    oid = order_id


    order = {

        "id": oid,

        "customer_id": update.effective_user.id,

        "name": data["name"],

        "phone": data["phone"],

        "service": data["service"],

        "address": data["address"],

        "description": data["description"],

        "status": "new",

        "master_id":None,

        "master":None,

        "created":datetime.now()

    }


    orders[oid]=order



    text=(

        "🆕 ЯНГИ БУЮРТМА\n\n"

        f"🔢 №{oid}\n"

        f"👤 Мижоз: {order['name']}\n"

        f"📞 Телефон: {order['phone']}\n"

        f"🛠 Хизмат: {order['service']}\n"

        f"📍 Манзил: {order['address']}\n"

        f"📝 Изоҳ: {order['description']}\n\n"

        "👨‍🔧 Уста қабул қилиши мумкин"

    )



    keyboard=InlineKeyboardMarkup(

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


    return oid




# ==========================
# MESSAGE HANDLER
# ==========================


async def message_handler(update,context):


    if not update.message:

        return


    user=update.effective_user

    text=update.message.text



    # BUYURTMA

    if text=="📝 Buyurtma berish":

        await new_order(update,context)

        return



    state=user_state.get(user.id)


    if not state:

        return



    step=state["step"]



    if step=="name":

        state["name"]=text

        state["step"]="phone"

        await ask_phone(update,context)

        return




    if step=="phone":


        if update.message.contact:

            phone=update.message.contact.phone_number

        else:

            phone=text



        state["phone"]=phone

        state["step"]="service"


        await update.message.reply_text(

            "🛠 Хизмат танланг",

            reply_markup=service_menu()

        )

        return




    if step=="service":


        state["service"]=text

        state["step"]="location"


        await ask_location(update,context)

        return




    if step=="location":


        if update.message.location:

            state["address"]=(
                f"{update.message.location.latitude},"
                f"{update.message.location.longitude}"
            )

        else:

            state["address"]=text



        state["step"]="description"


        await update.message.reply_text(

            "📝 Буюртма ҳақида ёзинг"

        )

        return




    if step=="description":


        state["description"]=text



        oid=await send_order_to_masters(

            update,

            context,

            state

        )


        user_state.pop(user.id)



        await update.message.reply_text(

            f"✅ Буюртма қабул қилинди\n\n"

            f"🔢 №{oid}\n"

            "👨‍🔧 Усталарга юборилди",

            reply_markup=main_menu()

        )

        return





# ==========================
# USTA BUTTONLAR
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


        master=(

            f"@{user.username}"

            if user.username

            else user.first_name

        )



        order["status"]="accepted"

        order["master"]=master

        order["master_id"]=user.id



        await query.edit_message_text(

            "🟡 ҚАБУЛ ҚИЛИНДИ\n\n"

            f"№{oid}\n"

            f"👨‍🔧 Уста: {master}"

        )



        await context.bot.send_message(

            order["customer_id"],

            f"🟡 №{oid} буюртмангиз қабул қилинди\n"

            f"👨‍🔧 Уста: {master}"

        )





    elif data.startswith("reject_"):


        oid=int(data.split("_")[1])

        orders[oid]["status"]="rejected"



        await query.edit_message_text(

            f"🚫 №{oid} буюртма рад этилди"

        )





    elif data.startswith("start_"):


        oid=int(data.split("_")[1])

        orders[oid]["status"]="process"



        await query.edit_message_text(

            f"🔵 №{oid} иш жараёнида"

        )





    elif data.startswith("done_"):


        oid=int(data.split("_")[1])

        orders[oid]["status"]="done"



        await query.edit_message_text(

            f"✅ №{oid} якунланди"

        )





    elif data.startswith("cancel_"):


        oid=int(data.split("_")[1])

        orders[oid]["status"]="cancel"



        await query.edit_message_text(

            f"❌ №{oid} бекор қилинди"
# =====================================================
# 3-QISM
# ADMIN + STATISTIKA + START
# =====================================================


# ==========================
# ADMIN PANEL
# ==========================

async def dispatcher(update,context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз"
        )
        return


    await update.message.reply_text(

        "👑 USTA 24 ADMIN PANEL\n\n"
        "Бўлимни танланг:",

        reply_markup=admin_menu()

    )




# ==========================
# USTA QO'SHISH
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

            "id":mid,

            "name":name,

            "phone":phone

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
# USTALAR RO'YXATI
# ==========================

async def masters_list(update,context):


    text="👨‍🔧 УСТАЛАР\n\n"


    for m in masters.values():

        text+=(
            f"🆔 {m['id']}\n"
            f"👨‍🔧 {m['name']}\n"
            f"📞 {m['phone']}\n"
            "────────\n"
        )


    await update.message.reply_text(text)





# ==========================
# STATISTIKA
# ==========================

async def statistics(update,context):


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
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор: {cancel}"

    )





# ==========================
# MIJOZ BAZASI
# ==========================

async def customer_base(update,context):


    text="👤 МИЖОЗЛАР\n\n"

    done=set()


    for o in orders.values():

        uid=o["customer_id"]


        if uid not in done:

            done.add(uid)

            text+=(
                f"👤 {o['name']}\n"
                f"📞 {o['phone']}\n"
                "────────\n"
            )


    await update.message.reply_text(text)






# ==========================
# REYTING
# ==========================

async def review(update,context):


    await update.message.reply_text(

        "⭐ Устага баҳо беринг\n"
        "1 дан 5 гача рақам ёзинг"

    )


    user_state[update.effective_user.id]={
        "review":True
    }






# ==========================
# XABAR TARQATISH
# ==========================

async def broadcast(update,context):


    if update.effective_user.id != ADMIN_ID:
        return


    msg=" ".join(context.args)


    count=0


    for uid in customers:


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
# NARXLAR
# ==========================

async def price_list(update,context):


    text="💰 НАРХЛАР\n\n"


    for k,v in prices.items():

        text+=(
            f"{k} - {v} сўм\n"
        )


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
        CommandHandler(
            "dispatcher",
            dispatcher
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

    import threading

    threading.Thread(
        target=run_web,
        daemon=True
    ).start()


    main()

    )
