from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape

from bot.utils.telegram import get_chat_sender
from bot.config import SHOW_DICT_DEBUG


from bot.db import (
    list_packs, activate_pack, get_user_active_packs,
    pick_one_item_from_pack, set_session, get_session,
    clear_session, get_item_by_id, ensure_review_row,
    get_user_languages, get_lexicon_cache_it,pick_one_item_for_user,
    pick_next_new_item_for_user,
    pick_next_new_item_for_user_in_pack,
    get_active_items_total,
    get_active_items_introduced,get_user_profile,
    get_random_context_for_item, get_item_holographic_meta,
    get_learn_since_scene,
    set_learn_since_scene,
    pick_one_scene_for_user_active_packs,
    get_random_meanings_from_active_packs,
    get_random_meanings_from_pack,
    get_pack_info,
    get_pack_item_counts,
    mark_item_mature,
    get_learned_terms_for_pack,
    mark_scenario_completed,
    record_practice,
    upsert_user_pack_progress,
    set_user_journey_progress,
    get_user_persona,

)
from bot.scenarios import pick_scenario_for_pack, list_scenarios_by_pack_key
from bot.storyline import get_current_story_beat, advance_story

from bot.services.dictionary_it import validate_it_term
from bot.services.ai_feedback import generate_learn_feedback,generate_reverse_context_quiz,generate_roleplay_feedback 
from bot.services.validation import validate_sentence, build_anchors
import random
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.tts_edge import tts_it


SCENE_EVERY_N_NEW_ITEMS = 3

import time

def _continue_quota_reached(meta: dict | None) -> bool:
    if not meta:
        return False
    quota = int(meta.get("continue_quota") or 0)
    used = int(meta.get("continue_used") or 0)
    return quota > 0 and used >= quota

def _increment_continue_used(meta: dict | None) -> dict:
    meta = meta or {}
    meta["continue_used"] = int(meta.get("continue_used") or 0) + 1
    return meta

def _max_scenarios_for_level(level: str) -> int:
    if (level or "").upper() == "A1":
        return 2
    if (level or "").upper() == "A2":
        return 3
    return 4


def _update_progress_meta(meta: dict, term: str, ok: bool, phase: str | None = None) -> tuple[dict, bool, bool]:
    """
    Update streak + error counts.
    Returns (meta, trigger_error, trigger_phase).
    """
    meta = meta or {}
    error_counts = meta.get("error_counts") or {}
    correct_streak = int(meta.get("correct_streak", 0))
    phases_seen = set(meta.get("phases_seen") or [])

    trigger_error = False
    trigger_phase = False

    if ok:
        correct_streak += 1
        error_counts.pop(term, None)
    else:
        correct_streak = 0
        error_counts[term] = int(error_counts.get(term, 0)) + 1
        if error_counts[term] >= 2:
            trigger_error = True

    if phase and phase not in phases_seen:
        phases_seen.add(phase)
        trigger_phase = True

    meta["correct_streak"] = correct_streak
    meta["error_counts"] = error_counts
    meta["phases_seen"] = list(phases_seen)
    return meta, trigger_error, trigger_phase

# Simple progression map for guided packs
PACK_PROGRESS = {
    "it_a1_mission_airport_v2": "it_a2_mission_airport_glue_v1",
    "it_a2_mission_airport_glue_v1": "it_b1_mission_airport_pressure_v1",
    "it_a1_mission_hotel_v1": "it_a2_mission_hotel_glue_v1",
    "it_a2_mission_hotel_glue_v1": "it_b1_mission_hotel_pressure_v1",
}


def h(text: str) -> str:
    return escape(text or "")


def _role_for_pack(pack_id: str) -> str:
    pid = (pack_id or "").lower()
    if "airport" in pid:
        return "Staff"
    if "hotel" in pid:
        return "Reception"
    return "Staff"


async def _start_phrase_mission(user, msg, meta: dict):
    chunk_items = (meta or {}).get("chunk_items") or []
    if not chunk_items:
        return

    persona = get_user_persona(user.id) or (None, None, None)
    p_name, p_city, p_role = persona
    if p_name or p_city or p_role:
        meta = meta or {}
        meta["persona"] = {"name": p_name, "city": p_city, "role": p_role}

    pack_id = (meta or {}).get("pack_id") or ""
    chunk_terms = [ci.get("phrase") or "" for ci in chunk_items]
    learned_terms = list(get_learned_terms_for_pack(user.id, pack_id))
    scenario = pick_scenario_for_pack(user.id, pack_id, chunk_terms + learned_terms)
    pack_info = get_pack_info(pack_id) if pack_id else None
    pack_level = pack_info[1] if pack_info and len(pack_info) > 1 else None
    if scenario:
        turns = scenario.get("turns") or []
        meta["scene"] = {
            "pack_id": pack_id,
            "scene_id": scenario.get("scenario_id"),
            "intro_lines": (scenario.get("intro_lines") or []),
            "goal": scenario.get("goal"),
            "roleplay": {
                "setting": scenario.get("location") or "Mission",
                "bot_role": scenario.get("role_ai") or _role_for_pack(pack_id),
                "turns": turns,
            },
            "turns": turns,
            "idx": 0
        }
    else:
        # Fallback to a minimal generic mission if no scenario matches
        turns = []
        for i, ci in enumerate(chunk_items):
            phrase = ci.get("phrase") or ""
            prompt = "Say this naturally."
            turns.append({"bot": "Buongiorno. In cosa posso aiutarla?"})
            turns.append({"user_task": prompt, "expected_phrase": phrase})

        meta["scene"] = {
            "pack_id": pack_id,
            "scene_id": f"chunk_{user.id}",
            "intro_lines": ["🎭 Mission", "Short practice round."],
            "roleplay": {
                "setting": "Real-life mission",
                "bot_role": _role_for_pack(pack_id),
                "turns": turns,
            },
            "turns": turns,
            "idx": 0
        }
    meta["chunk_items"] = []

    set_session(user.id, mode="learn", item_id=meta.get("item_id"), stage="scene_turn", meta=meta)
    await send_scene_prompt(msg, meta)


