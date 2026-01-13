# tests/test_time_agent_summaries.py
import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")


@pytest.mark.contract
def test_cf_5_daily_summary_quadrants_add_up_and_match_db():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "get_daily_summary"):
        pytest.fail("Implement time_service.get_daily_summary(date_iso)")

    day = dt.date(2026, 1, 12)
    base = dt.datetime(2026, 1, 12, 9, 0, tzinfo=TZ)

    # Insert 4 segments and actual time entries: 30m each Q1..Q4
    segments = [
        ("seg_q1", "Q1", "dev"),
        ("seg_q2", "Q2", "dev"),
        ("seg_q3", "Q3", "client"),
        ("seg_q4", "Q4", "loj"),
    ]

    for i, (sid, quad, dom) in enumerate(segments):
        start = base + dt.timedelta(minutes=30 * i)
        end = start + dt.timedelta(minutes=30)
        tb.insert_segment({
            "id": sid,
            "type": "scheduled",
            "rigidity": "soft",
            "start_at": start,
            "end_at": end,
            "title": f"Block {quad}",
            "domain": dom,
            "tz": "Europe/London",
            "quadrant": quad,  # if you store it
        })
        tb.insert_time_entry(
            seg_id=sid,
            minutes=30,
            started_at=start,
            ended_at=end,
            title=f"Block {quad}",
            domain=dom,
            subdomain_slug=None,
            build_id=None,
            sprint_id=None,
            source="time_agent",
        )

    out = ts.get_daily_summary(day.isoformat())

    # Enforce stable shape
    assert "quadrants" in out, out
    assert "by_domain" in out, out

    q = out["quadrants"]
    for key in ("q1", "q2", "q3", "q4"):
        assert key in q, f"Missing quadrants.{key} in {q}"

    total = q["q1"] + q["q2"] + q["q3"] + q["q4"]
    assert total == 120, f"Expected 120 minutes total, got {total} ({q})"

    bd = out["by_domain"]
    assert bd.get("dev", 0) == 60
    assert bd.get("client", 0) == 30
    assert bd.get("loj", 0) == 30