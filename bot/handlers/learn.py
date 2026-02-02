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

)

from bot.services.dictionary_it import validate_it_term
from bot.services.ai_feedback import generate_learn_feedback,generate_reverse_context_quiz,generate_roleplay_feedback 
from bot.services.validation import validate_sentence, build_anchors
import random
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.tts_edge import tts_it


SCENE_EVERY_N_NEW_ITEMS = 3

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


def _setting_for_pack(pack_id: str) -> str:
    pid = (pack_id or "").lower()
    if "airport" in pid:
        return "Fiumicino airport, boarding starts in 10 minutes, screens just changed"
    if "hotel" in pid:
        return "Hotel reception at night, booking mix‑up, you’re tired"
    return "Real-life mission"


def _bot_line_for_pack(pack_id: str, idx: int) -> str:
    pid = (pack_id or "").lower()
    if "airport" in pid:
        lines = [
            "Buongiorno. In cosa posso aiutarla?",
            "Mi dica pure.",
            "Un attimo… controllo.",
            "Capisco. Vediamo.",
            "Sì, certo.",
        ]
        return lines[idx % len(lines)]
    if "hotel" in pid:
        lines = [
            "Buonasera. Come posso aiutarla?",
            "Controllo subito la prenotazione.",
            "Mi dica, qual è il problema?",
            "Va bene. Vediamo una soluzione.",
            "Certo, un attimo.",
        ]
        return lines[idx % len(lines)]
    return "Va bene. Mi dica."


