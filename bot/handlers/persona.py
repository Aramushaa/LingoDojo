from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.db import get_user_persona, set_user_persona, set_session, get_session, clear_session
from bot.utils.telegram import get_chat_sender


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = get_chat_sender(update)

    persona = get_user_persona(user.id) or (None, None, None)
    name, city, role = persona
    current = "not set"
    if name or city or role:
        current = f"{name or 'Unknown'} — {role or 'role'} in {city or 'city'}"

    await msg.reply_text(
        f"🎭 <b>Alter‑Ego</b>\n"
        f"Current: <b>{current}</b>\n\n"
        f"Let's update it.\n"
        f"What's your Italian name?",
        parse_mode=ParseMode.HTML,
    )

    clear_session(user.id)
    set_session(user.id, mode="persona", item_id=None, stage="ask_name", meta={})


async def on_persona_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if mode != "persona":
        return

    meta = meta or {}
    if stage == "ask_name":
        meta["name"] = text
        set_session(user.id, mode="persona", item_id=None, stage="ask_role", meta=meta)
        await msg.reply_text("Great. What's your role/job?")
        return

    if stage == "ask_role":
        meta["role"] = text
        set_session(user.id, mode="persona", item_id=None, stage="ask_city", meta=meta)
        await msg.reply_text("And which city are you in?")
        return

    if stage == "ask_city":
        name = meta.get("name")
        role = meta.get("role")
        city = text
        set_user_persona(user.id, name, city, role)
        clear_session(user.id)
        await msg.reply_text(
            f"✅ Alter‑Ego updated:\n"
            f"<b>{name}</b> — <b>{role}</b> in <b>{city}</b>",
            parse_mode=ParseMode.HTML,
        )
