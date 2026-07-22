#!/usr/bin/env bash
# Create venv and install guide-validator (CDP edge nodes: use python3, not python).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON} not found" >&2
  exit 1
fi

if ! "${PYTHON}" -c "import venv" 2>/dev/null; then
  echo "ERROR: ${PYTHON} has no venv module. On RHEL/CentOS try: yum install python3-venv" >&2
  exit 1
fi

echo "Using: $("${PYTHON}" --version)"

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# CDP parcel Python often ships pip 21.x — upgrade before pyproject editable install
python -m pip install --upgrade pip setuptools wheel

python -m pip install -e ".[dev]"

echo "Done. Activate with: source ${VENV_DIR}/bin/activate"
