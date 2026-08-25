from datetime import datetime, timezone

from configuration import (
    ConfigurationSource,
    build_bootstrap_server_config,
    build_motion_server_config,
    load_configuration,
    load_configuration_snapshot,
    parse_cli_overrides,
)
from device import available_device_names
from motion_server.app.initialization import (
    InitializationStage,
    InitializationStatus,
    initialization_failure_from_exception,
    log_initialization_failure,
)
from motion_server.diagnostic import DiagnosticManager
from motion_server.diagnostic.startup import detect_initialization_fault
from motion_server.app.session import ServerSession


class MotionServerApplication:
    """Composition root for one immutable Motion Server configuration."""

    def __init__(
        self,
        bootstrap_config,
        config=None,
        initialization_status=None,
        initialization_exception=None,
        list_adapters=False,
    ):
        self._bootstrap_config = bootstrap_config
        self._config = config
        self._initialization_status = (
            initialization_status or InitializationStatus.ready()
        )
        self._initialization_exception = initialization_exception
        self._list_adapters = bool(list_adapters)

    @property
    def config(self):
        return self._config

    @property
    def bootstrap_config(self):
        return self._bootstrap_config

    @property
    def initialization_status(self):
        return self._initialization_status

    @property
    def initialization_exception(self):
        return self._initialization_exception

    @classmethod
    def from_source(cls, source, argv=None, environ=None):
        if not isinstance(source, ConfigurationSource):
            raise TypeError("source must be a ConfigurationSource")
        argv = list(argv or ())
        if argv:
            cli_overrides, list_adapters = parse_cli_overrides(argv)
        else:
            cli_overrides, list_adapters = parse_cli_overrides([])

        snapshot = load_configuration_snapshot(
            source.project_root,
            project_filename=source.project_filename,
            device_filename=source.device_filename,
            environ=environ,
        )
        bootstrap_config = build_bootstrap_server_config(
            snapshot,
            cli_overrides,
        )

        try:
            raw_config = load_configuration(
                available_profiles=available_device_names(),
                snapshot=snapshot,
                bus_override=cli_overrides.bus,
            )
            typed_config = build_motion_server_config(
                raw_config,
                cli_overrides,
                bootstrap=bootstrap_config,
            )
        except Exception as exc:
            failure = initialization_failure_from_exception(
                InitializationStage.CONFIGURATION,
                exc,
                occurred_at=datetime.now(timezone.utc),
            )
            return cls(
                bootstrap_config,
                initialization_status=InitializationStatus.failed(failure),
                initialization_exception=exc,
                list_adapters=list_adapters,
            )
        return cls(
            bootstrap_config,
            typed_config,
            initialization_status=InitializationStatus.ready(),
            list_adapters=list_adapters,
        )

    def run(self, runner=None):
        if self._config is None:
            if runner is not None:
                return runner(
                    bootstrap_config=self._bootstrap_config,
                    initialization_status=self._initialization_status,
                    diagnostic_manager=DiagnosticManager(),
                )
            from motion_server.server import (
                ServerRestartRequested,
                restart_current_process,
                run_configuration_degraded_once,
            )

            session = ServerSession(self._initialization_status)
            log_initialization_failure(
                self._initialization_status.failure,
                self._initialization_exception,
            )
            detect_initialization_fault(
                session,
                at=self._initialization_status.failure.occurred_at,
            )
            while True:
                try:
                    run_configuration_degraded_once(
                        session,
                        self._bootstrap_config,
                    )
                    return
                except ServerRestartRequested:
                    restart_current_process()

        dependencies = {
            "server_config": self._config.server,
            "ethercat_config": self._config.ethercat,
            "motion_config": self._config.motion,
            "logging_config": self._config.logging,
            "devices": self._config.devices,
        }
        if runner is not None:
            return runner(
                diagnostic_manager=DiagnosticManager(),
                **dependencies,
            )

        # S03 replaces the Namespace adapter with typed projections. Runtime
        # reset/reconnect lifecycle already belongs to this composition root.
        from motion_server.server import (
            BusReconnectRequested,
            ServerResetRequested,
            ServerRestartRequested,
            restart_current_process,
            run_main_once,
            list_adapters,
        )

        if self._list_adapters:
            list_adapters()
            return

        session = ServerSession(
            InitializationStatus.ready(),
            diagnostic_manager=DiagnosticManager(),
        )
        while True:
            try:
                run_main_once(session, **dependencies)
                return
            except ServerResetRequested:
                print(
                    "Motion Server runtime reinitialization requested; "
                    "reinitializing runtime and bus.",
                    flush=True,
                )
                session = ServerSession(InitializationStatus.ready())
                continue
            except BusReconnectRequested:
                print(
                    "Motion Server bus reconnect requested; "
                    "reinitializing runtime with the current Diagnostic state.",
                    flush=True,
                )
                continue
            except ServerRestartRequested:
                print(
                    "Motion Server restart requested; restarting process.",
                    flush=True,
                )
                restart_current_process()
