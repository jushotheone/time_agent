# db.py
import os
import psycopg2
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
        conn.commit()

def was_event_notified(event_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM event_notifications WHERE event_id = %s", (event_id,))
            return cur.fetchone() is not None

def mark_event_as_notified(event_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO event_notifications (event_id) VALUES (%s) ON CONFLICT DO NOTHING", (event_id,))
        conn.commit()