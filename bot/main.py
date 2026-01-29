from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging

from bot.config import BOT_TOKEN
from bot.db import init_db, import_packs_from_folder,get_session
from bot.handlers.start import start
from bot.handlers.stats import stats
from bot.handlers.learn import learn, on_guess_button, on_pronounce_button
from bot.handlers.learn import on_text as on_learn_text
from bot.handlers.settings import settings, on_settings_button
from bot.handlers.review import review, on_review_text, on_grade_button, on_undo_button
from bot.handlers.home import on_home_button
from dotenv import load_dotenv
from bot.handlers.setlevel import setlevel, on_setlevel_button



load_dotenv()




logger = logging.getLogger(__name__)

async def on_error(update, context):
    logger.exception("Unhandled exception:", exc_info=context.error)


async def on_text_router(update, context):
    user = update.effective_user
    if not user:
        return

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage, meta = session  # meta added

    if mode == "learn":
        await on_learn_text(update, context)
    elif mode == "review":
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
    app.add_handler(CommandHandler("setlevel", setlevel))



    app.add_handler(CallbackQueryHandler(on_grade_button, pattern=r"^GRADE\|"))
    app.add_handler(CallbackQueryHandler(on_settings_button, pattern=r"^SET_(TARGET|UI)\|"))
    app.add_handler(CallbackQueryHandler(on_home_button, pattern=r"^home:"))
    app.add_handler(CallbackQueryHandler(on_undo_button, pattern=r"^UNDO\|"))
    # Settings callbacks
    app.add_handler(CallbackQueryHandler(on_settings_button, pattern=r"^(SET_TARGET|SET_UI|SET_HELPER|SETTINGS|PKTOG)\|"))
    # Learn callbacks
    app.add_handler(CallbackQueryHandler(on_guess_button, pattern=r"^GUESS\|"))
    app.add_handler(CallbackQueryHandler(on_pronounce_button, pattern=r"^PRON\|"))
    app.add_handler(CallbackQueryHandler(on_setlevel_button, pattern=r"^SETLEVEL\|"))


    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_router))

    app.add_error_handler(on_error)

    app.run_polling(drop_pending_updates=True)

   


if __name__ == "__main__":
    main()

