from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

import random

from bot.db import get_connection, get_user_persona, set_user_persona, set_session, clear_session, get_session
from bot.ui import home_keyboard
from bot.ui import home_keyboard
from bot.utils.telegram import get_chat_sender


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    session = get_session(user.id)
    msg = get_chat_sender(update)
    if session:
        mode, item_id, stage, meta = session
        await msg.reply_text(
            "You're in the middle of something.\nResume?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Resume", callback_data="START|RESUME")],
                [InlineKeyboardButton("🏠 Home", callback_data="START|HOME")],
                [InlineKeyboardButton("❌ End session", callback_data="START|END")],
            ])
        )
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (user_id, first_name, created_at, target_language, ui_language, helper_language)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user.id, user.first_name, utc_now_iso(), "it", "en", None)

    )
    conn.commit()
    conn.close()

    await msg.reply_text(
        "🏠 <b>Home</b>\nChoose where to go next:",
        reply_markup=home_keyboard(),
        parse_mode="HTML",
    )

    persona = get_user_persona(user.id)
    if not persona or not any(persona):
        clear_session(user.id)
        set_session(user.id, mode="onboarding", item_id=None, stage="ask_job", meta={})
        await msg.reply_text(
            "🎭 <b>Alter‑Ego setup</b>\n"
            "What is your dream job? (1–3 words)",
            parse_mode="HTML"
        )


def _pick_italian_name() -> str:
    names = ["Giovanni", "Marco", "Luca", "Matteo", "Francesco", "Sofia", "Giulia", "Alessia", "Martina", "Chiara"]
    return random.choice(names)


async def on_onboarding_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)
    text = (update.message.text or "").strip()
    if not text:
        await msg.reply_text("Please type a short answer.")
        return

    session = get_session(user.id)
    if not session:
        return

    mode, item_id, stage, meta = session
    if mode != "onboarding":
        return

    if stage == "ask_job":
        meta = meta or {}
        meta["job"] = text
        set_session(user.id, mode="onboarding", item_id=None, stage="ask_city", meta=meta)
        await msg.reply_text("Nice. Which city do you live in? (in Italy)")
        return

    if stage == "ask_city":
        job = (meta or {}).get("job") or "student"
        city = text
        name = _pick_italian_name()
        set_user_persona(user.id, name, city, job)
        clear_session(user.id)
        await msg.reply_text(
            f"✅ Done.\n"
            f"From now on, you are <b>{name}</b>, a <b>{job}</b> in <b>{city}</b>.\n"
            f"All missions will talk to you as {name}.",
            parse_mode="HTML"
        )


async def on_start_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    msg = get_chat_sender(update)

    session = get_session(user.id)
    action = (query.data or "").split("|", 1)[1] if "|" in (query.data or "") else ""

    if action == "END":
        clear_session(user.id)
        await query.edit_message_text("Session ended. Back to home.")
        await msg.reply_text("🏠 <b>Home</b>\nChoose where to go next:", reply_markup=home_keyboard(), parse_mode="HTML")
        return

    if action == "HOME":
        await query.edit_message_text("🏠 Home")
        await msg.reply_text("🏠 <b>Home</b>\nChoose where to go next:", reply_markup=home_keyboard(), parse_mode="HTML")
        return

    if action == "RESUME" and session:
        mode, item_id, stage, meta = session
        if mode == "learn":
            from bot.handlers.learn import learn
            await query.edit_message_text("▶️ Resuming…")
            await learn(update, context)
            return
        if mode == "review":
            from bot.handlers.review import resume_review
            await query.edit_message_text("▶️ Resuming…")
            await resume_review(update, context)
            return
        if mode in ("onboarding", "persona"):
            await query.edit_message_text("▶️ Resuming…")
            await msg.reply_text("Continue where you left off.")
            return

    await query.edit_message_text("Nothing to resume.")