async def _send_next_learn_card(user, msg, target: str, pack_id: str | None, meta: dict | None = None) -> bool:
    meta_in = meta or {}
    if pack_id:
        item = pick_next_new_item_for_user_in_pack(user.id, pack_id)
    else:
        item = pick_next_new_item_for_user(user.id, target_language=target)

    if not item:
        if pack_id:
            total, introduced = get_pack_item_counts(user.id, pack_id)
            next_pack = PACK_PROGRESS.get(pack_id)
            kb = None
            journey_path = meta_in.get("journey_path") if meta_in else None
            journey_index = int(meta_in.get("journey_index", 0)) if meta_in else 0
            if journey_path and journey_index + 1 < len(journey_path):
                next_pack = journey_path[journey_index + 1]

            if next_pack:
                next_info = get_pack_info(next_pack)
                if next_info:
                    _, next_level, next_title, _, _, _, _, _ = next_info
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"🔓 Unlock {next_title}", callback_data=f"UNLOCKNEXT|{pack_id}|{next_pack}")],
                        [InlineKeyboardButton("⬅️ Back to Packs", callback_data="SETTINGS|PACKS")],
                    ])
                    await msg.reply_text(
                        f"✅ You finished all NEW items in this pack.\n"
                        f"Progress: {introduced}/{total}\n\n"
                        f"Next recommended pack: <b>{h(next_title)}</b> (level {h(next_level or '-')}).",
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb
                    )
                    clear_session(user.id)
                    return False

            await msg.reply_text(
                f"✅ You finished all NEW items in this pack.\n"
                f"Progress: {introduced}/{total}\n\n"
                f"Now go /review 🔁",
                reply_markup=kb
            )
        else:
            total = get_active_items_total(user.id, target)
            introduced = get_active_items_introduced(user.id, target)
            await msg.reply_text(
                f"✅ You finished all NEW items in your packs.\n"
                f"Progress: {introduced}/{total}\n\n"
                f"Now go /review 🔁"
            )
        clear_session(user.id)
        return False

    # Support older tuple shapes
    if len(item) >= 7:
        item_id, term, chunk, translation_en, note, pack_id_row, focus = item[:7]
    else:
        item_id, term, chunk, translation_en, note = item[:5]
        pack_id_row = None
        focus = None

    if not pack_id and pack_id_row:
        pack_id = pack_id_row

    ctx_it = get_random_context_for_item(item_id)
    holo = get_item_holographic_meta(item_id)

    try:
        get_or_fetch_lexicon_it(term)
    except Exception:
        pass

    ensure_review_row(user.id, item_id)

    lexicon = get_lexicon_cache_it(term)
    if pack_id:
        total, introduced = get_pack_item_counts(user.id, pack_id)
        upsert_user_pack_progress(user.id, pack_id, introduced, total)
    if pack_id:
        distractors = get_random_meanings_from_pack(pack_id, item_id, limit=2)
    else:
        distractors = get_random_meanings_from_active_packs(user.id, target, item_id, limit=2)

    quiz = await generate_reverse_context_quiz(
        term=term,
        chunk=chunk,
        translation_en=translation_en,
        lexicon=lexicon,
        context_it=ctx_it,
        distractors_en=distractors,
    )

    pack_info = get_pack_info(pack_id) if pack_id else None
    if pack_info and len(pack_info) > 4 and pack_info[4]:
        pack_type = pack_info[4]
    elif focus:
        pack_type = "phrase" if focus == "phrase" else "word"
    else:
        pack_type = "word"
    chunk_size = (pack_info[5] if pack_info else None) or (5 if pack_type == "phrase" else None)

    chunk_items = meta_in.get("chunk_items") or []
    prev_pack = meta_in.get("pack_id")
    if prev_pack and pack_id and prev_pack != pack_id:
        chunk_items = []

    meta = {
        "term": term,
        "chunk": chunk,
        "translation_en": translation_en,
        "quiz": quiz,
        "holo": holo,
        "pack_id": pack_id,
        "pack_type": pack_type,
        "chunk_size": chunk_size,
        "chunk_items": chunk_items,
        "item_id": item_id,
    }

    # carry journey info if provided
    if "journey_path" in meta_in:
        meta["journey_path"] = meta_in.get("journey_path")
        meta["journey_index"] = meta_in.get("journey_index", 0)

    if not quiz.get("ok"):
        meta["pending_ai"] = {
            "kind": "quiz",
            "term": term,
            "chunk": chunk,
            "translation_en": translation_en,
            "context_it": ctx_it,
        }
        set_session(user.id, mode="learn", item_id=item_id, stage="await_ai_choice", meta=meta)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Try again", callback_data="AI|RETRY_QUIZ")],
            [InlineKeyboardButton("⏭ Skip quiz", callback_data="AI|SKIP_QUIZ")]
        ])
        await msg.reply_text(
            "⚠️ <b>AI quiz not available</b>\n"
            "Do you want to try again, or skip the quiz?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return True

    if pack_id:
        total, introduced = get_pack_item_counts(user.id, pack_id)
        progress_line = f"📦 Progress: {introduced}/{total}"
    else:
        total = get_active_items_total(user.id, target)
        introduced = get_active_items_introduced(user.id, target)
        progress_line = f"📦 Progress: {introduced}/{total}"

    set_session(user.id, mode="learn", item_id=item_id, stage="await_guess", meta=meta)
    text, keyboard = _build_quiz_message(term, quiz, progress_line)
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return True

def _build_quiz_message(term: str, quiz: dict, progress_line: str | None = None):
    opts = quiz.get("options_en", ["A", "B", "C"])
    keyboard = [
        [InlineKeyboardButton(f"A) {opts[0]}", callback_data="GUESS|0")],
        [InlineKeyboardButton(f"B) {opts[1]}", callback_data="GUESS|1")],
        [InlineKeyboardButton(f"C) {opts[2]}", callback_data="GUESS|2")],
        [InlineKeyboardButton("🔊 Pronounce", callback_data="PRON|word")],
        [InlineKeyboardButton("✅ I know it (skip)", callback_data="LEARN|SKIP")],
    ]

    text = (
        f"{progress_line + '\n\n' if progress_line else ''}"
        f"🧠 What does this mean?\n\n"
        f"<b>{h(term)}</b>"
    )
    return text, InlineKeyboardMarkup(keyboard)

async def offer_scene(msg, user_id: int, item_id: int, meta: dict):
    """
    Save a pending scene in session and ask user to Start/Skip.
    """
    scene = pick_one_scene_for_user_active_packs(user_id)
    if not scene:
        await msg.reply_text("🎭 No scenes found in your packs yet.")
        return

    roleplay = scene.get("roleplay") or {}
    turns = roleplay.get("turns") or []
    if not turns:
        await msg.reply_text("🎭 Scene found but it's empty (no turns).")
        return

    meta = meta or {}
    meta["pending_scene"] = {
        "pack_id": scene.get("pack_id"),
        "scene_id": scene.get("scene_id"),
        "roleplay": roleplay,
        "turns": turns,
        "idx": 0
    }

    # Set session to await scene decision
    set_session(user_id, mode="learn", item_id=item_id, stage="await_scene_choice", meta=meta)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 Start Scene", callback_data="SCENE|START")],
        [InlineKeyboardButton("⏭ Skip for now", callback_data="SCENE|SKIP")]
    ])

    await msg.reply_text(
        f"🎭 <b>Mission Time</b>\n"
        f"You learned <b>{SCENE_EVERY_N_NEW_ITEMS}</b> cards.\n"
        f"Ready for a short scene?",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


async def send_scene_prompt(msg, meta: dict):
    scene = (meta or {}).get("scene") or {}
    roleplay = scene.get("roleplay") or {}
    turns = scene.get("turns") or []
    idx = int(scene.get("idx", 0))

    persona = (meta or {}).get("persona") or {}
    persona_name = persona.get("name") if isinstance(persona, dict) else None
    persona_city = persona.get("city") if isinstance(persona, dict) else None
    persona_role = persona.get("role") if isinstance(persona, dict) else None

    setting = roleplay.get("setting", "Scene")
    bot_role = roleplay.get("bot_role", "Bot")

    # Walk forward until we find the next bot line or user_task
    out = []
    intro_lines = scene.get("intro_lines") or []
    if intro_lines and not scene.get("intro_shown"):
        out.extend(intro_lines)
        scene["intro_shown"] = True

    out.append(f"🎭 <b>{h(setting)}</b>")
    if persona_name or persona_city:
        who = f"{persona_name or 'You'}"
        where = f" ({persona_city})" if persona_city else ""
        out.append(f"👤 <b>You</b>: {h(who + where)}")
    out.append(f"🧑‍💼 <b>NPC</b>: {h(bot_role)}")

    # Append any bot messages until first user_task
    addressed = bool(scene.get("persona_addressed"))
    user_task_found = False
    expected_phrase = None
    while idx < len(turns):
        t = turns[idx]
        if "bot" in t:
            bot_line = t["bot"]
            if persona_name and not addressed:
                bot_line = f"{persona_name}! {bot_line}"
                addressed = True
                scene["persona_addressed"] = True
            out.append(f"🗣 <b>{h(bot_role)}</b>: {h(bot_line)}")
            idx += 1
            continue
        if "user_task" in t:
            turn_label = f"{persona_name}, your turn" if persona_name else "Your turn"
            out.append(f"\n🗣 <b>{h(turn_label)}</b>: {h(t['user_task'])}")
            user_task_found = True
            expected_phrase = t.get("expected_phrase")
            break
        idx += 1

    scene = (meta or {}).get("scene") or {}
    scene["idx"] = idx
    meta["scene"] = scene

    kb = None
    if user_task_found:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Hint", callback_data="SCENEACT|HINT"),
             InlineKeyboardButton("🧩 2 options", callback_data="SCENEACT|OPTIONS")],
            [InlineKeyboardButton("⏭ Skip", callback_data="SCENEACT|SKIP")],
        ])
    await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML, reply_markup=kb)



