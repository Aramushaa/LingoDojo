from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging

from bot.config import BOT_TOKEN
from bot.db import init_db, import_packs_from_folder
from bot.handlers.start import start
from bot.handlers.stats import stats
from bot.handlers.learn import learn, on_pack_button
from bot.handlers.learn import on_text as on_learn_text
from bot.handlers.settings import settings, on_settings_button
from bot.handlers.review import review, on_review_text, on_grade_button



logger = logging.getLogger(__name__)

async def on_error(update, context):
    logger.exception("Unhandled exception:", exc_info=context.error)


async def on_text_router(update, context):
    # try learn handler
    await on_learn_text(update, context)
    # try review handler
    await on_review_text(update, context)


def main():  
    print("🚀 Bot is starting...")

    init_db()
    import_packs_from_folder()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("learn", learn))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("review", review))


    app.add_handler(CallbackQueryHandler(on_grade_button, pattern=r"^GRADE\|"))
    app.add_handler(CallbackQueryHandler(on_pack_button, pattern=r"^PACK\|"))
    app.add_handler(CallbackQueryHandler(on_settings_button, pattern=r"^SET_(TARGET|UI)\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_router))

    app.run_polling(drop_pending_updates=True)

    app.add_error_handler(on_error)


if __name__ == "__main__":
    main()

