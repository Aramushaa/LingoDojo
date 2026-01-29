from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from bot.db import get_connection
from bot.ui import home_keyboard
from bot.utils.telegram import get_chat_sender


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (user_id, first_name, created_at, target_language, ui_language, helper_language)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user.id, user.first_name, utc_now_iso(), "it", "en", None)

    )
    conn.commit()
    conn.close()

    msg = get_chat_sender(update)
    await msg.reply_text(
    "Welcome to LingoDojo 🥋\nPick a mode:",
    reply_markup=home_keyboard()
    )


