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
