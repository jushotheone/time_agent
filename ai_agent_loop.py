# ai_agent_loop.py
import datetime as dt
from db import get_events_for_review, mark_ai_reviewed, get_user_context
from gpt_agent import generate_nudge
from telegram import Bot
import os

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

def run_ai_loop():
    now = dt.datetime.utcnow()
    events = get_events_for_review(now)

    for event in events:
        user_id = event["user_id"]
        context = get_user_context(user_id, now)
        nudge = generate_nudge(event, context)

        if nudge:
            bot.send_message(chat_id=user_id, text=nudge, parse_mode="Markdown")
            mark_ai_reviewed(event["event_id"])