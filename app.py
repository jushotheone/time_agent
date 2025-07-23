# app.py
from apscheduler.schedulers.background import BackgroundScheduler
from agent_brain.evening_review import run_evening_review
from agent_brain.weekly_audit import send_weekly_audit
from ai_agent_loop import run_ai_loop
from datetime import datetime
import time
import logging

# Optional: Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    scheduler = BackgroundScheduler(timezone="Europe/London")

    # 🧠 Agent loop — runs every 30 minutes
    scheduler.add_job(run_ai_loop, 'interval', minutes=30, id='ai_agent_loop')
    logger.info("Scheduled: AI Agent Loop every 30 minutes")

    # 🌙 Evening Review — every day at 21:30
    scheduler.add_job(run_evening_review, 'cron', hour=21, minute=30, id='evening_review')
    logger.info("Scheduled: Evening Review at 21:30 daily")

    # 📊 Weekly Audit — every Sunday at 21:00
    scheduler.add_job(send_weekly_audit, 'cron', day_of_week='sun', hour=21, id='weekly_audit')
    logger.info("Scheduled: Weekly Audit on Sundays at 21:00")

    scheduler.start()
    logger.info("🚀 Assistant Scheduler is running...")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("🛑 Scheduler shutdown gracefully")

if __name__ == "__main__":
    main()