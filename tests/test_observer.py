# ✅ tests/test_observer.py
import datetime as dt
from unittest.mock import patch, MagicMock
from agent_brain.observer import detect_drift

def test_detect_drift_missed_event():
    mock_event = {
        "id": "abc123",
        "summary": "Fix urgent plumbing",
        "start": {"dateTime": (dt.datetime.now() - dt.timedelta(hours=1)).isoformat()},
        "end": {"dateTime": (dt.datetime.now() - dt.timedelta(minutes=6)).isoformat()},
    }
    with patch("calendar_client.get_current_and_next_event", return_value={"current": mock_event}), \
         patch("db.was_event_notified", return_value=False):
        result = detect_drift()
        assert result["status"] == "missed"
        assert result["event_id"] == "abc123"
        assert result["quadrant"] == "I"


def test_detect_drift_none():
    with patch("calendar_client.get_current_and_next_event", return_value={"current": None}):
        assert detect_drift() is None

