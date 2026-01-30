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
    get_active_items_total,
    get_active_items_introduced,get_user_profile,
    get_random_context_for_item, get_item_holographic_meta,
    get_learn_since_scene,
    set_learn_since_scene,
    pick_one_scene_for_user_active_packs,

)

from bot.services.dictionary_it import validate_it_term
from bot.services.ai_feedback import generate_learn_feedback,generate_reverse_context_quiz,generate_roleplay_feedback
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.tts_edge import tts_it


SCENE_EVERY_N_NEW_ITEMS = 3


def h(text: str) -> str:
    return escape(text or "")

def _build_quiz_message(term: str, quiz: dict, progress_line: str | None = None):
    opts = quiz.get("options_en", ["A", "B", "C"])
    keyboard = [
        [InlineKeyboardButton(f"A) {opts[0]}", callback_data="GUESS|0")],
        [InlineKeyboardButton(f"B) {opts[1]}", callback_data="GUESS|1")],
        [InlineKeyboardButton(f"C) {opts[2]}", callback_data="GUESS|2")],
        [InlineKeyboardButton("🔊 Pronounce", callback_data="PRON|word")],
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
        await msg.reply_text("🎭 No scenes found in your active packs yet.")
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

    active_packs = get_user_active_packs(user.id)
    if not active_packs:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings → Packs", callback_data="HOME|SETTINGS")]
        ])
        await msg.reply_text(
            "You don’t have any active packs yet.\n\nGo to ⚙️ Settings → 📦 Packs and turn at least one ON.",
            reply_markup=kb
        )
        return

    item = pick_next_new_item_for_user(user.id, target_language=target)
    if not item:
        total = get_active_items_total(user.id, target_language)
        introduced = get_active_items_introduced(user.id, target_language)
        await msg.reply_text(
            f"✅ You finished all NEW items in your active packs.\n"
            f"Progress: {introduced}/{total}\n\n"
            f"Now go /review 🔁"
        )
        return

    item_id, term, chunk, translation_en, note = item

    ctx_it = get_random_context_for_item(item_id)
    holo = get_item_holographic_meta(item_id)


    # Prefetch/cache lexicon (silent)
    try:
        get_or_fetch_lexicon_it(term)
    except Exception:
        pass

    ensure_review_row(user.id, item_id)

    lexicon = get_lexicon_cache_it(term)
    quiz = await generate_reverse_context_quiz(
    term=term,
    chunk=chunk,
    translation_en=translation_en,
    lexicon=lexicon,
    context_it=ctx_it,   # ✅ use fixed context if available
    )


    meta = {
        "term": term,
        "chunk": chunk,
        "translation_en": translation_en,
        "quiz": quiz,
        "holo": holo,
    }

    # Progress header
    total = get_active_items_total(user.id, target)
    introduced = get_active_items_introduced(user.id, target)
    progress_line = f"📦 Progress: {introduced}/{total}"

    if not quiz.get("ok"):
        meta = meta or {}
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

        try:
            await msg.reply_text(
                "⚠️ <b>AI quiz not available</b>\n"
                "Do you want to try again, or skip the quiz?",
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    set_session(user.id, mode="learn", item_id=item_id, stage="await_guess", meta=meta)
    text, keyboard = _build_quiz_message(term, quiz, progress_line)
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)





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

    _, term_db, chunk_db, translation_en_db, note = item

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

    # Move to sentence stage
    set_session(user.id, mode="learn", item_id=item_id, stage="await_sentence", meta=meta)

    holo = (meta or {}).get("holo") or {}
    drills = holo.get("drills") or {}
    scenario = drills.get("scenario_prompt") if isinstance(drills, dict) else None

    term = (meta or {}).get("term") or ""

    lines = []
    lines.append(f"{status}")
    lines.append(f"<b>Meaning:</b> {h(meaning)}")

    if clue:
        lines.append(f"<i>Clue:</i> {h(clue)}")

    # --- Deconstruct panel (short + native) ---
    reg = holo.get("register")
    risk = holo.get("risk")
    trap = holo.get("trap")
    culture = holo.get("cultural_note")
    sauce = holo.get("native_sauce")

    if reg:
        lines.append(f"\n🧭 <b>Register</b>: <i>{h(reg)}</i>")

    # show risk only if not safe
    if risk and str(risk).strip().lower() != "safe":
        lines.append(f"⚠️ <b>Risk</b>: {h(risk)}")

    if trap:
        lines.append(f"🪤 <b>Trap</b>: {h(trap)}")

    if culture:
        lines.append(f"🍝 <b>Culture</b>: {h(culture)}")

    if sauce:
        lines.append(f"🧃 <b>Native sauce</b>: {h(sauce)}")

    # Scenario prompt (optional)
    if scenario:
        lines.append(f"\n🎬 <b>Scenario</b>: {h(scenario)}")

    # Production task (always)
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

    # tiny correction (optional but good)
    try:
        fb = await generate_roleplay_feedback(
            target_language="it",
            user_sentence=user_text,
            setting=setting,
            bot_role=bot_role
        )
    except Exception:
        fb = {}
        await msg.reply_text("⚠️ AI feedback unavailable — continuing scene.", parse_mode=ParseMode.HTML)

    if not fb.get("ok"):
        await msg.reply_text("⚠️ AI feedback unavailable — continuing scene.", parse_mode=ParseMode.HTML)

    out = []
    if fb.get("correction"):
        out.append(f"🛠 <b>Correction</b>: {h(fb['correction'])}")
    if fb.get("rewrite"):
        out.append(f"✨ <b>Native</b>: {h(fb['rewrite'])}")
    if fb.get("notes"):
        out.append(f"💡 {h(fb['notes'])}")

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
