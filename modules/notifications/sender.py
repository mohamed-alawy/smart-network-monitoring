import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger


def send_email(to: str, subject: str, body: str) -> str | None:
    """Send email via Gmail SMTP. Returns None on success, error string on failure."""
    sender   = os.getenv("SMTP_SENDER", "").strip()
    password = os.getenv("SMTP_APP_PASSWORD", "").strip()

    if not sender or not password:
        err = "SMTP_SENDER or SMTP_APP_PASSWORD not configured"
        logger.error(err)
        return err

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.send_message(msg)
        logger.info(f"Email sent to {to} | subject: {subject}")
        return None
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return str(e)
