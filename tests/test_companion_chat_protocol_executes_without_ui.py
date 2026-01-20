import pytest
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@pytest.mark.contract
def test_cc_4_router_executes_text_command_without_callback_query():
    """
    Text commands must execute with no Telegram callback_query present.
    """
    import beia_core.models.timebox as tb
    import gpt_agent
    from agent_brain import actions as AB

    now = dt.datetime(2026, 1, 12, 10, 0, tzinfo=TZ)

    tb.insert_segment({
        "id": "seg_x",
        "type": "scheduled",
        "rigidity": "soft",
        "start_at": now - dt.timedelta(minutes=30),
        "end_at": now + dt.timedelta(minutes=30),
        "title": "Deep Work",
        "domain": "dev",
        "tz": "Europe/London",
    })

    parsed = gpt_agent.parse_command("DONE Deep Work")
    assert parsed and parsed["action"] == "done"

    # Shim update/context with no UI
    class _ShimUpdate:
        callback_query = None
        message = type("M", (), {"text": "DONE Deep Work", "reply_text": lambda self, t: None})()
        effective_chat = type("C", (), {"id": "test"})()

    class _ShimContext:
        pass

    # Must not raise
    AB.handle_action(parsed, _ShimUpdate(), _ShimContext())