"""Unit tests for template renderer."""

from guide_validator.template_renderer import CdpEnv, render_sql, rewrite_data_files_sql


def test_render_sql_substitutes_catalog_and_table():
    env = CdpEnv(
        catalog="hive_catalog",
        database="maintenance",
        table="test_iceberg",
        partition_filter="dt = DATE '2026-01-01'",
        allow_destructive=False,
    )
    sql = "CALL spark_catalog.system.rewrite_data_files(table => 'databases.table');"
    rendered = render_sql(sql, env)
    assert "hive_catalog" in rendered
    assert "maintenance.test_iceberg" in rendered


def test_rewrite_data_files_template_includes_partition_filter():
    env = CdpEnv(
        catalog="spark_catalog",
        database="db",
        table="tbl",
        partition_filter="p = 1",
        allow_destructive=False,
    )
    sql = rewrite_data_files_sql(env)
    assert "p = 1" in sql
    assert "db.tbl" in sql


def test_rewrite_data_files_escapes_quotes_in_partition_filter():
    env = CdpEnv(
        catalog="spark_catalog",
        database="db",
        table="tbl",
        partition_filter="business_date = DATE '2026-07-21'",
        allow_destructive=False,
    )
    sql = rewrite_data_files_sql(env)
    assert "where => 'business_date = DATE ''2026-07-21'''" in sql
    assert "'''2026" not in sql


def test_remove_orphan_files_uses_interval_not_timestampadd():
    from guide_validator.template_renderer import remove_orphan_files_dry_run_sql

    env = CdpEnv(
        catalog="spark_catalog",
        database="db",
        table="tbl",
        partition_filter="p = 1",
        allow_destructive=False,
    )
    sql = remove_orphan_files_dry_run_sql(env)
    assert "interval 7 days" in sql
    assert "TIMESTAMPADD" not in sql
