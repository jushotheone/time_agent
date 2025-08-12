# ======================
# agent_brain/state.py
# ======================
import db
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import os

TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/London"))

# --- tiny time helper ---
def _now_tz() -> datetime:
    return datetime.now(TZ)

def log_event_status(event_id, status, quadrant=None):  # ✅ Add quadrant param
    db.mark_event_as_notified(event_id, phase=status)
    db.log_event(
        event_id,
        status,
        timestamp=datetime.now(TZ),
        quadrant=quadrant  # ✅ Pass it along to DB
    )
    
# ---------- day_state wrappers (tone & counters) ----------

def _day_key(d: datetime | None = None) -> date:
    return (d or _now_tz()).date()

def get_tone(day: date | None = None) -> str:
    """
    Returns 'gentle' | 'coach' | 'ds'
    """
    st = db.get_day_state(_day_key(day))
    return st.get("current_tone", "gentle")

def set_tone_with_cooldown(
    day: date | None,
    tone: str,
    until: datetime | None = None
) -> None:
    """
    Persist tone + optional cooldown timestamp.
    `tone` must be one of: 'gentle','coach','ds'
    """
    fields = {"current_tone": tone}
    if until is not None:
        fields["tone_cooldown_until"] = until
    db.set_day_state(_day_key(day), **fields)

def bump_completion_streak() -> None:
    st = db.get_day_state(_day_key())
    db.set_day_state(
        _day_key(),
        consecutive_completions=(st.get("consecutive_completions", 0) + 1),
        consecutive_misses=0
    )

def bump_miss_streak() -> None:
    st = db.get_day_state(_day_key())
    db.set_day_state(
        _day_key(),
        consecutive_misses=(st.get("consecutive_misses", 0) + 1),
        consecutive_completions=0
    )

# ---------- segments write helpers (no business logic) ----------

def confirm_segment_start(seg_id: str) -> None:
    db.update_segment(seg_id, start_confirmed_at=_now_tz())

def mark_midpoint_status(seg_id: str, status: str) -> None:
    """
    status: 'ok'|'mia'|'overrun'|'pivot'
    """
    db.update_segment(seg_id, midpoint_status=status)

def record_completion(seg_id: str, *, reason_code: str | None = None, score_delta: int = 1) -> None:
    """
    Close segment as completed and bump completion streak.
    """
    db.update_segment(
        seg_id,
        end_status="completed",
        reason_code=reason_code,
        score_delta=score_delta
    )
    bump_completion_streak()

def record_miss(seg_id: str, *, reason_code: str | None = None, enqueue: bool = True) -> None:
    """
    Close segment as missed and bump miss streak.
    Optionally enqueue for recovery.
    """
    db.update_segment(
        seg_id,
        end_status="missed",
        reason_code=reason_code
    )
    if enqueue:
        db.enqueue_missed(seg_id)
    bump_miss_streak()

def record_reschedule(
    seg_id: str,
    *,
    reschedule_target: datetime | None,
    reason_code: str | None = None
) -> None:
    """
    Close segment as rescheduled. Does not alter streaks.
    """
    fields = {"end_status": "rescheduled", "reason_code": reason_code}
    if reschedule_target is not None:
        fields["reschedule_target"] = reschedule_target
    db.update_segment(seg_id, **fields)

def record_pivot(
    seg_id: str,
    *,
    reason_code: str | None = "pivot"
) -> None:
    """
    Mark segment as pivoted. Streaks are not changed here; caller decides.
    """
    db.update_segment(seg_id, end_status="pivoted", reason_code=reason_code)

# ---------- convenience wrappers for DS / Recovery bookkeeping ----------

def increment_recovery_blocks_used() -> None:
    st = db.get_day_state(_day_key())
    used = st.get("recovery_blocks_used", 0) + 1
    db.set_day_state(_day_key(), recovery_blocks_used=used)

def reset_daily_streaks() -> None:
    db.set_day_state(_day_key(), consecutive_misses=0, consecutive_completions=0)

def set_tone_cooldown(minutes: int) -> None:
    db.set_day_state(_day_key(), tone_cooldown_until=_now_tz() + timedelta(minutes=minutes))