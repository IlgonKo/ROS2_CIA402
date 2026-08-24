import argparse
import json
from pathlib import Path

from configuration.file_parser import read_key_value_config
from configuration.loader import load_configuration
from device import available_device_names


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Load Motion Server configuration.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--project-root", type=Path)
    source.add_argument("--file", type=Path)
    parser.add_argument("--project-filename", default=".env")
    parser.add_argument("--device-filename", default=".env")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.file is not None:
        values = read_key_value_config(args.file)
    else:
        model = load_configuration(
            args.project_root,
            project_filename=args.project_filename,
            device_filename=args.device_filename,
            available_profiles=available_device_names(),
        )
        values = dict(model.values)
    if args.format == "json":
        print(json.dumps(values, ensure_ascii=False, sort_keys=True))
        return
    for key in sorted(values):
        print(f"{key}={values[key]}")


if __name__ == "__main__":
    main()
