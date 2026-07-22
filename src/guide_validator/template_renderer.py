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
        database = os.environ.get("TEST_DATABASE", "")
        table = os.environ.get("TEST_TABLE", "")
        partition_filter = os.environ.get(
            "TEST_PARTITION_FILTER",
            "business_date = DATE '2026-07-21'",
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


def render_sql(sql: str, env: CdpEnv) -> str:
    rendered = sql
    rendered = rendered.replace("spark_catalog", env.catalog)
    rendered = rendered.replace("databases.table", env.full_table)
    rendered = re.sub(
        r"where\s*=>\s*'[^']*'",
        f"where => '{env.partition_filter}'",
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
          older_than => TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP),
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
          older_than => TIMESTAMPADD(DAY, -30, CURRENT_TIMESTAMP),
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
