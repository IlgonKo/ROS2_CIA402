#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

export PYTHONPATH=/workspace:${PYTHONPATH}

echo "Starting ROS Control Panel"
echo "ROS2_CIA402_AXIS_NAMES=${ROS2_CIA402_AXIS_NAMES:-from .env axis count}"
echo "PYTHONPATH=${PYTHONPATH}"

python3 /workspace/ros/control_panel.py
