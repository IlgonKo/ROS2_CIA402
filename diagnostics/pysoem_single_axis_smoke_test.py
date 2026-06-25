import argparse
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ethercat.pysoem_master import PySOEMMaster


CYCLE_TIME = 0.01


def parse_args():
    parser = argparse.ArgumentParser(
        description="Single-axis PySOEM smoke test for a CiA402 slave."
    )
    parser.add_argument(
        "interface",
        help="EtherCAT NIC name, for example eth0 or enp1s0.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=0.0,
        help="Final target position used only with --move.",
    )
    parser.add_argument(
        "--max-velocity",
        type=float,
        default=1000.0,
    )
    parser.add_argument(
        "--acceleration",
        type=float,
        default=500.0,
    )
    parser.add_argument(
        "--deceleration",
        type=float,
        default=500.0,
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=500,
        help="Number of cyclic process-data exchanges.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Actually command motion to --target.",
    )
    parser.add_argument(
        "--relative",
        action="store_true",
        help="Treat --target as an offset from the current actual position.",
    )
    parser.add_argument(
        "--skip-sdo-mode",
        action="store_true",
        help="Do not write 0x6060 Modes of operation by SDO.",
    )
    return parser.parse_args()


def exchange(master, cycles=1):
    wkc = 0
    for _ in range(cycles):
        master.send_processdata()
        wkc = master.receive_processdata()
        time.sleep(CYCLE_TIME)
    return wkc


def print_feedback(prefix, master):
    slave = master.slaves[0]
    print(
        f"{prefix} "
        f"WKC={master.wkc}/{master.expected_wkc()} "
        f"SW=0x{slave.txpdo.statusword:04X} "
        f"SW_MASK=0x{slave.txpdo.statusword & 0x006F:04X} "
        f"MODE={slave.txpdo.mode_of_operation_display} "
        f"TP={slave.rxpdo.target_position:.3f} "
        f"AP={slave.txpdo.actual_position} "
        f"AV={slave.txpdo.actual_velocity}"
    )


def print_process_image(prefix, master):
    print(
        f"{prefix} "
        f"OUT={master.get_slave_output_bytes().hex()} "
        f"IN={master.get_slave_input_bytes().hex()}"
    )


def wait_status(master, expected_status, max_cycles=100):
    for _ in range(max_cycles):
        exchange(master, cycles=1)
        status = master.slaves[0].txpdo.statusword & 0x006F
        if status == expected_status:
            return True

    return False


def read_sdo_or_none(read_fn, *args):
    try:
        return read_fn(*args)
    except Exception as exc:
        return f"read failed: {exc}"


def print_diagnostics(prefix, master):
    statusword = read_sdo_or_none(master.sdo_read_uint16, 0, 0x6041, 0)
    error_code = read_sdo_or_none(master.sdo_read_uint16, 0, 0x603F, 0)
    error_register = read_sdo_or_none(master.sdo_read_uint8, 0, 0x1001, 0)
    mode_request = read_sdo_or_none(master.sdo_read_int8, 0, 0x6060, 0)
    mode_display = read_sdo_or_none(master.sdo_read_int8, 0, 0x6061, 0)

    print(
        f"{prefix} "
        f"SDO_SW={format_hex(statusword, 4)} "
        f"ERR={format_hex(error_code, 4)} "
        f"ERR_REG={format_hex(error_register, 2)} "
        f"MODE_REQ={mode_request} "
        f"MODE_DISP={mode_display}"
    )


def format_hex(value, width):
    if isinstance(value, int):
        return f"0x{value:0{width}X}"

    return str(value)


def fault_reset(master):
    master.set_controlword_all(0x0080)
    exchange(master, cycles=20)
    print_feedback("Fault reset:", master)
    print_diagnostics("Fault reset diag:", master)

    master.set_controlword_all(0x0000)
    exchange(master, cycles=10)
    print_feedback("After reset clear:", master)


def main():
    args = parse_args()

    motion_limits = [
        {
            "max_velocity": args.max_velocity,
            "acceleration": args.acceleration,
            "deceleration": args.deceleration,
        }
    ]

    master = PySOEMMaster(
        interface_name=args.interface,
        slave_count=1,
        cycle_time=CYCLE_TIME,
        motion_limits=motion_limits,
    )

    try:
        master.connect()
        master.set_mode_of_operation_all(8)

        if not args.skip_sdo_mode:
            master.sdo_write_int8(0, 0x6060, 0, 8)
            mode_display = master.sdo_read_int8(0, 0x6061, 0)
            print(f"Mode display after SDO 0x6060=8: {mode_display}")

        exchange(master, cycles=10)
        master.sync_trajectory_to_actual_positions()
        print_feedback("Connected:", master)
        print_diagnostics("Connected diag:", master)

        if master.slaves[0].txpdo.statusword & 0x0008:
            fault_reset(master)

        for label, controlword, expected_status in [
            ("Shutdown:", 0x0006, 0x0021),
            ("Switch on:", 0x0007, 0x0023),
            ("Enable op:", 0x000F, 0x0027),
        ]:
            master.set_controlword_all(controlword)
            reached = wait_status(master, expected_status)
            print_feedback(label, master)
            if not reached:
                print(
                    f"{label} expected SW_MASK=0x{expected_status:04X} "
                    "was not reached before timeout."
                )
            print_diagnostics(f"{label} diag:", master)
            exchange(master, cycles=2)
            print_feedback(f"{label} after diag PDO refresh:", master)
            print_process_image(f"{label} process image:", master)

        if args.move:
            target_position = args.target

            if args.relative:
                target_position += master.slaves[0].txpdo.actual_position

            print(f"Commanding target position: {target_position}")
            master.set_target_positions([target_position])
            for index in range(args.cycles):
                exchange(master, cycles=1)
                if index % 20 == 0:
                    print_feedback(f"Move {index:04d}:", master)

            print_feedback("Final:", master)
        else:
            print(
                "Motion command was not sent. "
                "Pass --move --target VALUE after PDO/state checks are safe."
            )

    finally:
        master.close()


if __name__ == "__main__":
    main()
