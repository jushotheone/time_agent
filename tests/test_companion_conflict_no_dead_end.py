import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_2_conflict_must_offer_options():
    """
    When a conflict occurs, reply MUST include at least 2 options with times
    OR a 'move the other event' option. No dead-end.
    """
    from agent_brain import messages

    if not hasattr(messages, "build_conflict_reply"):
        pytest.fail("Add messages.build_conflict_reply(payload)")

    attempted_start = dt.datetime(2026, 1, 12, 12, 0, tzinfo=TZ)
    attempted_end   = dt.datetime(2026, 1, 12, 12, 30, tzinfo=TZ)

    # example suggested options (nearest free slots)
    options = [
        ("12:30", "13:00"),
        ("13:00", "13:30"),
    ]

    payload = {
        "kind": "conflict",
        "title": "Deep Work",
        "attempted_start": attempted_start,
        "attempted_end": attempted_end,
        "options": options,
        "move_other": "Move 'Client Call' instead",
    }

    txt = messages.build_conflict_reply(payload)

    assert "⚠️ Conflict:" in txt, f"Must label conflict:\n{txt}"
    assert ("Option A" in txt and "Option B" in txt) or ("Move" in txt), f"Must offer options:\n{txt}"
    assert "12:30" in txt and "13:00" in txt, f"Must include times:\n{txt}"
    assert "tell me a time" not in txt.lower(), f"Must not dead-end:\n{txt}"