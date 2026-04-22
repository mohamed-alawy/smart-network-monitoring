import os
from fastapi import FastAPI
from pydantic import BaseModel
from loguru import logger
from modules.notifications.generator import get_recipients, generate_messages
from modules.notifications.sender import send_email

app = FastAPI(title="Notification Engine")

_EMAIL_MAP = {
    "engineer": lambda: os.getenv("ENGINEER_EMAIL", ""),
    "call_center": lambda: os.getenv("CALL_CENTER_EMAIL", ""),
    "client": lambda: os.getenv("CLIENT_EMAIL", ""),
}

_SUBJECT_MAP = {
    "engineer": "🚨 Network Alert",
    "call_center": "Network Issue Update",
    "client": "Service Update",
}


class RagOutput(BaseModel):
    cause_explanation: str
    priority: str
    estimated_resolution_time: str
    suggested_solution: list[str]
    affected_standards: list[str] = []
    escalation_needed: bool = False
    additional_notes: str = ""


class NotificationRequest(BaseModel):
    location: str
    rag_output: RagOutput


class NotificationResponse(BaseModel):
    recipients_notified: list[str]
    status: str
    errors: list[str]


@app.post("/notifications/send", response_model=NotificationResponse)
def send_notification(req: NotificationRequest) -> NotificationResponse:
    rag = req.rag_output.model_dump()
    recipients = get_recipients(req.rag_output.priority)

    if not recipients:
        logger.info(f"No recipients for priority={req.rag_output.priority}")
        return NotificationResponse(recipients_notified=[], status="success", errors=[])

    messages = generate_messages(req.location, rag, recipients)
    notified, errors = [], []

    for recipient in recipients:
        to = _EMAIL_MAP[recipient]()
        if not to:
            logger.warning(f"No email configured for {recipient}, skipping")
            errors.append(f"{recipient} email not configured")
            continue
        subject = _SUBJECT_MAP[recipient]
        body = messages[recipient]
        err = send_email(to, subject, body)
        if err:
            errors.append(f"{recipient} email failed: {err}")
            logger.warning(f"Failed to notify {recipient}: {err}")
        else:
            notified.append(recipient)

    status = "success" if not errors else ("partial" if notified else "failed")
    return NotificationResponse(recipients_notified=notified, status=status, errors=errors)
