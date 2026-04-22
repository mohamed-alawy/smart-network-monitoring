import os

from loguru import logger

from modules.notifications.templates.message_templates import (
    engineer_message,
    call_center_message,
    client_message_template,
)


def get_llm():
    """Thin wrapper around the real get_llm; deferred import keeps optional deps lazy."""
    from modules.rag.chain.llm_provider import get_llm as _get_llm
    return _get_llm()

_RECIPIENT_MAP = {
    "high": ["engineer", "call_center", "client"],
    "medium": ["call_center"],
    "low": [],
}

_CLIENT_PROMPT = (
    "You are a customer service agent for a telecom company. "
    "Write a short, polite, non-technical apology to a customer about a service disruption. "
    "Issue: {issue}. Region: {region}. ETA to fix: {eta} minutes. "
    "Keep it under 3 sentences. Do not mention technical details."
)


def get_recipients(severity: str) -> list[str]:
    return _RECIPIENT_MAP.get(severity.lower(), [])


def _llm_client_message(payload: dict) -> str:
    llm = get_llm()
    prompt = _CLIENT_PROMPT.format(
        issue=payload["issue"],
        region=payload["region"],
        eta=payload["eta"],
    )
    return llm.invoke(prompt).content


def generate_messages(payload: dict, recipients: list[str]) -> dict[str, str]:
    mode = os.getenv("NOTIFICATION_LLM_MODE", "hybrid").lower()
    messages = {}

    for recipient in recipients:
        if recipient == "engineer":
            messages["engineer"] = engineer_message(payload)

        elif recipient == "call_center":
            messages["call_center"] = call_center_message(payload)

        elif recipient == "client":
            if mode in ("llm", "hybrid"):
                try:
                    messages["client"] = _llm_client_message(payload)
                except Exception as e:
                    logger.warning(f"LLM client message failed, falling back to template: {e}")
                    messages["client"] = client_message_template(payload)
            else:
                messages["client"] = client_message_template(payload)

    return messages
