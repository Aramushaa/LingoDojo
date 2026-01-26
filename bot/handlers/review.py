from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.db import get_due_item, get_item_by_id, set_session, get_session, clear_session, apply_grade

def grade_keyboard(item_id: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Good", callback_data=f"GRADE|good|{item_id}"),
            InlineKeyboardButton("❌ Again", callback_data=f"GRADE|again|{item_id}")
        ]
    ])

async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    item_id = get_due_item(user.id)
    if not item_id:
        await update.message.reply_text("🎉 Nothing due today. Use /learn to add more words.")
        return

    item = get_item_by_id(item_id)
    if not item:
        await update.message.reply_text("Review error. Try /review again.")
        return

    _, term, chunk, translation_en, note = item

    set_session(user.id, mode="review", item_id=item_id, stage="await_sentence")

    msg = (
        f"🧠 *Review*\n\n"
        f"Chunk: *{chunk}*\n"
        f"(Hint EN: {translation_en or '-'})\n\n"
        f"👉 Write *one sentence* using the chunk."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

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

        await update.message.reply_text(
            "How did it feel?",
            reply_markup=grade_keyboard(item_id)
        )

async def on_grade_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    _, grade, item_id_str = query.data.split("|", 2)
    item_id = int(item_id_str)

    new_status, new_interval, new_due = apply_grade(user.id, item_id, grade)

    clear_session(user.id)

    await query.edit_message_text(
        f"✅ Saved.\n"
        f"Status: {new_status}\n"
        f"Next due: {new_due} (in {new_interval} day(s))\n\n"
        f"Type /review for the next due item or /learn to add more."
    )
