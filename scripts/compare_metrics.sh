#!/usr/bin/env bash
# Compare before/after metric snapshots for a maintenance step.
# Usage: ./scripts/compare_metrics.sh <before.csv> <after.csv> <step_id>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <before.csv> <after.csv> <step_id>" >&2
  echo "Step ids: step2_rewrite_data_files, step3_rewrite_position_delete_files, ..." >&2
  exit 1
fi

python3 -m guide_validator.metrics_compare "$1" "$2" --step "$3" "${@:4}"
