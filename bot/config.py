import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_PUBLIC_URL")
TARGET_LANG = "it"  # MVP: later will come from user profile

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing in .env")
if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_PUBLIC_URL missing in .env")
