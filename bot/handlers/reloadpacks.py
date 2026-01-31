from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.telegram import get_chat_sender
from bot.db import import_packs_from_folder

PACKS_FOLDER = "data/packs"


async def reloadpacks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)

    try:
        import_packs_from_folder()
        await msg.reply_text(f"✅ Packs reloaded from {PACKS_FOLDER}.")
    except Exception as e:
        await msg.reply_text(f"❌ Reload failed: {type(e).__name__}: {e}")
