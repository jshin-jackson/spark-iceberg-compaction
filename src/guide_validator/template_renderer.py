"""Render guide SQL templates with CDP environment values."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class CdpEnv:
    catalog: str
    database: str
    table: str
    partition_filter: str
    allow_destructive: bool

    @classmethod
    def from_env(cls) -> CdpEnv:
        catalog = os.environ.get("ICEBERG_CATALOG", "spark_catalog")
        database = os.environ.get("TEST_DATABASE") or os.environ.get("TARGET_DATABASE", "")
        table = os.environ.get("TEST_TABLE") or os.environ.get("TARGET_TABLE", "")
        partition_filter = (
            os.environ.get("TEST_PARTITION_FILTER")
            or os.environ.get("PARTITION_FILTER")
            or "business_date = DATE '2026-07-21'"
        )
        allow_destructive = os.environ.get("CDP_ALLOW_DESTRUCTIVE", "false").lower() == "true"
        return cls(
            catalog=catalog,
            database=database,
            table=table,
            partition_filter=partition_filter,
            allow_destructive=allow_destructive,
        )

    @property
    def full_table(self) -> str:
        if self.database and self.table:
            return f"{self.database}.{self.table}"
        return self.table

    def is_configured(self) -> bool:
        return bool(self.database and self.table)


def _sql_string_literal(value: str) -> str:
    """Escape single quotes for embedding in a SQL single-quoted string."""
    return value.replace("'", "''")


def iceberg_partition_predicate(partition_filter: str) -> str:
    """Normalize partition filters for Spark ``rewrite_data_files`` ``where`` args.

    Iceberg 1.5.x resolves ``where`` via Spark's expression parser, so DATE columns
    need Spark ``DATE 'YYYY-MM-DD'`` syntax (not bare quoted strings).
    """
    stripped = partition_filter.strip()
    date_match = re.match(
        r"(\w+)\s*=\s*DATE\s+'(\d{4}-\d{2}-\d{2})'",
        stripped,
        re.IGNORECASE,
    )
    if date_match:
        return stripped
    string_date_match = re.match(
        r"(\w+)\s*=\s*'(\d{4}-\d{2}-\d{2})'",
        stripped,
    )
    if string_date_match:
        return f"{string_date_match.group(1)} = DATE '{string_date_match.group(2)}'"
    return stripped


def call_procedure_where(partition_filter: str) -> str:
    """Escaped ``where => '...'`` literal for Spark CALL procedures."""
    return _sql_string_literal(iceberg_partition_predicate(partition_filter))


def render_sql(sql: str, env: CdpEnv) -> str:
    rendered = sql
    rendered = rendered.replace("spark_catalog", env.catalog)
    rendered = rendered.replace("databases.table", env.full_table)
    predicate = iceberg_partition_predicate(env.partition_filter)
    escaped_filter = _sql_string_literal(predicate)
    rendered = re.sub(
        r"where\s*=>\s*'(?:[^']|'')*'",
        f"where => '{escaped_filter}'",
        rendered,
        flags=re.IGNORECASE,
    )
    return rendered


def rewrite_data_files_sql(env: CdpEnv) -> str:
    return render_sql(
        """
        CALL spark_catalog.system.rewrite_data_files(
          table => 'databases.table',
          strategy => 'binpack',
          where => 'business_date = DATE ''2026-07-21''',
          options => map(
            'target-file-size-bytes', '536870912',
            'min-input-files', '5',
            'max-concurrent-file-group-rewrites', '2',
            'max-file-group-size-bytes', '21474836480',
            'partial-progress.enabled', 'false'
          )
        )
        """.strip(),
        env,
    )


def rewrite_manifests_sql(env: CdpEnv) -> str:
    return render_sql(
        """
        CALL spark_catalog.system.rewrite_manifests(
          table => 'databases.table',
          use_caching => false
        )
        """.strip(),
        env,
    )


def remove_orphan_files_dry_run_sql(env: CdpEnv) -> str:
    return render_sql(
        """
        CALL spark_catalog.system.remove_orphan_files(
          table => 'databases.table',
          older_than => timestamp '2000-01-01 00:00:00',
          dry_run => true
        )
        """.strip(),
        env,
    )


def expire_snapshots_sql(env: CdpEnv) -> str:
    return render_sql(
        """
        CALL spark_catalog.system.expire_snapshots(
          table => 'databases.table',
          older_than => timestamp '2000-01-01 00:00:00',
          retain_last => 20,
          max_concurrent_deletes => 4
        )
        """.strip(),
        env,
    )


def rewrite_position_delete_files_sql(env: CdpEnv) -> str:
    return render_sql(
        """
        CALL spark_catalog.system.rewrite_position_delete_files(
          table => 'databases.table',
          options => map(
            'min-input-files', '2',
            'max-concurrent-file-group-rewrites', '2',
            'max-file-group-size-bytes', '21474836480'
          )
        )
        """.strip(),
        env,
    )
