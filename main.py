import os, logging, asyncio
from typing import Optional
import asyncpg
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters

# USTA 24 ANDIJON - one-file Telegram bot
# Python 3.11+ / python-telegram-bot 22.3 / PostgreSQL asyncpg
BOT_TOKEN=os.getenv('BOT_TOKEN','').strip()
DATABASE_URL=os.getenv('DATABASE_URL','').strip()
ADMIN_ID=int(os.getenv('ADMIN_ID','0') or 0)
DISPATCHER_ID=int(os.getenv('DISPATCHER_ID','0') or 0)
MASTERS_GROUP_ID=int(os.getenv('MASTERS_GROUP_ID','0') or 0)
DISPATCHER_PHONE=os.getenv('DISPATCHER_PHONE','+998770690003').strip()
if not BOT_TOKEN or not DATABASE_URL or not ADMIN_ID or not MASTERS_GROUP_ID:
    raise RuntimeError('BOT_TOKEN, DATABASE_URL, ADMIN_ID, MASTERS_GROUP_ID required')
logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | USTA24 | %(message)s')
log=logging.getLogger('usta24'); pool: Optional[asyncpg.Pool]=None; app=None

CLIENT,MASTER,DISPATCHER,ADMIN='client','master','dispatcher','admin'
NEW,SEARCHING,ACCEPTED,ONWAY,ARRIVED,STARTED,PAUSED,PAYMENT,DONE,CANCELLED='new','searching','accepted','on_way','arrived','started','paused','payment','completed','cancelled'
CAT={'🪑 Мебель':'Мебель','🍽 Кухня':'Кухня','🚪 Шкаф':'Шкаф','🛏 Кровать':'Кровать','🪑 Стол / стул':'Стол/стул','🛋 Диван':'Диван','🚚 Мебель ташиш':'Мебель ташиш','🏠 Уй кўчириш':'Уй кўчириш'}
ORDER_STATES=range(7); STAFF_STATES=range(7,9); REJECT_STATE=9; FINISH_PHOTO=10; FINISH_NOTE=11

def disp(): return f'🎧 Диспетчер: 📞 {DISPATCHER_PHONE}'
def se(s): return {'new':'🟡','searching':'🔎','accepted':'🔵','on_way':'🚗','arrived':'📍','started':'🔧','paused':'⏸','payment':'💰','completed':'🟢','cancelled':'🔴'}.get(s,'⚪')
def st(s): return {'new':'Янги','searching':'Уста қидирилмоқда','accepted':'Уста бириктирилди','on_way':'Йўлда','arrived':'Манзилга етди','started':'Иш бошланди','paused':'Танаффус','payment':'Тўлов кутилмоқда','completed':'Якунланган','cancelled':'Бекор қилинган'}.get(s,s)

def client_kb(): return ReplyKeyboardMarkup([['🛠 Уста чақириш','📋 Менинг буюртмаларим'],['👤 Профилим','ℹ️ Хизматлар'],['📞 Алоқа']],resize_keyboard=True)
def master_kb(): return ReplyKeyboardMarkup([['🆕 Янги буюртмалар','📋 Менинг буюртмаларим'],['🟢 Иш ҳолатим','📊 Статистика'],['👤 Профиль','📞 Диспетчер'],['🏠 Асосий меню']],resize_keyboard=True)
def disp_kb(): return ReplyKeyboardMarkup([['🆕 Янги буюртмалар','📋 Буюртмалар'],['👨‍🔧 Усталар','🔗 Бириктириш'],['📊 Статистика','📞 Диспетчер'],['🏠 Асосий меню']],resize_keyboard=True)
def admin_kb(): return ReplyKeyboardMarkup([['📊 Dashboard','👨‍🔧 Усталар'],['🎧 Dispatcherлар','👤 Мижозлар'],['📋 Буюртмалар','🛠 Хизматлар'],['💰 Нархлар','💰 Молия'],['📈 Статистика','➕ Ходим қўшиш'],['🏠 Асосий меню']],resize_keyboard=True)
def cancel_kb(): return ReplyKeyboardMarkup([['❌ Бекор қилиш']],resize_keyboard=True)

