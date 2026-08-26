def normalize_server_health(feedback):
    health = feedback.get("server_health", {})
    if not isinstance(health, dict):
        health = {}
    return {
        "initialized": bool(health.get("initialized", False)),
        "runtime_state": str(health.get("runtime_state", "unknown")),
        "diagnostic_level": str(health.get("diagnostic_level", "normal")),
        "fault_count": int(health.get("fault_count", 0) or 0),
        "alarm_count": int(health.get("alarm_count", 0) or 0),
        "representative_diagnostic": health.get("representative_diagnostic"),
        "initialization_failure": health.get("initialization_failure"),
        "process_data_valid": bool(feedback.get("process_data_valid", False)),
    }


def server_health_signature(feedback):
    health = normalize_server_health(feedback)
    representative = health["representative_diagnostic"] or {}
    failure = health["initialization_failure"] or {}
    return (
        health["initialized"],
        health["runtime_state"],
        health["diagnostic_level"],
        health["fault_count"],
        health["alarm_count"],
        representative.get("code"),
        failure.get("cause"),
        health["process_data_valid"],
    )


def format_server_health(feedback):
    health = normalize_server_health(feedback)
    state = health["runtime_state"].replace("_", " ")
    validity = "process data valid" if health["process_data_valid"] else "process data stale"
    text = (
        f"Server: {state} | initialized "
        f"{'yes' if health['initialized'] else 'no'} | "
        f"{health['diagnostic_level']} "
        f"(faults {health['fault_count']}, alarms {health['alarm_count']}) "
        f"| {validity}"
    )
    representative = health["representative_diagnostic"] or {}
    if representative:
        text += (
            f" | {representative.get('code', '')}: "
            f"{representative.get('title', '')}"
        )
    failure = health["initialization_failure"] or {}
    if failure:
        text += (
            f" | initialization {failure.get('stage', '')}/"
            f"{failure.get('cause', '')}: {failure.get('message', '')}"
        )
    return text
