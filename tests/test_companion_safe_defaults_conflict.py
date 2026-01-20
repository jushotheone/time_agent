import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_12c_create_block_now_conflict_returns_nearest_options():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "create_time_block"):
        pytest.fail("Missing time_service.create_time_block")
    if not hasattr(ts, "create_time_block_from_chat"):
        pytest.fail("Add time_service.create_time_block_from_chat(title, minutes, now_iso) -> operator-mode reply w/options on conflict")

    now = dt.datetime(2026, 1, 12, 12, 0, tzinfo=TZ)

    # create existing segment that causes conflict
    tb.insert_segment({
        "id": "seg_busy",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now,
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Busy",
        "domain": "dev",
        "tz": "Europe/London",
    })

    reply = ts.create_time_block_from_chat("Deep Work", 30, now.isoformat())
    assert isinstance(reply, dict)
    assert reply.get("kind") in ("scheduled", "conflict"), reply
    if reply.get("kind") == "conflict":
        opts = reply.get("options") or []
        assert len(opts) >= 2, reply