#!/usr/bin/env python3
import argparse
import os
import struct
import time

import pysoem


DEFAULT_INTERFACE = os.environ.get("PYSOEM_INTERFACE", "enp1s0")
DEFAULT_AXIS_COUNT = int(os.environ.get("PYSOEM_AXIS_COUNT", "1"))
DEFAULT_CYCLE_TIME = float(os.environ.get("PYSOEM_CYCLE_TIME", "0.001"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Probe and optionally write CMMT EtherCAT sync parameters."
    )
    parser.add_argument("--interface", default=DEFAULT_INTERFACE)
    parser.add_argument("--axis-count", type=int, default=DEFAULT_AXIS_COUNT)
    parser.add_argument("--cycle-time", type=float, default=DEFAULT_CYCLE_TIME)
    parser.add_argument(
        "--sync-mode",
        type=int,
        default=2,
        help="0=FreeRun, 1=Sync with process data, 2=DC Sync0.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write vendor sync objects 0x212E:01, 0x212E:02, and 0x212E:09.",
    )
    parser.add_argument(
        "--also-write-1c32",
        action="store_true",
        help="Also try direct CiA301 writes to 0x1C32/0x1C33 for comparison.",
    )
    parser.add_argument(
        "--target-state",
        choices=["preop", "safeop"],
        default="preop",
        help="EtherCAT state used while probing/writing.",
    )
    parser.add_argument("--timeout-us", type=int, default=50000)
    return parser.parse_args()


def sdo_read(slave, index, subindex, size):
    return slave.sdo_read(index, subindex, size=size)


def read_u16(slave, index, subindex):
    return struct.unpack("<H", sdo_read(slave, index, subindex, 2)[:2])[0]


def read_u32(slave, index, subindex):
    return struct.unpack("<I", sdo_read(slave, index, subindex, 4)[:4])[0]


def read_f32(slave, index, subindex):
    return struct.unpack("<f", sdo_read(slave, index, subindex, 4)[:4])[0]


def write_u16(slave, index, subindex, value):
    slave.sdo_write(index, subindex, struct.pack("<H", int(value)))


def write_u32(slave, index, subindex, value):
    slave.sdo_write(index, subindex, struct.pack("<I", int(value)))


def write_f32(slave, index, subindex, value):
    slave.sdo_write(index, subindex, struct.pack("<f", float(value)))


def read_or_error(label, read_fn):
    try:
        return f"{label}={read_fn()}"
    except Exception as exc:
        return f"{label}=ERROR({exc})"


def print_sync_values(prefix, slave):
    fields = [
        read_or_error("1C32:01", lambda: read_u16(slave, 0x1C32, 0x01)),
        read_or_error("1C32:02ns", lambda: read_u32(slave, 0x1C32, 0x02)),
        read_or_error("1C32:04", lambda: read_u16(slave, 0x1C32, 0x04)),
        read_or_error("1C32:05ns", lambda: read_u32(slave, 0x1C32, 0x05)),
        read_or_error("1C32:0A", lambda: read_u32(slave, 0x1C32, 0x0A)),
        read_or_error("1C33:01", lambda: read_u16(slave, 0x1C33, 0x01)),
        read_or_error("1C33:02ns", lambda: read_u32(slave, 0x1C33, 0x02)),
        read_or_error("212E:01", lambda: read_u16(slave, 0x212E, 0x01)),
        read_or_error("212E:02s", lambda: f"{read_f32(slave, 0x212E, 0x02):.9f}"),
        read_or_error("212E:04", lambda: read_u16(slave, 0x212E, 0x04)),
        read_or_error("212E:05s", lambda: f"{read_f32(slave, 0x212E, 0x05):.9f}"),
        read_or_error("212E:08s", lambda: f"{read_f32(slave, 0x212E, 0x08):.9f}"),
        read_or_error("212E:09s", lambda: f"{read_f32(slave, 0x212E, 0x09):.9f}"),
        read_or_error("212E:0C", lambda: read_u16(slave, 0x212E, 0x0C)),
    ]
    print(f"{prefix}: " + " | ".join(fields), flush=True)


def request_state(master, state, timeout_us):
    master.state = state
    master.write_state()
    reached = master.state_check(state, timeout_us)
    if reached != state:
        raise RuntimeError(f"Failed to reach EtherCAT state {state}; reached {reached}")


def main():
    args = parse_args()
    master = pysoem.Master()
    master.open(args.interface)
    try:
        discovered = master.config_init()
        print(f"Discovered slaves: {discovered}", flush=True)
        if discovered < args.axis_count:
            raise RuntimeError(
                f"Expected {args.axis_count} slaves, found {discovered}"
            )

        target_state = (
            pysoem.PREOP_STATE
            if args.target_state == "preop"
            else pysoem.SAFEOP_STATE
        )
        if target_state == pysoem.SAFEOP_STATE:
            master.config_map()
        request_state(master, target_state, args.timeout_us)
        print(f"Reached EtherCAT state: {target_state}", flush=True)

        print("Before:", flush=True)
        for axis in range(args.axis_count):
            print_sync_values(f"  Axis {axis}", master.slaves[axis])

        if args.write:
            print(
                "Writing vendor sync objects "
                f"sync_mode={args.sync_mode} cycle_time={args.cycle_time}",
                flush=True,
            )
            for axis in range(args.axis_count):
                slave = master.slaves[axis]
                print(f"  Axis {axis} write 0x212E:01", flush=True)
                write_u16(slave, 0x212E, 0x01, args.sync_mode)
                print(f"  Axis {axis} write 0x212E:02", flush=True)
                write_f32(slave, 0x212E, 0x02, args.cycle_time)
                print(f"  Axis {axis} write 0x212E:09", flush=True)
                write_f32(slave, 0x212E, 0x09, args.cycle_time)

                if args.also_write_1c32:
                    cycle_ns = int(round(args.cycle_time * 1_000_000_000.0))
                    print(f"  Axis {axis} try direct 0x1C32/0x1C33 writes", flush=True)
                    write_u16(slave, 0x1C32, 0x01, args.sync_mode)
                    write_u32(slave, 0x1C32, 0x02, cycle_ns)
                    write_u16(slave, 0x1C33, 0x01, args.sync_mode)
                    write_u32(slave, 0x1C33, 0x02, cycle_ns)

            time.sleep(0.2)
            print("After write:", flush=True)
            for axis in range(args.axis_count):
                print_sync_values(f"  Axis {axis}", master.slaves[axis])

        request_state(master, pysoem.INIT_STATE, args.timeout_us)
        print("Returned EtherCAT network to INIT.", flush=True)
    finally:
        master.close()


if __name__ == "__main__":
    main()
