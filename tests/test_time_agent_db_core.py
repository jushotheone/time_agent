import pytest
import datetime as dt
from zoneinfo import ZoneInfo

import beia_core.models.timebox as tb


TZ = ZoneInfo("Europe/London")


@pytest.mark.contract
def test_segments_insert_and_active_next_queries_work():
    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)

    seg1 = {
        "id": "seg_a",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    }
    seg2 = {
        "id": "seg_b",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now + dt.timedelta(minutes=60),
        "end_at": now + dt.timedelta(minutes=120),
        "title": "Gym",
        "domain": "health",
        "tz": "Europe/London",
    }

    tb.insert_segment(seg1)
    tb.insert_segment(seg2)

    active = tb.get_active_segment(now)
    assert active is not None
    assert active["id"] == "seg_a"
    assert active["title"] == "Deep Work"

    next_seg = tb.get_next_segment(now)
    assert next_seg is not None
    assert next_seg["id"] == "seg_b"
    assert next_seg["title"] == "Gym"


@pytest.mark.contract
def test_day_state_auto_creates_and_updates():
    day = dt.date(2026, 1, 12)

    st = tb.get_day_state(day)
    assert st["day"] == day
    assert st["current_tone"] in ("gentle", "coach", "ds")

    tb.set_day_state(day, consecutive_misses=2, consecutive_completions=0)
    st2 = tb.get_day_state(day)
    assert st2["consecutive_misses"] == 2


@pytest.mark.contract
def test_time_entry_insert_and_unconsumed_flow():
    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)

    tb.insert_segment({
        "id": "seg_done",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=60),
        "end_at": now,
        "title": "Client work",
        "domain": "client",
        "tz": "Europe/London",
    })

    tb.insert_time_entry(
        seg_id="seg_done",
        minutes=60,
        started_at=now - dt.timedelta(minutes=60),
        ended_at=now,
        title="Client work",
        domain="client",
        subdomain_slug=None,
        build_id=None,
        sprint_id=None,
        source="time_agent",
    )

    entries = tb.get_unconsumed_time_entries(limit=10)
    assert len(entries) == 1
    assert entries[0]["seg_id"] == "seg_done"
    assert entries[0]["minutes"] == 60

    entry_id = entries[0]["id"]
    tb.mark_time_entry_consumed(entry_id)

    entries2 = tb.get_unconsumed_time_entries(limit=10)
    assert entries2 == []


@pytest.mark.contract
def test_snooze_segment_extends_end_time():
    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)

    tb.insert_segment({
        "id": "seg_snooze",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now,
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Focus block",
        "tz": "Europe/London",
    })

    updated = tb.snooze_segment("seg_snooze", minutes=10)
    assert updated is not None
    assert updated["end_at"] == now + dt.timedelta(minutes=40)