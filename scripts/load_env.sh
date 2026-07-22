#!/usr/bin/env bash
# Bash-safe .env loader (supports quoted values; SPARK_CONF_* must use underscores, not dots).
load_env_file() {
  local env_file="${1:?env file path required}"
  if [[ ! -f "${env_file}" ]]; then
    return 0
  fi
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%%#*}"
    line="$(echo "${line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "${line}" ]] && continue
    if [[ "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      export "${line?}"
    else
      echo "WARN: skipping invalid .env line: ${line}" >&2
    fi
  done < "${env_file}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  load_env_file "${PROJECT_ROOT}/.env"
fi
