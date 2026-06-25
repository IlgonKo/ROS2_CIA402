from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ethercat.pysoem_master import PySOEMMaster


def decode_mapping_entry(entry):
    index = (entry >> 16) & 0xFFFF
    subindex = (entry >> 8) & 0xFF
    bit_length = entry & 0xFF
    return index, subindex, bit_length


def read_u8(master, object_index, subindex):
    return master.sdo_read_uint8(0, object_index, subindex)


def read_u32(master, object_index, subindex):
    return master.sdo_read_uint32(0, object_index, subindex)


def dump_mapping_object(master, object_index):
    try:
        count = read_u8(master, object_index, 0)
    except Exception as exc:
        print(f"0x{object_index:04X}: read failed: {exc}")
        return

    print(f"0x{object_index:04X}: {count} entries")

    total_bits = 0
    for subindex in range(1, count + 1):
        entry = read_u32(master, object_index, subindex)
        mapped_index, mapped_subindex, bit_length = decode_mapping_entry(entry)
        total_bits += bit_length
        print(
            f"  {subindex}: "
            f"0x{entry:08X} -> "
            f"0x{mapped_index:04X}:{mapped_subindex:02X} "
            f"{bit_length} bits"
        )

    print(f"  total: {total_bits} bits / {total_bits // 8} bytes")


def dump_assignment(master, object_index, label):
    try:
        count = read_u8(master, object_index, 0)
    except Exception as exc:
        print(f"{label} 0x{object_index:04X}: read failed: {exc}")
        return []

    print(f"{label} 0x{object_index:04X}: {count} assigned PDOs")

    pdo_indices = []
    for subindex in range(1, count + 1):
        pdo_index = master.sdo_read_uint16(0, object_index, subindex)
        pdo_indices.append(pdo_index)
        print(f"  {subindex}: 0x{pdo_index:04X}")

    return pdo_indices


def main():
    if len(sys.argv) != 2:
        print("usage: dump_pdo_mapping.py <interface>")
        raise SystemExit(2)

    master = PySOEMMaster(
        interface_name=sys.argv[1],
        slave_count=1,
    )

    try:
        master.connect()

        rxpdo_indices = dump_assignment(master, 0x1C12, "RxPDO assignment")
        for pdo_index in rxpdo_indices:
            dump_mapping_object(master, pdo_index)

        txpdo_indices = dump_assignment(master, 0x1C13, "TxPDO assignment")
        for pdo_index in txpdo_indices:
            dump_mapping_object(master, pdo_index)

    finally:
        master.close()


if __name__ == "__main__":
    main()
