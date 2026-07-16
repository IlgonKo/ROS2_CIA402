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
