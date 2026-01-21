# agent_brain/actions.py

import os
import datetime as dt
import calendar_client as cal
from calendar_client import rename_event
from zoneinfo import ZoneInfo
from agent_brain import messages as msg
from agent_brain.respond import respond_with_brain
# NEW imports (keep existing ones)
from agent_brain import prompts
from agent_brain import scheduler as sched   # centralize calendar reflows here
import beia_core.models.timebox as db                                    # segment/day_state writes
from feature_flags import ff
from agent_brain.fsm import Tone
import logging

TZ = ZoneInfo(os.getenv("TIMEZONE", "UTC"))

# -- Core event actions --
# -- Core event actions --
async def create_event(parsed, update=None, context=None):
    """
    Create a calendar event, then immediately handle domain intake.
    If domain is missing, prompt user in Telegram to classify it.
    """
    title = parsed['title']
    date = parsed['date']
    time = parsed['time']
    duration = parsed.get('duration_minutes', 60)
    start = dt.datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=TZ)

    # 1. Create the calendar event
    event = cal.create_event(
        title,
        start,
        duration,
        parsed.get('attendees'),
        parsed.get('recurrence')
    )

    # 2. Try to guess domain from title keywords
    from beia_core.models.enums import Domain
    title_lower = title.lower()
    domain = None
    for d in Domain:
        if d.name in title_lower or d.value.lower() in title_lower:
            domain = d
            break

    # 3. If not guessed, prompt user in Telegram
    if not domain and update and context:
        domain_options = ", ".join([d.name for d in Domain])
        await respond_with_brain(
            update,
            context,
            {"action": "classify_event_domain", "title": title},
            summary=(
                f"🗂 New event created: *{title}* on {date} at {time}.\n\n"
                f"Which domain does this belong to?\nOptions: {domain_options}"
            )
        )

    # 4. Persist in DB (timebox / segment entry)
    try:
        db.insert_event_with_domain(
            event_id=event.get("id"),
            title=title,
            start_at=start,
            duration=duration,
            domain=domain.name if domain else None,
        )
    except Exception:
        logging.exception("[Actions] Failed to persist event with domain info")

    # 5. Send normal event confirmation
    summary = format_event_description(event)
    logging.info(f"[Actions] Sending Telegram message: {summary}")
    if update and context:
        await respond_with_brain(update, context, parsed, summary=summary)

    return event

def reschedule_event(parsed):
    new_start = dt.datetime.fromisoformat(f"{parsed['new_date']}T{parsed['new_time']}").replace(tzinfo=TZ)
    cal.reschedule_event(parsed['original_title'], new_start)

def cancel_event(parsed):
    cal.cancel_event(parsed['title'], parsed['date'])

def extend_event(parsed):
    cal.extend_event(parsed['title'], parsed['additional_minutes'])

def rename(parsed):
    rename_event(parsed['original_title'], parsed['new_title'], parsed['date'])

def describe_event(parsed):
    return cal.describe_event(parsed['title'], parsed['date'])

def get_event_duration(parsed):
    return cal.get_event_duration(parsed['title'], parsed['date'])

def list_attendees(parsed):
    return cal.list_attendees(parsed['title'], parsed['date'])

def log_event_action(parsed):
    cal.log_event_action(parsed['event_id'], parsed['action'], parsed['timestamp'])

# -- Time and agenda related --
def get_agenda(parsed):
    return cal.get_agenda(parsed['range'])

def get_time_until_next_event():
    return cal.get_time_until_next_event()

def whats_next():
    return cal.get_current_and_next_event()

def list_today():
    return cal.list_today()

# -- Optional reply composition helpers (for bot.py to call) --
def format_agenda_reply(events, label: str) -> str:
    if not events or not events[0]:
        return msg.no_agenda(label)
    lines = []
    for ev in events:
        if not ev:
            continue
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        lines.append(f"{dt_start.strftime('%A %H:%M')} • {ev['summary']}")
    return f"🗓️ Your {label} agenda:\n" + "\n".join(lines)

def format_whats_next_reply(events: dict) -> str:
    out = ""
    if events.get("current"):
        start = events['current']['start']['dateTime']
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        out += f"🟢 You’re currently on: *{events['current']['summary']}* ({dt_start.strftime('%H:%M')})\n"
    if events.get("next"):
        start = events['next']['start']['dateTime']
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        out += f"➡️ Next: *{events['next']['summary']}* at {dt_start.strftime('%H:%M')}"
    return out or "📭 Nothing coming up today."

