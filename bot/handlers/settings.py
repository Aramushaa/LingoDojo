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
    toggle_pack,get_user_level,
    set_user_level,
)

TARGET_LANG_OPTIONS = [("it", "🇮🇹 Italian"), ("en", "🇬🇧 English")]
UI_LANG_OPTIONS = [("en", "EN"), ("fa", "FA")]
HELPER_LANG_OPTIONS = [
    (None, "None"),
    ("fa", "FA (Persian)"),
    ("en", "EN"),
]





def build_settings_text(target: str, ui: str, helper: str | None, level: str):
    return (
        "⚙️ <b>Settings</b>\n\n"
        f"🌍 <b>Target</b>: {target}\n"
        f"🗣 <b>UI</b>: {ui}\n"
        f"🧩 <b>Helper</b>: {helper or 'None'}\n"
        f"🎯 <b>Level</b>: {level}\n\n"
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
    rows.append([InlineKeyboardButton("📦 Packs", callback_data="SETTINGS|PACKS")])
    rows.append([InlineKeyboardButton("🎯 Set Level", callback_data="SETTINGS|LEVEL")])



    return InlineKeyboardMarkup(rows)


LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5}


def _level_rank(level: str) -> int:
    return LEVEL_ORDER.get((level or "").upper(), 1)


def _is_unlocked(user_level: str, pack_level: str) -> bool:
    # Treat B1+ as B1 for gating
    norm = (pack_level or "A1").upper().replace("+", "")
    return _level_rank(user_level) >= _level_rank(norm)


def build_packs_text(target: str):
    return (
        "📦 <b>Packs</b>\n\n"
        "Choose a category:\n"
        f"Target language: <b>{target}</b>\n"
    )


