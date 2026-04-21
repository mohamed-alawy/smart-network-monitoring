# Notification Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI notification module that takes RAG/RCA output, routes it by severity, generates messages via templates or LLM, and delivers via Gmail SMTP.

**Architecture:** A single POST /notifications/send endpoint receives a structured alert payload, determines recipients based on severity (high→3 recipients, medium→1, low→none), generates messages using the configured mode (template/llm/hybrid), and sends each via Gmail SMTP independently so one failure doesn't block the others.

**Tech Stack:** FastAPI, Pydantic, smtplib (stdlib), LangChain (reuses existing get_llm()), python-dotenv, loguru, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `modules/notifications/__init__.py` | Create | Package marker |
| `modules/notifications/templates/message_templates.py` | Create | f-string message builders for each recipient type |
| `modules/notifications/sender.py` | Create | Gmail SMTP delivery |
| `modules/notifications/generator.py` | Create | Routing logic + message generation (template/llm/hybrid) |
| `modules/notifications/api.py` | Create | FastAPI app with POST /notifications/send |
| `.env.example` | Modify | Add new env vars |
| `requirements.txt` | Modify | No new deps needed (smtplib is stdlib) |
| `tests/notifications/test_templates.py` | Create | Unit tests for template functions |
| `tests/notifications/test_generator.py` | Create | Unit tests for routing + generator |
| `tests/notifications/test_sender.py` | Create | Unit tests for sender (mocked SMTP) |
| `tests/notifications/test_api.py` | Create | Integration tests for POST /notifications/send |

---

## Task 1: Package skeleton + .env additions

**Files:**
- Create: `modules/notifications/__init__.py`
- Create: `modules/notifications/templates/__init__.py`
- Create: `tests/notifications/__init__.py`
- Modify: `.env.example`

- [ ] **Step 1: Create package files**

```bash
mkdir -p .worktrees/rca-notification/modules/notifications/templates
mkdir -p .worktrees/rca-notification/tests/notifications
touch .worktrees/rca-notification/modules/notifications/__init__.py
touch .worktrees/rca-notification/modules/notifications/templates/__init__.py
touch .worktrees/rca-notification/tests/__init__.py
touch .worktrees/rca-notification/tests/notifications/__init__.py
```

- [ ] **Step 2: Add env vars to .env.example**

Append to `.env.example`:
```
# ─── Notifications ────────────────────────────────────────────────────────────
SMTP_SENDER=your@gmail.com
SMTP_APP_PASSWORD=xxxx xxxx xxxx xxxx

ENGINEER_EMAIL=engineer@company.com
CALL_CENTER_EMAIL=callcenter@company.com
CLIENT_EMAIL=client@example.com

# template | llm | hybrid
NOTIFICATION_LLM_MODE=hybrid
```

- [ ] **Step 3: Commit skeleton**

```bash
git add modules/notifications/ tests/notifications/ .env.example
git commit -m "chore: add notifications package skeleton and env vars"
```

---

## Task 2: Message templates

**Files:**
- Create: `modules/notifications/templates/message_templates.py`
- Create: `tests/notifications/test_templates.py`

- [ ] **Step 1: Write failing tests**

Create `tests/notifications/test_templates.py`:
```python
from modules.notifications.templates.message_templates import (
    engineer_message,
    call_center_message,
    client_message_template,
)

PAYLOAD = {
    "issue": "Network Congestion",
    "severity": "high",
    "region": "Nasr City",
    "eta": 20,
    "action": "Reduce load and optimize routing",
    "root_cause": "traffic_spike",
}


def test_engineer_message_contains_required_fields():
    msg = engineer_message(PAYLOAD)
    assert "Network Congestion" in msg
    assert "Nasr City" in msg
    assert "high" in msg
    assert "20" in msg
    assert "Reduce load" in msg
    assert "traffic_spike" in msg


def test_call_center_message_contains_required_fields():
    msg = call_center_message(PAYLOAD)
    assert "Nasr City" in msg
    assert "Network Congestion" in msg
    assert "20" in msg


def test_client_message_template_contains_eta():
    msg = client_message_template(PAYLOAD)
    assert "20" in msg
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd .worktrees/rca-notification
pytest tests/notifications/test_templates.py -v
```
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement templates**

