from telegram import Update

def get_chat_sender(update: Update):
    """
    Returns something you can call .reply_text() on.
    Works for both:
    - normal commands (update.message)
    - callback buttons (update.callback_query.message)
    """
    if update.message:
        return update.message
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message
    return None
