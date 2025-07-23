import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import zoneinfo
from datetime import datetime
from agent_brain.principles import COVEY_SYSTEM_PROMPT

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