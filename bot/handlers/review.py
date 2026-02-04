from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape
from bot.db import (
    get_due_item, get_due_item_in_pack, get_item_by_id, set_session, get_session, clear_session,
    apply_grade, undo_last_grade, record_practice, get_pack_item_counts, upsert_user_pack_progress,
    get_due_count, get_due_count_in_pack, get_random_context_for_item, get_review_state, get_random_terms_from_pack,
    get_user_level,
)
from bot.services.ai_feedback import generate_sentence_upgrade, generate_learn_feedback
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.tts_edge import tts_it
from telegram import InputFile
from bot.utils.telegram import get_chat_sender


def h(text: str) -> str:
    return escape(text or "")


async def _send_tts(message, text: str):
    audio_path = await tts_it(text)
    suffix = audio_path.suffix.lower()
    with open(audio_path, "rb") as f:
        if suffix == ".ogg":
            await message.reply_voice(voice=InputFile(f, filename=f"{text}.ogg"))
        else:
            await message.reply_audio(audio=InputFile(f, filename=f"{text}{suffix}"), title=text)


def grade_keyboard(item_id: int, is_phrase: bool):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("0 Hard", callback_data=f"GRADE|0|{item_id}"),
            InlineKeyboardButton("1", callback_data=f"GRADE|1|{item_id}"),
            InlineKeyboardButton("2", callback_data=f"GRADE|2|{item_id}"),
        ],
        [
            InlineKeyboardButton("3", callback_data=f"GRADE|3|{item_id}"),
            InlineKeyboardButton("4", callback_data=f"GRADE|4|{item_id}"),
            InlineKeyboardButton("5 Perfect", callback_data=f"GRADE|5|{item_id}"),
        ]
    ])

def undo_keyboard(item_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Undo last grade", callback_data=f"UNDO|{item_id}")]
    ])

def review_header(title: str, due_count: int) -> str:
    return (
        f"🟣 <b>{title}</b>\n"
        f"⏳ Due now: <b>{due_count}</b>\n"
    )

def review_prompt_word(term: str, index: int | None = None, total: int | None = None) -> str:
    index_line = f"Card {index}/{total}\n" if index and total else ""
    return (
        f"{index_line}"
        "Step 1/2 — Write\n"
        f"🧱 Use the word: <b>{h(term)}</b>\n"
        "Write a short, real sentence (up to 12 words)."
    )

def review_grade_prompt() -> str:
    return (
        "Step 2/2 — Rate yourself\n"
        "0 = hard, 5 = perfect"
    )


def _next_level(level: str) -> str:
    order = ["A1", "A2", "B1", "B2", "C1", "C2"]
    lvl = (level or "A1").upper()
    if lvl not in order:
        return "A2"
    idx = order.index(lvl)
    return order[min(idx + 1, len(order) - 1)]


def review_actions_keyboard(item_id: int, is_phrase: bool) -> InlineKeyboardMarkup:
    if is_phrase:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💡 Hint", callback_data=f"REVIEW|HINT|{item_id}"),
                InlineKeyboardButton("🧩 Options", callback_data=f"REVIEW|OPTIONS|{item_id}"),
            ],
            [
                InlineKeyboardButton("⏭ Skip", callback_data=f"REVIEW|SKIP|{item_id}"),
            ],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💡 Hint", callback_data=f"REVIEW|HINT|{item_id}"),
            InlineKeyboardButton("📝 Example", callback_data=f"REVIEW|EXAMPLE|{item_id}"),
        ],
        [
            InlineKeyboardButton("🎙 Pronounce", callback_data=f"REVIEW|PRON|{item_id}"),
            InlineKeyboardButton("⏭ Skip", callback_data=f"REVIEW|SKIP|{item_id}"),
        ],
    ])



