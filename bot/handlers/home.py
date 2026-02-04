from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.journey import journey
from bot.handlers.stats import stats
from bot.handlers.settings import settings, open_packs
from bot.handlers.addword import add_command, mywords_command
from bot.utils.telegram import get_chat_sender
from bot.ui import home_keyboard


async def on_home_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Make the chat feel "app-like": remove the menu message if you want
    # await query.message.delete()

    if data == "home:journey":
        await journey(update, context)

    elif data == "home:packs":
        await open_packs(update, context)

    elif data == "home:add":
        await add_command(update, context)

    elif data == "home:mywords":
        await mywords_command(update, context)

    elif data == "home:progress":
        await stats(update, context)

    elif data == "home:settings":
        await settings(update, context)

    else:
        await query.message.reply_text("Unknown action.")


async def home_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_chat_sender(update)
    await msg.reply_text("🏠 <b>Home</b>\nChoose where to go next:", reply_markup=home_keyboard(), parse_mode="HTML")
