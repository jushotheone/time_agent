import os, logging, datetime as dt, zoneinfo
from dotenv import load_dotenv
import beia_core.models.timebox as db
from beia_core.models.enums import Domain
from beia_core.models.core import Sprint, Build, Subdomain

import re

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


import gpt_agent
from agent_brain.scheduler import (
    send_daily_agenda,
    send_time_reminders,
    handle_remind_again
)
import calendar_client as cal
from ai_agent_loop import run_ai_loop
from agent_brain.weekly_audit import send_weekly_audit
from agent_brain.evening_review import run_evening_review
from datetime import datetime as _dt
from zoneinfo import ZoneInfo as _ZoneInfo
from agent_brain import actions as AB
from agent_brain import observer as OBS

load_dotenv()
db.init_db()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

# bot.py (only the updated functions)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    # 1) ✅ Contract-first deterministic parser (CP-1 / CC-3)
    parsed = gpt_agent.parse_command(text)

    # 2) ✅ If not a contract command, use LLM tool-call parser (calendar ops)
    if not parsed:
        parsed = gpt_agent.parse(text)

    # 3) ✅ If still nothing, route to companion brain (no hardcoded assistant fluff)
    if not parsed:
        # Push raw user text into the companion brain via AB's existing fallback path
        # so the tone + context rules apply.
        parsed = {"action": "chat_fallback", "user_prompt": text}

    try:
        await AB.handle_action(parsed, update, context)
    except ValueError as ve:
        await update.message.reply_text(str(ve))
    except Exception as e:
        await update.message.reply_text(f"⚠️ Something went wrong while processing: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Time Master ready.\n\n"
        "Try:\n"
        "- SUMMARY today\n"
        "- WHAT DID I MISS today\n"
        "- WHAT’S NEXT\n"
        "- DONE <title>\n"
        "- DIDNT START <title>\n"
        "- NEED MORE <title> <minutes>\n\n"
        "Or just speak normally, e.g. “Add band practice today at 20:00”."
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = cal.list_today()
    if not events:
        await update.message.reply_text("You have no events today.")
        return
    lines = []
    for ev in events:
        start = ev['start'].get('dateTime', ev['start'].get('date'))
        dt_start = dt.datetime.fromisoformat(start).astimezone(TZ)
        lines.append(f"{dt_start.strftime('%H:%M')} • {ev['summary']}")
    await update.message.reply_text("\n".join(lines))
    
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Time Master ready. Try: SUMMARY today, WHAT’S NEXT, or SCHEDULE <title> <minutes>."
    )
    
_CHAT_TZ = _ZoneInfo(os.getenv("TIMEZONE", "UTC"))

async def handle_wf0_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Expects callback_data like: wf0:<segment_id>:<verb>[:arg]
    Examples:
      wf0:seg123:send_start
      wf0:seg123:snooze_segment:10
      wf0:seg123:extend_15
      wf0:seg123:pivot:Write proposal
    """
    q = update.callback_query
    await q.answer()

    try:
        _, seg_id, verb, *rest = q.data.split(":", 3)
    except ValueError:
        await q.edit_message_text("⚠️ Sorry, I couldn’t parse that action.")
        return

    parsed = {"action": verb, "segment_id": seg_id}

    # optional arg (minutes or new focus)
    if rest:
        arg = rest[0]
        if verb == "snooze_segment":
            try:
                parsed["minutes"] = int(arg)
            except ValueError:
                parsed["minutes"] = 5
        elif verb in ("extend_15", "extend_30"):
            # keep verb as-is; actions will map to minutes
            pass
        elif verb == "pivot":
            parsed["new_focus"] = arg

    # Reuse your normal action router so replies go through the LLM
    await AB.handle_action(parsed, update, context)

async def handle_domain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles domain selection callbacks.
    Callback format: domain|<event_id>|<domain>[|<subdomain>[|<build_id>[|<sprint_id>]]]
    """
    q = update.callback_query
    await q.answer()

    try:
        parts = q.data.split("|")
        _, event_id, domain = parts[:3]
        subdomain_slug = parts[3] if len(parts) > 3 else None
        build_id      = parts[4] if len(parts) > 4 else None
        sprint_id     = parts[5] if len(parts) > 5 else None
    except ValueError:
        await q.edit_message_text("⚠️ Invalid domain choice format.")
        return

    try:
        # Update both GCal + Postgres
        cal.link_event_to_domain(
            event_id,
            domain,
            subdomain_slug=subdomain_slug,
            build_id=build_id,
            sprint_id=sprint_id,
        )

        # Build human-friendly response
        parts_human = [domain.title()]
        if subdomain_slug:
            parts_human.append(subdomain_slug.title())
        if build_id:
            parts_human.append(f"Build {build_id}")
        if sprint_id:
            parts_human.append(f"Sprint {sprint_id}")

        await q.edit_message_text(f"✅ Linked event to: *{' / '.join(parts_human)}*")

    except Exception as e:
        await q.edit_message_text(f"⚠️ Failed to link domain: {e}")

