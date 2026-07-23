#!/usr/bin/env bash
# Run a maintenance step with automatic pre/post metrics capture and comparison.
# Usage:
#   ./scripts/run_step_with_verify.sh step2_rewrite_data_files pre   # capture pre only
#   ./scripts/run_step_with_verify.sh step2_rewrite_data_files post  # capture post + compare to pre
#   ./scripts/run_step_with_verify.sh step2_rewrite_data_files run    # pre → procedure → post → compare
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STEP="${1:?step id required (e.g. step2_rewrite_data_files)}"
MODE="${2:?mode required: pre | post | run}"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/load_env.sh"
  set +a
fi

: "${MAINTENANCE_RUN_ID:=$(date -u +%Y%m%d_%H%M%S)}"
: "${TARGET_DATABASE:=${TEST_DATABASE:-}}"
: "${TARGET_TABLE:=${TEST_TABLE:-}}"
: "${ICEBERG_CATALOG:=spark_catalog}"
: "${PARTITION_FILTER:=${TEST_PARTITION_FILTER:-}}"
FULL_TABLE="${TARGET_DATABASE}.${TARGET_TABLE}"

# Guide defaults (sec. 6 & 8). Override in .env to reproduce on freshly-seeded tables,
# e.g. EXPIRE_OLDER_THAN="CURRENT_TIMESTAMP" EXPIRE_RETAIN_LAST=1 ORPHAN_OLDER_THAN="CURRENT_TIMESTAMP"
: "${EXPIRE_OLDER_THAN:=timestamp '2000-01-01 00:00:00'}"
: "${EXPIRE_RETAIN_LAST:=20}"
: "${EXPIRE_MAX_CONCURRENT_DELETES:=4}"
: "${ORPHAN_OLDER_THAN:=timestamp '2000-01-01 00:00:00'}"

METRICS_DIR="${METRICS_DIR:-${PROJECT_ROOT}/metrics/${MAINTENANCE_RUN_ID}}"
PRE_FILE="${METRICS_DIR}/${STEP}_pre.csv"
POST_FILE="${METRICS_DIR}/${STEP}_post.csv"

capture() {
  local label="$1"
  MAINTENANCE_RUN_ID="${MAINTENANCE_RUN_ID}" METRICS_DIR="${METRICS_DIR}" \
    "${SCRIPT_DIR}/capture_metrics.sh" "${label}"
}

compare() {
  "${SCRIPT_DIR}/compare_metrics.sh" "$1" "$2" "${STEP}" --format text
}

run_procedure() {
  case "${STEP}" in
    step2_rewrite_data_files)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_data_files(
  table => '${FULL_TABLE}',
  strategy => 'binpack',
  where => '${PARTITION_FILTER}',
  options => map(
    'target-file-size-bytes', '536870912',
    'min-input-files', '5',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480',
    'partial-progress.enabled', 'false'
  )
);
EOF
      ;;
    step3_rewrite_position_delete_files)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_position_delete_files(
  table => '${FULL_TABLE}',
  options => map(
    'min-input-files', '2',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480'
  )
);
EOF
      ;;
    step4_rewrite_manifests)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_manifests(
  table => '${FULL_TABLE}',
  use_caching => false
);
EOF
      ;;
    step5_expire_snapshots)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.expire_snapshots(
  table => '${FULL_TABLE}',
  older_than => ${EXPIRE_OLDER_THAN},
  retain_last => ${EXPIRE_RETAIN_LAST},
  max_concurrent_deletes => ${EXPIRE_MAX_CONCURRENT_DELETES}
);
EOF
      ;;
    step7_orphan_dry_run)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.remove_orphan_files(
  table => '${FULL_TABLE}',
  older_than => ${ORPHAN_OLDER_THAN},
  dry_run => true
);
EOF
      ;;
    step7_orphan_delete)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" <<EOF
CALL ${ICEBERG_CATALOG}.system.remove_orphan_files(
  table => '${FULL_TABLE}',
  older_than => ${ORPHAN_OLDER_THAN}
);
EOF
      ;;
    step6_metadata_properties)
      "${SCRIPT_DIR}/spark_sql_maintenance.sh" -e "
ALTER TABLE ${FULL_TABLE} SET TBLPROPERTIES (
  'write.metadata.delete-after-commit.enabled' = 'true',
  'write.metadata.previous-versions-max' = '100'
);"
      ;;
    *)
      echo "ERROR: no automated procedure for step '${STEP}'" >&2
      exit 1
      ;;
  esac
}

case "${MODE}" in
  pre)
    capture "${STEP}_pre"
    echo "Pre-metrics → ${PRE_FILE}"
    ;;
  post)
    capture "${STEP}_post"
    echo "Post-metrics → ${POST_FILE}"
    if [[ -f "${PRE_FILE}" ]]; then
      compare "${PRE_FILE}" "${POST_FILE}"
    else
      echo "WARN: pre-metrics not found at ${PRE_FILE}; capture with: $0 ${STEP} pre" >&2
    fi
    ;;
  run)
    capture "${STEP}_pre"
    echo "=== Running procedure for ${STEP} ==="
    run_procedure
    capture "${STEP}_post"
    compare "${PRE_FILE}" "${POST_FILE}"
    ;;
  *)
    echo "Usage: $0 <step_id> pre|post|run" >&2
    exit 1
    ;;
esac
