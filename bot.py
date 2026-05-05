import logging
import asyncio
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

import config
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── States ──────────────────────────────────────────────
(
    WAITING_RECEIPT,
    WAITING_SUPPORT_MSG,
    WAITING_TOPUP_AMOUNT,
    WAITING_TOPUP_RECEIPT,
    WAITING_ADMIN_BALANCE_USER,
    WAITING_ADMIN_BALANCE_AMOUNT,
) = range(6)

# نگهداری وضعیت موقت کاربران در حافظه
user_state: dict = {}


# ─── Helpers ─────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS or user_id in db.get_admin_ids()


def fmt_price(p: int) -> str:
    return f"{p:,} تومان"


def user_info_text(user: dict) -> str:
    uname = f"@{user['username']}" if user.get("username") else "ندارد"
    return f"👤 نام: {user['full_name']}\n🔗 یوزرنیم: {uname}\n🆔 آیدی: {user['user_id']}"


def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🛒 خرید اشتراک"), KeyboardButton("🧪 اکانت تست")],
        [KeyboardButton("👥 زیرمجموعه‌گیری"), KeyboardButton("🎧 پشتیبانی")],
        [KeyboardButton("👤 حساب من"), KeyboardButton("💳 افزایش موجودی")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def admin_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("💰 پرداخت‌های در انتظار", callback_data="admin_payments")],
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton("💳 تغییر موجودی کاربر", callback_data="admin_change_balance")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def schedule_payment_timeout(context: ContextTypes.DEFAULT_TYPE, pay_id: int, user_id: int, chat_id: int, delay_seconds: int):
    """بعد از تایم‌اوت، پرداخت رو لغو کنه"""
    await asyncio.sleep(delay_seconds)
    pay = db.get_payment(pay_id)
    if pay and pay["status"] == "pending":
        db.cancel_payment(pay_id)
        # اگر اشتراک مرتبط داشت لغو کن
        if pay.get("ref_id") and pay["purpose"] in ("subscription", "test"):
            pass  # subscription status remains pending
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ زمان پرداخت شما به پایان رسید و سفارش لغو شد.\n\nمی‌توانید مجدداً اقدام کنید.",
                reply_markup=main_menu_keyboard()
            )
        except Exception:
            pass
        # پاک کردن وضعیت
        user_state.pop(user_id, None)


# ─── Start ───────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    referred_by = None
    if args:
        ref_user = db.get_user_by_referral(args[0])
        if ref_user and ref_user["user_id"] != user.id:
            referred_by = ref_user["user_id"]

    db_user = db.get_or_create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        referred_by=referred_by
    )

    # بررسی رسیدن به آستانه رفرال
    if referred_by:
        ref_owner = db.get_user(referred_by)
        if ref_owner and ref_owner["referral_count"] >= config.REFERRAL_THRESHOLD and not ref_owner["referral_rewarded"]:
            db.mark_referral_rewarded(referred_by)
            # پیام به ادمین
            for admin_id in (config.ADMIN_IDS + db.get_admin_ids()):
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"🎉 کاربر زیر به {config.REFERRAL_THRESHOLD} دعوت موفق رسید:\n\n"
                             f"{user_info_text(ref_owner)}\n\n"
                             f"لطفاً اشتراک تست برایشان ارسال کنید."
                    )
                except Exception:
                    pass
            # پیام به کاربر
            try:
                await context.bot.send_message(
                    chat_id=referred_by,
                    text=f"🎊 تبریک! دعوت شما موفقیت‌آمیز بود.\nاشتراک تست شما طی ساعات آینده ارسال می‌شود."
                )
            except Exception:
                pass

    await update.message.reply_text(
        f"سلام {user.first_name} عزیز! 👋\nبه ربات خوش آمدید.",
        reply_markup=main_menu_keyboard()
    )


