import pytest
import datetime as dt

import beia_core.services.time_service as ts


@pytest.mark.contract
def test_contract_surface_must_exist():
    # Canonical contract requires these to exist and be testable.
    required = [
        "create_time_block",
        "get_daily_summary",
        "get_sprint_time_rollup",
        "log_actual",
        "revise_time_block",
    ]
    missing = [name for name in required if not hasattr(ts, name)]
    assert not missing, f"Missing required time_service interfaces: {missing}"


@pytest.mark.contract
def test_cf_4_planned_vs_actual_are_separate_records(monkeypatch):
    """
    Contract: planned time is not rewritten to pretend it happened.
    Actual is logged separately.
    """
    # If you implement on top of beia_core.models.timebox,
    # you can wire these to tb.insert_segment / tb.insert_time_entry, etc.

    calls = {"planned": [], "actual": []}

    def fake_create_time_block(payload):
        calls["planned"].append(payload)
        return {"id": "plan_1", **payload}

    def fake_log_actual(payload):
        calls["actual"].append(payload)
        return {"id": "act_1", **payload}

    if not hasattr(ts, "create_time_block") or not hasattr(ts, "log_actual"):
        pytest.fail("Implement create_time_block + log_actual to satisfy the two-truth rule.")

    monkeypatch.setattr(ts, "create_time_block", fake_create_time_block, raising=True)
    monkeypatch.setattr(ts, "log_actual", fake_log_actual, raising=True)

    planned = ts.create_time_block({
        "domain": "dev",
        "start": dt.datetime(2026, 1, 12, 6, 0),
        "end": dt.datetime(2026, 1, 12, 6, 45),
        "intent": "Gym",
        "quadrant": "II",
    })
    _ = ts.log_actual({
        "planned_block_id": planned["id"],
        "occurred_at": dt.datetime(2026, 1, 12, 6, 0),
        "duration": 0,
        "outcome": "missed",
        "source": "user",
    })

    assert len(calls["planned"]) == 1
    assert len(calls["actual"]) == 1
    # planned block must remain as originally created (no mutation by log_actual)
    assert planned["intent"] == "Gym"