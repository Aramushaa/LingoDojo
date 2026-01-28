from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db import get_user_languages,ensure_review_row,apply_grade
from bot.db import (
    list_packs, activate_pack, get_user_active_packs,
    pick_one_item_from_pack, set_session, get_session,
    clear_session, get_item_by_id,ensure_review_row
)
from telegram.constants import ParseMode
from bot.utils.telegram import get_chat_sender
from bot.services.dictionary_it import validate_it_term
from bot.config import SHOW_DICT_DEBUG
from bot.services.ai_feedback import generate_learn_feedback

async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    langs = get_user_languages(user.id)
    if not langs:
        msg = get_chat_sender(update)
        await msg.reply_text("Use /start first.")
        return

    target_language, ui_language = langs
    packs = list_packs(target_language)


    if not packs:
        msg = get_chat_sender(update)
        await msg.reply_text("No packs found. (Import failed?)")
        return

    active = set(get_user_active_packs(user.id))

    buttons = []
    for pack_id, level, title, description in packs:
        label = f"✅ {title}" if pack_id in active else f"📦 {title}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"PACK|{pack_id}")])
    msg = get_chat_sender(update)
    await msg.reply_text(
        "Choose a pack to activate (✅ means active):",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def on_pack_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    _, pack_id = query.data.split("|", 1)

    activate_pack(user.id, pack_id)

    item = pick_one_item_from_pack(pack_id)

    if not item:
        await query.edit_message_text("This pack has no items.")
        return

    item_id, term, chunk, translation_en, note = item

    ensure_review_row(user.id, item_id)
    
    set_session(user.id, mode="learn", item_id=item_id, stage="await_sentence")

    msg = (
        f"🧩 *Learn Task*\n\n"
        f"Word: *{term}*\n"
        f"Chunk: *{chunk}*\n"
        f"Meaning (EN): {translation_en or '-'}\n\n"
        f"👉 Now you: write *one Italian sentence* using the chunk.\n"
        f"(Just type it as a normal message.)"
    )
    await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage = session
    if mode == "learn" and stage == "await_sentence" and item_id is not None:
        item = get_item_by_id(item_id)
        if not item:
            clear_session(user.id)
            msg = get_chat_sender(update)
            await msg.reply_text("Session error. Try /learn again.")
            return

        _, term, chunk, translation_en, note = item


        # 1) Silent dictionary validation (guardrails)
        validation = {"ok": True}
        try:
            validation = validate_it_term(term)
        except Exception:
            validation = {"ok": True}

        # 2) AI feedback (safe: fallback if not configured)
        ai = await generate_learn_feedback(
            target_language="it",
            term=term,
            chunk=chunk,
            translation_en=translation_en,
            user_sentence=text,
            dict_validation=validation,
        )

        # 3) Ensure item enters SRS queue, but do NOT grade it here
        ensure_review_row(user.id, item_id)

        debug_line = ""
        if SHOW_DICT_DEBUG and not validation.get("ok"):
            debug_line = f"\n🛠 dict check failed for '{term}', suggestion: {validation.get('suggestion')}\n"





        examples = ai.get("examples") or []
        examples_block = "\n".join([f"• {ex}" for ex in examples[:3]]) if examples else "• (no examples)"

        correction = ai.get("correction")
        rewrite = ai.get("rewrite")
        notes = ai.get("notes") or ""

        reply = (
            f"✅ *Learn — Feedback*\n\n"
            f"Chunk: *{chunk}*\n"
            f"Your sentence:\n“{text}”\n"
            f"{debug_line}\n"
        )

        if correction:
            reply += f"\n🛠 *Correction*: {correction}\n"
        if rewrite:
            reply += f"\n✨ *Native rewrite*: {rewrite}\n"
        if notes:
            reply += f"\n💡 {notes}\n"

        reply += (
            f"\n📌 *Examples*:\n{examples_block}\n\n"
            f"Type /review to practice or /learn for another item."
        )

        msg = get_chat_sender(update)
        await msg.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
        clear_session(user.id)



        ensure_review_row(user.id, item_id)
        clear_session(user.id)
        msg = get_chat_sender(update)
        await msg.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