# ─── Main Menu Handlers ──────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # بررسی وضعیت‌های انتظار
    state = user_state.get(user_id)

    if state:
        if state.get("waiting") == "receipt":
            await handle_receipt_photo(update, context)
            return
        elif state.get("waiting") == "support_msg":
            await handle_support_message(update, context)
            return
        elif state.get("waiting") == "topup_amount":
            await handle_topup_amount(update, context)
            return
        elif state.get("waiting") == "topup_receipt":
            await handle_topup_receipt_photo(update, context)
            return
        elif state.get("waiting") == "admin_bal_user":
            await handle_admin_bal_user(update, context)
            return
        elif state.get("waiting") == "admin_bal_amount":
            await handle_admin_bal_amount(update, context)
            return

    if text == "🛒 خرید اشتراک":
        await show_subscription_plans(update, context)
    elif text == "🧪 اکانت تست":
        await show_test_plans(update, context)
    elif text == "👥 زیرمجموعه‌گیری":
        await show_referral(update, context)
    elif text == "🎧 پشتیبانی":
        await start_support(update, context)
    elif text == "👤 حساب من":
        await show_account(update, context)
    elif text == "💳 افزایش موجودی":
        await start_topup(update, context)
    elif text == "🔧 پنل ادمین" and is_admin(user_id):
        await show_admin_panel(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id)
    if state:
        if state.get("waiting") == "receipt":
            await handle_receipt_photo(update, context)
        elif state.get("waiting") == "topup_receipt":
            await handle_topup_receipt_photo(update, context)


# ─── Subscription Plans ──────────────────────────────────

