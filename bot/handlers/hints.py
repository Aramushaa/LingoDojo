from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from bot.utils.telegram import get_chat_sender
from bot.db import get_session, get_user_profile
from bot.handlers.learn import h


async def hint_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    user = update.effective_user
    if not user:
        return

    session = get_session(user.id)
    if not session:
        await msg.reply_text("No active card.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn":
        await msg.reply_text("Hints are only available during Learn.")
        return

    meta = meta or {}
    if stage == "await_guess":
        meaning = meta.get("translation_en") or (meta.get("quiz") or {}).get("meaning_en")
        if meaning:
            await msg.reply_text(f"ℹ️ Hint: {h(str(meaning))}", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("ℹ️ Hint: focus on the context sentence.")
        return

    if stage == "await_sentence":
        term = meta.get("term") or ""
        if term:
            await msg.reply_text(f"ℹ️ Use: <b>{h(term)}</b>", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("ℹ️ Try using the target word.")
        return

    if stage == "scene_turn":
        scene = (meta or {}).get("scene") or {}
        turns = scene.get("turns") or []
        idx = int(scene.get("idx", 0))
        expected = None
        if idx < len(turns):
            expected = turns[idx].get("expected_phrase")
        if expected:
            await msg.reply_text(f"ℹ️ Try: <b>{h(expected)}</b>", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("ℹ️ Stay in role and answer naturally.")
        return

    await msg.reply_text("No hint available.")


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    user = update.effective_user
    if not user:
        return

    session = get_session(user.id)
    if not session:
        await msg.reply_text("No active card.")
        return

    mode, item_id, stage, meta = session
    if mode != "learn":
        await msg.reply_text("Why is only available during Learn.")
        return

    meta = meta or {}
    if stage == "await_guess":
        quiz = meta.get("quiz") or {}
        ctx = quiz.get("context_it")
        holo = meta.get("holo") or {}
        drills = holo.get("drills") or {}
        scenario = drills.get("scenario_prompt")
        lines = []
        if ctx:
            lines.append(f"📌 Context: <i>{h(ctx)}</i>")
        if scenario:
            lines.append(f"🎬 Scenario: {h(scenario)}")
        if lines:
            await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("No extra context available.")
        return

    if stage == "await_sentence":
        holo = meta.get("holo") or {}
        trap = holo.get("trap")
        culture = holo.get("cultural_note")
        sauce = holo.get("native_sauce")
        lines = []
        if sauce:
            lines.append(f"💡 {h(sauce)}")
        if culture:
            lines.append(f"🍝 {h(culture)}")
        if trap:
            lines.append(f"🪤 {h(trap)}")
        if lines:
            await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("No extra notes for this card.")
        return

    if stage == "scene_turn":
        scene = meta.get("scene") or {}
        goal = scene.get("goal")
        if goal:
            await msg.reply_text(f"🎯 Goal: {h(goal)}", parse_mode=ParseMode.HTML)
        else:
            await msg.reply_text("Stay in role and keep it natural.")
        return

    await msg.reply_text("No extra info available.")
