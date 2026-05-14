def engineer_message(location: str, rag: dict) -> str:
    steps = "\n".join(f"  {s}" for s in rag.get("suggested_solution", []))
    standards = ", ".join(rag.get("affected_standards", []))
    return (
        f"ALERT - {location}\n"
        f"Priority: {rag['priority']}\n"
        f"Cause: {rag['cause_explanation']}\n"
        f"ETA: {rag['estimated_resolution_time']}\n"
        f"Escalation needed: {rag['escalation_needed']}\n"
        f"\nSuggested Steps:\n{steps}\n"
        f"\nStandards: {standards}\n"
        f"Notes: {rag.get('additional_notes', '')}"
    )


def call_center_message(location: str, rag: dict) -> str:
    return (
        f"Network issue in {location}\n"
        f"Priority: {rag['priority']}\n"
        f"Expected resolution: {rag['estimated_resolution_time']}"
    )


def client_message_template(location: str, rag: dict) -> str:
    return (
        f"We are experiencing a temporary service disruption in {location}. "
        f"Our team expects to resolve it within {rag['estimated_resolution_time']}. "
        f"We apologize for the inconvenience."
    )
