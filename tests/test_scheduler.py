from agent_brain.scheduler import propose_adjustment
from datetime import datetime

def test_propose_adjustment():
    drift = {"summary": "Morning Planning"}
    suggestion = propose_adjustment(drift)
    assert suggestion["action"] == "reschedule_event"
    assert "Morning Planning" in suggestion["reason"]

    dt_obj = datetime.fromisoformat(suggestion["new_time"])
    assert dt_obj.minute == 0 and dt_obj.second == 0  # Ensures it's top of the hour