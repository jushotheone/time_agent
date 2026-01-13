# ✅ tests/test_observer.py
import datetime as dt
from zoneinfo import ZoneInfo
from unittest.mock import patch

from agent_brain.observer import detect_drift

TZ = ZoneInfo("Europe/London")


def test_detect_drift_missed_event():
    """Legacy behaviour: if a current event is past grace, return a single 'missed' dict."""
    now = dt.datetime.now(TZ)

    mock_event = {
        "id": "abc123",
        "summary": "Fix urgent plumbing",
        "start": {"dateTime": (now - dt.timedelta(hours=1)).isoformat()},
        # ended 6 minutes ago -> past 5 minute grace window
        "end": {"dateTime": (now - dt.timedelta(minutes=6)).isoformat()},
    }

    with patch("agent_brain.observer._ensure_current_event_segment", return_value=None), \
         patch("agent_brain.observer.cal.get_current_and_next_event", return_value={"current": mock_event, "next": None}), \
         patch("agent_brain.observer.db.get_active_segment", return_value=None), \
         patch("agent_brain.observer.db.was_event_notified", return_value=False), \
         patch("agent_brain.observer.detect_quadrant", return_value="I"):

        result = detect_drift()

    assert isinstance(result, dict)
    assert result["status"] == "missed"
    assert result["event_id"] == "abc123"
    assert result["quadrant"] == "I"


def test_detect_drift_none():
    """If there is no current event and the gap is < 15 minutes, do nothing."""
    now = dt.datetime.now(TZ)
    soon = now + dt.timedelta(minutes=5)

    with patch("agent_brain.observer._ensure_current_event_segment", return_value=None), \
         patch("agent_brain.observer.cal.get_current_and_next_event", return_value={
             "current": None,
             "next": {"start": {"dateTime": soon.isoformat()}, "end": {"dateTime": (soon + dt.timedelta(minutes=30)).isoformat()}},
         }), \
         patch("agent_brain.observer.db.get_active_segment", return_value=None):

        assert detect_drift() is None
