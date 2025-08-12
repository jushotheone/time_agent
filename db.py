# db.py
import os
import psycopg2
import datetime as dt
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:

            # --- ensure base tables exist with final schema (idempotent) ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS event_notifications (
                    event_id   TEXT,
                    phase      TEXT,
                    notified_at TIMESTAMPTZ DEFAULT now(),
                    PRIMARY KEY (event_id, phase)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS postponed_reminders (
                    event_id  TEXT,
                    remind_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (event_id, remind_at)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    event_id  TEXT,
                    status    TEXT,
                    timestamp TIMESTAMPTZ DEFAULT now(),
                    quadrant  TEXT,
                    PRIMARY KEY (event_id, status)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    user_id  TEXT,
                    role     TEXT CHECK (role IN ('user','assistant')),
                    content  TEXT,
                    timestamp TIMESTAMPTZ DEFAULT now()
                );
            """)

            # --- one-time, idempotent migrations for legacy installs ---
            # Bring legacy event_notifications (PK on event_id only) up to date.
            cur.execute("""
                DO $$
                BEGIN
                    IF to_regclass('public.event_notifications') IS NOT NULL THEN
                        -- Add phase column if missing
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='event_notifications' AND column_name='phase'
                        ) THEN
                            ALTER TABLE event_notifications ADD COLUMN phase TEXT;
                        END IF;

                        -- Ensure composite PK (event_id, phase)
                        BEGIN
                            ALTER TABLE event_notifications DROP CONSTRAINT event_notifications_pkey;
                        EXCEPTION WHEN undefined_object THEN
                            -- no old PK; ignore
                        END;

                        BEGIN
                            ALTER TABLE event_notifications ADD PRIMARY KEY (event_id, phase);
                        EXCEPTION WHEN duplicate_table THEN
                            -- already composite; ignore
                        WHEN others THEN
                            -- ignore if already correct
                        END;
                    END IF;
                END
                $$;
            """)

            # ---------- NEW for Workflow #0 ----------
            cur.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK (type IN ('scheduled','free')) NOT NULL,
                    rigidity TEXT CHECK (rigidity IN ('hard','firm','soft','free')) DEFAULT 'soft',
                    energy_tag TEXT,
                    start_at TIMESTAMPTZ NOT NULL,
                    end_at   TIMESTAMPTZ NOT NULL,
                    tone_at_start TEXT CHECK (tone_at_start IN ('gentle','coach','ds')) DEFAULT 'gentle',
                    start_confirmed_at TIMESTAMPTZ,
                    midpoint_status TEXT,
                    end_status TEXT,
                    reason_code TEXT,
                    reschedule_target TIMESTAMPTZ,
                    distraction_flag BOOLEAN DEFAULT FALSE,
                    theme_alignment BOOLEAN,
                    score_delta INTEGER DEFAULT 0,
                    location_id TEXT,
                    tz TEXT,
                    travel_buffer_min INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS day_state (
                    day DATE PRIMARY KEY,
                    current_tone TEXT CHECK (current_tone IN ('gentle','coach','ds')) DEFAULT 'gentle',
                    consecutive_misses INTEGER DEFAULT 0,
                    consecutive_completions INTEGER DEFAULT 0,
                    tone_cooldown_until TIMESTAMPTZ,
                    recovery_blocks_used INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS missed_queue (
                    id SERIAL PRIMARY KEY,
                    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recovery_blocks (
                    id SERIAL PRIMARY KEY,
                    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
                    scheduled_at TIMESTAMPTZ NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id SERIAL PRIMARY KEY,
                    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                    kind TEXT,     -- 'editor','focus','location','tz'
                    value TEXT,
                    meta JSONB
                );
            """)
            
            # ✅ Legacy compatibility: ensure `title` column exists on segments
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'segments' AND column_name = 'title'
                    ) THEN
                        ALTER TABLE segments ADD COLUMN title TEXT;
                    END IF;
                END
                $$;
            """)

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_start ON segments(start_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_segments_end_status ON segments(end_status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_missed_queue_created ON missed_queue(created_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_recovery_scheduled ON recovery_blocks(scheduled_at);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_recovery_once ON recovery_blocks(segment_id, scheduled_at);")

        conn.commit()

def was_event_notified(event_id: str, phase: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM event_notifications WHERE event_id = %s AND phase = %s",
                (event_id, phase)
            )
            return cur.fetchone() is not None

def mark_event_as_notified(event_id: str, phase: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO event_notifications (event_id, phase) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (event_id, phase)
            )
        conn.commit()

def save_postponed_reminder(event_id: str, remind_at: dt.datetime):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO postponed_reminders (event_id, remind_at)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (event_id, remind_at))
        conn.commit()

def get_due_postponed_reminders(now: dt.datetime) -> list[tuple[str, dt.datetime]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, remind_at FROM postponed_reminders
                WHERE remind_at <= %s
            """, (now,))
            return cur.fetchall()

def delete_postponed_reminder(event_id: str, remind_at: dt.datetime):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM postponed_reminders
                WHERE event_id = %s AND remind_at = %s
            """, (event_id, remind_at))
        conn.commit()

def is_event_blocked(user_id: str, event_title: str, phase: str) -> bool:
    keywords = [word.strip().lower() for word in event_title.lower().split()]
    if not keywords:
        return False

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                q_marks = ",".join(["%s"] * len(keywords))
                query = f"""
                    SELECT 1 FROM event_preferences
                    WHERE user_id = %s
                    AND keyword IN ({q_marks})
                    AND block_phase IN (%s, %s)
                    LIMIT 1
                """
                params = [user_id] + keywords + [phase, "all"]
                cur.execute(query, params)
                return cur.fetchone() is not None
    except Exception:
        # table may not exist yet → default to not blocked
        return False
        
def get_events_for_review(now):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM events
                    WHERE end_time BETWEEN %s - INTERVAL '2 hours' AND %s
                    AND ai_reviewed IS NOT TRUE
                """, (now, now))
                return [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]
    except Exception:
        return []

