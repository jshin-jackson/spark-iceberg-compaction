#!/usr/bin/env python3
"""Inject unreferenced (orphan) files into an Iceberg table's data location.

Iceberg only tracks files listed in its manifests. Any extra physical file that
sits under the table's data directory but is not referenced by metadata is an
"orphan" that ``remove_orphan_files`` (guide sec. 8) is meant to clean up.

This script places such files and, by default, backdates their modification time
so the guide's real ``older_than => -7 days`` value catches them.

Usage:
    python scripts/inject_orphan_files.py
    python scripts/inject_orphan_files.py --count 3 --age-days 10
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from guide_validator.cdp_spark import build_spark_session


def resolve_target() -> str:
    database = os.environ.get("TARGET_DATABASE") or os.environ.get("TEST_DATABASE", "")
    table = os.environ.get("TARGET_TABLE") or os.environ.get("TEST_TABLE", "")
    if not database or not table:
        print(
            "ERROR: set TARGET_DATABASE/TARGET_TABLE (or TEST_DATABASE/TEST_TABLE) in .env",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return f"{database}.{table}"


def data_dir_from_files(spark, full_table: str) -> str:
    """Derive the table data directory from an existing tracked data file path."""
    rows = spark.sql(
        f"SELECT file_path FROM {full_table}.files WHERE content = 'DATA' LIMIT 1"
    ).collect()
    if not rows:
        print(
            "ERROR: table has no data files yet; run seed_iceberg_table.py first",
            file=sys.stderr,
        )
        raise SystemExit(2)
    file_path = rows[0]["file_path"]
    return file_path.rsplit("/", 1)[0]


def inject(spark, data_dir: str, count: int, age_days: int) -> list[str]:
    """Write orphan parquet files into data_dir via the Hadoop FileSystem API."""
    jvm = spark._jvm
    hadoop_conf = spark._jsc.hadoopConfiguration()
    Path = jvm.org.apache.hadoop.fs.Path
    FileSystem = jvm.org.apache.hadoop.fs.FileSystem

    fs = FileSystem.get(Path(data_dir).toUri(), hadoop_conf)

    staging = f"{data_dir}/_orphan_staging_{uuid.uuid4().hex}"
    spark.range(0, 100).toDF("id").coalesce(1).write.mode("overwrite").parquet(staging)

    staged_parts = [
        f.getPath()
        for f in fs.listStatus(Path(staging))
        if f.getPath().getName().endswith(".parquet")
    ]

    now_ms = jvm.java.lang.System.currentTimeMillis()
    old_ms = now_ms - age_days * 24 * 60 * 60 * 1000

    created: list[str] = []
    for i in range(count):
        src = staged_parts[i % len(staged_parts)]
        dest = Path(f"{data_dir}/orphan-{uuid.uuid4().hex}.parquet")
        # copy (not rename) so we can reuse the single staged part for N orphans
        jvm.org.apache.hadoop.fs.FileUtil.copy(fs, src, fs, dest, False, True, hadoop_conf)
        fs.setTimes(dest, old_ms, old_ms)
        created.append(dest.toString())

    fs.delete(Path(staging), True)
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inject orphan files for remove_orphan_files test")
    parser.add_argument("--count", type=int, default=3, help="number of orphan files to create")
    parser.add_argument(
        "--age-days",
        type=int,
        default=10,
        help="backdate file mtime by this many days (default 10 > guide's 7)",
    )
    args = parser.parse_args(argv)

    full_table = resolve_target()
    spark = build_spark_session()

    data_dir = data_dir_from_files(spark, full_table)
    print(f"Injecting {args.count} orphan file(s) into {data_dir} (aged {args.age_days}d)")
    created = inject(spark, data_dir, args.count, args.age_days)
    for path in created:
        print(f"  orphan -> {path}")

    spark.stop()
    print(
        "\nRun the dry-run to confirm detection:\n"
        "  ./scripts/run_step_with_verify.sh step7_orphan_dry_run run"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
