# agent_brain/fsm.py
from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime, timedelta

class State(Enum):
    IDLE_DAY = auto()
    SEGMENT_PLANNED = auto()
    AWAITING_START = auto()
    IN_PROGRESS = auto()
    OFF_TRACK = auto()
    PAUSED = auto()       # manual pause (short)
    SNOOZED = auto()      # 10/20/30m snooze
    INTERRUPTED = auto()  # phone call/driving etc.
    COMPLETED = auto()
    MISSED = auto()
    RESCHEDULED = auto()

class Event(Enum):
    TICK_START = auto()
    TICK_MID = auto()
    TICK_END = auto()
    USER_START = auto()
    USER_SNOOZE = auto()
    USER_SKIP = auto()
    USER_EXTEND_15 = auto()
    USER_EXTEND_30 = auto()
    USER_PIVOT = auto()
    USER_DONE = auto()
    USER_NEED_MORE = auto()
    USER_DIDNT_START = auto()
    USER_PAUSE = auto()        # NEW: short manual pause
    EXTERNAL_INTERRUPTED = auto()
    EXTERNAL_RESUME = auto()
    AUTO_MIA = auto()

class Tone(Enum):
    GENTLE = auto()
    COACH = auto()
    DS = auto()

@dataclass
class DayState:
    current_tone: Tone = Tone.GENTLE
    consecutive_misses: int = 0
    consecutive_completions: int = 0
    tone_cooldown_until: Optional[datetime] = None

@dataclass
class SegmentCtx:
    id: str
    rigidity: str  # 'hard'|'firm'|'soft'|'free'
    start_at: datetime
    end_at: datetime
    is_free_time: bool = False

TONE_COOLDOWN = timedelta(minutes=30)

def _can_change_tone(day: DayState, now: datetime) -> bool:
    return not day.tone_cooldown_until or now >= day.tone_cooldown_until

def _bump_tone(day: DayState, direction: int, now: datetime) -> None:
    order = [Tone.GENTLE, Tone.COACH, Tone.DS]
    idx = max(0, min(len(order)-1, order.index(day.current_tone) + direction))
    new_tone = order[idx]
    if new_tone != day.current_tone and _can_change_tone(day, now):
        day.current_tone = new_tone
        day.tone_cooldown_until = now + TONE_COOLDOWN

# Optional: expose relax helpers for the caller (observer) after clean runs
def relax_one_level(day: DayState) -> None:
    _bump_tone(day, -1, datetime.utcnow())

def escalate_one_level(day: DayState) -> None:
    _bump_tone(day, +1, datetime.utcnow())

def _action_for_reschedule(seg: SegmentCtx, ds_enabled: bool) -> Tuple[State, str]:
    """
    Respect rigidity here by returning a special action the caller can enforce.
    - hard: never auto-move (needs confirm)
    - firm: propose, require confirm
    - soft/free: auto-move
    For DS, prefer recovery path over soft reschedule.
    """
    if seg.rigidity == "hard":
        return State.RESCHEDULED, "needs_confirm_reschedule"
    if seg.rigidity == "firm":
        return State.RESCHEDULED, "confirm_reschedule"
    # soft/free
    return (State.MISSED, "schedule_recovery") if ds_enabled else (State.RESCHEDULED, "schedule_more")

def apply_event(
    state: State,
    event: Event,
    day: DayState,
    seg: SegmentCtx,
    *,
    ds_enabled: bool,
) -> Tuple[State, Optional[str]]:
    """
    Returns (new_state, action)
    action examples:
      'send_start','send_mid','send_end','mark_mia',
      'extend_15','extend_30','pivot','schedule_more',
      'schedule_recovery','snooze_segment','pause_timer',
      'started','confirm_reschedule','needs_confirm_reschedule'
    """
    now = datetime.utcnow()
    action = None

    # Escalation hook when caller flags MIA
    if event == Event.AUTO_MIA and ds_enabled:
        _bump_tone(day, +1, now)  # escalate tone

    # --- Planned -> Awaiting ---
    if state == State.SEGMENT_PLANNED and event == Event.TICK_START:
        return State.AWAITING_START, "send_start"

    # --- Awaiting Start ---
    if state == State.AWAITING_START:
        if event == Event.USER_START:
            return State.IN_PROGRESS, "started"
        if event == Event.USER_SNOOZE:
            return State.SNOOZED, "snooze_segment"
        if event == Event.USER_PAUSE:
            return State.PAUSED, "pause_timer"
        if event == Event.USER_SKIP or event == Event.USER_DIDNT_START:
            # Spec: Skip/Didn't Start → Missed (DS) or Reschedule
            return _action_for_reschedule(seg, ds_enabled)
        if event == Event.EXTERNAL_INTERRUPTED:
            return State.INTERRUPTED, None
        if event == Event.TICK_MID and ds_enabled:
            # DS mid-block hard stance: mark MIA if still not started
            return State.OFF_TRACK, "mark_mia"
        if event == Event.TICK_END:
            # End reached without start
            return (State.MISSED, "schedule_recovery") if ds_enabled else _action_for_reschedule(seg, ds_enabled)

    # --- In Progress ---
    if state == State.IN_PROGRESS:
        if event == Event.TICK_MID:
            return State.IN_PROGRESS, "send_mid"
        if event == Event.USER_EXTEND_15:
            return State.IN_PROGRESS, "extend_15"
        if event == Event.USER_EXTEND_30:
            return State.IN_PROGRESS, "extend_30"
        if event == Event.USER_PIVOT:
            return State.OFF_TRACK, "pivot"
        if event == Event.USER_SNOOZE:
            return State.PAUSED, "pause_timer"
        if event == Event.USER_SKIP:
            # Mid-block skip → DS prefers recovery; else reschedule
            return _action_for_reschedule(seg, ds_enabled)
        if event == Event.USER_DONE:
            return State.COMPLETED, "send_end"
        if event == Event.USER_NEED_MORE:
            # Ask for more time (prefer reschedule unless DS wants recovery)
            return _action_for_reschedule(seg, ds_enabled)
        if event == Event.TICK_END:
            # DS may force outcome
            return (State.MISSED, "schedule_recovery") if ds_enabled else _action_for_reschedule(seg, ds_enabled)

    # --- Paused ---
    if state == State.PAUSED:
        if event in (Event.USER_START, Event.TICK_START):
            return State.IN_PROGRESS, "started"
        if event == Event.TICK_END:
            return _action_for_reschedule(seg, ds_enabled)

    # --- Snoozed (timed) ---
    if state == State.SNOOZED:
        if event in (Event.TICK_START, Event.USER_START):
            return State.IN_PROGRESS, "started"
        if event == Event.TICK_END:
            return _action_for_reschedule(seg, ds_enabled)

    # --- Interrupted (external) ---
    if state == State.INTERRUPTED:
        if event == Event.EXTERNAL_RESUME:
            return State.AWAITING_START, "send_start"
        if event == Event.TICK_END:
            # never resumed before end
            return _action_for_reschedule(seg, ds_enabled)

    # --- Off Track resolution ---
    if state == State.OFF_TRACK:
        if event == Event.USER_NEED_MORE:
            return _action_for_reschedule(seg, ds_enabled)
        if event == Event.USER_DONE:
            return State.COMPLETED, "send_end"
        if event == Event.TICK_END and ds_enabled:
            return State.MISSED, "schedule_recovery"

    # Terminal → Idle
    if state in (State.COMPLETED, State.MISSED, State.RESCHEDULED):
        return State.IDLE_DAY, None

    return state, action