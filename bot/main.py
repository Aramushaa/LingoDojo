from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from bot.config import BOT_TOKEN
from bot.db import init_db, import_packs_from_folder
from bot.handlers.start import start
from bot.handlers.stats import stats
from bot.handlers.learn import learn, on_pack_button, on_text

def main():  
    print("🚀 Bot is starting...")
    
    init_db()
    import_packs_from_folder()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("learn", learn))

    app.add_handler(CallbackQueryHandler(on_pack_button, pattern=r"^PACK\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

