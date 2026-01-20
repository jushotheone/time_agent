import pytest

@pytest.mark.contract
def test_cc_3_parse_command_supports_full_protocol():
    import gpt_agent

    if not hasattr(gpt_agent, "parse_command"):
        pytest.fail("Missing gpt_agent.parse_command(text)")

    cases = [
        ("DONE Deep Work",                 {"action": "done", "title": "Deep Work"}),
        ("DIDNT START Deep Work",          {"action": "didnt_start", "title": "Deep Work"}),
        ("NEED MORE Deep Work 15",         {"action": "need_more", "title": "Deep Work", "minutes": 15}),
        ("RESCHEDULE Deep Work 18:00",     {"action": "reschedule", "title": "Deep Work", "new_time": "18:00"}),
        ("MOVE NEXT Deep Work",            {"action": "move_next", "title": "Deep Work"}),
        ("SUMMARY today",                  {"action": "summary", "date": "today"}),
        ("WHAT DID I MISS today",          {"action": "misses", "date": "today"}),
        ("PAUSE",                          {"action": "pause"}),
        ("SNOOZE 5",                       {"action": "snooze", "minutes": 5}),
        ("SNOOZE 15",                      {"action": "snooze", "minutes": 15}),
        ("I'M DOING YouTube thumbnails",   {"action": "drift", "title": "YouTube thumbnails"}),
    ]

    for text, expected in cases:
        out = gpt_agent.parse_command(text)
        assert isinstance(out, dict), f"{text} must return dict"
        for k, v in expected.items():
            assert out.get(k) == v, f"{text} → {out} expected {k}={v}"