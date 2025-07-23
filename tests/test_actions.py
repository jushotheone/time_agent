# tests/test_actions.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agent_brain import actions
import datetime as dt
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")

@patch("agent_brain.actions.cal.create_event")
@patch("agent_brain.actions.format_event_description")
@patch("agent_brain.actions.respond_with_brain", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_handle_create_event_detailed(mock_respond, mock_format, mock_create):
    parsed = {
        "action": "create_event",
        "title": "Strategy Sync",
        "date": "2025-07-23",
        "time": "10:00"
    }

    mock_create.return_value = {"summary": "Strategy Sync", "start": {"dateTime": "2025-07-23T10:00:00"}}
    mock_format.return_value = "📝 *Strategy Sync*\n📅 10:00 — 11:00"

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await actions.handle_action(parsed, update, context)

    mock_create.assert_called_once()
    mock_format.assert_called_once()
    mock_respond.assert_awaited_once()
    summary_sent = mock_respond.call_args[1]['summary']
    assert "Strategy Sync" in summary_sent

@patch("calendar_client.reschedule_event")
@pytest.mark.asyncio
async def test_reschedule_event(mock_reschedule):
    parsed = {"original_title": "Test Event", "new_date": "2025-07-24", "new_time": "11:00"}
    actions.reschedule_event(parsed)
    mock_reschedule.assert_called_once()

@patch("calendar_client.cancel_event")
@pytest.mark.asyncio
async def test_cancel_event(mock_cancel):
    parsed = {"title": "Test Event", "date": "2025-07-23"}
    actions.cancel_event(parsed)
    mock_cancel.assert_called_once()

@patch("agent_brain.actions.cal.reschedule_event")
@patch("agent_brain.actions.respond_with_brain", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_handle_reschedule_event(mock_respond, mock_reschedule):
    parsed = {
        "action": "reschedule_event",
        "original_title": "Daily Standup",
        "new_date": "2025-07-25",
        "new_time": "14:00"
    }

    # ✅ THIS is the key: a real dict, not a mock!
    mock_reschedule.return_value = {
        "summary": "Daily Standup",
        "start": {"dateTime": "2025-07-25T14:00:00"},
        "end": {"dateTime": "2025-07-25T15:00:00"},
        "location": "Zoom",
        "description": "Planning sync",
        "recurrence": "None",
        "attendees": ["alice@example.com"]
    }

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await actions.handle_action(parsed, update, context)

    mock_reschedule.assert_called_once()
    mock_respond.assert_awaited_once()

    summary = mock_respond.call_args[1]["summary"]
    assert "Daily Standup" in summary
    assert "Zoom" in summary
    assert "Planning sync" in summary

@patch("agent_brain.actions.rename_event")
@pytest.mark.asyncio
async def test_rename_event(mock_rename):
    parsed = {"original_title": "Old Title", "new_title": "New Title", "date": "2025-07-23"}
    actions.rename(parsed)
    mock_rename.assert_called_once()

@patch("calendar_client.describe_event")
@pytest.mark.asyncio
async def test_describe_event(mock_describe):
    
    parsed = {"title": "Test Event", "date": "2025-07-23"}
    mock_describe.return_value = {"summary": "Test Event", "start": "10:00", "end": "11:00"}
    result = actions.describe_event(parsed)
    assert result["summary"] == "Test Event"

@patch("calendar_client.get_event_duration")
@pytest.mark.asyncio
async def test_get_event_duration(mock_duration):
    parsed = {"title": "Test Event", "date": "2025-07-23"}
    mock_duration.return_value = 60
    duration = actions.get_event_duration(parsed)
    assert duration == 60

@patch("calendar_client.list_attendees")
@pytest.mark.asyncio
async def test_list_attendees(mock_attendees):
    parsed = {"title": "Test Event", "date": "2025-07-23"}
    mock_attendees.return_value = ["Alice", "Bob"]
    attendees = actions.list_attendees(parsed)
    assert "Alice" in attendees

@patch("calendar_client.log_event_action")
@pytest.mark.asyncio
async def test_log_event_action(mock_log):
    parsed = {"event_id": "123", "action": "completed", "timestamp": dt.datetime.now()}
    actions.log_event_action(parsed)
    mock_log.assert_called_once()

@patch("calendar_client.get_agenda")
@pytest.mark.asyncio
async def test_get_agenda(mock_agenda):
    parsed = {"range": "today"}
    mock_agenda.return_value = [{"summary": "Meeting", "start": {"dateTime": "2025-07-23T10:00:00"}}]
    agenda = actions.get_agenda(parsed)
    assert isinstance(agenda, list)

@patch("calendar_client.get_time_until_next_event")
@pytest.mark.asyncio
async def test_get_time_until_next_event(mock_time):
    mock_time.return_value = "10 minutes"
    result = actions.get_time_until_next_event()
    assert result == "10 minutes"

@patch("calendar_client.get_current_and_next_event")
@pytest.mark.asyncio
async def test_whats_next(mock_next):
    mock_next.return_value = {"current": {"summary": "Now", "start": {"dateTime": "2025-07-23T09:00:00"}}, "next": {"summary": "Next", "start": {"dateTime": "2025-07-23T10:00:00"}}}
    events = actions.whats_next()
    assert "current" in events and "next" in events

@patch("calendar_client.get_current_and_next_event")
@pytest.mark.asyncio
async def test_whats_now(mock_next):
    mock_next.return_value = {"current": {"summary": "Now", "start": {"dateTime": "2025-07-23T09:00:00"}}}
    events = actions.whats_next()
    assert "current" in events

@patch("agent_brain.actions.respond_with_brain", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_handle_chat_fallback(mock_respond):
    parsed = {
        "action": "chat_fallback",
        "user_prompt": "What should I do with this free time?"
    }

    update = MagicMock()
    update.message.reply_text = AsyncMock()  # Make awaitable

    context = MagicMock()
    await actions.handle_action(parsed, update, context)

    mock_respond.assert_awaited_once()
    
@patch("agent_brain.actions.cal.get_agenda")
@patch("agent_brain.actions.format_agenda_reply")
@patch("agent_brain.actions.respond_with_brain", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_handle_get_agenda(mock_respond, mock_format, mock_get_agenda):
    parsed = {"action": "get_agenda", "range": "today"}
    mock_get_agenda.return_value = [{"summary": "Sync", "start": {"dateTime": "2025-07-23T10:00:00"}}]
    mock_format.return_value = "🗓️ Your today agenda:\n10:00 • Sync"

    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    await actions.handle_action(parsed, update, context)

    mock_get_agenda.assert_called_once()
    mock_format.assert_called_once()
    mock_respond.assert_awaited_once()
    
    
