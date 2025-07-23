import os
import datetime as dt
import zoneinfo
from typing import List, Dict, Optional, Union

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import json

from dateutil.parser import isoparse
import dateparser

SCOPES = ['https://www.googleapis.com/auth/calendar']
TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

def _get_creds() -> Credentials:
    import base64
    creds = None
    token_path = 'token.json'
    creds_path = 'client_secret.json'

    # ✅ Recreate client_secret.json from base64 env var
    if os.getenv("GOOGLE_CREDENTIALS_JSON") and not os.path.exists(creds_path):
        with open(creds_path, "wb") as f:
            f.write(base64.b64decode(os.environ["GOOGLE_CREDENTIALS_JSON"]))

    # ✅ Recreate token.json from base64 env var (Railway-safe)
    if os.getenv("GOOGLE_TOKEN_JSON") and not os.path.exists(token_path):
        with open(token_path, "wb") as f:
            f.write(base64.b64decode(os.environ["GOOGLE_TOKEN_JSON"]))

    # Load credentials from token file
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Refresh or authenticate if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This will not work on Railway; fallback in dev only
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_console()

        # Save refreshed token (optional if Railway is stateless)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return creds

def _service():
    creds = _get_creds()
    return build('calendar', 'v3', credentials=creds)

def create_event(title: str, start: dt.datetime, duration_minutes: int = 60, attendees: Optional[List[str]] = None, recurrence: Optional[str] = None) -> Dict:
    service = _service()
    end = start + dt.timedelta(minutes=duration_minutes)

    def _is_conflicting(start: dt.datetime, end: dt.datetime) -> bool:
        overlapping = service.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True
        ).execute().get('items', [])
        return len(overlapping) > 0

    if _is_conflicting(start, end):
        raise ValueError("⛔ Conflict detected: Another event exists during this time.")

    event_body = {
        'summary': title,
        'start': {'dateTime': start.isoformat(), 'timeZone': str(TZ)},
        'end': {'dateTime': end.isoformat(), 'timeZone': str(TZ)},
        'reminders': {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 15}]
        }
    }
    if attendees:
        event_body['attendees'] = [{'email': email} for email in attendees]
    if recurrence:
        event_body['recurrence'] = [recurrence]

    event = service.events().insert(calendarId='primary', body=event_body).execute()
    log_event_action("create", event)
    return event

