# agent_brain/messages.py
import random

def event_created(title=None):
    return f"✅ I’ve added *{title}* to your schedule." if title else "✅ Event created."

def event_rescheduled(title=None):
    return f"🔁 Rescheduled *{title}* as requested." if title else "🔁 Event rescheduled."

def event_canceled(title=None):
    return f"🗑️ *{title}* has been removed from your agenda." if title else "🗑️ Event canceled."

def event_extended(title=None, minutes=None):
    return f"⏳ Extended *{title}* by {minutes} minutes." if title and minutes else "⏳ Event extended."

def event_renamed(old=None, new=None):
    return f"✏️ Renamed *{old}* to *{new}*." if old and new else "✏️ Event renamed."

def event_not_found():
    return "I couldn’t find that event."

def duration_response(minutes):
    return f"⏱️ That event lasts for {minutes} minutes."

def attendees_list(attendees):
    return f"👥 Attendees: {', '.join(attendees)}"

def no_attendees():
    return "No attendees found for that event."

def next_event(summary, minutes):
    return f"🕒 Your next event is *{summary}* in {minutes} minutes."

def no_upcoming_events():
    return "📭 You have no upcoming events today."

def whats_now(title, time):
    return f"🟢 Right now, you're on *{title}* ({time})."

def no_current_event(next_title=None, next_time=None):
    if next_title and next_time:
        choices = [
            f"You're free at the moment, but *{next_title}* is coming up at {next_time}.",
            f"Nothing scheduled right now. Next up: *{next_title}* at {next_time}.",
            f"📭 No event right now — your next is *{next_title}* at {next_time}.",
        ]
    else:
        choices = [
            "📭 You're not scheduled for anything at the moment.",
            "No events on right now — enjoy the peace! ☕",
            "You're all clear for now. Want to add something?",
        ]
    return random.choice(choices)

def no_agenda(label):
    options = {
        "now": [
            "📭 You're free right now — no events scheduled.",
            "Nothing happening at the moment. Breathe easy. 😌",
            "You’re not booked for anything right now. Want to add something?"
        ],
        "today": [
            "🕒 You have a clear day ahead. Perfect for focus.",
            "No scheduled events today. Time to make things happen.",
            "Your schedule looks empty today — shall we fill it?"
        ],
        "evening": [
            "🌙 No evening plans — enjoy your time!",
            "Evening's clear. Great time to unwind.",
            "Nothing on the books tonight."
        ],
    }

    return random.choice(options.get(label, ["📭 Nothing scheduled."]))

def unrecognized_action(action):
    return f"⚠️ I don’t recognize the action: `{action}`"

def fallback_reply():
    return "🧠 I'm not sure how to help with that."

def default_reply(reply):
    return reply

