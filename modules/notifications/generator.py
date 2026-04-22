import os
from loguru import logger
from modules.notifications.templates.message_templates import (
    engineer_message,
    call_center_message,
    client_message_template,
)

_RECIPIENT_MAP = {
    "critical": ["engineer", "call_center", "client"],
    "high": ["engineer", "call_center", "client"],
    "medium": ["call_center"],
    "low": [],
}

_CLIENT_PROMPT = (
    "You are a customer service agent for a telecom company. "
    "Write a short, polite, non-technical apology to a customer about a service disruption. "
    "Location: {location}. Expected resolution time: {eta}. "
    "Keep it under 3 sentences. Do not mention technical details."
)


def get_llm():
    from modules.rag.chain.llm_provider import get_llm as _get_llm
    return _get_llm()


def get_recipients(priority: str) -> list[str]:
    return _RECIPIENT_MAP.get(priority.lower(), [])


def _llm_client_message(location: str, rag: dict) -> str:
    llm = get_llm()
    prompt = _CLIENT_PROMPT.format(
        location=location,
        eta=rag["estimated_resolution_time"],
    )
    return llm.invoke(prompt).content


def generate_messages(location: str, rag_output: dict, recipients: list[str]) -> dict[str, str]:
    mode = os.getenv("NOTIFICATION_LLM_MODE", "hybrid").lower()
    messages = {}

    for recipient in recipients:
        if recipient == "engineer":
            messages["engineer"] = engineer_message(location, rag_output)
        elif recipient == "call_center":
            messages["call_center"] = call_center_message(location, rag_output)
        elif recipient == "client":
            if mode in ("llm", "hybrid"):
                try:
                    messages["client"] = _llm_client_message(location, rag_output)
                except Exception as e:
                    logger.warning(f"LLM client message failed, falling back to template: {e}")
                    messages["client"] = client_message_template(location, rag_output)
            else:
                messages["client"] = client_message_template(location, rag_output)

    return messages
