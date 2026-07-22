#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker/motion_server/compose.yaml"
ENV_FILE="${PROJECT_ROOT}/.env"
source "${PROJECT_ROOT}/scripts/env.sh"
SERVICE_NAME="ros-cia402-axis-server.service"
LEGACY_SERVICE_NAME="ros2-cia402-pysoem.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
LEGACY_SERVICE_FILE="/etc/systemd/system/${LEGACY_SERVICE_NAME}"
ACTION="${1:-install}"

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run with sudo:"
    echo "  sudo bash scripts/host/service.sh ${ACTION}"
    exit 1
  fi
}

install_service() {
  require_root

  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}"
    echo "Create it from .env.example, then edit MOTION_SERVER_BACKEND and PYSOEM_BUS."
    echo "  cp .env.example .env"
    exit 1
  fi

  COMPOSE_ENV_FILE="$(prepare_compose_env_file "${PROJECT_ROOT}")"

  systemctl disable --now "${LEGACY_SERVICE_NAME}" 2>/dev/null || true
  rm -f "${LEGACY_SERVICE_FILE}"

  cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=ROS CiA402 Axis Server
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${PROJECT_ROOT}
ExecStartPre=-/usr/bin/docker rm -f ros_cia402_motion_server
ExecStartPre=-/usr/bin/docker rm -f ros2_cia402_pysoem_host
ExecStart=/usr/bin/bash -lc 'source ${PROJECT_ROOT}/scripts/env.sh; COMPOSE_ENV_FILE="\$(prepare_compose_env_file ${PROJECT_ROOT})"; exec /usr/bin/docker compose -f ${COMPOSE_FILE} --env-file "\${COMPOSE_ENV_FILE}" up -d motion_server'
ExecStop=/usr/bin/bash -lc 'source ${PROJECT_ROOT}/scripts/env.sh; COMPOSE_ENV_FILE="\$(prepare_compose_env_file ${PROJECT_ROOT})"; exec /usr/bin/docker compose -f ${COMPOSE_FILE} --env-file "\${COMPOSE_ENV_FILE}" down'
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

  cd "${PROJECT_ROOT}"
  docker compose -f "${COMPOSE_FILE}" --env-file "${COMPOSE_ENV_FILE}" build motion_server
  docker rm -f ros_cia402_motion_server 2>/dev/null || true
  docker rm -f ros2_cia402_pysoem_host 2>/dev/null || true

  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"

  echo "Installed and started ${SERVICE_NAME}"
  echo "Runtime settings are read from ${COMPOSE_ENV_FILE}"
  cat "${COMPOSE_ENV_FILE}"
  echo ""
  systemctl --no-pager status "${SERVICE_NAME}"
}

uninstall_service() {
  require_root

  systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable --now "${LEGACY_SERVICE_NAME}" 2>/dev/null || true
  rm -f "${SERVICE_FILE}"
  rm -f "${LEGACY_SERVICE_FILE}"
  systemctl daemon-reload

  echo "Uninstalled ${SERVICE_NAME}"
}

case "${ACTION}" in
  install)
    install_service
    ;;
  uninstall)
    uninstall_service
    ;;
  restart)
    require_root
    systemctl restart "${SERVICE_NAME}"
    ;;
  stop)
    require_root
    systemctl stop "${SERVICE_NAME}"
    ;;
  status)
    systemctl --no-pager status "${SERVICE_NAME}"
    ;;
  logs)
    journalctl -xeu "${SERVICE_NAME}" --no-pager
    ;;
  *)
    echo "Usage: bash scripts/host/service.sh {install|uninstall|restart|stop|status|logs}"
    exit 2
    ;;
esac
