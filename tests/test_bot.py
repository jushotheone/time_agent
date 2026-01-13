# tests/test_main.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import bot  # ✅ This matches patch targets like "bot.send_daily_agenda"

@patch("bot.run_evening_review", new_callable=AsyncMock)
@patch("bot.send_weekly_audit", new_callable=AsyncMock)
@patch("bot.send_time_reminders")
@patch("bot.send_daily_agenda")
@patch("bot.run_ai_loop")
@patch("bot.ApplicationBuilder")
@patch("bot.os.getenv")
def test_main_sets_up_bot(
    mock_getenv,
    mock_app_builder,
    mock_run_ai_loop,
    mock_send_daily_agenda,
    mock_send_time_reminders,
    mock_send_weekly_audit,
    mock_evening_review,
):
    # Arrange: fake environment and Telegram app
    mock_getenv.return_value = "fake-token"
    mock_app = MagicMock()
    mock_job_queue = MagicMock()
    mock_app.job_queue = mock_job_queue
    mock_app.run_polling = MagicMock()

    # Mock ApplicationBuilder chain
    builder_instance = MagicMock()
    builder_instance.token.return_value = builder_instance
    builder_instance.post_init.return_value = builder_instance
    builder_instance.build.return_value = mock_app
    mock_app_builder.return_value = builder_instance

    # Act
    bot.main()

    # Assert bot setup
    mock_getenv.assert_called_with("TELEGRAM_BOT_TOKEN")
    mock_send_daily_agenda.assert_called_once_with(mock_app)
    mock_send_time_reminders.assert_called_once_with(mock_app)
    # Bot schedules two repeating jobs: the AI loop + workflow #0 tick.
    assert mock_job_queue.run_repeating.call_count == 2

    calls = mock_job_queue.run_repeating.call_args_list
    intervals = [kwargs.get("interval") for _, kwargs in calls]
    assert 3600 in intervals  # ai_loop_job
    assert 60 in intervals    # wf0_tick
    assert mock_job_queue.run_daily.call_count == 2
    mock_app.run_polling.assert_called_once()