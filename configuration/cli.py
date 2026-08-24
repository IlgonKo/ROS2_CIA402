import argparse

from configuration.builder import CliOverrides
from configuration.models import (
    BackendType,
    CspInterpolationMode,
    CspProfile,
    ServerMode,
)


def parse_cli_overrides(argv=None):
    parser = argparse.ArgumentParser(
        description="TCP JSON-lines Motion Server for CiA402 axes."
    )
    parser.add_argument("interface", nargs="?", default=None)
    parser.add_argument("--list-adapters", action="store_true")
    parser.add_argument("--backend", choices=[item.value for item in BackendType])
    parser.add_argument("--bus")
    parser.add_argument("--server-mode", choices=[item.value for item in ServerMode])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--cycle-time", type=float)
    parser.add_argument("--spin-wait-time", type=float)
    parser.add_argument("--sync-mode")
    parser.add_argument("--dc-enabled", action="store_const", const=True, default=None)
    parser.add_argument("--dc-sync0-shift-time", type=int)
    parser.add_argument("--dc-phase-lock", action="store_const", const=True, default=None)
    parser.add_argument("--dc-absolute-shift", action="store_const", const=True, default=None)
    parser.add_argument("--dc-phase-offset", type=int)
    parser.add_argument("--dc-phase-kp", type=float)
    parser.add_argument("--dc-phase-ki", type=float)
    parser.add_argument("--dc-phase-max-correction", type=float)
    parser.add_argument("--max-velocity", type=float)
    parser.add_argument("--acceleration", type=float)
    parser.add_argument("--deceleration", type=float)
    parser.add_argument("--jerk", type=float)
    parser.add_argument("--pp-jerk", type=int)
    parser.add_argument("--motion-mode", choices=("pp", "pv", "jog", "csp"))
    parser.add_argument("--csp-profile", choices=[item.value for item in CspProfile])
    parser.add_argument(
        "--csp-interpolation-mode",
        type=int,
        choices=[item.value for item in CspInterpolationMode],
    )
    parser.add_argument(
        "--csp-velocity-offset",
        action="store_const",
        const=True,
        default=None,
    )
    parser.add_argument("--csp-command-step-threshold", type=float)
    parser.add_argument("--csp-command-step-error-threshold", type=float)
    args = parser.parse_args(argv)
    overrides = CliOverrides(
        host=args.host,
        port=args.port,
        backend=None if args.backend is None else BackendType(args.backend),
        interface=args.interface,
        bus=args.bus,
        server_mode=None if args.server_mode is None else ServerMode(args.server_mode),
        cycle_time=args.cycle_time,
        spin_wait_time=args.spin_wait_time,
        sync_mode=(
            None
            if args.sync_mode is None or not str(args.sync_mode).strip()
            else int(args.sync_mode, 0)
        ),
        dc_enabled=args.dc_enabled,
        dc_sync0_shift_time_ns=args.dc_sync0_shift_time,
        dc_phase_lock=args.dc_phase_lock,
        dc_absolute_shift=args.dc_absolute_shift,
        dc_phase_offset_ns=args.dc_phase_offset,
        dc_phase_kp=args.dc_phase_kp,
        dc_phase_ki=args.dc_phase_ki,
        dc_phase_max_correction=args.dc_phase_max_correction,
        max_velocity=args.max_velocity,
        acceleration=args.acceleration,
        deceleration=args.deceleration,
        jerk=args.jerk,
        pp_jerk=args.pp_jerk,
        motion_mode=args.motion_mode,
        csp_profile=None if args.csp_profile is None else CspProfile(args.csp_profile),
        csp_interpolation_mode=(
            None
            if args.csp_interpolation_mode is None
            else CspInterpolationMode(args.csp_interpolation_mode)
        ),
        csp_velocity_offset=args.csp_velocity_offset,
        csp_command_step_threshold=args.csp_command_step_threshold,
        csp_command_step_error_threshold=args.csp_command_step_error_threshold,
    )
    return overrides, args.list_adapters
