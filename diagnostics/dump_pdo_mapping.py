from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from device import get_device_profile
from ethercat.pysoem_master import PySOEMMaster


def parse_args():
    parser = argparse.ArgumentParser(description="Dump EtherCAT PDO mappings.")
    parser.add_argument("interface")
    parser.add_argument("--axis-count", type=int, default=1)
    parser.add_argument(
        "--target-state",
        choices=["preop", "safeop", "op"],
        default="preop",
        help="State requested before dumping. preop avoids SAFE_OP validation.",
    )
    return parser.parse_args()


def decode_mapping_entry(entry):
    index = (entry >> 16) & 0xFFFF
    subindex = (entry >> 8) & 0xFF
    bit_length = entry & 0xFF
    return index, subindex, bit_length


def read_u8(master, axis_index, object_index, subindex):
    return master.sdo.read_uint8(axis_index, object_index, subindex)


def read_u32(master, axis_index, object_index, subindex):
    return master.sdo.read_uint32(axis_index, object_index, subindex)


def dump_mapping_object(master, axis_index, object_index):
    try:
        count = read_u8(master, axis_index, object_index, 0)
    except Exception as exc:
        print(f"0x{object_index:04X}: read failed: {exc}")
        return

    print(f"0x{object_index:04X}: {count} entries")

    total_bits = 0
    for subindex in range(1, count + 1):
        entry = read_u32(master, axis_index, object_index, subindex)
        mapped_index, mapped_subindex, bit_length = decode_mapping_entry(entry)
        total_bits += bit_length
        print(
            f"  {subindex}: "
            f"0x{entry:08X} -> "
            f"0x{mapped_index:04X}:{mapped_subindex:02X} "
            f"{bit_length} bits"
        )

    print(f"  total: {total_bits} bits / {total_bits // 8} bytes")


def dump_assignment(master, axis_index, object_index, label):
    try:
        count = read_u8(master, axis_index, object_index, 0)
    except Exception as exc:
        print(f"{label} 0x{object_index:04X}: read failed: {exc}")
        return []

    print(f"{label} 0x{object_index:04X}: {count} assigned PDOs")

    pdo_indices = []
    for subindex in range(1, count + 1):
        pdo_index = master.sdo.read_uint16(axis_index, object_index, subindex)
        pdo_indices.append(pdo_index)
        print(f"  {subindex}: 0x{pdo_index:04X}")

    return pdo_indices


def main():
    args = parse_args()

    master = PySOEMMaster(
        interface_name=args.interface,
        device_profiles=[
            get_device_profile("cmmt")
            for _ in range(args.axis_count)
        ],
    )

    try:
        pysoem = master._load_pysoem()
        target_states = {
            "preop": pysoem.PREOP_STATE,
            "safeop": pysoem.SAFEOP_STATE,
            "op": pysoem.OP_STATE,
        }
        master.connect(target_state=target_states[args.target_state])

        for axis_index in range(args.axis_count):
            print(f"\nAxis {axis_index}")
            rxpdo_indices = dump_assignment(
                master,
                axis_index,
                0x1C12,
                "RxPDO assignment",
            )
            for pdo_index in rxpdo_indices:
                dump_mapping_object(master, axis_index, pdo_index)

            txpdo_indices = dump_assignment(
                master,
                axis_index,
                0x1C13,
                "TxPDO assignment",
            )
            for pdo_index in txpdo_indices:
                dump_mapping_object(master, axis_index, pdo_index)

    finally:
        master.close()


if __name__ == "__main__":
    main()
