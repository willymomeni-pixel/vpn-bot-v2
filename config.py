import os

# Bot Token از محیط Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8757391333:AAEOrwa2vSdR7p2sWAxUV24onmQ-4e3_RLk")

# آیدی ادمین (عددی)
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "2083913926").split(",") if x.strip()]

# شماره کارت برای پرداخت
CARD_NUMBER = os.environ.get("CARD_NUMBER", "6037-9981-7623-7674")
CARD_HOLDER = os.environ.get("CARD_HOLDER", "مومنی")

# زمان انقضای پرداخت (دقیقه)
PAYMENT_TIMEOUT_MINUTES = 20

# پلن‌ها (قیمت‌ها را از محیط بخوان یا پیش‌فرض باشند)
PLANS = {
    "1gb": {
        "name": "اشتراک ۱ گیگ",
        "size": "۱ گیگابایت",
        "duration": "نامحدود",
        "price": int(os.environ.get("PRICE_1GB", "350000")),
    },
    "2gb": {
        "name": "اشتراک ۲ گیگ",
        "size": "۲ گیگابایت",
        "duration": "نامحدود",
        "price": int(os.environ.get("PRICE_2GB", "650000")),
    },
}

TEST_PLANS = {
    "50mb": {
        "name": "۵۰ مگابایت تست",
        "size": "۵۰ مگابایت",
        "price": int(os.environ.get("PRICE_TEST_50MB", "45000")),
    },
    "100mb": {
        "name": "۱۰۰ مگابایت تست",
        "size": "۱۰۰ مگابایت",
        "price": int(os.environ.get("PRICE_TEST_100MB", "85000")),
    },
}

# تعداد دعوت برای دریافت تست رایگان
REFERRAL_THRESHOLD = 5
