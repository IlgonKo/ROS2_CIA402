from collections.abc import Mapping


def normalize_response(message):
    if not isinstance(message, Mapping):
        return _malformed_response("Response must be a JSON object")

    message = dict(message)
    result = message.get("result")
    if result is None:
        return _normalize_legacy_response(message)
    if result == "success":
        return _normalize_success_response(message)
    if result == "fail":
        return _normalize_fail_response(message)
    return _malformed_response(
        "Response result must be success or fail",
        message.get("type", ""),
    )


def is_fail_response(message):
    normalized = normalize_response(message)
    return normalized.get("ok") is False


def _normalize_success_response(message):
    data = message.get("data")
    if not isinstance(data, Mapping):
        return _malformed_response(
            "Success response data must be an object",
            message.get("type", ""),
        )
    normalized = dict(data)
    normalized["type"] = str(message.get("type", ""))
    normalized["ok"] = True
    if "request_id" in message:
        normalized["request_id"] = message["request_id"]
    return _normalize_device_diagnostics(normalized)


def _normalize_fail_response(message):
    failure = message.get("failure")
    if not isinstance(failure, Mapping):
        return _malformed_response(
            "Fail response failure must be an object",
            message.get("type", ""),
        )
    failure = dict(failure)
    code = str(failure.get("code", "INTERNAL_FAILURE"))
    text = str(failure.get("message", "Motion Server request failed"))
    normalized = {
        "type": str(message.get("type", "")),
        "ok": False,
        "error": text,
        "message": text,
        "reason": code.lower(),
        "failure_code": code,
        "failure": failure,
    }
    details = failure.get("details")
    if isinstance(details, Mapping):
        for field in ("owner", "available", "axis", "io", "module", "slot", "port"):
            if field in details:
                normalized[field] = details[field]
    if "request_id" in message:
        normalized["request_id"] = message["request_id"]
    return normalized


def _normalize_legacy_response(message):
    normalized = dict(message)
    if normalized.get("type") == "command_rejected":
        normalized["ok"] = False
    if normalized.get("ok") is False:
        text = str(
            normalized.get(
                "message",
                normalized.get("error", "Motion Server request failed"),
            )
        )
        normalized.setdefault("message", text)
        normalized.setdefault("error", text)
        reason = str(normalized.get("reason", ""))
        if reason:
            normalized.setdefault("failure_code", reason.upper())
    return _normalize_device_diagnostics(normalized)


def _normalize_device_diagnostics(message):
    if "device_diagnostics" not in message and "diagnostics" in message:
        message["device_diagnostics"] = message["diagnostics"]
    return message


def _malformed_response(message, response_type=""):
    return {
        "type": str(response_type),
        "ok": False,
        "error": str(message),
        "message": str(message),
        "reason": "malformed_response",
        "failure_code": "MALFORMED_RESPONSE",
    }
