🥋 LingoDojo — Language Practice GymTelegram Bot + Mini WebApp for Active RecallLingoDojo is a personal language practice system, designed as a "gym" for your brain rather than a traditional linear course. It focuses on forcing production and active recall rather than passive consumption.🎯 Core PhilosophyActive Recall First: Users must produce language before seeing examples.Units of Meaning: Focus on word + chunk combinations rather than isolated words.Contextual Mastery: Real usage through scenarios, register, and cultural context.Telegram-First: High-frequency, low-friction interactions via Telegram and Mini WebApps (TWA).🏗 ArchitectureThe system consists of two tightly integrated components:1. Telegram Bot (The Controller)Fast Interaction: Handles commands and sends reminders.Practice Flow: Manages the logic for active recall sessions.Gatekeeper: Launches the Mini WebApp and handles user authentication.2. Telegram Mini WebApp (The UI)Rich Interface: A minimal scaffold designed for expansion.Future Features: Visual pack browsing, interactive word cards, and progress charts.✨ Features (MVP Progress)✅ User Profiles: SQLite-backed storage for user preferences and target languages.✅ Vocabulary Packs: Modular JSON-based packs (Demo English & Italian packs included).✅ Active Learning: A /learn flow that requires users to compose sentences using specific chunks.✅ Dynamic Settings: Real-time switching of UI and Target languages.✅ Extensible Engine: Language-agnostic core capable of supporting any language pair.🛠 Tech StackComponentTechnologyLanguagePython 3.10+Bot Frameworkpython-telegram-botWeb FrameworkFastAPI + UvicornDatabaseSQLiteTunnelingngrok (for local TWA development)Data FormatJSON📂 Project StructurePlaintextLingoDojo/
├── bot/
│   ├── handlers/          # Command logic (start, learn, settings)
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
🚀 Getting Started1. PrerequisitesA Telegram Bot Token from @BotFather.Python 3.10 or higher installed.ngrok installed (for WebApp testing).2. InstallationBash# Clone the repository
git clone https://github.com/yourusername/LingoDojo.git
cd LingoDojo

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
3. ConfigurationCopy the example environment file and fill in your credentials:Bashcp .env.example .env
4. Running the ProjectYou will need two terminal windows:Terminal 1: Start the WebAppBashuvicorn webapp.app:app --reload --port 8001
Terminal 2: Start the BotBash# Start ngrok to get a public URL for the WebApp
ngrok http 8001

# Update WEBAPP_PUBLIC_URL in your .env with the ngrok https link
python -m bot.main
🗺 Roadmap[ ] SRS Integration: Spaced Repetition System logic using the /review command.[ ] Vocabulary States: Tracking words from "Learning" to "Mature."[ ] Multimedia Context: Integrating YouGlish for video-based pronunciation context.[ ] Culture Capsules: Short interactive notes on cultural nuances.🤝 ContributingContributions are welcome! Please feel free to submit a Pull Request.📄 LicenseThis project is licensed under the MIT License - see the LICENSE file for details.