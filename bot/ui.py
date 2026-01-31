from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Learn", callback_data="home:learn"),
         InlineKeyboardButton("🎯 Missions", callback_data="home:missions")],
        [InlineKeyboardButton("📦 Packs", callback_data="home:packs"),
         InlineKeyboardButton("📊 Progress", callback_data="home:progress")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])
