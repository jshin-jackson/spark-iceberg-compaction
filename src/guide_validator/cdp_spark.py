"""CDP Spark session helpers for integration tests."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from dotenv import load_dotenv

from guide_validator.template_renderer import CdpEnv


def load_cdp_env() -> None:
    load_dotenv()


def cdp_configured() -> bool:
    load_cdp_env()
    env = CdpEnv.from_env()
    has_kerberos = bool(os.environ.get("KERBEROS_KEYTAB") or os.environ.get("KERBEROS_PRINCIPAL"))
    has_spark = bool(os.environ.get("CDP_SPARK_MASTER"))
    return env.is_configured() and has_spark and (has_kerberos or os.environ.get("CDP_SKIP_KERBEROS") == "true")


def ensure_kerberos_ticket() -> None:
    """Obtain Kerberos ticket via kinit when keytab is configured."""
    load_cdp_env()
    if os.environ.get("CDP_SKIP_KERBEROS") == "true":
        return

    principal = os.environ.get("KERBEROS_PRINCIPAL") or os.environ.get("SPARK_YARN_PRINCIPAL")
    keytab = os.environ.get("KERBEROS_KEYTAB") or os.environ.get("SPARK_YARN_KEYTAB")
    if not principal or not keytab:
        return

    subprocess.run(
        ["kinit", "-kt", keytab, principal],
        check=True,
        capture_output=True,
        text=True,
    )


def apply_autotls_java_opts() -> None:
    """Set JAVA_TOOL_OPTIONS for Auto-TLS truststore if configured."""
    truststore = os.environ.get("TRUSTSTORE_PATH")
    if not truststore:
        return

    password = os.environ.get("TRUSTSTORE_PASSWORD", "changeit")
    store_type = os.environ.get("TRUSTSTORE_TYPE", "JKS")
    opts = (
        f"-Djavax.net.ssl.trustStore={truststore} "
        f"-Djavax.net.ssl.trustStorePassword={password} "
        f"-Djavax.net.ssl.trustStoreType={store_type}"
    )
    existing = os.environ.get("JAVA_TOOL_OPTIONS", "")
    if truststore not in existing:
        os.environ["JAVA_TOOL_OPTIONS"] = f"{existing} {opts}".strip()


def spark_configs_from_env() -> dict[str, str]:
    load_cdp_env()
    configs: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("SPARK_CONF_"):
            spark_key = key.removeprefix("SPARK_CONF_").replace("_", ".")
            configs[spark_key] = value
    return configs


def kerberos_spark_configs() -> dict[str, str]:
    load_cdp_env()
    if os.environ.get("CDP_SKIP_KERBEROS") == "true":
        return {}

    principal = os.environ.get("SPARK_YARN_PRINCIPAL") or os.environ.get("KERBEROS_PRINCIPAL")
    keytab = os.environ.get("SPARK_YARN_KEYTAB") or os.environ.get("KERBEROS_KEYTAB")
    if not principal or not keytab:
        return {}

    return {
        "spark.kerberos.principal": principal,
        "spark.kerberos.keytab": keytab,
        "spark.yarn.principal": principal,
        "spark.yarn.keytab": keytab,
    }


def build_spark_session() -> Any:
    from pyspark.sql import SparkSession

    load_cdp_env()
    ensure_kerberos_ticket()
    apply_autotls_java_opts()

    master = os.environ.get("CDP_SPARK_MASTER", "local[*]")
    builder = SparkSession.builder.master(master).appName("guide-validator-cdp")

    queue = os.environ.get("SPARK_QUEUE")
    if queue:
        builder = builder.config("spark.yarn.queue", queue)

    all_configs = {**kerberos_spark_configs(), **spark_configs_from_env()}
    for key, value in all_configs.items():
        builder = builder.config(key, value)

    defaults = {
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    }
    for key, value in defaults.items():
        if key not in all_configs:
            builder = builder.config(key, value)

    catalog = os.environ.get("ICEBERG_CATALOG", "spark_catalog")
    catalog_defaults = {
        f"spark.sql.catalog.{catalog}": "org.apache.iceberg.spark.SparkCatalog",
        f"spark.sql.catalog.{catalog}.type": "hive",
    }
    for key, value in catalog_defaults.items():
        if key not in all_configs:
            builder = builder.config(key, value)

    return builder.getOrCreate()
