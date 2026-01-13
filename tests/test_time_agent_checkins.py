# tests/test_time_agent_checkins.py
import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")


@pytest.mark.contract
def test_cf_2_post_event_checkin_created_once_even_if_job_runs_twice():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "schedule_post_event_checkin"):
        pytest.fail("Implement time_service.schedule_post_event_checkin(event_id, end_at, minutes_after)")

    end_at = dt.datetime(2026, 1, 12, 11, 0, tzinfo=TZ)

    tb.insert_segment({
        "id": "seg_x",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": end_at - dt.timedelta(minutes=60),
        "end_at": end_at,
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })

    # Run twice to ensure idempotency (no duplicates)
    ts.schedule_post_event_checkin(event_id="seg_x", end_at=end_at, minutes_after=5)
    ts.schedule_post_event_checkin(event_id="seg_x", end_at=end_at, minutes_after=5)

    if not hasattr(tb, "list_event_notifications"):
        pytest.fail("Implement timebox.list_event_notifications() to inspect scheduled check-ins/reminders")

    notes = tb.list_event_notifications()
    checkins = [n for n in notes if n.get("type") == "checkin" and n.get("event_id") == "seg_x"]
    assert len(checkins) == 1, f"Expected one checkin, got {len(checkins)}: {checkins}"