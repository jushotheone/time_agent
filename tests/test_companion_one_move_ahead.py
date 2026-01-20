import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_10_after_any_action_reply_includes_next_move():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "mark_done_by_title"):
        pytest.skip("Depends on mark_done_by_title from CC-5")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    tb.insert_segment({
        "id": "seg_done2",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })
    tb.insert_segment({
        "id": "seg_next2",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now + dt.timedelta(minutes=40),
        "end_at": now + dt.timedelta(minutes=70),
        "title": "Client Output",
        "domain": "client",
        "tz": "Europe/London",
    })

    reply = ts.mark_done_by_title("Deep Work", now.isoformat())
    assert "Next:" in reply, reply
    # must not ask more than one question
    assert reply.count("?") <= 1, reply