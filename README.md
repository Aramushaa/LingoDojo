# LingoDojo MVP (Telegram Bot + Mini WebApp)

A personal language practice system focused on:
- Vocabulary packs (JSON -> SQLite)
- Active recall tasks via Telegram Bot
- Telegram Mini WebApp as the main UI (coming next)

## Features (current)
- /start: saves user profile in SQLite
- /stats: reads user profile from SQLite
- Packs import: loads JSON packs from `data/packs/` into SQLite
- /learn: lists packs, activate a pack, starts an active recall task
- Simple session: waits for user sentence, then responds

## Tech
- Python
- SQLite (local persistence)
- python-telegram-bot
- FastAPI + Uvicorn (Mini WebApp)
- ngrok (development tunneling)

## Setup
1) Create a Telegram bot via BotFather and get a token.
2) Create `.env` from the example:

```bash
cp .env.example .env

## Install dependencies
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt

## Run WebApp
uvicorn webapp.app:app --reload --port 8001

## Run ngrok
ngrok http 8001

## Put the ngrok https URL into .env as WEBAPP_PUBLIC_URL.

##Run bot:
python -m bot.main

#Notes

# Database file is created at data/app.db (ignored by git).

# Never commit your .env.


---

### 5) Initialize git + first push (Windows-friendly)
In the project root:

```bash
git init
git add .
git commit -m "MVP: bot + sqlite + packs import + learn flow"
