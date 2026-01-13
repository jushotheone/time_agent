import pytest
import beia_core.services.time_service as ts


@pytest.mark.contract
def test_io_contract_surface_must_exist():
    # These can live inside get_sprint_time_rollup or a dedicated function.
    if not hasattr(ts, "get_income_rollup"):
        pytest.fail("Implement time_service.get_income_rollup(date_range) for IO-3 ROI exports.")


@pytest.mark.contract
def test_io_time_block_supports_income_fields():
    if not hasattr(ts, "create_time_block"):
        pytest.fail("Implement time_service.create_time_block first.")

    # When implemented, this should accept the fields (even if stored nullable).
    block = ts.create_time_block({
        "domain": "client",
        "start": "2026-01-12T10:00:00+00:00",
        "end": "2026-01-12T12:00:00+00:00",
        "intent": "Client work",
        "income_related": True,
        "income_stream_id": None,
    })
    assert "income_related" in block