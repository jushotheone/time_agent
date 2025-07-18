import openai
from jinja2 import Template
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

def generate_nudge(event, context):
    with open("prompts/daily_review.txt") as f:
        template = Template(f.read())

    prompt = template.render(event=event, context=context)

    res = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "system", "content": prompt}]
    )

    reply = res.choices[0].message["content"]
    return reply.strip() if "❌" not in reply else None