from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import TOKEN
from handlers import start, handler, photo


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # /start
    app.add_handler(CommandHandler("start", start))

    # دکمه‌ها
    app.add_handler(CallbackQueryHandler(handler))

    # رسید پرداخت (عکس)
    app.add_handler(MessageHandler(filters.PHOTO, photo))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
