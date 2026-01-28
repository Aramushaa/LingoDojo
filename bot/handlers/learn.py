from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender
from bot.config import SHOW_DICT_DEBUG

from bot.db import (
    list_packs, activate_pack, get_user_active_packs,
    pick_one_item_from_pack, set_session, get_session,
    clear_session, get_item_by_id, ensure_review_row,
    get_user_languages, get_lexicon_cache_it
)

from bot.services.dictionary_it import validate_it_term
from bot.services.ai_feedback import generate_learn_feedback
from bot.services.lexicon_it import get_or_fetch_lexicon_it




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

    try:
        get_or_fetch_lexicon_it(term)  # prefetch/cache; don't block UX
    except Exception:
        pass



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
    if not (mode == "learn" and stage == "await_sentence" and item_id is not None):
        return

    # 1) Load the current learning item
    item = get_item_by_id(item_id)
    if not item:
        clear_session(user.id)
        msg = get_chat_sender(update)
        await msg.reply_text("Session error. Try /learn again.")
        return

    _, term, chunk, translation_en, note = item

    # 2) Get cached lexicon facts (silent grounding)
    lexicon = get_lexicon_cache_it(term)  # may be None if not cached yet

    # Optional: add a soft validation result (debug only)
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

    # 3) AI feedback (safe fallback if not configured)
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
        f"✅ *Learn — Feedback*\n\n"
        f"Chunk: *{chunk}*\n"
        f"Your sentence:\n“{text}”\n"
        f"{debug_line}"
    )

    if ai.get("correction"):
        reply += f"\n🛠 *Correction*: {ai['correction']}\n"
    if ai.get("rewrite"):
        reply += f"\n✨ *Rewrite*: {ai['rewrite']}\n"
    if ai.get("notes"):
        reply += f"\n💡 {ai['notes']}\n"

    reply += (
        f"\n📌 *Examples*:\n{examples_block}\n\n"
        f"Type /review to practice or /learn for another item."
    )

    msg = get_chat_sender(update)
    await msg.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    clear_session(user.id)
