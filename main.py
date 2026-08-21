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
# CONFIG
# ============================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
MASTERS_GROUP_ID = os.getenv("MASTERS_GROUP_ID")
DISPATCHER_ID = os.getenv("DISPATCHER_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID topilmadi")

if not MASTERS_GROUP_ID:
    raise RuntimeError("MASTERS_GROUP_ID topilmadi")

ADMIN_ID = int(ADMIN_ID)
MASTERS_GROUP_ID = int(MASTERS_GROUP_ID)

if DISPATCHER_ID:
    DISPATCHER_ID = int(DISPATCHER_ID)
else:
    DISPATCHER_ID = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("USTA24")


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
    port = int(os.getenv("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port,
    )


# ============================================================
# MEMORY DATABASE
# ============================================================
# Hozircha botni barqaror ishlatish uchun memory storage.
# Keyinchalik PostgreSQL alohida ulab berish mumkin.
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
    "❄️ Кондиционер",
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
            ["📞 Алоқа"],
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
            ["👤 Мижозлар", "👨‍🔧 Усталар"],
            ["📊 Статистика", "📢 Хабар тарқатиш"],
            ["⬅️ Бош меню"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# MASTER MENU
# ============================================================

def master_menu():

    return ReplyKeyboardMarkup(
        [
            ["📋 Менинг буюртмаларим"],
            ["📊 Менинг статистикам"],
            ["⬅️ Бош меню"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# MASTER MANAGEMENT MENU
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
# DISPATCHER MENU
# ============================================================

def dispatcher_menu():

    return ReplyKeyboardMarkup(
        [
            ["📋 Янги буюртмалар"],
            ["📋 Барча буюртмалар"],
            ["📊 Статистика"],
            ["⬅️ Бош меню"],
        ],
        resize_keyboard=True,
    )


# ============================================================
# /START
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user = update.effective_user

    if not user:
        return

    uid = user.id

    users.setdefault(
        uid,
        {
            "name": user.first_name or "",
            "phone": "",
            "username": user.username or "",
            "step": None,
            "last_order": None,
        },
    )

    await update.message.reply_text(
        f"👋 Ассалому алайкум, {user.first_name or 'ҳурматли мижоз'}!\n\n"
        "🏠 USTA 24\n\n"
        "Уй ва хизмат ишлари учун ишончли усталар.\n\n"
        "Керакли бўлимни танланг:",
        reply_markup=client_menu(),
    )


# ============================================================
# /ADMIN
# ============================================================

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
# /DISPATCHER
# ============================================================

async def dispatcher_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    uid = update.effective_user.id

    if DISPATCHER_ID and uid != DISPATCHER_ID and uid != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз диспетчер эмассиз."
        )

        return

    await update.message.reply_text(
        "🎧 USTA 24 ДИСПЕТЧЕР\n\n"
        "Бўлимни танланг:",
        reply_markup=dispatcher_menu(),
    )


# ============================================================
# /MASTER
# ============================================================

async def master_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    uid = update.effective_user.id

    if uid not in masters and uid != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз тизимда уста сифатида рўйхатдан ўтмагансиз."
        )

        return

    await update.message.reply_text(
        "👨‍🔧 USTA 24 УСТА БЎЛИМИ\n\n"
        "Бўлимни танланг:",
        reply_markup=master_menu(),
    )


# ============================================================
# CLIENT: NEW ORDER
# ============================================================

async def new_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    users[uid] = {
        "name": "",
        "phone": "",
        "username": update.effective_user.username or "",
        "step": "name",
        "last_order": users.get(uid, {}).get("last_order"),
    }

    await update.message.reply_text(
        "📝 БУЮРТМА БЕРИШ\n\n"
        "1️⃣ Исмингизни ёзинг:"
    )


# ============================================================
# CLIENT: REPEAT ORDER
# ============================================================

async def repeat_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    last_id = users.get(uid, {}).get("last_order")

    if not last_id or last_id not in orders:

        await update.message.reply_text(
            "🔁 Сизда аввалги буюртма топилмади.\n\n"
            "Янги буюртма беришингиз мумкин.",
            reply_markup=client_menu(),
        )

        return

    old = orders[last_id]

    users[uid] = {
        "name": old["name"],
        "phone": old["phone"],
        "username": old.get("username", ""),
        "service": old["service"],
        "address": old["address"],
        "comment": old["comment"],
        "step": "repeat_confirm",
        "last_order": last_id,
    }

    await update.message.reply_text(
        "🔁 ҚАЙТА БУЮРТМА\n\n"
        f"👤 Исм: {old['name']}\n"
        f"📞 Телефон: {old['phone']}\n"
        f"🛠 Хизмат: {old['service']}\n"
        f"📍 Манзил: {old['address']}\n"
        f"📝 Изоҳ: {old['comment']}\n\n"
        "Шу маълумотлар билан қайта буюртма бериш учун "
        "«✅ Тасдиқлаш»ни босинг.",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ Тасдиқлаш"],
                ["❌ Бекор қилиш"],
            ],
            resize_keyboard=True,
        ),
    )


# ============================================================
# CLIENT HANDLER
# ============================================================

async def client_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    uid = update.effective_user.id
    text = update.message.text or ""

    # --------------------------------------------------------
    # MAIN BUTTONS
    # --------------------------------------------------------

    if text == "📝 Буюртма бериш":

        await new_order(update, context)

        return

    if text == "📋 Хизматлар":

        await update.message.reply_text(
            "📋 USTA 24 ХИЗМАТЛАРИ\n\n"
            + "\n".join(
                f"• {x}" for x in SERVICES
            ),
            reply_markup=client_menu(),
        )

        return

    if text == "📞 Алоқа":

        await update.message.reply_text(
            "📞 USTA 24 АЛОҚА\n\n"
            "☎️ +998 77 069 00 03\n\n"
            "🏠 Уй хизматлари ва усталар.",
            reply_markup=client_menu(),
        )

        return

    if text == "🔁 Қайта буюртма":

        await repeat_order(update, context)

        return

    if text == "⬅️ Бош меню":

        users.setdefault(uid, {})["step"] = None

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

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    if step == "name":

        if not text.strip():

            await update.message.reply_text(
                "❌ Исмни киритинг."
            )

            return

        data["name"] = text.strip()
        data["step"] = "phone"

        button = KeyboardButton(
            "📞 Телефон рақамимни юбориш",
            request_contact=True,
        )

        await update.message.reply_text(
            "2️⃣ Телефон рақамингизни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [[button]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )

        return

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    if step == "phone":

        if update.message.contact:

            data["phone"] = update.message.contact.phone_number

        elif text:

            data["phone"] = text.strip()

        else:

            await update.message.reply_text(
                "❌ Телефон рақамини юборинг."
            )

            return

        data["step"] = "service"

        await update.message.reply_text(
            "3️⃣ Хизматни танланг:",
            reply_markup=service_menu(),
        )

        return

    # --------------------------------------------------------
    # SERVICE
    # --------------------------------------------------------

    if step == "service":

        if text not in SERVICES:

            await update.message.reply_text(
                "❌ Илтимос, хизматни пастдаги рўйхатдан танланг.",
                reply_markup=service_menu(),
            )

            return

        data["service"] = text
        data["step"] = "address"

        location_button = KeyboardButton(
            "📍 Геолокация юбориш",
            request_location=True,
        )

        await update.message.reply_text(
            "4️⃣ Манзилни юборинг:",
            reply_markup=ReplyKeyboardMarkup(
                [
                    [location_button],
                    ["✍️ Манзилни ёзиш"],
                ],
                resize_keyboard=True,
            ),
        )

        return

    # --------------------------------------------------------
    # ADDRESS MENU
    # --------------------------------------------------------

    if step == "address" and text == "✍️ Манзилни ёзиш":

        data["step"] = "address_text"

        await update.message.reply_text(
            "📍 Манзилни тўлиқ ёзинг:"
        )

        return

    # --------------------------------------------------------
    # ADDRESS TEXT
    # --------------------------------------------------------

    if step == "address_text":

        if not text.strip():

            await update.message.reply_text(
                "❌ Манзилни ёзинг."
            )

            return

        data["address"] = text.strip()
        data["step"] = "comment"

        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қўшимча изоҳ ёзинг.\n\n"
            "Масалан: шкаф йиғиш, 2-қават, кечқурун керак ва ҳ.к."
        )

        return

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    if step == "address" and update.message.location:

        loc = update.message.location

        data["address"] = (
            f"https://maps.google.com/?q="
            f"{loc.latitude},{loc.longitude}"
        )

        data["step"] = "comment"

        await update.message.reply_text(
            "5️⃣ Буюртма ҳақида қўшимча изоҳ ёзинг:"
        )

        return

    # --------------------------------------------------------
    # COMMENT
    # --------------------------------------------------------

    if step == "comment":

        data["comment"] = text.strip()

        await send_order(
            update,
            context,
            data,
        )

        data["step"] = None

        return

    # --------------------------------------------------------
    # REPEAT CONFIRM
    # --------------------------------------------------------

    if step == "repeat_confirm":

        if text == "❌ Бекор қилиш":

            data["step"] = None

            await update.message.reply_text(
                "❌ Буюртма бекор қилинди.",
                reply_markup=client_menu(),
            )

            return

        if text == "✅ Тасдиқлаш":

            await send_order(
                update,
                context,
                data,
            )

            data["step"] = None

            return


# ============================================================
# CREATE ORDER
# ============================================================

async def send_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data,
):

    global order_id

    order_id += 1

    oid = order_id

    uid = update.effective_user.id

    username = update.effective_user.username or ""

    orders[oid] = {
        "id": oid,
        "customer_id": uid,
        "name": data.get("name", ""),
        "phone": data.get("phone", ""),
        "username": username,
        "service": data.get("service", ""),
        "address": data.get("address", ""),
        "comment": data.get("comment", ""),
        "status": "new",
        "master_id": None,
        "master_name": None,
        "created": datetime.now(),
        "review": None,
    }

    users.setdefault(uid, {})
    users[uid]["last_order"] = oid

    text = format_order(orders[oid])

    keyboard = order_keyboard(oid)

    # --------------------------------------------------------
    # DISPATCHER
    # --------------------------------------------------------

    if DISPATCHER_ID:

        try:

            await context.bot.send_message(
                chat_id=DISPATCHER_ID,
                text="🎧 ДИСПЕТЧЕРГА ЯНГИ БУЮРТМА\n\n" + text,
                reply_markup=keyboard,
            )

        except Exception as e:

            logger.error(
                f"Dispatcherga yuborilmadi: {e}"
            )

    # --------------------------------------------------------
    # MASTERS GROUP
    # --------------------------------------------------------

    try:

        await context.bot.send_message(
            chat_id=MASTERS_GROUP_ID,
            text=text,
            reply_markup=keyboard,
        )

    except Exception as e:

        logger.error(
            f"Masters group error: {e}"
        )

        await update.message.reply_text(
            "❌ Буюртмани усталар гуруҳига юборишда хатолик юз берди.\n\n"
            "Админга хабар беринг."
        )

        return

    # --------------------------------------------------------
    # CUSTOMER
    # --------------------------------------------------------

    await update.message.reply_text(
        f"✅ Буюртмангиз қабул қилинди!\n\n"
        f"🔢 Буюртма №{oid}\n\n"
        "🎧 Диспетчер буюртмани назорат қилади.\n"
        "👨‍🔧 Сизга уста бириктирилади.\n\n"
        "☎️ USTA 24\n"
        "+998 77 069 00 03",
        reply_markup=client_menu(),
    )


