"""Unit tests for metrics comparison."""

from guide_validator.metrics_compare import MetricRow, compare_metrics, load_metrics


def test_compare_rewrite_data_files_passes_typical_compaction(tmp_path):
    before = {
        "logical_row_count_total": MetricRow("logical_row_count_total", "1000000", "rows"),
        "logical_row_count_partition": MetricRow("logical_row_count_partition", "50000", "rows"),
        "data_file_count_partition": MetricRow("data_file_count_partition", "120", "files"),
        "data_file_avg_size_partition": MetricRow("data_file_avg_size_partition", "64000000", "bytes"),
        "data_file_bytes_total": MetricRow("data_file_bytes_total", "8000000000", "bytes"),
        "data_file_bytes_partition": MetricRow("data_file_bytes_partition", "400000000", "bytes"),
        "snapshot_count": MetricRow("snapshot_count", "45", "snapshots"),
        "latest_snapshot_id": MetricRow("latest_snapshot_id", "990", "id"),
    }
    after = {
        "logical_row_count_total": MetricRow("logical_row_count_total", "1000000", "rows"),
        "logical_row_count_partition": MetricRow("logical_row_count_partition", "50000", "rows"),
        "data_file_count_partition": MetricRow("data_file_count_partition", "18", "files"),
        "data_file_avg_size_partition": MetricRow("data_file_avg_size_partition", "420000000", "bytes"),
        "data_file_bytes_total": MetricRow("data_file_bytes_total", "8010000000", "bytes"),
        "data_file_bytes_partition": MetricRow("data_file_bytes_partition", "401000000", "bytes"),
        "snapshot_count": MetricRow("snapshot_count", "46", "snapshots"),
        "latest_snapshot_id": MetricRow("latest_snapshot_id", "991", "id"),
    }
    result = compare_metrics(before, after, "step2_rewrite_data_files")
    assert result.passed, result.failures


def test_compare_expire_snapshots_detects_snapshot_decrease(tmp_path):
    before = {
        "logical_row_count_total": MetricRow("logical_row_count_total", "1000000", "rows"),
        "snapshot_count": MetricRow("snapshot_count", "50", "snapshots"),
        "all_file_count_total": MetricRow("all_file_count_total", "200", "files"),
        "data_file_bytes_total": MetricRow("data_file_bytes_total", "8000000000", "bytes"),
    }
    after = {
        "logical_row_count_total": MetricRow("logical_row_count_total", "1000000", "rows"),
        "snapshot_count": MetricRow("snapshot_count", "25", "snapshots"),
        "all_file_count_total": MetricRow("all_file_count_total", "180", "files"),
        "data_file_bytes_total": MetricRow("data_file_bytes_total", "7900000000", "bytes"),
    }
    result = compare_metrics(before, after, "step5_expire_snapshots")
    assert result.passed


def test_compare_fails_when_row_count_changes_unexpectedly():
    before = {"logical_row_count_total": MetricRow("logical_row_count_total", "100", "rows")}
    after = {"logical_row_count_total": MetricRow("logical_row_count_total", "99", "rows")}
    result = compare_metrics(before, after, "step2_rewrite_data_files")
    assert not result.passed


def test_load_metrics_csv(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text("metric,value,unit\nsnapshot_count,10,snapshots\n", encoding="utf-8")
    metrics = load_metrics(path)
    assert metrics["snapshot_count"].value == "10"
