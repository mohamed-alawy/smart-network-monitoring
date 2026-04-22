import os
from unittest.mock import patch, MagicMock
from modules.notifications.generator import generate_messages, get_recipients

LOCATION = "Nasr City"
RAG = {
    "cause_explanation": "DDoS attack.",
    "priority": "critical",
    "estimated_resolution_time": "2-4 hours",
    "suggested_solution": ["Step 1: Mitigate.", "Step 2: Block."],
    "affected_standards": ["TS 28.552"],
    "escalation_needed": True,
    "additional_notes": "Monitor continuously.",
}


def test_get_recipients_critical():
    assert get_recipients("critical") == ["engineer", "call_center", "client"]


def test_get_recipients_high():
    assert get_recipients("high") == ["engineer", "call_center", "client"]


def test_get_recipients_medium():
    assert get_recipients("medium") == ["call_center"]


def test_get_recipients_low():
    assert get_recipients("low") == []


def test_generate_messages_template_mode():
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "template"}):
        msgs = generate_messages(LOCATION, RAG, ["engineer", "call_center", "client"])
    assert "engineer" in msgs
    assert "call_center" in msgs
    assert "client" in msgs
    assert "DDoS" in msgs["engineer"]
    assert "Nasr City" in msgs["call_center"]


def test_generate_messages_hybrid_client_uses_llm():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "LLM-generated apology"
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "hybrid"}):
        with patch("modules.notifications.generator.get_llm", return_value=mock_llm):
            msgs = generate_messages(LOCATION, RAG, ["engineer", "call_center", "client"])
    assert msgs["client"] == "LLM-generated apology"
    assert "DDoS" in msgs["engineer"]


def test_generate_messages_hybrid_llm_failure_falls_back_to_template():
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("LLM unavailable")
    with patch.dict(os.environ, {"NOTIFICATION_LLM_MODE": "hybrid"}):
        with patch("modules.notifications.generator.get_llm", return_value=mock_llm):
            msgs = generate_messages(LOCATION, RAG, ["client"])
    assert "Nasr City" in msgs["client"]
    assert "2-4 hours" in msgs["client"]
