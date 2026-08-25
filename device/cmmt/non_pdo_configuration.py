from dataclasses import dataclass


@dataclass(frozen=True)
class NonPdoOdValue:
    index: int
    subindex: int
    value: int | float | str


@dataclass(frozen=True)
class NonPdoConfiguration:
    name: str
    values: tuple[NonPdoOdValue, ...]


def od(index, subindex, value):
    return NonPdoOdValue(index, subindex, value)


CMMT_NON_PDO_CONFIGURATIONS = {
    "linear_mm": NonPdoConfiguration(
        "linear_mm",
        (
            od(0x216E, 0x01, 0x0100),
            od(0x2194, 0x01, 6), od(0x2194, 0x02, 3),
            od(0x2194, 0x03, 3), od(0x2194, 0x04, 3),
            od(0x607D, 0x01, -1000000), od(0x607D, 0x02, 1000000),
            od(0x6067, 0x00, 20), od(0x6068, 0x00, 20),
            od(0x607F, 0x00, 200), od(0x2183, 0x0C, -0.2),
            od(0x6083, 0x00, 1000),
            od(0x6084, 0x00, 1000), od(0x6098, 0x00, 37),
            od(0x6099, 0x01, 100), od(0x6099, 0x02, 50),
            od(0x609A, 0x00, 100), od(0x60C5, 0x00, 2000),
            od(0x60C6, 0x00, 2000), od(0x60A4, 0x01, 100000),
        ),
    ),
    "rotary_deg": NonPdoConfiguration(
        "rotary_deg",
        (
            od(0x216E, 0x01, 0x4100),
            od(0x2194, 0x01, 6), od(0x2194, 0x02, 3),
            od(0x2194, 0x03, 3), od(0x2194, 0x04, 3),
            od(0x607D, 0x01, -180000000), od(0x607D, 0x02, 180000000),
            od(0x6067, 0x00, 20000), od(0x6068, 0x00, 20),
            od(0x607F, 0x00, 200000), od(0x2183, 0x0C, -200.0),
            od(0x6083, 0x00, 1000000),
            od(0x6084, 0x00, 1000000), od(0x6098, 0x00, 37),
            od(0x6099, 0x01, 100000), od(0x6099, 0x02, 50000),
            od(0x609A, 0x00, 100000), od(0x60C5, 0x00, 2000000),
            od(0x60C6, 0x00, 2000000), od(0x60A4, 0x01, 100000000),
        ),
    ),
}


def non_pdo_configuration_names():
    return tuple(sorted(CMMT_NON_PDO_CONFIGURATIONS))


def get_non_pdo_configuration(name):
    normalized = str(name or "").strip().lower().replace("-", "_")
    try:
        return CMMT_NON_PDO_CONFIGURATIONS[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported CMMT Non-PDO configuration: {name!r}. "
            f"Supported: {', '.join(non_pdo_configuration_names())}"
        ) from exc
