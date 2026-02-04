from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧭 Journey", callback_data="home:journey"),
         InlineKeyboardButton("➕ Add", callback_data="home:add")],
        [InlineKeyboardButton("📦 Packs", callback_data="home:packs"),
         InlineKeyboardButton("🗂 My Words", callback_data="home:mywords")],
        [InlineKeyboardButton("📊 Progress", callback_data="home:progress"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])