Create `modules/notifications/templates/message_templates.py`:
```python
def engineer_message(p: dict) -> str:
    return (
        f"ALERT: {p['issue']}\n"
        f"Region: {p['region']}\n"
        f"Severity: {p['severity']}\n"
        f"ETA: {p['eta']} min\n"
        f"Action: {p['action']}\n"
        f"Root Cause: {p['root_cause']}"
    )


def call_center_message(p: dict) -> str:
    return (
        f"Issue in {p['region']}\n"
        f"Type: {p['issue']}\n"
        f"ETA: {p['eta']} min"
    )


def client_message_template(p: dict) -> str:
    return (
        f"We are currently experiencing a temporary issue in {p['region']}. "
        f"Our team is working to resolve it within {p['eta']} minutes. "
        f"We apologize for any inconvenience."
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/notifications/test_templates.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add modules/notifications/templates/message_templates.py tests/notifications/test_templates.py
git commit -m "feat: add notification message templates"
```

---

## Task 3: Gmail SMTP sender

**Files:**
- Create: `modules/notifications/sender.py`
- Create: `tests/notifications/test_sender.py`

- [ ] **Step 1: Write failing tests**

Create `tests/notifications/test_sender.py`:
```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/notifications/test_sender.py -v
```
Expected: `ImportError` — sender module doesn't exist yet.

- [ ] **Step 3: Implement sender**

Create `modules/notifications/sender.py`:
```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/notifications/test_sender.py -v
```
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add modules/notifications/sender.py tests/notifications/test_sender.py
git commit -m "feat: add Gmail SMTP sender"
```

---

## Task 4: Routing + message generator

**Files:**
- Create: `modules/notifications/generator.py`
- Create: `tests/notifications/test_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/notifications/test_generator.py`:
```python
import os
from unittest.mock import patch, MagicMock
from modules.notifications.generator import generate_messages, get_recipients

PAYLOAD = {
    "issue": "Network Congestion",
    "severity": "high",
    "region": "Nasr City",
    "eta": 20,
    "action": "Reduce load",
    "root_cause": "traffic_spike",
}


def test_get_recipients_high():
    assert get_recipients("high") == ["engineer", "call_center", "client"]


def test_get_recipients_medium():
    assert get_recipients("medium") == ["call_center"]


def test_get_recipients_low():
    assert get_recipients("low") == []


def test_generate_messages_template_mode():
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "template"}):
        msgs = generate_messages(PAYLOAD, ["engineer", "call_center", "client"])
    assert "engineer" in msgs
    assert "call_center" in msgs
    assert "client" in msgs
    assert "traffic_spike" in msgs["engineer"]


def test_generate_messages_hybrid_client_differs():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "LLM-generated apology"
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "hybrid"}):
        with patch("modules.notifications.generator.get_llm", return_value=mock_llm):
            msgs = generate_messages(PAYLOAD, ["engineer", "call_center", "client"])
    assert msgs["client"] == "LLM-generated apology"
    assert "traffic_spike" in msgs["engineer"]


