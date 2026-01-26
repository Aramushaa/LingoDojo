import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes,CallbackQueryHandler, MessageHandler, filters

from datetime import datetime, timezone
from db import init_db, get_connection, import_packs_from_folder, list_packs, activate_pack, get_user_active_packs, pick_one_item_from_pack, set_session, get_session, clear_session, get_item_by_id

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_PUBLIC_URL")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Check your .env file location and value.")

if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_PUBLIC_URL is missing. Put your ngrok https link in .env.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, created_at) VALUES (?, ?, ?)",
        (user.id, user.first_name, datetime.now(timezone.utc).isoformat())
    )

    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton(
            "🚀 Open Mini WebApp",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]

    await update.message.reply_text(
        f"Welcome {user.first_name}! 👋\nYour profile is saved.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT first_name, created_at FROM users WHERE user_id = ?",
        (user.id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row is None:
        await update.message.reply_text("No profile found. Use /start first.")
        return

    first_name, created_at_iso = row
    created_at_dt = datetime.fromisoformat(created_at_iso)
    pretty_date = created_at_dt.strftime("%d %b %Y")


    text = (
        f"📊 Your Stats\n"
        f"👤 Name: {first_name}\n"
        f"🆔 User ID: {user.id}\n"
        f"📅 Joined: {pretty_date}\n"
    )

    await update.message.reply_text(text)


TARGET_LANG = "it"  # MVP: fixed; later comes from user profile

async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    packs = list_packs(TARGET_LANG)

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
    data = query.data  # like: "PACK|it_demo_a1_core"
    _, pack_id = data.split("|", 1)

    activate_pack(user.id, pack_id)

    # Start a learn task immediately: pick one item
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
        return  # ignore normal chat for now

    mode, item_id, stage = session
    if mode == "learn" and stage == "await_sentence" and item_id is not None:
        item = get_item_by_id(item_id)
        if not item:
            clear_session(user.id)
            await update.message.reply_text("Session error. Try /learn again.")
            return

        _, term, chunk, translation_en, note = item

        # MVP feedback (no AI yet): just confirm + give a better example
        reply = (
            f"✅ Nice! You used the target.\n\n"
            f"Your sentence:\n“{text}”\n\n"
            f"Here’s a clean native-ish example:\n"
            f"• *Oggi vorrei prendere un caffè.*\n\n"
            f"Next: type /learn to pick another pack or task."
        )

        clear_session(user.id)
        await update.message.reply_text(reply, parse_mode="Markdown")



def main():
    print("🚀 Bot is starting...")
    print("🌐 WEBAPP_URL =", WEBAPP_URL)

    init_db()
    import_packs_from_folder()


    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("learn", learn))
    app.add_handler(CallbackQueryHandler(on_pack_button, pattern=r"^PACK\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))




    print("✅ Bot is polling now. Go to Telegram and send /start")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
