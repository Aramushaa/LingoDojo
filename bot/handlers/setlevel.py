from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.telegram import get_chat_sender
from bot.db import get_user_level, set_user_level

LEVELS = ["A1", "A2", "B1", "B2", "C1"]

def _kb(current: str):
    rows = []
    row = []
    for lv in LEVELS:
        prefix = "✅ " if lv == current else ""
        row.append(InlineKeyboardButton(f"{prefix}{lv}", callback_data=f"SETLEVEL|{lv}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)

async def setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    current = get_user_level(user.id)
    msg = get_chat_sender(update)
    await msg.reply_text(
        f"🎚 Choose your level (current: {current})",
        reply_markup=_kb(current),
    )

async def on_setlevel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    _, lv = query.data.split("|", 1)

    if lv not in LEVELS:
        await query.edit_message_text("Invalid level.")
        return

    set_user_level(user.id, lv)
    await query.edit_message_text(f"✅ Level saved: {lv}")
