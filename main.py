# ============================================================
# USTA 24 PRO BOT
# SINGLE CLEAN MAIN.PY
# MIJOZ + DISPETCHER + USTA + ADMIN
# ============================================================

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


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("USTA24")


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
DISPATCHER_ID = os.getenv("DISPATCHER_ID")

DATABASE_URL = os.getenv("DATABASE_URL")


if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")


ADMIN_ID = int(ADMIN_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)

# DISPATCHER_ID бўлмаса ADMIN_ID ишлайди
if DISPATCHER_ID:
    DISPATCHER_ID = int(DISPATCHER_ID)
else:
    DISPATCHER_ID = ADMIN_ID


# ============================================================
# FLASK / RENDER
# ============================================================

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
        port=int(os.getenv("PORT", "10000")),
    )


# ============================================================
# MEMORY DATABASE
# ============================================================

users = {}
orders = {}
masters = {}
reviews = {}

order_id = 0


# ============================================================
# SERVICES
# ============================================================

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
    "🔧 Бошқа хизмат",
]


# ============================================================
# STATUS
# ============================================================

STATUS = {
    "new": "🆕 Янги",
    "accepted": "🟡 Қабул қилинган",
    "process": "🔵 Иш жараёнида",
    "done": "✅ Якунланган",
    "cancel": "❌ Бекор қилинган",
    "reject": "🚫 Рад этилган",
}


# ============================================================
# CLIENT MENU
# ============================================================

