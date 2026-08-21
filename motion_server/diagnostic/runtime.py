from motion_server.diagnostic.definitions import (
    AXIS_DRIVE_FAULT,
    AXIS_DRIVE_WARNING,
    BUS_PROCESS_DATA_INCOMPLETE,
)
from motion_server.diagnostic.models import (
    DiagnosticSource,
    DiagnosticSourceType,
)


BUS_WKC_MISMATCH_DETECTION_CYCLES = 3
BUS_SOURCE = DiagnosticSource(DiagnosticSourceType.BUS, 0)
CIA402_FAULT_BIT = 1 << 3
CIA402_WARNING_BIT = 1 << 7


class RuntimeDiagnosticMonitor:
    def __init__(
        self,
        diagnostic_manager,
        *,
        bus_wkc_mismatch_detection_cycles=BUS_WKC_MISMATCH_DETECTION_CYCLES,
    ):
        threshold = int(bus_wkc_mismatch_detection_cycles)
        if threshold < 1:
            raise ValueError("Bus WKC mismatch detection cycles must be positive")
        self.diagnostic_manager = diagnostic_manager
        self.bus_wkc_mismatch_detection_cycles = threshold
        self._bus_wkc_mismatch_cycles = 0

    def update(self, runtime, *, at=None):
        self._update_bus(runtime, at=at)
        self._update_axes(runtime, at=at)

    def _update_bus(self, runtime, *, at=None):
        expected_wkc = int(runtime.expected_wkc())
        actual_wkc = int(runtime.wkc)
        if expected_wkc > 0 and actual_wkc != expected_wkc:
            self._bus_wkc_mismatch_cycles += 1
            if (
                self._bus_wkc_mismatch_cycles
                >= self.bus_wkc_mismatch_detection_cycles
            ):
                self.diagnostic_manager.detect(
                    BUS_PROCESS_DATA_INCOMPLETE,
                    BUS_SOURCE,
                    at=at,
                )
            return

        self._bus_wkc_mismatch_cycles = 0
        self._resolve_if_active(
            BUS_PROCESS_DATA_INCOMPLETE.code,
            BUS_SOURCE,
            at=at,
        )

    def _update_axes(self, runtime, *, at=None):
        for axis_index, slave in enumerate(runtime.slaves):
            statusword = int(slave.txpdo.statusword)
            source = DiagnosticSource(DiagnosticSourceType.AXIS, axis_index)
            self._update_condition(
                bool(statusword & CIA402_FAULT_BIT),
                AXIS_DRIVE_FAULT,
                source,
                at=at,
            )
            self._update_condition(
                bool(statusword & CIA402_WARNING_BIT),
                AXIS_DRIVE_WARNING,
                source,
                at=at,
            )

    def _update_condition(self, active, definition, source, *, at=None):
        if active:
            return self.diagnostic_manager.detect(definition, source, at=at)
        return self._resolve_if_active(definition.code, source, at=at)

    def _resolve_if_active(self, code, source, *, at=None):
        if self.diagnostic_manager.status_for(code, source) is None:
            return None
        return self.diagnostic_manager.resolve(code, source, at=at)
