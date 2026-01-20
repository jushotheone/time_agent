import pytest
import re

OPERATOR_PREFIX_RE = re.compile(r"^(✅ Done:|🗓️ Scheduled:|↩️ Updated:|⚠️ Conflict:|📌 Noted:)\s")

DELTA_RE = re.compile(
    r"(seg[_\-]?\w+|gcal:\w+|\b\d{2}:\d{2}\b|status=|end_status=|minutes=\d+)",
    re.IGNORECASE
)

@pytest.mark.contract
def test_cc_1_operator_mode_prefix_and_delta_present():
    """
    Every outward assistant reply must start with operator prefix
    and contain a concrete delta token (segment id OR title OR time window OR status).
    """
    from agent_brain import messages

    if not hasattr(messages, "format_operator_reply"):
        pytest.fail("Add messages.format_operator_reply(payload)")

    payload = {
        "kind": "scheduled",
        "delta": {"title": "Deep Work", "start": "12:30", "end": "13:00", "segment_id": "seg_q2"},
        "current": None,
        "next": {"title": "Deep Work", "start": "12:30"},
        "options": ["START", "SNOOZE 5", "SKIP"],
    }

    txt = messages.format_operator_reply(payload)

    assert OPERATOR_PREFIX_RE.search(txt), f"Missing operator prefix:\n{txt}"
    assert DELTA_RE.search(txt), f"Missing delta token:\n{txt}"