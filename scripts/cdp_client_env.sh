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

_cdp_spark_env_candidates() {
  local spark_env
  for spark_env in \
    /opt/cloudera/parcels/SPARK3/lib/spark3/bin/spark-env.sh \
    /var/lib/cloudera-scm-agent/build/*/spark3/spark3-env.sh \
    /opt/cloudera/parcels/CDH/lib/spark3/bin/spark-env.sh
  do
    if [[ -f "${spark_env}" ]]; then
      echo "${spark_env}"
    fi
  done
}

# spark-sql CLI needs hive-thriftserver jars; CDH/lib/spark3 alone is often incomplete.
_cdp_spark_home_has_hive_cli() {
  local home="$1"
  [[ -n "${home}" && -d "${home}/bin" && -d "${home}/jars" ]] || return 1
  [[ -x "${home}/bin/spark3-sql" || -x "${home}/bin/spark-sql" ]] || return 1
  compgen -G "${home}/jars/spark-hive_*.jar" >/dev/null \
    || compgen -G "${home}/jars/*hive*thrift*.jar" >/dev/null
}

_cdp_spark_home_from_env_file() {
  local spark_env="$1"
  dirname "$(dirname "${spark_env}")"
}

_configure_cdp_spark_home() {
  if [[ -n "${SPARK_HOME:-}" ]] && _cdp_spark_home_has_hive_cli "${SPARK_HOME}"; then
    export SPARK_HOME
    return 0
  fi

  local spark_env home saved_home="${SPARK_HOME:-}"
  unset SPARK_HOME
  for spark_env in $(_cdp_spark_env_candidates); do
    _source_vendor_env "${spark_env}"
    home="${SPARK_HOME:-}"
    if [[ -z "${home}" ]]; then
      home="$(_cdp_spark_home_from_env_file "${spark_env}")"
    fi
    if _cdp_spark_home_has_hive_cli "${home}"; then
      export SPARK_HOME="${home}"
      return 0
    fi
    unset SPARK_HOME
  done

  if [[ -n "${saved_home}" ]]; then
    export SPARK_HOME="${saved_home}"
  fi
  return 1
}

# Resolve CDP spark3-sql / spark-sql — never use PATH (avoids .venv PySpark shims).
resolve_spark_sql() {
  _configure_cdp_spark_home || true
  local home="${SPARK_HOME:-}" candidate
  if [[ -n "${home}" ]]; then
    for candidate in "${home}/bin/spark3-sql" "${home}/bin/spark-sql"; do
      if [[ -x "${candidate}" ]]; then
        echo "${candidate}"
        return 0
      fi
    done
  fi

  for home in \
    /opt/cloudera/parcels/SPARK3/lib/spark3 \
    /var/lib/cloudera-scm-agent/build/*/spark3 \
    /opt/cloudera/parcels/CDH/lib/spark3
  do
    [[ -d "${home}" ]] || continue
    for candidate in "${home}/bin/spark3-sql" "${home}/bin/spark-sql"; do
      if [[ -x "${candidate}" ]] && _cdp_spark_home_has_hive_cli "${home}"; then
        export SPARK_HOME="${home}"
        echo "${candidate}"
        return 0
      fi
    done
  done
  return 1
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

_configure_cdp_spark_home || true