async def _start_phrase_mission(user, msg, meta: dict):
    chunk_items = (meta or {}).get("chunk_items") or []
    if not chunk_items:
        return

    pack_id = (meta or {}).get("pack_id") or ""
    pack_info = get_pack_info(pack_id) or ()
    pack_title = pack_info[2] if len(pack_info) > 2 else "Mission"
    setting = _setting_for_pack(pack_id)

    turns = []
    for i, ci in enumerate(chunk_items):
        phrase = ci.get("phrase") or ""
        scenario = ci.get("scenario") or "Use this naturally."
        prompt = (
            f"Scenario: {scenario}\n"
            f"Use the phrase you learned."
        )
        turns.append({"bot": _bot_line_for_pack(pack_id, i)})
        turns.append({"user_task": prompt, "expected_phrase": phrase})

    meta["scene"] = {
        "pack_id": pack_id,
        "scene_id": f"chunk_{user.id}",
        "roleplay": {
            "setting": f"{pack_title} — {setting}",
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
        f"🕵️ <b>Guess the meaning</b>\n\n"
        f"Word: <b>{h(term)}</b>\n\n"
        f"Context:\n<i>{h(quiz.get('context_it',''))}</i>\n\n"
        f"Pick the best meaning:"
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
        f"You learned <b>{SCENE_EVERY_N_NEW_ITEMS}</b> new cards.\n"
        f"Want to practice a short real-life scene now?",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


async def send_scene_prompt(msg, meta: dict):
    scene = (meta or {}).get("scene") or {}
    roleplay = scene.get("roleplay") or {}
    turns = scene.get("turns") or []
    idx = int(scene.get("idx", 0))

    setting = roleplay.get("setting", "Scene")
    bot_role = roleplay.get("bot_role", "Bot")

    # Walk forward until we find the next bot line or user_task
    out = [f"🎭 <b>Mission Scene</b>\n<i>{h(setting)}</i>\n<b>Role:</b> {h(bot_role)}\n"]

    # Append any bot messages until first user_task
    while idx < len(turns):
        t = turns[idx]
        if "bot" in t:
            out.append(f"🗣 <b>{h(bot_role)}</b>: {h(t['bot'])}")
            idx += 1
            continue
        if "user_task" in t:
            out.append(f"\n✅ <b>Your turn</b>: {h(t['user_task'])}")
            break
        idx += 1

    scene = (meta or {}).get("scene") or {}
    scene["idx"] = idx
    meta["scene"] = scene

    msg_text = "\n".join(out) + "\n\n✍️ Reply with your message (type it)."
    await msg.reply_text(msg_text, parse_mode=ParseMode.HTML)



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
                    "🧠 You have an active Learn card.\n\n"
                    f"Word: <b>{h(term)}</b>\n\n"
                    f"Context:\n<i>{h(quiz.get('context_it',''))}</i>\n\n"
                    "Pick the best meaning:"
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

    examples = ai.get("examples") or []
    examples_block = "\n".join([f"• {ex}" for ex in examples if ex]) or "• (no examples)"

    reply = (
        f"✅ <b>Learn — Feedback</b>\n\n"
        f"Word: <b>{h(term)}</b>\n"
        f"Your sentence:\n“{h(text)}”\n"
        f"{h(debug_line)}"
    )

    if ai.get("correction"):
        reply += f"\n🛠 <b>Correction</b>: {h(ai['correction'])}\n"
    if ai.get("rewrite"):
        reply += f"\n✨ <b>Rewrite</b>: {h(ai['rewrite'])}\n"
    why = ai.get("why") or []
    if why:
        reply += "\n🧠 <b>Why</b>:\n" + "\n".join([f"• {h(x)}" for x in why]) + "\n"

    gnotes = ai.get("grammar_notes") or []
    if gnotes:
        lines = []
        for gn in gnotes[:2]:
            issue = h(str(gn.get("issue", "")))
            explain = h(str(gn.get("explain", "")))
            ex = h(str(gn.get("example", "")))
            if issue or explain or ex:
                lines.append(f"• <b>{issue}</b>: {explain}" + (f" <i>({ex})</i>" if ex else ""))
        if lines:
            reply += "\n📚 <b>Grammar</b>:\n" + "\n".join(lines) + "\n"
    if ai.get("notes"):
        reply += f"\n💡 {h(ai['notes'])}\n"

    reply += (
        f"\n📌 <b>Examples</b>:\n{h(examples_block)}\n\n"
        f"Type /review to practice or /learn for another item."
    )

    msg = get_chat_sender(update)
    await msg.reply_text(reply, parse_mode=ParseMode.HTML)
    
    # ✅ persistent counter (survives clear_session)
    count = get_learn_since_scene(user.id) + 1
    set_learn_since_scene(user.id, count)

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

    examples = ai.get("examples") or []
    examples_block = "\n".join([f"• {ex}" for ex in examples if ex]) or "• (no examples)"

    reply = (
        f"✅ <b>Learn — Feedback</b>\n\n"
        f"Word: <b>{h(term)}</b>\n"
        f"Your sentence:\n“{h(user_sentence)}”\n"
    )
    if ai.get("correction"):
        reply += f"\n🛠 <b>Correction</b>: {h(ai['correction'])}\n"
    if ai.get("rewrite"):
        reply += f"\n✨ <b>Rewrite</b>: {h(ai['rewrite'])}\n"
    if ai.get("notes"):
        reply += f"\n💡 {h(ai['notes'])}\n"

    reply += f"\n📌 <b>Examples</b>:\n{h(examples_block)}\n\nType /review or /learn."

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
    clue = quiz.get("clue", "")

    ok = (picked == correct)
    status = "🎯 Correct!" if ok else "😅 Not quite."

    holo = (meta or {}).get("holo") or {}
    drills = holo.get("drills") or {}
    scenario = drills.get("scenario_prompt") if isinstance(drills, dict) else None

    term = (meta or {}).get("term") or ""
    pack_type = (meta or {}).get("pack_type") or "word"
    pack_id = (meta or {}).get("pack_id")
    chunk_size = (meta or {}).get("chunk_size") or 5

    lines = []
    lines.append(f"{status}")
    lines.append(f"<b>Italian:</b> {h(term)}")
    lines.append(f"<b>English:</b> {h(meaning)}")

    # minimal tips
    trap = holo.get("trap")
    culture = holo.get("cultural_note")
    sauce = holo.get("native_sauce")
    tip_lines = []
    if sauce:
        tip_lines.append(f"🧃 {h(sauce)}")
    if culture:
        tip_lines.append(f"🍝 {h(culture)}")
    if trap:
        tip_lines.append(f"🪤 {h(trap)}")
    if tip_lines:
        lines.append("\n<b>Tip</b>: " + " ".join(tip_lines[:1]))

    # Scenario prompt (optional, short)
    if scenario:
        lines.append(f"\n🎬 <b>Scenario</b>: {h(scenario)}")

    if pack_type == "phrase":
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

        # start mission if chunk complete
        if len(chunk_items) >= int(chunk_size or 5):
            msg = get_chat_sender(update)
            await msg.reply_text("🎭 Mission starting…", parse_mode=ParseMode.HTML)
            await _start_phrase_mission(user, msg, meta)
            return

        # otherwise continue to next card in this pack
        profile = get_user_profile(user.id)
        target = profile[0] if profile else "it"
        msg = get_chat_sender(update)
        await _send_next_learn_card(user, msg, target, pack_id=pack_id, meta=meta)
        return

    # word packs: move to sentence stage
    set_session(user.id, mode="learn", item_id=item_id, stage="await_sentence", meta=meta)

    if len((term or "").split()) > 1:
        lines.append(
            f"\n✍️ Now you:\n"
            f"Write <b>one Italian sentence</b> using: <b>{h(term)}</b>.\n"
            f"<i>(Any tense/form is OK. Don’t copy the whole phrase.)</i>"
        )
    else:
        lines.append(
            f"\n✍️ Now you:\n"
            f"Write <b>one Italian sentence</b> using the word <b>{h(term)}</b>.\n"
            f"<i>(Any tense/form is OK. Don’t copy the chunk — just use the word naturally.)</i>"
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

    clear_session(user.id)
    meta = {"pack_id": pack_id, "chunk_items": []}
    if journey_meta:
        meta.update(journey_meta)
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

    if fb.get("ok") is False and fb.get("provider") == "gemini" and expected_phrase:
        hint = fb.get("notes") or "Try again."
        await msg.reply_text(
            f"⚠️ {h(hint)}\nUse this phrase:\n<b>{h(expected_phrase)}</b>",
            parse_mode=ParseMode.HTML
        )
        return

    if not fb.get("ok"):
        await msg.reply_text("⚠️ AI feedback unavailable — continuing scene.", parse_mode=ParseMode.HTML)

    out = []
    if fb.get("ok") and not (fb.get("correction") or fb.get("rewrite") or fb.get("notes")):
        out.append("✅ <b>Acceptable</b>")
    if fb.get("correction"):
        out.append(f"🛠 <b>Correction</b>: {h(fb['correction'])}")
    if fb.get("rewrite"):
        out.append(f"✨ <b>Native</b>: {h(fb['rewrite'])}")
    if fb.get("notes"):
        out.append(f"💡 {h(fb['notes'])}")
    tips = fb.get("tips") or []
    if tips:
        out.append("\n🧠 <b>Tips</b>:\n" + "\n".join([f"• {h(t)}" for t in tips]))
    grammar = fb.get("grammar") or []
    if grammar:
        out.append("\n📚 <b>Grammar</b>:\n" + "\n".join([f"• {h(g)}" for g in grammar]))

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
            out.append(f"\n✅ <b>Your turn</b>: {h(t['user_task'])}")
            break
        idx += 1

    # Scene finished
    if idx >= len(turns):
        out.append("\n🏁 <b>Scene complete.</b> Type /learn to continue or /review to practice.")
        clear_session(user.id)
        await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML)
        return

    # Save updated index
    scene["idx"] = idx
    meta["scene"] = scene
    set_session(user.id, mode="learn", item_id=item_id, stage="scene_turn", meta=meta)

    await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML)
