#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

export CIA402_AXIS_SERVER_HOST="${CIA402_AXIS_SERVER_HOST:-${CIA402_PYSOEM_HOST:-192.168.0.12}}"
export CIA402_AXIS_SERVER_PORT="${CIA402_AXIS_SERVER_PORT:-${CIA402_PYSOEM_PORT:-15000}}"
export PYTHONPATH=/workspace:${PYTHONPATH}

echo "ROS2_CIA402_AXIS_NAMES=${ROS2_CIA402_AXIS_NAMES:-from .env axis count}"
echo "Axis Server=${CIA402_AXIS_SERVER_HOST}:${CIA402_AXIS_SERVER_PORT}"

python3 /workspace/ros/bridge.py
