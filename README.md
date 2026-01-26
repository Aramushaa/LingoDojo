# LingoDojo — Language Practice Gym (Telegram Bot + Mini WebApp)

LingoDojo is a **personal language practice system**, not a traditional course app.

It focuses on:
- vocabulary as *units of meaning* (word + chunk)
- active recall (forced production)
- spaced repetition (SRS)
- real usage (scenarios, register, culture)
- Telegram-first UX with a Mini WebApp as the main UI

---

## Architecture

The system has **two main parts**:

### 1) Telegram Bot (Controller)
- Fast interaction and commands
- Launches the Mini WebApp
- Manages practice flow and reminders

Commands implemented so far:
- `/start` – create user profile
- `/stats` – show stored user info
- `/learn` – select packs and start active recall
- `/settings` – change target language and UI language

### 2) Telegram Mini WebApp (UI)
- Currently a minimal scaffold
- Will host:
  - packs
  - word cards
  - stats
  - video context
  - interactive exercises

---

## Core Concepts

- **Language-agnostic core**  
  The engine works for any language.  
  Content (packs) is language-specific.

- **Active recall first**  
  The user must produce language before seeing examples.

- **Packs, not random words**  
  Ready-made vocabulary packs are imported from JSON files.

---

## Current Features (MVP Progress)

### ✅ User Profile
- Stored in SQLite
- Fields:
  - Telegram user id
  - name
  - created_at
  - target language
  - UI language

### ✅ Vocabulary Packs
- Imported from `data/packs/*.json`
- Stored in SQLite
- Italian and English demo packs included

### ✅ Learning Flow
- `/learn` lists available packs for the selected target language
- User activates a pack
- Bot selects a random item
- User must write a sentence using the chunk
- Bot gives feedback and a native-like example

### ✅ Settings
- `/settings` lets user change:
  - 🌍 target language
  - 🗣 UI language

---

## Tech Stack

- **Backend:** Python
- **Telegram Bot:** python-telegram-bot
- **Database:** SQLite (local, file-based)
- **WebApp:** FastAPI + Uvicorn
- **Tunneling (dev):** ngrok
- **Data format:** JSON packs

---

## Project Structure

LingoDojo/
bot/
main.py
config.py
db.py
handlers/
start.py
stats.py
learn.py
settings.py
webapp/
app.py
data/
packs/
it_demo.json
en_demo.json
app.db (ignored by git)
.env.example
.gitignore
requirements.txt
README.md


---

## Setup (Local Development)

1) Create a Telegram bot via BotFather and get a token.

2) Create `.env` from the example:
```bash
cp .env.example .env


Install dependencies:

python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt


Run the Mini WebApp:

uvicorn webapp.app:app --reload --port 8001


Run ngrok:

ngrok http 8001


Put the HTTPS URL into .env as WEBAPP_PUBLIC_URL.

Run the bot:

python -m bot.main

Roadmap (Next Steps)

Spaced Repetition System (SRS) with /review

User vocabulary tracking (learning / mature states)

Mini WebApp pages: Packs, Word Card, Stats

Video context with YouGlish

Scenarios and culture capsules

Philosophy

This project is built as a learning gym, not a course:

short

active

repeatable

personalized


---

## Git commit for README update
```bash
git add README.md
git commit -m "Update README with current MVP architecture and features"
git push