"""Iceberg table metrics SQL and step-wise change expectations."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class MetricsContext:
    full_table: str
    partition_filter: str = ""
    files_partition_predicate: str = ""

    @classmethod
    def from_env(cls) -> MetricsContext:
        database = os.environ.get("TARGET_DATABASE") or os.environ.get("TEST_DATABASE", "")
        table = os.environ.get("TARGET_TABLE") or os.environ.get("TEST_TABLE", "")
        full_table = f"{database}.{table}" if database and table else table
        partition_filter = os.environ.get("PARTITION_FILTER") or os.environ.get(
            "TEST_PARTITION_FILTER", ""
        )
        files_predicate = os.environ.get("FILES_PARTITION_PREDICATE", "")
        if not files_predicate and partition_filter:
            files_predicate = _partition_filter_to_files_predicate(partition_filter)
        return cls(
            full_table=full_table,
            partition_filter=partition_filter,
            files_partition_predicate=files_predicate,
        )


def _partition_filter_to_files_predicate(partition_filter: str) -> str:
    """Best-effort map table WHERE clause to files.partition struct predicate."""
    match = re.match(r"(\w+)\s*=\s*(.+)", partition_filter.strip(), re.IGNORECASE)
    if match:
        column, value = match.group(1), match.group(2).strip()
        return f"partition.{column} = {value}"
    return partition_filter


def _metric_select(name: str, sql: str, unit: str = "") -> str:
    return f"SELECT '{name}' AS metric, CAST(({sql}) AS STRING) AS value, '{unit}' AS unit"


def build_metrics_sql(ctx: MetricsContext) -> str:
    t = ctx.full_table
    parts: list[str] = []

    parts.append(_metric_select("logical_row_count_total", f"SELECT count(*) FROM {t}", "rows"))

    if ctx.partition_filter:
        parts.append(
            _metric_select(
                "logical_row_count_partition",
                f"SELECT count(*) FROM {t} WHERE {ctx.partition_filter}",
                "rows",
            )
        )

    parts.append(
        _metric_select(
            "data_file_count_total",
            f"SELECT count(*) FROM {t}.files WHERE content = 'DATA'",
            "files",
        )
    )
    parts.append(
        _metric_select(
            "data_file_bytes_total",
            f"SELECT coalesce(sum(file_size_in_bytes), 0) FROM {t}.files WHERE content = 'DATA'",
            "bytes",
        )
    )
    parts.append(
        _metric_select(
            "data_file_avg_size_total",
            f"SELECT coalesce(cast(avg(file_size_in_bytes) as bigint), 0) "
            f"FROM {t}.files WHERE content = 'DATA'",
            "bytes",
        )
    )

    if ctx.files_partition_predicate:
        pred = ctx.files_partition_predicate
        parts.append(
            _metric_select(
                "data_file_count_partition",
                f"SELECT count(*) FROM {t}.files WHERE content = 'DATA' AND {pred}",
                "files",
            )
        )
        parts.append(
            _metric_select(
                "data_file_bytes_partition",
                f"SELECT coalesce(sum(file_size_in_bytes), 0) FROM {t}.files "
                f"WHERE content = 'DATA' AND {pred}",
                "bytes",
            )
        )
        parts.append(
            _metric_select(
                "data_file_avg_size_partition",
                f"SELECT coalesce(cast(avg(file_size_in_bytes) as bigint), 0) "
                f"FROM {t}.files WHERE content = 'DATA' AND {pred}",
                "bytes",
            )
        )

    parts.append(
        _metric_select(
            "position_delete_file_count",
            f"SELECT count(*) FROM {t}.files WHERE content = 'POSITION_DELETES'",
            "files",
        )
    )
    parts.append(
        _metric_select(
            "position_delete_file_bytes",
            f"SELECT coalesce(sum(file_size_in_bytes), 0) FROM {t}.files "
            f"WHERE content = 'POSITION_DELETES'",
            "bytes",
        )
    )
    parts.append(
        _metric_select(
            "equality_delete_file_count",
            f"SELECT count(*) FROM {t}.files WHERE content = 'EQUALITY_DELETES'",
            "files",
        )
    )
    parts.append(
        _metric_select(
            "all_file_count_total",
            f"SELECT count(*) FROM {t}.files",
            "files",
        )
    )
    parts.append(
        _metric_select(
            "snapshot_count",
            f"SELECT count(*) FROM {t}.snapshots",
            "snapshots",
        )
    )
    parts.append(
        _metric_select(
            "manifest_count",
            f"SELECT count(*) FROM {t}.manifests",
            "manifests",
        )
    )
    parts.append(
        _metric_select(
            "latest_snapshot_id",
            f"SELECT coalesce(max(snapshot_id), 0) FROM {t}.snapshots",
            "id",
        )
    )
    parts.append(
        _metric_select(
            "history_entry_count",
            f"SELECT count(*) FROM {t}.history",
            "entries",
        )
    )

    return "\nUNION ALL\n".join(parts) + "\nORDER BY metric\n"


def build_history_sql(ctx: MetricsContext, limit: int = 5) -> str:
    return (
        f"SELECT made_current_at, snapshot_id, parent_id, summary "
        f"FROM {ctx.full_table}.history "
        f"ORDER BY made_current_at DESC LIMIT {limit}"
    )


def build_tblproperties_sql(ctx: MetricsContext) -> str:
    keys = (
        "format-version",
        "write.target-file-size-bytes",
        "write.metadata.delete-after-commit.enabled",
        "write.metadata.previous-versions-max",
    )
    quoted = ", ".join(f"'{k}'" for k in keys)
    return (
        f"SELECT key, value FROM {ctx.full_table} "
        f"WHERE key IN ({quoted}) OR key LIKE 'write.%' "
        f"ORDER BY key"
    )


# Expectation tokens used by metrics_compare
Expectation = str

STEP_EXPECTATIONS: dict[str, dict[str, Expectation]] = {
    "step1_baseline": {},
    "step2_rewrite_data_files": {
        "logical_row_count_total": "unchanged",
        "logical_row_count_partition": "unchanged",
        "data_file_count_partition": "decrease_or_equal",
        "data_file_avg_size_partition": "increase_or_equal",
        "data_file_bytes_total": "approx_unchanged",
        "data_file_bytes_partition": "approx_unchanged",
        "snapshot_count": "increase",
        "latest_snapshot_id": "increase",
    },
    "step3_rewrite_position_delete_files": {
        "logical_row_count_total": "unchanged",
        "position_delete_file_count": "decrease_or_equal",
        "position_delete_file_bytes": "decrease_or_equal",
        "snapshot_count": "increase",
        "latest_snapshot_id": "increase",
    },
    "step4_rewrite_manifests": {
        "logical_row_count_total": "unchanged",
        "manifest_count": "decrease_or_equal",
        "snapshot_count": "increase",
        "latest_snapshot_id": "increase",
    },
    "step5_expire_snapshots": {
        "logical_row_count_total": "unchanged",
        "snapshot_count": "decrease_or_equal",
        "all_file_count_total": "decrease_or_equal",
        "data_file_bytes_total": "decrease_or_equal",
    },
    "step6_metadata_properties": {
        "logical_row_count_total": "unchanged",
    },
    "step7_orphan_dry_run": {
        "logical_row_count_total": "unchanged",
        "all_file_count_total": "unchanged",
        "data_file_count_total": "unchanged",
    },
    "step7_orphan_delete": {
        "logical_row_count_total": "unchanged",
    },
}

STEP_LABELS: dict[str, str] = {
    "step0_baseline": "0. Baseline (maintenance run 시작)",
    "step1_baseline": "1. 사전 점검 baseline",
    "step2_rewrite_data_files": "2. rewrite_data_files",
    "step3_rewrite_position_delete_files": "3. rewrite_position_delete_files",
    "step4_rewrite_manifests": "4. rewrite_manifests",
    "step5_expire_snapshots": "5. expire_snapshots",
    "step6_metadata_properties": "6. metadata TBLPROPERTIES",
    "step7_orphan_dry_run": "7a. remove_orphan_files (dry-run)",
    "step7_orphan_delete": "7b. remove_orphan_files (delete)",
}