# ============================================================
# FORMAT ORDER
# ============================================================

def format_order(order):

    username = order.get("username")

    username_text = (
        f"@{username}"
        if username
        else "кўрсатилмаган"
    )

    return (
        "🆕 ЯНГИ БУЮРТМА\n\n"
        f"🔢 №{order['id']}\n"
        f"👤 Мижоз: {order['name']}\n"
        f"📞 Телефон: {order['phone']}\n"
        f"👤 Username: {username_text}\n"
        f"🛠 Хизмат: {order['service']}\n"
        f"📍 Манзил: {order['address']}\n"
        f"📝 Изоҳ: {order['comment']}\n"
        f"📌 Ҳолат: {STATUS.get(order['status'], order['status'])}"
    )


# ============================================================
# ORDER KEYBOARD
# ============================================================

def order_keyboard(oid):

    return InlineKeyboardMarkup(
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
            [
                InlineKeyboardButton(
                    "🎧 Диспетчерга",
                    callback_data=f"dispatch_{oid}",
                ),
            ],
        ]
    )


# ============================================================
# ACCEPTED ORDER KEYBOARD
# ============================================================

def accepted_keyboard(oid):

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔵 Ишни бошлаш",
                    callback_data=f"start_{oid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"cancel_{oid}",
                ),
            ],
        ]
    )


