import os, logging, datetime as dt, zoneinfo
from dotenv import load_dotenv
import db
import asyncio



from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import gpt_agent
from agent_brain.scheduler import (
    send_daily_agenda,
    send_time_reminders,
    handle_remind_again
)
import calendar_client as cal
from ai_agent_loop import run_ai_loop
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import Application
from agent_brain.weekly_audit import send_weekly_audit
from agent_brain.evening_review import run_evening_review
from calendar_client import rename_event
from agent_brain.actions import handle_action

load_dotenv()
db.init_db()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

notified_event_ids = set()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parsed = gpt_agent.parse(text)

    if not parsed:
        await update.message.reply_text("Hmm, I couldn’t process that. Try rephrasing?")
        return

    try:
        await handle_action(parsed, update, context)
    except ValueError as ve:
        await update.message.reply_text(str(ve))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Something went wrong while processing: {e}")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = cal.list_today()
    if not events:
        await update.message.reply_text("You have no events today.")
        return
    lines = []
    for ev in events:
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        lines.append(f"{dt_start.strftime('%H:%M')} • {ev['summary']}")
    await update.message.reply_text("\n".join(lines))
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm your Calendar Assistant. What would you like to do today?")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    
    async def init_job_queue(app):
        # No-op async init
        pass

    app = ApplicationBuilder().token(token).post_init(init_job_queue).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_remind_again, pattern=r"^remind_again\|"))
    app.job_queue.run_repeating(callback=lambda ctx: run_ai_loop(), interval=3600)

    # ✅ Daily Agenda (early morning)
    send_daily_agenda(app)

    # ✅ Time-sensitive event reminders
    send_time_reminders(app)

    # 🧠 Weekly Audit (Sunday 21:00)
    from agent_brain.weekly_audit import send_weekly_audit
    app.job_queue.run_daily(
        callback=lambda ctx: asyncio.create_task(send_weekly_audit()),
        time=dt.time(hour=21, minute=0, tzinfo=TZ),
        days=(6,)  # Sunday
    )

    # 🌙 Evening Review (Every day at 21:30)
    from agent_brain.evening_review import run_evening_review
    app.job_queue.run_daily(
        callback=lambda ctx: asyncio.create_task(run_evening_review()),
        time=dt.time(hour=21, minute=30, tzinfo=TZ)
    )

    app.run_polling()
    
if __name__ == "__main__":
    main()
