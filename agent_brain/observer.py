# ======================
# agent_brain/observer.py
# ======================
import os
import datetime as dt
import zoneinfo
import calendar_client as cal
import beia_core.models.timebox as db
from agent_brain.quadrant_detector import detect_quadrant  # ✅ New

import feature_flags as ff
from agent_brain import fsm
from agent_brain.fsm import State, Event, Tone, DayState, SegmentCtx
from dateutil.parser import isoparse
import logging


TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))
# For boundary‑crossing detection (start/mid/end fire exactly once)
_LAST_TICK: dt.datetime | None = None

def _ensure_current_event_segment(now: dt.datetime) -> None:
    """If there is a current Google event but no active segment, upsert one into segments."""
    # Only bail if we're already stewarding a scheduled segment.
    active = db.get_active_segment(now)
    if active and active.get("type") == "scheduled":
        return

    cur_next = cal.get_current_and_next_event()
    current = cur_next.get("current")
    if not current:
        return

    eid = current["id"]
    title = current.get("summary") or "Untitled"
    start_s = current["start"].get("dateTime", current["start"].get("date"))
    end_s   = current["end"].get("dateTime",   current["end"].get("date"))
    start_at = isoparse(start_s).astimezone(TZ)
    end_at   = isoparse(end_s).astimezone(TZ)

    # derive rigidity from description tags, default to soft
    rigidity = "soft"
    desc = (current.get("description") or "").lower()
    for tag in ("#rigidity:hard", "#rigidity:firm", "#rigidity:soft", "#rigidity:free"):
        if tag in desc:
            rigidity = tag.split(":")[1]
            break

    seg_doc = {
        "id": f"gcal:{eid}",
        "type": "scheduled",
        "title": title,
        "rigidity": rigidity,
        "start_at": start_at,
        "end_at": end_at,
        "tz": str(TZ),
    }

    # upsert (fallback to insert if you don’t have upsert)
    if hasattr(db, "upsert_segment"):
        db.upsert_segment(seg_doc)
    else:
        if not getattr(db, "get_segment_by_id", None) or not db.get_segment_by_id(seg_doc["id"]):
            db.insert_segment(seg_doc)


def _row_to_ctx(row) -> SegmentCtx:
    """
    Normalize DB row (dict preferred) into SegmentCtx. Avoids KeyError: 0 when
    a dict is passed by ensuring we only use index-access as a last resort.
    """
    if isinstance(row, dict):
        rid = row.get('id')
        rigidity = (row.get('rigidity') or 'soft')
        start_at = row.get('start_at')
        end_at = row.get('end_at')
        rtype = row.get('type')
    else:
        # Try to coerce mapping-like rows (e.g., psycopg2.extras.RealDictRow)
        try:
            m = dict(row)
            rid = m.get('id')
            rigidity = (m.get('rigidity') or 'soft')
            start_at = m.get('start_at')
            end_at = m.get('end_at')
            rtype = m.get('type')
        except Exception:
            # Last resort: assume tuple ordering (id, type, rigidity, start_at, end_at, ...)
            rid = row[0]
            rtype = row[1]
            rigidity = (row[2] or 'soft')
            start_at = row[3]
            end_at = row[4]

    return SegmentCtx(
        id=rid,
        rigidity=rigidity,
        start_at=start_at,
        end_at=end_at,
        is_free_time=(rtype == 'free')
    )

def _infer_state(seg_row: dict, now: dt.datetime) -> State:
    start = seg_row['start_at']
    end = seg_row['end_at']
    start_confirmed = seg_row.get('start_confirmed_at')
    end_status = seg_row.get('end_status')
    midpoint_status = seg_row.get('midpoint_status')
    if end_status in ('completed','rescheduled','missed','pivoted','rest','drift'):
        return State.IDLE_DAY
    if start > now:
        return State.SEGMENT_PLANNED
    if start <= now <= end:
        if not start_confirmed:
            return State.AWAITING_START
        if midpoint_status in ('mia','pivot'):
            return State.OFF_TRACK
        return State.IN_PROGRESS
    if now > end and not end_status:
        # ran past end; treat as IN_PROGRESS until closed
        return State.IN_PROGRESS
    return State.IDLE_DAY

