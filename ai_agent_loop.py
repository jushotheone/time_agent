# ai_agent_loop.py
import datetime as dt
from db import get_events_for_review, mark_ai_reviewed, get_user_context
from gpt_agent import generate_nudge
from telegram import Bot
import os
import asyncio

from agent_brain.core import run_brain
from agent_brain.weekly_audit import run_weekly_audit
from agent_brain.quadrant_detector import detect_quadrant
from agent_brain.evening_review import run_evening_review

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

def run_ai_loop():
    now = dt.datetime.utcnow()

    # 🧠 Executive loop: detect drift, reschedule, nudge
    asyncio.run(run_brain())

    # After run_brain() and before review nudges
    followup_missed_q2(now)
    
    # 🌙 Evening review
    run_evening_review()

    
    # 📅 Sunday: Run weekly quadrant audit
    if now.weekday() == 6:  # Sunday
        audit_summary = run_weekly_audit()
        if audit_summary:
            bot.send_message(
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=audit_summary,
                parse_mode="Markdown"
            )

    # 🤖 Review recently completed events
    events = get_events_for_review(now)
    for event in events:
        user_id = event["user_id"]
        context = get_user_context(user_id, now)
        nudge = generate_nudge(event, context)

        if nudge:
            bot.send_message(chat_id=user_id, text=nudge, parse_mode="Markdown")
            mark_ai_reviewed(event["event_id"])
            
def followup_missed_q2(now):
    from db import get_conn
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, status FROM event_log
                WHERE quadrant = 'II'
                AND status = 'missed'
                AND followed_up IS NOT TRUE
                AND timestamp >= %s
            """, (now - dt.timedelta(days=3),))

            missed_q2_events = cur.fetchall()

            for event_id, status in missed_q2_events:
                # Prevent double-followup
                cur.execute("UPDATE event_log SET followed_up = TRUE WHERE event_id = %s AND status = %s", (event_id, status))
                conn.commit()

                msg = f"🙏 You missed a Q2 block recently. Want to reschedule or reflect on it?\nEvent: *{event_id}*"
                bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=msg, parse_mode="Markdown")