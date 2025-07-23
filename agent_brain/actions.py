# agent_brain/actions.py
import os
import datetime as dt
import calendar_client as cal
from calendar_client import rename_event
from zoneinfo import ZoneInfo
from agent_brain import messages as msg
from agent_brain.respond import respond_with_brain

TZ = ZoneInfo(os.getenv("TIMEZONE", "UTC"))

# -- Core event actions --
def create_event(parsed):
    title = parsed['title']
    date = parsed['date']
    time = parsed['time']
    duration = parsed.get('duration_minutes', 60)
    start = dt.datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=TZ)
    cal.create_event(title, start, duration)

def reschedule_event(parsed):
    new_start = dt.datetime.fromisoformat(f"{parsed['new_date']}T{parsed['new_time']}").replace(tzinfo=TZ)
    cal.reschedule_event(parsed['original_title'], new_start)

def cancel_event(parsed):
    cal.cancel_event(parsed['title'], parsed['date'])

def extend_event(parsed):
    cal.extend_event(parsed['title'], parsed['additional_minutes'])

def rename(parsed):
    rename_event(parsed['original_title'], parsed['new_title'], parsed['date'])

def describe_event(parsed):
    return cal.describe_event(parsed['title'], parsed['date'])

def get_event_duration(parsed):
    return cal.get_event_duration(parsed['title'], parsed['date'])

def list_attendees(parsed):
    return cal.list_attendees(parsed['title'], parsed['date'])

def log_event_action(parsed):
    cal.log_event_action(parsed['event_id'], parsed['action'], parsed['timestamp'])

# -- Time and agenda related --
def get_agenda(parsed):
    return cal.get_agenda(parsed['range'])

def get_time_until_next_event():
    return cal.get_time_until_next_event()

def whats_next():
    return cal.get_current_and_next_event()

def list_today():
    return cal.list_today()

# -- Optional reply composition helpers (for bot.py to call) --
def format_agenda_reply(events, label: str) -> str:
    if not events or not events[0]:
        return msg.no_agenda(label)
    lines = []
    for ev in events:
        if not ev:
            continue
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        lines.append(f"{dt_start.strftime('%A %H:%M')} • {ev['summary']}")
    return f"🗓️ Your {label} agenda:\n" + "\n".join(lines)

def format_whats_next_reply(events: dict) -> str:
    msg = ""
    if events.get("current"):
        start = events['current']['start']['dateTime']
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        msg += f"🟢 You’re currently on: *{events['current']['summary']}* ({dt_start.strftime('%H:%M')})\n"
    if events.get("next"):
        start = events['next']['start']['dateTime']
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        msg += f"➡️ Next: *{events['next']['summary']}* at {dt_start.strftime('%H:%M')}"
    return msg or "📭 Nothing coming up today."

def format_event_description(details: dict) -> str:
    if not details:
        return "I couldn’t find that event."
    lines = [
        f"📝 *{details.get('summary')}*",
        f"📅 {details.get('start')} — {details.get('end')}",
        f"📍 Location: {details.get('location', 'N/A')}",
        f"📓 Description: {details.get('description', 'N/A')}",
        f"🔄 Recurrence: {details.get('recurrence', 'None')}",
        f"👥 Attendees: {', '.join(details.get('attendees', [])) or 'None'}",
    ]
    return "\n".join(lines)

# --- Main handler ---
async def handle_action(parsed, update, context):
    action = parsed.get("action")

    if action == "create_event":
        start = dt.datetime.fromisoformat(f"{parsed['date']}T{parsed['time']}").replace(tzinfo=TZ)
        event = cal.create_event(
            parsed['title'],
            start,
            parsed.get('duration_minutes', 60),
            parsed.get('attendees'),
            parsed.get('recurrence')
        )
        summary = format_event_description(event)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "reschedule_event":
        new_start = dt.datetime.fromisoformat(f"{parsed['new_date']}T{parsed['new_time']}").replace(tzinfo=TZ)
        updated = cal.reschedule_event(parsed['original_title'], new_start)
        summary = format_event_description(updated)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "cancel_event":
        cancel_event(parsed)
        summary = f"❌ Event '{parsed['title']}' on {parsed['date']} cancelled."
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "extend_event":
        # Perform extend, then refetch the updated event for metadata-rich summary
        cal.extend_event(parsed['title'], parsed['additional_minutes'])
        updated = cal.describe_event(parsed['title'], parsed['date'])
        summary = format_event_description(updated)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "rename_event":
        updated = rename_event(parsed['original_title'], parsed['new_title'], parsed['date'])
        summary = format_event_description(updated)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "describe_event":
        details = describe_event(parsed)
        summary = format_event_description(details)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_event_duration":
        duration = get_event_duration(parsed)
        summary = f"🕒 Duration of '{parsed['title']}': {duration} minutes"
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "list_attendees":
        attendees = list_attendees(parsed)
        summary = f"👥 Attendees for '{parsed['title']}': {', '.join(attendees) or 'None'}"
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_agenda":
        events = get_agenda(parsed)
        summary = format_agenda_reply(events, parsed['range'])
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_time_until_next_event":
        result = get_time_until_next_event()
        summary = f"⏳ Time until next event: {result}"
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "whats_next":
        events = whats_next()
        summary = format_whats_next_reply(events)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "log_event_action":
        log_event_action(parsed)
        return
    
    elif action == "whats_now":
        events = whats_next()
        summary = format_whats_next_reply(events)
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "chat_fallback":
        await respond_with_brain(update, context, parsed)