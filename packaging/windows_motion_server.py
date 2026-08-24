from windows_runtime import prepare_runtime
import sys


root = prepare_runtime()

from configuration import ConfigurationSource
from motion_server.application import MotionServerApplication


if __name__ == "__main__":
    MotionServerApplication.from_source(
        ConfigurationSource(
            project_root=root,
            project_filename="config.txt",
            device_filename="config.txt",
        ),
        argv=sys.argv[1:],
    ).run()
