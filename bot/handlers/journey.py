from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender
from bot.handlers.learn import start_pack_learn, send_scene_prompt
from bot.handlers.review import review
from bot.db import get_due_item, get_pack_info, get_pack_item_counts, count_completed_scenarios, set_session, get_user_persona, get_due_count, pick_next_new_item_for_user, get_user_profile
from bot.scenarios import list_scenarios_by_pack_key
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


JOURNEY_PATH = [
    "it_a1_mission_airport_v2",
    "it_a1_mission_hotel_v1",
    "it_a2_mission_airport_glue_v1",
    "it_a2_mission_hotel_glue_v1",
    "it_b1_mission_airport_pressure_v1",
    "it_b1_mission_hotel_pressure_v1",
]

STAGES = [
    {"code": "A1", "title": "Survival Tools", "packs": ["it_a1_mission_airport_v2", "it_a1_mission_hotel_v1"]},
    {"code": "A2", "title": "Social Tools", "packs": ["it_a2_mission_airport_glue_v1", "it_a2_mission_hotel_glue_v1"]},
    {"code": "B1", "title": "Thinking Tools", "packs": ["it_b1_mission_airport_pressure_v1", "it_b1_mission_hotel_pressure_v1"]},
    {"code": "B2", "title": "Thinking Tools (Advanced)", "packs": []},
    {"code": "C1", "title": "Cultured Voice", "packs": []},
    {"code": "C2", "title": "Native+ Mastery", "packs": []},
]

