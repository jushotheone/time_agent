# ======================
# agent_brain/prompts.py
# ======================
from gpt_agent import fallback_reply
from agent_brain.principles import COVEY_SYSTEM_PROMPT

def generate_followup_nudge(drift, suggestion):
    user_prompt = f"""
The user missed the scheduled block "{drift['summary']}".
Suggest a supportive next step:
- Reschedule?
- Reflect?
- Compress?
Keep it guilt-free, purpose-aligned, and gentle.
"""
    full_prompt = COVEY_SYSTEM_PROMPT + "\n" + user_prompt
    return fallback_reply(full_prompt)