import os
import logging
from telegram.error import BadRequest
from agent_brain.core import conversational_brain

logging.basicConfig(level=logging.INFO)

# If the router didn't give us real user text, these strings are too vague to send to GPT
_BAD_DEFAULTS = {
    "✅ action complete.",
    "✅ Action complete.",
    "The user performed the action:",
    "The user performed the action",
}


def _get_chat_id(update, context):
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    if not chat_id:
        chat_id = getattr(getattr(context, "job", None), "chat_id", None)
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
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=None)


def _clean(s: str | None) -> str:
    return (s or "").strip()


def _looks_like_bad_default(s: str) -> bool:
    if not s:
        return True
    if s in _BAD_DEFAULTS:
        return True
    # "The user performed the action: xyz" patterns
    if s.lower().startswith("the user performed the action"):
        return True
    return False


def _build_llm_user_message(parsed: dict, summary: str | None) -> str:
    """
    Build the user message that we send to conversational_brain().

    Rules:
    - If we have 'summary' (facts), lead with an instruction + facts.
    - Otherwise, prefer the REAL user text (parsed['user_prompt']) if available.
    - Avoid feeding parsed['reply'] back into the brain as the "user said..." text.
    """
    action = _clean(parsed.get("action"))

    # 1) Facts-first mode (agenda/event summaries/etc.)
    if summary and _clean(summary):
        return (
            "Write the exact message to send to the user.\n"
            "Be concise, human, and action-first.\n"
            "Do not mention internal errors, tool calls, or debugging.\n"
            "If helpful, include ONE next move.\n\n"
            "Facts (treat these as the source of truth; do not rewrite them):\n"
            f"{summary.strip()}"
        )

    # 2) No facts: companion chat mode. Use the actual user text.
    user_prompt = _clean(parsed.get("user_prompt"))
    if user_prompt:
        return (
            "Reply as the user’s time companion.\n"
            "Be warm and brief.\n"
            "If the user is greeting you or chatting, acknowledge it and offer ONE useful next move "
            "(eg WHAT'S ON NOW / SUMMARY today), without interrogating them.\n\n"
            f"User said: {user_prompt}"
        )

    # 3) Absolute fallback: minimal, safe, non-looping
    # Avoid the “chat_fallback action…” loop.
    if action == "chat_fallback":
        return (
            "Reply as the user’s time companion.\n"
            "Be warm and brief.\n"
            "Offer ONE next move (eg WHAT'S ON NOW / SUMMARY today).\n\n"
            "User said: (no text captured)"
        )

    # 4) Last resort: acknowledge the action without sounding broken
    return (
        "Reply as the user’s time companion.\n"
        "Confirm the last thing you did in one short sentence, then offer ONE next move.\n\n"
        f"Action: {action or 'unknown'}"
    )


async def respond_with_brain(
    update,
    context,
    parsed,
    *,
    system=None,
    user=None,
    summary=None,
    send=True,
    parse_mode="Markdown",
):
    """
    Main rule:
    - If summary exists -> send instruction + facts.
    - Else -> send the *real user text* (parsed['user_prompt']) to conversational_brain.
    """
    # If caller explicitly passes a user message, honour it
    user_msg = _clean(user)

    # Otherwise, build it deterministically
    if not user_msg:
        user_msg = _build_llm_user_message(parsed or {}, summary)

    # Guard: if some caller passed junk defaults, override them
    if _looks_like_bad_default(user_msg):
        user_msg = _build_llm_user_message(parsed or {}, summary)

    logging.info(f"🧠 Final user_message sent to GPT:\n{user_msg}\n")

    try:
        if system and _clean(system):
            llm_text = await conversational_brain({"system": system, "user": user_msg})
        else:
            llm_text = await conversational_brain(user_msg)
    except Exception as e:
        logging.exception("conversational_brain failed: %s", e)
        llm_text = "⚠️ Quick hiccup on my side. Try: WHAT'S ON NOW or SUMMARY today."

    if send:
        await send_text_safe(update, context, llm_text, parse_mode=parse_mode)

    return llm_text