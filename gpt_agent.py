import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import zoneinfo
from datetime import datetime

load_dotenv()

# Timezone-aware datetime
TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))
now = datetime.now(TZ)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM = f"""
You are a highly capable personal AI calendar assistant, working for a busy entrepreneur.

🕒 Today is {now.strftime('%A, %d %B %Y')}, and the current time is {now.strftime('%H:%M')} ({TZ} timezone).
Always use this as your reference when interpreting phrases like "tomorrow", "next Friday", or "after lunch".

🎯 Your job is to convert natural, casual human speech into structured scheduling instructions, using a function call.

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
    }
]

def parse(text: str) -> Optional[Dict[str, Any]]:
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"{text}\nToday is {now.strftime('%A %d %B %Y')}, and current time is {now.strftime('%H:%M')} in Europe/London timezone."
                }
            ],
            tools=[{"type": "function", "function": tool} for tool in TOOL_DEFS],
            tool_choice="auto",
            temperature=0.2,
        )

        message = response.choices[0].message

        # ✅ If it calls a function (like create_event, cancel_event)
        if message.tool_calls:
            function_call = message.tool_calls[0].function
            args = json.loads(function_call.arguments)
            args["action"] = function_call.name
            args["reply"] = message.content or f"✅ {function_call.name.replace('_', ' ').title()} complete."
            return args

        # ✅ If it didn't call a function, fallback to human-style reply
        elif message.content:
            return {
                "action": "chat_fallback",
                "reply": message.content
            }

    except Exception as e:
        print("OpenAI error:", e)

    return None

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