async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session(user.id)
    msg = get_chat_sender(update)
    if session:
        mode, item_id, stage, meta = session
        if mode == "learn":
            await msg.reply_text(
                "You're in a mission. Pause and review now?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Review now", callback_data="REVIEWFLOW|NOW")],
                    [InlineKeyboardButton("▶️ Resume mission", callback_data="REVIEWFLOW|RESUME")],
                ])
            )
            return

    item_id = get_due_item(user.id)

    if not item_id:
        await msg.reply_text("🎉 Nothing due today. Use /journey to add more.")
        return

    item = get_item_by_id(item_id)
    if not item:
        await msg.reply_text("Review error. Try /review again.")
        return

    _, term, chunk, translation_en, note, pack_id, focus = item
    due_count = get_due_count(user.id)
    is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)
    review_state = get_review_state(user.id, item_id)
    status = review_state[0] if review_state else "new"
    mode = "A"
    if is_phrase:
        if due_count >= 20 or status == "new":
            mode = "B"
        elif status == "mature":
            mode = "C"
        else:
            mode = "A"

    set_session(user.id, mode="review", item_id=item_id, stage="await_sentence", meta={"due_total": due_count, "due_index": 1, "mode": mode})

    if is_phrase:
        if mode == "B":
            opts = [chunk] if chunk else []
            opts += get_random_terms_from_pack(pack_id, item_id, limit=2)
            opts = [o for o in opts if o]
            while len(opts) < 3:
                opts.append("Mi scusi, può aiutarmi?")
            opts = opts[:3]
            set_session(user.id, mode="review", item_id=item_id, stage="await_choice", meta={"options": opts, "correct": 0, "due_total": due_count, "due_index": 1, "mode": mode})
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"A) {opts[0]}", callback_data=f"REVIEW|CHOICE|{item_id}|0")],
                [InlineKeyboardButton(f"B) {opts[1]}", callback_data=f"REVIEW|CHOICE|{item_id}|1")],
                [InlineKeyboardButton(f"C) {opts[2]}", callback_data=f"REVIEW|CHOICE|{item_id}|2")],
            ])
            text = review_header("Review", due_count) + "\n" + "🧠 Which phrase fits?\n" + f"👉 {h(translation_en or 'Say this in Italian.')}"
            await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        elif mode == "C":
            npc = get_random_context_for_item(item_id) or "Il gate è cambiato."
            prompt = (
                "👮 Staff:\n"
                f"{h(npc)}\n\n"
                "How do you respond?"
            )
        else:
            prompt = (
                "🧠 Situation\n"
                f"{h(translation_en or 'You need help in a real situation.')}\n\n"
                "What do you say?"
            )
        text = review_header("Review", due_count) + "\n" + prompt
    else:
        text = review_header("Review", due_count) + "\n" + review_prompt_word(term or chunk, 1, due_count)

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=review_actions_keyboard(item_id, is_phrase))


async def review_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, pack_id: str):
    user = update.effective_user
    msg = get_chat_sender(update)

    item_id = get_due_item_in_pack(user.id, pack_id)
    if not item_id:
        await msg.reply_text("🎉 Nothing due in this pack. Use /journey or /packs.")
        return

    item = get_item_by_id(item_id)
    if not item:
        await msg.reply_text("Review error. Try again.")
        return

    _, term, chunk, translation_en, note, pack_id, focus = item
    total, introduced = get_pack_item_counts(user.id, pack_id)
    upsert_user_pack_progress(user.id, pack_id, introduced, total)
    due_count = get_due_count_in_pack(user.id, pack_id)
    is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)
    review_state = get_review_state(user.id, item_id)
    status = review_state[0] if review_state else "new"
    mode = "A"
    if is_phrase:
        if due_count >= 20 or status == "new":
            mode = "B"
        elif status == "mature":
            mode = "C"
        else:
            mode = "A"
    set_session(user.id, mode="review", item_id=item_id, stage="await_sentence", meta={"due_total": due_count, "due_index": 1, "mode": mode, "pack_id": pack_id})

    if is_phrase:
        if mode == "B":
            opts = [chunk] if chunk else []
            opts += get_random_terms_from_pack(pack_id, item_id, limit=2)
            opts = [o for o in opts if o]
            while len(opts) < 3:
                opts.append("Mi scusi, può aiutarmi?")
            opts = opts[:3]
            set_session(user.id, mode="review", item_id=item_id, stage="await_choice", meta={"options": opts, "correct": 0, "due_total": due_count, "due_index": 1, "mode": mode, "pack_id": pack_id})
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"A) {opts[0]}", callback_data=f"REVIEW|CHOICE|{item_id}|0")],
                [InlineKeyboardButton(f"B) {opts[1]}", callback_data=f"REVIEW|CHOICE|{item_id}|1")],
                [InlineKeyboardButton(f"C) {opts[2]}", callback_data=f"REVIEW|CHOICE|{item_id}|2")],
            ])
            text = review_header("Pack Review", due_count) + "\n" + "🧠 Which phrase fits?\n" + f"👉 {h(translation_en or 'Say this in Italian.')}"
            await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        elif mode == "C":
            npc = get_random_context_for_item(item_id) or "Il gate è cambiato."
            prompt = (
                "👮 Staff:\n"
                f"{h(npc)}\n\n"
                "How do you respond?"
            )
        else:
            prompt = (
                "🧠 Situation\n"
                f"{h(translation_en or 'You need help in a real situation.')}\n\n"
                "What do you say?"
            )
        text = review_header("Pack Review", due_count) + "\n" + prompt
    else:
        text = review_header("Pack Review", due_count) + "\n" + review_prompt_word(term or chunk, 1, due_count)

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=review_actions_keyboard(item_id, is_phrase))


