import pytest

@pytest.mark.contract
def test_cc_9_brief_today_has_priorities_risk_and_next_action():
    import beia_core.services.time_service as ts

    if not hasattr(ts, "brief_today"):
        pytest.fail("Implement time_service.brief_today(date_iso) -> payload dict")

    out = ts.brief_today("2026-01-12")
    assert isinstance(out, dict)
    assert set(["priorities", "risk", "next_action"]).issubset(out.keys()), out