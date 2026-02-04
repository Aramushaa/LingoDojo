# bot/handlers/settings.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.utils.telegram import get_chat_sender
from bot.scenarios import list_scenarios_by_pack_key
from bot.db import count_completed_scenarios
from html import escape


from bot.db import (
    get_user_profile,
    set_user_target_language,
    set_user_ui_language,
    set_user_helper_language,
    list_packs,
    get_user_level,
    set_user_level,
    get_pack_info,
    get_pack_item_counts,
)
from bot.handlers.learn import start_pack_learn
from bot.handlers.review import review_pack

TARGET_LANG_OPTIONS = [("it", "🇮🇹 Italian"), ("en", "🇬🇧 English")]
UI_LANG_OPTIONS = [("en", "EN"), ("fa", "FA")]
HELPER_LANG_OPTIONS = [
    (None, "None"),
    ("fa", "FA (Persian)"),
    ("en", "EN"),
]




def h(text: str) -> str:
    return escape(text or "")

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
    rows.append([InlineKeyboardButton("🎭 Alter‑Ego", callback_data="SETTINGS|PERSONA")])
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
        "Tip: Pick a pack and start — no activation needed."
    )


def build_packs_keyboard(user_level: str):
    rows = [
        [InlineKeyboardButton("🧠 Foundation", callback_data="PACKCAT|foundation")],
        [InlineKeyboardButton("🧳 Survival Italian", callback_data="PACKCAT|survival")],
        [InlineKeyboardButton("🟥 Dark Mode ", callback_data="PACKCAT|dark")],
        [InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|BACK")],
    ]
    return InlineKeyboardMarkup(rows)


def build_category_text(category_key: str) -> str:
    if category_key == "foundation":
        return (
            "🧠 <b>Foundation</b>\n\n"
            "Pick a category:"
        )
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


def build_category_keyboard(category_key: str, pack_ids: set[str]):
    rows = []
    if category_key == "foundation":
        if any("foundation_verbs" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🧱 Survival Verbs", callback_data="PACKMOD|foundation_verbs")])
        if any("foundation_phrases" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("💬 Instant Phrases", callback_data="PACKMOD|foundation_phrases")])
        if any("foundation_numbers_time_price" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("⏱ Numbers • Time • Price", callback_data="PACKMOD|foundation_numbers")])
        if any("foundation_repair_yesno" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🛠 Yes/No & Repair", callback_data="PACKMOD|foundation_repair")])
        if any("foundation_response_glue" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🧩 Response Glue", callback_data="PACKMOD|foundation_response")])
        if any("foundation_politeness_modulators" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🎛 Politeness Modulators", callback_data="PACKMOD|foundation_politeness")])
    elif category_key == "survival":
        if any("airport" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("✈️ Airport", callback_data="PACKMOD|airport")])
        if any("hotel" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🏨 Hotel / Airbnb", callback_data="PACKMOD|hotel")])
    elif category_key == "dark":
        if any("airport_dark" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("✈️ Airport Dark Mode", callback_data="PACKMOD|airport_dark")])
        if any("hotel_dark" in pid for pid in pack_ids):
            rows.append([InlineKeyboardButton("🏨 Hotel Dark Mode", callback_data="PACKMOD|hotel_dark")])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="SETTINGS|PACKS")])
    return InlineKeyboardMarkup(rows)


