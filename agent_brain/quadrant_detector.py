# agent_brain/quadrant_detector.py

def detect_quadrant(summary: str) -> str:
    text = summary.lower()

    # Q1: Crises, deadlines, things that can’t be missed
    q1_keywords = [
        "urgent", "deadline", "emergency", "fix", "handle",
        "call landlord", "refund", "tenant issue", "medical", "school"
    ]

    # Q3: Admin, reactive, meetings that aren't essential
    q3_keywords = [
        "check-in", "email", "catch-up", "ping", "admin", "meeting", "call", "sync", "review with", "update"
    ]

    # If explicitly marked, override
    if "#q1" in text:
        return "I"
    if "#q2" in text:
        return "II"
    if "#q3" in text:
        return "III"

    if any(keyword in text for keyword in q1_keywords):
        return "I"
    if any(keyword in text for keyword in q3_keywords):
        return "III"

    # Default to Q2 — your designed time
    return "II"