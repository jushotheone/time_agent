import pytest
import re


BANNED_PHRASES = [
    r"\byou should\b",
    r"\byou must\b",
    r"\byou need to\b",
    r"\byou have to\b",
    r"\bwhy didn’t you\b",
]
BANNED_RE = re.compile("|".join(BANNED_PHRASES), re.IGNORECASE)


@pytest.mark.contract
def test_ab_1_sovereignty_lock_no_guilt_language():
    """
    Canonical contract: no guilt language, no parental tone, no 'should'.
    This requires a deterministic response builder we can test without hitting OpenAI.
    """
    from agent_brain import messages

    if not hasattr(messages, "build_missed_task_nudge_text"):
        pytest.fail("Add messages.build_missed_task_nudge_text(...) so adversarial tests are enforceable.")

    txt = messages.build_missed_task_nudge_text(
        name="gym",
        planned_hhmm="06:00",
        date_iso="2026-01-12",
        options=["DONE", "SKIP", "RESCHEDULE", "EDIT"],
        tone="gentle",
    )

    assert not BANNED_RE.search(txt), f"Found banned language in:\n{txt}"
    assert "?" in txt, "Prefer a question framing for choice/authority."