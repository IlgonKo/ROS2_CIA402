from collections.abc import Mapping


NOTIFICATION_TYPES = frozenset({"system/feedback", "log"})


def decode_server_message(message):
    if not isinstance(message, Mapping):
        return _malformed_response("Response must be a JSON object")
    message = dict(message)
    if "result" not in message:
        if message.get("type") in NOTIFICATION_TYPES:
            return message
        return _malformed_response("Request response requires result", message.get("type", ""))
    if message.get("result") == "success":
        return _decode_success(message)
    if message.get("result") == "fail":
        return _decode_fail(message)
    return _malformed_response("Response result must be success or fail", message.get("type", ""))


def is_fail_message(message):
    return isinstance(message, Mapping) and message.get("ok") is False


def _decode_success(message):
    data = message.get("data")
    if not isinstance(data, Mapping):
        return _malformed_response("Success response data must be an object", message.get("type", ""))
    decoded = dict(data)
    decoded["type"] = str(message.get("type", ""))
    decoded["ok"] = True
    if "request_id" in message:
        decoded["request_id"] = message["request_id"]
    return decoded


def _decode_fail(message):
    failure = message.get("failure")
    if not isinstance(failure, Mapping):
        return _malformed_response("Fail response failure must be an object", message.get("type", ""))
    failure = dict(failure)
    code = str(failure.get("code", "INTERNAL_FAILURE"))
    text = str(failure.get("message", "Motion Server request failed"))
    decoded = {
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
                decoded[field] = details[field]
    if "request_id" in message:
        decoded["request_id"] = message["request_id"]
    return decoded


def _malformed_response(message, response_type=""):
    return {
        "type": str(response_type),
        "ok": False,
        "error": str(message),
        "message": str(message),
        "reason": "malformed_response",
        "failure_code": "MALFORMED_RESPONSE",
    }
