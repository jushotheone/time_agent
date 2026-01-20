import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_7_need_more_creates_recovery_block_and_acknowledges():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "need_more_by_title"):
        pytest.fail("Implement time_service.need_more_by_title(title, extra_minutes, now_iso)")

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    tb.insert_segment({
        "id": "seg_nm",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })

    payload = ts.need_more_by_title("Deep Work", extra_minutes=15, now_iso=now.isoformat())
    assert isinstance(payload, dict)
    assert payload.get("kind") in ("scheduled", "updated"), payload
    assert payload.get("segment_id") == "seg_nm", payload
    recovery_id = payload.get("recovery_segment_id")

    # Expect a recovery block exists (your DB already has recovery_blocks table in truncation list)
    if not hasattr(tb, "list_recovery_blocks"):
        pytest.fail("Add tb.list_recovery_blocks(day_iso) to verify recovery scheduling.")
    blocks = tb.list_recovery_blocks("2026-01-12")
    assert len(blocks) >= 1
    if recovery_id:
        assert any(b.get("id") == recovery_id for b in blocks)