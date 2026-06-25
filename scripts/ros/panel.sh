#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash

export ROS2_CIA402_MASTER=pysoem
export ROS2_CIA402_AXIS_NAMES="${ROS2_CIA402_AXIS_NAMES:-X}"
export PYTHONPATH=/workspace:${PYTHONPATH}

echo "ROS2_CIA402_MASTER=${ROS2_CIA402_MASTER}"
echo "ROS2_CIA402_AXIS_NAMES=${ROS2_CIA402_AXIS_NAMES}"
echo "PYTHONPATH=${PYTHONPATH}"

python3 /workspace/ros/control_panel.py
