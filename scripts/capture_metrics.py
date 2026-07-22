#!/usr/bin/env python3
"""Capture Iceberg table metrics to CSV/JSON for step-wise verification."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from guide_validator.verification_queries import MetricsContext, build_metrics_sql


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value", "unit"])
        writer.writeheader()
        writer.writerows(rows)


def write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def capture_with_spark(ctx: MetricsContext) -> list[dict[str, str]]:
    from guide_validator.cdp_spark import build_spark_session

    spark = build_spark_session()
    sql = build_metrics_sql(ctx)
    df = spark.sql(sql)
    return [row.asDict() for row in df.collect()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Iceberg maintenance metrics")
    parser.add_argument(
        "label",
        help="Snapshot label (e.g. step2_pre, step2_post)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: metrics/$MAINTENANCE_RUN_ID)",
    )
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print metrics SQL and exit (for spark-sql -f)",
    )
    args = parser.parse_args(argv)

    ctx = MetricsContext.from_env()
    if not ctx.full_table or "." not in ctx.full_table:
        print("ERROR: set TARGET_DATABASE and TARGET_TABLE (or TEST_*) in .env", file=sys.stderr)
        return 2

    sql = build_metrics_sql(ctx)
    if args.print_sql:
        print(sql)
        return 0

    run_id = __import__("os").environ.get("MAINTENANCE_RUN_ID") or datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )
    out_dir = args.output_dir or Path("metrics") / run_id
    ext = args.format
    out_path = out_dir / f"{args.label}.{ext}"

    rows = capture_with_spark(ctx)
    captured_at = datetime.now(timezone.utc).isoformat()

    if args.format == "csv":
        write_csv(rows, out_path)
    else:
        write_json(
            {
                "label": args.label,
                "captured_at": captured_at,
                "full_table": ctx.full_table,
                "partition_filter": ctx.partition_filter,
                "metrics": {r["metric"]: {"value": r["value"], "unit": r["unit"]} for r in rows},
            },
            out_path,
        )

    print(f"Captured {len(rows)} metrics → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
