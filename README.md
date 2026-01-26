🥋 LingoDojo — Language Practice Gym

Telegram Bot + Mini WebApp for Active Recall

LingoDojo is a personal language practice system, designed as a "gym" for your brain rather than a traditional linear course. It focuses on forcing production and active recall rather than passive consumption.

🎯 Core Philosophy

Active Recall First: Users must produce language before seeing examples.

Units of Meaning: Focus on word + chunk combinations rather than isolated words.

Contextual Mastery: Real usage through scenarios, register, and cultural context.

Telegram-First: High-frequency, low-friction interactions via Telegram and Mini WebApps (TWA).

🏗 Architecture

The system consists of two tightly integrated components:

1. Telegram Bot (The Controller)

Fast Interaction: Handles commands and sends reminders.

Practice Flow: Manages the logic for active recall sessions.

Gatekeeper: Launches the Mini WebApp and handles user authentication.

2. Telegram Mini WebApp (The UI)

Rich Interface: A visual dashboard for deeper interactions.

Current State: Minimal scaffold ready for expansion into packs and stats visualization.

✨ Features (MVP Progress)

✅ User Profiles: SQLite-backed storage for user preferences and target languages.

✅ Vocabulary Packs: Modular JSON-based packs (Demo English & Italian packs included).

✅ Active Learning: A /learn flow that requires users to compose sentences using specific chunks.

✅ Dynamic Settings: Real-time switching of UI and Target languages via /settings.

✅ Extensible Engine: Language-agnostic core capable of supporting any language pair.

🛠 Tech Stack

Component

Technology

Language

Python 3.10+

Bot Framework

python-telegram-bot

Web Framework

FastAPI + Uvicorn

Database

SQLite

Tunneling

ngrok (for local development)

Data Format

JSON

📂 Project Structure

LingoDojo/
├── bot/
│   ├── handlers/          # Command logic (start, learn, settings, etc.)
│   ├── config.py          # Environment & Bot config
│   ├── db.py              # Database models & queries
│   └── main.py            # Bot entry point
├── webapp/
│   └── app.py             # FastAPI application
├── data/
│   └── packs/             # JSON vocabulary packs
├── .env.example           # Template for environment variables
├── requirements.txt       # Project dependencies
└── README.md


🚀 Getting Started

1. Prerequisites

A Telegram Bot Token from @BotFather.

Python 3.10 or higher installed.

ngrok installed (to expose your local WebApp to Telegram).

2. Installation

# Clone the repository
git clone [https://github.com/yourusername/LingoDojo.git](https://github.com/yourusername/LingoDojo.git)
cd LingoDojo

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt


3. Configuration

Copy the example environment file:

cp .env.example .env


Open .env and add your BOT_TOKEN.

4. Running the Project

You will need two terminal windows:

Terminal 1: Start the WebApp & Tunnel

# Start the FastAPI server
uvicorn webapp.app:app --reload --port 8001

# In a separate prompt, start ngrok
ngrok http 8001


Note: Copy the https://... URL from ngrok and paste it as WEBAPP_PUBLIC_URL in your .env.

Terminal 2: Start the Bot

python -m bot.main


🗺 Roadmap

[ ] SRS Integration: Spaced Repetition System logic using a /review command.

[ ] Vocabulary States: Tracking words from "Learning" to "Mature."

[ ] Multimedia Context: Integrating YouGlish for video-based pronunciation context.

[ ] Culture Capsules: Short interactive notes on cultural nuances.

🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

📄 License

This project is licensed under the MIT License.