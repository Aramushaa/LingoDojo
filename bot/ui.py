from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧭 Journey", callback_data="home:journey"),
         InlineKeyboardButton("📦 Packs", callback_data="home:packs")],
        [InlineKeyboardButton("📊 Progress", callback_data="home:progress"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])
