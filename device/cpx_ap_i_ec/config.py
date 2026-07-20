import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CPXIoConfig:
    digital_inputs: int = 0
    analog_inputs: int = 0
    digital_outputs: int = 0
    analog_outputs: int = 0
    analog_bits: int = 16
    analog_signed: bool = True

    @property
    def analog_bytes(self):
        return self.analog_bits // 8

    @property
    def input_digital_bytes(self):
        return bytes_for_bits(self.digital_inputs)

    @property
    def output_digital_bytes(self):
        return bytes_for_bits(self.digital_outputs)

    @property
    def input_bytes(self):
        return self.input_digital_bytes + self.analog_inputs * self.analog_bytes

    @property
    def output_bytes(self):
        return self.output_digital_bytes + self.analog_outputs * self.analog_bytes


def bytes_for_bits(bit_count):
    return (max(0, int(bit_count)) + 7) // 8


def load_cpx_config():
    project_root = Path(__file__).resolve().parents[2]
    env_file = os.environ.get(
        "CPX_AP_I_EC_ENV_FILE",
        "device/cpx_ap_i_ec/.env",
    )
    env_path = Path(env_file)
    if not env_path.is_absolute():
        env_path = project_root / env_path

    values = read_env_file(env_path)
    values.update({
        key: value
        for key, value in os.environ.items()
        if key.startswith("CPX_")
    })

    config = CPXIoConfig(
        digital_inputs=env_int(values, "CPX_DIGITAL_INPUTS", 0),
        analog_inputs=env_int(values, "CPX_ANALOG_INPUTS", 0),
        digital_outputs=env_int(values, "CPX_DIGITAL_OUTPUTS", 0),
        analog_outputs=env_int(values, "CPX_ANALOG_OUTPUTS", 0),
        analog_bits=env_int(values, "CPX_ANALOG_BITS", 16),
        analog_signed=env_bool(values, "CPX_ANALOG_SIGNED", True),
    )
    validate_config(config, env_path)
    return config


def read_env_file(path):
    values = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_int(values, key, default):
    value = values.get(key, "")
    if value == "":
        return int(default)
    return int(value, 0)


def env_bool(values, key, default):
    value = values.get(key, "")
    if value == "":
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def validate_config(config, env_path):
    counts = {
        "CPX_DIGITAL_INPUTS": config.digital_inputs,
        "CPX_ANALOG_INPUTS": config.analog_inputs,
        "CPX_DIGITAL_OUTPUTS": config.digital_outputs,
        "CPX_ANALOG_OUTPUTS": config.analog_outputs,
    }
    negative = [key for key, value in counts.items() if value < 0]
    if negative:
        raise ValueError(
            f"Negative CPX I/O counts in {env_path}: {', '.join(negative)}"
        )
    if config.analog_bits not in (8, 16, 32):
        raise ValueError(
            f"Unsupported CPX_ANALOG_BITS={config.analog_bits}; "
            "expected 8, 16, or 32"
        )
