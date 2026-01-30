from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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
)

from bot.services.dictionary_it import validate_it_term
from bot.services.ai_feedback import generate_learn_feedback,generate_reverse_context_quiz
from bot.services.lexicon_it import get_or_fetch_lexicon_it
from bot.services.tts_edge import tts_it


def h(text: str) -> str:
    return escape(text or "")




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
    )

    meta = {
        "term": term,
        "chunk": chunk,
        "translation_en": translation_en,
        "quiz": quiz,
    }

    set_session(user.id, mode="learn", item_id=item_id, stage="await_guess", meta=meta)
    

    # Progress header
    total = get_active_items_total(user.id, target)
    introduced = get_active_items_introduced(user.id)
    progress_line = f"📦 Progress: {introduced}/{total}"

    opts = quiz.get("options_en", ["A", "B", "C"])
    keyboard = [
        [InlineKeyboardButton(f"A) {opts[0]}", callback_data="GUESS|0")],
        [InlineKeyboardButton(f"B) {opts[1]}", callback_data="GUESS|1")],
        [InlineKeyboardButton(f"C) {opts[2]}", callback_data="GUESS|2")],
        [InlineKeyboardButton("🔊 Pronounce", callback_data="PRON|word")],
    ]

    text = (
        f"{progress_line}\n\n"
        f"🕵️ <b>Guess the meaning</b>\n\n"
        f"Word: <b>{h(term)}</b>\n\n"
        f"Context:\n<i>{h(quiz.get('context_it',''))}</i>\n\n"
        f"Pick the best meaning:"
    )

    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))





async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage, meta = session
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
    ai = await generate_learn_feedback(
        target_language="it",
        term=term,
        chunk=chunk,
        translation_en=translation_en,
        user_sentence=text,
        lexicon=lexicon,
    )

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

    msg = (
        f"{status}\n"
        f"<b>Meaning:</b> {h(meaning)}\n"
    )
    if clue:
        msg += f"<i>Clue:</i> {h(clue)}\n"

    msg += (
        f"\n✍️ Now you:\n"
        f"Write <b>one Italian sentence</b> using the word <b>{h(meta.get('term') or '')}</b>.\n"
        f"(Any sentence you want — your choice.)"
    )

    await query.edit_message_text(msg, parse_mode=ParseMode.HTML)


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

    try:
        path = await tts_it(term)

        # Decide how to send based on extension
        suffix = path.suffix.lower()

        with open(path, "rb") as f:
            if suffix == ".ogg":
                await query.message.reply_voice(
                    voice=InputFile(f, filename=f"{term}.ogg"),
                    caption=f"🔊 {term}",
                )
            else:
                # mp3/wav -> send as audio
                await query.message.reply_audio(
                    audio=InputFile(f, filename=f"{term}{suffix}"),
                    title=term,
                )

    except Exception as e:
        await query.message.reply_text(f"TTS failed: {type(e).__name__}: {e}")
