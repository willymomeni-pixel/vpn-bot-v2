import time
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# ================= CONFIG =================
TOKEN = "8757391333:AAEOrwa2vSdR7p2sWAxUV24onmQ-4e3_RLk"
ADMIN_ID = 2083913926
CARD_NUMBER = "6037 9981 7623 7674"

# ذخیره ساده سفارش‌ها
orders = {}

# ================= MENUS =================
def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy"),
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

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 به ربات خوش آمدی", reply_markup=main_menu())

# ================= BUTTONS =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id

    # MAIN BUY
    if q.data == "buy":
        await q.message.edit_text("📦 انتخاب پلن:", reply_markup=plans_menu())

    # TEST
    elif q.data == "test":
        await q.message.edit_text("🧪 پلن تست: 50MB - 45,000", reply_markup=back_menu())

    # PLANS
    elif q.data in ["p1", "p2"]:
        plans = {
            "p1": ("1GB", 350000),
            "p2": ("2GB", 650000)
        }

        name, price = plans[q.data]

        orders[uid] = {
            "plan": name,
            "price": price,
            "time": time.time()
        }

        await q.message.edit_text(
            f"📦 {name}\n💰 {price} تومان\n\nتایید می‌کنی؟",
            reply_markup=confirm_menu()
        )

    # CONFIRM
    elif q.data == "confirm":
        order = orders.get(uid)

        if not order:
            await q.message.edit_text("❌ سفارش پیدا نشد")
            return

        orders[uid]["expire"] = time.time() + 1200  # 20 دقیقه

        await q.message.edit_text(
            f"💳 پرداخت به کارت:\n\n{CARD_NUMBER}\n\n"
            f"📦 {order['plan']}\n💰 {order['price']}\n\n"
            "⏳ 20 دقیقه فرصت داری رسید بفرستی",
            reply_markup=back_menu()
        )

    # CANCEL
    elif q.data == "cancel":
        orders.pop(uid, None)
        await q.message.edit_text("❌ لغو شد", reply_markup=main_menu())

    # BACK
    elif q.data == "back":
        await q.message.edit_text("🏠 منو اصلی", reply_markup=main_menu())

# ================= PHOTO (RECEIPT) =================
async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id

    order = orders.get(uid)

    if not order:
        await update.message.reply_text("❌ سفارش فعالی نداری")
        return

    # چک تایم
    if time.time() > order.get("expire", 0):
        orders.pop(uid, None)
        await update.message.reply_text("⛔ زمان پرداخت تموم شده")
        return

    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=f"📥 رسید جدید\nUser: {uid}\nPlan: {order['plan']}\nPrice: {order['price']}"
    )

    await update.message.reply_text("✅ رسید دریافت شد، منتظر تایید")

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button))
app.add_handler(MessageHandler(filters.PHOTO, photo))

app.run_polling()
