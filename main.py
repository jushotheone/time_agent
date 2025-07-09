# Entry point for non-telegram CLI testing
import argparse, datetime as dt, zoneinfo, os
import gpt_agent
import calendar_client as cal

TZ = zoneinfo.ZoneInfo(os.getenv("TIMEZONE", "UTC"))

parser = argparse.ArgumentParser(description="Test calendar assistant via CLI.")
parser.add_argument("text", help="Natural language scheduling command")
args = parser.parse_args()

parsed = gpt_agent.parse(args.text)
if not parsed:
    print("Could not parse instruction.")
    exit()

title = parsed['title']
date = parsed['date']
time = parsed['time']
duration = parsed['duration_minutes']
start = dt.datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=TZ)
event = cal.create_event(title, start, duration)
print("Booked:", event['htmlLink'])
