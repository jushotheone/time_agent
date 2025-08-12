# ai_agent_loop.py
import os, asyncio, inspect, datetime as dt
from telegram import Bot

from db import get_events_for_review, mark_ai_reviewed, get_user_context
from gpt_agent import generate_nudge

from agent_brain.core import run_brain
from agent_brain.weekly_audit import run_weekly_audit
from agent_brain.evening_review import run_evening_review

# helper: call bot.send_message whether it's async (PTB v20+) or sync
async def _send(bot, **kwargs):
    fn = bot.send_message
    if inspect.iscoroutinefunction(fn):
        return await fn(**kwargs)
    # sync fallback (older libs or your own wrapper)
    return await asyncio.to_thread(fn, **kwargs)

async def run_ai_loop():
    now = dt.datetime.utcnow()
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

    # 🧠 Main brain pass (was asyncio.run(run_brain()))
    await run_brain()

    # After run_brain() and before review nudges
    await followup_missed_q2(now, bot)

    # 🌙 Evening review (sync in your code; run it off-thread to avoid blocking)
    await asyncio.to_thread(run_evening_review)

    # 📅 Sunday weekly audit
    if now.weekday() == 6:  # Sunday
        audit_summary = await asyncio.to_thread(run_weekly_audit)
        if audit_summary:
            await _send(
                bot,
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                text=audit_summary,
                parse_mode="Markdown",
            )

    # 🤖 Review recently completed events
    events = await asyncio.to_thread(get_events_for_review, now)
    for event in events:
        user_id = event["user_id"]
        context = await asyncio.to_thread(get_user_context, user_id, now)
        nudge = await asyncio.to_thread(generate_nudge, event, context)
        if nudge:
            await _send(bot, chat_id=user_id, text=nudge, parse_mode="Markdown")
            await asyncio.to_thread(mark_ai_reviewed, event["event_id"])

async def followup_missed_q2(now, bot):
    from db import get_conn
    import datetime as dt

    def _fetch():
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, status FROM event_log
                WHERE quadrant = 'II'
                  AND status = 'missed'
                  AND followed_up IS NOT TRUE
                  AND timestamp >= %s
            """, (now - dt.timedelta(days=3),))
            rows = cur.fetchall()
            for event_id, status in rows:
                cur.execute(
                    "UPDATE event_log SET followed_up = TRUE WHERE event_id = %s AND status = %s",
                    (event_id, status),
                )
            conn.commit()
            return rows

    missed_q2_events = await asyncio.to_thread(_fetch)
    for event_id, _ in missed_q2_events:
        msg = f"🙏 You missed a Q2 block recently. Want to reschedule or reflect on it?\nEvent: *{event_id}*"
        await _send(bot, chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=msg, parse_mode="Markdown")