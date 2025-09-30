# =============================
# agent_brain/weekly_audit.py
# =============================
from telegram import Bot
import os
import datetime as dt
from zoneinfo import ZoneInfo
import beia_core.models.timebox as db
from collections import defaultdict
import asyncio

TZ = ZoneInfo("Europe/London")

QUADRANT_LABELS = {
    "I": "Q1 — Urgent + Important",
    "II": "Q2 — Important but Not Urgent",
    "III": "Q3 — Urgent but Not Important",
    "IV": "Q4 — Not Urgent + Not Important",
    None: "Unclassified"
}

def start_of_week(now):
    return (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

def end_of_week(start):
    return start + dt.timedelta(days=7)

def audit_quadrants(now=None):
    now = now or dt.datetime.now(TZ)
    start = start_of_week(now)
    end = end_of_week(start)

    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT quadrant, COUNT(*) FROM event_log
                WHERE timestamp BETWEEN %s AND %s
                GROUP BY quadrant
            """, (start, end))
            rows = cur.fetchall()

    stats = defaultdict(int, {row[0]: row[1] for row in rows})
    total = sum(stats.values()) or 1

    report_lines = ["📊 *Weekly Time Audit*"]
    report_lines.append(f"From *{start.date()}* to *{(end - dt.timedelta(days=1)).date()}*:\n")

    for code in ["II", "I", "III", "IV", None]:
        label = QUADRANT_LABELS[code]
        count = stats[code]
        pct = round((count / total) * 100)
        report_lines.append(f"• {label}: {count} events ({pct}%)")

    # Micro-coaching nudge
    q2_pct = (stats["II"] / total) * 100
    q3_pct = (stats["III"] / total) * 100
    advice = []

    if q2_pct < 20:
        advice.append("⚠️ You spent little time on Q2 (important but not urgent). Let’s protect this zone better next week.")
    if q3_pct > 30:
        advice.append("🧹 Q3 is noisy — too many urgent-but-unimportant tasks. Consider setting stronger boundaries.")

    if advice:
        report_lines.append("\n🎯 *Coaching Insight*")
        report_lines.extend(advice)

    return "\n".join(report_lines)

def run_weekly_audit():
    summary = audit_quadrants()
    return summary

async def send_weekly_audit():
    summary = audit_quadrants()
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    await bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=summary, parse_mode="Markdown")

if __name__ == "__main__":
    print(run_weekly_audit())