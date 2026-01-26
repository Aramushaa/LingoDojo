from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from bot.config import WEBAPP_URL
from bot.db import get_connection

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, created_at) VALUES (?, ?, ?)",
        (user.id, user.first_name, utc_now_iso())
    )
    conn.commit()
    conn.close()

    keyboard = [[InlineKeyboardButton("🚀 Open Mini WebApp", web_app=WebAppInfo(url=WEBAPP_URL))]]

    await update.message.reply_text(
        f"Welcome {user.first_name}! 👋\nYour profile is saved.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
