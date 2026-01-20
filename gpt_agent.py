import os
import json
import re
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import zoneinfo
from datetime import datetime, date
from agent_brain.principles import COVEY_SYSTEM_PROMPT
from feature_flags import ff

load_dotenv()

# Timezone-aware datetime
TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

conversation_history = []

def reset_conversation():
    """Clears the in-memory conversation history (useful between tasks)."""
    global conversation_history
    conversation_history.clear()

SYSTEM = """
You are a highly capable personal AI calendar assistant, working for a busy entrepreneur.

🕒 Today is {today}, and the current time is {current_time} ({timezone} timezone).
Always use this as your reference when interpreting phrases like "tomorrow", "next Friday", or "after lunch".

🎯 Your job is to convert natural, casual human speech into structured scheduling instructions, using a function call.

If the user says they are tired, need rest, or want to push the current event forward, suggest a reschedule.
If the user asks “how long is my meeting” or “who is attending”, use the duration or attendee tools.
Use describe_event to give full metadata when the user wants full context of a meeting.

You can perform these actions:
- create_event: Add a new calendar event
- reschedule_event: Change the time of an existing event
- cancel_event: Remove a calendar event
- get_agenda: Summarise today’s, tomorrow’s, or this week’s schedule

Always extract these fields when scheduling:
- title: What the user is doing
- date: YYYY-MM-DD (in the future)
- time: 24-hour format HH:MM
- duration_minutes: Estimate duration (default to 60 mins if unclear)

✅ Always assume the user wants the event in the future unless they clearly state otherwise.
⛔ Never create or move events to the past.
👂 Be conversational, natural, and helpful — like a real assistant.

You can respond to these time-based queries with the `get_agenda` tool:

- "What’s this morning?" → range = "morning"
- "What’s this afternoon?" → range = "afternoon"
- "What’s this evening?" → range = "evening"
- "What was I doing yesterday?" → range = "yesterday"
- "What’s next?" → range = "next"
- "What am I doing now?" → range = "now"
"""

CONVERSATION_MODE_SYSTEM = """
You are a warm, intelligent personal assistant for a busy entrepreneur.

If the user’s message doesn’t include a clear scheduling action, offer helpful suggestions or follow-up questions based on their calendar and focus goals.

You’re proactive, supportive, and focused on helping the user use their time wisely.

Always stay on-topic with time management, focus, and daily priorities — no chit-chat.
"""

TOOL_DEFS = [
    {
        "name": "create_event",
        "description": "Add a new calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "duration_minutes": {"type": "integer"}
            },
            "required": ["title", "date", "time", "duration_minutes"]
        }
    },
    {
        "name": "reschedule_event",
        "description": "Change an existing event to a new time",
        "parameters": {
            "type": "object",
            "properties": {
                "original_title": {"type": "string"},
                "new_date": {"type": "string"},
                "new_time": {"type": "string"}
            },
            "required": ["original_title", "new_date", "new_time"]
        }
    },
    {
        "name": "cancel_event",
        "description": "Cancel a calendar event",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string"}
            },
            "required": ["title", "date"]
        }
    },
    {
        "name": "get_agenda",
        "description": "Summarise the user's calendar for a given time range (e.g. 'today', 'tomorrow', or phrases like 'next Monday morning')",
        "parameters": {
            "type": "object",
            "properties": {
            "range": {
                "type": "string",
                "description": "Time period to show events for. Can be 'today', 'tomorrow', 'morning', or a natural phrase like 'next Tuesday afternoon'."
            }
            },
            "required": ["range"]
        }
    },
    {
        "name": "extend_event",
        "description": "Extend the duration of an existing event",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "additional_minutes": {"type": "integer"}
            },
            "required": ["title", "additional_minutes"]
        }
    },
    {
        "name": "rename_event",
        "description": "Change the title of an existing event on a specific date",
        "parameters": {
            "type": "object",
            "properties": {
                "original_title": {"type": "string"},
                "new_title": {"type": "string"},
                "date": {"type": "string", "description": "Date of the event in YYYY-MM-DD"}
            },
            "required": ["original_title", "new_title", "date"]
        }
    },
    {
        "name": "get_event_duration",
        "description": "Check how long a scheduled event is",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string"}
            },
            "required": ["title", "date"]
        }
    },
    {
        "name": "get_time_until_next_event",
        "description": "Find out how much time is left before the next scheduled event starts",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "describe_event",
        "description": "Get full metadata for a calendar event including time, location, attendees, recurrence",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string"}
            },
            "required": ["title", "date"]
        }
    },
    {
        "name": "list_attendees",
        "description": "List the people invited to a given meeting",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "date": {"type": "string"}
            },
            "required": ["title", "date"]
        }
    },
    {
        "name": "log_event_action",
        "description": "Track when events are created, updated, or deleted for audit history",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "action": {"type": "string"},  # create, update, delete
                "timestamp": {"type": "string"}
            },
            "required": ["event_id", "action", "timestamp"]
        }
    }
]