def client_menu():

    return ReplyKeyboardMarkup(
        [
            ["📝 Буюртма бериш"],
            ["📋 Хизматлар"],
            ["🔁 Қайта буюртма"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# SERVICES MENU
# ============================================================

def service_menu():

    rows = []

    for service in SERVICES:
        rows.append([service])

    rows.append(["⬅️ Бош меню"])

    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
    )


# ============================================================
# ADMIN MENU
# ============================================================

def admin_menu():

    return ReplyKeyboardMarkup(
        [
            ["👤 Мижозлар"],
            ["👨‍🔧 Усталар"],
            ["📊 Статистика"],
            ["📢 Хабар тарқатиш"],
            ["⬅️ Бош меню"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# MASTER MENU
# ============================================================

def masters_menu():

    return ReplyKeyboardMarkup(
        [
            ["➕ Уста қўшиш"],
            ["👨‍🔧 Усталар рўйхати"],
            ["🗑 Устани ўчириш"],
            ["⬅️ Админ меню"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user = update.effective_user

    await update.message.reply_text(
        f"👋 Ассалому алайкум, {user.first_name}!\n\n"
        "🏠 USTA 24\n\n"
        "Уй ва хизмат ишлари учун уста чақиринг.",
        reply_markup=client_menu(),
    )


# ============================================================
# ADMIN START
# ============================================================

async def admin_start(update, context):

    if not update.message:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )
        return

    await update.message.reply_text(
        "👑 USTA 24 АДМИН\n\n"
        "Бўлимни танланг:",
        reply_markup=admin_menu(),
    )


# ============================================================
# NEW ORDER
# ============================================================

async def new_order(update, context):

    if not update.message:
        return

    uid = update.effective_user.id

    users[uid] = {
        "step": "name",
        "name": "",
        "phone": "",
        "service": "",
        "address": "",
        "comment": "",
    }

    await update.message.reply_text(
        "📝 БУЮРТМА БЕРИШ\n\n"
        "👤 Исмингизни ёзинг:"
    )


# ============================================================
# CLIENT HANDLER
# ============================================================

async def client_handler(update, context):

    if not update.message:
        return

    # Фақат шахсий чатда ишлайди
    if update.effective_chat.type != "private":
        return

    uid = update.effective_user.id

    text = update.message.text or ""

    # --------------------------------------------------------
    # NEW ORDER
    # --------------------------------------------------------

    if text == "📝 Буюртма бериш":

        await new_order(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # SERVICES
    # --------------------------------------------------------

    if text == "📋 Хизматлар":

        await update.message.reply_text(
            "📋 USTA 24 ХИЗМАТЛАРИ\n\n"
            + "\n".join(SERVICES),
            reply_markup=client_menu(),
        )

        return

    # --------------------------------------------------------
    # REPEAT ORDER
    # --------------------------------------------------------

    if text == "🔁 Қайта буюртма":

        previous = None

        for oid in sorted(
            orders.keys(),
            reverse=True
        ):

            if orders[oid].get(
                "customer_id"
            ) == uid:

                previous = orders[oid]
                break

        if not previous:

            await update.message.reply_text(
                "❌ Сизда аввалги буюртма топилмади."
            )

            return

        users[uid] = {
            "step": "comment",
            "name": previous.get(
                "name",
                ""
            ),
            "phone": previous.get(
                "phone",
                ""
            ),
            "service": previous.get(
                "service",
                ""
            ),
            "address": previous.get(
                "address",
                ""
            ),
            "comment": "",
        }

        await update.message.reply_text(
            "🔁 ҚАЙТА БУЮРТМА\n\n"
            f"👤 Исм: {previous.get('name')}\n"
            f"📞 Телефон: {previous.get('phone')}\n"
            f"🛠 Хизмат: {previous.get('service')}\n"
            f"📍 Манзил: {previous.get('address')}\n\n"
            "📝 Қўшимча изоҳ ёзинг:"
        )

        return

    # --------------------------------------------------------
    # BACK MENU
    # --------------------------------------------------------

    if text == "⬅️ Бош меню":

        users.pop(
            uid,
            None
        )

        await update.message.reply_text(
            "🏠 Асосий меню:",
            reply_markup=client_menu(),
        )

        return

    # --------------------------------------------------------
    # NO ACTIVE ORDER
    # --------------------------------------------------------

    if uid not in users:
        return

    data = users[uid]

    step = data.get("step")

    # ========================================================
    # NAME
    # ========================================================

    if step == "name":

        if not text.strip():

            await update.message.reply_text(
                "❗ Исмни ёзинг."
            )

            return

        data["name"] = text.strip()

        data["step"] = "phone"

        phone_button = KeyboardButton(
            "📞 Телефон рақамимни юбориш",
            request_contact=True,
        )

        await update.message.reply_text(
            "📞 Телефон рақамингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [phone_button]
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

        return

    # ========================================================
    # PHONE
    # ========================================================

    if step == "phone":

        # CONTACT
        if update.message.contact:

            data["phone"] = (
                update.message.contact.phone_number
            )

        # MANUAL PHONE
        elif text:

            data["phone"] = text.strip()

        else:

            await update.message.reply_text(
                "📞 Телефон рақамингизни юборинг."
            )

            return

        data["step"] = "service"

        await update.message.reply_text(
            "🛠 Хизматни танланг:",
            reply_markup=service_menu(),
        )

        return

    # ========================================================
    # SERVICE
    # ========================================================

    if step == "service":

        if text == "⬅️ Бош меню":

            users.pop(uid, None)

            await update.message.reply_text(
                "🏠 Асосий меню:",
                reply_markup=client_menu(),
            )

            return

        if text not in SERVICES:

            await update.message.reply_text(
                "❗ Илтимос, хизматлар рўйхатидан танланг."
            )

            return

        data["service"] = text

        data["step"] = "address"

        location_button = KeyboardButton(
            "📍 Геолокация юбориш",
            request_location=True,
        )

        await update.message.reply_text(
            "📍 Манзилни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [location_button],
                    ["✍️ Манзилни ёзиш"],
                ],
                resize_keyboard=True,
            ),
        )

        return

    # ========================================================
    # ADDRESS
    # ========================================================

    if step == "address":

        if text == "✍️ Манзилни ёзиш":

            data["step"] = "address_text"

            await update.message.reply_text(
                "📍 Манзилни тўлиқ ёзинг:"
            )

            return

        if update.message.location:

            lat = update.message.location.latitude
            lon = update.message.location.longitude

            data["address"] = (
                f"{lat}, {lon}"
            )

        elif text:

            data["address"] = text.strip()

        else:

            await update.message.reply_text(
                "📍 Манзилни юборинг."
            )

            return

        data["step"] = "comment"

        await update.message.reply_text(
            "📝 Буюртма ҳақида қўшимча изоҳ ёзинг:"
        )

        return

    # ========================================================
    # ADDRESS TEXT
    # ========================================================

    if step == "address_text":

        if not text.strip():

            await update.message.reply_text(
                "📍 Манзилни ёзинг."
            )

            return

        data["address"] = text.strip()

        data["step"] = "comment"

        await update.message.reply_text(
            "📝 Буюртма ҳақида қўшимча изоҳ ёзинг:"
        )

        return

    # ========================================================
    # COMMENT
    # ========================================================

    if step == "comment":

        data["comment"] = (
            text.strip()
            if text
            else "Изоҳ йўқ"
        )

        await send_order(
            update,
            context,
            data,
        )

        users.pop(
            uid,
            None
        )

        return


# ============================================================
# CREATE ORDER
# ============================================================

async def send_order(
    update,
    context,
    data
):

    global order_id

    order_id += 1

    oid = order_id

    customer = update.effective_user

    username = (
        f"@{customer.username}"
        if customer.username
        else ""
    )

    orders[oid] = {
        "id": oid,
        "customer_id": customer.id,
        "name": data["name"],
        "phone": data["phone"],
        "service": data["service"],
        "address": data["address"],
        "comment": data["comment"],
        "username": username,
        "status": "new",
        "master_id": None,
        "master": None,
        "created": datetime.now(),
    }

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟡 Қабул қилиш",
                    callback_data=f"accept_{oid}",
                ),
                InlineKeyboardButton(
                    "🚫 Рад этиш",
                    callback_data=f"reject_{oid}",
                ),
            ],
        ]
    )

    text = (
        "🆕 ЯНГИ БУЮРТМА\n\n"
        f"🔢 Буюртма: №{oid}\n"
        f"👤 Мижоз: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"🛠 Хизмат: {data['service']}\n"
        f"📍 Манзил: {data['address']}\n"
        f"📝 Изоҳ: {data['comment']}\n"
        f"👤 Username: {username or 'йўқ'}\n\n"
        "📌 Буюртмани қабул қилиш ёки рад этиш мумкин."
    )

    # ========================================================
    # MASTERS GROUP
    # ========================================================

    try:

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=text,
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.exception(
            f"MASTERS_GROUP_ID га юборишда хато: {e}"
        )

        await update.message.reply_text(
            "❌ Буюртмани усталар гуруҳига юбориб бўлмади.\n\n"
            "Админ гуруҳ ID ва ботнинг гуруҳдаги ҳуқуқларини текширинг."
        )

        return

    # ========================================================
    # DISPATCHER / ADMIN
    # ========================================================

    if DISPATCHER_ID:

        try:

            await context.bot.send_message(
                chat_id=DISPATCHER_ID,
                text=(
                    "📥 ДИСПЕТЧЕРГА ЯНГИ БУЮРТМА\n\n"
                    + text
                ),
                reply_markup=keyboard,
            )

        except Exception as e:

            logger.warning(
                f"Dispatcher message error: {e}"
            )

    # ========================================================
    # CLIENT
    # ========================================================

    await update.message.reply_text(
        "✅ Буюртмангиз қабул қилинди.\n\n"
        f"🔢 Буюртма №{oid}\n\n"
        "👨‍🔧 Диспетчер уста бириктиради.\n\n"
        "☎️ USTA 24\n"
        "+998 77 069 00 03",
        reply_markup=client_menu(),
    )


# ============================================================
# ORDER CALLBACK
# ============================================================

async def order_callback(
    update,
    context
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    if "_" not in data:
        return

    action, oid_text = data.split(
        "_",
        1
    )

    try:

        oid = int(oid_text)

    except ValueError:

        return

    if oid not in orders:

        await query.answer(
            "Буюртма топилмади.",
            show_alert=True,
        )

        return

    order = orders[oid]

    user = query.from_user

    # ========================================================
    # ACCEPT
    # ========================================================

    if action == "accept":

        master_name = (
            f"@{user.username}"
            if user.username
            else user.first_name
        )

        order["status"] = "accepted"
        order["master_id"] = user.id
        order["master"] = master_name

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔵 Ишни бошлаш",
                        callback_data=f"start_{oid}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel_{oid}",
                    )
                ],
            ]
        )

        await query.edit_message_text(
            "🟡 БУЮРТМА ҚАБУЛ ҚИЛИНДИ\n\n"
            f"🔢 №{oid}\n"
            f"👨‍🔧 Уста: {master_name}\n\n"
            "Ишни бошлаш мумкин.",
            reply_markup=keyboard,
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "Тез орада иш бошланади."
                ),
            )

        except Exception as e:

            logger.warning(
                f"Client accept message error: {e}"
            )

        return

    # ========================================================
    # REJECT
    # ========================================================

    if action == "reject":

        order["status"] = "reject"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔁 Қайта уста қидириш",
                        callback_data=f"redispatch_{oid}",
                    )
                ]
            ]
        )

        await query.edit_message_text(
            "🚫 БУЮРТМА РАД ЭТИЛДИ\n\n"
            f"🔢 №{oid}\n\n"
            "Бошқа уста бириктириш мумкин.",
            reply_markup=keyboard,
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🚫 №{oid} буюртма рад этилди.\n\n"
                    "Бошқа уста бириктириш учун диспетчер ишлаяпти."
                ),
            )

        except Exception as e:

            logger.warning(
                f"Reject client message error: {e}"
            )

        return

    # ========================================================
    # START
    # ========================================================

    if action == "start":

        order["status"] = "process"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Ишни якунлаш",
                        callback_data=f"done_{oid}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Бекор қилиш",
                        callback_data=f"cancel_{oid}",
                    )
                ],
            ]
        )

        await query.edit_message_text(
            "🔵 ИШ ЖАРАЁНИДА\n\n"
            f"🔢 №{oid}\n"
            f"👨‍🔧 Уста: {order.get('master')}",
            reply_markup=keyboard,
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"
                    f"👨‍🔧 Уста: {order.get('master')}"
                ),
            )

        except Exception as e:

            logger.warning(
                f"Start client message error: {e}"
            )

        return

    # ========================================================
    # DONE
    # ========================================================

    if action == "done":

        order["status"] = "done"

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐ Баҳо бериш",
                        callback_data=f"review_{oid}",
                    )
                ]
            ]
        )

        await query.edit_message_text(
            "✅ БУЮРТМА ЯКУНЛАНДИ\n\n"
            f"🔢 №{oid}\n"
            f"👨‍🔧 Уста: {order.get('master')}",
            reply_markup=keyboard,
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"✅ №{oid} буюртма якунланди.\n\n"
                    "⭐ Устага баҳо беришингиз мумкин."
                ),
                reply_markup=keyboard,
            )

        except Exception as e:

            logger.warning(
                f"Done client message error: {e}"
            )

        return

    # ========================================================
    # CANCEL
    # ========================================================

    if action == "cancel":

        order["status"] = "cancel"

        await query.edit_message_text(
            "❌ БУЮРТМА БЕКОР ҚИЛИНДИ\n\n"
            f"🔢 №{oid}"
        )

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"❌ №{oid} буюртма бекор қилинди."
                ),
            )

        except Exception as e:

            logger.warning(
                f"Cancel client message error: {e}"
            )

        return

    # ========================================================
    # REDISPATCH
    # ========================================================

    if action == "redispatch":

        order["status"] = "new"
        order["master_id"] = None
        order["master"] = None

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🟡 Қабул қилиш",
                        callback_data=f"accept_{oid}",
                    ),
                    InlineKeyboardButton(
                        "🚫 Рад этиш",
                        callback_data=f"reject_{oid}",
                    ),
                ]
            ]
        )

        text = (
            "🔁 ҚАЙТА ДИСПЕТЧЕРЛАШ\n\n"
            f"🔢 №{oid}\n"
            f"👤 Мижоз: {order['name']}\n"
            f"📞 Телефон: {order['phone']}\n"
            f"🛠 Хизмат: {order['service']}\n"
            f"📍 Манзил: {order['address']}\n"
            f"📝 Изоҳ: {order['comment']}"
        )

        try:

            await context.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=text,
                reply_markup=keyboard,
            )

        except Exception as e:

            logger.exception(
                f"Redispatch error: {e}"
            )

        await query.edit_message_text(
            f"🔁 №{oid} қайта диспетчерга берилди."
        )

        return

    # ========================================================
    # REVIEW
    # ========================================================

    if action == "review":

        if user.id != order["customer_id"]:

            await query.answer(
                "Бу буюртма сизники эмас.",
                show_alert=True,
            )

            return

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⭐ 1",
                        callback_data=f"rate_{oid}_1",
                    ),
                    InlineKeyboardButton(
                        "⭐ 2",
                        callback_data=f"rate_{oid}_2",
                    ),
                    InlineKeyboardButton(
                        "⭐ 3",
                        callback_data=f"rate_{oid}_3",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⭐ 4",
                        callback_data=f"rate_{oid}_4",
                    ),
                    InlineKeyboardButton(
                        "⭐ 5",
                        callback_data=f"rate_{oid}_5",
                    ),
                ],
            ]
        )

        await query.message.reply_text(
            "⭐ Устага баҳо беринг:",
            reply_markup=keyboard,
        )

        return

    # ========================================================
    # RATE
    # ========================================================

    if action == "rate":

        parts = data.split("_")

        if len(parts) != 3:
            return

        try:

            rating = int(parts[2])

        except ValueError:

            return

        reviews[oid] = {
            "customer_id": user.id,
            "rating": rating,
            "master_id": order.get(
                "master_id"
            ),
        }

        await query.edit_message_text(
            f"⭐ Раҳмат!\n\n"
            f"Сиз {rating}/5 баҳо бердингиз."
        )

        return


