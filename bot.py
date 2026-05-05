import sqlite3
import time
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = "8757391333:AAEOrwa2vSdR7p2sWAxUV24onmQ-4e3_RLk"
ADMIN_ID = 2083913926
SUPPORT = "@wsterrn"

CARD_NUMBER = "6037 9981 7623 7674"

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    invites INTEGER DEFAULT 0,
    ref_by INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    plan TEXT,
    amount INTEGER,
    status TEXT,
    expire INTEGER
)
""")
conn.commit()

# ================= HELPERS =================
def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def create_user(uid, ref=None):
    if not get_user(uid):
        cur.execute("INSERT INTO users (user_id, ref_by) VALUES (?,?)", (uid, ref))
        conn.commit()

# ================= MENUS =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy")],
        [InlineKeyboardButton("🧪 اکانت تست", callback_data="test")],
        [InlineKeyboardButton("👥 زیرمجموعه گیری", callback_data="ref")],
        [InlineKeyboardButton("💳 افزایش موجودی", callback_data="wallet")],
        [InlineKeyboardButton("👤 حساب من", callback_data="me")],
        [InlineKeyboardButton("📩 پشتیبانی", url=f"https://t.me/{SUPPORT.replace('@','')}")]
    ])

def plans_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1GB نامحدود - 350K", callback_data="p1")],
        [InlineKeyboardButton("2GB نامحدود - 650K", callback_data="p2")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    ref = context.args[0] if context.args else None
    create_user(uid, ref)

    await update.message.reply_text("🚀 خوش آمدید", reply_markup=main_menu())

# ================= CALLBACK =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    create_user(uid)

    # BUY
    if q.data == "buy":
        await q.message.edit_text("📦 انتخاب پلن:", reply_markup=plans_menu())

    # TEST
    elif q.data == "test":
        await q.message.edit_text("🧪 تست فعال شد\n50MB - 45,000")

    # PLANS
    elif q.data in ["p1", "p2"]:
        plans = {
            "p1": ("1GB", 350000),
            "p2": ("2GB", 650000)
        }

        name, price = plans[q.data]
        pid = str(uuid.uuid4())[:8]

        cur.execute("INSERT INTO payments VALUES (?,?,?,?,?,?)",
                    (pid, uid, name, price, "pending", int(time.time())+1200))
        conn.commit()

        await q.message.edit_text(
            f"📦 {name}\n💰 {price} تومان\n\n"
            "❓ تایید می‌کنی؟"
        )

        context.user_data["active_payment"] = pid

    # REF
    elif q.data == "ref":
        link = f"https://t.me/YOUR_BOT?start={uid}"
        await q.message.edit_text(f"👥 لینک دعوت:\n{link}")

    # WALLET
    elif q.data == "wallet":
        await q.message.edit_text("💳 مبلغ شارژ رو ارسال کن")

    # ME
    elif q.data == "me":
        u = get_user(uid)
        await q.message.edit_text(
            f"👤 حساب شما\n💰 موجودی: {u[1]}\n👥 دعوت: {u[2]}"
        )

# ================= PHOTO (RECEIPT) =================
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    pid = context.user_data.get("active_payment")

    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=f"📥 رسید جدید\nUser: {uid}\nPayID: {pid}"
    )

    await update.message.reply_text("✅ رسید دریافت شد، در حال بررسی")

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.PHOTO, photo))

app.run_polling()
