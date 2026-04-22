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


class NotificationRequest(BaseModel):
    issue: str
    severity: str
    region: str
    eta: int
    action: str
    root_cause: str


class NotificationResponse(BaseModel):
    recipients_notified: list[str]
    status: str
    errors: list[str]


@app.post("/notifications/send", response_model=NotificationResponse)
def send_notification(req: NotificationRequest) -> NotificationResponse:
    payload = req.model_dump()
    recipients = get_recipients(req.severity)

    if not recipients:
        logger.info(f"No recipients for severity={req.severity}")
        return NotificationResponse(recipients_notified=[], status="success", errors=[])

    messages = generate_messages(payload, recipients)
    notified, errors = [], []

    for recipient in recipients:
        to = _EMAIL_MAP[recipient]()
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
