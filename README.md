🥋 LingoDojo — Language Practice Gym

Telegram Bot + Mini WebApp for Active Recall

LingoDojo is a personal language practice system designed as a "gym" for your brain: it forces production and active recall instead of passive consumption.

🎯 Core Philosophy

Active Recall First — Users must produce language before seeing examples.

Units of Meaning — Focus on word + chunk combinations rather than isolated words.

Contextual Mastery — Real usage through scenarios, register, and cultural context.

Telegram-First — High-frequency, low-friction interactions via Telegram + Mini WebApp.

✨ Features (Current)

✅ User Profiles — SQLite-backed storage for user preferences and target/UI languages.

✅ Vocabulary Packs — Modular JSON-based packs (demo English & Italian packs included).

✅ Active Learning — /learn flow that requires composing sentences with chunks.

✅ SRS Reviews — /review flow with basic spaced repetition scheduling.

✅ Dynamic Settings — Change target/UI languages via /settings.

✅ Web Stats UI — Mini WebApp dashboard at `/stats`.

🛠 Tech Stack

Language: Python 3.10+

Bot Framework: python-telegram-bot

Web Framework: FastAPI + Uvicorn

Database: SQLite

Tunneling: ngrok (for local Telegram WebApp)

📂 Project Structure

LingoDojo/
├── bot/
│   ├── handlers/          # Command logic (start, learn, review, stats, settings, home)
│   ├── utils/             # Telegram helpers (shared UI utilities)
│   ├── config.py          # Environment & bot config
│   ├── db.py              # Database models & queries
│   ├── ui.py              # Inline keyboards (home menu)
│   └── main.py            # Bot entry point
├── webapp/
│   ├── app.py             # FastAPI application
│   └── telegram_auth.py   # Telegram WebApp initData verification
├── data/
│   └── packs/             # JSON vocabulary packs
├── .env.example           # Template for environment variables
├── requirements.txt       # Project dependencies
└── README.md

🚀 Getting Started (Full Setup)

1) Prerequisites

- Telegram bot token from @BotFather.
- Python 3.10+ installed.
- ngrok installed (to expose the WebApp over HTTPS).

2) Install

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

3) Configure Environment

Copy the example env file:

cp .env.example .env

Set:
- TELEGRAM_BOT_TOKEN=your_bot_token_here
- WEBAPP_PUBLIC_URL=https://your-ngrok-domain.ngrok-free.app

Note: `WEBAPP_PUBLIC_URL` is required because `bot/config.py` validates it on import.

4) Run the WebApp (Terminal 1)

uvicorn webapp.app:app --reload --port 8001

5) Expose WebApp to Telegram (Terminal 1, new tab)

ngrok http 8001

Copy the HTTPS URL from ngrok and paste it into:
- `.env` as `WEBAPP_PUBLIC_URL`
- BotFather `/setdomain` (must match exactly)

6) Run the Bot (Terminal 2)

python -m bot.main

✅ You should see: "🚀 Bot is starting..."

7) Use the Bot in Telegram

- Open your bot chat
- Send `/start`
- Use the inline menu:
  - 🧠 Learn
  - 🔁 Review
  - 📊 Stats
  - ⚙️ Settings

WebApp access:
- The Mini WebApp is served at `https://<ngrok-domain>/stats`
- It only shows real data when opened inside Telegram (initData auth)

Optional: Add a WebApp button

If you want `/start` to include a Telegram WebApp button, add a button in `bot/handlers/start.py`
using `WebAppInfo(url=f"{WEBAPP_PUBLIC_URL}/stats")`.

Troubleshooting

- WebApp shows “Invalid Telegram initData”:
  - Make sure you opened the URL inside Telegram (via a WebApp button), not a normal browser tab.
  - Confirm BotFather `/setdomain` matches your current HTTPS ngrok URL.
  - Ensure your WebApp URL is HTTPS (Telegram requires HTTPS).

- Bot crashes on startup:
  - Check `.env` and ensure both `TELEGRAM_BOT_TOKEN` and `WEBAPP_PUBLIC_URL` are set.

🗺 Roadmap

- Multimedia Context: Integrate YouGlish for pronunciation examples.
- Culture Capsules: Short interactive notes on cultural nuances.
- Smarter SRS Scheduling: More robust review intervals and ease factors.

🤝 Contributing

PRs are welcome! Open an issue or submit a PR with improvements.

📄 License

This project is licensed under the MIT License.
