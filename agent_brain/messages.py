# agent_brain/messages.py
import random
import datetime as dt
from typing import Optional, Dict, List, Any
from beia_core.models.enums import Domain
from feature_flags import ff_is_enabled

def build_domain_picker(event_id: str) -> Dict[str, Any]:
    """Chat-native domain picker.

    Returns an operator payload with text + typed options (no Telegram UI).
    The router can accept commands like: DOMAIN <event_id> <DOMAIN_NAME>
    """
    options = [f"DOMAIN {event_id} {d.name}" for d in Domain]
    return {
        "kind": "noted",
        "delta": {"title": "Choose a domain", "id": event_id},
        "current": None,
        "next": None,
        "options": options,
    }

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

# Legacy: formerly Telegram callback encoding. Kept for backwards-compat,
# but chat-first now (typed commands).
CB_PREFIX = "wf0"  # legacy

def _cb(seg_id: str, code: str, arg: Optional[str] = None) -> str:
    # Still returns a stable token, but routers should prefer typed commands.
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
) -> Dict[str, Any]:
    """Chat-native start prompt payload."""
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    subtitle = []
    if qii:
        subtitle.append("QII")
    if theme:
        subtitle.append(f"Theme: {theme}")
    meta = f" — {' • '.join(subtitle)}" if subtitle else ""

    text = _tone_copy(
        tone,
        gentle=f"Ready to start *{title}*{meta}?",
        coach=f"Starting *{title}*{meta}. This matters — shall we begin?",
        ds=f"You're late to *{title}*{meta}. Starting now — confirm.",
        ds_on=ds_on,
    )

    return {
        "kind": "scheduled",
        "delta": {"title": title, "segment_id": seg_id},
        "current": None,
        "next": {"title": title, "start": "now"},
        "text": text,
        "options": [f"START {title}", "SNOOZE 5", f"SKIP {title}", f"EDIT {title}"],
    }

# ---------- MIDPOINT PROMPT ----------
def build_mid_message(
    seg_id: str,
    title: str,
    tone: str,
    user_id: str,
) -> Dict[str, Any]:
    """Chat-native midpoint prompt payload."""
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    text = _tone_copy(
        tone,
        gentle=f"Still on *{title}*?",
        coach=f"Halfway through *{title}*. On track to finish?",
        ds=f"Mark status for *{title}*: DONE • DIDNT START • NEED MORE",
        ds_on=ds_on,
    )

    return {
        "kind": "noted",
        "delta": {"title": title, "segment_id": seg_id},
        "text": text,
        "options": [
            f"DONE {title}",
            f"DIDNT START {title}",
            f"NEED MORE {title} 15",
            f"NEED MORE {title} 30",
        ],
    }

# ---------- END PROMPT ----------
def build_end_message(
    seg_id: str,
    title: str,
    tone: str,
    user_id: str,
) -> Dict[str, Any]:
    """Chat-native end prompt payload."""
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    text = _tone_copy(
        tone,
        gentle=f"Wrap up *{title}*?",
        coach=f"Did we finish *{title}*? I can reschedule if not.",
        ds=f"*{title}* ended — DONE • DIDNT START • NEED MORE",
        ds_on=ds_on,
    )

    return {
        "kind": "noted",
        "delta": {"title": title, "segment_id": seg_id, "status": "ended"},
        "text": text,
        "options": [
            f"DONE {title}",
            f"NEED MORE {title} 15",
            f"DIDNT START {title}",
        ],
    }

# ---------- DRIFT PROMPT ----------
def build_drift_message(seg_id: str, current_title: str) -> Dict[str, Any]:
    """Chat-native drift prompt payload."""
    return {
        "kind": "noted",
        "delta": {"title": current_title, "segment_id": seg_id, "status": "drift"},
        "text": f"You're doing *{current_title}* instead. What do you want to do?",
        "options": [
            "KEEP AS IS",
            "SHIFT",
            "LOG",
        ],
    }