def _emit_tick_events(seg_row: dict, now: dt.datetime) -> list[Event]:
    global _LAST_TICK
    start = seg_row['start_at']
    end = seg_row['end_at']
    prev = _LAST_TICK or (now - dt.timedelta(seconds=61))  # safe first run fallback

    events: list[Event] = []

    # START: fire when we cross into the window
    if prev < start <= now and not seg_row.get('start_confirmed_at'):
        events.append(Event.TICK_START)

    # midpoint (~50%) only once
    duration = (end - start).total_seconds()
    if duration > 0:
        midpoint = start + dt.timedelta(seconds=duration / 2)
        # MIDPOINT: fire once when crossing the boundary
        if prev < midpoint <= now and not seg_row.get('midpoint_status'):
            events.append(Event.TICK_MID)

    # END: fire when we cross past end
    if prev < end <= now and not seg_row.get('end_status'):
        events.append(Event.TICK_END)

    # safe debug log
    try:
        seg_id = seg_row.get('id') if isinstance(seg_row, dict) else seg_row['id']
    except Exception:
        seg_id = "<unknown>"
    logging.info(f"[Observer] Tick events for seg {seg_id}: {[e.name for e in events]}")

    _LAST_TICK = now
    return events

def detect_drift():
    """
    Backward-compatible shim.
    Old behavior: only detect a missed current Google event.
    New behavior: drive FSM ticks for the active/next segment and, if needed,
    still return a legacy dict when a current calendar event is definitively missed
    (so older callers don't break).
    """
    now = dt.datetime.now(TZ)
    
    # NEW: ensure current gcal event is mirrored as a segment
    _ensure_current_event_segment(now)

    # 1) Prefer segments table (Workflow #0 path)
    seg = db.get_active_segment(now)
    logging.info(f"[Observer] Now: {now}, Active segment: {seg}")
    results = []
    
    # If an FTW is active but a real calendar event is current, switch stewardship
    cur_next = cal.get_current_and_next_event()
    current = cur_next.get("current")
    if seg and seg.get("type") == "free" and current:
        # Mirror the current gcal event into segments and end the FTW
        _ensure_current_event_segment(now)
        try:
            db.update_segment(seg["id"], end_at=now, end_status="drift")
        except Exception:
            pass
        # Re-fetch the active segment after the switch
        seg = db.get_active_segment(now)
    

    if seg:
        state = _infer_state(seg, now)
        day_row = db.get_day_state(now.date())
        day = DayState(
            current_tone=Tone[day_row['current_tone'].upper()],
            consecutive_misses=day_row['consecutive_misses'],
            consecutive_completions=day_row['consecutive_completions'],
            tone_cooldown_until=day_row.get('tone_cooldown_until')
        )
        ctx = _row_to_ctx(seg)
        ds_enabled = ff.enabled('WF0_DS_MODE') if hasattr(ff, 'enabled') else False

        for ev in _emit_tick_events(seg, now):
            # 1) Free‑time: start intent (you already had this)
            if ctx.is_free_time and ev == Event.TICK_START and not seg.get('start_confirmed_at'):
                results.append({
                    'segment_id': seg['id'],
                    'action': 'send_ftw_intent',
                    'tone': day.current_tone.name.lower(),
                    'event': ev.name.lower(),
                })
                db.update_segment(seg['id'], start_confirmed_at=now)
                continue

            # 2) SCHEDULED fallback mappings (ensure prompts fire even if FSM returns None)

            # TICK_START → send_start (once)
            if (not ctx.is_free_time
                and ev == Event.TICK_START
                and not seg.get('start_confirmed_at')):
                results.append({
                    'segment_id': seg['id'],
                    'action': 'send_start',
                    'tone': day.current_tone.name.lower(),
                    'event': ev.name.lower(),
                })
                # Do NOT mark start here; wait for explicit user confirm
                db.update_segment(seg['id'], tone_at_start=day.current_tone.name.lower())
                continue

            # TICK_MID → send_mid (once)
            if (not ctx.is_free_time
                and ev == Event.TICK_MID
                and seg.get('start_confirmed_at')
                and not seg.get('midpoint_status')):
                results.append({
                    'segment_id': seg['id'],
                    'action': 'send_mid',
                    'tone': day.current_tone.name.lower(),
                    'event': ev.name.lower(),
                })
                # mark so we don't ping every minute
                db.update_segment(seg['id'], midpoint_status='pinged')
                continue

            # TICK_END → send_end (once)
            if (ev == Event.TICK_END
                and not seg.get('end_status')):
                results.append({
                    'segment_id': seg['id'],
                    'action': 'send_end',
                    'tone': day.current_tone.name.lower(),
                    'event': ev.name.lower(),
                })
                # don't set end_status here; let the verb handler decide (completed/missed/etc.)
                continue

            # 3) Otherwise let the FSM handle it (keeps your advanced logic intact)
            new_state, action = fsm.apply_event(state, ev, day, ctx, ds_enabled=ds_enabled)
            state = new_state
            if action:
                results.append({
                    'segment_id': seg['id'],
                    'action': action,
                    'tone': day.current_tone.name.lower(),
                    'event': ev.name.lower(),
                })

    # Also handle segments that ended in the last minute (not active anymore)
    try:
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM segments
                 WHERE end_status IS NULL
                   AND end_at > (NOW() - INTERVAL '65 seconds')
                   AND end_at <= NOW()
            """)
            rows = cur.fetchall()
            if rows:
                cols = [d[0] for d in cur.description]
                for r in rows:
                    s = dict(zip(cols, r))
                    day_row = db.get_day_state(now.date())
                    tone = (day_row['current_tone'] or 'gentle').lower()
                    results.append({
                        'segment_id': s['id'],
                        'action': 'send_end',
                        'tone': tone,
                        'event': 'tick_end',
                    })
    except Exception:
        logging.exception("[Observer] just‑ended scan failed")

    # 2) Create Free-Time Window if no active segment and there is a gap ≥15m
    if not seg:
        events = cal.get_current_and_next_event()
        current = events.get('current')
        upcoming = events.get('next')
        if not current:
            gap_end = None
            if upcoming:
                gap_end = isoparse(upcoming['start'].get('dateTime', upcoming['start'].get('date'))).astimezone(TZ)
            else:
                gap_end = now + dt.timedelta(minutes=30)
            gap_min = (gap_end - now).total_seconds() / 60.0
            if gap_min >= 15:
                seg_id = f"ftw:{now.strftime('%Y%m%dT%H%M')}"
                db.insert_segment({
                    'id': seg_id,
                    'type': 'free',
                    'rigidity': 'free',
                    'start_at': now,
                    'end_at': gap_end,
                    'tone_at_start': db.get_day_state(now.date())['current_tone'],
                })
                # emit a start prompt for the gap intent
                results.append({'segment_id': seg_id, 'action': 'send_ftw_intent', 'tone': db.get_day_state(now.date())['current_tone'], 'event': 'tick_start'})

    # 3) Legacy return for older callers (missed current event)
    if not results:
        events = cal.get_current_and_next_event()
        current = events.get('current')
        if current:
            start = isoparse(current['start'].get('dateTime', current['start'].get('date'))).astimezone(TZ)
            end   = isoparse(current['end'].get('dateTime', current['end'].get('date'))).astimezone(TZ)
            grace_end = end + dt.timedelta(minutes=5)
            if now > grace_end and not db.was_event_notified(current['id'], 'missed'):
                quadrant = detect_quadrant(current['summary'])
                return {
                    'event_id': current['id'],
                    'summary': current['summary'],
                    'status': 'missed',
                    'start': start,
                    'end': end,
                    'quadrant': quadrant,
                }
    logging.info(f"[Observer] Results to return: {results}")
    return results or None