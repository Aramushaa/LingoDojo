from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from bot.db import get_connection,get_due_count, get_status_counts, get_user_level, get_user_persona, get_practice_stats, get_user_journey_progress, get_pack_info, get_story_progress
from bot.storyline import STORY_ARCS




def format_pretty_date(iso_str: str) -> str:
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%d %b %Y, %H:%M")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name, created_at FROM users WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    due_today = get_due_count(user.id)
    counts = get_status_counts(user.id)

    new_count = counts["new"]
    learning_count = counts["learning"]
    mature_count = counts["mature"]
    conn.close()

    if row is None:
        await update.effective_message.reply_text("No profile found. Use /start first.")
        return

    first_name, created_at_iso = row
    pretty = format_pretty_date(created_at_iso)

    level = get_user_level(user.id)
    persona = get_user_persona(user.id) or (None, None, None)
    p_name, p_city, p_role = persona
    practice = get_practice_stats(user.id)
    journey_row = get_user_journey_progress(user.id)
    journey_pack = journey_row[0] if journey_row else None
    journey_title = None
    if journey_pack:
        info = get_pack_info(journey_pack)
        journey_title = info[2] if info and len(info) > 2 else journey_pack

    persona_line = "🎭 Alter-Ego: not set"
    if p_name or p_city or p_role:
        parts = [p_name or "Unknown", p_role or "Role", p_city or "City"]
        persona_line = f"🎭 Alter-Ego: {parts[0]} — {parts[1]} in {parts[2]}"

    journey_line = "🧭 Journey: not started"
    if journey_title:
        journey_line = f"🧭 Journey: {journey_title}"

    arc_idx, beat_idx = get_story_progress(user.id)
    story_line = None
    if (arc_idx > 0 or beat_idx > 0) and 0 <= arc_idx < len(STORY_ARCS):
        arc = STORY_ARCS[arc_idx]
        beats = arc.get("beats") or []
        if beats:
            last_idx = min(max(beat_idx - 1, 0), len(beats) - 1)
            story_line = f"🕵️ Story so far: {beats[last_idx]}"

    await update.effective_message.reply_text(
    f"📊 Your Stats\n"
    f"👤 Name: {first_name}\n"
    f"🆔 User ID: {user.id}\n"
    f"📅 Joined: {pretty}\n"
    f"🎯 Level: {level}\n\n"
    f"{persona_line}\n"
    f"{journey_line}\n"
    f"{story_line + '\n' if story_line else ''}\n"
    f"🔥 Streak: {practice['current_streak']} days (best {practice['longest_streak']})\n"
    f"📅 Last practice: {practice['last_practice_date'] or '-'}\n"
    f"✅ Correct: {practice['total_correct']}  ❌ Wrong: {practice['total_wrong']}\n\n"
    f"🧠 SRS\n"
    f"🔁 Due today: {due_today}\n"
    f"🟡 Learning: {learning_count}\n"
    f"🟢 Mature: {mature_count}\n"
    f"⚪ New: {new_count}\n\n"
    f"Next: /review"
    )

