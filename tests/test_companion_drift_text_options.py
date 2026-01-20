import pytest
import re

BANNED_RE = re.compile(r"\byou should\b|\byou must\b|\byou need to\b|\byou have to\b|\bwhy didn’t you\b", re.IGNORECASE)

@pytest.mark.contract
def test_cc_11_drift_reply_has_three_text_options_and_no_guilt():
    from agent_brain import messages

    if not hasattr(messages, "build_drift_text"):
        pytest.fail("Add messages.build_drift_text(payload)")

    payload = {"current_title": "YouTube thumbnails", "options": ["KEEP", "SHIFT", "LOG"]}
    txt = messages.build_drift_text(payload)

    assert "keep as is" in txt.lower(), txt
    assert "shift schedule" in txt.lower(), txt
    assert "log distraction" in txt.lower(), txt
    assert not BANNED_RE.search(txt), txt