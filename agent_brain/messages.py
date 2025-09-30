# agent_brain/messages.py
import random
from typing import Tuple, Optional, Dict
from beia_core.models.enums import Domain
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from feature_flags import ff_is_enabled

def build_domain_picker(event_id: str):
    """
    Build inline keyboard with all Domain enum values.
    event_id is needed so the callback can carry context.
    """
    buttons = []
    for d in Domain:
        buttons.append(
            [InlineKeyboardButton(f"{d.name.title()}", callback_data=f"domain|{event_id}|{d.name}")]
        )
    return InlineKeyboardMarkup(buttons)

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

# Compact callback encoding to stay within Telegram 64-char limit
CB_PREFIX = "wf0"  # workflow 0

def _cb(seg_id: str, code: str, arg: Optional[str] = None) -> str:
    return f"{CB_PREFIX}|{seg_id}|{code}" + (f"|{arg}" if arg else "")

def _tone_copy(tone: str, gentle: str, coach: str, ds: str, ds_on: bool) -> str:
    tone = (tone or "gentle").lower()
    if tone == "ds" and ds_on:
        return ds
    if tone == "coach":
        return coach
    return gentle

# ---------- START PROMPT ----------
def build_start_message(
    seg_id: str,
    title: str,
    tone: str,
    user_id: str,
    qii: bool = False,
    theme: Optional[str] = None,
) -> Tuple[str, InlineKeyboardMarkup]:
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    subtitle = []
    if qii: subtitle.append("QII")
    if theme: subtitle.append(f"Theme: {theme}")
    meta = f" — {' • '.join(subtitle)}" if subtitle else ""

    text = _tone_copy(
        tone,
        gentle=f"Ready to start *{title}*{meta}?",
        coach=f"Starting *{title}*{meta}. This matters — shall we begin?",
        ds=f"You're late to *{title}*{meta}. Starting now — confirm.",
        ds_on=ds_on
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Start", callback_data=_cb(seg_id, "START")),
            InlineKeyboardButton("🕔 5m",   callback_data=_cb(seg_id, "SNOOZE", "5")),
            InlineKeyboardButton("⏭ Skip",  callback_data=_cb(seg_id, "SKIP")),
            InlineKeyboardButton("✏️ Edit", callback_data=_cb(seg_id, "EDIT")),
        ]
    ])
    return text, kb

# ---------- MIDPOINT PROMPT ----------
def build_mid_message(
    seg_id: str,
    title: str,
    tone: str,
    user_id: str,
) -> Tuple[str, InlineKeyboardMarkup]:
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    text = _tone_copy(
        tone,
        gentle=f"Still on *{title}*?",
        coach=f"Halfway through *{title}*. On track to finish?",
        ds=f"Mark status for *{title}*: ✅ Done • 🛑 Miss • ↩ Pivot",
        ds_on=ds_on
    )
    if tone.lower() == "ds" and ds_on:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Done", callback_data=_cb(seg_id, "DONE")),
                InlineKeyboardButton("🛑 Miss", callback_data=_cb(seg_id, "DIDNT")),
                InlineKeyboardButton("↩ Pivot", callback_data=_cb(seg_id, "PIVOT")),
            ]
        ])
    else:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👍 Yes",   callback_data=_cb(seg_id, "MID_OK")),
                InlineKeyboardButton("+15m",     callback_data=_cb(seg_id, "EXT15")),
                InlineKeyboardButton("+30m",     callback_data=_cb(seg_id, "EXT30")),
                InlineKeyboardButton("↩ Pivot",  callback_data=_cb(seg_id, "PIVOT")),
            ]
        ])
    return text, kb

# ---------- END PROMPT ----------
def build_end_message(
    seg_id: str,
    title: str,
    tone: str,
    user_id: str,
) -> Tuple[str, InlineKeyboardMarkup]:
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    text = _tone_copy(
        tone,
        gentle=f"Wrap up *{title}*?",
        coach=f"Did we finish *{title}*? I'll reschedule if not.",
        ds=f"*{title}* ended — ✅ Complete • ❌ Miss • ↩ Pivot. No mark = Missed.",
        ds_on=ds_on
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Done",           callback_data=_cb(seg_id, "DONE")),
            InlineKeyboardButton("⏳ Need More",      callback_data=_cb(seg_id, "NEED_MORE")),
            InlineKeyboardButton("❌ Didn’t Start",   callback_data=_cb(seg_id, "DIDNT")),
        ]
    ])
    return text, kb

