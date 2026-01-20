import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_6_didnt_start_marks_segment_status_and_acknowledges():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "mark_didnt_start_by_title"):
        pytest.fail("Implement time_service.mark_didnt_start_by_title(title, now_iso)")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    tb.insert_segment({
        "id": "seg_miss",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Client Output - 5 proposals",
        "domain": "client",
        "tz": "Europe/London",
    })

    payload = ts.mark_didnt_start_by_title("Client Output - 5 proposals", now.isoformat())
    assert isinstance(payload, dict)
    assert payload.get("kind") in ("updated", "missed"), payload
    assert payload.get("segment_id") == "seg_miss", payload

    seg = tb.get_active_segment(now)  # could be none depending on time; fetch by id in your layer if needed
    # Contract expectation: you store end_status or status somewhere. If not, enforce it with a getter.
    if not hasattr(tb, "get_segment"):
        pytest.fail("Add tb.get_segment(seg_id) to verify end_status.")
    s = tb.get_segment("seg_miss")
    assert s.get("end_status") in ("didnt_start", "missed", "skipped"), s