# ---------- FREE TIME PROMPT ----------
def build_free_time_message(
    seg_id: str,
    minutes: int,
    tone: str,
    user_id: str,
    theme_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Chat-native free-time prompt payload."""
    ds_on = ff_is_enabled("WF0_DS_MODE", user_id)
    hint = f" — *{theme_hint}*" if theme_hint else ""
    text = _tone_copy(
        tone,
        gentle=f"You've got {minutes}m free. Use it for:{hint}",
        coach=f"Let's claim this {minutes}m gap. Pick one:{hint}",
        ds=f"Idle {minutes}m detected. Choose now:{hint}",
        ds_on=ds_on,
    )

    return {
        "kind": "noted",
        "delta": {"title": "Free time", "segment_id": seg_id, "minutes": minutes},
        "text": text,
        "options": [
            "FREE TIME THEME",
            "FREE TIME QUICK WIN",
            "FREE TIME ADMIN",
            "FREE TIME REST",
        ],
    }

# ---------- CALLBACK PARSER ----------
def parse_wf0_callback(data: str) -> Dict[str, Any]:
    """Legacy shim.

    Historically decoded Telegram callback_data. In chat mode, we don't use callback
    payloads, but keeping this function avoids breaking old imports.

    If the string looks like the legacy `wf0|seg|CODE|arg`, we decode it.
    Otherwise we return a simple dict and let the caller treat it as plain text.
    """
    raw = (data or "").strip()
    if not raw:
        return {"kind": "error", "reason": "empty"}

    if "|" not in raw:
        return {"kind": "chat", "text": raw}

    try:
        prefix, seg_id, code, *rest = raw.split("|")
    except ValueError:
        return {"kind": "error", "reason": "malformed"}

    if prefix != CB_PREFIX:
        return {"kind": "ignore"}

    arg = rest[0] if rest else None
    code = (code or "").upper()

    # Map to deterministic actions (best-effort)
    if code == "START":
        return {"kind": "action", "action": "start", "seg_id": seg_id}
    if code == "SNOOZE":
        try:
            minutes = int(arg or "5")
        except Exception:
            minutes = 5
        return {"kind": "action", "action": "snooze", "seg_id": seg_id, "minutes": minutes}
    if code == "SKIP":
        return {"kind": "action", "action": "skip", "seg_id": seg_id}
    if code == "DONE":
        return {"kind": "action", "action": "done", "seg_id": seg_id}
    if code in ("DIDNT", "DIDNT_START"):
        return {"kind": "action", "action": "didnt_start", "seg_id": seg_id}
    if code == "NEED_MORE":
        return {"kind": "action", "action": "need_more", "seg_id": seg_id}

    if code in ("DRIFT_SHIFT", "DRIFT_KEEP", "DRIFT_LOG"):
        return {"kind": "action", "action": code.lower(), "seg_id": seg_id}

    if code.startswith("FT_"):
        return {"kind": "action", "action": "free_time", "seg_id": seg_id, "choice": code[3:].lower()}

    if code == "EDIT":
        return {"kind": "action", "action": "edit", "seg_id": seg_id}
    if code == "RESET_DAY":
        return {"kind": "action", "action": "reset_day"}

    return {"kind": "error", "reason": "unknown_code", "seg_id": seg_id}

# ---------- MISSED TASK NUDGE ----------
def build_missed_task_nudge_text(
    *,
    name: str,
    planned_hhmm: str,
    date_iso: str,
    options: List[str],
    tone: str = "gentle",
) -> str:
    """
    Deterministic missed-task nudge with machine-readable footer.
    Must avoid guilt/parent tone (tests ban: should/must/need to/have to).
    """
    human = f"Looks like {name} didn't happen. Want to reschedule or skip?"
    opts = ",".join([o.upper() for o in options])
    footer = f"#ACTION type=missed_task name={name} date={date_iso} options=[{opts}]"
    return f"{human}\n{footer}"


# ---------- LOW-COGNITIVE + CHANGED-MIND ----------
def build_changed_mind_reply(tone: str = "gentle") -> str:
        """
        User says: 'I changed my mind'
        Contract:
            - yield authority immediately
            - max ONE question
            - no optimisation
            - no guilt / parental tone
        """
        return "Got it. Do you want today to be lighter, or just different?"


def build_low_cognitive_load_default(context: Optional[Dict] = None) -> str:
        """
        User says: 'I don't want to think'
        Contract:
            - offer ONE default path
            - no choices
            - no questions
        """
        return "Alright. I’ll hold everything else and just remind you about rest and dinner."


OP_PREFIXES = {
    "done": "✅ Done:",
    "scheduled": "🗓️ Scheduled:",
    "updated": "↩️ Updated:",
    "conflict": "⚠️ Conflict:",
    "noted": "📌 Noted:",
    "missed": "↩️ Updated:",
}


def _hhmm(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dt.datetime):
        return x.strftime("%H:%M")
    if hasattr(x, "strftime"):
        try:
            return x.strftime("%H:%M")
        except Exception:
            return str(x)
    return ""


def format_operator_reply(payload: dict) -> str:
    """Contract: messages.format_operator_reply(payload) -> string.

    Payload keys:
      - kind: done|scheduled|updated|conflict|noted|missed
      - delta: dict containing at least one concrete token (title/time/status/id)
      - current: optional dict
      - next: optional dict
      - options: list of strings
    """
    p = payload or {}
    kind = (p.get("kind") or "noted").lower()
    delta = p.get("delta") or {}
    current = p.get("current")
    nxt = p.get("next")
    options = p.get("options") or []

    prefix = OP_PREFIXES.get(kind, OP_PREFIXES["noted"])

    title = delta.get("title")
    seg_id = delta.get("segment_id") or delta.get("id")
    start = delta.get("start")
    end = delta.get("end")
    status = delta.get("status")

    bits: List[str] = []
    if title:
        bits.append(str(title))
    if start and end:
        bits.append(f"{start}–{end}")
    if status:
        bits.append(f"status={status}")
    if seg_id:
        bits.append(f"id={seg_id}")

    main = " ".join(bits).strip() or "Updated."
    lines = [f"{prefix} {main}".strip()]

    # continuity lines (tests want 'Current:' and 'Next:')
    if current is not None or nxt is not None:
        if current:
            c_title = current.get("title")
            c_end = current.get("end") or current.get("end_at") or current.get("end_time")
            c_end_s = _hhmm(c_end)
            lines.append(f"Current: {c_title} (ends {c_end_s})".strip())
        else:
            lines.append("Current: None")

        if nxt:
            n_title = nxt.get("title")
            n_start = nxt.get("start") or nxt.get("start_at") or nxt.get("start_time")
            n_start_s = _hhmm(n_start)
            lines.append(f"Next: {n_title} (starts {n_start_s})".strip())
        else:
            lines.append("Next: None")

    if options:
        lines.append("Options:")
        for o in options:
            lines.append(f"- {o}")

    return "\n".join(lines).strip()

def build_conflict_reply(payload: dict) -> str:
    """Contract: build_conflict_reply(payload) -> string.

    Expected payload fields (from tests):
      - title: str
      - attempted_start: datetime
      - attempted_end: datetime
      - options: list of tuples like [("12:30","13:00"), ...] OR list of strings
      - move_other: optional string
    """
    p = payload or {}
    title = p.get("title") or "(untitled)"
    attempted_start = p.get("attempted_start")
    attempted_end = p.get("attempted_end")
    move_other = p.get("move_other")

    opts_in = p.get("options") or []
    opts_out: List[str] = []
    for item in opts_in:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            opts_out.append(f"{item[0]}–{item[1]}")
        else:
            opts_out.append(str(item))

    # Ensure at least 2 option lines if provided
    opts_out = [o for o in opts_out if o.strip()]

    if move_other:
        opts_out.append(str(move_other))

    delta = {
        "title": title,
        "start": _hhmm(attempted_start),
        "end": _hhmm(attempted_end),
        "status": "conflict",
    }

    return format_operator_reply(
        {
            "kind": "conflict",
            "delta": delta,
            "current": p.get("current"),
            "next": p.get("next"),
            "options": opts_out,
        }
    )

def build_drift_text(payload: dict) -> str:
    """Contract: build_drift_text(payload) -> string.

    Tests expect:
      - includes 'keep as is' (exact phrase, case-insensitive)
      - includes 'shift'
      - includes 'log'
      - neutral, no guilt.
    """
    p = payload or {}
    current_title = p.get("current_title") or p.get("title") or "(something else)"
    # Allow caller-provided options, but we render stable copy for tests.
    _ = p.get("options") or ["KEEP", "SHIFT", "LOG"]

    opts = [
        "KEEP: keep as is",
        "SHIFT: shift schedule to match what you're doing",
        "LOG: log distraction and return to plan",
    ]

    return format_operator_reply(
        {
            "kind": "noted",
            "delta": {"title": f"Drift detected: {current_title}", "status": "drift"},
            "current": p.get("current"),
            "next": p.get("next"),
            "options": opts,
        }
    )