# 🧠 Time Assistant — Your AI-Powered Calendar Companion

A personal Telegram bot that uses OpenAI GPT-4o and Google Calendar to help busy professionals schedule, summarise, and manage their time like a pro — using natural language.

> “What’s on next Monday morning?”
> “Cancel my 10am meeting.”
> “Schedule dinner tomorrow at 6pm.”

---

## 🚀 Features

✅ Natural language commands via Telegram
✅ GPT-4o (tool-calling) converts text to structured calendar actions
✅ Google Calendar integration (read/write)
✅ Handles:
 • 🗕️ Creating events
 • 🔁 Rescheduling
 • ❌ Cancelling
 • 🧱 Time-aware queries (e.g., “What’s next?”, “Now?”)
✅ Morning agenda sent at 9am daily
✅ Supports time ranges: `today`, `tomorrow`, `this week`, `morning`, `afternoon`, `evening`, `yesterday`, `now`, `next`

---

## 🛠️ Tech Stack

* Python 3.11+
* OpenAI GPT-4o (tool-calling)
* Google Calendar API
* Telegram Bot API (`python-telegram-bot`)
* APScheduler
* `.env` file for secrets and timezone config

---

## 📦 Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/jushotheone/time_agent.git
cd time_agent
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Create `.env` File

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
OPENAI_API_KEY=your_openai_api_key
TIMEZONE=Europe/London
GOOGLE_CREDENTIALS_JSON=client_secret.json
```

### 4. Set Up Google Calendar API

* Enable **Google Calendar API** in the Google Cloud Console
* Create **OAuth 2.0 credentials (Client ID)**
* Save the credentials as `client_secret.json`
* Run the bot once — it will launch a browser to authenticate and save `token.json`

---

## 📆 Example Commands

* `"Add school pickup tomorrow at 3pm"`
* `"What do I have this week?"`
* `"Cancel Family Dinner on Friday"`
* `"Reschedule meditation to Sunday 4am"`
* `"What was I doing yesterday at 10am?"`

---

## 🧠 How It Works

* `gpt_agent.py` – GPT-4o parsing and tool-calling logic
* `calendar_client.py` – Reads/writes events to Google Calendar
* `bot.py` – Telegram command handler
* `apscheduler` – Sends morning agenda at 9am

---

## ✅ Roadmap

* Natural language command parsing
* Morning/afternoon/evening filter support
* Current and next event awareness
* Past agenda queries
* 🗕️ Compound phrases (e.g., “next Friday afternoon”) — ✅ Implemented

---

## 🔐 Security

* Secrets like `.env` and `token.json` are excluded via `.gitignore`
* This project is intended for personal use — always review permissions before deploying

---

## 📄 License

**MIT** – Feel free to fork and build your own assistant.
This project is open-source and available under the [MIT License](LICENSE).
