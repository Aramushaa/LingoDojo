from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.db import get_user_languages
from bot.db import (
    list_packs, activate_pack, get_user_active_packs,
    pick_one_item_from_pack, set_session, get_session,
    clear_session, get_item_by_id
)

async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    langs = get_user_languages(user.id)
    if not langs:
        await update.message.reply_text("Use /start first.")
        return

    target_language, ui_language = langs
    packs = list_packs(target_language)


    if not packs:
        await update.message.reply_text("No packs found. (Import failed?)")
        return

    active = set(get_user_active_packs(user.id))

    buttons = []
    for pack_id, level, title, description in packs:
        label = f"✅ {title}" if pack_id in active else f"📦 {title}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"PACK|{pack_id}")])

    await update.message.reply_text(
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
    set_session(user.id, mode="learn", item_id=item_id, stage="await_sentence")

    msg = (
        f"🧩 *Learn Task*\n\n"
        f"Word: *{term}*\n"
        f"Chunk: *{chunk}*\n"
        f"Meaning (EN): {translation_en or '-'}\n\n"
        f"👉 Now you: write *one Italian sentence* using the chunk.\n"
        f"(Just type it as a normal message.)"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")

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
            await update.message.reply_text("Session error. Try /learn again.")
            return

        _, term, chunk, translation_en, note = item

        reply = (
            f"✅ Nice! You did the active part (you produced output).\n\n"
            f"Your sentence:\n“{text}”\n\n"
            f"Native-ish example:\n"
            f"• *Oggi vorrei prendere un caffè.*\n\n"
            f"Type /learn for another task."
        )

        clear_session(user.id)
        await update.message.reply_text(reply, parse_mode="Markdown")
