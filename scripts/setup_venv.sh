#!/usr/bin/env bash
# Create venv and install guide-validator (CDP edge nodes: use python3, not python).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-python3}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON} not found" >&2
  exit 1
fi

if ! "${PYTHON}" -c "import venv" 2>/dev/null; then
  echo "ERROR: ${PYTHON} has no venv module. On RHEL/CentOS try: yum install python3-venv" >&2
  exit 1
fi

echo "Using: $("${PYTHON}" --version)"
"${PYTHON}" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
echo "Done. Activate with: source .venv/bin/activate"
