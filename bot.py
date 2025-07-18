import os, logging, datetime as dt, zoneinfo
from dotenv import load_dotenv
import db
import asyncio



from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import gpt_agent
import calendar_client as cal
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import Application

load_dotenv()
db.init_db()

logging.basicConfig(level=logging.INFO)

TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

notified_event_ids = set()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # print(f"Chat ID: {update.effective_chat.id}")
    text = update.message.text
    parsed = gpt_agent.parse(text)

    if not parsed:
        await update.message.reply_text("Hmm, I couldn’t process that. Try rephrasing?")
        return
    elif parsed.get("action") == "chat_fallback":
        await update.message.reply_text(parsed["reply"])
        return

    action = parsed["action"]

    try:
        if action == "create_event":
            title = parsed['title']
            date = parsed['date']
            time = parsed['time']
            duration = parsed.get('duration_minutes', 60)
            start = dt.datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=TZ)
            cal.create_event(title, start, duration)

        elif action == "reschedule_event":
            title = parsed['original_title']
            new_date = parsed['new_date']
            new_time = parsed['new_time']
            new_start = dt.datetime.fromisoformat(f"{new_date}T{new_time}").replace(tzinfo=TZ)
            cal.reschedule_event(title, new_start)

        elif action == "cancel_event":
            title = parsed['title']
            date = parsed['date']
            cal.cancel_event(title, date)

        elif action == "get_agenda":
            range = parsed['range']
            events = cal.get_agenda(range)
            if not events:
                await update.message.reply_text(f"You have no events {range}.")
                return
            lines = []
            for ev in events:
                start = ev['start'].get('dateTime', ev['start'].get('date'))
                dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
                lines.append(f"{dt_start.strftime('%A %H:%M')} • {ev['summary']}")
            await update.message.reply_text(f"🗓️ Your {range} agenda:\n" + "\n".join(lines))
            return
        
        elif action == "chat_fallback":
            await update.message.reply_text(parsed['reply'])
            return
        
        elif action == "whats_next":
            events = cal.get_current_and_next_event()
            msg = ""
            if events["current"]:
                start = events["current"]["start"]['dateTime']
                dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
                msg += f"🟢 You’re currently on: *{events['current']['summary']}* ({dt_start.strftime('%H:%M')})\n"
            if events["next"]:
                start = events["next"]["start"]['dateTime']
                dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
                msg += f"➡️ Next: *{events['next']['summary']}* at {dt_start.strftime('%H:%M')}"
            await update.message.reply_text(msg or "📭 Nothing coming up today.")

        # 🧠 Here’s the magic: use GPT's natural reply
        if "reply" in parsed:
            await update.message.reply_text(parsed["reply"])
        else:
            await update.message.reply_text(f"✅ {action.replace('_', ' ').title()} completed.")

    except ValueError as ve:
        # Handles clean, user-friendly errors like time conflicts
        await update.message.reply_text(str(ve))

    except Exception as e:
        # Handles unexpected technical errors
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
    
def send_daily_agenda(app: Application):
    loop = asyncio.get_event_loop()  # ✅ Get the loop once here

    async def job():
        from datetime import datetime
        now = datetime.now(TZ)
        events = cal.get_agenda("today")
        if not events:
            text = "🗓️ Good morning! You have no events scheduled today."
        else:
            lines = []
            for ev in events:
                start = ev['start'].get('dateTime', ev['start'].get('date'))
                dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
                lines.append(f"{dt_start.strftime('%H:%M')} • {ev['summary']}")
            text = f"🗓️ Good morning! Here's your agenda:\n" + "\n".join(lines)

        await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text)

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(job(), loop), 'cron', hour=4, minute=00, timezone=TZ)
    scheduler.start()

def send_time_reminders(app: Application):
    loop = asyncio.get_event_loop()  # ✅ Same fix here

    async def job():
        from datetime import datetime
        now = datetime.now(TZ)
        upcoming_events = cal.get_agenda("today")

        for ev in upcoming_events:
            start_str = ev['start'].get('dateTime')
            if not start_str:
                continue

            start_time = dt.datetime.fromisoformat(start_str).astimezone(TZ)
            delta = (start_time - now).total_seconds()
            
            print(f"⏳ Checking event: {ev['summary']} | starts in {delta//60:.1f} mins")

            if 9*60 <= delta <= 11*60 and not db.was_event_notified(ev['id']):
                text = f"⏰ Reminder: *{ev['summary']}* starts at {start_time.strftime('%H:%M')}"
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown")
                db.mark_event_as_notified(ev['id'])

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(job(), loop), 'interval', minutes=1)
    scheduler.start()

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ✅ Register the daily agenda scheduler
    send_daily_agenda(app)
    
    # ✅ Time-based reminders for upcoming events
    send_time_reminders(app)

    # ✅ Start polling after scheduler is set
    app.run_polling()
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm your Calendar Assistant. What would you like to do today?")

if __name__ == "__main__":
    main()
