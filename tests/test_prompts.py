# ✅ tests/test_prompts.py
from agent_brain.prompts import generate_followup_nudge

def test_generate_followup_nudge():
    drift = {"summary": "Fix plumbing"}
    suggestion = {"action": "reschedule_event"}
    message = generate_followup_nudge(drift, suggestion)
    assert "Fix plumbing" in message
    assert "reschedule" in message.lower() or "reflect" in message.lower()
