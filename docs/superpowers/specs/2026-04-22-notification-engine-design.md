# Notification Engine — Design Spec

Date: 2026-04-22  
Branch: feature/rca-notification  
Module: modules/notifications/

---

## Overview

A standalone FastAPI module that receives RAG/RCA output, routes it to the correct recipients based on severity, generates human-readable messages (via templates or LLM), and delivers them via Gmail SMTP.

---

## Architecture

```
POST /notifications/send
        │
        ▼
 NotificationRequest (Pydantic)
   issue, severity, region, eta, action, root_cause
        │
        ▼
 notification_engine()
   ├── routing logic  → who gets notified based on severity
   ├── generator.py   → message content (template | llm | hybrid)
   └── sender.py      → Gmail SMTP delivery
        │
        ▼
 NotificationResponse
   recipients_notified[], status, errors[]
```

---

## File Structure

```
modules/notifications/
├── __init__.py
├── templates/
│   └── message_templates.py   ← f-string templates for engineer, call_center, client
├── generator.py               ← routing + message generation
├── sender.py                  ← Gmail SMTP
└── api.py                     ← FastAPI POST /notifications/send
```

---

## Routing Logic

| Severity | Recipients                          |
|----------|-------------------------------------|
| `high`   | engineer + call_center + client     |
| `medium` | call_center                         |
| `low`    | (none)                              |

---

## LLM Mode (env flag)

```
NOTIFICATION_LLM_MODE=hybrid   # template | llm | hybrid
```

| Mode       | Engineer msg | Call center msg | Client msg |
|------------|-------------|-----------------|------------|
| `template` | f-string    | f-string        | f-string   |
| `llm`      | LLM         | LLM             | LLM        |
| `hybrid`   | f-string    | f-string        | LLM        |

LLM reuses `modules/rag/chain/llm_provider.get_llm()` — no new provider setup needed.

---

## API Contract

**Endpoint:** `POST /notifications/send`

**Request body:**
```json
{
  "issue": "Network Congestion",
  "severity": "high",
  "region": "Nasr City",
  "eta": 20,
  "action": "Reduce load and optimize routing",
  "root_cause": "traffic_spike"
}
```

**Response:**
```json
{
  "recipients_notified": ["engineer", "call_center", "client"],
  "status": "success",
  "errors": []
}
```

**Error response (partial failure):**
```json
{
  "recipients_notified": ["engineer", "call_center"],
  "status": "partial",
  "errors": ["client email delivery failed: <reason>"]
}
```

---

## Message Templates

### Engineer (high severity only)
```
ALERT: {issue}
Region: {region}
Severity: {severity}
ETA: {eta} min
Action: {action}
Root Cause: {root_cause}
```

### Call Center (high + medium)
```
Issue in {region}
Type: {issue}
ETA: {eta} min
```

### Client (high severity only)
- **template mode:** "Temporary issue in your area. Will be resolved within {eta} minutes."
- **hybrid/llm mode:** LLM generates a polite, non-technical apology using issue + region + eta

---

## Email Configuration (.env additions)

```
# Gmail SMTP
SMTP_SENDER=your@gmail.com
SMTP_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Recipient addresses
ENGINEER_EMAIL=engineer@company.com
CALL_CENTER_EMAIL=callcenter@company.com
CLIENT_EMAIL=client@example.com

# Notification mode
NOTIFICATION_LLM_MODE=hybrid   # template | llm | hybrid
```

---

## Error Handling

- SMTP failure for one recipient → log error, continue sending to others, report in `errors[]`
- LLM generation failure in hybrid/llm mode → fall back to template, log warning
- Invalid severity value → 422 Unprocessable Entity from Pydantic validation
- Missing required fields → 422 from Pydantic

---

## Integration Point

This module is called by the pipeline orchestrator (`pipeline/orchestrator.py`) after RAG/RCA produces output. It can also be called directly via HTTP for testing.

```python
# orchestrator calls it like:
import httpx
httpx.post("http://localhost:8001/notifications/send", json=rag_output)
```

---

## Out of Scope

- Twilio SMS (deferred — Gmail SMTP only for now)
- MLflow tracking (orchestrator's responsibility)
- Authentication on the endpoint (internal service, no auth needed)
