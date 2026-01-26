from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.handlers.learn import learn
from bot.handlers.review import review
from bot.handlers.stats import stats
from bot.handlers.settings import settings

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Learn", callback_data="NAV|learn"),
            InlineKeyboardButton("🧠 Review", callback_data="NAV|review"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="NAV|stats"),
            InlineKeyboardButton("⚙️ Settings", callback_data="NAV|settings"),
        ]
    ])

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Quick menu 👇", reply_markup=main_menu_keyboard())

async def on_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, dest = query.data.split("|", 1)

    command_map = {
        "learn": "/learn",
        "review": "/review",
        "stats": "/stats",
        "settings": "/settings",
    }

    await query.message.reply_text(f"Tap this command:\n{command_map[dest]}")
