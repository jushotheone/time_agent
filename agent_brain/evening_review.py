# agent_brain/evening_review.py
import datetime as dt
from telegram import Bot
import os
import asyncio

async def run_evening_review():
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    now = dt.datetime.now()

    message = (
        "🌙 *Evening Reflection Time*\n"
        "- What worked well today?\n"
        "- What would you change?\n"
        "- Did you protect your Q2 blocks?\n\n"
        "📆 Want to adjust tomorrow’s plan now?"
    )

    await bot.send_message(
        chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        text=message,
        parse_mode="Markdown"
    )