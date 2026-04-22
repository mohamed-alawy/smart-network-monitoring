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