def build_domain_keyboard(event_id: str, subdomains=None):
    """
    Build inline keyboard from backend Domain enum.
    Supports optional subdomains for each domain.
    Callback format: domain|<event_id>|<domain>[|<subdomain>[|<build_id>[|<sprint_id>]]]
    """
    buttons = []
    for d in Domain:
        # If subdomains for this domain exist, add buttons for each
        if subdomains and d.name in subdomains:
            for sub in subdomains[d.name]:
                buttons.append([
                    InlineKeyboardButton(
                        f"{d.value.title()} / {sub.title()}",
                        callback_data=f"domain|{event_id}|{d.name}|{sub}"
                    )
                ])
        else:
            # Fallback: domain only
            buttons.append([
                InlineKeyboardButton(
                    d.value.title(),
                    callback_data=f"domain|{event_id}|{d.name}"
                )
            ])
    return InlineKeyboardMarkup(buttons)

async def handle_pivot_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    m = re.match(r"^i'?m doing (.+)$", text, flags=re.IGNORECASE)
    if not m:
        return

    new_focus = m.group(1).strip()
    # drop trailing "now" if present
    if new_focus.lower().endswith(" now"):
        new_focus = new_focus[:-4].strip(" .")

    now = _dt.now(_CHAT_TZ)
    seg = db.get_active_segment(now)
    if not seg:
        await update.message.reply_text("There isn’t an active block to pivot from right now.")
        return

    parsed = {"action": "pivot", "segment_id": seg["id"], "new_focus": new_focus or "Ad‑hoc Focus"}
    await AB.handle_action(parsed, update, context)

async def wf0_tick(context):
    """Runs every minute. Pulls FSM ticks & gap detections and dispatches actions."""
    results = OBS.detect_drift()  # returns list[{'segment_id','action','tone','event'}] or None
    if not results:
        return
    chat_id = os.getenv("TELEGRAM_CHAT_ID")  # or derive from your user model
    if not chat_id:
        return
    # Build a fake Update/Context so we can reuse handle_action’s reply path
    class _ShimUpdate: pass
    shim_update = _ShimUpdate()
    shim_update.effective_chat = type("C", (), {"id": chat_id})()
    shim_update.callback_query = None
    shim_update.message = None

    for r in results:
        parsed = {"action": r["action"], "segment_id": r["segment_id"]}
        await AB.handle_action(parsed, shim_update, context)
        
async def ai_loop_job(context):
    await run_ai_loop()
    
async def weekly_audit_job(context):
    await send_weekly_audit()
    
async def evening_review_job(context):
    await run_evening_review()

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_remind_again, pattern=r"^remind_again\|"))
    app.add_handler(CallbackQueryHandler(handle_domain_callback, pattern=r"^domain\|"))
    app.job_queue.run_repeating(ai_loop_job, interval=3600)
    app.job_queue.run_repeating(wf0_tick, interval=60, first=0)

    # ✅ Daily Agenda (early morning)
    send_daily_agenda(app)

    # ✅ Time-sensitive event reminders
    send_time_reminders(app)

    # 🧠 Weekly Audit (Sunday 21:00)
    app.job_queue.run_daily(weekly_audit_job, time=dt.time(hour=21, minute=0, tzinfo=TZ), days=(6,))

    # 🌙 Evening Review (Every day at 21:30)
    app.job_queue.run_daily(evening_review_job, time=dt.time(hour=21, minute=30, tzinfo=TZ))
    app.add_handler(CallbackQueryHandler(handle_wf0_callback, pattern=r"^wf0:"))
    app.add_handler(
    MessageHandler(
        filters.Regex(re.compile(r"^(i'?m doing )", re.IGNORECASE)) & ~filters.COMMAND,
        handle_pivot_text
    )
)
    
    app.run_polling()
    
if __name__ == "__main__":
    main()
