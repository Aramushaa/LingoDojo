from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)

    text = (
        "🫧 <b>LingoDojo — Command Glass</b>\n"
        "<i>(tap a card)</i>\n\n"
        "🧠 <b>/learn</b> — New items from active packs\n"
        "🎯 <b>/missions</b> — Mission flow (inside Learn)\n"
        "📦 <b>/packs</b> — Browse & activate packs\n"
        "📊 <b>/progress</b> — Stats + streak\n"
        "⚙️ <b>/settings</b> — Languages + level\n"
        "🧰 <b>/help</b> — Show this menu\n\n"
        "Tip: Activate packs in 📦 Packs, then /learn becomes a smooth stream."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Learn", callback_data="home:learn"),
         InlineKeyboardButton("🎯 Missions", callback_data="home:missions")],
        [InlineKeyboardButton("📦 Packs", callback_data="home:packs"),
         InlineKeyboardButton("📊 Progress", callback_data="home:progress")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