def mark_ai_reviewed(event_id):
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE events SET ai_reviewed = TRUE WHERE event_id = %s", (event_id,))
                conn.commit()
    except Exception:
        return

def get_user_context(user_id, now):
    return {
        "today": now.date().isoformat(),
        "user_values": "Faith, Family, Focus",
        "spiritual_goals": "Pray daily, Sabbath on Saturday, journal at night",
        "weekly_theme": "Ruoth listings",
        "known_struggles": "Neglects rest; works late"
    }
    
def log_event(event_id: str, status: str, timestamp: dt.datetime, quadrant: str = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO event_log (event_id, status, timestamp, quadrant)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id, status) DO NOTHING
            """, (event_id, status, timestamp, quadrant))
        conn.commit()
        
def save_conversation_turn(user_id: str, role: str, content: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations (user_id, role, content)
                VALUES (%s, %s, %s)
            """, (user_id, role, content))
        conn.commit()

def get_recent_conversation(user_id: str, limit: int = 6):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM conversations
                WHERE user_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (user_id, limit))
            rows = cur.fetchall()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        
def clear_conversation_history(user_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        conn.commit()
        
# --- segments CRUD ---

def insert_segment(seg: dict):
    cols = ", ".join(seg.keys())
    vals = ", ".join(["%s"] * len(seg))
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO segments ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING", tuple(seg.values()))
        conn.commit()

def update_segment(seg_id: str, **fields):
    if not fields:
        return
    sets = ", ".join([f"{k}=%s" for k in fields.keys()])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE segments SET {sets} WHERE id=%s", tuple(fields.values()) + (seg_id,))
        conn.commit()

def get_active_segment(now) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM segments
            WHERE start_at <= %s AND end_at >= %s
            ORDER BY start_at DESC LIMIT 1
        """, (now, now))
        row = cur.fetchone()
        if not row: return None
        return dict(zip([d.name for d in cur.description], row))

def get_next_segment(after_ts) -> dict | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM segments
            WHERE start_at > %s
            ORDER BY start_at ASC LIMIT 1
        """, (after_ts,))
        row = cur.fetchone()
        if not row: return None
        return dict(zip([d.name for d in cur.description], row))


# --- day_state helpers ---

def get_day_state(day) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM day_state WHERE day=%s", (day,))
        row = cur.fetchone()
        if row:
            return dict(zip([d.name for d in cur.description], row))
        cur.execute("INSERT INTO day_state (day) VALUES (%s) RETURNING *", (day,))
        row = cur.fetchone()
        conn.commit()
        return dict(zip([d.name for d in cur.description], row))

def set_day_state(day, **fields):
    if not fields: return
    sets = ", ".join([f"{k}=%s" for k in fields.keys()])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"""
            UPDATE day_state SET {sets}, updated_at=now()
            WHERE day=%s
        """, tuple(fields.values()) + (day,))
        conn.commit()


# --- queues ---

def enqueue_missed(segment_id: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO missed_queue (segment_id) VALUES (%s)", (segment_id,))
        conn.commit()

# Alias for clarity
def push_to_missed_queue(segment_id: str):
    enqueue_missed(segment_id)

def schedule_recovery(segment_id: str, scheduled_at, reason: str | None = None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO recovery_blocks (segment_id, scheduled_at, reason)
            VALUES (%s, %s, %s)
            ON CONFLICT (segment_id, scheduled_at) DO NOTHING
        """, (segment_id, scheduled_at, reason))
        conn.commit()

# --- segment lifecycle writers (used by FSM/observer) ---

def mark_segment_start(seg_id: str, ts: dt.datetime, tone_at_start: str | None = None):
    fields = {"start_confirmed_at": ts}
    if tone_at_start:
        fields["tone_at_start"] = tone_at_start
    update_segment(seg_id, **fields)

def set_midpoint_status(seg_id: str, status: str):
    # expected values: 'ok','mia','overrun','pivot'
    update_segment(seg_id, midpoint_status=status)

def close_segment(
    seg_id: str,
    end_status: str,                      # 'completed','rescheduled','missed','pivoted','rest','drift'
    reason_code: str | None = None,
    reschedule_target: dt.datetime | None = None,
    score_delta: int = 0
):
    fields = {"end_status": end_status, "score_delta": score_delta}
    if reason_code is not None:
        fields["reason_code"] = reason_code
    if reschedule_target is not None:
        fields["reschedule_target"] = reschedule_target
    update_segment(seg_id, **fields)

# --- day_state convenience helpers for tone/escalation ---

def inc_consecutive_misses(day: dt.date):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE day_state
            SET consecutive_misses = consecutive_misses + 1,
                consecutive_completions = 0,
                updated_at = now()
            WHERE day = %s
        """, (day,))
        conn.commit()

def inc_consecutive_completions(day: dt.date):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE day_state
            SET consecutive_completions = consecutive_completions + 1,
                consecutive_misses = 0,
                updated_at = now()
            WHERE day = %s
        """, (day,))
        conn.commit()

def set_tone(day: dt.date, tone: str, cooldown_until: dt.datetime | None = None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE day_state
            SET current_tone = %s,
                tone_cooldown_until = %s,
                updated_at = now()
            WHERE day = %s
        """, (tone, cooldown_until, day))
        conn.commit()

def reset_streaks(day: dt.date):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE day_state
            SET consecutive_misses = 0,
                consecutive_completions = 0,
                updated_at = now()
            WHERE day = %s
        """, (day,))
        conn.commit()
        
        