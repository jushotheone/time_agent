import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_12a_summary_today_matches_db_totals():
    import beia_core.models.timebox as tb
    import beia_core.services.time_service as ts

    if not hasattr(ts, "get_daily_summary"):
        pytest.fail("Missing time_service.get_daily_summary(date_iso)")

    day = dt.date(2026, 1, 12)
    base = dt.datetime(2026, 1, 12, 9, 0, tzinfo=TZ)

    quads = [("seg_q1","Q1","dev"),("seg_q2","Q2","dev"),("seg_q3","Q3","client"),("seg_q4","Q4","loj")]
    for i,(sid,q,dom) in enumerate(quads):
        start = base + dt.timedelta(minutes=30*i)
        end   = start + dt.timedelta(minutes=30)
        tb.insert_segment({"id":sid,"type":"scheduled","rigidity":"soft","start_at":start,"end_at":end,"title":f"Block {q}","domain":dom,"tz":"Europe/London","quadrant":q})
        tb.insert_time_entry(seg_id=sid,minutes=30,started_at=start,ended_at=end,title=f"Block {q}",domain=dom,subdomain_slug=None,build_id=None,sprint_id=None,source="time_agent")

    summary = ts.get_daily_summary(day.isoformat())

    assert "q1" in summary["quadrants"] and "q4" in summary["quadrants"], summary
    assert "planned_minutes" in summary["by_domain"] and "actual_minutes" in summary["by_domain"], summary

    # Each quadrant logged 30 minutes
    assert summary["quadrants"]["q1"]["actual_minutes"] == 30
    assert summary["quadrants"]["q2"]["actual_minutes"] == 30
    assert summary["quadrants"]["q3"]["actual_minutes"] == 30
    assert summary["quadrants"]["q4"]["actual_minutes"] == 30

    # Domain totals should include both planned and actual
    dev = summary["by_domain"].get("dev", {})
    client = summary["by_domain"].get("client", {})
    loj = summary["by_domain"].get("loj", {})
    assert dev.get("actual_minutes") == 60
    assert client.get("actual_minutes") == 30
    assert loj.get("actual_minutes") == 30