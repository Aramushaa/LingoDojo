from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.db import get_user_languages, set_user_target_language, set_user_ui_language
from bot.utils.telegram import get_chat_sender

# MVP options (we can add more later)
TARGET_LANG_OPTIONS = [("it", "🇮🇹 Italian"), ("en", "🇬🇧 English")]
UI_LANG_OPTIONS = [("en", "EN"), ("fa", "FA")]

def build_settings_keyboard(current_target: str, current_ui: str):
    rows = []

    # Target language buttons
    target_row = []
    for code, label in TARGET_LANG_OPTIONS:
        prefix = "✅ " if code == current_target else ""
        target_row.append(
            InlineKeyboardButton(f"{prefix}{label}", callback_data=f"SET_TARGET|{code}")
        )
    rows.append(target_row)

    # UI language buttons
    ui_row = []
    for code, label in UI_LANG_OPTIONS:
        prefix = "✅ " if code == current_ui else ""
        ui_row.append(
            InlineKeyboardButton(f"{prefix}{label}", callback_data=f"SET_UI|{code}")
        )
    rows.append(ui_row)

    return InlineKeyboardMarkup(rows)

def build_settings_text(current_target: str, current_ui: str):
    return (
        "⚙️ Settings\n\n"
        f"🌍 Target language: {current_target}\n"
        f"🗣 UI language: {current_ui}\n\n"
        "Tap buttons to change."
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    langs = get_user_languages(user.id)
    if not langs:
        msg = get_chat_sender(update)
        await msg.reply_text("Use /start first.")
        return

    current_target, current_ui = langs

    msg = get_chat_sender(update)
    await msg.reply_text(
        build_settings_text(current_target, current_ui),
        reply_markup=build_settings_keyboard(current_target, current_ui),
    )

async def on_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    # Example data: "SET_TARGET|it" or "SET_UI|fa"
    action, code = data.split("|", 1)

    if action == "SET_TARGET":
        set_user_target_language(user.id, code)
    elif action == "SET_UI":
        set_user_ui_language(user.id, code)

    # Re-read updated values
    current_target, current_ui = get_user_languages(user.id)

    await query.edit_message_text(
        build_settings_text(current_target, current_ui),
        reply_markup=build_settings_keyboard(current_target, current_ui),
    )
