#!/usr/bin/env python3.11
"""Run Spark SQL on CDP via PySpark when spark-sql CLI is unavailable.

Uses the same Kerberos, Auto-TLS, Iceberg, and HDFS HA settings as seed/pytest
(build_spark_session). Output format matches spark-sql enough for capture_metrics.sh.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    for part in sql.split(";"):
        stmt = part.strip()
        if not stmt:
            continue
        if all(not line.strip() or line.strip().startswith("--") for line in stmt.splitlines()):
            continue
        statements.append(stmt)
    return statements


def result_row_limit(sql: str) -> int:
    """PySpark show() defaults to 20 rows; DESCRIBE/SHOW often need more."""
    normalized = " ".join(sql.strip().upper().split())
    if normalized.startswith(("DESCRIBE", "DESC ", "SHOW ", "EXPLAIN")):
        return 1000
    return 20


def run_statement(spark, sql: str) -> None:
    df = spark.sql(sql)
    if df.columns:
        df.show(result_row_limit(sql), truncate=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spark SQL via PySpark (CDP maintenance)")
    parser.add_argument("-e", "--execute", dest="execute", help="SQL statement")
    parser.add_argument("-f", "--file", dest="file", help="SQL file path")
    args = parser.parse_args(argv)

    if args.execute:
        statements = split_statements(args.execute)
    elif args.file:
        statements = split_statements(Path(args.file).read_text(encoding="utf-8"))
    else:
        statements = split_statements(sys.stdin.read())

    if not statements:
        print("ERROR: no SQL to execute", file=sys.stderr)
        return 2

    from guide_validator.cdp_spark import build_spark_session

    spark = build_spark_session()
    try:
        for stmt in statements:
            run_statement(spark, stmt)
    finally:
        spark.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
