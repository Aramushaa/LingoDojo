from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)

    text = (
        "🫧 <b>LingoDojo — Command Glass</b>\n"
        "<i>(tap a card)</i>\n\n"
        "🧭 <b>/journey</b> — Guided level‑up path\n"
        "📦 <b>/packs</b> — Browse packs\n"
        "📊 <b>/progress</b> — Stats + streak\n"
        "⚙️ <b>/settings</b> — Languages + level\n"
        "🧰 <b>/help</b> — Show this menu\n"
        "🎭 <b>/persona</b> — Edit your Alter‑Ego\n"
        "➕ <b>/add</b> — Add your own words\n"
        "🗂 <b>/mywords</b> — Browse your words\n"
        "🩺 <b>/ttscheck</b> — TTS health check\n"
        "🆘 <b>/sos</b> — Emergency help\n\n"
        "How it works:\n"
        "1) Learn → 2) Mission → 3) Review\n\n"
        "Tip: Journey is the recommended path. Packs are for custom training."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧭 Journey", callback_data="home:journey"),
         InlineKeyboardButton("📦 Packs", callback_data="home:packs")],
        [InlineKeyboardButton("📊 Progress", callback_data="home:progress"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def sos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_command(update, context)