async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)

    profile = get_user_profile(user.id)
    if not profile:
        await msg.reply_text("Use /start first.")
        return
    
    target, ui, helper = profile

    langs = get_user_languages(user.id)
    if not langs:
        msg = get_chat_sender(update)
        await msg.reply_text("Use /start first.")
        return

    target_language, ui_language = langs

    session = get_session(user.id)
    if session:
        mode, item_id, stage, meta = session
        if mode == "learn" and item_id is not None and stage in ("await_guess", "await_sentence"):
            if stage == "await_guess":
                quiz = (meta or {}).get("quiz") or {}
                term = (meta or {}).get("term") or ""
                opts = quiz.get("options_en", ["A", "B", "C"])

                keyboard = [
                    [InlineKeyboardButton(f"A) {opts[0]}", callback_data="GUESS|0")],
                    [InlineKeyboardButton(f"B) {opts[1]}", callback_data="GUESS|1")],
                    [InlineKeyboardButton(f"C) {opts[2]}", callback_data="GUESS|2")],
                    [InlineKeyboardButton("🔊 Pronounce", callback_data="PRON|word")],
                    [InlineKeyboardButton("✅ I know it (skip)", callback_data="LEARN|SKIP")],
                ]

                text = (
                    "🧠 What does this mean?\n\n"
                    f"<b>{h(term)}</b>"
                )
                await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
                return

            if stage == "await_sentence":
                term = (meta or {}).get("term") or ""
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ I know it (skip)", callback_data="LEARN|SKIP")]
                ])
                is_phrase = len((term or "").split()) > 1
                if is_phrase:
                    anchors = build_anchors(term or "")
                    hint = ", ".join(anchors[:4]) if anchors else ""
                    extra = f"\nKey parts: <b>{h(hint)}</b>" if hint else ""
                    prompt = (
                        "✍️ Finish your current card first.\n\n"
                        f"Write one Italian sentence using the key parts of: <b>{h(term)}</b>."
                        f"{extra}"
                    )
                else:
                    prompt = (
                        "✍️ Finish your current card first.\n\n"
                        f"Write one Italian sentence using <b>{h(term)}</b>."
                    )
                await msg.reply_text(
                    prompt,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                return

    active_packs = get_user_active_packs(user.id)
    if not active_packs:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings → Packs", callback_data="HOME|SETTINGS")]
        ])
        await msg.reply_text(
            "You haven’t started any packs yet.\n\nGo to 📦 Packs and start one, or use /journey.",
            reply_markup=kb
        )
        return
    await _send_next_learn_card(user, msg, target, pack_id=None, meta=None)





