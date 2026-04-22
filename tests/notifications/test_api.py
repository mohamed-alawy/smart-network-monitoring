import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from modules.notifications.api import app

client = TestClient(app)

PAYLOAD = {
    "location": "Nasr City",
    "rag_output": {
        "cause_explanation": "DDoS attack overwhelming the network.",
        "priority": "critical",
        "estimated_resolution_time": "2-4 hours",
        "suggested_solution": ["Step 1: Activate mitigation.", "Step 2: Block sources."],
        "affected_standards": ["TS 28.552 Section 5.8"],
        "escalation_needed": True,
        "additional_notes": "Monitor N3IWF continuously.",
    },
}


def test_send_notification_critical_priority_success():
    with patch("modules.notifications.api.send_email", return_value=None):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "ENGINEER_EMAIL": "eng@test.com",
            "CALL_CENTER_EMAIL": "cc@test.com",
            "CLIENT_EMAIL": "support@test.com",
        }):
            resp = client.post("/notifications/send", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert set(data["recipients_notified"]) == {"engineer", "call_center", "client"}
    assert data["errors"] == []


def test_send_notification_medium_priority_only_call_center():
    payload = {**PAYLOAD, "rag_output": {**PAYLOAD["rag_output"], "priority": "medium"}}
    with patch("modules.notifications.api.send_email", return_value=None):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "CALL_CENTER_EMAIL": "cc@test.com",
        }):
            resp = client.post("/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipients_notified"] == ["call_center"]
    assert data["status"] == "success"


def test_send_notification_low_priority_no_recipients():
    payload = {**PAYLOAD, "rag_output": {**PAYLOAD["rag_output"], "priority": "low"}}
    with patch("modules.notifications.api.send_email", return_value=None):
        resp = client.post("/notifications/send", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["recipients_notified"] == []
    assert data["status"] == "success"


def test_send_notification_partial_failure():
    call_count = {"n": 0}

    def fake_send(to, subject, body):
        call_count["n"] += 1
        if call_count["n"] == 3:
            return "connection refused"
        return None

    with patch("modules.notifications.api.send_email", side_effect=fake_send):
        with patch.dict(os.environ, {
            "NOTIFICATION_LLM_MODE": "template",
            "ENGINEER_EMAIL": "eng@test.com",
            "CALL_CENTER_EMAIL": "cc@test.com",
            "CLIENT_EMAIL": "support@test.com",
        }):
            resp = client.post("/notifications/send", json=PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "partial"
    assert len(data["errors"]) == 1


def test_send_notification_invalid_payload_422():
    resp = client.post("/notifications/send", json={"location": "Cairo"})
    assert resp.status_code == 422