def list_today() -> List[Dict]:
    service = _service()
    now = dt.datetime.now(TZ)
    start = dt.datetime(now.year, now.month, now.day, tzinfo=TZ)
    end = start + dt.timedelta(days=1)
    return service.events().list(
        calendarId='primary',
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

def reschedule_event(original_title: str, new_start: dt.datetime) -> Optional[Dict]:
    service = _service()
    now = dt.datetime.utcnow().isoformat() + 'Z'
    events = service.events().list(
        calendarId='primary',
        q=original_title,
        timeMin=now,
        maxResults=1,
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

    if not events:
        return None

    event = events[0]
    event['start'] = {'dateTime': new_start.isoformat(), 'timeZone': str(TZ)}
    event['end'] = {'dateTime': (new_start + dt.timedelta(minutes=60)).isoformat(), 'timeZone': str(TZ)}

    updated_event = service.events().update(calendarId='primary', eventId=event['id'], body=event).execute()
    log_event_action("update", updated_event)
    return updated_event

def cancel_event(title: str, date: str) -> bool:
    service = _service()
    time_min = f"{date}T00:00:00Z"
    time_max = f"{date}T23:59:59Z"
    events = service.events().list(
        calendarId='primary',
        q=title,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        maxResults=1
    ).execute().get('items', [])

    if not events:
        return False

    event_id = events[0]['id']
    service.events().delete(calendarId='primary', eventId=event_id).execute()
    log_event_action("delete", events[0])
    return True

def parse_compound_range(phrase: str) -> Optional[Dict[str, dt.datetime]]:
    now = dt.datetime.now(TZ)
    phrase = phrase.lower()

    # Extract known parts
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    times = {
        "morning": (4, 12),
        "afternoon": (12, 17),
        "evening": (17, 22),
    }

    day_match = next((d for d in days if d in phrase), None)
    time_match = next((t for t in times if t in phrase), None)

    if not day_match or not time_match:
        # Fallback to loose natural time parsing
        dt_obj = parse_loose_natural_time(phrase)
        if dt_obj:
            return {"start": dt_obj, "end": dt_obj + dt.timedelta(hours=1)}
        return None

    # Find target date
    target_day_index = days.index(day_match)
    current_day_index = now.weekday()
    delta = (target_day_index - current_day_index) % 7
    if "next" in phrase:
        delta += 7 if delta == 0 else 0
    target_date = (now + dt.timedelta(days=delta)).replace(hour=0, minute=0, second=0)

    # Build datetime range
    start_hour, end_hour = times[time_match]
    start = target_date.replace(hour=start_hour)
    end = target_date.replace(hour=end_hour)

    return {"start": start, "end": end}

def parse_loose_natural_time(phrase: str) -> Optional[dt.datetime]:
    dt_obj = dateparser.parse(phrase, settings={'TIMEZONE': str(TZ), 'RETURN_AS_TIMEZONE_AWARE': True})
    return dt_obj

def get_agenda(range_: str) -> List[Dict]:
    service = _service()
    range_ = range_.lower()
    now = dt.datetime.now(TZ)

    if range_ == "today":
        start = now.replace(hour=0, minute=0, second=0)
        end = start + dt.timedelta(days=1)
    elif range_ == "tomorrow":
        start = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end = start + dt.timedelta(days=1)
    elif range_ == "this week":
        start = now - dt.timedelta(days=now.weekday())  # Monday
        end = start + dt.timedelta(days=7)
    elif range_ == "morning":
        start = now.replace(hour=4, minute=0)
        end = now.replace(hour=12, minute=0)
    elif range_ == "afternoon":
        start = now.replace(hour=12, minute=0)
        end = now.replace(hour=17, minute=0)
    elif range_ == "evening":
        start = now.replace(hour=17, minute=0)
        end = now.replace(hour=22, minute=0)
    elif range_ == "yesterday":
        start = (now - dt.timedelta(days=1)).replace(hour=0, minute=0)
        end = start + dt.timedelta(days=1)
    elif range_ == "now":
        current = get_current_and_next_event().get("current")
        return [current] if current else []

    elif range_ == "next":
        events = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            maxResults=1,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])
        return events
    else:
        compound = parse_compound_range(range_)
        if compound:
            return service.events().list(
                calendarId='primary',
                timeMin=compound["start"].isoformat(),
                timeMax=compound["end"].isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute().get('items', [])
        return [{"summary": "I couldn't find anything for that range."}]

    return service.events().list(
        calendarId='primary',
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

def describe_event(title: str, date: str) -> Optional[Dict]:
    service = _service()
    time_min = f"{date}T00:00:00Z"
    time_max = f"{date}T23:59:59Z"
    events = service.events().list(
        calendarId='primary',
        q=title,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        maxResults=1
    ).execute().get('items', [])
    return events[0] if events else None

def list_attendees(title: str, date: str) -> List[str]:
    event = describe_event(title, date)
    if not event or 'attendees' not in event:
        return []
    return [a['email'] for a in event['attendees']]
    
def get_current_and_next_event() -> Dict[str, Optional[Dict]]:
    now = dt.datetime.now(TZ)
    events = list_today()

    current = None
    next_event = None

    for ev in events:
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        end = ev['end'].get('dateTime', ev['end'].get('date'))
        dt_start = isoparse(start).astimezone(TZ)
        dt_end = isoparse(end).astimezone(TZ)

        if dt_start <= now <= dt_end:
            current = ev
        elif dt_start > now:
            next_event = ev
            break

    return {"current": current, "next": next_event}

def extend_event(title: str, additional_minutes: int):
    events = get_agenda("today")
    for ev in events:
        if title.lower() in ev["summary"].lower():
            start_str = ev["start"].get("dateTime")
            end_str = ev["end"].get("dateTime")
            if not start_str or not end_str:
                raise ValueError("Event missing time info")

            start = dt.datetime.fromisoformat(start_str)
            end = dt.datetime.fromisoformat(end_str)
            new_end = end + dt.timedelta(minutes=additional_minutes)

            event_id = ev["id"]
            service = _service()  # ✅ Corrected here
            service.events().patch(
                calendarId="primary",
                eventId=event_id,
                body={"end": {"dateTime": new_end.isoformat(), "timeZone": "UTC"}}
            ).execute()
            return
    raise ValueError(f"Could not find event titled: {title}")

def cancel_event_natural(phrase: str) -> bool:
    service = _service()
    events = service.events().list(
        calendarId='primary',
        timeMin=dt.datetime.now(TZ).isoformat(),
        maxResults=10,
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

    for ev in events:
        if phrase.lower() in ev["summary"].lower():
            event_id = ev["id"]
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return True
    return False

def log_missed_events() -> List[Dict]:
    service = _service()
    now = dt.datetime.now(TZ).isoformat()
    events = service.events().list(
        calendarId='primary',
        timeMax=now,
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

    missed = []
    for ev in events:
        status = ev.get("status", "confirmed")
        if status == "confirmed":
            missed.append({
                "summary": ev.get("summary"),
                "start": ev["start"].get("dateTime"),
                "id": ev["id"]
            })
    return missed

UNDO_FILE = ".undo_event.json"

def backup_event(event: Dict):
    with open(UNDO_FILE, "w") as f:
        json.dump(event, f)

def undo_last_event_change():
    if not os.path.exists(UNDO_FILE):
        raise RuntimeError("No undo history found.")
    with open(UNDO_FILE, "r") as f:
        last_event = json.load(f)

    service = _service()
    return service.events().update(
        calendarId="primary",
        eventId=last_event["id"],
        body=last_event
    ).execute()
    
def smart_q2_reschedule():
    service = _service()
    now = dt.datetime.now(TZ)
    events = get_agenda("today")

    for ev in events:
        if "q2" in ev["summary"].lower():
            end_str = ev["end"].get("dateTime")
            if not end_str:
                continue
            original_end = dt.datetime.fromisoformat(end_str).astimezone(TZ)

            # Try to move 1 hour forward, skip if conflict
            proposed_start = original_end + dt.timedelta(minutes=30)
            proposed_end = proposed_start + dt.timedelta(minutes=60)

            conflict = service.events().list(
                calendarId="primary",
                timeMin=proposed_start.isoformat(),
                timeMax=proposed_end.isoformat(),
                singleEvents=True
            ).execute().get('items', [])

            if not conflict:
                event_id = ev["id"]
                backup_event(ev)
                ev["start"]["dateTime"] = proposed_start.isoformat()
                ev["end"]["dateTime"] = proposed_end.isoformat()
                ev["start"]["timeZone"] = str(TZ)
                ev["end"]["timeZone"] = str(TZ)
                return service.events().update(calendarId="primary", eventId=event_id, body=ev).execute()

    raise ValueError("No reschedulable Q2 blocks found or no open slot available.")

def rename_event(original_title: str, new_title: str, date: str) -> Optional[Dict]:
    service = _service()
    time_min = f"{date}T00:00:00Z"
    time_max = f"{date}T23:59:59Z"

    events = service.events().list(
        calendarId='primary',
        q=original_title,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        maxResults=1
    ).execute().get('items', [])

    if not events:
        return None

    event = events[0]
    event['summary'] = new_title

    updated_event = service.events().update(calendarId='primary', eventId=event['id'], body=event).execute()
    log_event_action("update", updated_event)
    return updated_event
def log_event_action(action: str, event: Dict):
    log = {
        "action": action,
        "summary": event.get("summary"),
        "id": event.get("id"),
        "timestamp": dt.datetime.now(TZ).isoformat()
    }
    with open("event_log.json", "a") as f:
        f.write(json.dumps(log) + "\n")
        
def get_event_duration(title: str, date: str) -> Optional[int]:
    event = describe_event(title, date)
    if not event or 'start' not in event or 'end' not in event:
        return None

    start_str = event['start'].get('dateTime')
    end_str = event['end'].get('dateTime')
    if not start_str or not end_str:
        return None

    start = dt.datetime.fromisoformat(start_str)
    end = dt.datetime.fromisoformat(end_str)
    return int((end - start).total_seconds() / 60)

def get_time_until_next_event() -> Dict[str, Optional[Union[int, str]]]:
    now = dt.datetime.now(TZ)
    events = get_agenda("today")

    for ev in events:
        start_str = ev["start"].get("dateTime")
        if not start_str:
            continue
        start = dt.datetime.fromisoformat(start_str).astimezone(TZ)
        if start > now:
            minutes_until = int((start - now).total_seconds() / 60)
            return {"minutes_until": minutes_until, "summary": ev["summary"]}

    return {"minutes_until": None, "summary": None}