async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()
    msg = get_chat_sender(update)

    session = get_session(user.id)
    if not session:
        return
    
    mode, item_id, stage, meta = session

    # --- Scene handler ---
    if mode == "learn" and stage == "scene_turn":
        await handle_scene_reply(update, context, item_id, meta)
        return


    if not (mode == "learn" and stage == "await_sentence" and item_id is not None):
        return

    # 1) Load item (fallback source)
    item = get_item_by_id(item_id)
    if not item:
        clear_session(user.id)
        msg = get_chat_sender(update)
        await msg.reply_text("Session error. Try /learn again.")
        return

    _, term_db, chunk_db, translation_en_db, note, _, focus_db = item

    # 2) Meta (preferred source)
    meta = meta or {}
    term = meta.get("term") or term_db
    chunk = meta.get("chunk") or chunk_db
    translation_en = meta.get("translation_en") or translation_en_db

    # 3) Cached lexicon facts (silent grounding)
    lexicon = get_lexicon_cache_it(term)

    # Optional debug only
    debug_line = ""
    if SHOW_DICT_DEBUG:
        try:
            validation = validate_it_term(term)
            if not validation.get("ok"):
                debug_line = (
                    f"\n🛠 dict check failed for '{term}', "
                    f"suggestion: {validation.get('suggestion')}\n"
                )
        except Exception:
            pass

    # 1) Too short
    if len(text) < 3:
        await msg.reply_text("⚠️ Write a full sentence (not just one word). Try again 🙂")
        return

    # 2) Must contain at least one letter
    if not any(ch.isalpha() for ch in text):
        await msg.reply_text("⚠️ Please write a sentence with letters 🙂")
        return

    # 3) Must include the target word (word packs only)
    if (focus_db or "").lower() != "phrase":
        target_phrase = (term or "").strip()
        ok, meta_val = validate_sentence(text, target_phrase, min_hits=1)
        if not ok:
            await msg.reply_text(
                f"⚠️ Your sentence must include the word <b>{h(term)}</b>.\nTry again 🙂",
                parse_mode=ParseMode.HTML
            )
            return

    # 4) AI feedback
    try:
        ai = await generate_learn_feedback(
            target_language="it",
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            user_sentence=text,
            lexicon=lexicon,
        )
    except Exception:
        # Save what we need to retry
        meta = meta or {}
        meta["pending_ai"] = {
            "kind": "learn_feedback",
            "term": term,
            "chunk": chunk,
            "translation_en": translation_en,
            "user_sentence": text
        }
        set_session(user.id, mode="learn", item_id=item_id, stage="await_ai_choice", meta=meta)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Try again", callback_data="AI|RETRY_LEARN")],
            [InlineKeyboardButton("⏭ Skip AI feedback", callback_data="AI|SKIP_LEARN")]
        ])

        await msg.reply_text(
            "⚠️ <b>AI is not available right now.</b>\n"
            "Do you want to try again, or skip feedback and continue?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return

    # ✅ If AI returned fallback, offer Retry/Skip
    if not ai.get("ok"):
        meta = meta or {}
        meta["pending_ai"] = {
            "kind": "learn_feedback",
            "term": term,
            "chunk": chunk,
            "translation_en": translation_en,
            "user_sentence": text,
        }
        set_session(user.id, mode="learn", item_id=item_id, stage="await_ai_choice", meta=meta)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Try again", callback_data="AI|RETRY_LEARN")],
            [InlineKeyboardButton("⏭ Skip feedback", callback_data="AI|SKIP_LEARN")]
        ])

        reason = ai.get("notes") or "AI not available."
        await msg.reply_text(
            f"⚠️ <b>AI not available</b>\n{h(reason)}\n\nWhat do you want to do?",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return

    reply = (
        f"✅ <b>{h(term)}</b>\n"
        f"“{h(text)}”\n"
        f"{h(debug_line)}"
    )

    if ai.get("correction"):
        reply += f"\n⚠️ Fix: {h(ai['correction'])}"
    elif ai.get("rewrite"):
        reply += f"\n👍 Better: {h(ai['rewrite'])}"
    elif ai.get("notes"):
        reply += f"\n✅ {h(ai['notes'])}"
    else:
        reply += f"\n✅ Good."

    reply += "\n\nNext: /learn or /review."

    msg = get_chat_sender(update)
    await msg.reply_text(reply, parse_mode=ParseMode.HTML)
    
    # ✅ persistent counter (survives clear_session)
    count = get_learn_since_scene(user.id) + 1
    set_learn_since_scene(user.id, count)

    meta = _increment_continue_used(meta or {})
    if _continue_quota_reached(meta):
        clear_session(user.id)
        await msg.reply_text(
            "✅ Continue complete. Back to Journey.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Continue", callback_data="home:journey")]
            ])
        )
        return

    # If it's time, offer scene (do NOT auto-start)
    if count >= SCENE_EVERY_N_NEW_ITEMS:
        set_learn_since_scene(user.id, 0)
        await offer_scene(msg, user.id, item_id, meta)
        return

    clear_session(user.id)


