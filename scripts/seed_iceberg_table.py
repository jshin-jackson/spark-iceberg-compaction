#!/usr/bin/env python3.11
"""Seed a CDP Iceberg test table so every guide compaction scenario is reproducible.

The script builds an Iceberg format-v2, merge-on-read, partitioned table and then
deliberately creates the "bad" states the maintenance guide fixes:

  * many small data files in one partition  -> rewrite_data_files (guide sec. 3)
  * position delete files (DELETE/UPDATE)    -> rewrite_position_delete_files (sec. 4)
  * many manifests / snapshots               -> rewrite_manifests / expire_snapshots (sec. 5-6)
  * metadata JSON accumulation               -> metadata TBLPROPERTIES (sec. 7)

Data is generated with plain Spark expressions (no external dependency). Values are
shaped to look like SBI (bank) transaction events.

Usage:
    python3.11 scripts/seed_iceberg_table.py
    python3.11 scripts/seed_iceberg_table.py --batches 30 --rows-per-batch 20000
    python3.11 scripts/seed_iceberg_table.py --recreate
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from guide_validator.cdp_spark import build_spark_session, load_cdp_env

DEFAULT_BUSINESS_DATE = "2026-07-21"


def resolve_target() -> tuple[str, str, str]:
    load_cdp_env()
    catalog = os.environ.get("ICEBERG_CATALOG", "spark_catalog")
    database = os.environ.get("TARGET_DATABASE") or os.environ.get("TEST_DATABASE", "")
    table = os.environ.get("TARGET_TABLE") or os.environ.get("TEST_TABLE", "")
    if not database or not table:
        print(
            "ERROR: set TARGET_DATABASE/TARGET_TABLE (or TEST_DATABASE/TEST_TABLE) in .env",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return catalog, database, table


def resolve_business_date() -> str:
    explicit = os.environ.get("SEED_BUSINESS_DATE")
    if explicit:
        return explicit
    partition_filter = os.environ.get("PARTITION_FILTER") or os.environ.get(
        "TEST_PARTITION_FILTER", ""
    )
    match = re.search(r"DATE\s*'?(\d{4}-\d{2}-\d{2})'?", partition_filter)
    if match:
        return match.group(1)
    return DEFAULT_BUSINESS_DATE


def create_table(spark, full_table: str, database: str, recreate: bool) -> None:
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {database}")
    if recreate:
        spark.sql(f"DROP TABLE IF EXISTS {full_table}")
    spark.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {full_table} (
          txn_id            STRING,
          account_id        STRING,
          branch_code       STRING,
          txn_type          STRING,
          amount            DECIMAL(18,2),
          currency          STRING,
          channel           STRING,
          status            STRING,
          customer_segment  STRING,
          txn_ts            TIMESTAMP,
          business_date     DATE
        )
        USING iceberg
        PARTITIONED BY (business_date)
        TBLPROPERTIES (
          'format-version'               = '2',
          'write.delete.mode'            = 'merge-on-read',
          'write.update.mode'            = 'merge-on-read',
          'write.merge.mode'             = 'merge-on-read',
          'write.target-file-size-bytes' = '536870912'
        )
        """
    )