def _progress_bar(done: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "░" * width
    filled = int(round((done / total) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

def _pack_key_for_id(pack_id: str) -> str:
    pid = (pack_id or "").lower()
    if "airport" in pid and "a1" in pid:
        return "airport_a1"
    if "airport" in pid and "a2" in pid:
        return "airport_a2"
    if "airport" in pid and "b1" in pid:
        return "airport_b1"
    if "hotel" in pid and "a1" in pid:
        return "hotel_a1"
    if "hotel" in pid and "a2" in pid:
        return "hotel_a2"
    if "hotel" in pid and "b1" in pid:
        return "hotel_b1"
    return "generic"

def _stage_scenarios(stage: dict) -> list[str]:
    ids: list[str] = []
    for pid in stage.get("packs") or []:
        pack_key = _pack_key_for_id(pid)
        scenarios = list_scenarios_by_pack_key(pack_key)
        ids.extend([s.get("scenario_id") for s in scenarios if s.get("scenario_id")])
    return ids

def _stage_progress(user_id: int, stage: dict) -> tuple[int, int]:
    total = 0
    done = 0
    for pid in stage.get("packs") or []:
        t, d = get_pack_item_counts(user_id, pid)
        total += max(t, 0)
        done += max(d, 0)
    return total, done

def _gatekeeper_done(user_id: int, stage: dict) -> bool:
    ids = _stage_scenarios(stage)
    if not ids:
        return True
    return count_completed_scenarios(user_id, ids) >= 1


async def journey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    user = update.effective_user

    # Determine current stage
    stage_current = None
    stage_gatekeeper_pending = False
    for stage in STAGES:
        total, done = _stage_progress(user.id, stage)
        if total <= 0:
            continue
        if done < total or not _gatekeeper_done(user.id, stage):
            stage_current = stage
            if done >= total and not _gatekeeper_done(user.id, stage):
                stage_gatekeeper_pending = True
            break

    # Next pack in journey path
    next_pack = None
    for pid in JOURNEY_PATH:
        total, introduced = get_pack_item_counts(user.id, pid)
        if total > 0 and introduced < total:
            next_pack = pid
            break

    stage_code = stage_current["code"] if stage_current else "Complete"
    stage_title = stage_current["title"] if stage_current else "Complete"
    total_stage, done_stage = _stage_progress(user.id, stage_current) if stage_current else (0, 0)
    pct = int(round((done_stage / total_stage) * 100)) if total_stage else 0
    bar = _progress_bar(done_stage, total_stage, width=10)

    due_count = get_due_count(user.id)
    profile = get_user_profile(user.id)
    target_lang = profile[0] if profile else "it"
    learn_available = bool(pick_next_new_item_for_user(user.id, target_lang))

    mission_line = "🎭 Mission: -"
    if next_pack:
        info = get_pack_info(next_pack)
        title = info[2] if info else "Mission"
        pack_key = _pack_key_for_id(next_pack)
        scenarios = list_scenarios_by_pack_key(pack_key)
        if scenarios:
            ids = [s.get("scenario_id") for s in scenarios if s.get("scenario_id")]
            done_s = count_completed_scenarios(user.id, ids)
            mission_line = f"🎭 Mission: {title} ({done_s}/{len(ids)})"

    lines = [
        "🧭 <b>Journey</b>",
        f"Stage: <b>{stage_code}</b> — {stage_title}",
        f"Progress: {done_stage}/{total_stage} ({pct}%) {bar}",
        "",
        "<b>Next up (3 mins):</b>",
        f"1. 🔁 Review due: {due_count}",
        f"2. 🧠 Learn new: {1 if learn_available else 0} card",
        f"3. {mission_line}",
    ]

    kb_rows = [
        [InlineKeyboardButton("▶️ Continue (recommended)", callback_data="JOURNEY|CONTINUE")],
        [InlineKeyboardButton("🧳 Open World Packs", callback_data="SETTINGS|PACKS")],
        [InlineKeyboardButton("📊 Progress", callback_data="home:progress"),
         InlineKeyboardButton("⚙️ Settings", callback_data="home:settings")],
    ]

    await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb_rows))


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
    if action == "CONTINUE":
        due_count = get_due_count(query.from_user.id)
        if due_count > 0:
            await query.edit_message_text("🔁 Starting review…", parse_mode=ParseMode.HTML)
            await review(update, context)
            return
        # Gatekeeper if pending
        stage_current = None
        stage_gatekeeper_pending = False
        for stage in STAGES:
            total, done = _stage_progress(query.from_user.id, stage)
            if total <= 0:
                continue
            if done < total or not _gatekeeper_done(query.from_user.id, stage):
                stage_current = stage
                if done >= total and not _gatekeeper_done(query.from_user.id, stage):
                    stage_gatekeeper_pending = True
                break
        if stage_current and stage_gatekeeper_pending:
            gate_pack = (stage_current.get("packs") or [None])[0]
            if gate_pack:
                await query.edit_message_text("🎭 Gatekeeper starting…", parse_mode=ParseMode.HTML)
                # reuse GATE path
                query.data = f"JOURNEY|GATE|{gate_pack}"
                await on_journey_choice(update, context)
                return
        # otherwise start next pack
        next_pack = None
        for pid in JOURNEY_PATH:
            total, introduced = get_pack_item_counts(query.from_user.id, pid)
            if total > 0 and introduced < total:
                next_pack = pid
                break
        if next_pack:
            await query.edit_message_text("✅ Starting Journey…", parse_mode=ParseMode.HTML)
            await start_pack_learn(
                update,
                context,
                next_pack,
                journey_meta={"continue_quota": 2, "continue_used": 0}
            )
            return
        await query.edit_message_text("🎉 Journey complete. Pick a pack.", parse_mode=ParseMode.HTML)
        return
    if action == "GATE":
        if len(parts) < 3:
            return
        pack_id = parts[2]
        pack_key = _pack_key_for_id(pack_id)
        scenarios = list_scenarios_by_pack_key(pack_key)
        scenario = None
        if scenarios:
            for s in scenarios:
                sid = s.get("scenario_id")
                if not sid:
                    continue
                if count_completed_scenarios(query.from_user.id, [sid]) == 0:
                    scenario = s
                    break
            if not scenario:
                scenario = scenarios[0]
        if not scenario:
            await query.edit_message_text("No gatekeeper scene available yet.")
            return
        persona = get_user_persona(query.from_user.id) or (None, None, None)
        p_name, p_city, p_role = persona
        meta = {
            "persona": {"name": p_name, "city": p_city, "role": p_role},
            "scene": {
                "pack_id": pack_id,
                "scene_id": scenario.get("scenario_id"),
                "intro_lines": ["🎭 Gatekeeper", "High‑pressure mission. Pass to advance."],
                "roleplay": scenario.get("roleplay") or {},
                "turns": (scenario.get("roleplay") or {}).get("turns") or [],
                "idx": 0,
            }
        }
        set_session(query.from_user.id, mode="learn", item_id=None, stage="scene_turn", meta=meta)
        await query.edit_message_text("🎭 Gatekeeper starting…", parse_mode=ParseMode.HTML)
        msg = get_chat_sender(update)
        await send_scene_prompt(msg, meta)
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
