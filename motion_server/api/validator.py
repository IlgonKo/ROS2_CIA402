INT32_MIN = -(2 ** 31)
INT32_MAX = 2 ** 31 - 1
UINT32_MAX = 2 ** 32 - 1


def parse_int(value, base=0):
    if isinstance(value, int):
        return value
    return int(str(value), base)


def require_int32(value, field_name):
    result = int(round(float(value)))
    if result < INT32_MIN or result > INT32_MAX:
        raise ValueError(
            f"{field_name}={result} is outside int32 PDO range "
            f"[{INT32_MIN}, {INT32_MAX}]"
        )
    return result


def require_uint32(value, field_name):
    result = int(round(float(value)))
    if result < 0 or result > UINT32_MAX:
        raise ValueError(
            f"{field_name}={result} is outside uint32 PDO range "
            f"[0, {UINT32_MAX}]"
        )
    return result


def is_advanced_mode(state):
    return state.get("server_mode") == "advanced"


def command_allowed_by_mode(spec, state):
    return not spec.advanced_only or is_advanced_mode(state)


def command_allowed_during_initialization_error(spec, state):
    return (
        state.get("drive_initialized", True)
        or not spec.is_command
        or spec.initialization_error_allowed
    )


def command_requires_authority(spec):
    return spec.is_command and spec.authority_required


def validate_command(spec, client, state, has_authority):
    if spec is None:
        return "unknown"
    if not command_allowed_by_mode(spec, state):
        return "advanced_only"
    if command_requires_authority(spec) and not has_authority:
        return "authority_required"
    if not command_allowed_during_initialization_error(spec, state):
        return "not_initialized"
    return None
