from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy"),
         InlineKeyboardButton("🎁 اکانت تست", callback_data="test")],

        [InlineKeyboardButton("👥 رفرال", callback_data="ref"),
         InlineKeyboardButton("💰 موجودی", callback_data="wallet")],

        [InlineKeyboardButton("👤 حساب من", callback_data="me"),
         InlineKeyboardButton("🧑‍💬 پشتیبانی", callback_data="support")]
    ])


def plans():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1 گیگ اینترنت سبز نت", callback_data="p1"),
         InlineKeyboardButton("2 گیگ اینترنت سبز نت", callback_data="p2")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])


def confirm():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تایید", callback_data="confirm"),
         InlineKeyboardButton("❌ لغو", callback_data="cancel")]
    ])


def wallet_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزایش موجودی", callback_data="add_balance")],
        [InlineKeyboardButton("🔙 برگشت", callback_data="back")]
    ])
