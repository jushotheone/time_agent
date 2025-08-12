# ======================
# agent_brain/prompts.py
# ======================
from __future__ import annotations
from typing import Dict, Optional
from agent_brain.principles import COVEY_SYSTEM_PROMPT

# ----------------------------
# Legacy function (unchanged)
# ----------------------------
from gpt_agent import fallback_reply

def generate_followup_nudge(drift, suggestion):
    user_prompt = f"""
The user missed the scheduled block "{drift['summary']}".
Suggest a supportive next step:
- Reschedule?
- Reflect?
- Compress?
Keep it guilt-free, purpose-aligned, and gentle.
Respond in one short paragraph (<= 2 sentences).
"""
    full_prompt = COVEY_SYSTEM_PROMPT + "\n" + user_prompt
    return fallback_reply(full_prompt)

# ----------------------------
# Workflow #0 tone-aware LLM builders
# ----------------------------

def _tone_rules(tone: str) -> str:
    tone = (tone or "gentle").lower()
    if tone == "ds":
        return (
            "Tone: crisp, imperative, zero fluff. Max 1 sentence. "
            "Lead with action. No emojis. Use direct verbs."
        )
    if tone == "coach":
        return (
            "Tone: encouraging and focused. Max 1–2 short sentences. "
            "Affirm priority and invite commitment. Minimal warmth."
        )
    # gentle
    return (
        "Tone: warm and light. Max 1–2 short sentences. "
        "Keep it supportive and non-judgmental."
    )

def _constraints(extra: str = "") -> str:
    core = (
        "Keep under 180 characters. "
        "Do NOT invent buttons; align copy with the UI buttons shown to the user. "
        "No markdown beyond italics/bold already provided by UI, no emojis unless explicitly asked."
    )
    return (core + " " + extra).strip()

def _context_lines(title: str = "", qii: bool = False, theme: Optional[str] = None) -> str:
    parts = []
    if title:
        parts.append(f'Task: "{title}".')
    if qii:
        parts.append("Quadrant: QII (important, not urgent).")
    if theme:
        parts.append(f'Weekly Theme: "{theme}".')
    return " ".join(parts)

def start_prompt(
    title: str,
    tone: str,
    *,
    qii: bool = False,
    theme: Optional[str] = None,
) -> Dict[str, str]:
    """
    Buttons shown in UI: Start • 5m • Skip • Edit
    """
    system = COVEY_SYSTEM_PROMPT
    user = f"""
You are preparing a *start-of-block* message.
{_context_lines(title, qii, theme)}
Goal: secure an explicit Start OR a short Snooze OR a Skip.
{_tone_rules(tone)}
{_constraints("Mention the importance briefly if relevant (e.g., QII or theme), but keep it tight.")}
Write 1 line that pairs with these buttons: Start • 5m • Skip • Edit.
"""
    return {"system": system, "user": user.strip()}

def mid_prompt(
    title: str,
    tone: str,
) -> Dict[str, str]:
    """
    Buttons shown in UI:
      Gentle/Coach: Yes • +15m • +30m • Pivot
      DS: ✅ Done • 🛑 Miss • ↩ Pivot (the UI switches, but copy should still be generic)
    """
    system = COVEY_SYSTEM_PROMPT
    user = f"""
You are preparing a *midpoint heartbeat* message for the current block "{title}".
Goal: confirm progress or pivot/extend.
{_tone_rules(tone)}
{_constraints("Be explicit about choosing to continue or adjust.")}
Write 1 line that pairs with these possible buttons:
- Normal: Yes • +15m • +30m • Pivot
- DS mode: ✅ Done • 🛑 Miss • ↩ Pivot
"""
    return {"system": system, "user": user.strip()}

def end_prompt(
    title: str,
    tone: str,
) -> Dict[str, str]:
    """
    Buttons shown in UI: Done • Need More • Didn’t Start
    """
    system = COVEY_SYSTEM_PROMPT
    user = f"""
You are preparing an *end-of-block* closure message for "{title}".
Goal: mark outcome cleanly to keep schedule accurate.
{_tone_rules(tone)}
{_constraints("Push for clarity: either Done, Need More (reschedule), or Didn’t Start.")}
Write 1 line that pairs with these buttons: Done • Need More • Didn’t Start.
"""
    return {"system": system, "user": user.strip()}

def free_time_prompt(
    gap_minutes: int,
    tone: str,
    *,
    theme_hint: Optional[str] = None,
) -> Dict[str, str]:
    """
    Buttons shown in UI: Theme • Quick Win • Admin • Rest
    """
    theme_text = f'Focus hint: "{theme_hint}".' if theme_hint else ""
    system = COVEY_SYSTEM_PROMPT
    user = f"""
You are preparing a *free-time* intent message.
Gap length: {gap_minutes} minutes. {theme_text}
Goal: help the user claim the gap intentionally.
{_tone_rules(tone)}
{_constraints("Nudge to choose an option, not to chat.")}
Write 1 line that pairs with these buttons: Theme • Quick Win • Admin • Rest.
"""
    return {"system": system, "user": user.strip()}

def drift_prompt(
    current_title: str,
    tone: str,
) -> Dict[str, str]:
    """
    Buttons shown in UI: Shift Schedule • Keep As Is • Log Distraction
    """
    system = COVEY_SYSTEM_PROMPT
    user = f"""
The user has drifted and is now doing "{current_title}" instead of the planned block.
We need a concise drift message to realign the day.
{_tone_rules(tone)}
{_constraints("Make the tradeoff visible but not shaming.")}
Write 1 line that pairs with these buttons: Shift Schedule • Keep As Is • Log Distraction.
"""
    return {"system": system, "user": user.strip()}

# Optional helper for callers:
def build_llm_payload(kind: str, **kwargs) -> Dict[str, str]:
    """
    Convenience router so callers can do:
      payload = build_llm_payload("start", title="Deep Work", tone="coach", qii=True, theme="Hiring")
    """
    kind = kind.lower()
    if kind == "start":
        return start_prompt(**kwargs)
    if kind == "mid":
        return mid_prompt(**kwargs)
    if kind == "end":
        return end_prompt(**kwargs)
    if kind == "free_time":
        return free_time_prompt(**kwargs)
    if kind == "drift":
        return drift_prompt(**kwargs)
    raise ValueError(f"Unknown prompt kind: {kind}")