def parse(text: str) -> Optional[Dict[str, Any]]:
        # 🧹 Listen for memory reset commands
    if text.strip().lower() in ["reset", "clear memory", "start over", "forget what i said"]:
        reset_conversation()
        return {
            "action": "reset",
            "reply": "🧠 Conversation memory cleared. Let’s start fresh — what would you like to do?"
        }
    try:
        # 🕒 Always fetch fresh timestamp
        now = datetime.now(TZ)
        system_prompt = SYSTEM.format(
            today=now.strftime('%A, %d %B %Y'),
            current_time=now.strftime('%H:%M'),
            timezone=TZ
        )

        # 💬 Save this user message
        conversation_history.append({"role": "user", "content": text})
        if len(conversation_history) > 6:
            conversation_history.pop(0)

        # 🧠 Build full message list with memory
        messages = [{"role": "system", "content": system_prompt}] + conversation_history

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[{"type": "function", "function": tool} for tool in TOOL_DEFS],
            tool_choice="auto",
            temperature=0.3,
        )

        message = response.choices[0].message

        if message.tool_calls:
            function_call = message.tool_calls[0].function
            args = json.loads(function_call.arguments)
            args["action"] = function_call.name
            args["reply"] = message.content or f"✅ {function_call.name.replace('_', ' ').title()} complete."
        else:
            args = {
                "action": "chat_fallback",
                "reply": message.content
            }

        # 💬 Save assistant reply
        conversation_history.append({"role": "assistant", "content": args["reply"]})
        if len(conversation_history) > 6:
            conversation_history.pop(0)

        return args

    except Exception as e:
        print("OpenAI error:", e)
        return {
            "action": "error",
            "reply": "⚠️ Sorry, something went wrong while processing your request."
        }

def fallback_reply(text: str) -> Optional[str]:
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CONVERSATION_MODE_SYSTEM},
                {"role": "user", "content": text}
            ],
            temperature=0.6
        )
        return response.choices[0].message.content
    except Exception as e:
        print("OpenAI fallback error:", e)
        return "Hmm, I wasn’t sure how to help with that, but I’m here if you need help with your day."