async def on_review_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage, meta = session
    if mode == "review" and stage == "await_sentence" and item_id is not None:
        item = get_item_by_id(item_id)
        focus = item[6] if item and len(item) > 6 else None
        term = item[1] if item else ""
        chunk = item[2] if item else ""
        translation_en = item[3] if item else ""
        is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)
        msg = get_chat_sender(update)

        if not is_phrase:
            level_from = get_user_level(user.id)
            level_to = _next_level(level_from)
            upgrade = await generate_sentence_upgrade(
                term=term or chunk,
                user_sentence=text,
                level_from=level_from,
                level_to=level_to,
            )
            out = [
                f"✅ <b>{h(term or chunk)}</b>",
                "",
                f"Your sentence:\n“{h(text)}”",
            ]
            if upgrade.get("ok"):
                if upgrade.get("better"):
                    out.append(f"\nBetter ({level_from}):\n{h(upgrade['better'])}")
                if upgrade.get("level_up"):
                    out.append(f"\nLevel‑up ({level_to}):\n{h(upgrade['level_up'])}")
                if upgrade.get("native_sentence"):
                    out.append(f"\nNative:\n{h(upgrade['native_sentence'])}")
                if upgrade.get("tip"):
                    out.append(f"\nTip:\n{h(upgrade['tip'])}")
            else:
                fb = await generate_learn_feedback(
                    target_language="it",
                    term=term or chunk,
                    chunk=chunk or term,
                    translation_en=translation_en,
                    user_sentence=text,
                    lexicon=get_or_fetch_lexicon_it(term or chunk),
                )
                if fb.get("correction"):
                    out.append(f"\nFix:\n{h(fb['correction'])}")
                elif fb.get("rewrite"):
                    out.append(f"\nBetter:\n{h(fb['rewrite'])}")
                examples = fb.get("examples") or []
                if examples and examples[0]:
                    out.append(f"\nNative:\n{h(examples[0])}")
                if fb.get("notes"):
                    out.append(f"\nTip:\n{h(fb['notes'])}")
            await msg.reply_text("\n".join(out), parse_mode=ParseMode.HTML)
        else:
            expected = chunk or term
            if expected:
                await msg.reply_text(f"✅ Expected:\n{h(expected)}", parse_mode=ParseMode.HTML)
            else:
                await msg.reply_text("✅ Got it.")

        # now ask the user to rate themselves
        set_session(user.id, mode="review", item_id=item_id, stage="await_grade", meta=meta)
        await msg.reply_text(
            review_grade_prompt(),
            reply_markup=grade_keyboard(item_id, is_phrase)
        )

