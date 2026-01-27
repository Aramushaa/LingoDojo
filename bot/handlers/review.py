from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from bot.db import get_due_item, get_item_by_id, set_session, get_session, clear_session, apply_grade,undo_last_grade
from bot.utils.telegram import get_chat_sender


def grade_keyboard(item_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Good", callback_data=f"GRADE|good|{item_id}"),
            InlineKeyboardButton("😅 Hard", callback_data=f"GRADE|hard|{item_id}"),
            InlineKeyboardButton("❌ Again", callback_data=f"GRADE|again|{item_id}")
        ]
    ])

def undo_keyboard(item_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Undo last grade", callback_data=f"UNDO|{item_id}")]
    ])



async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    item_id = get_due_item(user.id)
    msg = get_chat_sender(update)

    if not item_id:
        await msg.reply_text("🎉 Nothing due today. Use /learn to add more words.")
        return

    item = get_item_by_id(item_id)
    if not item:
        await msg.reply_text("Review error. Try /review again.")
        return

    _, term, chunk, translation_en, note = item

    set_session(user.id, mode="review", item_id=item_id, stage="await_sentence")

    text = (
        f"🧠 *Review*\n\n"
        f"Chunk: *{chunk}*\n"
        f"(Hint EN: {translation_en or '-'})\n\n"
        f"👉 Write *one sentence* using the chunk."
    )

    await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def on_review_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage = session
    if mode == "review" and stage == "await_sentence" and item_id is not None:
        # now ask the user to grade themselves (fast UX)
        set_session(user.id, mode="review", item_id=item_id, stage="await_grade")

        msg = get_chat_sender(update)
        await msg.reply_text(
            "How did it go?",
            reply_markup=grade_keyboard(item_id)
        )

async def on_grade_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    _, grade, item_id_str = query.data.split("|", 2)
    item_id = int(item_id_str)

    session = get_session(user.id)
    if not session:
        await query.edit_message_text("No active review session. Type /review.")
        return

    mode, session_item_id, stage = session
    if mode != "review" or stage != "await_grade" or session_item_id != item_id:
        await query.edit_message_text("Invalid grading action. Type /review again.")
        return


    new_status, new_interval, new_due = apply_grade(user.id, item_id, grade)

    clear_session(user.id)

    await query.edit_message_text(
        f"✅ Saved ({grade}).\n"
        f"Status: {new_status}\n"
        f"Next due: {new_due} (in {new_interval} day(s))\n\n"
        f"Type /review for the next due item or /learn to add more.",
        reply_markup=undo_keyboard(item_id)
    )

    # Auto-continue: immediately send the next due item (keeps the undo message intact)
    next_item_id = get_due_item(user.id)

    if not next_item_id:
        await query.message.reply_text("🎉 All done for today. Type /learn to add more.")
        return

    next_item = get_item_by_id(next_item_id)
    if not next_item:
        await query.message.reply_text("Review error loading next item. Type /review.")
        return

    _, term, chunk, translation_en, note = next_item

    set_session(user.id, mode="review", item_id=next_item_id, stage="await_sentence")

    next_text = (
        f"🧠 *Review*\n\n"
        f"Chunk: *{chunk}*\n"
        f"(Hint EN: {translation_en or '-'})\n\n"
        f"👉 Write *one sentence* using the chunk."
    )

    await query.message.reply_text(next_text, parse_mode=ParseMode.MARKDOWN)



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