def test_generate_messages_hybrid_llm_failure_falls_back_to_template():
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("LLM unavailable")
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "hybrid"}):
        with patch("modules.notifications.generator.get_llm", return_value=mock_llm):
            msgs = generate_messages(PAYLOAD, ["client"])
    assert "20" in msgs["client"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/notifications/test_generator.py -v
```
Expected: `ImportError` — generator doesn't exist yet.

- [ ] **Step 3: Implement generator**

Create `modules/notifications/generator.py`:
```python
import os

from loguru import logger

from modules.notifications.templates.message_templates import (
    engineer_message,
    call_center_message,
    client_message_template,
)

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
    from modules.rag.chain.llm_provider import get_llm
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/notifications/test_generator.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add modules/notifications/generator.py tests/notifications/test_generator.py
git commit -m "feat: add routing logic and message generator"
```

---

## Task 5: FastAPI endpoint

**Files:**
- Create: `modules/notifications/api.py`
- Create: `tests/notifications/test_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/notifications/test_api.py`:
```python
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from modules.notifications.api import app

client = TestClient(app)

PAYLOAD = {
    "issue": "Network Congestion",
    "severity": "high",
    "region": "Nasr City",
    "eta": 20,
    "action": "Reduce load",
    "root_cause": "traffic_spike",
}


def test_send_notification_high_severity_success():
    with patch("modules.notifications.api.send_email", return_value=None):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "ENGINEER_EMAIL": "eng@test.com",
            "CALL_CENTER_EMAIL": "cc@test.com",
            "CLIENT_EMAIL": "client@test.com",
        }):
            resp = client.post("/notifications/send", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert set(data["recipients_notified"]) == {"engineer", "call_center", "client"}
    assert data["errors"] == []


def test_send_notification_medium_severity_only_call_center():
    payload = {**PAYLOAD, "severity": "medium"}
    with patch("modules.notifications.api.send_email", return_value=None):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "CALL_CENTER_EMAIL": "cc@test.com",
        }):
            resp = client.post("/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipients_notified"] == ["call_center"]


def test_send_notification_low_severity_no_recipients():
    payload = {**PAYLOAD, "severity": "low"}
    with patch("modules.notifications.api.send_email", return_value=None):
        resp = client.post("/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipients_notified"] == []
    assert data["status"] == "success"


def test_send_notification_partial_failure():
    def fake_send(to, subject, body):
        if "client" in to:
            return "connection refused"
        return None

    with patch("modules.notifications.api.send_email", side_effect=fake_send):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "ENGINEER_EMAIL": "eng@test.com",
            "CALL_CENTER_EMAIL": "cc@test.com",
            "CLIENT_EMAIL": "client@test.com",
        }):
            resp = client.post("/notifications/send", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "partial"
    assert len(data["errors"]) == 1


def test_send_notification_invalid_payload_422():
    resp = client.post("/notifications/send", json={"severity": "high"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/notifications/test_api.py -v
```
Expected: `ImportError` — api module doesn't exist yet.

- [ ] **Step 3: Implement API**

Create `modules/notifications/api.py`:
```python
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
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/notifications/ -v
```
Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add modules/notifications/api.py tests/notifications/test_api.py
git commit -m "feat: add FastAPI notification endpoint"
```

---

## Task 6: Run full test suite + push branch

- [ ] **Step 1: Run all notification tests**

```bash
pytest tests/notifications/ -v --tb=short
```
Expected: all PASSED, 0 failures.

- [ ] **Step 2: Push branch to remote**

```bash
git push -u origin feature/rca-notification
```

---

## Self-Review Checklist

- [x] **message_templates.py** — 3 functions (engineer, call_center, client template) ✓
- [x] **sender.py** — Gmail SMTP, returns None on success / error string on failure ✓
- [x] **generator.py** — `get_recipients()` + `generate_messages()`, all 3 modes (template/llm/hybrid), LLM fallback ✓
- [x] **api.py** — POST /notifications/send, Pydantic models, partial failure handling ✓
- [x] **env vars** — SMTP_SENDER, SMTP_APP_PASSWORD, ENGINEER_EMAIL, CALL_CENTER_EMAIL, CLIENT_EMAIL, NOTIFICATION_LLM_MODE ✓
- [x] **LLM reuse** — imports `get_llm()` from existing `modules/rag/chain/llm_provider` ✓
- [x] **Type consistency** — `generate_messages(payload: dict, recipients: list[str]) -> dict[str, str]` used consistently across generator + test ✓
- [x] **No placeholders** — all code blocks complete ✓
