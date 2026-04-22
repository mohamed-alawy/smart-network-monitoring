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