# ============================================================
# PROCESS KEYBOARD
# ============================================================

def process_keyboard(oid):

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Якунлаш",
                    callback_data=f"done_{oid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ Бекор қилиш",
                    callback_data=f"cancel_{oid}",
                ),
            ],
        ]
    )


# ============================================================
# ORDER CALLBACK
# ============================================================

async def order_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    if "_" not in data:
        return

    action, oid_text = data.split("_", 1)

    try:
        oid = int(oid_text)
    except ValueError:
        return

    if oid not in orders:

        await query.answer(
            "❌ Буюртма топилмади.",
            show_alert=True,
        )

        return

    order = orders[oid]

    uid = query.from_user.id

    # ========================================================
    # ACCEPT
    # ========================================================

    if action == "accept":

        # Админ/диспетчер/уста қабул қилиши мумкин
        allowed = (
            uid == ADMIN_ID
            or uid == DISPATCHER_ID
            or uid in masters
        )

        if not allowed:

            await query.answer(
                "❌ Сизда рухсат йўқ.",
                show_alert=True,
            )

            return

        master_name = (
            f"@{query.from_user.username}"
            if query.from_user.username
            else query.from_user.first_name
        )

        order["status"] = "accepted"
        order["master_id"] = uid
        order["master_name"] = master_name

        try:

            await query.edit_message_text(
                format_order(order)
                + "\n\n🟡 УСТА ҚАБУЛ ҚИЛДИ",
                reply_markup=accepted_keyboard(oid),
            )

        except Exception:
            pass

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🟡 Буюртмангиз №{oid} қабул қилинди.\n\n"
                    f"👨‍🔧 Уста: {master_name}\n\n"
                    "Тез орада иш бошланади.\n\n"
                    "☎️ USTA 24\n"
                    "+998 77 069 00 03"
                ),
            )

        except Exception as e:

            logger.error(
                f"Customer accept notification error: {e}"
            )

        return

    # ========================================================
    # REJECT
    # ========================================================

    if action == "reject":

        allowed = (
            uid == ADMIN_ID
            or uid == DISPATCHER_ID
            or uid in masters
        )

        if not allowed:

            await query.answer(
                "❌ Сизда рухсат йўқ.",
                show_alert=True,
            )

            return

        order["status"] = "reject"
        order["master_id"] = None
        order["master_name"] = None

        try:

            await query.edit_message_text(
                format_order(order)
                + "\n\n🚫 УСТА БУЮРТМАНИ РАД ЭТДИ",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔁 Қайта устага бериш",
                                callback_data=f"redispatch_{oid}",
                            )
                        ]
                    ]
                ),
            )

        except Exception:
            pass

        # Мижозга рад этилганини айтмаймиз,
        # чунки бошқа уста қидирилади.

        if DISPATCHER_ID:

            try:

                await context.bot.send_message(
                    chat_id=DISPATCHER_ID,
                    text=(
                        f"🚫 №{oid} буюртма рад этилди.\n\n"
                        "🔁 Бошқа уста бириктириш керак."
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🔁 Қайта устага бериш",
                                    callback_data=f"redispatch_{oid}",
                                )
                            ]
                        ]
                    ),
                )

            except Exception:
                pass

        return

    # ========================================================
    # START
    # ========================================================

    if action == "start":

        if uid != order.get("master_id") and uid != ADMIN_ID:

            await query.answer(
                "❌ Фақат бириктирилган уста бошлайди.",
                show_alert=True,
            )

            return

        order["status"] = "process"

        try:

            await query.edit_message_text(
                format_order(order)
                + "\n\n🔵 ИШ ЖАРАЁНИДА",
                reply_markup=process_keyboard(oid),
            )

        except Exception:
            pass

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"🔵 №{oid} буюртма бўйича иш бошланди.\n\n"
                    f"👨‍🔧 Уста: {order['master_name']}"
                ),
            )

        except Exception:
            pass

        return

    # ========================================================
    # DONE
    # ========================================================

    if action == "done":

        if uid != order.get("master_id") and uid != ADMIN_ID:

            await query.answer(
                "❌ Фақат бириктирилган уста якунлайди.",
                show_alert=True,
            )

            return

        order["status"] = "done"

        try:

            await query.edit_message_text(
                format_order(order)
                + "\n\n✅ БУЮРТМА ЯКУНЛАНДИ"
            )

        except Exception:
            pass

        review_keyboard = InlineKeyboardMarkup(
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

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"✅ №{oid} буюртма якунланди.\n\n"
                    "⭐ Уста хизматини баҳоланг:"
                ),
                reply_markup=review_keyboard,
            )

        except Exception:
            pass

        return

    # ========================================================
    # CANCEL
    # ========================================================

    if action == "cancel":

        if (
            uid != order.get("master_id")
            and uid != ADMIN_ID
            and uid != DISPATCHER_ID
        ):

            await query.answer(
                "❌ Сизда рухсат йўқ.",
                show_alert=True,
            )

            return

        order["status"] = "cancel"

        try:

            await query.edit_message_text(
                format_order(order)
                + "\n\n❌ БУЮРТМА БЕКОР ҚИЛИНДИ"
            )

        except Exception:
            pass

        try:

            await context.bot.send_message(
                chat_id=order["customer_id"],
                text=(
                    f"❌ №{oid} буюртма бекор қилинди."
                ),
            )

        except Exception:
            pass

        return

    # ========================================================
    # REDISPATCH
    # ========================================================

    if action == "redispatch":

        if (
            uid != ADMIN_ID
            and uid != DISPATCHER_ID
        ):

            await query.answer(
                "❌ Фақат диспетчер ёки админ.",
                show_alert=True,
            )

            return

        order["status"] = "new"
        order["master_id"] = None
        order["master_name"] = None

        keyboard = order_keyboard(oid)

        try:

            await context.bot.send_message(
                chat_id=MASTERS_GROUP_ID,
                text=(
                    "🔁 ҚАЙТА УСТАЛАРГА БЕРИЛДИ\n\n"
                    + format_order(order)
                ),
                reply_markup=keyboard,
            )

            await query.edit_message_text(
                f"🔁 №{oid} буюртма қайта усталарга берилди."
            )

        except Exception as e:

            logger.error(
                f"Redispatch error: {e}"
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

        if uid != order["customer_id"]:

            await query.answer(
                "❌ Бу буюртма сизники эмас.",
                show_alert=True,
            )

            return

        order["review"] = rating

        reviews[oid] = {
            "order_id": oid,
            "customer_id": uid,
            "master_id": order.get("master_id"),
            "rating": rating,
            "created": datetime.now(),
        }

        try:

            await query.edit_message_text(
                f"⭐ Раҳмат!\n\n"
                f"Сиз {rating}/5 баҳо бердингиз."
            )

        except Exception:
            pass

        return


# ============================================================
# ADMIN: CUSTOMER BASE
# ============================================================

async def customer_base(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    if not orders:

        await update.message.reply_text(
            "👤 Мижозлар базаси ҳозирча бўш."
        )

        return

    customer_map = {}

    for order in orders.values():

        customer_map[order["customer_id"]] = order

    text = "👤 МИЖОЗЛАР БАЗАСИ\n\n"

    for order in customer_map.values():

        username = order.get("username")

        username_text = (
            f"@{username}"
            if username
            else "-"
        )

        text += (
            f"👤 {order['name']}\n"
            f"📞 {order['phone']}\n"
            f"👤 {username_text}\n"
            f"🛠 {order['service']}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text
    )


# ============================================================
# ADMIN: MASTERS LIST
# ============================================================

async def masters_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    if not masters:

        await update.message.reply_text(
            "👨‍🔧 Ҳозирча уста қўшилмаган."
        )

        return

    text = "👨‍🔧 УСТАЛАР РЎЙХАТИ\n\n"

    for mid, master in masters.items():

        text += (
            f"🆔 ID: {mid}\n"
            f"👨‍🔧 Исм: {master['name']}\n"
            f"📞 Телефон: {master['phone']}\n"
            f"👤 Username: {master.get('username', '-')}\n"
            f"🛠 Хизматлар: {master.get('services', '-')}\n"
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
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["master_add"] = True

    await update.message.reply_text(
        "➕ УСТА ҚЎШИШ\n\n"
        "Формат:\n\n"
        "ID | Исм | Телефон | Username | Хизматлар\n\n"
        "Масалан:\n"
        "123456789 | Али | +998901234567 | ali123 | Мебель, Сантехника"
    )


# ============================================================
# ADD MASTER HANDLER
# ============================================================

async def add_master_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    if text == "⬅️ Админ меню":

        context.user_data.pop("master_add", None)

        await update.message.reply_text(
            "👑 Админ меню",
            reply_markup=admin_menu(),
        )

        return

    parts = [x.strip() for x in text.split("|")]

    if len(parts) != 5:

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

    masters[mid] = {
        "name": parts[1],
        "phone": parts[2],
        "username": parts[3].lstrip("@"),
        "services": parts[4],
        "orders": 0,
    }

    context.user_data.pop("master_add", None)

    await update.message.reply_text(
        "✅ УСТА ҚЎШИЛДИ\n\n"
        f"🆔 ID: {mid}\n"
        f"👨‍🔧 Исм: {parts[1]}\n"
        f"📞 Телефон: {parts[2]}\n"
        f"👤 Username: @{parts[3].lstrip('@')}\n"
        f"🛠 Хизматлар: {parts[4]}",
        reply_markup=masters_menu(),
    )


# ============================================================
# DELETE MASTER START
# ============================================================

async def delete_master_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["delete_master"] = True

    await update.message.reply_text(
        "🗑 УСТАНИ ЎЧИРИШ\n\n"
        "Устанинг Telegram ID рақамини юборинг:"
    )


# ============================================================
# DELETE MASTER HANDLER
# ============================================================

async def delete_master_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""

    if text == "⬅️ Админ меню":

        context.user_data.pop("delete_master", None)

        await update.message.reply_text(
            "👑 Админ меню",
            reply_markup=admin_menu(),
        )

        return

    try:

        mid = int(text.strip())

    except ValueError:

        await update.message.reply_text(
            "❌ Telegram ID рақамини киритинг."
        )

        return

    if mid not in masters:

        await update.message.reply_text(
            "❌ Бу ID билан уста топилмади."
        )

        return

    name = masters[mid]["name"]

    del masters[mid]

    context.user_data.pop("delete_master", None)

    await update.message.reply_text(
        f"🗑 Уста ўчирилди.\n\n"
        f"👨‍🔧 {name}",
        reply_markup=masters_menu(),
    )


# ============================================================
# STATISTICS
# ============================================================

async def statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if (
        update.effective_user.id != ADMIN_ID
        and update.effective_user.id != DISPATCHER_ID
    ):
        return

    total = len(orders)

    new = 0
    accepted = 0
    process = 0
    done = 0
    cancel = 0
    reject = 0

    for order in orders.values():

        status = order["status"]

        if status == "new":
            new += 1

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
        f"📋 Жами: {total}\n"
        f"🆕 Янги: {new}\n"
        f"🟡 Қабул қилинган: {accepted}\n"
        f"🔵 Иш жараёнида: {process}\n"
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор қилинган: {cancel}\n"
        f"🚫 Рад этилган: {reject}\n"
        f"⭐ Баҳо берилган: {len(reviews)}"
    )


# ============================================================
# BROADCAST
# ============================================================

async def send_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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

    msg = " ".join(context.args)

    customer_ids = set()

    for order in orders.values():

        customer_id = order.get("customer_id")

        if customer_id:
            customer_ids.add(customer_id)

    count = 0

    for customer_id in customer_ids:

        try:

            await context.bot.send_message(
                chat_id=customer_id,
                text=msg,
            )

            count += 1

        except Exception as e:

            logger.error(
                f"Broadcast error {customer_id}: {e}"
            )

    await update.message.reply_text(
        "📢 ХАБАР ЮБОРИЛДИ\n\n"
        f"👥 {count} та мижозга юборилди."
    )


# ============================================================
# MY ORDERS - MASTER
# ============================================================

async def my_master_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    if uid not in masters and uid != ADMIN_ID:

        await update.message.reply_text(
            "❌ Сиз уста эмассиз."
        )

        return

    result = []

    for order in orders.values():

        if order.get("master_id") == uid:

            result.append(order)

    if not result:

        await update.message.reply_text(
            "📋 Сизга бириктирилган буюртмалар йўқ.",
            reply_markup=master_menu(),
        )

        return

    text = "📋 МЕНИНГ БУЮРТМАЛАРИМ\n\n"

    for order in result:

        text += (
            f"🔢 №{order['id']}\n"
            f"👤 {order['name']}\n"
            f"🛠 {order['service']}\n"
            f"📍 {order['address']}\n"
            f"📌 {STATUS.get(order['status'])}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=master_menu(),
    )


# ============================================================
# MASTER STATISTICS
# ============================================================

async def master_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    if uid not in masters:

        await update.message.reply_text(
            "❌ Сиз уста сифатида рўйхатдан ўтмагансиз."
        )

        return

    total = 0
    done = 0
    process = 0
    cancel = 0
    rating_sum = 0
    rating_count = 0

    for order in orders.values():

        if order.get("master_id") != uid:
            continue

        total += 1

        if order["status"] == "done":
            done += 1

        elif order["status"] == "process":
            process += 1

        elif order["status"] == "cancel":
            cancel += 1

        if order.get("review"):

            rating_sum += order["review"]
            rating_count += 1

    rating = (
        round(rating_sum / rating_count, 1)
        if rating_count
        else 0
    )

    await update.message.reply_text(
        "📊 МЕНИНГ СТАТИСТИКАМ\n\n"
        f"📋 Жами буюртма: {total}\n"
        f"🔵 Ишда: {process}\n"
        f"✅ Якунланган: {done}\n"
        f"❌ Бекор: {cancel}\n"
        f"⭐ Ўртача баҳо: {rating}/5"
    )


# ============================================================
# DISPATCHER: NEW ORDERS
# ============================================================

async def dispatcher_new_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    if uid != ADMIN_ID and uid != DISPATCHER_ID:

        await update.message.reply_text(
            "❌ Рухсат йўқ."
        )

        return

    new_orders = [
        o
        for o in orders.values()
        if o["status"] == "new"
    ]

    if not new_orders:

        await update.message.reply_text(
            "🆕 Янги буюртмалар йўқ.",
            reply_markup=dispatcher_menu(),
        )

        return

    for order in new_orders:

        await update.message.reply_text(
            format_order(order),
            reply_markup=order_keyboard(order["id"]),
        )


# ============================================================
# DISPATCHER: ALL ORDERS
# ============================================================

async def dispatcher_all_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    uid = update.effective_user.id

    if uid != ADMIN_ID and uid != DISPATCHER_ID:
        return

    if not orders:

        await update.message.reply_text(
            "📋 Буюртмалар йўқ."
        )

        return

    for order in list(orders.values())[-20:]:

        await update.message.reply_text(
            format_order(order)
        )


# ============================================================
# ADMIN BUTTON ROUTER
# ============================================================

async def admin_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return False

    if update.effective_user.id != ADMIN_ID:
        return False

    text = update.message.text or ""

    if text == "👤 Мижозлар":

        await customer_base(update, context)
        return True

    if text == "👨‍🔧 Усталар":

        await update.message.reply_text(
            "👨‍🔧 УСТАЛАР БОШҚАРУВИ",
            reply_markup=masters_menu(),
        )

        return True

    if text == "➕ Уста қўшиш":

        await add_master_start(update, context)
        return True

    if text == "👨‍🔧 Усталар рўйхати":

        await masters_list(update, context)
        return True

    if text == "🗑 Устани ўчириш":

        await delete_master_start(update, context)
        return True

    if text == "📊 Статистика":

        await statistics(update, context)
        return True

    if text == "📢 Хабар тарқатиш":

        await update.message.reply_text(
            "📢 Хабар юбориш:\n\n"
            "/send Хабар матни"
        )

        return True

    if text == "⬅️ Админ меню":

        await update.message.reply_text(
            "👑 USTA 24 АДМИН",
            reply_markup=admin_menu(),
        )

        return True

    if text == "⬅️ Бош меню":

        await update.message.reply_text(
            "🏠 Асосий меню:",
            reply_markup=client_menu(),
        )

        return True

    return False


# ============================================================
# DISPATCHER ROUTER
# ============================================================

async def dispatcher_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return False

    uid = update.effective_user.id

    if uid != ADMIN_ID and uid != DISPATCHER_ID:
        return False

    text = update.message.text or ""

    if text == "📋 Янги буюртмалар":

        await dispatcher_new_orders(update, context)
        return True

    if text == "📋 Барча буюртмалар":

        await dispatcher_all_orders(update, context)
        return True

    if text == "📊 Статистика":

        await statistics(update, context)
        return True

    if text == "⬅️ Бош меню":

        await update.message.reply_text(
            "🏠 Асосий меню:",
            reply_markup=client_menu(),
        )

        return True

    return False


# ============================================================
# MASTER ROUTER
# ============================================================

async def master_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return False

    uid = update.effective_user.id

    if uid not in masters:
        return False

    text = update.message.text or ""

    if text == "📋 Менинг буюртмаларим":

        await my_master_orders(update, context)
        return True

    if text == "📊 Менинг статистикам":

        await master_statistics(update, context)
        return True

    if text == "⬅️ Бош меню":

        await update.message.reply_text(
            "🏠 Асосий меню:",
            reply_markup=client_menu(),
        )

        return True

    return False


# ============================================================
# ALL TEXT ROUTER
# ============================================================

async def all_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    uid = update.effective_user.id

    # --------------------------------------------------------
    # ADMIN ACTIVE OPERATIONS
    # --------------------------------------------------------

    if uid == ADMIN_ID:

        if context.user_data.get("master_add"):

            await add_master_handler(
                update,
                context,
            )

            return

        if context.user_data.get("delete_master"):

            await delete_master_handler(
                update,
                context,
            )

            return

    # --------------------------------------------------------
    # ADMIN MENU
    # --------------------------------------------------------

    if uid == ADMIN_ID:

        handled = await admin_router(
            update,
            context,
        )

        if handled:
            return

    # --------------------------------------------------------
    # DISPATCHER
    # --------------------------------------------------------

    if uid == DISPATCHER_ID:

        handled = await dispatcher_router(
            update,
            context,
        )

        if handled:
            return

    # --------------------------------------------------------
    # MASTER
    # --------------------------------------------------------

    if uid in masters:

        handled = await master_router(
            update,
            context,
        )

        if handled:
            return

    # --------------------------------------------------------
    # CLIENT
    # --------------------------------------------------------

    await client_handler(
        update,
        context,
    )


# ============================================================
# CONTACT / LOCATION
# ============================================================

async def contact_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    # Telegram contact request works in private chat.
    # This prevents "Phone number can be requested in private chats only".

    if update.effective_chat.type != "private":

        await update.message.reply_text(
            "📞 Телефон рақамини бот билан шахсий чатда юборинг."
        )

        return

    await client_handler(
        update,
        context,
    )


async def location_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    if update.effective_chat.type != "private":

        return

    await client_handler(
        update,
        context,
    )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    data = query.data or ""

    # ALL ORDER CALLBACKS
    if data.startswith(
        (
            "accept_",
            "reject_",
            "start_",
            "done_",
            "cancel_",
            "redispatch_",
            "rate_",
        )
    ):

        await order_callback(
            update,
            context,
        )

        return


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.error(
        "Telegram bot error",
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

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_start,
        )
    )

    application.add_handler(
        CommandHandler(
            "dispatcher",
            dispatcher_start,
        )
    )

    application.add_handler(
        CommandHandler(
            "master",
            master_start,
        )
    )

    application.add_handler(
        CommandHandler(
            "send",
            send_command,
        )
    )

    # --------------------------------------------------------
    # CALLBACK
    # --------------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            callback_router,
        )
    )

    # --------------------------------------------------------
    # CONTACT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.CONTACT,
            contact_handler,
        )
    )

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.LOCATION,
            location_handler,
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            all_text_handler,
        )
    )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

    application.add_error_handler(
        error_handler,
    )

    # --------------------------------------------------------
    # FLASK
    # --------------------------------------------------------

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    print(
        "========================================"
    )

    print(
        "       USTA 24 BOT ISHLADI"
    )

    print(
        "========================================"
    )

    application.run_polling(
        drop_pending_updates=True,
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
