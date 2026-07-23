#!/usr/bin/env bash
# CDP client-side Hadoop/Spark environment (HDFS HA nameservice, conf dir).
# Source after load_env.sh so .env overrides apply:
#   source scripts/load_env.sh
#   source scripts/cdp_client_env.sh
#
# Prevents Spark/YARN from hitting a standby NameNode (host:8020) when HDFS HA
# is configured with nameservice ns1.

# CDP hadoop-env.sh / spark-env.sh reference vars that may be unset; callers
# (kinit_cdp.sh, spark_sql_maintenance.sh) use set -u.
_source_vendor_env() {
  local env_file="$1"
  local had_nounset=0
  [[ $- == *u* ]] && had_nounset=1 && set +u
  # shellcheck disable=SC1090
  source "${env_file}"
  if (( had_nounset )); then
    set -u
  fi
}

: "${HADOOP_CONF_DIR:=/etc/hadoop/conf}"
if [[ -d "${HADOOP_CONF_DIR}" ]]; then
  export HADOOP_CONF_DIR
  if [[ -f "${HADOOP_CONF_DIR}/hadoop-env.sh" ]]; then
    _source_vendor_env "${HADOOP_CONF_DIR}/hadoop-env.sh"
  fi
fi

: "${HDFS_NAMESERVICE:=ns1}"
export HDFS_NAMESERVICE

: "${HDFS_DEFAULT_FS:=hdfs://${HDFS_NAMESERVICE}}"
export HDFS_DEFAULT_FS

# Spark parcel (for spark-sql / PySpark when SPARK_HOME unset)
if [[ -z "${SPARK_HOME:-}" ]]; then
  for spark_env in /opt/cloudera/parcels/CDH/lib/spark3/bin/spark-env.sh \
                   /var/lib/cloudera-scm-agent/build/*/spark3/spark3-env.sh; do
    if [[ -f "${spark_env}" ]]; then
      _source_vendor_env "${spark_env}"
      break
    fi
  done
fi
