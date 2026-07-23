#!/usr/bin/env bash
# Run spark-sql on CDP with Kerberos, Auto-TLS, and Iceberg settings from environment.
# Falls back to PySpark (scripts/spark_sql_maintenance.py) when CDP spark-sql CLI
# is missing or lacks hive-thriftserver — same path as seed/pytest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/load_env.sh"
  set +a
fi

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/cdp_client_env.sh"

: "${KERBEROS_PRINCIPAL:=systest@QE-INFRA-AD.CLOUDERA.COM}"
: "${SPARK_MASTER:=yarn}"
: "${ICEBERG_CATALOG:=spark_catalog}"
: "${SPARK_QUEUE:=default}"
: "${SPARK_EXECUTOR_MEMORY:=8g}"
: "${SPARK_DRIVER_MEMORY:=4g}"
: "${SPARK_NUM_EXECUTORS:=4}"
: "${PYTHON:=python3.11}"
: "${SPARK_SQL_BACKEND:=auto}"

_resolve_python() {
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    echo "${PROJECT_ROOT}/.venv/bin/python"
  elif command -v "${PYTHON}" >/dev/null 2>&1; then
    command -v "${PYTHON}"
  else
    echo "${PYTHON}"
  fi
}

_run_pyspark_sql() {
  local py
  py="$(_resolve_python)"
  if [[ "${SPARK_SQL_BACKEND}" != "pyspark" && "${SPARK_SQL_BACKEND}" != "auto" ]]; then
    echo "ERROR: spark-sql CLI not found and SPARK_SQL_BACKEND=${SPARK_SQL_BACKEND}" >&2
    exit 1
  fi
  echo "NOTE: using PySpark SQL runner (same settings as seed/pytest)." >&2
  exec env PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}" \
    "${py}" "${SCRIPT_DIR}/spark_sql_maintenance.py" "$@"
}

SPARK_SQL=""
if [[ "${SPARK_SQL_BACKEND}" != "pyspark" ]]; then
  SPARK_SQL="$(resolve_spark_sql || true)"
fi

if [[ -z "${SPARK_SQL}" || ! -x "${SPARK_SQL}" ]]; then
  _run_pyspark_sql "$@"
fi

# Auto-TLS truststore for JVM (driver + client connections to HMS/HDFS/YARN)
if [[ -n "${TRUSTSTORE_PATH:-}" ]]; then
  export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} \
-Djavax.net.ssl.trustStore=${TRUSTSTORE_PATH} \
-Djavax.net.ssl.trustStorePassword=${TRUSTSTORE_PASSWORD:-changeit} \
-Djavax.net.ssl.trustStoreType=${TRUSTSTORE_TYPE:-JKS}"
fi

CONF=(
  --master "${SPARK_MASTER}"
  --deploy-mode client
  --name "iceberg-maintenance-${USER:-systest}"
  --queue "${SPARK_QUEUE}"
  --conf "spark.executor.memory=${SPARK_EXECUTOR_MEMORY}"
  --conf "spark.driver.memory=${SPARK_DRIVER_MEMORY}"
  --conf "spark.executor.instances=${SPARK_NUM_EXECUTORS}"
  --conf "spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
  --conf "spark.sql.catalog.${ICEBERG_CATALOG}=org.apache.iceberg.spark.SparkCatalog"
  --conf "spark.sql.catalog.${ICEBERG_CATALOG}.type=hive"
)

if [[ -n "${SPARK_YARN_PRINCIPAL:-${KERBEROS_PRINCIPAL}}" ]] && [[ -n "${SPARK_YARN_KEYTAB:-${KERBEROS_KEYTAB:-}}" ]]; then
  CONF+=(
    --conf "spark.kerberos.principal=${SPARK_YARN_PRINCIPAL:-${KERBEROS_PRINCIPAL}}"
    --conf "spark.kerberos.keytab=${SPARK_YARN_KEYTAB:-${KERBEROS_KEYTAB}}"
    --conf "spark.yarn.principal=${SPARK_YARN_PRINCIPAL:-${KERBEROS_PRINCIPAL}}"
    --conf "spark.yarn.keytab=${SPARK_YARN_KEYTAB:-${KERBEROS_KEYTAB}}"
  )
fi

# Extra SPARK_CONF_* from .env (SPARK_CONF_spark.sql.shuffle.partitions=200 → spark.sql.shuffle.partitions)
while IFS='=' read -r key value; do
  if [[ "${key}" == SPARK_CONF_* ]]; then
    spark_key="${key#SPARK_CONF_}"
    spark_key="${spark_key//_/.}"
    CONF+=(--conf "${spark_key}=${value}")
  fi
done < <(env)

if [[ $# -eq 0 ]]; then
  exec "${SPARK_SQL}" "${CONF[@]}"
fi

if [[ "${1}" == "-e" ]]; then
  shift
  exec "${SPARK_SQL}" "${CONF[@]}" -e "$*"
fi

if [[ "${1}" == "-f" ]]; then
  shift
  exec "${SPARK_SQL}" "${CONF[@]}" -f "$1"
fi

# heredoc on stdin
exec "${SPARK_SQL}" "${CONF[@]}"
