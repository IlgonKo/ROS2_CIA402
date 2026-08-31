"""Temporary, explicitly armed, read-only probe using the server's live Master.

No public API, gateway command write, or additional EtherCAT connection is added.
Remove the startup hook after the requested investigation is complete.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from motion_server.failure import MotionServerException


REQUEST_PATH = Path(__file__).resolve().parents[2] / ".runtime/iol-gateway-probe.request"
RESULT_PATH = REQUEST_PATH.with_name("iol-gateway-probe-result.json")
TARGETS = ((0x2001, 2), (0x2021, 2))


def original_abort_code(exception):
    seen = set()
    while exception is not None and id(exception) not in seen:
        seen.add(id(exception))
        code = getattr(exception, "abort_code", None)
        if code is not None:
            return f"0x{int(code):08X}"
        exception = exception.__cause__
    return None


def probe(runtime):
    slave_index = runtime.device_manager.io.slave_index("io0")
    results = []
    for index, subindex in TARGETS:
        item = {"io": "io0", "slave_index": slave_index,
                "index": f"0x{index:04X}", "subindex": subindex, "operation": "read_uint8"}
        try:
            raw = bytes(runtime.ethercat_master.read_sdo(slave_index, index, subindex, 1))
        except (MotionServerException, RuntimeError, OSError) as exception:
            item.update(result="fail", exception=type(exception).__name__,
                        message=str(exception), abort_code=original_abort_code(exception))
        else:
            if len(raw) == 1:
                item.update(result="success", value=raw[0], raw=raw.hex())
            else:
                item.update(result="invalid_length", length=len(raw), raw=raw.hex())
        results.append(item)
    return {"occurred_at": datetime.now(timezone.utc).isoformat(), "reads": results}


def run_pending_probe(runtime, *, request_path=REQUEST_PATH, result_path=RESULT_PATH):
    if not request_path.is_file():
        return
    try:
        # Consume before attempting I/O: ordinary restarts never repeat this probe.
        request_path.unlink()
        result = probe(runtime)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("IO-Link read-only gateway probe: " + json.dumps(result, ensure_ascii=False), flush=True)
    except (MotionServerException, RuntimeError, OSError, ValueError) as exception:
        print(f"IO-Link gateway probe could not complete: {exception}", flush=True)