# ---------- DRIFT PROMPT ----------
def build_drift_message(seg_id: str, current_title: str) -> Tuple[str, InlineKeyboardMarkup]:
    text = f"You’re doing *{current_title}* instead. Adjust the plan?"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔀 Shift Schedule", callback_data=_cb(seg_id, "DRIFT_SHIFT")),
            InlineKeyboardButton("🙈 Keep As Is",      callback_data=_cb(seg_id, "DRIFT_KEEP")),
            InlineKeyboardButton("📝 Log Distraction", callback_data=_cb(seg_id, "DRIFT_LOG")),
        ]
    ])
    return text, kb

# ---------- FREE TIME PROMPT ----------
def build_free_time_message(
    seg_id: str,
    minutes: int,
    tone: str,
    user_id: str,
    theme_hint: Optional[str] = None
) -> Tuple[str, InlineKeyboardMarkup]:
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    hint = f" — *{theme_hint}*" if theme_hint else ""
    text = _tone_copy(
        tone,
        gentle=f"You’ve got {minutes}m free. Use it for:{hint}",
        coach=f"Let’s claim this {minutes}m gap. Choose one so it doesn’t vanish:{hint}",
        ds=f"Idle {minutes}m detected. Locking a recovery/theme block unless you choose now:{hint}",
        ds_on=ds_on
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Theme",   callback_data=_cb(seg_id, "FT_THEME")),
            InlineKeyboardButton("⚡ Quick Win", callback_data=_cb(seg_id, "FT_QWIN")),
            InlineKeyboardButton("🧹 Admin",   callback_data=_cb(seg_id, "FT_ADMIN")),
            InlineKeyboardButton("😌 Rest",    callback_data=_cb(seg_id, "FT_REST")),
        ]
    ])
    return text, kb

# ---------- CALLBACK PARSER ----------
# Returns a dict describing what to do:
#   { "kind": "fsm", "event": <Event>, "params": {...} }
# or{ "kind": "action", "code": "...", "params": {...} }
def parse_wf0_callback(data: str) -> Dict:
    try:
        prefix, seg_id, code, *rest = data.split("|")
    except ValueError:
        return {"kind": "error", "reason": "malformed"}

    if prefix != CB_PREFIX:
        return {"kind": "ignore"}

    arg = rest[0] if rest else None
    code = code.upper()

    # Map to FSM events (names match your fsm.Event members)
    if code == "START":
        return {"kind": "fsm", "event": "USER_START", "seg_id": seg_id}
    if code == "SNOOZE":
        minutes = int(arg or "5")
        return {"kind": "fsm", "event": "USER_SNOOZE", "seg_id": seg_id, "params": {"minutes": minutes}}
    if code == "SKIP":
        return {"kind": "fsm", "event": "USER_SKIP", "seg_id": seg_id}
    if code == "MID_OK":
        return {"kind": "fsm", "event": "TICK_MID", "seg_id": seg_id, "params": {"status": "ok"}}
    if code == "EXT15":
        return {"kind": "fsm", "event": "USER_EXTEND_15", "seg_id": seg_id}
    if code == "EXT30":
        return {"kind": "fsm", "event": "USER_EXTEND_30", "seg_id": seg_id}
    if code == "PIVOT":
        return {"kind": "fsm", "event": "USER_PIVOT", "seg_id": seg_id}
    if code == "DONE":
        return {"kind": "fsm", "event": "USER_DONE", "seg_id": seg_id}
    if code == "NEED_MORE":
        return {"kind": "fsm", "event": "USER_NEED_MORE", "seg_id": seg_id}
    if code == "DIDNT":
        return {"kind": "fsm", "event": "USER_DIDNT_START", "seg_id": seg_id}

    # Side actions (caller handles scheduler/db effects)
    if code in ("DRIFT_SHIFT", "DRIFT_KEEP", "DRIFT_LOG"):
        return {"kind": "action", "code": code, "seg_id": seg_id}
    if code.startswith("FT_"):  # FT_THEME / FT_QWIN / FT_ADMIN / FT_REST
        return {"kind": "action", "code": "FT_SELECT", "seg_id": seg_id, "params": {"choice": code[3:].lower()}}
    if code == "EDIT":
        return {"kind": "action", "code": "EDIT", "seg_id": seg_id}
    if code == "RESET_DAY":
        return {"kind": "action", "code": "RESET_DAY"}

    return {"kind": "error", "reason": "unknown_code", "seg_id": seg_id}
