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
        "🧰 <b>/help</b> — Show this menu\n\n"
        "Tip: Journey is the recommended path. Packs are for custom training."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧭 Journey", callback_data="home:journey"),
         InlineKeyboardButton("📦 Packs", callback_data="home:packs")],
        [InlineKeyboardButton("📊 Progress", callback_data="home:progress"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
