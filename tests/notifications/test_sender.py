from unittest.mock import patch, MagicMock
from modules.notifications.sender import send_email


def test_send_email_success():
    with patch("modules.notifications.sender.smtplib.SMTP") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        err = send_email("to@example.com", "Subject", "Body")
        assert err is None


def test_send_email_returns_error_string_on_failure():
    with patch("modules.notifications.sender.smtplib.SMTP", side_effect=Exception("connection refused")):
        err = send_email("to@example.com", "Subject", "Body")
        assert err is not None
        assert "connection refused" in err
