# ===========================
# agent_brain/scheduler.py
# ===========================
import os
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

import db
import calendar_client as cal
from gpt_agent import create_reminder_message

TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))

def send_daily_agenda(app):
    loop = asyncio.get_event_loop()

    async def job():
        now = dt.datetime.now(TZ)
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

    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(job(), loop), 'cron', hour=4, minute=0, timezone=TZ)
    scheduler.start()

def send_time_reminders(app):
    loop = asyncio.get_event_loop()

    async def job():
        now = dt.datetime.now(TZ)
        due = db.get_due_postponed_reminders(now)
        for event_id, remind_at in due:
            await app.bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=f"🔔 Reminder: *{event_id}* is due now!",
                parse_mode="Markdown"
            )
            db.delete_postponed_reminder(event_id, remind_at)

        upcoming_events = cal.get_agenda("today")
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

            # BEFORE
            if min_before * 60 <= delta_to_start <= max_before * 60 and not db.was_event_notified(ev['id'], "before"):
                if db.is_event_blocked(os.getenv("TELEGRAM_CHAT_ID"), ev['summary'], "before"):
                    continue
                text = create_reminder_message(ev['summary'], phase="before")
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔁 Remind me again in 10 min", callback_data=f"remind_again|{ev['id']}|{start_str}")]
                ])
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown", reply_markup=keyboard)
                db.mark_event_as_notified(ev['id'], "before")

            # DURING
            if -180 <= delta_to_start <= -60 and not db.was_event_notified(ev['id'], "during"):
                text = create_reminder_message(ev['summary'], phase="during")
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown")
                db.mark_event_as_notified(ev['id'], "during")

            # AFTER
            if -180 <= delta_to_end <= -60 and not db.was_event_notified(ev['id'], "after"):
                text = create_reminder_message(ev['summary'], phase="after")
                await app.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=text, parse_mode="Markdown")
                db.mark_event_as_notified(ev['id'], "after")

    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(job(), loop), 'interval', minutes=1)
    scheduler.start()

async def handle_remind_again(update, context):
    query = update.callback_query
    await query.answer()
    _, event_id, _ = query.data.split("|")
    remind_at = dt.datetime.now(TZ) + dt.timedelta(minutes=10)
    db.save_postponed_reminder(event_id, remind_at)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔁 Reminder set again for *{event_id}* at {remind_at.strftime('%H:%M')}",
        parse_mode="Markdown"
    )
    
def propose_adjustment(drift):
    now = dt.datetime.now(TZ)
    fallback_time = now + dt.timedelta(hours=2)
    fallback_start = fallback_time.replace(minute=0, second=0, microsecond=0)

    return {
        "action": "reschedule_event",
        "new_time": fallback_start.isoformat(),
        "reason": f"missed earlier block for {drift['summary']}"
    }