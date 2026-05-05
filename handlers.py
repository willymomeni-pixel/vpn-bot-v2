import time
from config import *
from db import *
from keyboards import *


# START + REF
async def start(update, context):
    uid = update.message.from_user.id

    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except:
            pass

    get_user(uid)
    set_ref(uid, ref)

    await update.message.reply_text("🚀 خوش آمدید", reply_markup=menu())


# CALLBACKS
async def handler(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    user = get_user(uid)

    # MENU
    if data == "buy":
        await q.message.edit_text("📦 انتخاب پلن:", reply_markup=plans())

    elif data == "back":
        await q.message.edit_text("🏠 منو", reply_markup=menu())

    # PLANS
    elif data == "p1":
        add_order(uid, "1GB سبز نت", 350000, "sub")
        await q.message.edit_text("🧾 فاکتور:\nهیچ کدام از اشتراک ها دارای مدت زمان نیستند", reply_markup=confirm())

    elif data == "p2":
        add_order(uid, "2GB سبز نت", 650000, "sub")
        await q.message.edit_text("🧾 فاکتور:\nهیچ کدام از اشتراک ها دارای مدت زمان نیستند", reply_markup=confirm())

    # TEST
    elif data == "test":
        await q.message.edit_text("🎁 تست:\n50MB\n100MB")

    # CONFIRM
    elif data == "confirm":
        order = last_order(uid)
        set_expire(uid, int(time.time()) + PAY_TIMEOUT)

        await q.message.edit_text(
            f"💳 کارت:\n{CARD_NUMBER}\n\n⏳ 20 دقیقه فرصت دارید"
        )

    elif data == "cancel":
        await q.message.edit_text("❌ لغو شد", reply_markup=menu())

    # WALLET
    elif data == "wallet":
        await q.message.edit_text(f"💰 موجودی: {user[1]}", reply_markup=wallet_menu())

    # REF
    elif data == "ref":
        await q.message.edit_text(
            f"👥 رفرال شما\n\n🔗 لینک:\nhttps://t.me/YOURBOT?start={uid}\n\n👤 تعداد: {user[3]}"
        )

        if user[3] >= REF_REWARD_COUNT:
            await context.bot.send_message(ADMIN_ID, f"🎁 کاربر {uid} 5 رفرال گرفت")
            await context.bot.send_message(uid, "🎉 جایزه شما ثبت شد")

    # ME
    elif data == "me":
        await q.message.edit_text(
            f"👤 حساب\n\n💰 موجودی: {user[1]}\n👥 دعوت: {user[3]}"
        )

    # SUPPORT
    elif data == "support":
        await q.message.edit_text("🧑‍💬 پیام خود را بفرستید")


# PAYMENT (simplified)
async def photo(update, context):
    uid = update.message.from_user.id
    order = last_order(uid)

    if order:
        pay(uid)

        await context.bot.send_message(
            ADMIN_ID,
            f"📥 پرداخت\nUser:{uid}\nPlan:{order[2]}\nPrice:{order[3]}"
        )

        await update.message.reply_text("✅ رسید دریافت شد")
