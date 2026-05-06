import logging
import asyncio

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

import config
import database as db

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Force Subscribe ──────────────────────────────────────
FORCE_CHANNEL = "@v2greenorg"  # آیدی کانال اجباری

async def is_member(bot, user_id: int) -> bool:
    """چک می‌کنه کاربر عضو کانال هست یا نه"""
    try:
        member = await bot.get_chat_member(chat_id=FORCE_CHANNEL, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def send_join_required(update: Update, bot):
    """پیام عضویت اجباری رو می‌فرسته"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 عضویت در کانال", url=f"https://t.me/v2greenorg")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
    ])
    await update.effective_message.reply_text(
        "⚠️ برای استفاده از ربات، ابتدا باید در کانال ما عضو شوید.\n\n"
        "پس از عضویت، روی «✅ عضو شدم» کلیک کنید.",
        reply_markup=keyboard
    )

user_state: dict = {}

# ─── State helpers (ترکیب حافظه + دیتابیس) ──────────────
def set_state(user_id: int, state: dict):
    import json
    user_state[user_id] = state
    db.set_setting(f"state_{user_id}", json.dumps(state, ensure_ascii=False))

def get_state(user_id: int) -> dict:
    if user_id in user_state:
        return user_state[user_id]
    import json
    val = db.get_setting(f"state_{user_id}")
    if val and val not in ("{}", ""):
        try:
            s = json.loads(val)
            if s:
                user_state[user_id] = s
                return s
        except Exception:
            pass
    return {}

def clear_state(user_id: int):
    user_state.pop(user_id, None)
    db.set_setting(f"state_{user_id}", "{}")

# نگاشت plan_key به نام فارسی
PLAN_LABELS = {
    "1gb": "اشتراک ۱ گیگ",
    "2gb": "اشتراک ۲ گیگ",
    "50mb": "تست ۵۰ مگ",
    "100mb": "تست ۱۰۰ مگ",
    "referral": "رفرال",
}


# ─── Helpers ─────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS or user_id in db.get_admin_ids()


def fmt_price(p: int) -> str:
    return f"{p:,} تومان"


def user_info_text(user: dict) -> str:
    uname = f"@{user['username']}" if user.get("username") else "ندارد"
    return f"👤 نام: {user['full_name']}\n🔗 یوزرنیم: {uname}\n🆔 آیدی: {user['user_id']}"


def get_price(key: str, default: int) -> int:
    val = db.get_setting(f"price_{key}")
    return int(val) if val else default


def get_card_number() -> str:
    return db.get_setting("card_number") or config.CARD_NUMBER


def get_card_holder() -> str:
    return db.get_setting("card_holder") or config.CARD_HOLDER


def get_all_admins() -> list:
    return list(set(config.ADMIN_IDS + db.get_admin_ids()))


def is_sales_open() -> bool:
    val = db.get_setting("sales_open")
    return val != "0"

def is_card_payment_open() -> bool:
    val = db.get_setting("card_payment_open")
    return val != "0"

def is_topup_open() -> bool:
    val = db.get_setting("topup_open")
    return val != "0"


def main_menu_keyboard(user_id: int = None):
    rows = [
        [KeyboardButton("🛒 خرید اشتراک"), KeyboardButton("🧪 اکانت تست")],
        [KeyboardButton("👥 زیرمجموعه‌گیری"), KeyboardButton("🎧 پشتیبانی")],
        [KeyboardButton("👤 حساب من"), KeyboardButton("💳 افزایش موجودی")],
    ]
    if user_id and is_admin(user_id):
        rows.append([KeyboardButton("🔧 پنل ادمین")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu_keyboard():
    sales_status = "🟢 فروش باز است" if is_sales_open() else "🔴 فروش بسته است"
    card_status = "🟢 پرداخت کارت باز" if is_card_payment_open() else "🔴 پرداخت کارت بسته"
    topup_status = "🟢 افزایش موجودی باز" if is_topup_open() else "🔴 افزایش موجودی بسته"
    keyboard = [
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("💰 پرداخت‌های در انتظار", callback_data="admin_payments")],
        [InlineKeyboardButton("📦 مدیریت کانفیگ‌ها", callback_data="admin_configs")],
        [InlineKeyboardButton("💲 تغییر قیمت‌ها", callback_data="admin_prices")],
        [InlineKeyboardButton("💳 ویرایش شماره کارت", callback_data="admin_edit_card")],
        [InlineKeyboardButton("👤 مدیریت ادمین‌ها", callback_data="admin_manage_admins")],
        [InlineKeyboardButton("💰 تغییر موجودی کاربر", callback_data="admin_change_balance")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")],
        [InlineKeyboardButton(f"{sales_status} — تغییر", callback_data="admin_toggle_sales")],
        [InlineKeyboardButton(f"{card_status} — تغییر", callback_data="admin_toggle_card")],
        [InlineKeyboardButton(f"{topup_status} — تغییر", callback_data="admin_toggle_topup")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_admin():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back")]])


async def schedule_payment_timeout(bot, pay_id: int, user_id: int, chat_id: int, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    pay = db.get_payment(pay_id)
    if pay and pay["status"] == "pending":
        db.cancel_payment(pay_id)
        clear_state(user_id)
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="⏰ زمان پرداخت شما به پایان رسید و سفارش لغو شد.\n\nمی‌توانید مجدداً اقدام کنید.",
                reply_markup=main_menu_keyboard(user_id)
            )
        except Exception:
            pass


async def send_config_to_user(bot, user_id: int, plan_key: str, plan_name: str) -> bool:
    """ارسال کانفیگ به کاربر — True اگر موفق"""
    cfg = db.assign_config(plan_key, user_id)
    if cfg:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ *اشتراک شما آماده است!*\n\n📦 پلن: {plan_name}\n\n🔑 کانفیگ:\n`{cfg}`",
                parse_mode="Markdown"
            )
            return True
        except Exception:
            return False
    return False


# ─── Start ───────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_state.pop(user.id, None)

    if not await is_member(context.bot, user.id):
        await send_join_required(update, context.bot)
        return

    referred_by = None
    if context.args:
        ref_user = db.get_user_by_referral(context.args[0])
        if ref_user and ref_user["user_id"] != user.id:
            referred_by = ref_user["user_id"]

    db_user = db.get_or_create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        referred_by=referred_by
    )

    if referred_by and db_user.get("_is_new"):
        ref_owner = db.get_user(referred_by)
        if ref_owner and ref_owner["referral_count"] >= config.REFERRAL_THRESHOLD and not ref_owner["referral_rewarded"]:
            db.mark_referral_rewarded(referred_by)
            sent = await send_config_to_user(context.bot, referred_by, "referral", "رفرال")
            if not sent:
                for admin_id in get_all_admins():
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"🎉 کاربر زیر به {config.REFERRAL_THRESHOLD} دعوت موفق رسید:\n\n"
                                 f"{user_info_text(ref_owner)}\n\n"
                                 f"⚠️ کانفیگ رفرال موجود نیست! لطفاً اضافه کنید."
                        )
                    except Exception:
                        pass
                try:
                    await context.bot.send_message(
                        chat_id=referred_by,
                        text="🎊 تبریک! دعوت شما موفقیت‌آمیز بود.\nاشتراک تست شما طی ساعات آینده ارسال می‌شود."
                    )
                except Exception:
                    pass

    await update.message.reply_text(
        f"سلام {user.first_name} عزیز! 👋\nبه ربات خوش آمدید.",
        reply_markup=main_menu_keyboard(user.id)
    )


# ─── Message Handler ─────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    state = get_state(user_id)

    if not await is_member(context.bot, user_id):
        await send_join_required(update, context.bot)
        return

    if state:
        w = state.get("waiting")
        handlers = {
            "receipt": handle_receipt_photo,
            "support_msg": handle_support_message,
            "topup_amount": handle_topup_amount,
            "topup_receipt": handle_topup_receipt_photo,
            "admin_bal_user": handle_admin_bal_user,
            "admin_bal_amount": handle_admin_bal_amount,
            "admin_set_price": handle_admin_set_price,
            "admin_add_configs": handle_admin_add_configs,
            "admin_broadcast": handle_admin_broadcast,
            "admin_add_admin_id": handle_admin_add_admin_id,
            "admin_remove_admin_id": handle_admin_remove_admin_id,
            "admin_edit_card": handle_admin_edit_card,
            "admin_reply_user": handle_admin_reply_user,
        }
        if w in handlers:
            await handlers[w](update, context)
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
    state = get_state(user_id)
    if state:
        w = state.get("waiting")
        if w == "receipt":
            await handle_receipt_photo(update, context)
        elif w == "topup_receipt":
            await handle_topup_receipt_photo(update, context)


# ─── Plans ───────────────────────────────────────────────

async def show_subscription_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sales_open():
        await update.message.reply_text("🔴 متأسفانه فروش در حال حاضر بسته است.\nلطفاً بعداً مراجعه کنید.")
        return
    keyboard = []
    for key, plan in config.PLANS.items():
        price = get_price(key, plan["price"])
        cnt = db.get_config_count(key)
        label = f"📦 {plan['name']} - {fmt_price(price)}"
        if cnt == 0:
            label += " (ناموجود)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"plan_{key}")])
    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_order")])
    await update.message.reply_text(
        "📋 *پلن‌های اشتراک*\n\nیکی از پلن‌های زیر را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_test_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_sales_open():
        await update.message.reply_text("🔴 متأسفانه فروش در حال حاضر بسته است.\nلطفاً بعداً مراجعه کنید.")
        return
    keyboard = []
    for key, plan in config.TEST_PLANS.items():
        price = get_price(key, plan["price"])
        cnt = db.get_config_count(key)
        label = f"🧪 {plan['name']} - {fmt_price(price)}"
        if cnt == 0:
            label += " (ناموجود)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"test_{key}")])
    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_order")])
    await update.message.reply_text(
        "🧪 *اکانت تست*\n\nیک پلن تست انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── Callback Handler ────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ── چک عضویت ──
    if data == "check_join":
        if await is_member(context.bot, user_id):
            await query.edit_message_text("✅ عضویت تأیید شد! حالا می‌توانید از ربات استفاده کنید.")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"سلام {query.from_user.first_name} عزیز! 👋
به ربات خوش آمدید.",
                reply_markup=main_menu_keyboard(user_id)
            )
        else:
            await query.answer("❌ هنوز عضو کانال نشده‌اید!", show_alert=True)
        return

    # ── خرید اشتراک ──
    if data.startswith("plan_"):
        key = data.split("_", 1)[1]
        plan = config.PLANS.get(key)
        if plan:
            if not is_sales_open():
                await query.edit_message_text("🔴 فروش در حال حاضر بسته است.")
                return
            if db.get_config_count(key) == 0:
                await query.edit_message_text("⚠️ این پلن در حال حاضر موجود نیست.\nلطفاً بعداً مراجعه کنید.")
                return
            price = get_price(key, plan["price"])
            p = dict(plan); p["price"] = price
            await show_invoice(query, user_id, p, key, "subscription")

    elif data.startswith("test_"):
        key = data.split("_", 1)[1]
        plan = config.TEST_PLANS.get(key)
        if plan:
            if not is_sales_open():
                await query.edit_message_text("🔴 فروش در حال حاضر بسته است.")
                return
            if db.get_config_count(key) == 0:
                await query.edit_message_text("⚠️ این پلن در حال حاضر موجود نیست.\nلطفاً بعداً مراجعه کنید.")
                return
            price = get_price(key, plan["price"])
            p = dict(plan); p["price"] = price
            await show_invoice(query, user_id, p, key, "test")

    elif data.startswith("confirm_order_"):
        parts = data.split("_")
        order_type = parts[2]
        plan_key = parts[3]
        await process_order_confirm(query, user_id, order_type, plan_key, context)

    elif data.startswith("pay_wallet_"):
        parts = data.split("_")
        order_type = parts[2]
        plan_key = parts[3]
        await process_wallet_payment(query, user_id, order_type, plan_key, context)

    elif data == "cancel_order":
        clear_state(user_id)
        await query.edit_message_text("❌ عملیات لغو شد.")

    # ── ادمین: تایید/رد پرداخت ──
    elif data.startswith("admin_confirm_pay_"):
        pay_id = int(data.split("_")[-1])
        await admin_confirm_payment(query, pay_id, context)

    elif data.startswith("admin_cancel_pay_"):
        pay_id = int(data.split("_")[-1])
        await admin_cancel_payment(query, pay_id, context)

    # ── ادمین: پیام مستقیم به کاربر ──
    elif data.startswith("admin_msg_user_"):
        target_id = int(data.split("_")[-1])
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_reply_user", "target_id": target_id})
        await query.edit_message_text(
            f"✍️ پیام خود را برای کاربر `{target_id}` بنویسید:",
            parse_mode="Markdown"
        )

    # ── پنل ادمین ──
    elif data == "admin_back":
        await query.edit_message_text("🔧 *پنل مدیریت*", parse_mode="Markdown", reply_markup=admin_menu_keyboard())

    elif data == "admin_users":
        await show_admin_users(query)

    elif data == "admin_payments":
        await show_admin_payments(query)

    elif data == "admin_configs":
        await show_admin_configs(query)

    elif data.startswith("admin_add_cfg_"):
        plan_key = data.split("_")[-1]
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_add_configs", "plan_key": plan_key})
        plan_label = PLAN_LABELS.get(plan_key, plan_key)
        await query.edit_message_text(
            f"📦 *افزودن کانفیگ — {plan_label}*\n\n"
            f"هر کانفیگ را در یک خط جداگانه بنویسید:",
            parse_mode="Markdown"
        )

    elif data == "admin_prices":
        await show_admin_prices(query)

    elif data.startswith("set_price_"):
        key = data.split("_", 2)[2]
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_set_price", "price_key": key})
        await query.edit_message_text(f"قیمت جدید برای `{key}` را وارد کنید (تومان):", parse_mode="Markdown")

    elif data == "admin_edit_card":
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_edit_card"})
        await query.edit_message_text(
            f"💳 شماره کارت فعلی: `{get_card_number()}`\n\n"
            f"شماره کارت جدید را وارد کنید (فقط ارقام یا با خط تیره):",
            parse_mode="Markdown"
        )

    elif data == "admin_manage_admins":
        await show_admin_manage(query)

    elif data == "admin_add_admin":
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_add_admin_id"})
        await query.edit_message_text("آیدی عددی کاربر جدید را ارسال کنید:")

    elif data == "admin_remove_admin":
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_remove_admin_id"})
        await query.edit_message_text("آیدی عددی ادمینی که می‌خواهید حذف کنید را ارسال کنید:")

    elif data == "admin_change_balance":
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_bal_user"})
        await query.edit_message_text("آیدی عددی کاربر را ارسال کنید:")

    elif data == "admin_broadcast":
        if not is_admin(user_id):
            return
        set_state(user_id, {"waiting": "admin_broadcast"})
        await query.edit_message_text("📢 متن پیام همگانی را بنویسید:")

    elif data == "admin_toggle_sales":
        if not is_admin(user_id):
            return
        current = is_sales_open()
        db.set_setting("sales_open", "0" if current else "1")
        status = "🟢 باز" if not current else "🔴 بسته"
        await query.edit_message_text(
            f"✅ وضعیت فروش به *{status}* تغییر کرد.",
            parse_mode="Markdown",
            reply_markup=back_to_admin()
        )

    elif data == "admin_toggle_card":
        if not is_admin(user_id):
            return
        current = is_card_payment_open()
        db.set_setting("card_payment_open", "0" if current else "1")
        status = "🟢 باز" if not current else "🔴 بسته"
        await query.edit_message_text(
            f"✅ پرداخت کارت به کارت به *{status}* تغییر کرد.",
            parse_mode="Markdown",
            reply_markup=back_to_admin()
        )

    elif data == "admin_toggle_topup":
        if not is_admin(user_id):
            return
        current = is_topup_open()
        db.set_setting("topup_open", "0" if current else "1")
        status = "🟢 باز" if not current else "🔴 بسته"
        await query.edit_message_text(
            f"✅ افزایش موجودی به *{status}* تغییر کرد.",
            parse_mode="Markdown",
            reply_markup=back_to_admin()
        )


# ─── Invoice ─────────────────────────────────────────────

async def show_invoice(query, user_id: int, plan: dict, plan_key: str, order_type: str):
    db_user = db.get_user(user_id)
    balance = db_user["balance"] if db_user else 0
    price = plan["price"]
    has_enough = balance >= price

    text = (
        f"🧾 *فاکتور خرید*\n\n"
        f"📦 پلن: {plan['name']}\n"
        f"📊 حجم: {plan['size']}\n"
    )
    if plan.get("duration"):
        text += f"⏱ مدت: {plan['duration']}\n"
    text += (
        f"💵 مبلغ: *{fmt_price(price)}*\n"
        f"💰 موجودی شما: {fmt_price(balance)}\n\n"
        f"روش پرداخت را انتخاب کنید:"
    )

    wallet_label = "💰 پرداخت با موجودی ✅" if has_enough else "💰 پرداخت با موجودی (ناکافی)"
    keyboard = [
        [InlineKeyboardButton("💳 پرداخت با کارت", callback_data=f"confirm_order_{order_type}_{plan_key}")],
        [InlineKeyboardButton(wallet_label, callback_data=f"pay_wallet_{order_type}_{plan_key}")],
        [InlineKeyboardButton("❌ لغو", callback_data="cancel_order")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def process_order_confirm(query, user_id: int, order_type: str, plan_key: str, context):
    if order_type == "subscription":
        plan = config.PLANS.get(plan_key)
    else:
        plan = config.TEST_PLANS.get(plan_key)
    if not plan:
        return

    if db.get_config_count(plan_key) == 0:
        await query.edit_message_text(
            "⚠️ متأسفانه این پلن در حال حاضر موجود نیست.\nلطفاً بعداً مراجعه کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ بستن", callback_data="cancel_order")]])
        )
        return

    if not is_card_payment_open():
        await query.edit_message_text(
            "🔴 پرداخت کارت به کارت غیرفعال است. از پرداخت با موجودی استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ بستن", callback_data="cancel_order")]])
        )
        return

    price = get_price(plan_key, plan["price"])
    sub_id = db.create_subscription(user_id, plan_key, plan["name"], plan["size"], price, "card")
    pay_id = db.create_payment(user_id, price, order_type, sub_id)

    set_state(user_id, {
        "waiting": "receipt",
        "pay_id": pay_id,
        "sub_id": sub_id,
        "plan_key": plan_key,
        "price": price,
        "plan_name": plan["name"],
    })

    await query.edit_message_text(
        f"💳 *اطلاعات پرداخت*\n\n"
        f"مبلغ: *{fmt_price(price)}*\n"
        f"شماره کارت:\n`{get_card_number()}`\n"
        f"به نام: {get_card_holder()}\n\n"
        f"⏰ شما *{config.PAYMENT_TIMEOUT_MINUTES} دقیقه* فرصت دارید.\n"
        f"پس از واریز، تصویر رسید را ارسال کنید.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_order")]])
    )

    asyncio.create_task(
        schedule_payment_timeout(context.bot, pay_id, user_id, query.message.chat_id, config.PAYMENT_TIMEOUT_MINUTES * 60)
    )


async def process_wallet_payment(query, user_id: int, order_type: str, plan_key: str, context):
    if order_type == "subscription":
        plan = config.PLANS.get(plan_key)
    else:
        plan = config.TEST_PLANS.get(plan_key)
    if not plan:
        return

    price = get_price(plan_key, plan["price"])
    db_user = db.get_user(user_id)

    if not db_user or db_user["balance"] < price:
        await query.edit_message_text(
            "❌ موجودی کافی نیست.\n\nبرای شارژ کیف پول از گزینه «افزایش موجودی» استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ بستن", callback_data="cancel_order")]])
        )
        return

    if db.get_config_count(plan_key) == 0:
        await query.edit_message_text(
            "⚠️ این پلن در حال حاضر موجود نیست.\nلطفاً بعداً مراجعه کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ بستن", callback_data="cancel_order")]])
        )
        return

    db.update_balance(user_id, -price)
    sub_id = db.create_subscription(user_id, plan_key, plan["name"], plan["size"], price, "wallet")
    pay_id = db.create_payment(user_id, price, order_type, sub_id)
    db.confirm_payment(pay_id)
    db.confirm_subscription(sub_id)

    # ارسال خودکار کانفیگ
    sent = await send_config_to_user(context.bot, user_id, plan_key, plan["name"])

    user = db.get_user(user_id)
    for admin_id in get_all_admins():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🛍 *سفارش جدید (پرداخت با موجودی)*\n\n"
                    f"{user_info_text(user)}\n\n"
                    f"📦 پلن: {plan['name']}\n"
                    f"💵 مبلغ: {fmt_price(price)}\n"
                    f"✅ کانفیگ: {'ارسال شد' if sent else '⚠️ موجود نبود'}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    if not sent:
        await query.edit_message_text(
            f"✅ پرداخت انجام شد.\n\n"
            f"📦 پلن: {plan['name']}\n"
            f"⚠️ کانفیگ موجود نبود — طی ساعات آینده ارسال می‌شود."
        )
    # اگر sent=True کاربر پیام کانفیگ رو جداگانه گرفته
    else:
        await query.edit_message_text(
            f"✅ پرداخت انجام شد.\n📦 پلن: {plan['name']}\n\nکانفیگ در پیام بعدی ارسال شد."
        )


# ─── Receipt ─────────────────────────────────────────────

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    pay_id = state.get("pay_id")
    if not pay_id:
        return

    pay = db.get_payment(pay_id)
    if not pay or pay["status"] != "pending":
        clear_state(user_id)
        await update.message.reply_text("⚠️ این سفارش منقضی یا لغو شده است.")
        return

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("لطفاً تصویر رسید را به صورت عکس ارسال کنید.")
        return

    is_document = bool(update.message.document)
    db.update_payment_receipt(pay_id, file_id)
    user = db.get_user(user_id)

    await update.message.reply_text(
        "✅ رسید شما با موفقیت دریافت شد.\nپس از تایید نهایی، اشتراک شما ارسال خواهد شد.",
        reply_markup=main_menu_keyboard(user_id)
    )

    plan_key = state.get("plan_key", "")
    plan_name = state.get("plan_name", "")

    for admin_id in get_all_admins():
        try:
            caption = (
                f"🧾 *رسید پرداخت جدید*\n\n"
                f"{user_info_text(user)}\n\n"
                f"📦 پلن: {plan_name}\n"
                f"💵 مبلغ: {fmt_price(pay['amount'])}\n"
                f"🔖 شناسه پرداخت: #{pay_id}\n"
                f"🗂 plan_key: {plan_key}"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید", callback_data=f"admin_confirm_pay_{pay_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"admin_cancel_pay_{pay_id}"),
                ],
                [InlineKeyboardButton("✉️ پیام مستقیم", callback_data=f"admin_msg_user_{user_id}")]
            ])
            if is_document:
                await context.bot.send_document(
                    chat_id=admin_id, document=file_id,
                    caption=caption, parse_mode="Markdown", reply_markup=kb
                )
            else:
                await context.bot.send_photo(
                    chat_id=admin_id, photo=file_id,
                    caption=caption, parse_mode="Markdown", reply_markup=kb
                )
        except Exception as e:
            logger.error(f"Error sending receipt to admin: {e}")

    clear_state(user_id)


# ─── Admin: Confirm / Cancel Payment ─────────────────────

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
        await query.edit_message_caption(f"✅ شارژ کیف پول #{pay_id} تایید شد.")

    else:
        # پیدا کردن plan_key از subscription
        sub = db.get_subscription(pay.get("ref_id")) if pay.get("ref_id") else None
        if sub:
            db.confirm_subscription(sub["id"])
            plan_key = sub["plan_key"]
            plan_name = sub["plan_name"]
        else:
            plan_key = pay.get("purpose", "")
            plan_name = PLAN_LABELS.get(plan_key, plan_key)

        # ارسال خودکار کانفیگ
        sent = await send_config_to_user(context.bot, pay["user_id"], plan_key, plan_name)

        if sent:
            await query.edit_message_caption(f"✅ پرداخت #{pay_id} تایید شد — کانفیگ ارسال شد.")
        else:
            # کانفیگ موجود نبود، پیام دستی بده
            try:
                await context.bot.send_message(
                    chat_id=pay["user_id"],
                    text="✅ پرداخت شما تایید شد.\n⚠️ کانفیگ شما طی ساعات آینده ارسال می‌شود."
                )
            except Exception:
                pass
            await query.edit_message_caption(
                f"✅ پرداخت #{pay_id} تایید شد.\n⚠️ کانفیگ موجود نبود — برای {PLAN_LABELS.get(plan_key, plan_key)} اضافه کنید."
            )


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
        f"🎁 {remaining} نفر دیگر برای کانفیگ رایگان\n\n"
        f"هر {config.REFERRAL_THRESHOLD} دعوت = یک کانفیگ تست رایگان"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Support ─────────────────────────────────────────────

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_state(user_id, {"waiting": "support_msg"})
    await update.message.reply_text(
        "🎧 *پشتیبانی*\n\nپیام خود را بنویسید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_order")]])
    )


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    msg = update.message.text
    clear_state(user_id)

    await update.message.reply_text(
        "✅ پیام شما ارسال شد. به زودی پاسخ داده می‌شود.",
        reply_markup=main_menu_keyboard(user_id)
    )

    for admin_id in get_all_admins():
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📩 *پیام پشتیبانی جدید*\n\n"
                    f"{user_info_text(user)}\n\n"
                    f"💬 پیام:\n{msg}"
                ),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✉️ پاسخ مستقیم", callback_data=f"admin_msg_user_{user_id}")
                ]])
            )
        except Exception:
            pass


async def handle_admin_reply_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    target_id = state.get("target_id")
    msg = update.message.text
    clear_state(user_id)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📨 *پیام از پشتیبانی:*\n\n{msg}",
            parse_mode="Markdown"
        )
        await update.message.reply_text("✅ پیام با موفقیت ارسال شد.", reply_markup=main_menu_keyboard(user_id))
    except Exception:
        await update.message.reply_text("❌ ارسال پیام ناموفق بود.")


# ─── Account ─────────────────────────────────────────────

async def show_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        return
    subs = db.get_user_subscriptions(user_id)
    subs_text = ""
    for s in subs[:5]:
        emoji = "✅" if s["status"] == "confirmed" else "⏳"
        subs_text += f"\n{emoji} {s['plan_name']} — {s['created_at'][:10]}"
    if not subs_text:
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
    if not is_topup_open():
        await update.message.reply_text("🔴 افزایش موجودی در حال حاضر غیرفعال است.")
        return
    set_state(user_id, {"waiting": "topup_amount"})
    await update.message.reply_text(
        "💳 *افزایش موجودی*\n\nمبلغ مورد نظر را وارد کنید (۵۰,۰۰۰ تا ۵,۰۰۰,۰۰۰ تومان):",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_order")]])
    )


async def handle_topup_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.replace(",", "").replace("،", "").strip())
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
    set_state(user_id, {"waiting": "topup_receipt", "pay_id": pay_id, "amount": amount})

    await update.message.reply_text(
        f"🧾 *فاکتور شارژ کیف پول*\n\n"
        f"💵 مبلغ: *{fmt_price(amount)}*\n\n"
        f"💳 شماره کارت:\n`{get_card_number()}`\n"
        f"به نام: {get_card_holder()}\n\n"
        f"⏰ پس از واریز رسید را ارسال کنید. (مهلت: {config.PAYMENT_TIMEOUT_MINUTES} دقیقه)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="cancel_order")]])
    )

    asyncio.create_task(
        schedule_payment_timeout(context.bot, pay_id, user_id, update.effective_chat.id, config.PAYMENT_TIMEOUT_MINUTES * 60)
    )


async def handle_topup_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
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
        reply_markup=main_menu_keyboard(user_id)
    )

    for admin_id in get_all_admins():
        try:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید", callback_data=f"admin_confirm_pay_{pay_id}"),
                    InlineKeyboardButton("❌ رد", callback_data=f"admin_cancel_pay_{pay_id}"),
                ],
                [InlineKeyboardButton("✉️ پیام مستقیم", callback_data=f"admin_msg_user_{user_id}")]
            ])
            await context.bot.send_photo(
                chat_id=admin_id, photo=file_id,
                caption=(
                    f"💳 *درخواست افزایش موجودی*\n\n"
                    f"{user_info_text(user)}\n\n"
                    f"💵 مبلغ: {fmt_price(pay['amount'])}\n"
                    f"🔖 شناسه: #{pay_id}"
                ),
                parse_mode="Markdown", reply_markup=kb
            )
        except Exception:
            pass

    clear_state(user_id)


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
        text += f"• {u['full_name']} | {uname} | {fmt_price(u['balance'])}\n"
    if len(users) > 20:
        text += f"\n... و {len(users)-20} نفر دیگر"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_admin())


async def show_admin_payments(query):
    pays = db.get_all_pending_payments()
    if not pays:
        await query.edit_message_text("✅ پرداخت در انتظاری وجود ندارد.", reply_markup=back_to_admin())
        return
    text = f"💰 *پرداخت‌های در انتظار ({len(pays)})*\n\n"
    for p in pays:
        uname = f"@{p['username']}" if p.get("username") else "—"
        text += f"• #{p['id']} | {p['full_name']} | {uname} | {fmt_price(p['amount'])}\n"
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_admin())


async def show_admin_configs(query):
    summary = db.get_configs_summary()
    all_plan_keys = list(config.PLANS.keys()) + list(config.TEST_PLANS.keys()) + ["referral"]
    counts = {r["plan_key"]: r["available"] for r in summary}

    text = "📦 *مدیریت کانفیگ‌ها*\n\n"
    for key in all_plan_keys:
        label = PLAN_LABELS.get(key, key)
        cnt = counts.get(key, 0)
        text += f"• {label}: {cnt} عدد\n"

    kb = []
    for key in all_plan_keys:
        label = PLAN_LABELS.get(key, key)
        kb.append([InlineKeyboardButton(f"➕ افزودن کانفیگ {label}", callback_data=f"admin_add_cfg_{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def show_admin_prices(query):
    all_plans = {**config.PLANS, **config.TEST_PLANS}
    lines = ""
    for key, plan in all_plans.items():
        price = get_price(key, plan["price"])
        lines += f"• {plan['name']}: {fmt_price(price)}\n"
    kb = []
    for key, plan in all_plans.items():
        kb.append([InlineKeyboardButton(f"✏️ {plan['name']}", callback_data=f"set_price_{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")])
    await query.edit_message_text(
        f"💲 *قیمت‌های فعلی*\n\n{lines}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


async def show_admin_manage(query):
    admin_ids = db.get_admin_ids()
    text = f"👤 *مدیریت ادمین‌ها*\n\nادمین‌های فعلی:\n"
    for aid in admin_ids:
        text += f"• `{aid}`\n"
    if not admin_ids:
        text += "هیچ ادمینی ثبت نشده\n"
    kb = [
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")],
        [InlineKeyboardButton("➖ حذف ادمین", callback_data="admin_remove_admin")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")],
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ─── Admin Input Handlers ────────────────────────────────

async def handle_admin_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    key = state.get("price_key")
    try:
        price = int(update.message.text.strip().replace(",", "").replace("،", ""))
        db.set_setting(f"price_{key}", str(price))
        clear_state(user_id)
        await update.message.reply_text(
            f"✅ قیمت {PLAN_LABELS.get(key, key)} به {fmt_price(price)} تغییر کرد.",
            reply_markup=main_menu_keyboard(user_id)
        )
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد صحیح وارد کنید.")


async def handle_admin_add_configs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    plan_key = state.get("plan_key", "referral")
    text = update.message.text.strip()
    configs = [line.strip() for line in text.split("\n") if line.strip()]
    if not configs:
        await update.message.reply_text("⚠️ هیچ کانفیگی یافت نشد.")
        return
    db.add_configs(plan_key, configs)
    clear_state(user_id)
    cnt = db.get_config_count(plan_key)
    await update.message.reply_text(
        f"✅ {len(configs)} کانفیگ برای «{PLAN_LABELS.get(plan_key, plan_key)}» اضافه شد.\n📊 موجودی: {cnt} عدد",
        reply_markup=main_menu_keyboard(user_id)
    )


async def handle_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    clear_state(user_id)
    all_ids = db.get_all_user_ids()
    sent = 0
    failed = 0
    for uid in all_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 *پیام ادمین:*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(
        f"📢 پیام همگانی ارسال شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}",
        reply_markup=main_menu_keyboard(user_id)
    )


async def handle_admin_bal_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        target_id = int(update.message.text.strip())
        target = db.get_user(target_id)
        if not target:
            await update.message.reply_text("⚠️ کاربر یافت نشد.")
            return
        set_state(user_id, {"waiting": "admin_bal_amount", "target_id": target_id})
        await update.message.reply_text(
            f"کاربر: {target['full_name']}\nموجودی: {fmt_price(target['balance'])}\n\n"
            f"مقدار تغییر (مثبت=افزایش، منفی=کاهش):"
        )
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً آیدی عددی وارد کنید.")


async def handle_admin_bal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_state(user_id)
    target_id = state.get("target_id")
    try:
        delta = int(update.message.text.strip().replace(",", ""))
        db.update_balance(target_id, delta)
        target = db.get_user(target_id)
        clear_state(user_id)
        await update.message.reply_text(
            f"✅ موجودی به‌روز شد.\nموجودی جدید: {fmt_price(target['balance'])}",
            reply_markup=main_menu_keyboard(user_id)
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"💰 موجودی کیف پول شما تغییر کرد.\nموجودی جدید: {fmt_price(target['balance'])}"
            )
        except Exception:
            pass
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یک عدد وارد کنید.")


async def handle_admin_add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        new_id = int(update.message.text.strip())
        db.add_admin(new_id)
        clear_state(user_id)
        await update.message.reply_text(f"✅ کاربر {new_id} به عنوان ادمین اضافه شد.", reply_markup=main_menu_keyboard(user_id))
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def handle_admin_remove_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        rem_id = int(update.message.text.strip())
        if rem_id in config.ADMIN_IDS:
            await update.message.reply_text("⚠️ این ادمین اصلی است و قابل حذف نیست.")
            return
        db.remove_admin(rem_id)
        clear_state(user_id)
        await update.message.reply_text(f"✅ ادمین {rem_id} حذف شد.", reply_markup=main_menu_keyboard(user_id))
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def handle_admin_edit_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    card = update.message.text.strip()
    db.set_setting("card_number", card)
    clear_state(user_id)
    await update.message.reply_text(f"✅ شماره کارت به روز شد:\n`{card}`", parse_mode="Markdown", reply_markup=main_menu_keyboard(user_id))


# ─── Admin Commands ──────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await show_admin_panel(update, context)


async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استفاده: /addadmin <user_id>")
        return
    try:
        db.add_admin(int(context.args[0]))
        await update.message.reply_text(f"✅ ادمین {context.args[0]} اضافه شد.")
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("استفاده: /removeadmin <user_id>")
        return
    try:
        db.remove_admin(int(context.args[0]))
        await update.message.reply_text(f"✅ ادمین {context.args[0]} حذف شد.")
    except ValueError:
        await update.message.reply_text("⚠️ آیدی باید عدد باشد.")


async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /setbalance <user_id> <amount>")
        return
    try:
        db.set_balance(int(context.args[0]), int(context.args[1]))
        await update.message.reply_text("✅ موجودی تنظیم شد.")
    except ValueError:
        await update.message.reply_text("⚠️ مقادیر نامعتبر.")


# ─── Main ────────────────────────────────────────────────

def main():
    db.init_db()
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

    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
