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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS event_notifications (
                    event_id TEXT PRIMARY KEY,
                    notified_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    event_id TEXT,
                    status TEXT,
                    timestamp TIMESTAMPTZ DEFAULT now(),
                    quadrant TEXT,
                    PRIMARY KEY (event_id, status)
                );
            """)
             # ✅ NEW: conversation memory
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    user_id TEXT,
                    role TEXT CHECK (role IN ('user', 'assistant')),
                    content TEXT,
                    timestamp TIMESTAMPTZ DEFAULT now()
                );
            """)
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
        
def get_events_for_review(now):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM events
                WHERE end_time BETWEEN %s - INTERVAL '2 hours' AND %s
                AND ai_reviewed IS NOT TRUE
            """, (now, now))
            return [dict(zip([desc[0] for desc in cur.description], row)) for row in cur.fetchall()]

def mark_ai_reviewed(event_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE events SET ai_reviewed = TRUE WHERE event_id = %s", (event_id,))
            conn.commit()

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