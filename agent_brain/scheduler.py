# ===========================
# agent_brain/scheduler.py
# ===========================
#
# --- NEW imports for Workflow #0 backbone ---
from agent_brain import observer  # will expose observer.tick(now, app)
from agent_brain import fsm       # types only; logic handled by observer
import feature_flags as ff

# Use a single APScheduler across this module
from apscheduler.schedulers.background import BackgroundScheduler
SCHED = BackgroundScheduler()

import os
import asyncio
import datetime as dt
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

import db
import calendar_client as cal
from gpt_agent import create_reminder_message

# --- NEW: gating for quiet hours / Sabbath / OOO ---
def _is_quiet(now: dt.datetime) -> bool:
    quiet = os.getenv("QUIET_HOURS", "22:00-06:00")
    start_s, end_s = quiet.split("-")
    start_h, start_m = map(int, start_s.split(":"))
    end_h, end_m = map(int, end_s.split(":"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if start <= end:
        return start <= now <= end
    # wraps past midnight
    return now >= start or now <= end

def _is_sabbath(now: dt.datetime) -> bool:
    day = os.getenv("SABBATH_DAY", "").strip().lower()
    if not day:
        return False
    # map names -> weekday (Mon=0..Sun=6)
    names = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    try:
        return now.weekday() == names.index(day)
    except ValueError:
        return False

def _gated(now: dt.datetime) -> bool:
    """Return True if we should suppress pings/escalations right now."""
    if _is_quiet(now):
        return True
    if _is_sabbath(now):
        return True
    return False

# --- NEW: schedule a one-off midpoint tick for a segment ---
def schedule_midpoint_tick(seg_id: str, start_at: dt.datetime, end_at: dt.datetime):
    duration = (end_at - start_at).total_seconds()
    if duration <= 0:
        return
    mid_at = start_at + dt.timedelta(seconds=duration/2)
    def _mid_cb():
        now = dt.datetime.now(TZ)
        if _gated(now):
            return
        # delegate the heavy FSM logic to observer
        try:
            observer.emit_midpoint(seg_id=seg_id, now=now)
        except AttributeError:
            # Fallback: if emit_midpoint not yet implemented, call generic tick
            observer.tick(now=now)
    SCHED.add_job(_mid_cb, 'date', run_date=mid_at)

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

# --- NEW: Live Session loop jobs (Workflow #0) ---
def start_live_session_jobs(app):
    """
    1) every_minute: drive the FSM via observer.tick(now)
    2) reconcile_30m: ensure segments mirror calendar and insert buffers
    """
    loop = asyncio.get_event_loop()

    async def _tick_async():
        now = dt.datetime.now(TZ)
        if _gated(now):
            # still allow observer to mark completions silently if desired
            observer.tick(now=now, gated=True)
            return
        observer.tick(now=now, app=app)

    def _tick_job():
        asyncio.run_coroutine_threadsafe(_tick_async(), loop)

    def _reconcile_job():
        try:
            reconcile_segments_with_calendar(app=app)
        except Exception as e:
            # avoid crashing the scheduler
            print(f"[reconcile] error: {e}")

    # kick off jobs once (idempotent start)
    if not SCHED.running:
        SCHED.start()
    SCHED.add_job(_tick_job, 'interval', minutes=1, id='wf0_tick', replace_existing=True, timezone=TZ)
    SCHED.add_job(_reconcile_job, 'interval', minutes=30, id='wf0_reconcile', replace_existing=True, timezone=TZ)

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

# --- NEW: reconcile calendar ↔ segments; add buffers; respect rigidity ---
def reconcile_segments_with_calendar(app=None):
    now = dt.datetime.now(TZ)
    events = cal.get_agenda("today") or []
    # Build simple segment views from events
    segs_from_cal = []
    for ev in events:
        start_str = ev['start'].get('dateTime')
        end_str = ev['end'].get('dateTime')
        if not start_str or not end_str:
            continue
        start_at = dt.datetime.fromisoformat(start_str).astimezone(TZ)
        end_at = dt.datetime.fromisoformat(end_str).astimezone(TZ)
        # Rigidity can be embedded in extendedProperties; default firm for meetings, soft for others
        rigidity = 'firm' if ev.get('attendees') or ev.get('hangoutLink') else 'soft'
        segs_from_cal.append({
            "id": ev['id'],
            "type": "scheduled",
            "rigidity": rigidity,
            "start_at": start_at,
            "end_at": end_at,
            "tone_at_start": "gentle",
        })

    # Upsert into DB and schedule midpoint ticks
    for s in segs_from_cal:
        db.insert_segment({
            "id": s["id"],
            "type": s["type"],
            "rigidity": s["rigidity"],
            "start_at": s["start_at"],
            "end_at": s["end_at"],
            "tone_at_start": s["tone_at_start"],
        })
        try:
            schedule_midpoint_tick(seg_id=s["id"], start_at=s["start_at"], end_at=s["end_at"])
        except Exception as e:
            print(f"[midpoint] could not schedule midpoint for {s['id']}: {e}")

    # Add 5–10m transition buffers between adjacent soft/free segments (no mutation of 'hard')
    # NOTE: This is a minimal placeholder; a fuller version should read back from DB,
    # detect collisions, and write buffer minutes into segments.travel_buffer_min.
    # Left intentionally simple to avoid unintended calendar edits here.

    # Detect free gaps and (optionally) seed Free Time Windows via observer
    try:
        observer.seed_free_time_windows(now=now)
    except AttributeError:
        # if not implemented yet, skip
        pass

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

# --- NEW: convenience initializer ---
def start_all_schedulers(app):
    """
    Keep existing reminder jobs, add Workflow #0 loop jobs.
    Call this from app/main startup instead of calling each individually.
    """
    send_daily_agenda(app)
    send_time_reminders(app)
    start_live_session_jobs(app)