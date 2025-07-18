import os, logging, datetime as dt, zoneinfo
from dotenv import load_dotenv
import db
import asyncio



from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import gpt_agent
from gpt_agent import create_reminder_message
import calendar_client as cal
from ai_agent_loop import run_ai_loop
from apscheduler.schedulers.background import BackgroundScheduler
from telegram.ext import Application

load_dotenv()
db.init_db()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

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
    loop = asyncio.get_event_loop()

    async def job():
        from datetime import datetime
        now = datetime.now(TZ)
        # 🔁 Check and send any postponed reminders
        due = db.get_due_postponed_reminders(now)
        for event_id, remind_at in due:
            await app.bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=f"🔔 Reminder: *{event_id}* is due now!",
                parse_mode="Markdown"
            )
            db.delete_postponed_reminder(event_id, remind_at)
        upcoming_events = cal.get_agenda("today")

        # Get window config from .env
        min_before = int(os.getenv("REMINDER_MIN_BEFORE", 9))
        max_before = int(os.getenv("REMINDER_MAX_BEFORE", 11))

        for ev in upcoming_events:
            start_str = ev['start'].get('dateTime')
            end_str = ev['end'].get('dateTime')
            if not start_str or not end_str:
                continue

            start_time = dt.datetime.fromisoformat(start_str).astimezone(TZ)
            end_time = dt.datetime.fromisoformat(end_str).astimezone(TZ)
            delta_to_start = (start_time - now).total_seconds()
            delta_to_end = (end_time - now).total_seconds()

            # Logging event status
            logging.info(f"⏳ Event: {ev['summary']} | Starts in {delta_to_start/60:.1f} min | Ends in {delta_to_end/60:.1f} min")

            # BEFORE event
            if min_before * 60 <= delta_to_start <= max_before * 60 and not db.was_event_notified(ev['id'], phase="before"):
                if db.is_event_blocked(os.getenv("TELEGRAM_CHAT_ID"), ev['summary'], "before"):
                    continue
                text = create_reminder_message(ev['summary'], phase="before")
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Remind me again in 10 min", callback_data=f"remind_again|{ev['id']}|{start_str}")]
                ])

                await app.bot.send_message(
                    chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )

                db.mark_event_as_notified(ev['id'], phase="before")

            # DURING event (1–3 mins into start)
            if -180 <= delta_to_start <= -60 and not db.was_event_notified(ev['id'], phase="during"):
                text = create_reminder_message(ev['summary'], phase="during")
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown")
                db.mark_event_as_notified(ev['id'], phase="during")

            # AFTER event (1–3 mins after end)
            if -180 <= delta_to_end <= -60 and not db.was_event_notified(ev['id'], phase="after"):
                text = create_reminder_message(ev['summary'], phase="after")
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown")
                db.mark_event_as_notified(ev['id'], phase="after")

    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(job(), loop), 'interval', minutes=1)
    scheduler.start()
    
def create_reminder_message(summary: str, phase: str) -> str:
    title = summary.lower()
    if "prayer" in title:
        prefix = "🙏 Gentle reminder:"
    elif "workout" in title:
        prefix = "💪 Let’s move:"
    elif "call" in title or "meeting" in title:
        prefix = "📞 Heads up:"
    else:
        prefix = "⏰ Reminder:"
    
    if phase == "before":
        return f"{prefix} *{summary}* starts soon."
    elif phase == "during":
        return f"{prefix} You're currently in *{summary}*. Stay focused!"
    elif phase == "after":
        return f"✅ Just checking — were you able to complete *{summary}*?"
    return f"{prefix} *{summary}*"

async def handle_remind_again(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, event_id, start_str = query.data.split("|")

    remind_at = dt.datetime.now(TZ) + dt.timedelta(minutes=10)
    db.save_postponed_reminder(event_id, remind_at)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔁 Reminder set again for *{event_id}* at {remind_at.strftime('%H:%M')}",
        parse_mode="Markdown"
    )
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hi! I'm your Calendar Assistant. What would you like to do today?")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
    
    async def init_job_queue(app):
    # This is just a no-op that satisfies the async requirement
        pass

    app = ApplicationBuilder().token(token).post_init(init_job_queue).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_remind_again, pattern=r"^remind_again\|"))
    app.job_queue.run_repeating(callback=lambda ctx: run_ai_loop(), interval=3600)
    
    # ✅ Register the daily agenda scheduler
    send_daily_agenda(app)
    
    # ✅ Time-based reminders for upcoming events
    send_time_reminders(app)

    # ✅ Start polling after scheduler is set
    app.run_polling()

if __name__ == "__main__":
    main()
