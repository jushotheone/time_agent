import asyncio
import pytest

@pytest.mark.contract
@pytest.mark.asyncio
async def test_cc_12d_ui_optional_text_only_flow():
    """
    Ensure core flow does not require InlineKeyboard callbacks.
    """
    import gpt_agent
    from agent_brain import actions as AB

    parsed = gpt_agent.parse_command("SNOOZE 5")
    assert parsed and parsed["action"] == "snooze" and parsed.get("minutes") == 5

    class _ShimUpdate:
        callback_query = None
        message = type("M", (), {"text": "SNOOZE 5", "reply_text": lambda self, t: None})()
        effective_chat = type("C", (), {"id": "test"})()

    class _ShimContext:
        pass

    await AB.handle_action(parsed, _ShimUpdate(), _ShimContext())