from pathlib import Path
import sys

from configuration import ConfigurationSource
from motion_server.application import MotionServerApplication


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    source = ConfigurationSource(
        project_root=Path(__file__).resolve().parents[1],
    )
    return MotionServerApplication.from_source(source, argv=argv).run()


if __name__ == "__main__":
    main()
