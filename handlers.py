from db import *
from config import *
from keyboards import *

# START
async def start(update, context):
    uid = update.message.from_user.id
    get_user(uid)

    await update.message.reply_text(
        "🚀 خوش اومدی به ربات فروش",
        reply_markup=main_menu()
    )


# CALLBACK
async def handler(update, context):
    q = update.callback_query
    await q.answer()

    uid = q.from_user.id
    data = q.data
    user = get_user(uid)

    # خرید
    if data == "buy":
        await q.message.edit_text("📦 انتخاب پلن:", reply_markup=plans())

    # پلن‌ها
    elif data == "p1":
        add_order(uid, "1 گیگ اینترنت سبز نت", 350000)
        await q.message.edit_text(
            "🧾 فاکتور\n\nهیچ کدام از اشتراک ها دارای مدت زمان نیستند",
            reply_markup=confirm()
        )

    elif data == "p2":
        add_order(uid, "2 گیگ اینترنت سبز نت", 650000)
        await q.message.edit_text(
            "🧾 فاکتور\n\nهیچ کدام از اشتراک ها دارای مدت زمان نیستند",
            reply_markup=confirm()
        )

    # تایید
    elif data == "confirm":
        await q.message.edit_text(
            f"💳 شماره کارت:\n{CARD_NUMBER}\n\n📸 رسید بفرست",
            reply_markup=back()
        )

    elif data == "cancel":
        await q.message.edit_text("❌ لغو شد", reply_markup=main_menu())

    # تست
    elif data == "test":
        add_order(uid, "50MB تست", 45000)
        await q.message.edit_text(
            "🧾 تست\nمدت زمان ۱۰ روز",
            reply_markup=confirm()
        )

    # کیف پول
    elif data == "wallet":
        await q.message.edit_text(
            f"💰 موجودی: {user[1]}",
            reply_markup=back()
        )

    # حساب
    elif data == "me":
        await q.message.edit_text(
            f"👤 حساب شما\n\n💰 موجودی: {user[1]}\n👥 دعوت: {user[2]}",
            reply_markup=back()
        )

    # رفرال
    elif data == "ref":
        await q.message.edit_text(
            f"👥 لینک دعوت:\nhttps://t.me/YOURBOT?start={uid}",
            reply_markup=back()
        )

    # پشتیبانی
    elif data == "support":
        context.user_data["support"] = True
        await q.message.edit_text("🧑‍💬 پیام خود را ارسال کن", reply_markup=back())

    elif data == "back":
        await q.message.edit_text("🏠 منو", reply_markup=main_menu())


# پیام‌ها
async def text_handler(update, context):
    uid = update.message.from_user.id

    if context.user_data.get("support"):
        await context.bot.send_message(
            ADMIN_ID,
            f"📩 پیام پشتیبانی\nUser:{uid}\n\n{update.message.text}"
        )
        await update.message.reply_text("✅ ارسال شد")
        context.user_data["support"] = False


# رسید
async def photo(update, context):
    uid = update.message.from_user.id
    order = get_last_order(uid)

    if order:
        pay_order(uid)

        await context.bot.send_photo(
            ADMIN_ID,
            update.message.photo[-1].file_id,
            caption=f"💰 پرداخت\nUser:{uid}\nPlan:{order[2]}"
        )

        await update.message.reply_text("✅ رسید دریافت شد")
