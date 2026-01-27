from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.learn import learn
from bot.handlers.review import review
from bot.handlers.stats import stats
from bot.handlers.settings import settings


async def on_home_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Make the chat feel "app-like": remove the menu message if you want
    # await query.message.delete()

    if data == "home:learn":
        await learn(update, context)

    elif data == "home:review":
        await review(update, context)

    elif data == "home:stats":
        await stats(update, context)

    elif data == "home:settings":
        await settings(update, context)

    else:
        await query.message.reply_text("Unknown action.")