def format_event_description(details: dict) -> str:
    if not details:
        return "I couldn’t find that event."
    lines = [
        f"📝 *{details.get('summary')}*",
        f"📅 {details.get('start')} — {details.get('end')}",
        f"📍 Location: {details.get('location', 'N/A')}",
        f"📓 Description: {details.get('description', 'N/A')}",
        f"🔄 Recurrence: {details.get('recurrence', 'None')}",
        f"👥 Attendees: {', '.join(details.get('attendees', [])) or 'None'}",
    ]
    return "\n".join(lines)

# --- LLM send helper (graceful fallback) ---
async def _send_llm_payload(update, context, action_name: str, payload: dict):
    """
    payload must be like {"system": "...", "user": "..."} from prompts.py.
    Now always sends via respond_with_brain, which handles safe sending and fallback.
    """
    try:
        # Ask LLM to write the line, and send it (respond_with_brain now handles safe sending)
        return await respond_with_brain(
            update, context, {"action": action_name},
            system=payload.get("system"),
            user=payload.get("user"),
            send=True,
        )
    except Exception as e:
        logging.exception("[Actions] _send_llm_payload failed; falling back to summary. %s", e)
        # Fallback: send just the user text
        return await respond_with_brain(
            update, context, {"action": action_name},
            summary=(payload.get("user") or ""),
            send=True,
        )

