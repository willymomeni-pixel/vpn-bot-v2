import time
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

TOKEN = "8757391333:AAEOrwa2vSdR7p2sWAxUV24onmQ-4e3_RLk"
ADMIN_ID = 2083913926
CARD = "6037 9981 7623 7674"

# ================= DB =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    ref_count INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan TEXT,
    price INTEGER,
    status TEXT,
    expire INTEGER
)
""")
db.commit()

# ================= HELPERS =================
def get_user(uid):
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (id) VALUES (?)", (uid,))
        db.commit()
        return (uid, 0, 0)
    return user

def create_order(uid, plan, price):
    cur.execute(
        "INSERT INTO orders (user_id, plan, price, status, expire) VALUES (?,?,?,?,?)",
        (uid, plan, price, "pending", 0)
    )
    db.commit()

def get_order(uid):
    cur.execute("SELECT * FROM orders WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid,))
    return cur.fetchone()

def set_expire(uid, t):
    cur.execute("UPDATE orders SET expire=? WHERE user_id=? AND status='pending'", (t, uid))
    db.commit()

def pay_order(uid):
    cur.execute("UPDATE orders SET status='paid' WHERE user_id=? AND status='pending'", (uid,))
    db.commit()

# ================= UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 خرید", callback_data="buy"),
            InlineKeyboardButton("🧪 تست", callback_data="test")
        ],
        [
            InlineKeyboardButton("👥 رفرال", callback_data="ref"),
            InlineKeyboardButton("💰 کیف پول", callback_data="wallet")
        ],
        [
            InlineKeyboardButton("👤 حساب", callback_data="me"),
            InlineKeyboardButton("📩 پشتیبانی", url="https://t.me/wsterrn")
        ]
    ])

def plans_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1GB", callback_data="p1"),
            InlineKeyboardButton("2GB", callback_data="p2")
        ],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])

def confirm_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید", callback_data="confirm"),
            InlineKeyboardButton("❌ لغو", callback_data="cancel")
        ],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    get_user(uid)
    await update.message.reply_text("🚀 ربات فعال شد", reply_markup=main_menu())

# ================= BUTTONS =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    get_user(uid)

    # BUY
    if q.data == "buy":
        await q.message.edit_text("📦 انتخاب پلن:", reply_markup=plans_menu())

    # TEST
    elif q.data == "test":
        create_order(uid, "TEST 50MB", 45000)
        await q.message.edit_text("🧪 تست 45,000\nتایید؟", reply_markup=confirm_menu())

    # PLANS
    elif q.data == "p1":
        create_order(uid, "1GB", 350000)
        await q.message.edit_text("📦 1GB - 350K\nتایید؟", reply_markup=confirm_menu())

    elif q.data == "p2":
        create_order(uid, "2GB", 650000)
        await q.message.edit_text("📦 2GB - 650K\nتایید؟", reply_markup=confirm_menu())

    # CONFIRM
    elif q.data == "confirm":
        order = get_order(uid)
        if not order:
            await q.message.edit_text("❌ سفارش پیدا نشد")
            return

        set_expire(uid, int(time.time()) + 1200)

        await q.message.edit_text(
            f"💳 پرداخت به کارت:\n\n{CARD}\n\n"
            f"📦 {order[2]}\n💰 {order[3]}\n\n"
            "⏳ ۲۰ دقیقه فرصت داری رسید بفرستی"
        )

    # CANCEL
    elif q.data == "cancel":
        await q.message.edit_text("❌ لغو شد", reply_markup=main_menu())

    # REF
    elif q.data == "ref":
        link = f"https://t.me/YOUR_BOT?start={uid}"
        await q.message.edit_text(f"👥 لینک رفرال:\n{link}", reply_markup=main_menu())

    # WALLET
    elif q.data == "wallet":
        user = get_user(uid)
        await q.message.edit_text(f"💰 موجودی: {user[1]}", reply_markup=main_menu())

    # ME
    elif q.data == "me":
        await q.message.edit_text(f"👤 ID: {uid}", reply_markup=main_menu())

    # BACK
    elif q.data == "back":
        await q.message.edit_text("🏠 منو", reply_markup=main_menu())

# ================= RECEIPT =================
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    order = get_order(uid)
    if not order:
        await update.message.reply_text("❌ سفارشی نیست")
        return

    if order[5] and time.time() > order[5]:
        await update.message.reply_text("⛔ تایم تموم شده")
        return

    pay_order(uid)

    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=f"📥 پرداخت\nUser:{uid}\nPlan:{order[2]}\nPrice:{order[3]}"
    )

    await update.message.reply_text("✅ رسید ثبت شد")

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.PHOTO, photo))
app.run_polling()