async def on_grade_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    _, grade_raw, item_id_str = query.data.split("|", 2)
    item_id = int(item_id_str)

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("No active review session. Type /review.")
        return

    mode, session_item_id, stage, meta = session
    if mode != "review" or stage != "await_grade" or session_item_id != item_id:
        await query.edit_message_text("Invalid grading action. Type /review again.")
        return


    grade = grade_raw
    if grade_raw.isdigit():
        val = int(grade_raw)
        if val <= 1:
            grade = "again"
        elif val <= 3:
            grade = "hard"
        else:
            grade = "good"

    new_status, new_interval, new_due = apply_grade(user.id, item_id, grade)
    record_practice(user.id, "review", grade != "again")

    clear_session(user.id)

    await query.edit_message_text(
        f"✅ Saved.\n"
        f"Next due: {new_due} (in {new_interval} day(s))",
        reply_markup=undo_keyboard(item_id)
    )

    # Auto-continue: immediately send the next due item (keeps the undo message intact)
    pack_id = (meta or {}).get("pack_id")
    if pack_id:
        next_item_id = get_due_item_in_pack(user.id, pack_id)
        due_total = get_due_count_in_pack(user.id, pack_id)
    else:
        next_item_id = get_due_item(user.id)
        due_total = get_due_count(user.id)

    if not next_item_id:
        await query.message.reply_text("🎉 All done for today. Type /journey to add more.")
        return

    next_item = get_item_by_id(next_item_id)
    if not next_item:
        await query.message.reply_text("Review error loading next item. Type /review.")
        return

    _, term, chunk, translation_en, note, pack_id, focus = next_item

    meta = meta or {}
    due_index = int(meta.get("due_index") or 1) + 1
    is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)
    review_state = get_review_state(user.id, next_item_id)
    status = review_state[0] if review_state else "new"
    mode = "A"
    if is_phrase:
        if due_total >= 20 or status == "new":
            mode = "B"
        elif status == "mature":
            mode = "C"
        else:
            mode = "A"
    set_session(user.id, mode="review", item_id=next_item_id, stage="await_sentence", meta={"due_total": due_total, "due_index": due_index, "mode": mode, "pack_id": meta.get("pack_id")})

    due_count = due_total
    title = "Pack Review" if meta.get("pack_id") else "Review"
    if is_phrase:
        if mode == "B":
            opts = [chunk] if chunk else []
            opts += get_random_terms_from_pack(pack_id, next_item_id, limit=2)
            opts = [o for o in opts if o]
            while len(opts) < 3:
                opts.append("Mi scusi, può aiutarmi?")
            opts = opts[:3]
            set_session(user.id, mode="review", item_id=next_item_id, stage="await_choice", meta={
                "options": opts,
                "correct": 0,
                "due_total": due_total,
                "due_index": due_index,
                "mode": mode,
                "pack_id": meta.get("pack_id"),
            })
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"A) {opts[0]}", callback_data=f"REVIEW|CHOICE|{next_item_id}|0")],
                [InlineKeyboardButton(f"B) {opts[1]}", callback_data=f"REVIEW|CHOICE|{next_item_id}|1")],
                [InlineKeyboardButton(f"C) {opts[2]}", callback_data=f"REVIEW|CHOICE|{next_item_id}|2")],
            ])
            next_text = review_header(title, due_count) + "\n" + "🧠 Which phrase fits?\n" + f"👉 {h(translation_en or 'Say this in Italian.')}"
            await query.message.reply_text(next_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        elif mode == "C":
            npc = get_random_context_for_item(next_item_id) or "Il gate è cambiato."
            prompt = (
                "👮 Staff:\n"
                f"{h(npc)}\n\n"
                "How do you respond?"
            )
        else:
            prompt = (
                "🧠 Situation\n"
                f"{h(translation_en or 'You need help in a real situation.')}\n\n"
                "What do you say?"
            )
        next_text = review_header(title, due_count) + "\n" + prompt
    else:
        next_text = review_header(title, due_count) + "\n" + review_prompt_word(term or chunk, due_index, due_total)

    await query.message.reply_text(next_text, parse_mode=ParseMode.HTML, reply_markup=review_actions_keyboard(next_item_id, is_phrase))



async def on_undo_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    _, item_id_str = query.data.split("|", 1)
    item_id = int(item_id_str)

    restored = undo_last_grade(user.id, item_id)
    if not restored:
        await query.edit_message_text("⚠️ Undo not available (already used or expired). Type /review.")
        return

    status, interval_days, due_date = restored
    await query.edit_message_text(
        f"↩️ Undone.\n"
        f"Restored status: {status}\n"
        f"Restored due: {due_date} (interval {interval_days} day(s))\n\n"
        f"Type /review to continue."
    )


async def resume_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)
    session = get_session(user.id)
    if not session:
        await msg.reply_text("No active review session. Type /review.")
        return
    mode, item_id, stage, meta = session
    if mode != "review" or not item_id:
        await msg.reply_text("No active review session. Type /review.")
        return
    item = get_item_by_id(item_id)
    if not item:
        await msg.reply_text("Review error. Try /review again.")
        return
    _, term, chunk, translation_en, note, pack_id, focus = item
    is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)
    pack_id = (meta or {}).get("pack_id")
    if pack_id:
        due_total = int((meta or {}).get("due_total") or get_due_count_in_pack(user.id, pack_id))
        due_count = get_due_count_in_pack(user.id, pack_id)
        title = "Pack Review"
    else:
        due_total = int((meta or {}).get("due_total") or get_due_count(user.id))
        due_count = get_due_count(user.id)
        title = "Review"
    due_index = int((meta or {}).get("due_index") or 1)
    if stage == "await_grade":
        await msg.reply_text(review_grade_prompt(), reply_markup=grade_keyboard(item_id, is_phrase))
        return
    mode = (meta or {}).get("mode") or "A"
    if is_phrase:
        if mode == "B":
            prompt = (
                "🧠 Which phrase fits?\n"
                f"👉 {h(translation_en or 'Say this in Italian.')}"
            )
        elif mode == "C":
            npc = get_random_context_for_item(item_id) or "Il gate è cambiato."
            prompt = (
                "👮 Staff:\n"
                f"{h(npc)}\n\n"
                "How do you respond?"
            )
        else:
            prompt = (
                "🧠 Situation\n"
                f"{h(translation_en or 'You need help in a real situation.')}\n\n"
                "What do you say?"
            )
        text = review_header(title, due_count) + "\n" + prompt
    else:
        text = review_header(title, due_count) + "\n" + review_prompt_word(term or chunk, due_index, due_total)
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=review_actions_keyboard(item_id, is_phrase))


