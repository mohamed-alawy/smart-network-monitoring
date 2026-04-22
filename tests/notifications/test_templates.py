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
