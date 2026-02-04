from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from bot.services.tts_edge import tts_it
from bot.utils.telegram import get_chat_sender


async def _safe_answer(query):
    try:
        await query.answer()
    except BadRequest:
        return


async def ttscheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    await msg.reply_text("Running TTS health check…")
    try:
        audio_path = await tts_it("Ciao! Questo è un test.")
        await msg.reply_text("✅ TTS OK. Playing sample:")
        await msg.reply_voice(voice=InputFile(audio_path))
    except Exception as e:
        await msg.reply_text(
            f"❌ TTS failed ({type(e).__name__}).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Retry", callback_data="TTS|CHECK")],
            ]),
        )


async def on_tts_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    action = (query.data or "").split("|", 1)[1] if "|" in (query.data or "") else ""
    if action != "CHECK":
        return
    try:
        audio_path = await tts_it("Ciao! Questo è un test.")
        await query.message.reply_text("✅ TTS OK. Playing sample:")
        await query.message.reply_voice(voice=InputFile(audio_path))
    except Exception as e:
        await query.message.reply_text(
            f"❌ TTS failed ({type(e).__name__}).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Retry", callback_data="TTS|CHECK")],
            ]),
        )
