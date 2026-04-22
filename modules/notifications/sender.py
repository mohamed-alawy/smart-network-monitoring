import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

_SENDER = os.getenv("SMTP_SENDER", "")
_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "")


def send_email(to: str, subject: str, body: str) -> str | None:
    """Send email via Gmail SMTP. Returns None on success, error string on failure."""
    msg = MIMEMultipart()
    msg["From"] = _SENDER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(_SENDER, _PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent to {to} | subject: {subject}")
        return None
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return str(e)
