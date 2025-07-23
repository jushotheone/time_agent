# ✅ tests/test_quadrant_detector.py
import pytest
from agent_brain.quadrant_detector import detect_quadrant

def test_detect_quadrant_explicit():
    assert detect_quadrant("#q1 urgent stuff") == "I"
    assert detect_quadrant("#q2 planning time") == "II"
    assert detect_quadrant("#q3 admin call") == "III"

def test_detect_quadrant_keywords():
    assert detect_quadrant("Fix tenant issue") == "I"
    assert detect_quadrant("Weekly admin meeting") == "III"

def test_detect_quadrant_default():
    assert detect_quadrant("Read book") == "II"