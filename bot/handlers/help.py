from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)

    text = (
        "🫧 <b>LingoDojo — Command Menu</b>\n"
        "<i>(pick one)</i>\n\n"
        "⚡ <b>/learn</b> — Learn a new item (no repeats)\n"
        "🔁 <b>/review</b> — Review due items (SRS)\n"
        "📊 <b>/stats</b> — Progress + counts\n"
        "⚙️ <b>/settings</b> — Packs + languages + level\n"
        "🎯 <b>/setlevel</b> — Set A1/A2/B1…\n\n"
        "Tip: Activate packs in ⚙️ Settings, then /learn becomes a smooth stream."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Learn", callback_data="HOME|LEARN"),
         InlineKeyboardButton("🔁 Review", callback_data="HOME|REVIEW")],
        [InlineKeyboardButton("📊 Stats", callback_data="HOME|STATS"),
         InlineKeyboardButton("⚙️ Settings", callback_data="HOME|SETTINGS")],
    ])

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
