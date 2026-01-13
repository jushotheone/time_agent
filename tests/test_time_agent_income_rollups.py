import pytest


@pytest.mark.contract
def test_io_2_income_fields_in_schema():
    """
    IO-2: segments/time_entries must have income_related and income_stream_id columns.
    """
    pytest.xfail("Add income_related and income_stream_id columns to DB schema.")


@pytest.mark.contract
def test_io_3_income_rollup_export():
    """
    IO-3: time_service.get_income_rollup() must export hours by income stream/client.
    """
    pytest.xfail("Implement get_income_rollup with stable structure.")


@pytest.mark.contract
def test_io_2_actual_log_can_link_outcome_type():
    import beia_core.services.time_service as ts

    if not hasattr(ts, "log_actual"):
        pytest.fail("Implement time_service.log_actual(...)")
    if not hasattr(ts, "get_income_rollup"):
        pytest.fail("Implement time_service.get_income_rollup(date_range)")

    rec = ts.log_actual({
        "occurred_at": "2026-01-12T10:00:00+00:00",
        "duration_minutes": 60,
        "domain": "client",
        "income_related": True,
        "income_stream_id": None,
        "outcome_type": "proposal_submitted",
        "source": "chat",
    })
    assert rec.get("outcome_type") == "proposal_submitted"


@pytest.mark.contract
def test_io_3_income_rollup_counts_hours_and_outcomes_from_db():
    import beia_core.services.time_service as ts

    if not hasattr(ts, "get_income_rollup"):
        pytest.fail("Implement time_service.get_income_rollup(date_range)")

    out = ts.get_income_rollup({
        "start": "2026-01-12",
        "end": "2026-01-12",
    })

    # Stable keys
    assert "hours_by_income_stream" in out
    assert "outcomes_count_by_type" in out