def create_reminder_message(event_title: str, phase: str = "before") -> str:
    """
    Use GPT to generate motivational reminder message for a given event.
    """
    phase_text = {
        "before": "10 mins before the event",
        "during": "in the first few minutes of the event",
        "after": "just after the scheduled end time"
    }.get(phase, "at the appropriate time")

    prompt = f"""{COVEY_SYSTEM_PROMPT}

You're a motivational, time-aware assistant helping a busy entrepreneur steward their time.

⏰ It's currently the *{phase}* phase — {phase_text}.

Generate a short message (1–2 lines) to send as a reminder for this event:
“{event_title}”

Respond with only the message to send. Be natural, supportive, and purpose-aligned.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("GPT Reminder error:", e)
        if phase == "before":
            return f"⏰ Reminder: {event_title} is starting soon."
        elif phase == "during":
            return f"🚀 Just checking in — are you focused on {event_title}?"
        else:
            return f"✅ Finished with {event_title}? Great job!"
        
def generate_nudge(event, context):
    from jinja2 import Template
    with open("prompts/daily_review.txt") as f:
        template = Template(f.read())

    body = template.render(event=event, context=context)
    full_prompt = COVEY_SYSTEM_PROMPT + "\n" + body

    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": full_prompt}]
    )

    reply = res.choices[0].message["content"]
    return reply.strip() if "❌" not in reply else None




# --- add near the bottom of gpt_agent.py ---
def llm_tone_polish(text: str, tone: str, context: dict | None = None) -> str:
    """
    Optional: Rewrite a short message in the requested tone ('gentle'|'coach'|'ds').
    Guarded by WF0_LLM_TONE. Returns input text unchanged if flag is off or error occurs.
    """
    if not ff.enabled("WF0_LLM_TONE"):
        return text

    try:
        system = (
            "You are a time-discipline assistant. Rewrite the user's short message "
            "to match the requested tone:\n"
            "- gentle: warm, supportive, brief\n"
            "- coach: firm, encouraging, goal-aligned\n"
            "- ds: direct, no-nonsense, concise\n"
            "Keep buttons/emoji if present; do not add new actions."
        )
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"TONE={tone}\nCONTEXT={context or {}}\nTEXT:\n{text}"}
        ]
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=msgs,
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("LLM tone polish error:", e)
        return text
    
# ----------------------------
# Deterministic Chat Protocol (Contract)
# ----------------------------
_CMD_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\b")
_CMD_INT_RE  = re.compile(r"\b(\d{1,3})\b")


def parse_command(text: str) -> Optional[Dict[str, Any]]:
    """Deterministic command parser for contract-style chat commands.

    This MUST NOT use OpenAI. It returns a stable dict schema so the router can
    execute without Telegram UI.

    Supported commands:
      - DONE <title>
      - DIDNT START <title>
      - NEED MORE <title> <minutes>
      - RESCHEDULE <title> <HH:MM>
      - MOVE NEXT <title>
      - SKIP <title>
      - SUMMARY today | SUMMARY YYYY-MM-DD
      - WHAT DID I MISS today | WHAT DID I MISS YYYY-MM-DD
      - PAUSE
      - SNOOZE 5 | SNOOZE 15
      - I'M DOING <x> / IM DOING <x>
    """
    raw = (text or "").strip()
    if not raw:
        return None

    upper = raw.upper()

    # DONE <title...>
    if upper.startswith("DONE "):
        return {"action": "done", "title": raw[5:].strip()}

    # DIDNT START <title...>
    if upper.startswith("DIDNT START "):
        return {"action": "didnt_start", "title": raw[len("DIDNT START "):].strip()}

    # NEED MORE <title...> <minutes>
    if upper.startswith("NEED MORE "):
        rest = raw[len("NEED MORE "):].strip()
        m = re.search(r"(\d+)\s*$", rest)
        if not m:
            return {"action": "need_more", "title": rest, "minutes": None}
        minutes = int(m.group(1))
        title = rest[: m.start(1)].strip()
        return {"action": "need_more", "title": title, "minutes": minutes}

    # RESCHEDULE <title...> <HH:MM>
    if upper.startswith("RESCHEDULE "):
        rest = raw[len("RESCHEDULE "):].strip()
        m = _CMD_TIME_RE.search(rest)
        if not m:
            return {"action": "reschedule", "title": rest, "new_time": None}
        hhmm = m.group(0)
        title = (rest[:m.start()] + rest[m.end():]).strip()
        return {"action": "reschedule", "title": title, "new_time": hhmm}

    # MOVE NEXT <title...>
    if upper.startswith("MOVE NEXT "):
        return {"action": "move_next", "title": raw[len("MOVE NEXT "):].strip()}

    # SKIP <title...>
    if upper.startswith("SKIP "):
        return {"action": "skip", "title": raw[len("SKIP "):].strip()}

    # SUMMARY today | SUMMARY YYYY-MM-DD
    if upper.startswith("SUMMARY"):
        rest = raw[len("SUMMARY"):].strip()
        if rest.lower() == "today" or rest == "":
            return {"action": "summary", "date": "today"}
        return {"action": "summary", "date": rest}

    # WHAT DID I MISS today | WHAT DID I MISS YYYY-MM-DD
    if upper.startswith("WHAT DID I MISS"):
        rest = raw[len("WHAT DID I MISS"):].strip()
        if rest.lower() == "today" or rest == "":
            return {"action": "misses", "date": "today"}
        return {"action": "misses", "date": rest}

    # PAUSE
    if upper == "PAUSE":
        return {"action": "pause"}

    # SNOOZE 5 / SNOOZE 15
    if upper.startswith("SNOOZE"):
        rest = raw[len("SNOOZE"):].strip()
        try:
            minutes = int(rest)
        except Exception:
            minutes = None
        return {"action": "snooze", "minutes": minutes}

    # I'M DOING <x>  (accept both I'M and IM)
    if upper.startswith("I'M DOING ") or upper.startswith("IM DOING "):
        prefix_len = len("I'M DOING ") if upper.startswith("I'M DOING ") else len("IM DOING ")
        return {"action": "drift", "title": raw[prefix_len:].strip()}

    return None