async def on_scene_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("Session expired. Type /learn again.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn" or stage != "await_scene_choice":
        return

    data = query.data  # SCENE|START or SCENE|SKIP
    _, action = data.split("|", 1)

    if action == "SKIP":
        clear_session(user.id)
        await query.edit_message_text(
            "⏭ Skipped. No worries.\nType /learn to continue or /review to practice.",
            parse_mode=ParseMode.HTML
        )
        return

    # START
    pending = (meta or {}).get("pending_scene")
    if not pending:
        clear_session(user.id)
        await query.edit_message_text("No pending scene found. Type /learn again.")
        return

    meta["scene"] = pending
    meta.pop("pending_scene", None)

    set_session(user.id, mode="learn", item_id=item_id, stage="scene_turn", meta=meta)

    # Replace the offer message with “starting…”
    await query.edit_message_text("🎭 Starting scene…", parse_mode=ParseMode.HTML)

    # Send the actual first prompt
    msg = get_chat_sender(update)
    await send_scene_prompt(msg, meta)


async def on_scene_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = (query.data or "").split("|", 1)[1] if "|" in (query.data or "") else ""

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("No active scene.")
        return
    mode, item_id, stage, meta = session
    if mode != "learn" or stage != "scene_turn":
        await query.edit_message_text("No active scene.")
        return

    scene = (meta or {}).get("scene") or {}
    roleplay = scene.get("roleplay") or {}
    turns = scene.get("turns") or []
    idx = int(scene.get("idx", 0))

    expected = None
    if idx < len(turns) and "user_task" in turns[idx]:
        expected = turns[idx].get("expected_phrase")

    if action == "HINT":
        if expected:
            await query.message.reply_text(f"💡 Hint: <b>{h(expected)}</b>", parse_mode=ParseMode.HTML)
        else:
            await query.message.reply_text("💡 Hint: Try a simple question.")
        return
    if action == "OPTIONS":
        opt_a = expected or "Dov'è il gate?"
        opt_b = "Mi scusi, può aiutarmi?"
        await query.message.reply_text(f"🧩 Options:\nA) {h(opt_a)}\nB) {h(opt_b)}", parse_mode=ParseMode.HTML)
        return
    if action == "SKIP":
        # Advance scene without validation
        out = ["⏭ Skipped."]
        # Advance idx past the current user_task
        while idx < len(turns) and "user_task" not in turns[idx]:
            idx += 1
        if idx < len(turns) and "user_task" in turns[idx]:
            idx += 1

        # Append next bot lines and next user task
        while idx < len(turns):
            t = turns[idx]
            if "bot" in t:
                out.append(f"\n🗣 <b>{h(roleplay.get('bot_role', 'Bot'))}</b>: {h(t['bot'])}")
                idx += 1
                continue
            if "user_task" in t:
                out.append(f"\n✅ <b>Your turn</b>: {h(t['user_task'])}")
                break
            idx += 1

        if idx >= len(turns):
            out.append("\n🏁 <b>Scene complete.</b>")
            scene_id = scene.get("scene_id")
            if scene_id:
                mark_scenario_completed(user.id, scene_id)
            clear_session(user.id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Try again", callback_data=f"SCENEREPLAY|{scene.get('pack_id') or ''}")],
                [InlineKeyboardButton("▶️ Continue", callback_data="home:journey")],
            ])
            await query.message.reply_text("\n".join(out), parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        scene["idx"] = idx
        meta["scene"] = scene
        set_session(user.id, mode="learn", item_id=item_id, stage="scene_turn", meta=meta)
        await query.message.reply_text("\n".join(out), parse_mode=ParseMode.HTML)


async def start_pack_scene(update: Update, context: ContextTypes.DEFAULT_TYPE, pack_id: str):
    user = update.effective_user
    msg = get_chat_sender(update)

    pack_key = "generic"
    pk = (pack_id or "").lower()
    if "airport" in pk and "a1" in pk:
        pack_key = "airport_a1"
    elif "airport" in pk and "a2" in pk:
        pack_key = "airport_a2"
    elif "airport" in pk and "b1" in pk:
        pack_key = "airport_b1"
    elif "hotel" in pk and "a1" in pk:
        pack_key = "hotel_a1"
    elif "hotel" in pk and "a2" in pk:
        pack_key = "hotel_a2"
    elif "hotel" in pk and "b1" in pk:
        pack_key = "hotel_b1"

    scenarios = list_scenarios_by_pack_key(pack_key)
    if not scenarios:
        await msg.reply_text("No scenes found for this pack yet.")
        return
    scenario = scenarios[0]

    persona = get_user_persona(user.id) or (None, None, None)
    p_name, p_city, p_role = persona
    meta = {
        "persona": {"name": p_name, "city": p_city, "role": p_role},
        "scene": {
            "pack_id": pack_id,
            "scene_id": scenario.get("scenario_id"),
            "intro_lines": scenario.get("intro_lines") or [],
            "roleplay": scenario.get("roleplay") or {},
            "turns": (scenario.get("roleplay") or {}).get("turns") or [],
            "idx": 0,
        }
    }
    set_session(user.id, mode="learn", item_id=None, stage="scene_turn", meta=meta)
    await send_scene_prompt(msg, meta)


async def on_scene_replay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    pack_id = (query.data or "").split("|", 1)[1] if "|" in (query.data or "") else ""
    if not pack_id:
        await query.edit_message_text("No pack found.")
        return
    await query.edit_message_text("🔁 Restarting scene…")
    await start_pack_scene(update, context, pack_id)


async def on_ai_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("Session expired. Type /learn again.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn" or stage != "await_ai_choice":
        return

    data = query.data  # AI|RETRY_LEARN or AI|SKIP_LEARN
    _, action = data.split("|", 1)

    pending = (meta or {}).get("pending_ai") or {}
    if pending.get("kind") == "quiz":
        if action == "SKIP_QUIZ":
            quiz = (meta or {}).get("quiz") or {
                "context_it": f"Uso comune: {pending.get('term') or ''}.",
                "meaning_en": pending.get("translation_en") or "(meaning not available)",
                "options_en": [pending.get("translation_en") or "Meaning", "Other", "Other"],
                "correct_index": 0,
                "clue": "Fallback (AI off).",
            }

            meta = meta or {}
            meta["quiz"] = quiz
            set_session(user.id, mode="learn", item_id=item_id, stage="await_guess", meta=meta)

            profile = get_user_profile(user.id)
            if profile:
                target_lang = profile[0]
                total = get_active_items_total(user.id, target_lang)
                introduced = get_active_items_introduced(user.id, target_lang)
                progress_line = f"📦 Progress: {introduced}/{total}"
            else:
                progress_line = None

            text, keyboard = _build_quiz_message(pending.get("term") or "", quiz, progress_line)
        try:
            await query.edit_message_text("⏭ Skipping AI quiz. Here’s the fallback quiz.", parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        msg = get_chat_sender(update)
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

        # RETRY_QUIZ
        term = pending.get("term") or ""
        chunk = pending.get("chunk")
        translation_en = pending.get("translation_en")
        context_it = pending.get("context_it")

        lexicon = get_lexicon_cache_it(term)
        quiz = await generate_reverse_context_quiz(
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            lexicon=lexicon,
            context_it=context_it,
        )

        meta = meta or {}
        meta["quiz"] = quiz
        set_session(user.id, mode="learn", item_id=item_id, stage="await_guess", meta=meta)

        profile = get_user_profile(user.id)
        if profile:
            target_lang = profile[0]
            total = get_active_items_total(user.id, target_lang)
            introduced = get_active_items_introduced(user.id, target_lang)
            progress_line = f"📦 Progress: {introduced}/{total}"
        else:
            progress_line = None

        text, keyboard = _build_quiz_message(term, quiz, progress_line)
        try:
            await query.edit_message_text("✅ Quiz ready. Here you go:", parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        msg = get_chat_sender(update)
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        return

    if pending.get("kind") != "learn_feedback":
        clear_session(user.id)
        await query.edit_message_text("Nothing to retry. Type /learn again.")
        return

    if action == "SKIP_LEARN":
        await query.edit_message_text(
            "⏭ Skipped AI feedback.\nType /learn to continue or /review to practice.",
            parse_mode=ParseMode.HTML
        )
        clear_session(user.id)
        return

    term = pending.get("term")
    chunk = pending.get("chunk")
    translation_en = pending.get("translation_en")
    user_sentence = pending.get("user_sentence")

    lexicon = get_lexicon_cache_it(term)

    try:
        ai = await generate_learn_feedback(
            target_language="it",
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            user_sentence=user_sentence,
            lexicon=lexicon,
        )
    except Exception:
        await query.edit_message_text(
            "⚠️ AI still not available.\nYou can /learn without feedback or try later.",
            parse_mode=ParseMode.HTML
        )
        clear_session(user.id)
        return

    if not ai.get("ok"):
        meta = meta or {}
        meta["pending_ai"] = {
            "kind": "learn_feedback",
            "term": term,
            "chunk": chunk,
            "translation_en": translation_en,
            "user_sentence": user_sentence,
        }
        set_session(user.id, mode="learn", item_id=item_id, stage="await_ai_choice", meta=meta)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Try again", callback_data="AI|RETRY_LEARN")],
            [InlineKeyboardButton("⏭ Skip feedback", callback_data="AI|SKIP_LEARN")]
        ])

        reason = ai.get("notes") or "AI not available."
        try:
            await query.edit_message_text(
                f"⚠️ <b>AI not available</b>\n{h(reason)}\n\nWhat do you want to do?",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    reply = (
        f"✅ <b>{h(term)}</b>\n"
        f"“{h(user_sentence)}”\n"
    )
    if ai.get("correction"):
        reply += f"\n⚠️ Fix: {h(ai['correction'])}"
    elif ai.get("rewrite"):
        reply += f"\n👍 Better: {h(ai['rewrite'])}"
    elif ai.get("notes"):
        reply += f"\n✅ {h(ai['notes'])}"
    else:
        reply += "\n✅ Good."

    reply += "\n\nNext: /learn or /review."

    try:
        await query.edit_message_text("✅ AI is back. Sending feedback…", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
    msg = get_chat_sender(update)
    await msg.reply_text(reply, parse_mode=ParseMode.HTML)

    clear_session(user.id)
    



async def on_guess_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data  # "GUESS|1"
    _, idx_str = data.split("|", 1)
    picked = int(idx_str)

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("Session expired. Type /learn again.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn" or stage != "await_guess":
        return

    quiz = (meta or {}).get("quiz") or {}
    correct = quiz.get("correct_index", 0)
    meaning = quiz.get("meaning_en", meta.get("translation_en") or "-")

    ok = (picked == correct)
    status = "🟢 Correct" if ok else "⚠️ Almost"
    record_practice(user.id, "learn", ok)

    holo = (meta or {}).get("holo") or {}
    drills = holo.get("drills") or {}
    scenario = drills.get("scenario_prompt") if isinstance(drills, dict) else None

    term = (meta or {}).get("term") or ""
    pack_type = (meta or {}).get("pack_type") or "word"
    pack_id = (meta or {}).get("pack_id")
    chunk_size = (meta or {}).get("chunk_size") or 5
    phase = None
    if isinstance(holo, dict):
        phase = (holo.get("phase") or (meta or {}).get("phase"))

    lines = []
    if ok:
        lines.append(f"✔️ {h(meaning)}")
    else:
        lines.append("⚠️ Almost.")
        lines.append(f"✔️ {h(meaning)}")

    if pack_type == "phrase":
        meta, trigger_error, trigger_phase = _update_progress_meta(meta or {}, term, ok, phase)
        # record chunk item
        chunk_items = (meta or {}).get("chunk_items") or []
        if not any(ci.get("item_id") == item_id for ci in chunk_items):
            chunk_items.append({
                "item_id": item_id,
                "phrase": term,
                "scenario": scenario,
            })
        meta["chunk_items"] = chunk_items
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)

        # scenario trigger system (readiness + streak/error/time/phase)
        msg = get_chat_sender(update)
        now_ts = int(time.time())
        last_ts = int((meta or {}).get("last_scenario_ts") or 0)
        time_trigger = (now_ts - last_ts) >= 240

        pack_info = get_pack_info(pack_id) if pack_id else None
        level = pack_info[1] if pack_info and len(pack_info) > 1 else "A1"
        max_per_session = _max_scenarios_for_level(level)
        scenarios_done = int((meta or {}).get("scenarios_done") or 0)

        correct_streak = int((meta or {}).get("correct_streak") or 0)
        streak_trigger = correct_streak >= 3

        chunk_terms = [ci.get("phrase") or "" for ci in chunk_items]
        learned_terms = list(get_learned_terms_for_pack(user.id, pack_id or ""))
        scenario_obj = pick_scenario_for_pack(user.id, pack_id or "", chunk_terms + learned_terms)

        should_trigger = False
        if scenario_obj and scenarios_done < max_per_session:
            if streak_trigger or trigger_error or time_trigger or trigger_phase:
                should_trigger = True

        if should_trigger:
            meta["last_scenario_ts"] = now_ts
            meta["scenarios_done"] = scenarios_done + 1
            await msg.reply_text("🎭 Mission starting…", parse_mode=ParseMode.HTML)
            await _start_phrase_mission(user, msg, meta)
            return

        # otherwise continue to next card in this pack
        meta = _increment_continue_used(meta or {})
        if _continue_quota_reached(meta):
            clear_session(user.id)
            await msg.reply_text(
                "✅ Continue complete. Back to Journey.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Continue", callback_data="home:journey")]
                ])
            )
            return
        profile = get_user_profile(user.id)
        target = profile[0] if profile else "it"
        msg = get_chat_sender(update)
        await _send_next_learn_card(user, msg, target, pack_id=pack_id, meta=meta)
        return

    # word packs: move to sentence stage
    set_session(user.id, mode="learn", item_id=item_id, stage="await_sentence", meta=meta)

    # Keep feedback minimal for word packs too
    lines.append(
        f"\n🗣 Use it in a sentence:\n"
        f"<b>{h(term)}</b>"
    )

    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML)




