"""Unit tests for verification SQL generation."""

from guide_validator.verification_queries import MetricsContext, build_metrics_sql


def test_build_metrics_sql_includes_core_metrics():
    ctx = MetricsContext(
        full_table="db.events",
        partition_filter="business_date = DATE '2026-07-21'",
        files_partition_predicate="partition.business_date = DATE '2026-07-21'",
    )
    sql = build_metrics_sql(ctx)
    assert "logical_row_count_total" in sql
    assert "logical_row_count_partition" in sql
    assert "data_file_count_partition" in sql
    assert "position_delete_file_count" in sql
    assert "snapshot_count" in sql
    assert "db.events" in sql


def test_build_metrics_sql_without_partition_omits_partition_metrics():
    ctx = MetricsContext(full_table="db.events")
    sql = build_metrics_sql(ctx)
    assert "logical_row_count_partition" not in sql
    assert "data_file_count_partition" not in sql
