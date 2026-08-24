from configuration import (
    CliOverrides,
    ConfigurationSource,
    build_motion_server_config,
    load_configuration,
    set_active_configuration,
)
from device import available_device_names
from motion_server.diagnostic import DiagnosticManager


class MotionServerApplication:
    """Composition root for one immutable Motion Server configuration."""

    def __init__(self, config, list_adapters=False):
        self._config = config
        self._list_adapters = bool(list_adapters)

    @property
    def config(self):
        return self._config

    @classmethod
    def from_source(cls, source, argv=None, environ=None):
        if not isinstance(source, ConfigurationSource):
            raise TypeError("source must be a ConfigurationSource")
        raw_config = load_configuration(
            source.project_root,
            project_filename=source.project_filename,
            device_filename=source.device_filename,
            environ=environ,
            available_profiles=available_device_names(),
        )

        argv = list(argv or ())
        if argv:
            # Transitional CLI adapter through S03. The raw model is registered
            # before importing the legacy parser so files are not read twice.
            set_active_configuration(raw_config)
            from motion_server.config import parse_args

            parsed_args = parse_args(argv)
            typed_config = build_motion_server_config(
                raw_config,
                CliOverrides.from_namespace(parsed_args),
            )
            list_adapters = parsed_args.list_adapters
        else:
            typed_config = build_motion_server_config(raw_config)
            list_adapters = False
        return cls(typed_config, list_adapters=list_adapters)

    def run(self, runner=None):
        if runner is not None:
            return runner(
                config=self._config,
                diagnostic_manager=DiagnosticManager(),
            )

        # S03 replaces the Namespace adapter with typed projections. Runtime
        # reset/reconnect lifecycle already belongs to this composition root.
        from motion_server.server import (
            ServerResetRequested,
            ServerRestartRequested,
            restart_current_process,
            run_main_once,
            list_adapters,
        )

        if self._list_adapters:
            list_adapters()
            return

        diagnostic_manager = DiagnosticManager()
        while True:
            try:
                run_main_once(diagnostic_manager, config=self._config)
                return
            except ServerResetRequested:
                print(
                    "Motion Server runtime reinitialization requested; "
                    "reinitializing runtime and bus.",
                    flush=True,
                )
                continue
            except ServerRestartRequested:
                print(
                    "Motion Server restart requested; restarting process.",
                    flush=True,
                )
                restart_current_process()
