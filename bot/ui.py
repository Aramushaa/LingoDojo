from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Learn", callback_data="home:learn"),
         InlineKeyboardButton("🔁 Review", callback_data="home:review")],
        [InlineKeyboardButton("📊 Stats", callback_data="home:stats"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ])
