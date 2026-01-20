import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_8_reply_includes_current_and_next_lines():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "continuity_snapshot"):
        pytest.fail("Implement time_service.continuity_snapshot(now_iso) -> {current,next}")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)

    tb.insert_segment({
        "id": "seg_cur",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=15),
        "end_at": now + dt.timedelta(minutes=15),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })
    tb.insert_segment({
        "id": "seg_next",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now + dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=60),
        "title": "Gym",
        "domain": "health",
        "tz": "Europe/London",
    })

    snap = ts.continuity_snapshot(now.isoformat())
    assert isinstance(snap, dict)
    assert isinstance(snap.get("current"), dict), snap
    assert isinstance(snap.get("next"), dict), snap
    assert snap["current"].get("id") == "seg_cur", snap
    assert snap["next"].get("id") == "seg_next", snap