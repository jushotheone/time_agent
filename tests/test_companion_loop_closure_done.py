import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_5_done_closes_loop_writes_time_entry_and_acknowledges():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "mark_done_by_title"):
        pytest.fail("Implement time_service.mark_done_by_title(title, now_iso) returning operator-mode reply")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    tb.insert_segment({
        "id": "seg_done",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })

    payload = ts.mark_done_by_title("Deep Work", now.isoformat())

    assert isinstance(payload, dict)
    assert payload.get("kind") == "done", payload
    assert payload.get("segment_id") == "seg_done", payload

    entries = tb.get_unconsumed_time_entries(limit=10)
    assert len(entries) == 1
    assert entries[0]["seg_id"] == "seg_done"