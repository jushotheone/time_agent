import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from agent_brain.core import run_brain, conversational_brain

@pytest.mark.asyncio
@patch("agent_brain.core.Bot")
@patch("agent_brain.core.log_event_status")
@patch("agent_brain.core.generate_followup_nudge")
@patch("agent_brain.core.propose_adjustment")
@patch("agent_brain.core.detect_drift")
async def test_run_brain_with_drift(mock_drift, mock_adjust, mock_nudge, mock_log, mock_bot):
    mock_drift.return_value = {
        "event_id": "abc123",
        "summary": "Deep Work Block",
        "status": "missed"
    }
    mock_adjust.return_value = {"action": "reschedule_event", "new_time": "2025-07-21T10:00:00", "reason": "missed"}
    mock_nudge.return_value = "📌 You missed your Deep Work. Shall I reschedule it?"
    mock_bot.return_value.send_message = AsyncMock()

    await run_brain()

    mock_log.assert_called_once_with("abc123", "missed")
    mock_bot.return_value.send_message.assert_awaited_once()
    mock_nudge.assert_called_once()

@pytest.mark.asyncio
@patch("agent_brain.core.save_conversation_turn")
@patch("agent_brain.core.get_recent_conversation")
@patch("agent_brain.core.calendar_client.get_current_and_next_event")
@patch("agent_brain.core.get_user_context")
@patch("agent_brain.core.AsyncOpenAI")
async def test_conversational_brain_flow(mock_openai, mock_context, mock_calendar, mock_history, mock_save):
    mock_context.return_value = {"focus": "Build Ruoth", "energy": "High"}
    mock_calendar.return_value = {"current": {"summary": "Design Sprint"}}
    mock_history.return_value = [{"role": "assistant", "content": "Hi!"}]

    mock_openai.return_value.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="🗓️ Here's your next task."))]
    ))

    user_input = "What's on my schedule today?"
    response = await conversational_brain(user_input)

    assert "🗓️" in response
    mock_save.assert_called()
    mock_openai.return_value.chat.completions.create.assert_awaited_once()