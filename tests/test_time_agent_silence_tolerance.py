import pytest


@pytest.mark.contract
def test_cp_3_silence_tolerance_must_not_spam_after_timeout():
    """
    CP-3: If user ignores a prompt for N minutes, system silences.
    No infinite retry loops.
    """
    pytest.xfail("Implement silence tolerance (backoff after timeout).")


@pytest.mark.contract
def test_ab_b3_no_dark_patterns_or_manipulative_ui():
    """
    AB-B3: No dark patterns (forced engagement, fake urgency, etc).
    Buttons must be honest and equal in size/prominence.
    """
    pytest.xfail("Audit UI for dark patterns.")



@pytest.mark.contract
def test_cp_3_followup_rate_limit_one_followup_then_stop():
    """
    Given a missed item and no user reply,
    Then system should schedule/send at most ONE follow-up in the window.
    """
    import beia_core.services.time_service as ts

    if not hasattr(ts, "should_send_followup"):
        pytest.fail("Implement time_service.should_send_followup(missed_id, now) with rate limiting")

    missed_id = "missed_1"

    # Simulate: first followup allowed, second disallowed
    assert ts.should_send_followup(missed_id=missed_id, now_iso="2026-01-12T12:00:00+00:00") is True
    assert ts.should_send_followup(missed_id=missed_id, now_iso="2026-01-12T12:10:00+00:00") is False