async def on_review_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    parts = (query.data or "").split("|")
    if len(parts) < 3:
        return
    action = parts[1]
    item_id = int(parts[2])

    item = get_item_by_id(item_id)
    if not item:
        await query.edit_message_text("Review error. Try /review.")
        return
    _, term, chunk, translation_en, note, pack_id, focus = item
    is_phrase = (focus == "phrase") or (chunk and len(chunk.split()) > 1)

    if action == "HINT":
        await query.message.reply_text(f"💡 Hint: {h(translation_en or '-')}", parse_mode=ParseMode.HTML)
        return
    if action == "EXAMPLE":
        ex = get_random_context_for_item(item_id) or ""
        if not ex:
            ex = chunk
        await query.message.reply_text(f"📝 Example: {h(ex)}", parse_mode=ParseMode.HTML)
        return
    if action == "PRON":
        try:
            await _send_tts(query.message, chunk or term or "")
        except Exception as e:
            await query.message.reply_text(
                f"Pronunciation unavailable ({type(e).__name__}).",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Retry", callback_data=f"REVIEW|PRON|{item_id}")],
                    [InlineKeyboardButton("🩺 TTS Check", callback_data="TTS|CHECK")],
                ]),
            )
        return
    if action == "OPTIONS" and is_phrase:
        session = get_session(user.id)
        meta = session[3] if session else {}
        opts = [chunk] if chunk else []
        opts += get_random_terms_from_pack(pack_id, item_id, limit=2)
        opts = [o for o in opts if o]
        while len(opts) < 3:
            opts.append("Mi scusi, può aiutarmi?")
        opts = opts[:3]
        correct = 0
        set_session(user.id, mode="review", item_id=item_id, stage="await_choice", meta={
            "options": opts,
            "correct": correct,
            "due_total": (meta or {}).get("due_total"),
            "due_index": (meta or {}).get("due_index"),
            "mode": (meta or {}).get("mode"),
            "pack_id": (meta or {}).get("pack_id"),
        })
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"A) {opts[0]}", callback_data=f"REVIEW|CHOICE|{item_id}|0")],
            [InlineKeyboardButton(f"B) {opts[1]}", callback_data=f"REVIEW|CHOICE|{item_id}|1")],
            [InlineKeyboardButton(f"C) {opts[2]}", callback_data=f"REVIEW|CHOICE|{item_id}|2")],
        ])
        await query.message.reply_text("Choose the best phrase:", reply_markup=kb)
        return
    if action == "SKIP":
        apply_grade(user.id, item_id, "again")
        record_practice(user.id, "review", False)
        clear_session(user.id)
        await query.message.reply_text("⏭ Skipped. Type /review to continue.")

    if action == "CHOICE":
        # handled in on_review_choice
        return


async def on_review_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = (query.data or "").split("|")
    if len(parts) < 4:
        return
    item_id = int(parts[2])
    picked = int(parts[3])
    session = get_session(query.from_user.id)
    if not session:
        return
    mode, session_item_id, stage, meta = session
    if mode != "review" or stage != "await_choice" or session_item_id != item_id:
        return
    correct = int((meta or {}).get("correct", 0))
    if picked == correct:
        await query.message.reply_text("✅ Correct.")
    else:
        options = (meta or {}).get("options") or []
        right = options[correct] if correct < len(options) else ""
        await query.message.reply_text(f"❌ Correct: {h(right)}", parse_mode=ParseMode.HTML)
    # move to grade
    set_session(query.from_user.id, mode="review", item_id=item_id, stage="await_grade", meta=meta)
    item = get_item_by_id(item_id)
    focus = item[6] if item and len(item) > 6 else None
    is_phrase = (focus == "phrase")
    await query.message.reply_text(review_grade_prompt(), reply_markup=grade_keyboard(item_id, is_phrase))


async def on_review_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = (query.data or "").split("|", 1)[1] if "|" in (query.data or "") else ""
    if action == "RESUME":
        from bot.handlers.learn import learn
        await query.edit_message_text("▶️ Resuming mission…")
        await learn(update, context)
        return
    if action == "NOW":
        # End current session so review can proceed
        user = query.from_user
        clear_session(user.id)
        await query.edit_message_text("🔁 Starting review…")
        await review(update, context)
