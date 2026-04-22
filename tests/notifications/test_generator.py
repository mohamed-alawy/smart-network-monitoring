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