async def show_subscription_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for key, plan in config.PLANS.items():
        keyboard.append([InlineKeyboardButton(
            f"📦 {plan['name']} - {fmt_price(plan['price'])}",
            callback_data=f"plan_{key}"
        )])
    await update.message.reply_text(
        "📋 *پلن‌های اشتراک*\n\nیکی از پلن‌های زیر را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_test_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for key, plan in config.TEST_PLANS.items():
        keyboard.append([InlineKeyboardButton(
            f"🧪 {plan['name']} - {fmt_price(plan['price'])}",
            callback_data=f"test_{key}"
        )])
    await update.message.reply_text(
        "🧪 *اکانت تست*\n\nیک پلن تست انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── Callback Query Handler ──────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("plan_"):
        key = data.split("_", 1)[1]
        plan = config.PLANS.get(key)
        if plan:
            await show_invoice(query, user_id, plan, key, "subscription")

    elif data.startswith("test_"):
        key = data.split("_", 1)[1]
        plan = config.TEST_PLANS.get(key)
        if plan:
            await show_invoice(query, user_id, plan, key, "test")

    elif data.startswith("confirm_order_"):
        parts = data.split("_")
        order_type = parts[2]
        plan_key = parts[3]
        await process_order_confirm(query, user_id, order_type, plan_key)

    elif data.startswith("pay_wallet_"):
        parts = data.split("_")
        order_type = parts[2]
        plan_key = parts[3]
        await process_wallet_payment(query, user_id, order_type, plan_key)

    elif data == "cancel_order":
        user_state.pop(user_id, None)
        await query.edit_message_text("❌ سفارش لغو شد.")

    elif data.startswith("admin_confirm_pay_"):
        pay_id = int(data.split("_")[-1])
        await admin_confirm_payment(query, pay_id, context)

    elif data.startswith("admin_cancel_pay_"):
        pay_id = int(data.split("_")[-1])
        await admin_cancel_payment(query, pay_id, context)

    elif data == "admin_users":
        await show_admin_users(query)

    elif data == "admin_payments":
        await show_admin_payments(query)

    elif data == "admin_add_admin":
        await query.edit_message_text("آیدی عددی کاربر مورد نظر را ارسال کنید:\n(با دستور /addadmin <user_id>)")

    elif data == "admin_change_balance":
        user_state[user_id] = {"waiting": "admin_bal_user"}
        await query.edit_message_text("آیدی عددی کاربر را ارسال کنید:")


async def show_invoice(query, user_id: int, plan: dict, plan_key: str, order_type: str):
    db_user = db.get_user(user_id)
    balance = db_user["balance"] if db_user else 0
    price = plan["price"]

    wallet_btn_text = f"💰 پرداخت با موجودی ({fmt_price(balance)})"
    has_enough = balance >= price

    text = (
        f"🧾 *فاکتور خرید*\n\n"
        f"📦 پلن: {plan['name']}\n"
        f"📊 حجم: {plan['size']}\n"
    )
    if plan.get("duration"):
        text += f"⏱ مدت: {plan['duration']}\n"
    text += (
        f"💵 مبلغ: *{fmt_price(price)}*\n\n"
        f"روش پرداخت را انتخاب کنید:"
    )

    keyboard = [
        [InlineKeyboardButton("💳 پرداخت با کارت", callback_data=f"confirm_order_{order_type}_{plan_key}")],
        [InlineKeyboardButton(wallet_btn_text, callback_data=f"pay_wallet_{order_type}_{plan_key}")],
        [InlineKeyboardButton("❌ لغو", callback_data="cancel_order")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def process_order_confirm(query, user_id: int, order_type: str, plan_key: str):
    if order_type == "subscription":
        plan = config.PLANS.get(plan_key)
        plan_name = plan["name"]
        plan_size = plan["size"]
        price = plan["price"]
        purpose = "subscription"
    else:
        plan = config.TEST_PLANS.get(plan_key)
        plan_name = plan["name"]
        plan_size = plan["size"]
        price = plan["price"]
        purpose = "test"

    # ایجاد رکورد اشتراک
    sub_id = db.create_subscription(user_id, plan_key, plan_name, plan_size, price, "card")
    # ایجاد پرداخت
    pay_id = db.create_payment(user_id, price, purpose, sub_id)

    user_state[user_id] = {
        "waiting": "receipt",
        "pay_id": pay_id,
        "sub_id": sub_id,
        "price": price,
        "plan_name": plan_name,
    }

    text = (
        f"💳 *اطلاعات پرداخت*\n\n"
        f"مبلغ: *{fmt_price(price)}*\n"
        f"شماره کارت:\n`{config.CARD_NUMBER}`\n"
        f"به نام: {config.CARD_HOLDER}\n\n"
        f"⏰ شما *{config.PAYMENT_TIMEOUT_MINUTES} دقیقه* فرصت دارید.\n"
        f"پس از واریز، تصویر رسید را ارسال کنید."
    )
    await query.edit_message_text(text, parse_mode="Markdown")

    # زمان‌بندی لغو خودکار
    asyncio.create_task(
        schedule_payment_timeout(
            query._bot if hasattr(query, '_bot') else None,
            pay_id, user_id,
            query.message.chat_id,
            config.PAYMENT_TIMEOUT_MINUTES * 60
        )
    )


async def process_wallet_payment(query, user_id: int, order_type: str, plan_key: str):
    if order_type == "subscription":
        plan = config.PLANS.get(plan_key)
    else:
        plan = config.TEST_PLANS.get(plan_key)

    price = plan["price"]
    db_user = db.get_user(user_id)

    if not db_user or db_user["balance"] < price:
        await query.edit_message_text(
            "❌ موجودی کافی نیست.\n\nبرای شارژ کیف پول از گزینه «افزایش موجودی» استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="cancel_order")]])
        )
        return

    # کسر موجودی
    db.update_balance(user_id, -price)
    sub_id = db.create_subscription(
        user_id, plan_key, plan["name"],
        plan["size"], price, "wallet"
    )
    pay_id = db.create_payment(user_id, price, order_type, sub_id)
    db.confirm_payment(pay_id)

    # اطلاع به ادمین
    user = db.get_user(user_id)
    for admin_id in (config.ADMIN_IDS + db.get_admin_ids()):
        try:
            await query.get_bot().send_message(
                chat_id=admin_id,
                text=(
                    f"🛍 *سفارش جدید (پرداخت با موجودی)*\n\n"
                    f"{user_info_text(user)}\n\n"
                    f"📦 پلن: {plan['name']}\n"
                    f"💵 مبلغ: {fmt_price(price)}\n"
                    f"📋 نوع: {order_type}\n"
                    f"🔖 شناسه اشتراک: #{sub_id}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await query.edit_message_text(
        f"✅ پرداخت با موجودی انجام شد.\n\n"
        f"📦 پلن: {plan['name']}\n"
        f"💵 مبلغ کسر شده: {fmt_price(price)}\n\n"
        f"منتظر بمانید تا اشتراک برای شما ارسال شود."
    )


# ─── Receipt Handler ─────────────────────────────────────

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {})
    pay_id = state.get("pay_id")
    plan_name = state.get("plan_name", "")

    if not pay_id:
        return

    pay = db.get_payment(pay_id)
    if not pay or pay["status"] not in ("pending",):
        user_state.pop(user_id, None)
        await update.message.reply_text("⚠️ این سفارش منقضی یا لغو شده است.")
        return

    # گرفتن فایل آیدی عکس
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("لطفاً تصویر رسید را به صورت عکس ارسال کنید.")
        return

    db.update_payment_receipt(pay_id, file_id)

    user = db.get_user(user_id)
    await update.message.reply_text(
        "✅ رسید شما با موفقیت دریافت شد.\nپس از تایید نهایی، اشتراک شما ارسال خواهد شد.",
        reply_markup=main_menu_keyboard()
    )

    # ارسال به ادمین
    for admin_id in (config.ADMIN_IDS + db.get_admin_ids()):
        try:
            caption = (
                f"🧾 *رسید پرداخت جدید*\n\n"
                f"{user_info_text(user)}\n\n"
                f"📦 پلن: {plan_name}\n"
                f"💵 مبلغ: {fmt_price(pay['amount'])}\n"
                f"🔖 شناسه پرداخت: #{pay_id}"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید", callback_data=f"admin_confirm_pay_{pay_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"admin_cancel_pay_{pay_id}"),
                ]
            ])
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Error sending receipt to admin: {e}")

    user_state.pop(user_id, None)


# ─── Admin Payment Actions ───────────────────────────────

async def admin_confirm_payment(query, pay_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(query.from_user.id):
        return
    pay = db.get_payment(pay_id)
    if not pay:
        await query.edit_message_caption("⚠️ پرداخت یافت نشد.")
        return

    db.confirm_payment(pay_id)
    if pay["purpose"] == "topup":
        db.update_balance(pay["user_id"], pay["amount"])
        try:
            await context.bot.send_message(
                chat_id=pay["user_id"],
                text=f"✅ موجودی کیف پول شما به مبلغ {fmt_price(pay['amount'])} افزایش یافت."
            )
        except Exception:
            pass
    else:
        if pay.get("ref_id"):
            db.confirm_subscription(pay["ref_id"])
        try:
            await context.bot.send_message(
                chat_id=pay["user_id"],
                text="✅ پرداخت شما تایید شد. اشتراک شما به زودی ارسال خواهد شد."
            )
        except Exception:
            pass

    await query.edit_message_caption(f"✅ پرداخت #{pay_id} تایید شد.")


async def admin_cancel_payment(query, pay_id: int, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(query.from_user.id):
        return
    db.cancel_payment(pay_id)
    pay = db.get_payment(pay_id)
    if pay:
        try:
            await context.bot.send_message(
                chat_id=pay["user_id"],
                text="❌ متأسفانه پرداخت شما تایید نشد. لطفاً با پشتیبانی تماس بگیرید."
            )
        except Exception:
            pass
    await query.edit_message_caption(f"❌ پرداخت #{pay_id} رد شد.")


# ─── Referral ────────────────────────────────────────────

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = db.get_user(user_id)
    if not db_user:
        return

    code = db_user["referral_code"]
    count = db_user["referral_count"]
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={code}"
    remaining = max(0, config.REFERRAL_THRESHOLD - count)

    text = (
        f"👥 *زیرمجموعه‌گیری*\n\n"
        f"🔗 لینک اختصاصی شما:\n`{link}`\n\n"
        f"👫 تعداد دعوت‌ها: {count}\n"
        f"🎁 برای دریافت اشتراک تست رایگان، {remaining} نفر دیگر دعوت کنید!\n\n"
        f"هر {config.REFERRAL_THRESHOLD} دعوت موفق = یک اشتراک تست رایگان"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Support ─────────────────────────────────────────────

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"waiting": "support_msg"}
    await update.message.reply_text(
        "🎧 *پشتیبانی*\n\nپیام خود را بنویسید تا در اسرع وقت پاسخ داده شود:",
        parse_mode="Markdown"
    )


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    msg = update.message.text

    user_state.pop(user_id, None)
    await update.message.reply_text(
        "✅ پیام شما با موفقیت ارسال شد. به زودی پاسخ داده می‌شود.",
        reply_markup=main_menu_keyboard()
    )

    for admin_id in (config.ADMIN_IDS + db.get_admin_ids()):
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📩 *پیام پشتیبانی جدید*\n\n"
                    f"{user_info_text(user)}\n\n"
                    f"💬 پیام:\n{msg}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass


# ─── Account ─────────────────────────────────────────────

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        return

    subs = db.get_user_subscriptions(user_id)
    subs_text = ""
    if subs:
        for s in subs[:5]:
            status_emoji = "✅" if s["status"] == "confirmed" else "⏳"
            subs_text += f"\n{status_emoji} {s['plan_name']} — {s['created_at'][:10]}"
    else:
        subs_text = "\nاشتراکی یافت نشد."

    text = (
        f"👤 *حساب من*\n\n"
        f"💰 موجودی: {fmt_price(user['balance'])}\n"
        f"👥 تعداد دعوت‌ها: {user['referral_count']}\n\n"
        f"📦 *اشتراک‌ها:*{subs_text}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Top Up ──────────────────────────────────────────────

async def start_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_state[user_id] = {"waiting": "topup_amount"}
    await update.message.reply_text(
        "💳 *افزایش موجودی*\n\n"
        "مبلغ مورد نظر را وارد کنید (بین ۵۰,۰۰۰ تا ۵,۰۰۰,۰۰۰ تومان):",
        parse_mode="Markdown"
    )


async def handle_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.replace(",", "").replace("،", "").strip()

    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد صحیح وارد کنید.")
        return

    if amount < 50000:
        await update.message.reply_text("⚠️ حداقل مبلغ ۵۰,۰۰۰ تومان است.")
        return
    if amount > 5000000:
        await update.message.reply_text("⚠️ حداکثر مبلغ ۵,۰۰۰,۰۰۰ تومان است.")
        return

    pay_id = db.create_payment(user_id, amount, "topup")
    user_state[user_id] = {"waiting": "topup_receipt", "pay_id": pay_id, "amount": amount}

    await update.message.reply_text(
        f"🧾 *فاکتور شارژ کیف پول*\n\n"
        f"💵 مبلغ: *{fmt_price(amount)}*\n\n"
        f"💳 شماره کارت:\n`{config.CARD_NUMBER}`\n"
        f"به نام: {config.CARD_HOLDER}\n\n"
        f"⏰ پس از واریز، تصویر رسید را ارسال کنید.\n"
        f"(مهلت: {config.PAYMENT_TIMEOUT_MINUTES} دقیقه)",
        parse_mode="Markdown"
    )

    asyncio.create_task(
        schedule_payment_timeout(
            context, pay_id, user_id,
            update.effective_chat.id,
            config.PAYMENT_TIMEOUT_MINUTES * 60
        )
    )


async def handle_topup_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {})
    pay_id = state.get("pay_id")

    if not pay_id:
        return

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("لطفاً تصویر رسید را به صورت عکس ارسال کنید.")
        return

    db.update_payment_receipt(pay_id, file_id)
    pay = db.get_payment(pay_id)
    user = db.get_user(user_id)

    await update.message.reply_text(
        "✅ رسید شما دریافت شد. پس از تایید، موجودی شما افزایش خواهد یافت.",
        reply_markup=main_menu_keyboard()
    )

    for admin_id in (config.ADMIN_IDS + db.get_admin_ids()):
        try:
            caption = (
                f"💳 *درخواست افزایش موجودی*\n\n"
                f"{user_info_text(user)}\n\n"
                f"💵 مبلغ: {fmt_price(pay['amount'])}\n"
                f"🔖 شناسه: #{pay_id}"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید", callback_data=f"admin_confirm_pay_{pay_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"admin_cancel_pay_{pay_id}"),
                ]
            ])
            await context.bot.send_photo(
                chat_id=admin_id, photo=file_id,
                caption=caption, parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception:
            pass

    user_state.pop(user_id, None)


# ─── Admin Panel ─────────────────────────────────────────

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())


async def show_admin_users(query):
    users = db.get_all_users()
    text = f"👥 *کاربران ({len(users)} نفر)*\n\n"
    for u in users[:20]:
        uname = f"@{u['username']}" if u.get("username") else "—"
        text += f"• {u['full_name']} | {uname} | موجودی: {fmt_price(u['balance'])}\n"
    if len(users) > 20:
        text += f"\n... و {len(users)-20} نفر دیگر"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())


async def show_admin_payments(query):
    pays = db.get_all_pending_payments()
    if not pays:
        await query.edit_message_text("✅ پرداخت در انتظاری وجود ندارد.", reply_markup=admin_menu_keyboard())
        return
    text = f"💰 *پرداخت‌های در انتظار ({len(pays)})*\n\n"
    for p in pays:
        uname = f"@{p['username']}" if p.get("username") else "—"
        text += f"• #{p['id']} | {p['full_name']} | {uname} | {fmt_price(p['amount'])}\n"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_menu_keyboard())