async def on_pronounce_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = get_session(query.from_user.id)
    if not session:
        return

    mode, item_id, stage, meta = session
    if mode != "learn":
        return

    term = (meta or {}).get("term")
    if not term:
        return

    say_text = term.strip()


    try:
        path = await tts_it(say_text)

        # Decide how to send based on extension
        suffix = path.suffix.lower()

        with open(path, "rb") as f:
            if suffix == ".ogg":
                await query.message.reply_voice(
                    voice=InputFile(f, filename=f"{say_text}.ogg"),
                    caption=f"🔊 {say_text}",
                )
            else:
                # mp3/wav -> send as audio
                await query.message.reply_audio(
                    audio=InputFile(f, filename=f"{say_text}{suffix}"),
                    title=say_text,
                )

    except Exception as e:
        await query.message.reply_text(f"TTS failed: {type(e).__name__}: {e}")


async def start_pack_learn(update: Update, context: ContextTypes.DEFAULT_TYPE, pack_id: str, journey_meta: dict | None = None):
    user = update.effective_user
    msg = get_chat_sender(update)

    profile = get_user_profile(user.id)
    if not profile:
        await msg.reply_text("Use /start first.")
        return

    target, ui, helper = profile
    activate_pack(user.id, pack_id)
    total, introduced = get_pack_item_counts(user.id, pack_id)
    upsert_user_pack_progress(user.id, pack_id, introduced, total)

    clear_session(user.id)
    persona = get_user_persona(user.id) or (None, None, None)
    p_name, p_city, p_role = persona
    meta = {
        "pack_id": pack_id,
        "chunk_items": [],
        "persona": {"name": p_name, "city": p_city, "role": p_role},
    }
    if journey_meta:
        meta.update(journey_meta)
        set_user_journey_progress(user.id, pack_id)
    await _send_next_learn_card(user, msg, target, pack_id=pack_id, meta=meta)


