# bot/handlers/settings.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.telegram import get_chat_sender

from bot.db import (
    get_user_profile,
    set_user_target_language,
    set_user_ui_language,
    set_user_helper_language,
    list_packs,
    get_user_active_packs,
    toggle_pack,
)

TARGET_LANG_OPTIONS = [("it", "🇮🇹 Italian"), ("en", "🇬🇧 English")]
UI_LANG_OPTIONS = [("en", "EN"), ("fa", "FA")]
HELPER_LANG_OPTIONS = [
    (None, "None"),
    ("fa", "FA (Persian)"),
    ("en", "EN"),
]


def _label(code: str | None) -> str:
    if code is None:
        return "None"
    return code


def build_settings_text(target: str, ui: str, helper: str | None):
    return (
        "⚙️ <b>Settings</b>\n\n"
        f"🌍 <b>Target</b>: {_label(target)}\n"
        f"🗣 <b>UI</b>: {_label(ui)}\n"
        f"🧩 <b>Helper</b>: {_label(helper)}\n\n"
        "Choose what you want to change:"
    )


def build_settings_keyboard(target: str, ui: str, helper: str | None):
    rows = []

    # Target language row
    row = []
    for code, label in TARGET_LANG_OPTIONS:
        prefix = "✅ " if code == target else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"SET_TARGET|{code}"))
    rows.append(row)

    # UI language row
    row = []
    for code, label in UI_LANG_OPTIONS:
        prefix = "✅ " if code == ui else ""
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"SET_UI|{code}"))
    rows.append(row)

    # Helper language row
    row = []
    for code, label in HELPER_LANG_OPTIONS:
        prefix = "✅ " if code == helper else ""
        code_str = "none" if code is None else code
        row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"SET_HELPER|{code_str}"))
    rows.append(row)

    # Packs button
    rows.append([InlineKeyboardButton("📦 Packs (activate/deactivate)", callback_data="SETTINGS|PACKS")])

    return InlineKeyboardMarkup(rows)


def build_packs_text(target: str):
    return (
        "📦 <b>Packs</b>\n\n"
        "Tap to toggle packs ON/OFF.\n"
        f"Target language: <b>{target}</b>\n"
    )


def build_packs_keyboard(user_id: int, target: str):
    packs = list_packs(target)
    active = set(get_user_active_packs(user_id))

    rows = []
    for pack_id, level, title, description in packs:
        on = pack_id in active
        label = f"✅ {title}" if on else f"⬜ {title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"PKTOG|{pack_id}")])

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|BACK")])
    return InlineKeyboardMarkup(rows)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    profile = get_user_profile(user.id)
    if not profile:
        msg = get_chat_sender(update)
        await msg.reply_text("Use /start first.")
        return

    target, ui, helper = profile

    msg = get_chat_sender(update)
    await msg.reply_text(
        build_settings_text(target, ui, helper),
        reply_markup=build_settings_keyboard(target, ui, helper),
        parse_mode="HTML",
    )


async def on_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    profile = get_user_profile(user.id)
    if not profile:
        await query.edit_message_text("Use /start first.")
        return

    target, ui, helper = profile

    # NAV
    if data == "SETTINGS|PACKS":
        await query.edit_message_text(
            build_packs_text(target),
            reply_markup=build_packs_keyboard(user.id, target),
            parse_mode="HTML",
        )
        return

    if data == "SETTINGS|BACK":
        # reload profile in case changed
        target, ui, helper = get_user_profile(user.id)
        await query.edit_message_text(
            build_settings_text(target, ui, helper),
            reply_markup=build_settings_keyboard(target, ui, helper),
            parse_mode="HTML",
        )
        return

    # ACTIONS
    action, code = data.split("|", 1)

    if action == "SET_TARGET":
        set_user_target_language(user.id, code)
    elif action == "SET_UI":
        set_user_ui_language(user.id, code)
    elif action == "SET_HELPER":
        helper_code = None if code == "none" else code
        set_user_helper_language(user.id, helper_code)
    elif action == "PKTOG":
        toggle_pack(user.id, code)
        # stay on packs screen
        await query.edit_message_text(
            build_packs_text(target),
            reply_markup=build_packs_keyboard(user.id, target),
            parse_mode="HTML",
        )
        return

    # refresh settings view
    target, ui, helper = get_user_profile(user.id)
    await query.edit_message_text(
        build_settings_text(target, ui, helper),
        reply_markup=build_settings_keyboard(target, ui, helper),
        parse_mode="HTML",
    )