async def handle_admin_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        target_id = int(update.message.text.strip())
        target = db.get_user(target_id)
        if not target:
            await update.message.reply_text("⚠️ کاربر یافت نشد.")
            return
        user_state[user_id] = {"waiting": "admin_bal_amount", "target_id": target_id}
        await update.message.reply_text(
            f"کاربر: {target['full_name']}\nموجودی فعلی: {fmt_price(target['balance'])}\n\n"
            f"موجودی جدید را وارد کنید (عدد مثبت = افزایش، منفی = کاهش):"
        )
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً آیدی عددی وارد کنید.")


async def handle_admin_bal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {})
    target_id = state.get("target_id")
    try:
        delta = int(update.message.text.strip().replace(",", ""))
        db.update_balance(target_id, delta)
        target = db.get_user(target_id)
        user_state.pop(user_id, None)
        await update.message.reply_text(
            f"✅ موجودی کاربر به‌روز شد.\nموجودی جدید: {fmt_price(target['balance'])}",
            reply_markup=main_menu_keyboard()
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💰 موجودی کیف پول شما توسط ادمین تغییر کرد.\nموجودی جدید: {fmt_price(target['balance'])}"
            )
        except Exception:
            pass
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد وارد کنید.")


# ─── Admin Commands ──────────────────────────────────────

async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استفاده: /addadmin <user_id>")
        return
    try:
        new_admin_id = int(context.args[0])
        db.add_admin(new_admin_id)
        await update.message.reply_text(f"✅ کاربر {new_admin_id} به عنوان ادمین اضافه شد.")
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استفاده: /removeadmin <user_id>")
        return
    try:
        rem_id = int(context.args[0])
        db.remove_admin(rem_id)
        await update.message.reply_text(f"✅ ادمین {rem_id} حذف شد.")
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /setbalance <user_id> <amount>")
        return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
        db.set_balance(uid, amount)
        await update.message.reply_text(f"✅ موجودی کاربر {uid} به {fmt_price(amount)} تنظیم شد.")
    except ValueError:
        await update.message.reply_text("⚠️ مقادیر نامعتبر.")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await show_admin_panel(update, context)


# ─── Main ────────────────────────────────────────────────

def main():
    db.init_db()

    # اضافه کردن ادمین‌های پیش‌فرض به دیتابیس
    for admin_id in config.ADMIN_IDS:
        db.add_admin(admin_id)

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("addadmin", cmd_addadmin))
    app.add_handler(CommandHandler("removeadmin", cmd_removeadmin))
    app.add_handler(CommandHandler("setbalance", cmd_setbalance))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
