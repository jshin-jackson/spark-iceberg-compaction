#!/usr/bin/env bash
# Create venv and install guide-validator (CDP edge: use python3.11, not python/python3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/load_env.sh"
  set +a
fi

PYTHON="${PYTHON:-python3.11}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "ERROR: ${PYTHON} not found (CDP edge: install or use /usr/bin/python3.11)" >&2
  exit 1
fi

if ! "${PYTHON}" -c "import venv" 2>/dev/null; then
  echo "ERROR: ${PYTHON} has no venv module. On RHEL/CentOS try: yum install python3.11-venv" >&2
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
echo "Venv python: $(python --version)"
