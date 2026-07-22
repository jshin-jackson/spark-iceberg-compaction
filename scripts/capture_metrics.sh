#!/usr/bin/env bash
# Capture Iceberg table metrics snapshot for step-wise verification.
# Usage: ./scripts/capture_metrics.sh <label>
# Example: MAINTENANCE_RUN_ID=20260722_0100 ./scripts/capture_metrics.sh step2_pre
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <label>" >&2
  echo "Example: MAINTENANCE_RUN_ID=20260722_0100 $0 step2_pre" >&2
  exit 1
fi

LABEL="$1"
: "${MAINTENANCE_RUN_ID:=$(date -u +%Y%m%d_%H%M%S)}"
METRICS_DIR="${METRICS_DIR:-${PROJECT_ROOT}/metrics/${MAINTENANCE_RUN_ID}}"
mkdir -p "${METRICS_DIR}"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/load_env.sh"
  set +a
fi

: "${TARGET_DATABASE:=${TEST_DATABASE:-}}"
: "${TARGET_TABLE:=${TEST_TABLE:-}}"
FULL_TABLE="${TARGET_DATABASE}.${TARGET_TABLE}"

if [[ -z "${TARGET_DATABASE}" || -z "${TARGET_TABLE}" ]]; then
  echo "ERROR: TARGET_DATABASE and TARGET_TABLE must be set" >&2
  exit 1
fi

OUTPUT_CSV="${METRICS_DIR}/${LABEL}.csv"
OUTPUT_META="${METRICS_DIR}/${LABEL}.meta"
SQL_FILE="${METRICS_DIR}/._metrics_query.sql"
HISTORY_FILE="${METRICS_DIR}/${LABEL}_history.tsv"
PROPS_FILE="${METRICS_DIR}/${LABEL}_tblproperties.tsv"

export MAINTENANCE_RUN_ID METRICS_DIR

# Generate metrics SQL via Python (no Spark required for generation)
PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}" python3 - <<'PY' > "${SQL_FILE}"
from guide_validator.verification_queries import MetricsContext, build_metrics_sql
print(build_metrics_sql(MetricsContext.from_env()))
PY

echo "label=${LABEL}" > "${OUTPUT_META}"
echo "captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${OUTPUT_META}"
echo "full_table=${FULL_TABLE}" >> "${OUTPUT_META}"
echo "partition_filter=${PARTITION_FILTER:-${TEST_PARTITION_FILTER:-}}" >> "${OUTPUT_META}"
echo "run_id=${MAINTENANCE_RUN_ID}" >> "${OUTPUT_META}"

# Primary metrics (single result set)
"${SCRIPT_DIR}/spark_sql_maintenance.sh" -f "${SQL_FILE}" > "${OUTPUT_CSV}.raw" 2>"${METRICS_DIR}/${LABEL}.log"

# Normalize to CSV (spark-sql may include header + table borders)
{
  echo "metric,value,unit"
  awk -F'|' '
    NR > 3 && NF >= 3 {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      gsub(/^[ \t]+|[ \t]+$/, "", $3)
      gsub(/^[ \t]+|[ \t]+$/, "", $4)
      if ($2 != "" && $2 != "metric") print $2 "," $3 "," $4
    }
  ' "${OUTPUT_CSV}.raw"
} > "${OUTPUT_CSV}"

# Supplementary: recent history (human review)
"${SCRIPT_DIR}/spark_sql_maintenance.sh" -e \
  "SELECT made_current_at, snapshot_id, parent_id, summary FROM ${FULL_TABLE}.history ORDER BY made_current_at DESC LIMIT 5;" \
  > "${HISTORY_FILE}" 2>>"${METRICS_DIR}/${LABEL}.log" || true

# Supplementary: table properties
"${SCRIPT_DIR}/spark_sql_maintenance.sh" -e \
  "SHOW TBLPROPERTIES ${FULL_TABLE};" \
  > "${PROPS_FILE}" 2>>"${METRICS_DIR}/${LABEL}.log" || true

echo "Captured metrics:"
echo "  CSV:        ${OUTPUT_CSV}"
echo "  History:    ${HISTORY_FILE}"
echo "  Properties: ${PROPS_FILE}"
echo "  Run dir:    ${METRICS_DIR}"
wc -l < "${OUTPUT_CSV}" | xargs echo "  Metric rows:"
