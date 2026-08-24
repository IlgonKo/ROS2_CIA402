#!/usr/bin/env bash

prepare_compose_env_file() {
  local project_root="$1"
  local base_env="${project_root}/.env"
  local runtime_dir="${project_root}/.runtime"
  local combined_env="${runtime_dir}/compose.env"

  if [[ ! -f "${base_env}" ]]; then
    echo "Missing ${base_env}" >&2
    echo "Create it from .env.example first." >&2
    echo "  cp .env.example .env" >&2
    return 1
  fi

  mkdir -p "${runtime_dir}"
  (
    cd "${project_root}" || exit 1
    python3 -m configuration \
      --project-root "${project_root}" \
      --format env
  ) > "${combined_env}" || return 1

  printf '%s\n' "${combined_env}"
}
