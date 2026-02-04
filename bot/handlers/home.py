from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.journey import journey
from bot.handlers.stats import stats
from bot.handlers.settings import settings, open_packs
from bot.handlers.addword import add_command, mywords_command


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
