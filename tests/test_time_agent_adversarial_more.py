# tests/test_time_agent_adversarial_more.py
import pytest
import re

BANNED = re.compile(r"\byou should\b|\byou must\b|\byou need to\b|\byou have to\b", re.I)


@pytest.mark.contract
def test_ab_a1_changed_my_mind_yields_authority_one_question_max():
    from agent_brain import messages
    if not hasattr(messages, "build_changed_mind_reply"):
        pytest.fail("Add messages.build_changed_mind_reply(...) deterministic")

    txt = messages.build_changed_mind_reply()
    assert not BANNED.search(txt)
    assert txt.count("?") <= 1


@pytest.mark.contract
def test_ab_c2_dont_make_me_decide_offers_one_default_path_only():
    from agent_brain import messages
    if not hasattr(messages, "build_low_cognitive_load_default"):
        pytest.fail("Add messages.build_low_cognitive_load_default(...) deterministic")

    txt = messages.build_low_cognitive_load_default()
    assert not BANNED.search(txt)

    # crude enforcement: don’t list many options
    assert txt.lower().count("or") <= 1