async def _has_column(conn, table, column):
    return await conn.fetchval("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = $1
              AND column_name = $2
        )
    """, table, column)


async def _ensure_columns(conn, table, columns):
    # Add missing columns safely. Existing old databases may not have an `id` column.
    # BIGSERIAL fills old rows and gives new rows an automatic id.
    for column, sql_type in columns.items():
        if not await _has_column(conn, table, column):
            if column == "id":
                await conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "id" BIGSERIAL')
            else:
                await conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}')


async def db_init():
    """Create/migrate the complete PostgreSQL schema before any queries run."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

    async with pool.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                telegram_id BIGINT,
                name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                username TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'client',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                specialty TEXT DEFAULT 'Барча хизматлар',
                is_active BOOLEAN DEFAULT TRUE,
                is_busy BOOLEAN DEFAULT FALSE
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS dispatchers (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT, master_id BIGINT, dispatcher_id BIGINT,
                service_category TEXT, service_name TEXT,
                customer_name TEXT, customer_phone TEXT, address TEXT,
                latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
                description TEXT, status TEXT DEFAULT 'new',
                reject_reason TEXT DEFAULT '',
                rejected_master_ids BIGINT[] DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                accepted_at TIMESTAMPTZ, started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ, updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS order_photos (
                id BIGSERIAL PRIMARY KEY, order_id BIGINT,
                photo_id TEXT, photo_type TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS order_history (
                id BIGSERIAL PRIMARY KEY, order_id BIGINT,
                old_status TEXT, new_status TEXT, changed_by BIGINT,
                note TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id BIGSERIAL PRIMARY KEY, order_id BIGINT,
                customer_id BIGINT, master_id BIGINT, rating INT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id BIGSERIAL PRIMARY KEY, category TEXT, name TEXT,
                description TEXT, price TEXT DEFAULT 'Келишилади',
                is_active BOOLEAN DEFAULT TRUE
            )
        """)

        await _ensure_columns(c, "users", {
            "id": "BIGSERIAL",
            "telegram_id": "BIGINT", "name": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''", "username": "TEXT DEFAULT ''",
            "role": "TEXT NOT NULL DEFAULT 'client'",
            "is_active": "BOOLEAN DEFAULT TRUE",
            "created_at": "TIMESTAMPTZ DEFAULT NOW()"
        })

        # Migrate legacy Telegram-ID columns only when they really exist.
        # IMPORTANT: never assume that users.id is an old Telegram ID.
        # Old databases can have a completely different schema.
        legacy_user_cols = ("telegram", "tg_id", "user_id_telegram", "telegram_user_id")
        for oldcol in legacy_user_cols:
            if await _has_column(c, "users", oldcol):
                await c.execute(
                    f'UPDATE users SET telegram_id="{oldcol}" '
                    f'WHERE telegram_id IS NULL AND "{oldcol}" IS NOT NULL'
                )

        await c.execute("""
            DELETE FROM users a USING users b
            WHERE a.telegram_id IS NOT NULL
              AND a.telegram_id=b.telegram_id AND a.id>b.id
        """)
        await c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS users_telegram_id_uq
            ON users(telegram_id)
        """)

        await _ensure_columns(c, "masters", {
            "id": "BIGSERIAL",
            "user_id": "BIGINT",
            "specialty": "TEXT DEFAULT 'Барча хизматлар'",
            "is_active": "BOOLEAN DEFAULT TRUE",
            "is_busy": "BOOLEAN DEFAULT FALSE"
        })
        await _ensure_columns(c, "dispatchers", {
            "id": "BIGSERIAL",
            "user_id": "BIGINT", "is_active": "BOOLEAN DEFAULT TRUE"
        })

        for table in ("masters", "dispatchers"):
            for oldcol in ("telegram_id", "tg_id"):
                if await _has_column(c, table, oldcol):
                    await c.execute(
                        f'UPDATE "{table}" s SET user_id=u.id '
                        f'FROM users u WHERE s.user_id IS NULL '
                        f'AND u.telegram_id=s."{oldcol}"'
                    )

        await c.execute("""
            DELETE FROM masters a USING masters b
            WHERE a.user_id IS NOT NULL
              AND a.user_id=b.user_id AND a.id>b.id
        """)
        await c.execute("""
            DELETE FROM dispatchers a USING dispatchers b
            WHERE a.user_id IS NOT NULL
              AND a.user_id=b.user_id AND a.id>b.id
        """)
        await c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS masters_user_id_uq
            ON masters(user_id)
        """)
        await c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS dispatchers_user_id_uq
            ON dispatchers(user_id)
        """)

        await _ensure_columns(c, "orders", {
            "id": "BIGSERIAL",
            "customer_id": "BIGINT", "master_id": "BIGINT",
            "dispatcher_id": "BIGINT", "service_category": "TEXT",
            "service_name": "TEXT", "customer_name": "TEXT",
            "customer_phone": "TEXT", "address": "TEXT",
            "latitude": "DOUBLE PRECISION", "longitude": "DOUBLE PRECISION",
            "description": "TEXT", "status": "TEXT DEFAULT 'new'",
            "reject_reason": "TEXT DEFAULT ''",
            "rejected_master_ids": "BIGINT[] DEFAULT '{}'",
            "created_at": "TIMESTAMPTZ DEFAULT NOW()",
            "accepted_at": "TIMESTAMPTZ", "started_at": "TIMESTAMPTZ",
            "completed_at": "TIMESTAMPTZ",
            "updated_at": "TIMESTAMPTZ DEFAULT NOW()"
        })

        legacy_order_map = {
            "customer_id": ("client_id", "user_id"),
            "master_id": ("usta_id", "master_user_id"),
            "customer_name": ("name",),
            "customer_phone": ("phone",),
            "service_name": ("service",),
            "description": ("details", "comment", "note")
        }
        for target, candidates in legacy_order_map.items():
            for oldcol in candidates:
                if await _has_column(c, "orders", oldcol):
                    await c.execute(
                        f'UPDATE orders SET "{target}"="{oldcol}" '
                        f'WHERE "{target}" IS NULL AND "{oldcol}" IS NOT NULL'
                    )
                    break

        await _ensure_columns(c, "order_photos", {
            "id": "BIGSERIAL",
            "order_id": "BIGINT", "photo_id": "TEXT",
            "photo_type": "TEXT", "created_at": "TIMESTAMPTZ DEFAULT NOW()"
        })
        await _ensure_columns(c, "order_history", {
            "id": "BIGSERIAL",
            "order_id": "BIGINT", "old_status": "TEXT",
            "new_status": "TEXT", "changed_by": "BIGINT",
            "note": "TEXT DEFAULT ''", "created_at": "TIMESTAMPTZ DEFAULT NOW()"
        })
        await _ensure_columns(c, "ratings", {
            "id": "BIGSERIAL",
            "order_id": "BIGINT", "customer_id": "BIGINT",
            "master_id": "BIGINT", "rating": "INT",
            "created_at": "TIMESTAMPTZ DEFAULT NOW()"
        })
        await _ensure_columns(c, "services", {
            "id": "BIGSERIAL",
            "category": "TEXT", "name": "TEXT", "description": "TEXT",
            "price": "TEXT DEFAULT 'Келишилади'",
            "is_active": "BOOLEAN DEFAULT TRUE"
        })

        await c.execute("""
            DELETE FROM ratings a USING ratings b
            WHERE a.order_id IS NOT NULL
              AND a.order_id=b.order_id AND a.id>b.id
        """)
        await c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ratings_order_id_uq
            ON ratings(order_id)
        """)

        required = {
            "users": ("id","telegram_id","name","phone","username","role","is_active","created_at"),
            "masters": ("id","user_id","specialty","is_active","is_busy"),
            "dispatchers": ("id","user_id","is_active"),
            "orders": ("id","customer_id","master_id","dispatcher_id","service_category",
                       "service_name","customer_name","customer_phone","address","latitude",
                       "longitude","description","status","reject_reason","rejected_master_ids",
                       "created_at","accepted_at","started_at","completed_at","updated_at"),
            "order_photos": ("id","order_id","photo_id","photo_type","created_at"),
            "order_history": ("id","order_id","old_status","new_status","changed_by","note","created_at"),
            "ratings": ("id","order_id","customer_id","master_id","rating","created_at"),
            "services": ("id","category","name","description","price","is_active")
        }
        missing = []
        for table, cols in required.items():
            for col in cols:
                if not await _has_column(c, table, col):
                    missing.append(f"{table}.{col}")
        if missing:
            raise RuntimeError("DATABASE MIGRATION FAILED: " + ", ".join(missing))

        if not await c.fetchval("SELECT COUNT(*) FROM services"):
            data = [
                ("Мебель","Мебель йиғиш","Шкаф, стол, стул ва бошқа мебель йиғиш"),
                ("Мебель","Мебель таъмирлаш","Мебель таъмири"),
                ("Мебель","Мебель демонтаж","Мебельни ечиш"),
                ("Мебель","Мебель монтаж","Мебель ўрнатиш"),
                ("Мебель","Мебель қайта йиғиш","Қайта йиғиш"),
                ("Кухня","Кухня йиғиш","Кухня гарнитурини йиғиш"),
                ("Кухня","Кухня таъмирлаш","Кухня мебель таъмири"),
                ("Кухня","Кухня демонтаж","Кухняни ечиш"),
                ("Кухня","Кухня монтаж","Кухняни ўрнатиш"),
                ("Кухня","Кухня ўрнатиш","Тўлиқ ўрнатиш"),
                ("Шкаф","Шкаф йиғиш","Шкаф йиғиш"),
                ("Шкаф","Шкаф таъмирлаш","Шкаф таъмири"),
                ("Шкаф","Шкаф демонтаж","Шкафни ечиш"),
                ("Шкаф","Шкаф монтаж","Шкаф ўрнатиш"),
                ("Шкаф","Купе шкаф","Купе шкаф хизмати"),
                ("Кровать","Кровать йиғиш","Кровать йиғиш"),
                ("Кровать","Кровать таъмирлаш","Кровать таъмири"),
                ("Кровать","Кровать демонтаж","Кроватьни ечиш"),
                ("Стол/стул","Стол/стул йиғиш","Стол ва стул йиғиш"),
                ("Стол/стул","Стол/стул таъмирлаш","Таъмирлаш"),
                ("Стол/стул","Стол/стул монтаж","Ўрнатиш"),
                ("Диван","Диван таъмирлаш","Диван таъмири"),
                ("Диван","Диван демонтаж","Диванни ечиш"),
                ("Диван","Диван йиғиш","Диван йиғиш"),
                ("Мебель ташиш","Уйдан уйга","Мебельни уйдан уйга ташиш"),
                ("Мебель ташиш","Машина билан","Машина билан ташиш"),
                ("Мебель ташиш","Юклаш","Юклаш хизмати"),
                ("Мебель ташиш","Тушириш","Тушириш хизмати"),
                ("Мебель ташиш","Тўлиқ ташиш хизмати","Юклаш+ташиш+тушириш"),
                ("Уй кўчириш","Қадоқлаш","Қадоқлаш"),
                ("Уй кўчириш","Ташиш","Ташиш"),
                ("Уй кўчириш","Юклаш","Юклаш"),
                ("Уй кўчириш","Тушириш","Тушириш"),
                ("Уй кўчириш","Тўлиқ кўчириш","Тўлиқ кўчириш")
            ]
            await c.executemany(
                "INSERT INTO services(category,name,description) VALUES($1,$2,$3)",
                data
            )

    await user_upsert(ADMIN_ID, "Admin", "", "", ADMIN)
    if DISPATCHER_ID:
        await user_upsert(DISPATCHER_ID, "Dispatcher", DISPATCHER_PHONE, "", DISPATCHER)
        async with pool.acquire() as c:
            await c.execute("""
                INSERT INTO dispatchers(user_id)
                SELECT id FROM users WHERE telegram_id=$1
                ON CONFLICT(user_id) DO UPDATE SET is_active=TRUE
            """, DISPATCHER_ID)
    log.info("PostgreSQL schema verified and migrated successfully")

async def user_upsert(tid,name='',phone='',username='',role=CLIENT):
 async with pool.acquire() as c:
  await c.execute(
   """
   INSERT INTO users (telegram_id, name, phone, username, role)
   VALUES ($1, $2, $3, $4, $5)
   ON CONFLICT (telegram_id) DO UPDATE SET
       name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE users.name END,
       phone = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE users.phone END,
       username = CASE WHEN EXCLUDED.username <> '' THEN EXCLUDED.username ELSE users.username END,
       role = CASE
           WHEN users.role = 'admin' THEN 'admin'
           WHEN EXCLUDED.role <> 'client' THEN EXCLUDED.role
           ELSE users.role
       END,
       is_active = TRUE
   """,
   tid, name, phone, username, role
  )
async def user(tid):
 async with pool.acquire() as c:return await c.fetchrow('SELECT * FROM users WHERE telegram_id=$1',tid)
async def role(tid):
 if tid==ADMIN_ID:return ADMIN
 u=await user(tid);return u['role'] if u and u['is_active'] else CLIENT

async def order_row(oid):
 async with pool.acquire() as c:return await c.fetchrow('''SELECT o.*,cu.telegram_id customer_tg,mu.telegram_id master_tg,mu.name master_name FROM orders o LEFT JOIN users cu ON cu.id=o.customer_id LEFT JOIN users mu ON mu.id=o.master_id WHERE o.id=$1''',oid)
async def photos(oid,typ=None):
 async with pool.acquire() as c:
  q='SELECT photo_id FROM order_photos WHERE order_id=$1'+(' AND photo_type=$2' if typ else '')+' ORDER BY id'
  rs=await c.fetch(q,oid,typ) if typ else await c.fetch(q,oid);return [r['photo_id'] for r in rs]
async def addphoto(oid,pid,typ):
 async with pool.acquire() as c:await c.execute('INSERT INTO order_photos(order_id,photo_id,photo_type) VALUES($1,$2,$3)',oid,pid,typ)
async def hist(oid,old,new,by,note=''):
 async with pool.acquire() as c:await c.execute('INSERT INTO order_history(order_id,old_status,new_status,changed_by,note) VALUES($1,$2,$3,$4,$5)',oid,old,new,by,note)
async def setstatus(oid,new,by,note=''):
 async with pool.acquire() as c:
  old=await c.fetchval('SELECT status FROM orders WHERE id=$1',oid)
  await c.execute('UPDATE orders SET status=$1,updated_at=NOW(),accepted_at=CASE WHEN $1=$2 THEN NOW() ELSE accepted_at END,started_at=CASE WHEN $1=$3 THEN NOW() ELSE started_at END,completed_at=CASE WHEN $1=$4 THEN NOW() ELSE completed_at END WHERE id=$5',new,ACCEPTED,STARTED,DONE,oid)
 await hist(oid,old,new,by,note)
async def create_order(o):
 async with pool.acquire() as c:
  oid=await c.fetchval('''INSERT INTO orders(customer_id,service_category,service_name,customer_name,customer_phone,address,latitude,longitude,description,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id''',o['customer_id'],o['category'],o['service'],o['name'],o['phone'],o['address'],o.get('lat'),o.get('lon'),o['desc'],SEARCHING)
 await hist(oid,None,SEARCHING,o['customer_id'],'Янги буюртма')
 for p in o['photos']:await addphoto(oid,p,'customer')
 return oid

async def format_order(oid):
 o=await order_row(oid);ps=await photos(oid,'customer')
 loc=f'<a href="https://maps.google.com/?q={o["latitude"]},{o["longitude"]}">📍 Локацияни очиш</a>' if o['latitude'] is not None else '📍 Локация: берилмаган'
 return (f'📢 <b>БУЮРТМА №{o["id"]}</b>\n\n🛠 Хизмат: {o["service_name"]}\n👤 Мижоз: {o["customer_name"]}\n📞 Телефон: {o["customer_phone"] or "-"}\n🏠 Манзил: {o["address"]}\n{loc}\n📝 Изоҳ: {o["description"] or "-"}\n📸 Расмлар: {len(ps)} та\n📌 Ҳолат: {se(o["status"])} {st(o["status"])}\n\n{disp()}')

def group_buttons(oid):return InlineKeyboardMarkup([[InlineKeyboardButton('✅ ҚАБУЛ ҚИЛИШ',callback_data=f'a:{oid}'),InlineKeyboardButton('❌ РАД ЭТИШ',callback_data=f'r:{oid}')]])
def rating_kb(oid):return InlineKeyboardMarkup([[InlineKeyboardButton(str(i)+'⭐',callback_data=f'rate:{oid}:{i}') for i in range(1,6)]])

def master_status_kb(oid,status):
 m={ACCEPTED:[('🚗 Йўлга чиқдим','on_way')],ONWAY:[('📍 Манзилга етдим','arrived')],ARRIVED:[('🔧 Ишни бошладим','started')],STARTED:[('⏸ Танаффус','paused'),('💰 Тўлов','payment')],PAUSED:[('▶️ Давом эттириш','started')],PAYMENT:[]}
 rows=[]
 if status in m:
  rows.append([InlineKeyboardButton(t,callback_data=f's:{oid}:{v}') for t,v in m[status]])
 if status in (STARTED,PAYMENT):rows.append([InlineKeyboardButton('🟢 Ишни якунлаш',callback_data=f'f:{oid}')])
 return InlineKeyboardMarkup(rows) if rows else None

async def post_group(oid):
 txt=await format_order(oid);ps=await photos(oid,'customer')
 try:
  if ps:
   await app.bot.send_photo(MASTERS_GROUP_ID,ps[0],caption=txt,parse_mode='HTML',reply_markup=group_buttons(oid))
   for p in ps[1:]:await app.bot.send_photo(MASTERS_GROUP_ID,p)
  else:await app.bot.send_message(MASTERS_GROUP_ID,txt,parse_mode='HTML',reply_markup=group_buttons(oid))
 except Exception:log.exception('group post failed')
async def notify(tid,text,markup=None):
 try:await app.bot.send_message(tid,text,reply_markup=markup)
 except Exception:log.exception('notify failed')

# CLIENT ORDER FLOW
async def svc_categories(update,context):
 kb=[[InlineKeyboardButton(x,callback_data='cat:'+c)] for x,c in CAT.items()]
 kb.append([InlineKeyboardButton('🔧 Бошқа хизмат',callback_data='custom')])
 await update.message.reply_text('🛠 Хизмат турини танланг:',reply_markup=InlineKeyboardMarkup(kb))
async def cat_cb(update,context):
 q=update.callback_query;await q.answer();cat=q.data[4:]
 async with pool.acquire() as c:rs=await c.fetch('SELECT id,name,price FROM services WHERE category=$1 AND is_active=TRUE ORDER BY id',cat)
 await q.message.edit_text(f'📋 {cat} хизматлари:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f'🛠 {r["name"]} — {r["price"]}',callback_data=f'svc:{r["id"]}')] for r in rs]+[[InlineKeyboardButton('⬅️ Орқага',callback_data='cats')]]))
async def svc_cb(update,context):
 q=update.callback_query;await q.answer();sid=int(q.data[4:])
 async with pool.acquire() as c:r=await c.fetchrow('SELECT * FROM services WHERE id=$1',sid)
 u=await user(q.from_user.id);context.user_data['o']={'customer_id':u['id'],'category':r['category'],'service':r['name'],'name':u['name'] or q.from_user.full_name,'phone':u['phone'] or '','address':'','lat':None,'lon':None,'desc':'','photos':[]}
 await q.message.reply_text(f'🛠 {r["name"]}\n\n👤 Исмингизни юборинг:',reply_markup=cancel_kb());return 0
async def custom_cb(update,context):
 q=update.callback_query;await q.answer();u=await user(q.from_user.id);context.user_data['o']={'customer_id':u['id'],'category':'Бошқа','service':'','name':u['name'] or q.from_user.full_name,'phone':u['phone'] or '','address':'','lat':None,'lon':None,'desc':'','photos':[]};context.user_data['custom']=True
 await q.message.reply_text('🔧 Қандай хизмат керак? Ёзинг:',reply_markup=cancel_kb());return 6
async def custom_text(update,context):
 o=context.user_data['o'];o['service']=update.message.text[:200];o['desc']=o['service'];await update.message.reply_text('👤 Исмингизни юборинг:',reply_markup=cancel_kb());return 0
async def oname(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 context.user_data['o']['name']=update.message.text[:100]
 await update.message.reply_text('📞 Телефонни юборинг:',reply_markup=ReplyKeyboardMarkup([[KeyboardButton('📞 Телефонни юбориш',request_contact=True)],['❌ Бекор қилиш']],resize_keyboard=True));return 1
async def ophone(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 p=update.message.contact.phone_number if update.message.contact else update.message.text.strip();context.user_data['o']['phone']=p;await user_upsert(update.effective_user.id,update.effective_user.full_name,p,update.effective_user.username or '',CLIENT)
 await update.message.reply_text('📍 Геолокацияни юборинг:',reply_markup=ReplyKeyboardMarkup([[KeyboardButton('📍 Локацияни юбориш',request_location=True)],['⏭ Манзилни матн билан ёзиш'],['❌ Бекор қилиш']],resize_keyboard=True));return 2
async def oloc(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 if update.message.location:context.user_data['o']['lat']=update.message.location.latitude;context.user_data['o']['lon']=update.message.location.longitude
 await update.message.reply_text('🏠 Манзилни ёзинг:',reply_markup=cancel_kb());return 3
async def oaddr(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 context.user_data['o']['address']=update.message.text[:500]
 if not context.user_data['o']['desc']:await update.message.reply_text('📝 Муаммо/изоҳни ёзинг:',reply_markup=cancel_kb());return 4
 await update.message.reply_text('📸 Расм юборинг. Камида 1 та тавсия қилинади. Тугатганда «✅ Расмларни тугатиш».',reply_markup=ReplyKeyboardMarkup([['✅ Расмларни тугатиш'],['❌ Бекор қилиш']],resize_keyboard=True));return 5
async def odesc(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 context.user_data['o']['desc']=update.message.text[:2000];await update.message.reply_text('📸 Расм юборинг. Тугатганда «✅ Расмларни тугатиш».',reply_markup=ReplyKeyboardMarkup([['✅ Расмларни тугатиш'],['❌ Бекор қилиш']],resize_keyboard=True));return 5
async def ophotos(update,context):
 if update.message.text=='❌ Бекор қилиш':return await cancel_conv(update,context)
 if update.message.photo:
  context.user_data['o']['photos'].append(update.message.photo[-1].file_id);await update.message.reply_text(f'📸 Қабул қилинди: {len(context.user_data["o"]["photos"])} та');return 5
 if update.message.text=='✅ Расмларни тугатиш':return await confirm_order(update,context)
 await update.message.reply_text('📸 Расм юборинг ёки тугатиш тугмасини босинг.');return 5
async def confirm_order(update,context):
 o=context.user_data['o'];txt=f'👀 <b>БУЮРТМАНИ ТЕКШИРИНГ</b>\n\n🛠 {o["service"]}\n👤 {o["name"]}\n📞 {o["phone"]}\n🏠 {o["address"]}\n📝 {o["desc"] or "-"}\n📸 {len(o["photos"])} та\n\n{disp()}'
 await update.message.reply_text(txt,parse_mode='HTML',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✏️ Таҳрир',callback_data='edit')],[InlineKeyboardButton('❌ Бекор қилиш',callback_data='cancel_form')],[InlineKeyboardButton('✅ ТАСДИҚЛАШ',callback_data='submit')]]));return 6
async def order_cb(update,context):
 q=update.callback_query;await q.answer()
 if q.data=='cancel_form':return await cancel_conv(update,context)
 if q.data=='submit':
  o=context.user_data.get('o');oid=await create_order(o);context.user_data.pop('o',None);await q.message.edit_text(f'✅ Буюртма №{oid} қабул қилинди!\n📌 🔎 Уста қидирилмоқда\n\n{disp()}');await post_group(oid);await q.message.reply_text('📢 Буюртма усталарга юборилди.',reply_markup=client_kb());return ConversationHandler.END
 await q.message.reply_text('✏️ Таҳрирлаш учун қайта киритиш мумкин: /start');return 6
async def cancel_conv(update,context):
 context.user_data.pop('o',None);context.user_data.pop('custom',None)
 msg=update.message or update.callback_query.message;await msg.reply_text('❌ Бекор қилинди.',reply_markup=client_kb());return ConversationHandler.END

# MASTER accept/reject/status
async def accept_cb(update,context):
 q=update.callback_query;await q.answer()
 if await role(q.from_user.id)!=MASTER:return await q.answer('❌ Фақат уста.',show_alert=True)
 oid=int(q.data[2:])
 async with pool.acquire() as c:
  async with c.transaction():
   o=await c.fetchrow('SELECT * FROM orders WHERE id=$1 FOR UPDATE',oid)
   u=await c.fetchrow('SELECT u.id,m.is_busy,m.is_active FROM users u JOIN masters m ON m.user_id=u.id WHERE u.telegram_id=$1 FOR UPDATE',q.from_user.id)
   if not o or not u or not u['is_active'] or u['is_busy'] or o['status'] not in (NEW,SEARCHING):return await q.answer('❌ Буюртма банд ёки аллақачон қабул қилинган.',show_alert=True)
   rej=o['rejected_master_ids'] or []
   if u['id'] in rej:return await q.answer('❌ Сиз бу буюртмани аввал рад этгансиз.',show_alert=True)
   await c.execute('UPDATE orders SET master_id=$1,status=$2,accepted_at=NOW() WHERE id=$3',u['id'],ACCEPTED,oid);await c.execute('UPDATE masters SET is_busy=TRUE WHERE user_id=$1',u['id'])
 await hist(oid,SEARCHING,ACCEPTED,(await user(q.from_user.id))['id'],'Уста қабул қилди');await q.message.edit_reply_markup(reply_markup=None);o=await order_row(oid)
 await notify(o['customer_tg'],f'🔵 Буюртма №{oid} қабул қилинди!\n👨‍🔧 Уста: {o["master_name"]}\n{disp()}')
 await q.message.reply_text(f'✅ №{oid} қабул қилинди.\n{disp()}');
async def reject_cb(update,context):
 q=update.callback_query;await q.answer();context.user_data['reject']=int(q.data[2:]);await q.message.reply_text('❌ Рад этиш сабабини ёзинг:',reply_markup=cancel_kb());return REJECT_STATE
async def reject_text(update,context):
 if update.message.text=='❌ Бекор қилиш':context.user_data.pop('reject',None);await update.message.reply_text('Бекор қилинди.',reply_markup=master_kb());return ConversationHandler.END
 oid=context.user_data.pop('reject');reason=update.message.text[:500];u=await user(update.effective_user.id)
 async with pool.acquire() as c:
  o=await c.fetchrow('SELECT * FROM orders WHERE id=$1 FOR UPDATE',oid)
  if not o or o['status'] not in (NEW,SEARCHING):await update.message.reply_text('❌ Бу буюртма энди мавжуд эмас.',reply_markup=master_kb());return ConversationHandler.END
  rej=list(o['rejected_master_ids'] or []);rej.append(u['id']);await c.execute('UPDATE orders SET rejected_master_ids=$1,reject_reason=$2,status=$3 WHERE id=$4',rej,reason,SEARCHING,oid)
 await hist(oid,SEARCHING,SEARCHING,u['id'],'Рад этилди: '+reason);await update.message.reply_text(f'❌ Рад этилди. №{oid} қайта группага чиқади.',reply_markup=master_kb());await post_group(oid);return ConversationHandler.END
async def status_cb(update,context):
 q=update.callback_query;await q.answer();_,oid_s,new=q.data.split(':');oid=int(oid_s);o=await order_row(oid)
 if not o or o['master_tg']!=q.from_user.id:return await q.answer('❌ Бу буюртма сизга тегишли эмас.',show_alert=True)
 allowed={ACCEPTED:[ONWAY],ONWAY:[ARRIVED],ARRIVED:[STARTED],STARTED:[PAUSED,PAYMENT],PAUSED:[STARTED]}
 if new not in allowed.get(o['status'],[]):return await q.answer('❌ Нотўғри ҳолат.',show_alert=True)
 await setstatus(oid,new,(await user(q.from_user.id))['id']);await notify(o['customer_tg'],f'📋 №{oid}\n📌 {se(new)} {st(new)}\n\n{disp()}');await q.message.reply_text(f'№{oid}: {se(new)} {st(new)}',reply_markup=master_status_kb(oid,new))
async def finish_cb(update,context):
 q=update.callback_query;await q.answer();oid=int(q.data[2:]);o=await order_row(oid)
 if not o or o['master_tg']!=q.from_user.id:return await q.answer('❌ Бу сизники эмас.',show_alert=True)
 if o['status'] not in (STARTED,PAYMENT):return await q.answer('❌ Ҳозир якунлаб бўлмайди.',show_alert=True)
 context.user_data['finish']=oid;await q.message.reply_text('📸 Иш натижасининг якуний расмини юборинг:',reply_markup=cancel_kb());return FINISH_PHOTO
async def finish_photo(update,context):
 if update.message.text=='❌ Бекор қилиш':context.user_data.pop('finish',None);await update.message.reply_text('Бекор қилинди.',reply_markup=master_kb());return ConversationHandler.END
 if not update.message.photo:return await update.message.reply_text('📸 Расм мажбурий.')
 context.user_data['finish_photo']=update.message.photo[-1].file_id;await update.message.reply_text('📝 Изоҳ ёзинг ёки «⏭ Изоҳсиз»:',reply_markup=ReplyKeyboardMarkup([['⏭ Изоҳсиз'],['❌ Бекор қилиш']],resize_keyboard=True));return FINISH_NOTE
async def finish_note(update,context):
 if update.message.text=='❌ Бекор қилиш':context.user_data.pop('finish',None);context.user_data.pop('finish_photo',None);await update.message.reply_text('Бекор қилинди.',reply_markup=master_kb());return ConversationHandler.END
 oid=context.user_data.pop('finish');pid=context.user_data.pop('finish_photo');note='' if update.message.text=='⏭ Изоҳсиз' else update.message.text[:1000];o=await order_row(oid)
 await addphoto(oid,pid,'completion');await setstatus(oid,DONE,(await user(update.effective_user.id))['id'],note)
 async with pool.acquire() as c:await c.execute('UPDATE masters SET is_busy=FALSE WHERE user_id=$1',o['master_id'])
 await notify(o['customer_tg'],f'🎉 Буюртма №{oid} якунланди!\n👨‍🔧 Уста: {o["master_name"]}\n📸 Иш натижаси расм билан қабул қилинди.\n\n{disp()}\n\n⭐ Баҳоланг:',rating_kb(oid))
 await app.bot.send_photo(MASTERS_GROUP_ID,pid,caption=f'🎉 БУЮРТМА ЯКУНЛАНДИ №{oid}\n🛠 {o["service_name"]}\n👤 {o["customer_name"]}\n👨‍🔧 {o["master_name"]}\n📝 {note or "-"}\n{disp()}')
 await update.message.reply_text('🟢 Иш якунланди ва расм сақланди.',reply_markup=master_kb());return ConversationHandler.END
async def rate_cb(update,context):
 q=update.callback_query;await q.answer();_,oid,r=q.data.split(':');o=await order_row(int(oid))
 if not o or o['customer_tg']!=q.from_user.id:return await q.answer('❌',show_alert=True)
 async with pool.acquire() as c:await c.execute('INSERT INTO ratings(order_id,customer_id,master_id,rating) VALUES($1,$2,$3,$4) ON CONFLICT(order_id) DO UPDATE SET rating=$4',int(oid),o['customer_id'],o['master_id'],int(r))
 await q.message.edit_text(f'✅ Раҳмат! №{oid} учун {r}⭐ қабул қилинди.')

# ADMIN staff
async def staff_start(update,context):
 if await role(update.effective_user.id)!=ADMIN:return
 context.user_data['staff_role']=MASTER if update.message.text=='👨‍🔧 Уста қўшиш' else DISPATCHER
 await update.message.reply_text('📞 Ходимнинг Telegram контактини юборинг. ID ни қўлда киритиш шарт эмас.',reply_markup=ReplyKeyboardMarkup([[KeyboardButton('📞 Контактни юбориш',request_contact=True)],['❌ Бекор қилиш']],resize_keyboard=True));return 0
async def staff_contact(update,context):
 if update.message.text=='❌ Бекор қилиш':await update.message.reply_text('Бекор қилинди.',reply_markup=admin_kb());return ConversationHandler.END
 if not update.message.contact or not update.message.contact.user_id:return await update.message.reply_text('❌ Telegram контакт юборинг.')
 c=update.message.contact;context.user_data['staff_contact']=(c.user_id,c.first_name or '',c.phone_number or '')
 if context.user_data['staff_role']==MASTER:await update.message.reply_text('🛠 Мутахассислигини ёзинг:',reply_markup=cancel_kb());return 1
 return await save_staff(update,context,'Барча хизматлар')
async def staff_specialty(update,context):
 if update.message.text=='❌ Бекор қилиш':context.user_data.clear();await update.message.reply_text('Бекор қилинди.',reply_markup=admin_kb());return ConversationHandler.END
 return await save_staff(update,context,update.message.text[:200])
async def save_staff(update,context,specialty):
 tid,name,phone=context.user_data['staff_contact'];rr=context.user_data['staff_role'];await user_upsert(tid,name,phone,'',rr);u=await user(tid)
 async with pool.acquire() as c:
  if rr==MASTER:await c.execute("INSERT INTO masters(user_id,specialty) VALUES($1,$2) ON CONFLICT(user_id) DO UPDATE SET specialty=$2,is_active=TRUE",u['id'],specialty)
  else:await c.execute("INSERT INTO dispatchers(user_id) VALUES($1) ON CONFLICT(user_id) DO UPDATE SET is_active=TRUE",u['id'])
 await notify(tid,f'🎉 USTA 24 га {"👨‍🔧 Уста" if rr==MASTER else "🎧 Dispatcher"} сифатида қўшилдингиз. /start босинг.')
 context.user_data.pop('staff_contact',None);context.user_data.pop('staff_role',None);await update.message.reply_text('✅ Ходим қўшилди.',reply_markup=admin_kb());return ConversationHandler.END

# COMMON
async def start(update,context):
 tid=update.effective_user.id;r=await role(tid);await user_upsert(tid,update.effective_user.full_name,'',update.effective_user.username or '',r)
 if r==ADMIN:await update.message.reply_text('👑 USTA 24 ADMIN',reply_markup=admin_kb())
 elif r==MASTER:await update.message.reply_text('👨‍🔧 USTA 24 — УСТА',reply_markup=master_kb())
 elif r==DISPATCHER:await update.message.reply_text('🎧 USTA 24 — DISPATCHER',reply_markup=disp_kb())
 else:await update.message.reply_text('👤 USTA 24 ANDIJON\nУста чақириш учун хизматни танланг.',reply_markup=client_kb())
async def home(update,context):
 r=await role(update.effective_user.id);await update.message.reply_text('🏠 Асосий меню',reply_markup=admin_kb() if r==ADMIN else master_kb() if r==MASTER else disp_kb() if r==DISPATCHER else client_kb())
async def services(update,context):
 kb=[[InlineKeyboardButton(x,callback_data='icat:'+c)] for x,c in CAT.items()];await update.message.reply_text('ℹ️ ХИЗМАТЛАР',reply_markup=InlineKeyboardMarkup(kb))
async def icat_cb(update,context):
 q=update.callback_query;await q.answer();cat=q.data[5:]
 async with pool.acquire() as c:rs=await c.fetch('SELECT name,description,price FROM services WHERE category=$1 AND is_active=TRUE',cat)
 text=f'📋 {cat}\n\n'+''.join(f'🛠 {r["name"]}\n{r["description"]}\n💰 {r["price"]}\n\n' for r in rs);await q.message.edit_text(text[:4000],reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Орқага',callback_data='icats')]]))
async def icats_cb(update,context):
 q=update.callback_query;await q.answer();kb=[[InlineKeyboardButton(x,callback_data='icat:'+c)] for x,c in CAT.items()];await q.message.edit_text('ℹ️ ХИЗМАТЛАР',reply_markup=InlineKeyboardMarkup(kb))
async def profile(update,context):
 u=await user(update.effective_user.id);await update.message.reply_text(f'👤 ПРОФИЛЬ\n\n👤 {u["name"]}\n📞 {u["phone"] or "-"}\n🔐 {u["role"]}')
async def contact(update,context):await update.message.reply_text(f'📞 АЛОҚА\n\n{disp()}')
async def list_orders(update,context):
 r=await role(update.effective_user.id)
 async with pool.acquire() as c:
  if r==CLIENT:rs=await c.fetch('SELECT o.id,o.service_name,o.status FROM orders o JOIN users u ON u.id=o.customer_id WHERE u.telegram_id=$1 ORDER BY o.id DESC LIMIT 30',update.effective_user.id)
  elif r==MASTER:rs=await c.fetch('SELECT o.id,o.service_name,o.status FROM orders o JOIN users u ON u.id=o.master_id WHERE u.telegram_id=$1 ORDER BY o.id DESC LIMIT 30',update.effective_user.id)
  else:rs=await c.fetch('SELECT id,service_name,status FROM orders ORDER BY id DESC LIMIT 50')
 if not rs:return await update.message.reply_text('📭 Буюртмалар йўқ.')
 await update.message.reply_text('📋 БУЮРТМАЛАР',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f'№{x["id"]} {se(x["status"])} {x["service_name"][:25]}',callback_data=f'view:{x["id"]}')] for x in rs]))
async def view_cb(update,context):
 q=update.callback_query;await q.answer();oid=int(q.data[5:]);o=await order_row(oid);r=await role(q.from_user.id)
 if not o:return
 if r==CLIENT and o['customer_tg']!=q.from_user.id or r==MASTER and o['master_tg']!=q.from_user.id: return await q.answer('❌ Ҳуқуқ йўқ.',show_alert=True)
 kb=master_status_kb(oid,o['status']) if r==MASTER else rating_kb(oid) if r==CLIENT and o['status']==DONE else None;await q.message.reply_text(await format_order(oid),parse_mode='HTML',reply_markup=kb)
async def stats(update,context):
 async with pool.acquire() as c:x=await c.fetchrow("SELECT COUNT(*) total,COUNT(*) FILTER(WHERE status IN('new','searching')) new,COUNT(*) FILTER(WHERE status IN('accepted','on_way','arrived','started','paused','payment')) active,COUNT(*) FILTER(WHERE status='completed') done FROM orders")
 await update.message.reply_text(f'📊 СТАТИСТИКА\n\n📋 {x["total"]}\n🆕 {x["new"]}\n🔧 {x["active"]}\n🟢 {x["done"]}')

async def admin_router(update,context):
 t=update.message.text
 if t=='📊 Dashboard':await stats(update,context)
 elif t=='👨‍🔧 Усталар':
  async with pool.acquire() as c:rs=await c.fetch('SELECT u.name,u.phone,m.specialty,m.is_busy FROM users u JOIN masters m ON m.user_id=u.id ORDER BY u.name')
  await update.message.reply_text('👨‍🔧 УСТАЛАР\n\n'+''.join(f'👨‍🔧 {r["name"]}\n📞 {r["phone"]}\n🛠 {r["specialty"]}\n{"🔴 Банд" if r["is_busy"] else "🟢 Бўш"}\n\n' for r in rs)[:4000],reply_markup=admin_kb())
 elif t=='🎧 Dispatcherлар':
  async with pool.acquire() as c:rs=await c.fetch('SELECT u.name,u.phone FROM users u JOIN dispatchers d ON d.user_id=u.id')
  await update.message.reply_text('🎧 DISPATCHERЛАР\n\n'+''.join(f'{r["name"]} — {r["phone"] or DISPATCHER_PHONE}\n' for r in rs)+f'\nАсосий рақам: {DISPATCHER_PHONE}',reply_markup=admin_kb())
 elif t=='👤 Мижозлар':
  async with pool.acquire() as c:rs=await c.fetch("SELECT name,phone FROM users WHERE role='client' ORDER BY id DESC LIMIT 50")
  await update.message.reply_text('👤 МИЖОЗЛАР\n\n'+''.join(f'{r["name"]} — {r["phone"] or "-"}\n' for r in rs)[:4000],reply_markup=admin_kb())
 elif t=='📋 Буюртмалар':await list_orders(update,context)
 elif t=='🛠 Хизматлар':await services(update,context)
 elif t in ('💰 Нархлар','💰 Молия'):await update.message.reply_text('💰 Нархлар «Келишилади». Аниқ сумма буюртма бўйича келишилади.',reply_markup=admin_kb())
 elif t=='📈 Статистика':await stats(update,context)
 elif t=='➕ Ходим қўшиш':await update.message.reply_text('Қайси ходим?',reply_markup=ReplyKeyboardMarkup([['👨‍🔧 Уста қўшиш'],['🎧 Dispatcher қўшиш'],['❌ Бекор қилиш']],resize_keyboard=True))
 else:await update.message.reply_text('👑 Admin менюси',reply_markup=admin_kb())
async def master_router(update,context):
 t=update.message.text
 if t=='🆕 Янги буюртмалар':
  async with pool.acquire() as c: uid=await c.fetchval('SELECT id FROM users WHERE telegram_id=$1',update.effective_user.id)
  async with pool.acquire() as c:rs=await c.fetch("SELECT id,service_name,status FROM orders WHERE status IN('new','searching') AND NOT($1=ANY(COALESCE(rejected_master_ids,'{}'))) ORDER BY id DESC LIMIT 30",uid or 0)
  await update.message.reply_text('🆕 ЯНГИ БУЮРТМАЛАР',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f'№{x["id"]} 🔎 {x["service_name"][:25]}',callback_data=f'view:{x["id"]}')] for x in rs])) if rs else await update.message.reply_text('📭 Янги буюртма йўқ.')
 elif t=='📋 Менинг буюртмаларим':await list_orders(update,context)
 elif t=='📊 Статистика':await stats(update,context)
 elif t=='👤 Профиль':await profile(update,context)
 elif t=='📞 Диспетчер':await contact(update,context)
 elif t=='🟢 Иш ҳолатим':
  async with pool.acquire() as c:b=await c.fetchval('SELECT m.is_busy FROM masters m JOIN users u ON u.id=m.user_id WHERE u.telegram_id=$1',update.effective_user.id)
  await update.message.reply_text('🔴 Бандман' if b else '🟢 Бўшман',reply_markup=master_kb())
 else:await update.message.reply_text('Менюдан танланг.',reply_markup=master_kb())
async def dispatcher_router(update,context):
 t=update.message.text
 if t in ('🆕 Янги буюртмалар','📋 Буюртмалар'):await list_orders(update,context)
 elif t=='👨‍🔧 Усталар':
  async with pool.acquire() as c:rs=await c.fetch('SELECT u.name,u.phone,m.specialty,m.is_busy FROM users u JOIN masters m ON m.user_id=u.id WHERE m.is_active=TRUE')
  await update.message.reply_text('👨‍🔧 УСТАЛАР\n\n'+''.join(f'{r["name"]} — {"🔴 Банд" if r["is_busy"] else "🟢 Бўш"} — {r["specialty"]}\n' for r in rs)[:4000],reply_markup=disp_kb())
 elif t=='📊 Статистика':await stats(update,context)
 elif t=='📞 Диспетчер':await contact(update,context)
 elif t=='🔗 Бириктириш':await update.message.reply_text('🔗 Уста қабул қилиш орқали автоматик бириктириш ишлайди.',reply_markup=disp_kb())
 else:await update.message.reply_text('Менюдан танланг.',reply_markup=disp_kb())
async def router(update,context):
 r=await role(update.effective_user.id);t=update.message.text
 if t=='🏠 Асосий меню':return await home(update,context)
 if r==ADMIN:return await admin_router(update,context)
 if r==MASTER:return await master_router(update,context)
 if r==DISPATCHER:return await dispatcher_router(update,context)
 if t=='🛠 Уста чақириш':return await svc_categories(update,context)
 if t=='📋 Менинг буюртмаларим':return await list_orders(update,context)
 if t=='👤 Профилим':return await profile(update,context)
 if t=='ℹ️ Хизматлар':return await services(update,context)
 if t=='📞 Алоқа':return await contact(update,context)
 await update.message.reply_text('Менюдан танланг.',reply_markup=client_kb())

async def post_init(application):await db_init();log.info('DB ready')
async def shutdown(application):
 global pool
 if pool:await pool.close()
async def error(update,context):log.exception('Unhandled error',exc_info=context.error)

def build():
 global app
 app=Application.builder().token(BOT_TOKEN).post_init(post_init).post_shutdown(shutdown).build()
 order=ConversationHandler(entry_points=[CallbackQueryHandler(svc_cb,r'^svc:\d+$'),CallbackQueryHandler(custom_cb,r'^custom$')],states={0:[MessageHandler(filters.TEXT & ~filters.COMMAND,oname)],1:[MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND,ophone)],2:[MessageHandler((filters.LOCATION | filters.TEXT) & ~filters.COMMAND,oloc)],3:[MessageHandler(filters.TEXT & ~filters.COMMAND,oaddr)],4:[MessageHandler(filters.TEXT & ~filters.COMMAND,odesc)],5:[MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND,ophotos)],6:[CallbackQueryHandler(order_cb,r'^(submit|cancel_form|edit)$') ]},fallbacks=[CommandHandler('start',start)],allow_reentry=True)
 app.add_handler(order)
 app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(reject_cb,r'^r:\d+$')],states={REJECT_STATE:[MessageHandler(filters.TEXT & ~filters.COMMAND,reject_text)]},fallbacks=[CommandHandler('start',start)]))
 app.add_handler(ConversationHandler(entry_points=[CallbackQueryHandler(finish_cb,r'^f:\d+$')],states={FINISH_PHOTO:[MessageHandler(filters.PHOTO,finish_photo),MessageHandler(filters.Regex(r'^❌ Бекор қилиш$'),finish_photo)],FINISH_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,finish_note)]},fallbacks=[CommandHandler('start',start)]))
 app.add_handler(ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^👨‍🔧 Уста қўшиш$|^🎧 Dispatcher қўшиш$'),staff_start)],states={0:[MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND,staff_contact)],1:[MessageHandler(filters.TEXT & ~filters.COMMAND,staff_specialty)]},fallbacks=[CommandHandler('start',start)]))
 app.add_handler(CallbackQueryHandler(accept_cb,r'^a:\d+$'));app.add_handler(CallbackQueryHandler(status_cb,r'^s:\d+:(on_way|arrived|started|paused|payment)$'));app.add_handler(CallbackQueryHandler(rate_cb,r'^rate:\d+:[1-5]$'));app.add_handler(CallbackQueryHandler(view_cb,r'^view:\d+$'));app.add_handler(CallbackQueryHandler(cat_cb,r'^cat:.+$'));app.add_handler(CallbackQueryHandler(icat_cb,r'^icat:.+$'));app.add_handler(CallbackQueryHandler(icats_cb,r'^icats$'))
 app.add_handler(CommandHandler('start',start));app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,router));return app

if __name__=='__main__':
 app=build();app.add_error_handler(error);app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)
