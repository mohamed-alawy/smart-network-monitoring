from modules.notifications.templates.message_templates import (
    engineer_message,
    call_center_message,
    client_message_template,
)

LOCATION = "Nasr City"
RAG = {
    "cause_explanation": "DDoS attack overwhelming the network.",
    "priority": "critical",
    "estimated_resolution_time": "2-4 hours",
    "suggested_solution": ["Step 1: Activate DDoS mitigation.", "Step 2: Block sources."],
    "affected_standards": ["TS 28.552 Section 5.8"],
    "escalation_needed": True,
    "additional_notes": "Monitor N3IWF continuously.",
}


def test_engineer_message_contains_required_fields():
    msg = engineer_message(LOCATION, RAG)
    assert "Nasr City" in msg
    assert "critical" in msg
    assert "DDoS attack" in msg
    assert "2-4 hours" in msg
    assert "Step 1" in msg
    assert "TS 28.552" in msg
    assert "True" in msg or "true" in msg.lower()


def test_call_center_message_contains_required_fields():
    msg = call_center_message(LOCATION, RAG)
    assert "Nasr City" in msg
    assert "critical" in msg
    assert "2-4 hours" in msg


def test_client_message_template_contains_location_and_eta():
    msg = client_message_template(LOCATION, RAG)
    assert "Nasr City" in msg
    assert "2-4 hours" in msg
