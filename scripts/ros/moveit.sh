#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/ros/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
COMMAND=()
BUILD_MOVEIT=0

case "${1:-}" in
  "")
    COMMAND=(/bin/bash)
    ;;
  --build)
    BUILD_MOVEIT=1
    COMMAND=(/bin/bash)
    ;;
  --check)
    COMMAND=(bash -lc "source /opt/ros/jazzy/setup.bash && ros2 pkg prefix moveit_setup_assistant && ros2 pkg executables moveit_setup_assistant && ros2 pkg list | grep -E '^(moveit|moveit_ros|moveit_setup_assistant)' && echo 'MoveIt installation check passed.'")
    ;;
  --setup-assistant)
    COMMAND=(bash -lc "source /opt/ros/jazzy/setup.bash && if [[ -f install/moveit/setup.bash ]]; then source install/moveit/setup.bash; else echo 'MoveIt workspace is not built yet. Run: bash scripts/ros/moveit.sh --build-workspace'; exit 1; fi && ros2 run moveit_setup_assistant moveit_setup_assistant")
    ;;
  --build-workspace)
    COMMAND=(bash -lc "source /opt/ros/jazzy/setup.bash && colcon build --base-paths ros_moveit/ros2_cia402_cartesian_description ros_moveit/ros2_cia402_cartesian_moveit_config --build-base build/moveit --install-base install/moveit")
    ;;
  --display-cartesian)
    COMMAND=(bash -lc "source /opt/ros/jazzy/setup.bash && if [[ -f install/moveit/setup.bash ]]; then source install/moveit/setup.bash; else echo 'MoveIt workspace is not built yet. Run: bash scripts/ros/moveit.sh --build-workspace'; exit 1; fi && ros2 launch ros2_cia402_cartesian_description display.launch.py")
    ;;
  --move-group)
    COMMAND=(bash -lc "source /opt/ros/jazzy/setup.bash && if [[ -f install/moveit/setup.bash ]]; then source install/moveit/setup.bash; else echo 'MoveIt workspace is not built yet. Run: bash scripts/ros/moveit.sh --build-workspace'; exit 1; fi && ros2 launch ros2_cia402_cartesian_moveit_config move_group.launch.py")
    ;;
  *)
    echo "Usage: bash scripts/ros/moveit.sh [--build|--check|--setup-assistant|--build-workspace|--display-cartesian|--move-group]"
    exit 2
    ;;
esac

cd "${PROJECT_ROOT}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}"
  echo "Create it from .env.example first."
  echo "  cp .env.example .env"
  exit 1
fi

if [[ "${BUILD_MOVEIT}" == "1" ]]; then
  echo "Building ROS MoveIt image"
  docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build ros_moveit
fi

exec docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm ros_moveit "${COMMAND[@]}"
