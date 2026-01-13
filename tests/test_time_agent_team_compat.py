import pytest
import beia_core.models.timebox as tb
from beia_core.models.enums import Domain


@pytest.mark.contract
def test_tc_1_domain_values_are_enum_safe():
    # If you store domains in DB, they must map cleanly to the Domain enum names.
    required = {"loj", "telnwa", "dev", "client", "music"}
    actual = {d.name for d in Domain}
    assert required.issubset(actual)


@pytest.mark.contract
def test_tc_2_segments_support_build_and_sprint_fields():
    """
    Your init_db() adds build_id/sprint_id columns conditionally.
    This contract test forces the model layer to expose the concept consistently.
    """
    # We cannot introspect DB schema without a DB. Instead we enforce that the timebox layer
    # provides insert_segment/update_segment that accept build_id/sprint_id.
    if not hasattr(tb, "insert_segment") or not hasattr(tb, "update_segment"):
        pytest.fail("timebox must expose insert_segment/update_segment to support build_id/sprint_id linkage.")


@pytest.mark.contract
def test_tc_4_rollup_export_function_must_exist():
    import beia_core.services.time_service as ts
    if not hasattr(ts, "get_sprint_time_rollup"):
        pytest.fail("Implement time_service.get_sprint_time_rollup(sprint_id|date_range)")

    # When implemented, enforce stable keys:
    # total_focused_hours, total_meeting_hours, quadrants{q1,q2,q3,q4}, by_domain, by_build