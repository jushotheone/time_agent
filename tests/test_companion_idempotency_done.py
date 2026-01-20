import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_12b_done_twice_does_not_double_log():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "mark_done_by_title"):
        pytest.fail("Missing time_service.mark_done_by_title")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    tb.insert_segment({
        "id": "seg_idem",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })

    r1 = ts.mark_done_by_title("Deep Work", now.isoformat())
    r2 = ts.mark_done_by_title("Deep Work", now.isoformat())

    assert isinstance(r1, dict) and isinstance(r2, dict)
    assert r1.get("kind") == "done", r1
    assert r1.get("segment_id") == "seg_idem", r1
    assert r2.get("already_done") is True, r2

    entries = tb.get_unconsumed_time_entries(limit=10)
    assert len(entries) == 1, entries