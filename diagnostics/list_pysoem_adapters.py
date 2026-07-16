from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from device import get_device_profile
from ethercat.pysoem_master import PySOEMMaster


def main():
    loader = PySOEMMaster(
        "unused",
        device_profiles=[get_device_profile("cmmt")],
    )
    pysoem = loader._load_pysoem()

    for adapter in pysoem.find_adapters():
        print(f"name={adapter.name}")
        print(f"desc={adapter.desc}")
        print()


if __name__ == "__main__":
    main()