def build_batch(spark, rows: int, business_date: str, seed_offset: int):
    """Generate one batch of synthetic transaction rows via Spark expressions."""
    from pyspark.sql import functions as F

    df = spark.range(0, rows).withColumn("r", (F.col("id") + F.lit(seed_offset * rows)))
    df = (
        df.withColumn("txn_id", F.concat(F.lit("T"), F.format_string("%012d", F.col("r"))))
        .withColumn("account_id", F.concat(F.lit("AC"), F.format_string("%08d", F.col("r") % 5000)))
        .withColumn("branch_code", F.concat(F.lit("BR"), F.format_string("%04d", F.col("r") % 250)))
        .withColumn(
            "txn_type",
            F.element_at(
                F.array(
                    F.lit("DEPOSIT"),
                    F.lit("WITHDRAWAL"),
                    F.lit("TRANSFER"),
                    F.lit("PAYMENT"),
                    F.lit("INTEREST"),
                ),
                (F.col("r") % 5 + 1).cast("int"),
            ),
        )
        .withColumn("amount", (F.rand(seed_offset) * F.lit(500000)).cast("decimal(18,2)"))
        .withColumn("currency", F.lit("INR"))
        .withColumn(
            "channel",
            F.element_at(
                F.array(
                    F.lit("ATM"),
                    F.lit("MOBILE"),
                    F.lit("BRANCH"),
                    F.lit("NET"),
                    F.lit("UPI"),
                ),
                (F.col("r") % 5 + 1).cast("int"),
            ),
        )
        .withColumn(
            "status",
            F.element_at(
                F.array(F.lit("SUCCESS"), F.lit("SUCCESS"), F.lit("SUCCESS"), F.lit("FAILED"), F.lit("PENDING")),
                (F.col("r") % 5 + 1).cast("int"),
            ),
        )
        .withColumn(
            "customer_segment",
            F.element_at(
                F.array(F.lit("RETAIL"), F.lit("SME"), F.lit("CORP")),
                (F.col("r") % 3 + 1).cast("int"),
            ),
        )
        .withColumn(
            "txn_ts",
            (F.unix_timestamp(F.lit(f"{business_date} 00:00:00")) + (F.col("r") % 86400)).cast(
                "timestamp"
            ),
        )
        .withColumn("business_date", F.to_date(F.lit(business_date)))
    )
    return df.select(
        "txn_id",
        "account_id",
        "branch_code",
        "txn_type",
        "amount",
        "currency",
        "channel",
        "status",
        "customer_segment",
        "txn_ts",
        "business_date",
    )


def seed(
    spark,
    full_table: str,
    business_date: str,
    batches: int,
    rows_per_batch: int,
) -> None:
    """Append many small batches so each commit produces small files + a snapshot."""
    for i in range(batches):
        batch = build_batch(spark, rows_per_batch, business_date, seed_offset=i)
        # repartition(1) forces one small file per batch to trigger min-input-files.
        batch.repartition(1).writeTo(full_table).append()
        print(f"  batch {i + 1}/{batches} appended ({rows_per_batch} rows)")


def create_position_deletes(spark, full_table: str, business_date: str) -> None:
    """Row-level DELETE/UPDATE under merge-on-read produce position delete files."""
    spark.sql(
        f"DELETE FROM {full_table} "
        f"WHERE business_date = DATE '{business_date}' AND status = 'FAILED'"
    )
    spark.sql(
        f"UPDATE {full_table} SET channel = 'MOBILE' "
        f"WHERE business_date = DATE '{business_date}' AND channel = 'NET'"
    )
    spark.sql(
        f"DELETE FROM {full_table} "
        f"WHERE business_date = DATE '{business_date}' AND status = 'PENDING'"
    )


def summarize(spark, full_table: str) -> None:
    from pyspark.sql import functions as F

    files = spark.sql(f"SELECT content, count(*) AS n FROM {full_table}.files GROUP BY content")
    snapshots = spark.sql(f"SELECT count(*) AS n FROM {full_table}.snapshots").collect()[0]["n"]
    manifests = spark.sql(f"SELECT count(*) AS n FROM {full_table}.manifests").collect()[0]["n"]
    total_rows = spark.sql(f"SELECT count(*) AS n FROM {full_table}").collect()[0]["n"]

    print("\n=== Seed summary ===")
    print(f"table         : {full_table}")
    print(f"logical rows  : {total_rows}")
    print(f"snapshots     : {snapshots}")
    print(f"manifests     : {manifests}")
    for row in files.collect():
        print(f"files[{row['content']}] : {row['n']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Iceberg test table for compaction scenarios")
    parser.add_argument("--batches", type=int, default=20, help="number of small append commits")
    parser.add_argument("--rows-per-batch", type=int, default=10000, help="rows per append batch")
    parser.add_argument(
        "--recreate", action="store_true", help="drop and recreate the table before seeding"
    )
    parser.add_argument(
        "--no-deletes",
        action="store_true",
        help="skip DELETE/UPDATE (no position delete files)",
    )
    args = parser.parse_args(argv)

    _catalog, database, table = resolve_target()
    full_table = f"{database}.{table}"
    business_date = resolve_business_date()

    spark = build_spark_session()
    print(f"Seeding {full_table} for business_date={business_date}")

    create_table(spark, full_table, database, recreate=args.recreate)
    seed(spark, full_table, business_date, args.batches, args.rows_per_batch)
    if not args.no_deletes:
        print("Creating position deletes (DELETE/UPDATE, merge-on-read)...")
        create_position_deletes(spark, full_table, business_date)

    summarize(spark, full_table)
    spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
