# tests/test_time_agent_reminders.py
import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")


@pytest.mark.contract
def test_cf_1_reminder_timing_10_mins_before():
    """
    Given event at 10:00 Europe/London and reminder rule '10 mins before'
    Then reminder scheduled time = 09:50 Europe/London.
    """
    import beia_core.services.time_service as ts

    if not hasattr(ts, "compute_reminder_fire_time"):
        pytest.fail("Implement time_service.compute_reminder_fire_time(start_at, minutes_before, tz)")

    start = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)
    fire = ts.compute_reminder_fire_time(start_at=start, minutes_before=10, tz="Europe/London")

    assert fire.tzinfo is not None
    assert fire.astimezone(TZ).hour == 9
    assert fire.astimezone(TZ).minute == 50


@pytest.mark.contract
def test_cf_1_reminder_timing_dst_spring_forward_safe():
    """
    DST edge: ensure reminder computation is timezone-safe across DST changes.
    Use a UK DST start date (last Sunday in March).
    """
    import beia_core.services.time_service as ts
    if not hasattr(ts, "compute_reminder_fire_time"):
        pytest.fail("Implement time_service.compute_reminder_fire_time(start_at, minutes_before, tz)")

    # 2026-03-29 is UK DST start (spring forward) — if your TZ library differs, adjust date.
    start = dt.datetime(2026, 3, 29, 10, 0, tzinfo=TZ)
    fire = ts.compute_reminder_fire_time(start_at=start, minutes_before=10, tz="Europe/London")

    # Must still be exactly 10 minutes before in local time sense
    assert (start - fire).total_seconds() == 600