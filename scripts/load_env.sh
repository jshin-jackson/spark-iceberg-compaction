#!/usr/bin/env bash
# Bash-safe .env loader (supports quoted values; SPARK_CONF_* must use underscores, not dots).
#
# Usage (interactive shell — exports persist):
#   source scripts/load_env.sh
#
# Maintenance scripts (kinit_cdp.sh, spark_sql_maintenance.sh, ...) source this automatically.
# Do NOT run ./scripts/load_env.sh expecting exports in the parent shell (subshell limitation).

_LOAD_ENV_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_LOAD_ENV_PROJECT_ROOT="$(cd "${_LOAD_ENV_SCRIPT_DIR}/.." && pwd)"

load_env_file() {
  local env_file="${1:-${_LOAD_ENV_PROJECT_ROOT}/.env}"
  if [[ ! -f "${env_file}" ]]; then
    echo "WARN: .env not found: ${env_file} (run: cp .env.example .env)" >&2
    return 1
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

if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  load_env_file "${_LOAD_ENV_PROJECT_ROOT}/.env"
  if [[ -f "${_LOAD_ENV_SCRIPT_DIR}/cdp_client_env.sh" ]]; then
    # shellcheck disable=SC1091
    source "${_LOAD_ENV_SCRIPT_DIR}/cdp_client_env.sh"
  fi
else
  cat >&2 <<EOF
load_env.sh must be sourced to export variables into your current shell:

  cd ${_LOAD_ENV_PROJECT_ROOT}
  source scripts/load_env.sh

Or run a maintenance script directly (loads .env automatically):

  ./scripts/kinit_cdp.sh
EOF
  exit 1
fi