def build_module_text(module_key: str, user_level: str) -> str:
    if module_key == "foundation_verbs":
        return (
            "🧱 <b>Survival Verbs</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "foundation_phrases":
        return (
            "🧱 <b>Instant Phrases</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "foundation_numbers":
        return (
            "🧱 <b>Numbers • Time • Price</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "foundation_repair":
        return (
            "🧱 <b>Yes/No & Repair</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "foundation_response":
        return (
            "🧱 <b>Response Glue</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "foundation_politeness":
        return (
            "🧱 <b>Politeness Modulators</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "airport":
        return (
            "✈️ <b>Airport</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "Pick a pack:"
        )
    if module_key == "hotel":
        return (
            "🏨 <b>Hotel / Airbnb</b>\n\n"
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
    if module_key == "hotel_dark":
        return (
            "🟥 <b>Hotel Dark Mode</b>\n\n"
            f"Your level: <b>{user_level}</b>\n"
            "⚠️ These phrases can escalate situations.\n"
            "Learn for understanding only — do NOT use casually."
        )
    return "📦 <b>Packs</b>"


def build_pack_detail_text(pack_info, active: bool, user_level: str, user_id: int | None = None) -> str:
    if not pack_info:
        return "Pack not found."
    pack_id, level, title, description, pack_type, chunk_size, missions_enabled, _ = pack_info
    total, introduced = (0, 0)
    if user_id is not None:
        total, introduced = get_pack_item_counts(user_id, pack_id)
    # scenario progress (if any)
    pack_key = "generic"
    pid = (pack_id or "").lower()
    if "airport" in pid and "a1" in pid:
        pack_key = "airport_a1"
    elif "airport" in pid and "a2" in pid:
        pack_key = "airport_a2"
    elif "airport" in pid and "b1" in pid:
        pack_key = "airport_b1"
    elif "hotel" in pid and "a1" in pid:
        pack_key = "hotel_a1"
    elif "hotel" in pid and "a2" in pid:
        pack_key = "hotel_a2"
    elif "hotel" in pid and "b1" in pid:
        pack_key = "hotel_b1"
    scenarios = list_scenarios_by_pack_key(pack_key)
    scenario_line = ""
    if scenarios and user_id is not None:
        ids = [s.get("scenario_id") for s in scenarios if s.get("scenario_id")]
        done = count_completed_scenarios(user_id, ids)
        scenario_line = f"\nScenes: {done}/{len(ids)}"
    elif scenarios:
        scenario_line = f"\nScenes: {len(scenarios)}"
    return (
        f"📦 <b>{h(title)}</b>\n\n"
        f"Level: <b>{h(level or 'A1')}</b>\n"
        f"Cards: <b>{introduced}/{total}</b>\n"
        f"Type: <b>{h(pack_type or 'word')}</b>\n"
        f"{scenario_line}\n"
        f"What you'll be able to do: <b>{h(description or '')}</b>"
    )


def build_pack_detail_keyboard(pack_id: str, module_key: str, active: bool, resume_label: str = "▶️ Start"):
    back_cb = f"PACKMOD|{module_key}"
    if module_key == "list":
        back_cb = "SETTINGS|PACKS"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(resume_label, callback_data=f"PACKSTART|journey|{pack_id}|{module_key}")],
        [InlineKeyboardButton("🎭 Play scene", callback_data=f"PACKSCENE|{pack_id}")],
        [InlineKeyboardButton("🔁 Review this pack", callback_data=f"PACKSTART|review|{pack_id}|{module_key}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=back_cb)],
    ])


def build_module_keyboard(user_id: int, target: str, user_level: str, module_key: str):
    packs = list_packs(target)
    pack_map = {pid: (lvl, title, desc) for pid, lvl, title, desc in packs}

    rows = []

    if module_key in ("foundation_verbs", "foundation_phrases", "foundation_numbers", "foundation_repair", "foundation_response", "foundation_politeness"):
        if module_key == "foundation_verbs":
            prefix = "foundation_verbs"
        elif module_key == "foundation_phrases":
            prefix = "foundation_phrases"
        elif module_key == "foundation_numbers":
            prefix = "foundation_numbers_time_price"
        elif module_key == "foundation_repair":
            prefix = "foundation_repair_yesno"
        elif module_key == "foundation_response":
            prefix = "foundation_response_glue"
        else:
            prefix = "foundation_politeness_modulators"

        for pack_id, (level, title, description) in pack_map.items():
            if prefix not in pack_id:
                continue
            unlocked = _is_unlocked(user_level, level)
            title_label = title
            if level and f"({level})" not in title_label:
                title_label = f"{title_label} ({level})"
            label = f"{title_label}"
            if unlocked:
                rows.append([InlineKeyboardButton(label, callback_data=f"PACKOPEN|{pack_id}|{module_key}")])
            else:
                rows.append([InlineKeyboardButton(f"🔒 {label} (unlock {level})", callback_data=f"PACKLOCK|{level}|{module_key}")])

    elif module_key in ("airport", "airport_dark"):
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
            if unlocked:
                rows.append([InlineKeyboardButton(f"{label}", callback_data=f"PACKOPEN|{pack_id}|{module_key}")])
            else:
                rows.append([InlineKeyboardButton(f"🔒 {label} (unlock {level})", callback_data=f"PACKLOCK|{level}|{module_key}")])
    elif module_key in ("hotel", "hotel_dark"):
        ordered = [
            ("it_a1_mission_hotel_v1", "🟢 Core Survival"),
            ("it_a2_mission_hotel_glue_v1", "🔒 Glue & Expansion"),
            ("it_b1_mission_hotel_pressure_v1", "🔒 Real Pressure"),
            ("it_b1_mission_hotel_dark_v1", "🟥 Dark Mode"),
        ]
        if module_key == "hotel_dark":
            ordered = [("it_b1_mission_hotel_dark_v1", "🟥 Dark Mode")]

        for pack_id, label in ordered:
            if pack_id not in pack_map:
                continue
            level, title, description = pack_map[pack_id]
            unlocked = _is_unlocked(user_level, level)
            if unlocked:
                rows.append([InlineKeyboardButton(f"{label}", callback_data=f"PACKOPEN|{pack_id}|{module_key}")])
            else:
                rows.append([InlineKeyboardButton(f"🔒 {label} (unlock {level})", callback_data=f"PACKLOCK|{level}|{module_key}")])

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
        await query.edit_message_text(
            build_packs_text(target),
            reply_markup=build_packs_keyboard(get_user_level(user.id)),
            parse_mode="HTML",
        )
        return
    if data == "SETTINGS|PERSONA":
        from bot.handlers.persona import persona_command
        await persona_command(update, context)
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
        packs = list_packs(target)
        pack_ids = {pid for pid, _, _, _ in packs}
        await query.edit_message_text(
            build_category_text(category),
            reply_markup=build_category_keyboard(category, pack_ids),
            parse_mode="HTML",
        )
        return

    if data.startswith("PACKMOD|"):
        _, module_key = data.split("|", 1)
        level = get_user_level(user.id)
        if module_key in ("airport_dark", "hotel_dark"):
            await query.edit_message_text(
                build_module_text(module_key, level),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚠️ I Understand — Continue", callback_data=f"PACKDARK|{module_key}")],
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

    if data.startswith("PACKOPEN|"):
        _, pack_id, module_key = data.split("|", 2)
        pack_info = get_pack_info(pack_id)
        level = get_user_level(user.id)
        total, introduced = get_pack_item_counts(user.id, pack_id)
        resume_label = "▶️ Resume" if introduced > 0 and introduced < total else "▶️ Start"
        await query.edit_message_text(
            build_pack_detail_text(pack_info, False, level, user.id),
            parse_mode="HTML",
            reply_markup=build_pack_detail_keyboard(pack_id, module_key, False, resume_label),
        )
        return

    if data.startswith("PACKSTART|"):
        _, action, pack_id, module_key = data.split("|", 3)
        if action == "journey":
            await start_pack_learn(update, context, pack_id)
        elif action == "review":
            await review_pack(update, context, pack_id)
        return

    if data.startswith("PACKSCENE|"):
        _, pack_id = data.split("|", 1)
        from bot.handlers.learn import start_pack_scene
        await start_pack_scene(update, context, pack_id)
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
        module_key = parts[2] if len(parts) > 2 else "tools"
        await query.edit_message_text(
            "✅ Pack activation has been removed.\n\nStart a pack directly instead.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"PACKMOD|{module_key}")]]),
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
