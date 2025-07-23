from agent_brain.core import conversational_brain
import logging
logging.basicConfig(level=logging.INFO)

async def respond_with_brain(update, context, parsed, summary=None):
    user_message = parsed.get("user_prompt") or parsed.get("reply") or f"The user performed the action: {parsed.get('action')}"
    
    if summary:
        user_message += f"\n\nPlease respond naturally based on the following calendar info:\n{summary}"
    
    logging.info(f"🧠 Final user_message sent to GPT:\n{user_message}\n")

    response = await conversational_brain(user_message)
    await update.message.reply_text(response, parse_mode="Markdown")