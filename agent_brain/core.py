# ======================
# agent_brain/core.py
# ======================
import os
from telegram import Bot
from openai import AsyncOpenAI  # ✅ Use the async client
import calendar_client
from db import get_user_context
from agent_brain.observer import detect_drift
from agent_brain.scheduler import propose_adjustment
from agent_brain.prompts import generate_followup_nudge
from agent_brain.state import log_event_status
from agent_brain.principles import COVEY_SYSTEM_PROMPT
import datetime as dt
from db import get_user_context, get_recent_conversation, save_conversation_turn, clear_conversation_history


async def run_brain():
    print("🧠 [run_brain] Checking for drift...")
    drift = detect_drift()

    if not drift:
        print("✅ [run_brain] No drift detected.")
        return

    print(f"⚠️ [run_brain] Drift detected: {drift['summary']} ({drift['status']})")

    suggestion = propose_adjustment(drift)
    print(f"🛠️ [run_brain] Proposed adjustment: {suggestion}")

    message = generate_followup_nudge(drift, suggestion)
    print(f"📩 [run_brain] GPT Nudge:\n{message}\n")

    log_event_status(drift["event_id"], drift["status"])
    print("📚 [run_brain] Event status logged.")

    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    await bot.send_message(
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        text=message,
        parse_mode="Markdown"
    )
    print("📤 [run_brain] Message sent to Telegram.")
    
    
async def conversational_brain(user_message: str) -> str:
    user_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if user_message.lower().strip() in ["reset", "start over", "clear memory"]:
        clear_conversation_history(user_id)
        return "🧠 Memory cleared. Let's begin fresh — what would you like to focus on today?"

    context = get_user_context(user_id=user_id, now=dt.datetime.utcnow()) or {}
    current_event = calendar_client.get_current_and_next_event().get("current")

    current_summary = current_event.get("summary") if current_event else "None"
    focus = context.get("focus", "No focus set")
    energy = context.get("energy", "Unknown")

    system_prompt = f"""
{COVEY_SYSTEM_PROMPT}

You are a time-stewardship assistant, helping the user manage their calendar.

Instructions:
- If the user prompt includes an agenda (e.g. lines starting with 🗓️, ⏳, ✅), summarize that info directly.
- Be concise and focused. Only offer reflective advice if the user asks for it.
- Always respond with direct value **first** (agenda, event info, durations) before optional insights.
- Never ignore or rephrase event summaries. Treat them as the user's source of truth.
- Respond in plain English, not philosophical abstraction.

Context:
- Current Event: {current_summary}
- Weekly Focus: {focus}
- Energy Level: {energy}
""".strip()

    history = get_recent_conversation(user_id)

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages
    )

    reply = response.choices[0].message.content.strip()

    # ✅ Save to conversation memory
    save_conversation_turn(user_id, "user", user_message)
    save_conversation_turn(user_id, "assistant", reply)

    return reply