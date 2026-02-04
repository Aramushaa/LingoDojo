from telegram import BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging

from bot.config import BOT_TOKEN
from bot.db import init_db, import_packs_from_folder,get_session
from bot.handlers.start import start, on_onboarding_text, on_start_choice
from bot.handlers.stats import stats
from bot.handlers.learn import on_guess_button, on_pronounce_button, on_scene_choice, on_scene_action, on_scene_replay, on_ai_choice, on_learn_skip, on_unlock_next
from bot.handlers.learn import on_text as on_learn_text
from bot.handlers.journey import journey, on_journey_choice
from bot.handlers.settings import settings, on_settings_button, open_packs
from bot.handlers.review import review, on_review_text, on_grade_button, on_undo_button, on_review_action, on_review_flow, on_review_choice
from bot.handlers.home import on_home_button, home_command
from bot.handlers.reloadpacks import reloadpacks_command
from bot.handlers.help import help_command, sos_command
from bot.handlers.persona import persona_command, on_persona_text
from bot.handlers.addword import add_command, mywords_command, on_addword_text, on_addword_button, on_addword_category, on_mywords_button
from bot.handlers.tts import ttscheck_command, on_tts_button
from bot.handlers.hints import hint_command, why_command
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
    elif mode == "onboarding":
        await on_onboarding_text(update, context)
    elif mode == "persona":
        await on_persona_text(update, context)
    elif mode == "addword":
        await on_addword_text(update, context)

async def post_init(application):
    commands = [
        BotCommand("start", "Setup your profile (languages + level)"),
        BotCommand("add", "Add your own word(s)"),
        BotCommand("home", "Show main menu"),
        BotCommand("ttscheck", "Check TTS health"),
        BotCommand("journey", "Guided level‑up path"),
        BotCommand("packs", "Browse packs"),
        BotCommand("progress", "Stats + streak"),
        BotCommand("review", "Review due items (SRS)"),
        BotCommand("settings", "Languages + level"),
        BotCommand("mywords", "Browse your saved words"),
        BotCommand("hint", "Show a quick hint"),
        BotCommand("why", "Show extra context"),
        BotCommand("help", "Show command menu"),
        BotCommand("reloadpacks", "Reload packs from /data/packs (dev)"),
    ]
    await application.bot.set_my_commands(commands)



def main():  
    print("🚀 Bot is starting...")
    



    init_db()
    import_packs_from_folder()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("progress", stats))
    app.add_handler(CommandHandler("journey", journey))
    app.add_handler(CommandHandler("learn", journey))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("packs", open_packs))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(CommandHandler("home", home_command))
    app.add_handler(CommandHandler("setlevel", setlevel))
    app.add_handler(CommandHandler("persona", persona_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("mywords", mywords_command))
    app.add_handler(CommandHandler("ttscheck", ttscheck_command))
    app.add_handler(CommandHandler("hint", hint_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("sos", sos_command))
    app.add_handler(CommandHandler("reloadpacks", reloadpacks_command))



    app.add_handler(CallbackQueryHandler(on_grade_button, pattern=r"^GRADE\|"))
    app.add_handler(CallbackQueryHandler(on_home_button, pattern=r"^home:"))
    app.add_handler(CallbackQueryHandler(on_start_choice, pattern=r"^START\|"))
    app.add_handler(CallbackQueryHandler(on_undo_button, pattern=r"^UNDO\|"))
    app.add_handler(CallbackQueryHandler(on_review_choice, pattern=r"^REVIEW\|CHOICE\|"))
    app.add_handler(CallbackQueryHandler(on_review_action, pattern=r"^REVIEW\|"))
    app.add_handler(CallbackQueryHandler(on_review_flow, pattern=r"^REVIEWFLOW\|"))
    app.add_handler(CallbackQueryHandler(on_addword_category, pattern=r"^ADDWORD\|CAT\|"))
    app.add_handler(CallbackQueryHandler(on_addword_button, pattern=r"^ADDWORD\|"))
    app.add_handler(CallbackQueryHandler(on_mywords_button, pattern=r"^MYWORDS\|"))
    app.add_handler(CallbackQueryHandler(on_tts_button, pattern=r"^TTS\|"))
    # Settings callbacks
    app.add_handler(CallbackQueryHandler(on_settings_button,pattern=r"^(SET_(TARGET|UI|HELPER)\||SETTINGS\||SETLEVEL\||PACKCAT\||PACKMOD\||PACKLOCK\||PACKDARK\||PACKOPEN\||PACKSTART\||PACKSCENE\||PKTOG\|)"))
    # Learn callbacks
    app.add_handler(CallbackQueryHandler(on_guess_button, pattern=r"^GUESS\|"))
    app.add_handler(CallbackQueryHandler(on_pronounce_button, pattern=r"^PRON\|"))
    app.add_handler(CallbackQueryHandler(on_scene_choice, pattern=r"^SCENE\|(START|SKIP)$"))
    app.add_handler(CallbackQueryHandler(on_scene_action, pattern=r"^SCENEACT\|"))
    app.add_handler(CallbackQueryHandler(on_scene_replay, pattern=r"^SCENEREPLAY\|"))
    app.add_handler(CallbackQueryHandler(on_ai_choice, pattern=r"^AI\|"))
    app.add_handler(CallbackQueryHandler(on_learn_skip, pattern=r"^LEARN\|SKIP$"))
    app.add_handler(CallbackQueryHandler(on_unlock_next, pattern=r"^UNLOCKNEXT\|"))
    app.add_handler(CallbackQueryHandler(on_journey_choice, pattern=r"^JOURNEY\|"))
    app.add_handler(CallbackQueryHandler(on_setlevel_button, pattern=r"^SETLEVEL\|"))


    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_router))

    app.add_error_handler(on_error)

    app.run_polling(drop_pending_updates=True)

   


if __name__ == "__main__":
    main()

