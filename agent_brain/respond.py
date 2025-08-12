import os, logging
from telegram.error import BadRequest
from agent_brain.core import conversational_brain

logging.basicConfig(level=logging.INFO)

def _get_chat_id(update, context):
    # Try update first
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    # Then JobQueue context (if you stored it there)
    if not chat_id:
        chat_id = getattr(getattr(context, "job", None), "chat_id", None)
    # Finally env var
    if not chat_id:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
    return chat_id

async def send_text_safe(update, context, text, parse_mode="Markdown"):
    chat_id = _get_chat_id(update, context)
    if not chat_id:
        logging.error("send_text_safe: no chat_id available; dropping message")
        return
    if not text or not str(text).strip():
        logging.info("send_text_safe: empty response; nothing to send")
        return
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except BadRequest:
        # Fallback to plain text if Markdown trips on formatting
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=None)

async def respond_with_brain(
    update,
    context,
    parsed,
    *,
    system=None,
    user=None,
    summary=None,
    send=True,
    parse_mode="Markdown"
):
    # Build user message if not provided explicitly
    if user is None:
        user = parsed.get("user_prompt") or parsed.get("reply") \
               or f"The user performed the action: {parsed.get('action')}"

    if summary:
        user += f"\n\nPlease respond naturally based on the following calendar info:\n{summary}"

    logging.info(f"🧠 Final user_message sent to GPT:\n{user}\n")

    # Call your conversational brain (supports both string and {system,user} payloads)
    try:
        llm_text = await conversational_brain({"system": system, "user": user}) if system else await conversational_brain(user)
    except Exception as e:
        logging.exception("conversational_brain failed: %s", e)
        llm_text = "I hit a snag generating that message. I’ll try again shortly."

    if send:
        await send_text_safe(update, context, llm_text, parse_mode=parse_mode)

    return llm_text