#!/usr/bin/env bash
# Run spark-sql on CDP with Kerberos, Auto-TLS, and Iceberg settings from environment.
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

# Load Spark environment from CDP parcel if present (cdp_client_env.sh may have set SPARK_HOME)
if [[ -z "${SPARK_HOME:-}" ]]; then
for spark_env in /opt/cloudera/parcels/CDH/lib/spark3/bin/spark-env.sh \
                 /var/lib/cloudera-scm-agent/build/*/spark3/spark3-env.sh; do
  if [[ -f "${spark_env}" ]]; then
    # shellcheck disable=SC1090
    source "${spark_env}"
    break
  fi
done
fi

SPARK_SQL="${SPARK_HOME:-}/bin/spark-sql"
if [[ ! -x "${SPARK_SQL}" ]]; then
  SPARK_SQL="$(command -v spark-sql || true)"
fi
if [[ -z "${SPARK_SQL}" || ! -x "${SPARK_SQL}" ]]; then
  echo "ERROR: spark-sql not found. Set SPARK_HOME or run on a CDP gateway node." >&2
  exit 1
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