def build_packs_keyboard(user_level: str):
    rows = [
        [InlineKeyboardButton("🧳 Survival Italian", callback_data="PACKCAT|survival")],
        [InlineKeyboardButton("🟥 Dark Mode (locked)", callback_data="PACKCAT|dark")],
        [InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|BACK")],
    ]
    return InlineKeyboardMarkup(rows)


def build_category_text(category_key: str) -> str:
    if category_key == "survival":
        return (
            "🧳 <b>Survival Italian</b>\n\n"
            "Pick a module:"
        )
    if category_key == "dark":
        return (
            "🟥 <b>Dark Mode</b>\n\n"
            "These packs are gated and include risky phrases.\n"
            "Learn for understanding only."
        )
    return "📦 <b>Packs</b>"


def build_category_keyboard(category_key: str):
    rows = []
    if category_key == "survival":
        rows.append([InlineKeyboardButton("✈️ Airport", callback_data="PACKMOD|airport")])
        rows.append([InlineKeyboardButton("☕ Bar", callback_data="PACKMOD|bar")])
    elif category_key == "dark":
        rows.append([InlineKeyboardButton("✈️ Airport Dark Mode", callback_data="PACKMOD|airport_dark")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|PACKS")])
    return InlineKeyboardMarkup(rows)


def build_module_text(module_key: str, user_level: str) -> str:
    if module_key == "airport":
        return (
            "✈️ <b>Airport</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "airport_dark":
        return (
            "🟥 <b>Airport Dark Mode</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "⚠️ These phrases can escalate situations.\n"
            "Learn for understanding only — do NOT use casually."
        )
    if module_key == "bar":
        return (
            "☕ <b>Bar</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    return "📦 <b>Packs</b>"


def build_module_keyboard(user_id: int, target: str, user_level: str, module_key: str):
    packs = list_packs(target)
    active = set(get_user_active_packs(user_id))
    pack_map = {pid: (lvl, title, desc) for pid, lvl, title, desc in packs}

    rows = []

    if module_key in ("airport", "airport_dark"):
        ordered = [
            ("it_a1_mission_airport_v2", "🟢 Core Survival"),
            ("it_a2_mission_airport_glue_v1", "🔒 Glue & Expansion"),
            ("it_b1_mission_airport_pressure_v1", "🔒 Real Pressure"),
            ("it_b1_mission_airport_dark_v1", "🟥 Dark Mode"),
        ]
        if module_key == "airport_dark":
            ordered = [("it_b1_mission_airport_dark_v1", "🟥 Dark Mode")]

        for pack_id, label in ordered:
            if pack_id not in pack_map:
                continue
            level, title, description = pack_map[pack_id]
            unlocked = _is_unlocked(user_level, level)
            on = pack_id in active
            if unlocked:
                state = "✅" if on else "⬜"
                rows.append([InlineKeyboardButton(f"{state} {label}", callback_data=f"PKTOG|{pack_id}|{module_key}")])
            else:
                rows.append([InlineKeyboardButton(f"🔒 {label} (unlock {level})", callback_data=f"PACKLOCK|{level}|{module_key}")])
    elif module_key == "bar":
        # Simple Bar module (A1 only for now)
        for pack_id in ("it_a1_mission_bar_v2",):
            if pack_id not in pack_map:
                continue
            level, title, description = pack_map[pack_id]
            unlocked = _is_unlocked(user_level, level)
            on = pack_id in active
            if unlocked:
                state = "✅" if on else "⬜"
                rows.append([InlineKeyboardButton(f"{state} {title}", callback_data=f"PKTOG|{pack_id}|{module_key}")])
            else:
                rows.append([InlineKeyboardButton(f"🔒 {title} (unlock {level})", callback_data=f"PACKLOCK|{level}|{module_key}")])

    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|PACKS")])
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
    level = get_user_level(user.id)
    await msg.reply_text(
        build_settings_text(target, ui, helper, level),
        reply_markup=build_settings_keyboard(target, ui, helper),
        parse_mode="HTML",
    )


async def open_packs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    profile = get_user_profile(user.id)
    if not profile:
        msg = get_chat_sender(update)
        await msg.reply_text("Use /start first.")
        return
    target, ui, helper = profile
    level = get_user_level(user.id)

    msg = get_chat_sender(update)
    await msg.reply_text(
        build_packs_text(target),
        reply_markup=build_packs_keyboard(level),
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
        level = get_user_level(user.id)
        await query.edit_message_text(
            build_packs_text(target),
            reply_markup=build_packs_keyboard(level),
            parse_mode="HTML",
        )
        return

    if data == "SETTINGS|BACK":
        # reload profile in case changed
        target, ui, helper = get_user_profile(user.id)
        level = get_user_level(user.id)
        await query.edit_message_text(
            build_settings_text(target, ui, helper, level),
            reply_markup=build_settings_keyboard(target, ui, helper),
            parse_mode="HTML",
        )
        return

    
    if data == "SETTINGS|LEVEL":
        current = get_user_level(user.id)
        await query.edit_message_text(
            f"🎯 <b>Choose your level</b>\nCurrent: <b>{current}</b>",
            reply_markup=build_level_keyboard(current),
            parse_mode="HTML",
        )
        return

    if data.startswith("PACKCAT|"):
        _, category = data.split("|", 1)
        await query.edit_message_text(
            build_category_text(category),
            reply_markup=build_category_keyboard(category),
            parse_mode="HTML",
        )
        return

    if data.startswith("PACKMOD|"):
        _, module_key = data.split("|", 1)
        level = get_user_level(user.id)
        if module_key == "airport_dark":
            await query.edit_message_text(
                build_module_text(module_key, level),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚠️ I Understand — Continue", callback_data="PACKDARK|airport_dark")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="PACKCAT|dark")],
                ]),
            )
            return
        await query.edit_message_text(
            build_module_text(module_key, level),
            reply_markup=build_module_keyboard(user.id, target, level, module_key),
            parse_mode="HTML",
        )
        return

    if data.startswith("PACKDARK|"):
        _, module_key = data.split("|", 1)
        level = get_user_level(user.id)
        await query.edit_message_text(
            build_module_text(module_key, level),
            reply_markup=build_module_keyboard(user.id, target, level, module_key),
            parse_mode="HTML",
        )
        return

    if data.startswith("PACKLOCK|"):
        _, lock_level, module_key = data.split("|", 2)
        await query.edit_message_text(
            f"🔒 <b>Locked</b>\n\nThis pack unlocks at <b>{lock_level}</b>.\n"
            "Go to ⚙️ Settings → 🎯 Set Level if needed.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"PACKMOD|{module_key}")]]),
        )
        return
    
    if data.startswith("SETLEVEL|"):
        _, level_code = data.split("|", 1)
        set_user_level(user.id, level_code)

        # go back to settings screen
        target, ui, helper = get_user_profile(user.id)
        level = get_user_level(user.id)

        await query.edit_message_text(
            build_settings_text(target, ui, helper, level),
            reply_markup=build_settings_keyboard(target, ui, helper),
            parse_mode="HTML",
        )
        return



    # ACTIONS
    parts = data.split("|")
    action = parts[0]

    if action == "SET_TARGET":
        code = parts[1]
        set_user_target_language(user.id, code)
    elif action == "SET_UI":
        code = parts[1]
        set_user_ui_language(user.id, code)
    elif action == "SET_HELPER":
        code = parts[1]
        helper_code = None if code == "none" else code
        set_user_helper_language(user.id, helper_code)
    elif action == "PKTOG":
        pack_id = parts[1] if len(parts) > 1 else ""
        module_key = parts[2] if len(parts) > 2 else ""
        toggle_pack(user.id, pack_id)
        level = get_user_level(user.id)
        # stay on module screen if available
        if module_key:
            await query.edit_message_text(
                build_module_text(module_key, level),
                reply_markup=build_module_keyboard(user.id, target, level, module_key),
                parse_mode="HTML",
            )
            return
        await query.edit_message_text(
            build_packs_text(target),
            reply_markup=build_packs_keyboard(level),
            parse_mode="HTML",
        )
        return

    # refresh settings view
    target, ui, helper = get_user_profile(user.id)
    level = get_user_level(user.id)

    await query.edit_message_text(
        build_settings_text(target, ui, helper, level),
        reply_markup=build_settings_keyboard(target, ui, helper),
        parse_mode="HTML",
    )


LEVELS = ["A1", "A2", "B1", "B2", "C1"]

def build_level_keyboard(current: str):
    rows = []
    row = []
    for lv in LEVELS:
        prefix = "✅ " if lv == current else ""
        row.append(InlineKeyboardButton(f"{prefix}{lv}", callback_data=f"SETLEVEL|{lv}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|BACK")])
    return InlineKeyboardMarkup(rows)
