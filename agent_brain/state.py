# ======================
# agent_brain/state.py
# ======================
import db
from datetime import datetime
from zoneinfo import ZoneInfo
import os

TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))

def log_event_status(event_id, status, quadrant=None):  # ✅ Add quadrant param
    db.mark_event_as_notified(event_id, phase=status)
    db.log_event(
        event_id,
        status,
        timestamp=datetime.now(TZ),
        quadrant=quadrant  # ✅ Pass it along to DB
    )