# ============================================================
# ADMIN MENU BUTTONS
# ============================================================

async def admin_button_handler(
    update,
    context
):

    if not update.message:
        return False

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text or ""

    # --------------------------------------------------------
    # CLIENTS
    # --------------------------------------------------------

    if text == "👤 Мижозлар":

        await customer_base(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # MASTERS
    # --------------------------------------------------------

    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
            reply_markup=masters_menu(),
        )

        return True

    # --------------------------------------------------------
    # ADD MASTER
    # --------------------------------------------------------

    if text == "➕ Уста қўшиш":

        await add_master_start(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # MASTER LIST
    # --------------------------------------------------------

    if text == "👨‍🔧 Усталар рўйхати":

        await masters_list(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # DELETE MASTER
    # --------------------------------------------------------

    if text == "🗑 Устани ўчириш":

        await delete_master_start(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    if text == "📊 Статистика":

        await statistics(
            update,
            context
        )

        return True

    # --------------------------------------------------------
    # BROADCAST
    # --------------------------------------------------------

    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return True

    # --------------------------------------------------------
    # ADMIN MENU
    # --------------------------------------------------------

    if text == "⬅️ Админ меню":

        await update.message.reply_text(
            "👑 USTA 24 АДМИН\n\n"
            "Бўлимни танланг:",
            reply_markup=admin_menu(),
        )

        return True

    # --------------------------------------------------------
    # CLIENT MENU
    # --------------------------------------------------------

    if text == "⬅️ Бош меню":

        context.user_data.clear()

        await update.message.reply_text(
            "🏠 Асосий меню:",
            reply_markup=client_menu(),
        )

        return True

    return False


# ============================================================
# ALL TEXT HANDLER
# ============================================================

async def all_text_handler(
    update,
    context
):

    if not update.message:
        return

    uid = update.effective_user.id

    text = update.message.text or ""

    # ========================================================
    # ADMIN
    # ========================================================

    if uid == ADMIN_ID:

        # Уста қўшиш жараёни
        if context.user_data.get(
            "master_add"
        ):

            await add_master_handler(
                update,
                context
            )

            return

        # Уста ўчириш жараёни
        if context.user_data.get(
            "delete_master"
        ):

            await delete_master_handler(
                update,
                context
            )

            return

        handled = await admin_button_handler(
            update,
            context
        )

        if handled:
            return

    # ========================================================
    # CLIENT
    # ========================================================

    await client_handler(
        update,
        context
    )


# ============================================================
# CONTACT / LOCATION
# ============================================================

async def contact_location_handler(
    update,
    context
):

    if not update.message:
        return

    # CONTACT фақат private chatда
    if update.effective_chat.type != "private":
        return

    await client_handler(
        update,
        context
    )


# ============================================================
# CUSTOMER BASE
# ============================================================

async def customer_base(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    if not orders:

        await update.message.reply_text(
            "👤 Мижозлар базаси бўш."
        )

        return

    customers = {}

    for order in orders.values():

        cid = order.get(
            "customer_id"
        )

        customers[cid] = order

    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"

    for order in customers.values():

        text += (
            f"👤 {order.get('name', '-')}\n"
            f"📞 {order.get('phone', '-')}\n"
            f"🛠 {order.get('service', '-')}\n"
            f"📍 {order.get('address', '-')}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text
    )


# ============================================================
# MASTER LIST
# ============================================================

async def masters_list(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Ҳозирча усталар қўшилмаган.",
            reply_markup=masters_menu(),
        )

        return

    text = "👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"

    for mid, master in masters.items():

        services = ", ".join(
            master.get(
                "services",
                []
            )
        )

        text += (
            f"🆔 ID: {mid}\n"
            f"👨‍🔧 Исм: {master.get('name', '-')}\n"
            f"📞 Телефон: {master.get('phone', '-')}\n"
            f"👤 Username: {master.get('username', '-')}\n"
            f"🛠 Хизматлар: {services or '-'}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=masters_menu(),
    )


# ============================================================
# ADD MASTER START
# ============================================================

async def add_master_start(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["master_add"] = True

    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "Қуйидаги форматда юборинг:\n\n"
        "ID | Исм | Телефон | Username | Хизматлар\n\n"
        "Мисол:\n"
        "123456789 | Али | +998901234567 | @ali | Мебель, Сантехника"
    )


# ============================================================
# ADD MASTER HANDLER
# ============================================================

async def add_master_handler(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    parts = [
        x.strip()
        for x in text.split("|")
    ]

    if len(parts) < 5:

        await update.message.reply_text(
            "❌ Формат нотўғри.\n\n"
            "ID | Исм | Телефон | Username | Хизматлар"
        )

        return

    try:

        mid = int(parts[0])

    except ValueError:

        await update.message.reply_text(
            "❌ ID рақам бўлиши керак."
        )

        return

    name = parts[1]
    phone = parts[2]
    username = parts[3]

    services = [
        x.strip()
        for x in parts[4].split(",")
        if x.strip()
    ]

    masters[mid] = {
        "name": name,
        "phone": phone,
        "username": username,
        "services": services,
        "orders": 0,
    }

    context.user_data.pop(
        "master_add",
        None
    )

    await update.message.reply_text(
        "✅ УСТА ҚЎШИЛДИ\n\n"
        f"🆔 ID: {mid}\n"
        f"👨‍🔧 Исм: {name}\n"
        f"📞 Телефон: {phone}\n"
        f"👤 Username: {username}\n"
        f"🛠 Хизматлар: {', '.join(services)}",
        reply_markup=masters_menu(),
    )


# ============================================================
# DELETE MASTER START
# ============================================================

async def delete_master_start(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["delete_master"] = True

    await update.message.reply_text(
        "🗑 УСТАНИ ЎЧИРИШ\n\n"
        "Устанинг ID рақамини юборинг."
    )


# ============================================================
# DELETE MASTER HANDLER
# ============================================================

async def delete_master_handler(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    try:

        mid = int(text.strip())

    except ValueError:

        await update.message.reply_text(
            "❌ ID рақам бўлиши керак."
        )

        return

    if mid not in masters:

        await update.message.reply_text(
            "❌ Бундай уста топилмади."
        )

        return

    name = masters[mid].get(
        "name",
        "-"
    )

    del masters[mid]

    context.user_data.pop(
        "delete_master",
        None
    )

    await update.message.reply_text(
        f"🗑 {name} ўчирилди.",
        reply_markup=masters_menu(),
    )


# ============================================================
# STATISTICS
# ============================================================

async def statistics(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:
        return

    total = len(orders)

    new_count = 0
    accepted = 0
    process = 0
    done = 0
    cancel = 0
    reject = 0

    for order in orders.values():

        status = order.get(
            "status"
        )

        if status == "new":
            new_count += 1

        elif status == "accepted":
            accepted += 1

        elif status == "process":
            process += 1

        elif status == "done":
            done += 1

        elif status == "cancel":
            cancel += 1

        elif status == "reject":
            reject += 1

    await update.message.reply_text(
        "📊 USTA 24 СТАТИСТИКА\n\n"
        f"📋 Жами буюртма: {total}\n"
        f"🆕 Янги: {new_count}\n"
        f"🟡 Қабул қилинган: {accepted}\n"
        f"🔵 Иш жараёнида: {process}\n"
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор қилинган: {cancel}\n"
        f"🚫 Рад этилган: {reject}\n\n"
        f"👨‍🔧 Усталар: {len(masters)}\n"
        f"⭐ Баҳо берилган: {len(reviews)}",
        reply_markup=admin_menu(),
    )


# ============================================================
# SEND / BROADCAST
# ============================================================

async def send_command(
    update,
    context
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз админ эмассиз."
        )

        return

    if not context.args:

        await update.message.reply_text(
            "📢 ХАБАР ТАРҚАТИШ\n\n"
            "Формат:\n"
            "/send Хабар матни"
        )

        return

    msg = " ".join(
        context.args
    )

    customer_ids = set()

    for order in orders.values():

        cid = order.get(
            "customer_id"
        )

        if cid:
            customer_ids.add(cid)

    count = 0

    for customer_id in customer_ids:

        try:

            await context.bot.send_message(
                chat_id=customer_id,
                text=msg,
            )

            count += 1

        except Exception as e:

            logger.warning(
                f"Broadcast error {customer_id}: {e}"
            )

    await update.message.reply_text(
        "📢 ХАБАР ЮБОРИЛДИ\n\n"
        f"👥 {count} та мижозга юборилди.",
        reply_markup=admin_menu(),
    )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def callback_router(
    update,
    context
):

    await order_callback(
        update,
        context
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update,
    context
):

    logger.error(
        "USTA24 ERROR",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    application = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # ========================================================
    # /START
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # ========================================================
    # /ADMIN
    # ========================================================

    application.add_handler(
        CommandHandler(
            "admin",
            admin_start,
        )
    )

    # ========================================================
    # /SEND
    # ========================================================

    application.add_handler(
        CommandHandler(
            "send",
            send_command,
        )
    )

    # ========================================================
    # CALLBACK
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    # ========================================================
    # CONTACT
    # Фақат private chat
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.CONTACT,
            contact_location_handler,
        )
    )

    # ========================================================
    # LOCATION
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.LOCATION,
            contact_location_handler,
        )
    )

    # ========================================================
    # TEXT
    # ========================================================

    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND,
            all_text_handler,
        )
    )

    # ========================================================
    # ERROR
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    # ========================================================
    # FLASK
    # ========================================================

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    # ========================================================
    # START
    # ========================================================

    print(
        "======================================"
    )

    print(
        "        USTA 24 BOT ISHLADI"
    )

    print(
        "======================================"
    )

    print(
        f"ADMIN_ID: {ADMIN_ID}"
    )

    print(
        f"DISPATCHER_ID: {DISPATCHER_ID}"
    )

    print(
        f"MASTERS_GROUP_ID: {MASTERS_GROUP_ID}"
    )

    # ========================================================
    # POLLING
    # ========================================================

    application.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
