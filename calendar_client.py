import os
import datetime as dt
import zoneinfo
from typing import List, Dict, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from dateutil.parser import isoparse

SCOPES = ['https://www.googleapis.com/auth/calendar']
TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

def _get_creds() -> Credentials:
    creds = None
    token_path = 'token.json'
    creds_path = os.getenv("GOOGLE_CREDENTIALS_JSON", "client_secret.json")
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds

def _service():
    creds = _get_creds()
    return build('calendar', 'v3', credentials=creds)

def create_event(title: str, start: dt.datetime, duration_minutes: int = 60) -> Dict:
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

    return service.events().insert(calendarId='primary', body=event_body).execute()

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

    return service.events().update(calendarId='primary', eventId=event['id'], body=event).execute()

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
        return [get_current_and_next_event().get("current")]

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