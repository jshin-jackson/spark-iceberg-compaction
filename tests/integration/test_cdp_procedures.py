"""CDP Spark integration tests for guide procedures (tiered by safety)."""

from __future__ import annotations

import pytest

from guide_validator.template_renderer import (
    CdpEnv,
    expire_snapshots_sql,
    remove_orphan_files_dry_run_sql,
    rewrite_data_files_sql,
    rewrite_manifests_sql,
    rewrite_position_delete_files_sql,
)

pytestmark = pytest.mark.cdp


def test_t1_spark_session_active(spark):
    assert spark.sparkContext.appName == "guide-validator-cdp"


def test_t2_show_tables_and_describe(spark, cdp_env: CdpEnv):
    spark.sql(f"USE {cdp_env.database}")
    tables = spark.sql("SHOW TABLES").collect()
    table_names = {row.tableName for row in tables}
    assert cdp_env.table in table_names

    describe = spark.sql(f"DESCRIBE EXTENDED {cdp_env.full_table}").collect()
    assert len(describe) > 0


def test_t2_iceberg_metadata_files(spark, cdp_env: CdpEnv):
    files = spark.sql(
        f"SELECT file_path, file_size_in_bytes FROM {cdp_env.full_table}.files LIMIT 5"
    ).collect()
    assert files is not None


def test_t3_remove_orphan_files_dry_run(spark, cdp_env: CdpEnv):
    sql = remove_orphan_files_dry_run_sql(cdp_env)
    result = spark.sql(sql).collect()
    assert result is not None


def test_t4_rewrite_manifests(spark, cdp_env: CdpEnv):
    sql = rewrite_manifests_sql(cdp_env)
    result = spark.sql(sql).collect()
    assert result is not None


def test_t5_rewrite_data_files_partition(spark, cdp_env: CdpEnv):
    sql = rewrite_data_files_sql(cdp_env)
    result = spark.sql(sql).collect()
    assert result is not None


@pytest.mark.destructive
def test_t6_expire_snapshots(spark, cdp_env: CdpEnv):
    if not cdp_env.allow_destructive:
        pytest.skip("Set CDP_ALLOW_DESTRUCTIVE=true to run expire_snapshots")
    sql = expire_snapshots_sql(cdp_env)
    result = spark.sql(sql).collect()
    assert result is not None


@pytest.mark.destructive
def test_t6_rewrite_position_delete_files(spark, cdp_env: CdpEnv):
    if not cdp_env.allow_destructive:
        pytest.skip("Set CDP_ALLOW_DESTRUCTIVE=true to run rewrite_position_delete_files")
    sql = rewrite_position_delete_files_sql(cdp_env)
    result = spark.sql(sql).collect()
    assert result is not None
