# ======================
# agent_brain/observer.py
# ======================
import os
import datetime as dt
import zoneinfo
import calendar_client as cal
import db
from agent_brain.quadrant_detector import detect_quadrant  # ✅ New

TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))

def detect_drift():
    now = dt.datetime.now(TZ)
    events = cal.get_current_and_next_event()
    current = events.get("current")

    if current:
        start = dt.datetime.fromisoformat(current["start"]["dateTime"]).astimezone(TZ)
        end = dt.datetime.fromisoformat(current["end"]["dateTime"]).astimezone(TZ)
        grace_end = end + dt.timedelta(minutes=5)

        if now > grace_end and not db.was_event_notified(current["id"], "missed"):
            quadrant = detect_quadrant(current["summary"])  # ✅ Detect Covey quadrant
            return {
                "event_id": current["id"],
                "summary": current["summary"],
                "status": "missed",
                "start": start,
                "end": end,
                "quadrant": quadrant  # ✅ Include quadrant
            }
    return None