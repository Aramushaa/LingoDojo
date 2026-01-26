from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from bot.db import get_connection

def format_pretty_date(iso_str: str) -> str:
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%d %b %Y, %H:%M")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, created_at FROM users WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    conn.close()

    if row is None:
        await update.message.reply_text("No profile found. Use /start first.")
        return

    first_name, created_at_iso = row
    pretty = format_pretty_date(created_at_iso)

    await update.message.reply_text(
        f"📊 Your Stats\n"
        f"👤 Name: {first_name}\n"
        f"🆔 User ID: {user.id}\n"
        f"📅 Joined: {pretty}\n"
    )
