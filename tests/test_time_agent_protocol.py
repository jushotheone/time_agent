import pytest
import re

from agent_brain import messages


ACTION_FOOTER_RE = re.compile(
    r"#ACTION\s+type=\w+\s+name=[^\s]+\s+date=\d{4}-\d{2}-\d{2}\s+options=\[[A-Z,]+\]"
)


@pytest.mark.contract
def test_cp_2_agent_messages_must_include_action_footer_for_nudges():
    """
    Canonical contract: every proactive nudge must include:
      1) human sentence
      2) structured footer for automation parsing
    """

    # You don't yet have a pure text nudge builder, so this test forces you to add one.
    # Suggested future function: messages.build_missed_task_nudge_text(...)
    if not hasattr(messages, "build_missed_task_nudge_text"):
        pytest.fail(
            "Add messages.build_missed_task_nudge_text(...) returning a string with a #ACTION footer."
        )

    txt = messages.build_missed_task_nudge_text(
        name="calisthenics",
        planned_hhmm="05:00",
        date_iso="2026-01-12",
        options=["DONE", "SKIP", "RESCHEDULE", "EDIT"],
    )

    assert isinstance(txt, str) and txt.strip()
    assert ACTION_FOOTER_RE.search(txt), f"Missing/invalid #ACTION footer:\n{txt}"


@pytest.mark.contract
def test_cp_1_chat_only_commands_are_supported_by_parser():
    """
    You currently parse with gpt_agent.parse (LLM).
    Canonical contract requires deterministic parsing for commands like:
      DONE <task>, SKIP <task>, RESCHEDULE <task> <HH:MM>, SUMMARY today, etc.

    This test forces you to implement a deterministic command parser,
    even if you still keep the LLM for fuzzy stuff.
    """
    import gpt_agent

    if not hasattr(gpt_agent, "parse_command"):
        pytest.fail("Add gpt_agent.parse_command(text) for deterministic chat protocol commands.")

    cases = [
        ("DONE gym", {"action": "done"}),
        ("SKIP gym today", {"action": "skip"}),
        ("RESCHEDULE gym 18:00", {"action": "reschedule"}),
        ("SUMMARY today", {"action": "summary"}),
        ("WHAT DID I MISS today", {"action": "misses"}),
    ]

    for text, expected in cases:
        out = gpt_agent.parse_command(text)
        assert isinstance(out, dict), f"parse_command must return dict; got {type(out)}"
        assert out.get("action") == expected["action"], f"{text} → {out}"