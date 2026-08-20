#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
GRUB_FILE="/etc/default/grub"
ACTION="${1:-status}"

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
  fi

  ISOLATED_CPUS="${MOTION_SERVER_ISOLATED_CPUS:-${MOTION_SERVER_CPUSET:-6}}"
  HOUSEKEEPING_CPUS="${MOTION_SERVER_HOUSEKEEPING_CPUS:-0-5,7}"
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run with sudo:"
    echo "  sudo bash scripts/host/isolate_cpu.sh ${ACTION}"
    exit 1
  fi
}

install_isolation() {
  require_root
  load_env

  local backup
  backup="${GRUB_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "${GRUB_FILE}" "${backup}"

  python3 - "${GRUB_FILE}" "${ISOLATED_CPUS}" "${HOUSEKEEPING_CPUS}" <<'PY'
import re
import sys

path, isolated_cpus, housekeeping_cpus = sys.argv[1:4]
managed_keys = {
    "isolcpus",
    "nohz_full",
    "rcu_nocbs",
    "irqaffinity",
    "kthread_cpus",
}
new_args = [
    f"isolcpus=domain,managed_irq,{isolated_cpus}",
    f"nohz_full={isolated_cpus}",
    f"rcu_nocbs={isolated_cpus}",
    f"irqaffinity={housekeeping_cpus}",
    f"kthread_cpus={housekeeping_cpus}",
]

with open(path, "r", encoding="utf-8") as handle:
    text = handle.read()

pattern = re.compile(r'^(GRUB_CMDLINE_LINUX_DEFAULT=)"([^"]*)"', re.MULTILINE)
match = pattern.search(text)
if not match:
    raise SystemExit("GRUB_CMDLINE_LINUX_DEFAULT was not found")

current = match.group(2).split()
kept = [
    item
    for item in current
    if item.split("=", 1)[0] not in managed_keys
]
updated = " ".join(kept + new_args)
text = pattern.sub(rf'\1"{updated}"', text)

with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY

  update-grub

  echo "Installed host CPU isolation."
  echo "  isolated CPUs: ${ISOLATED_CPUS}"
  echo "  housekeeping CPUs: ${HOUSEKEEPING_CPUS}"
  echo "  backup: ${backup}"
  echo "Reboot is required:"
  echo "  sudo reboot"
}

revert_isolation() {
  require_root

  local backup
  backup="${GRUB_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "${GRUB_FILE}" "${backup}"

  python3 - "${GRUB_FILE}" <<'PY'
import re
import sys

path = sys.argv[1]
managed_keys = {
    "isolcpus",
    "nohz_full",
    "rcu_nocbs",
    "irqaffinity",
    "kthread_cpus",
}

with open(path, "r", encoding="utf-8") as handle:
    text = handle.read()

pattern = re.compile(r'^(GRUB_CMDLINE_LINUX_DEFAULT=)"([^"]*)"', re.MULTILINE)
match = pattern.search(text)
if not match:
    raise SystemExit("GRUB_CMDLINE_LINUX_DEFAULT was not found")

kept = [
    item
    for item in match.group(2).split()
    if item.split("=", 1)[0] not in managed_keys
]
text = pattern.sub(rf'\1"{" ".join(kept)}"', text)

with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY

  update-grub

  echo "Removed host CPU isolation arguments."
  echo "  backup: ${backup}"
  echo "Reboot is required:"
  echo "  sudo reboot"
}

status_isolation() {
  load_env

  echo "Configured in ${ENV_FILE}:"
  echo "  MOTION_SERVER_CPUSET=${MOTION_SERVER_CPUSET:-}"
  echo "  MOTION_SERVER_ISOLATED_CPUS=${MOTION_SERVER_ISOLATED_CPUS:-${MOTION_SERVER_CPUSET:-6}}"
  echo "  MOTION_SERVER_HOUSEKEEPING_CPUS=${MOTION_SERVER_HOUSEKEEPING_CPUS:-0-5,7}"
  echo ""
  echo "Current kernel command line:"
  cat /proc/cmdline
  echo ""
  echo "GRUB default command line:"
  grep '^GRUB_CMDLINE_LINUX_DEFAULT=' "${GRUB_FILE}" || true
}

case "${ACTION}" in
  install)
    install_isolation
    ;;
  revert|uninstall)
    revert_isolation
    ;;
  status)
    status_isolation
    ;;
  *)
    echo "Usage: bash scripts/host/isolate_cpu.sh {install|revert|status}"
    exit 2
    ;;
esac