async def on_learn_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    session = get_session(user.id)
    if not session:
        await query.edit_message_text("No active learn card. Type /learn.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn" or item_id is None:
        await query.edit_message_text("No active learn card. Type /learn.")
        return

    mark_item_mature(user.id, item_id)
    clear_session(user.id)

    await query.edit_message_text("✅ Skipped. Type /learn for the next item.")


async def on_unlock_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    parts = query.data.split("|")
    if len(parts) < 3:
        return
    _, current_pack, next_pack = parts[0], parts[1], parts[2]

    next_info = get_pack_info(next_pack)
    if not next_info:
        await query.edit_message_text("Next pack not found. Go to /packs.")
        return

    # activate and start
    activate_pack(user.id, next_pack)
    await query.edit_message_text("✅ Unlocked! Starting the next pack…", parse_mode=ParseMode.HTML)
    await start_pack_learn(update, context, next_pack)

async def handle_scene_reply(update, context, item_id: int, meta: dict):
    user = update.effective_user
    msg = get_chat_sender(update)
    user_text = (update.message.text or "").strip()

    scene = (meta or {}).get("scene") or {}
    roleplay = scene.get("roleplay") or {}
    turns = scene.get("turns") or []
    idx = int(scene.get("idx", 0))

    setting = roleplay.get("setting", "")
    bot_role = roleplay.get("bot_role", "Bot")
    expected_phrase = None
    if idx < len(turns):
        expected_phrase = turns[idx].get("expected_phrase")

    # tiny correction (optional but good)
    profile = get_user_profile(user.id)
    ui_lang = profile[1] if profile else "en"
    helper_lang = profile[2] if profile else None
    try:
        fb = await generate_roleplay_feedback(
            target_language="it",
            user_sentence=user_text,
            setting=setting,
            bot_role=bot_role,
            expected_phrase=expected_phrase,
            ui_language=ui_lang,
            helper_language=helper_lang,
        )
    except Exception:
        fb = {}
        await msg.reply_text("⚠️ AI feedback unavailable — continuing scene.", parse_mode=ParseMode.HTML)

    if fb.get("ok") is False and expected_phrase:
        hint = fb.get("notes") or "Try again."
        await msg.reply_text(
            f"⚠️ {h(hint)}\nTry this:\n<b>{h(expected_phrase)}</b>",
            parse_mode=ParseMode.HTML
        )
        return

    if not fb.get("ok"):
        await msg.reply_text("⚠️ AI feedback unavailable — continuing scene.", parse_mode=ParseMode.HTML)

    out = []
    persona = (meta or {}).get("persona") or {}
    persona_name = persona.get("name") if isinstance(persona, dict) else None

    if fb.get("correction"):
        out.append(f"⚠️ Fix: {h(fb['correction'])}")
    elif fb.get("rewrite"):
        out.append(f"👍 Better: {h(fb['rewrite'])}")
    else:
        out.append("✅ Good.")

    # Advance idx past the user_task we just answered
    while idx < len(turns) and "user_task" not in turns[idx]:
        idx += 1
    if idx < len(turns) and "user_task" in turns[idx]:
        idx += 1

    # Add next bot lines and next user task
    while idx < len(turns):
        t = turns[idx]
        if "bot" in t:
            out.append(f"\n🗣 <b>{h(bot_role)}</b>: {h(t['bot'])}")
            idx += 1
            continue
        if "user_task" in t:
            turn_label = f"{persona_name}, your turn" if persona_name else "Your turn"
            out.append(f"\n✅ <b>{h(turn_label)}</b>: {h(t['user_task'])}")
            break
        idx += 1

    # Scene finished
    if idx >= len(turns):
        out.append("\n🏁 <b>Scene complete.</b>")
        scene_id = scene.get("scene_id")
        if scene_id:
            mark_scenario_completed(user.id, scene_id)
        advance_story(user.id, pack_level)
        clear_session(user.id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Try again", callback_data=f"SCENEREPLAY|{scene.get('pack_id') or ''}")],
            [InlineKeyboardButton("▶️ Continue", callback_data="home:journey")],
        ])
        await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # Save updated index
    scene["idx"] = idx
    meta["scene"] = scene
    set_session(user.id, mode="learn", item_id=item_id, stage="scene_turn", meta=meta)

    await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML)