# --- Main handler ---
async def handle_action(parsed, update, context):
    action = parsed.get("action")
    logging.info(f"[Actions] Received action: {action}")

    # ------------------------------------------------------------
    # Contract adapter (CP-1 / CC-3)
    # Map deterministic chat-protocol actions (from gpt_agent.parse_command)
    # into the existing WF0/FSM verbs already implemented below.
    # ------------------------------------------------------------

    # Best-effort: resolve a segment_id for contract-style commands.
    def _resolve_active_segment_id() -> str | None:
        try:
            now = dt.datetime.now(tz=TZ)
            seg = db.get_active_segment(now)
            return seg.get("id") if seg else None
        except Exception:
            logging.exception("[Actions] Failed to resolve active segment")
            return None

    # Adapter for contract actions
    if action in {
        "done",
        "didnt_start",
        "need_more",
        "snooze",
        "drift",
        "pause",
        "summary",
        "misses",
        "reschedule",
        "move_next",
        "skip",
    }:
        seg_id = parsed.get("segment_id") or _resolve_active_segment_id()

        # DONE -> mark_done (closes current segment)
        if action == "done":
            if seg_id:
                parsed = {"action": "mark_done", "segment_id": seg_id}
            else:
                parsed = {"action": "chat_fallback", "user_prompt": "No active block to mark as done."}

        # DIDNT START -> mark_missed
        elif action == "didnt_start":
            if seg_id:
                parsed = {"action": "mark_missed", "segment_id": seg_id}
            else:
                parsed = {"action": "chat_fallback", "user_prompt": "No active block to mark as missed."}

        # NEED MORE <minutes> -> extend_15 / extend_30 (nearest supported)
        elif action == "need_more":
            minutes = parsed.get("minutes")
            try:
                minutes = int(minutes) if minutes is not None else 15
            except Exception:
                minutes = 15

            if not seg_id:
                parsed = {"action": "chat_fallback", "user_prompt": "No active block to extend."}
            else:
                # Map to existing extension verbs
                if minutes <= 15:
                    parsed = {"action": "extend_15", "segment_id": seg_id}
                else:
                    parsed = {"action": "extend_30", "segment_id": seg_id}

        # SNOOZE <minutes> -> snooze_segment
        elif action == "snooze":
            minutes = parsed.get("minutes")
            try:
                minutes = int(minutes) if minutes is not None else 5
            except Exception:
                minutes = 5

            if seg_id:
                parsed = {"action": "snooze_segment", "segment_id": seg_id, "minutes": minutes}
            else:
                parsed = {"action": "chat_fallback", "user_prompt": "No active block to snooze."}

        # I'M DOING <x> -> pivot
        elif action == "drift":
            new_focus = parsed.get("title") or parsed.get("new_focus")
            if seg_id and new_focus:
                parsed = {"action": "pivot", "segment_id": seg_id, "new_focus": new_focus}
            elif not seg_id:
                parsed = {"action": "chat_fallback", "user_prompt": "No active block to pivot from."}
            else:
                parsed = {"action": "chat_fallback", "user_prompt": "Tell me what you're doing (e.g. I'M DOING band practice)."}

        # PAUSE (not implemented in WF0 yet) -> chat_fallback
        elif action == "pause":
            parsed = {"action": "chat_fallback", "user_prompt": "Pause isn't wired yet. Try SNOOZE 5 or DONE."}

        # SUMMARY / MISSES / RESCHEDULE / MOVE NEXT / SKIP are part of the broader contract,
        # but are not wired into this actions router yet. Route them through chat_fallback
        # so the companion can respond without dead-ending.
        elif action in {"summary", "misses", "reschedule", "move_next", "skip"}:
            parsed = {
                "action": "chat_fallback",
                "user_prompt": f"Contract command '{action}' isn't wired yet in actions.py. Use agenda commands like 'Agenda for today' or WF0 buttons."  # noqa: E501
            }

        # Refresh action name after mapping
        action = parsed.get("action")
    


    if action == "create_event":
        start = dt.datetime.fromisoformat(f"{parsed['date']}T{parsed['time']}").replace(tzinfo=TZ)
        event = cal.create_event(
            parsed['title'],
            start,
            parsed.get('duration_minutes', 60),
            parsed.get('attendees'),
            parsed.get('recurrence')
        )

        # 1. Send the normal event description
        summary = format_event_description(event)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

        # 2. Prompt user to classify domain
        try:
            kb = msg.build_domain_picker(event["id"])
            await update.message.reply_text(
                "🗂 Please pick a domain for this event:",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.exception("[Actions] Failed to send domain keyboard: %s", e)

    elif action == "reschedule_event":
        new_start = dt.datetime.fromisoformat(f"{parsed['new_date']}T{parsed['new_time']}").replace(tzinfo=TZ)
        updated = cal.reschedule_event(parsed['original_title'], new_start)
        summary = format_event_description(updated)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "cancel_event":
        cancel_event(parsed)
        summary = f"❌ Event '{parsed['title']}' on {parsed['date']} cancelled."
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "extend_event":
        # Perform extend, then refetch the updated event for metadata-rich summary
        cal.extend_event(parsed['title'], parsed['additional_minutes'])
        updated = cal.describe_event(parsed['title'], parsed['date'])
        summary = format_event_description(updated)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "rename_event":
        updated = rename_event(parsed['original_title'], parsed['new_title'], parsed['date'])
        summary = format_event_description(updated)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "describe_event":
        details = describe_event(parsed)
        summary = format_event_description(details)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_event_duration":
        duration = get_event_duration(parsed)
        summary = f"🕒 Duration of '{parsed['title']}': {duration} minutes"
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "list_attendees":
        attendees = list_attendees(parsed)
        summary = f"👥 Attendees for '{parsed['title']}': {', '.join(attendees) or 'None'}"
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_agenda":
        events = get_agenda(parsed)
        summary = format_agenda_reply(events, parsed['range'])
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "get_time_until_next_event":
        result = get_time_until_next_event()
        summary = f"⏳ Time until next event: {result}"
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "whats_next":
        events = whats_next()
        summary = format_whats_next_reply(events)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "log_event_action":
        log_event_action(parsed)
        return
    
    elif action == "whats_now":
        events = whats_next()
        summary = format_whats_next_reply(events)
        logging.info(f"[Actions] Sending Telegram message: {summary}")
        await respond_with_brain(update, context, parsed, summary=summary)

    elif action == "chat_fallback":
        await respond_with_brain(update, context, parsed)
        
    elif action == "send_ftw_intent":
        seg_id = parsed["segment_id"]
        seg = _fetch_segment(seg_id)
        gap_min = 15
        tone_str = "gentle"
        if seg:
            try:
                gap_min = int((seg["end_at"] - seg["start_at"]).total_seconds() // 60)
            except Exception:
                gap_min = 15
            tone_str = (seg.get("tone_at_start") or "gentle").lower()

        payload = prompts.free_time_prompt(gap_minutes=gap_min, tone=tone_str, theme_hint=None)
        # Mark start so we don’t re-prompt each minute
        db.update_segment(seg_id, start_confirmed_at=dt.datetime.now(tz=TZ))
        await _send_llm_payload(update, context, "send_ftw_intent", payload)
    
    # --- FSM verb routing (Workflow #0) ---
    elif action == "send_start":
        await fsm_send_start(parsed["segment_id"], update, context)

    elif action == "send_mid":
        await fsm_send_mid(parsed["segment_id"], update, context)

    elif action == "send_end":
        await fsm_send_end(parsed["segment_id"], update, context)

    elif action == "extend_15":
        await fsm_extend(parsed["segment_id"], 15, update, context)

    elif action == "extend_30":
        await fsm_extend(parsed["segment_id"], 30, update, context)

    elif action == "pivot":
        await fsm_pivot(parsed["segment_id"], parsed.get("new_focus"), update, context)

    elif action == "snooze_segment":
        # default 5m if not provided; your keyboards send 5/10/20/30 explicitly
        await fsm_snooze(parsed["segment_id"], int(parsed.get("minutes", 5)), update, context)

    elif action == "schedule_more":
        await fsm_schedule_more(parsed["segment_id"], update, context)

    elif action == "schedule_recovery":
        await fsm_schedule_recovery(parsed["segment_id"], parsed.get("reason"), update, context)
        
    elif action == "confirm_start":
        await fsm_confirm_start(parsed["segment_id"], update, context)
    elif action == "mid_yes":
        await fsm_mid_yes(parsed["segment_id"], update, context)
    elif action == "mark_done":
        await fsm_mark_done(parsed["segment_id"], update, context)
    elif action == "mark_missed":
        await fsm_mark_missed(parsed["segment_id"], update, context)
        
# --- Helpers for Workflow #0 actions (segment-driven) ---

def _tone_from_str(s: str) -> Tone:
    return {"gentle": Tone.GENTLE, "coach": Tone.COACH, "ds": Tone.DS}.get((s or "gentle").lower(), Tone.GENTLE)


def _fetch_segment(seg_id: str) -> dict | None:
    # You already have db.get_active_segment/get_next_segment; this fetches by id for verbs
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM segments WHERE id=%s", (seg_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))

# --- Duplicate _send_llm_payload removal (if present, remove below) ---

# --- FSM "verbs" ---

async def fsm_send_start(seg_id: str, update, context):
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    # Build proper inputs for prompts
    title = seg.get("title") or seg.get("summary") or "This block"
    tone_str = (seg.get("tone_at_start") or "gentle").lower()  # "gentle"/"coach"/"ds"
    payload = prompts.start_prompt(title=title, tone=tone_str, qii=False, theme=None)
    logging.info(f"[FSM] send_start → title='{title}', tone='{tone_str}'")
    # Mark started, then send prompt
    db.update_segment(seg_id, start_confirmed_at=dt.datetime.now(tz=TZ))
    await _send_llm_payload(update, context, "fsm_send_start", payload)

async def fsm_send_mid(seg_id: str, update, context):
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    title = seg.get("title") or seg.get("summary") or "This block"
    tone_str = (seg.get("tone_at_start") or "gentle").lower()
    payload = prompts.mid_prompt(title=title, tone=tone_str)
    logging.info(f"[FSM] send_mid → title='{title}', tone='{tone_str}'")
    await _send_llm_payload(update, context, "fsm_send_mid", payload)

async def fsm_send_end(seg_id: str, update, context):
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    title = seg.get("title") or seg.get("summary") or "This block"
    tone_str = (seg.get("tone_at_start") or "gentle").lower()
    payload = prompts.end_prompt(title=title, tone=tone_str)
    logging.info(f"[FSM] send_end → title='{title}', tone='{tone_str}'")
    await _send_llm_payload(update, context, "fsm_send_end", payload)

async def fsm_extend(seg_id: str, minutes: int, update, context):
    seg = _fetch_segment(seg_id)
    if not seg: return
    # delegate reflow to scheduler (respects rigidity + buffers)
    changed = await sched.extend_current_segment(seg_id, minutes)
    if changed:
        await respond_with_brain(update, context, {"action":"fsm_extend","segment_id":seg_id, "minutes": minutes},
                                 summary=f"⏳ Extended this block by {minutes} min and reflowed the soft/free followers.")

async def fsm_pivot(seg_id: str, new_focus: str | None, update, context):
    seg = _fetch_segment(seg_id)
    if not seg: return
    created = await sched.pivot_segment(seg_id, new_focus or "Ad‑hoc Focus")
    db.update_segment(seg_id, end_status="pivoted", reason_code="pivot")
    await respond_with_brain(update, context, {"action":"fsm_pivot","segment_id":seg_id, "new_focus": new_focus},
                             summary=f"↩ Pivoted. New focus segment: *{created.get('summary','Focus')}*")

async def fsm_snooze(seg_id: str, minutes: int, update, context):
    seg = _fetch_segment(seg_id)
    if not seg: return
    ok, reason = await sched.snooze_segment(seg_id, minutes)  # enforce rigidity inside scheduler
    if ok:
        await respond_with_brain(update, context, {"action":"fsm_snooze","segment_id":seg_id, "minutes": minutes},
                                 summary=f"😌 Snoozed {minutes} min.")
    else:
        await respond_with_brain(update, context, {"action":"fsm_snooze_denied","segment_id":seg_id},
                                 summary=f"⛔ Can’t snooze this one ({reason}).")

async def fsm_schedule_more(seg_id: str, update, context):
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        target_ts = await sched.schedule_more(seg_id)  # finds next suitable slot and writes DB/calendar
    except Exception as e:
        # Calendar hiccup or scheduler failure
        await respond_with_brain(
            update, context,
            {"action":"fsm_schedule_more_error","segment_id":seg_id},
            summary=f"⚠️ I couldn’t book a follow‑up right now (calendar hiccup). I’ll retry shortly."
        )
        return

    if not target_ts:
        # No slot found today—offer a next‑day search without writing reschedule_target
        await respond_with_brain(
            update, context,
            {"action":"fsm_schedule_more_none","segment_id":seg_id},
            summary="🗓 No decent slot left today. Want me to search tomorrow morning and hold the first 45–60m window?"
        )
        return

    db.update_segment(seg_id, end_status="rescheduled", reschedule_target=target_ts)
    await respond_with_brain(
        update, context,
        {"action":"fsm_schedule_more","segment_id":seg_id},
        summary=f"🔄 Booked a follow‑up slot at {target_ts.astimezone(TZ).strftime('%a %H:%M')}."
    )

async def fsm_schedule_recovery(seg_id: str, reason: str | None, update, context):
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        # Respect DS caps & today‑first policy inside scheduler
        booked = await sched.schedule_recovery_block(seg_id, reason=reason)
    except Exception as e:
        await respond_with_brain(
            update, context,
            {"action":"fsm_schedule_recovery_error","segment_id":seg_id, "reason": reason},
            summary="⚠️ Couldn’t set a recovery slot due to a calendar error. I’ll retry in a few minutes."
        )
        return

    if not booked:
        await respond_with_brain(
            update, context,
            {"action":"fsm_schedule_recovery_none","segment_id":seg_id, "reason": reason},
            summary="🗓 No recovery window free today. I can lock the first available slot tomorrow morning—shall I?"
        )
        return

    db.update_segment(seg_id, end_status="missed")
    await respond_with_brain(
        update, context,
        {"action":"fsm_schedule_recovery","segment_id":seg_id, "reason": reason},
        summary=f"🛠 Recovery slot set for {booked.astimezone(TZ).strftime('%a %H:%M')} (reason: {reason or 'missed'})."
    )


# --- FSM segment status verbs: confirm_start, mid_yes, mark_done, mark_missed ---
async def fsm_confirm_start(seg_id: str, update, context):
    """
    User confirmed "Start" on the current segment. Do NOT create a new event.
    Simply mark the DB and acknowledge.
    """
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        db.update_segment(seg_id, start_confirmed_at=dt.datetime.now(tz=TZ))
    except Exception:
        logging.exception("[FSM] confirm_start failed to update segment")
    # Short, non-LLM confirmation to avoid motivational extras.
    await respond_with_brain(
        update, context,
        {"action": "fsm_confirm_start", "segment_id": seg_id},
        summary="✅ Started. I’ll check in at the midpoint."
    )


async def fsm_mid_yes(seg_id: str, update, context):
    """
    User indicated they are on track at midpoint.
    Record a light status and keep stewardship running.
    """
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        # Mark that we got a positive heartbeat so we don't reprompt.
        if not seg.get("midpoint_status"):
            db.update_segment(seg_id, midpoint_status="ok")
    except Exception:
        logging.exception("[FSM] mid_yes failed to update segment")
    await respond_with_brain(
        update, context,
        {"action": "fsm_mid_yes", "segment_id": seg_id},
        summary="👍 Noted — keep going."
    )


async def fsm_mark_done(seg_id: str, update, context):
    """
    User closed the block as Done.
    Mark the segment completed and acknowledge.
    """
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        db.update_segment(seg_id, end_status="completed", reason_code="user_done")
    except Exception:
        logging.exception("[FSM] mark_done failed to update segment")
    await respond_with_brain(
        update, context,
        {"action": "fsm_mark_done", "segment_id": seg_id},
        summary="✅ Marked done. Nice work."
    )


async def fsm_mark_missed(seg_id: str, update, context):
    """
    User marked the block as Missed / Didn’t start.
    Mark missed; no auto-reschedule here (that belongs to scheduler or RTC workflow).
    """
    seg = _fetch_segment(seg_id)
    if not seg:
        return
    try:
        db.update_segment(seg_id, end_status="missed", reason_code="user_missed")
    except Exception:
        logging.exception("[FSM] mark_missed failed to update segment")
    await respond_with_brain(
        update, context,
        {"action": "fsm_mark_missed", "segment_id": seg_id},
        summary="🛑 Logged as missed. Want a recovery slot?"
    )