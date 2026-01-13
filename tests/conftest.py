import os
import pytest
import beia_core.models.timebox as tb


def _has_db() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


@pytest.fixture(scope="session", autouse=True)
def _init_db_once():
    """
    Initialise schema once per test run.
    """
    if not _has_db():
        pytest.skip("DATABASE_URL not set; DB-backed Time Agent contract tests skipped.")
    tb.init_db()


@pytest.fixture(autouse=True)
def _clean_db_between_tests():
    """
    Clean tables between tests.
    WARNING: This truncates tables. Use a dedicated TEST database.
    """
    if not _has_db():
        return

    with tb.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE TABLE
                    event_notifications,
                    postponed_reminders,
                    event_log,
                    conversations,
                    missed_queue,
                    recovery_blocks,
                    signals,
                    time_entries,
                    segments,
                    day_state
                RESTART IDENTITY CASCADE;
            """)
        conn.commit()