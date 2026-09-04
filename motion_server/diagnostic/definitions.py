from motion_server.diagnostic.models import (
    DiagnosticDefinition,
    DiagnosticLevel,
    DiagnosticSource,
    DiagnosticSourceType,
)


SERVER_SOURCE = DiagnosticSource(DiagnosticSourceType.SERVER, 0)

SERVER_INITIALIZATION_FAILED = DiagnosticDefinition(
    code="SERVER_INITIALIZATION_FAILED",
    level=DiagnosticLevel.FAULT,
    title="Motion Server initialization failed",
    description=(
        "A required startup operation failed and Motion Server entered "
        "degraded mode."
    ),
    latching=True,
)

BUS_PROCESS_DATA_INCOMPLETE = DiagnosticDefinition(
    code="BUS_PROCESS_DATA_INCOMPLETE",
    level=DiagnosticLevel.FAULT,
    title="EtherCAT process data is incomplete",
    description=(
        "The EtherCAT working counter remained below its expected value."
    ),
    latching=True,
)

BUS_CONNECTION_LOST = DiagnosticDefinition(
    code="BUS_CONNECTION_LOST",
    level=DiagnosticLevel.FAULT,
    title="EtherCAT connection lost",
    description="Cyclic EtherCAT transport communication was interrupted.",
    latching=True,
)

BUS_RECONNECT_FAILED = DiagnosticDefinition(
    code="BUS_RECONNECT_FAILED",
    level=DiagnosticLevel.FAULT,
    title="EtherCAT reconnect failed",
    description="The EtherCAT transport could not complete reconnection.",
    latching=True,
)

AXIS_DRIVE_FAULT = DiagnosticDefinition(
    code="AXIS_DRIVE_FAULT",
    level=DiagnosticLevel.FAULT,
    title="Axis drive fault",
    description="The axis statusword reports the CiA 402 fault bit.",
    latching=True,
)

AXIS_RESTART_FAILED = DiagnosticDefinition(
    code="AXIS_RESTART_FAILED",
    level=DiagnosticLevel.FAULT,
    title="Axis restart failed",
    description=(
        "The Axis device did not complete restart and process image recovery."
    ),
    latching=True,
)

PARAMETER_REFRESH_FAILED = DiagnosticDefinition(
    code="PARAMETER_REFRESH_FAILED",
    level=DiagnosticLevel.FAULT,
    title="Runtime parameter refresh failed",
    description=(
        "Motion Server could not refresh required runtime parameter cache "
        "values from the device."
    ),
    latching=True,
)

AXIS_DRIVE_WARNING = DiagnosticDefinition(
    code="AXIS_DRIVE_WARNING",
    level=DiagnosticLevel.ALARM,
    title="Axis drive warning",
    description="The axis statusword reports the CiA 402 warning bit.",
    latching=False,
)
