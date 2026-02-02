from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender
from bot.handlers.learn import start_pack_learn
from bot.handlers.review import review
from bot.db import get_due_item, get_pack_info, get_pack_item_counts
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


JOURNEY_PATH = [
    "it_a1_mission_airport_v2",
    "it_a1_mission_hotel_v1",
    "it_a2_mission_airport_glue_v1",
    "it_a2_mission_hotel_glue_v1",
    "it_b1_mission_airport_pressure_v1",
    "it_b1_mission_hotel_pressure_v1",
]

def _progress_bar(done: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "░" * width
    filled = int(round((done / total) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


async def journey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    user = update.effective_user

    lines = ["🧭 <b>Journey Progress</b>\n"]
    next_pack = None
    level_totals: dict[str, int] = {}
    level_done: dict[str, int] = {}
    unlocked_lines = []
    locked_lines = []
    for pid in JOURNEY_PATH:
        info = get_pack_info(pid)
        if not info:
            continue
        _, level, title, _, _, _, _, _ = info
        total, introduced = get_pack_item_counts(user.id, pid)
        level_key = (level or "A1").upper()
        level_totals[level_key] = level_totals.get(level_key, 0) + max(total, 0)
        level_done[level_key] = level_done.get(level_key, 0) + max(introduced, 0)
        if total <= 0:
            status = "⚪️"
        elif introduced >= total:
            status = "✅"
        else:
            status = "➡️"
            if not next_pack:
                next_pack = pid
        line = f"{status} {title} <i>({introduced} / {total})</i>"
        if status == "⚪️":
            locked_lines.append(line)
        else:
            unlocked_lines.append(line)

    if unlocked_lines:
        lines.extend(unlocked_lines)
    if locked_lines:
        lines.append("\n🔒 <b>Locked (advance to unlock)</b>:")
        lines.extend(locked_lines)

    current_section = "Complete"
    if next_pack:
        info = get_pack_info(next_pack)
        current_section = info[2] if info else "Current Pack"

    a1_bar = _progress_bar(level_done.get("A1", 0), level_totals.get("A1", 0))
    a2_bar = _progress_bar(level_done.get("A2", 0), level_totals.get("A2", 0))
    b1_bar = _progress_bar(level_done.get("B1", 0), level_totals.get("B1", 0))

    def pct(level: str) -> int:
        total = level_totals.get(level, 0)
        done = level_done.get(level, 0)
        return int(round((done / total) * 100)) if total else 0

    lines.append("\n━━━━━━━━━━━━━━")
    lines.append("📊 <b>Level Progress</b>")
    lines.append(f"A1 {a1_bar}  {pct('A1')}%")
    lines.append(f"A2 {a2_bar}  {pct('A2')}%")
    lines.append(f"B1 {b1_bar}  {pct('B1')}%")

    lines.append("\n🎯 <b>Current Mission</b>:")
    lines.append(f"{current_section}")
    lines.append("━━━━━━━━━━━━━━")

    lines.append(
        "\n🔁 <b>CORE LOOP (used everywhere)</b>\n"
        "Survival Phrases\n"
        "→ recognition + instant meaning\n"
        "(no forced sentence production)\n\n"
        "Core Words (Builder Packs)\n"
        "→ verbs, nouns, connectors that power phrases\n\n"
        "Micro‑Pronunciation 🔊 (NEW)\n"
        "→ shadow once, move on\n"
        "(no phonetics lectures)\n\n"
        "Daily Review (SRS)\n"
        "→ brutal honesty, fast grading\n\n"
        "Grammar Boosters\n"
        "→ only when the brain needs it\n"
        "(micro‑rules, not lessons)\n\n"
        "Missions (Roleplay) 🎭\n"
        "→ pressure + goal + validation\n"
        "(this is where fluency grows)\n\n"
        "Stories & Listening\n"
        "→ passive absorption + pattern noticing\n\n"
        "Fluency Challenges ⚔️\n"
        "→ time‑boxed, imperfect, real\n"
        "(“say it anyway” mode)\n\n"
        "Culture & Register Warnings 🧠\n"
        "→ short, sharp, actionable\n"
        "(never essays)\n\n"
        "✅ Every step ends with output\n"
        "(write, choose, respond, survive)"
    )

    if not next_pack:
        lines.append("\n🎉 Journey complete. Pick a pack to keep practicing.")

    kb_rows = []
    if next_pack:
        kb_rows.append([InlineKeyboardButton("▶️ Continue Journey", callback_data=f"JOURNEY|START|{next_pack}")])
    if get_due_item(user.id):
        kb_rows.append([InlineKeyboardButton("🔁 Review due", callback_data="JOURNEY|REVIEW")])
    kb_rows.append([InlineKeyboardButton("📦 Open Packs", callback_data="SETTINGS|PACKS")])

    await msg.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb_rows)
    )


async def on_journey_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    if len(parts) < 2:
        return

    action = parts[1] if len(parts) > 1 else ""
    if action == "REVIEW":
        await query.edit_message_text("🔁 Starting review…", parse_mode=ParseMode.HTML)
        await review(update, context)
        return

    if len(parts) < 3:
        return
    pack_id = parts[2]
    try:
        idx = JOURNEY_PATH.index(pack_id)
    except ValueError:
        idx = 0
    await query.edit_message_text("✅ Starting Journey…", parse_mode=ParseMode.HTML)
    await start_pack_learn(
        update,
        context,
        pack_id,
        journey_meta={"journey_path": JOURNEY_PATH, "journey_index": idx}
    )
