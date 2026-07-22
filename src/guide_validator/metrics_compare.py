"""Compare Iceberg maintenance metrics snapshots and validate expected changes."""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from guide_validator.verification_queries import STEP_EXPECTATIONS, STEP_LABELS


@dataclass
class MetricRow:
    metric: str
    value: str
    unit: str = ""


@dataclass
class ComparisonResult:
    step: str
    before_label: str
    after_label: str
    rows: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def load_metrics(path: Path) -> dict[str, MetricRow]:
    metrics: dict[str, MetricRow] = {}
    with path.open(encoding="utf-8") as handle:
        if path.suffix == ".json":
            data = json.load(handle)
            for name, payload in data.get("metrics", data).items():
                if isinstance(payload, dict):
                    metrics[name] = MetricRow(name, str(payload.get("value", "")), payload.get("unit", ""))
                else:
                    metrics[name] = MetricRow(name, str(payload))
            return metrics

        reader = csv.DictReader(handle)
        for row in reader:
            name = row.get("metric", "").strip()
            if name:
                metrics[name] = MetricRow(name, row.get("value", "").strip(), row.get("unit", "").strip())
    return metrics


def _to_number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_expectation(
    expectation: str,
    before: float | None,
    after: float | None,
    metric: str,
    tolerance_pct: float,
) -> tuple[bool, str]:
    if before is None or after is None:
        return True, "non-numeric (skipped)"

    delta = after - before

    if expectation == "unchanged":
        ok = delta == 0
        return ok, f"{before} → {after} (Δ {delta:+})"

    if expectation == "increase":
        ok = after > before
        return ok, f"{before} → {after} (Δ {delta:+})"

    if expectation == "decrease":
        ok = after < before
        return ok, f"{before} → {after} (Δ {delta:+})"

    if expectation == "increase_or_equal":
        ok = after >= before
        return ok, f"{before} → {after} (Δ {delta:+})"

    if expectation == "decrease_or_equal":
        ok = after <= before
        return ok, f"{before} → {after} (Δ {delta:+})"

    if expectation == "approx_unchanged":
        if before == 0:
            ok = after == 0
        else:
            pct = abs(delta) / before * 100
            ok = pct <= tolerance_pct
        return ok, f"{before} → {after} (Δ {delta:+}, tol {tolerance_pct}%)"

    return True, f"{before} → {after} (unknown expectation {expectation})"


def compare_metrics(
    before: dict[str, MetricRow],
    after: dict[str, MetricRow],
    step: str,
    *,
    before_label: str = "before",
    after_label: str = "after",
    tolerance_pct: float = 1.0,
) -> ComparisonResult:
    expectations = STEP_EXPECTATIONS.get(step, {})
    all_keys = sorted(set(before) | set(after))
    result = ComparisonResult(step=step, before_label=before_label, after_label=after_label)

    for metric in all_keys:
        b = before.get(metric)
        a = after.get(metric)
        b_val = _to_number(b.value if b else "")
        a_val = _to_number(a.value if a else "")
        delta = None if b_val is None or a_val is None else a_val - b_val

        expectation = expectations.get(metric, "report")
        if expectation == "report":
            status = "INFO"
            detail = f"{b.value if b else '—'} → {a.value if a else '—'}"
        else:
            ok, detail = _check_expectation(expectation, b_val, a_val, metric, tolerance_pct)
            status = "PASS" if ok else "FAIL"
            if not ok:
                result.failures.append(f"{metric}: expected {expectation}, got {detail}")

        result.rows.append(
            {
                "metric": metric,
                "unit": (a or b).unit if (a or b) else "",
                "before": b.value if b else "",
                "after": a.value if a else "",
                "delta": f"{delta:+}" if delta is not None else "",
                "expectation": expectation,
                "status": status,
                "detail": detail,
            }
        )

    for metric, expectation in expectations.items():
        if metric not in all_keys:
            result.warnings.append(f"Expected metric '{metric}' missing from capture")

    return result


def format_comparison_text(result: ComparisonResult) -> str:
    title = STEP_LABELS.get(result.step, result.step)
    lines = [
        f"Metrics comparison: {title}",
        f"Before: {result.before_label}",
        f"After:  {result.after_label}",
        "",
        f"{'Metric':<32} {'Before':>14} {'After':>14} {'Delta':>10} {'Expect':<18} {'Status'}",
        "-" * 100,
    ]
    for row in result.rows:
        lines.append(
            f"{row['metric']:<32} {row['before']:>14} {row['after']:>14} "
            f"{row['delta']:>10} {row['expectation']:<18} {row['status']}"
        )

    if result.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"  - {w}" for w in result.warnings)

    if result.failures:
        lines.extend(["", "Failures:"])
        lines.extend(f"  - {f}" for f in result.failures)

    lines.append("")
    lines.append("RESULT: PASSED" if result.passed else "RESULT: FAILED")
    return "\n".join(lines)


def format_comparison_json(result: ComparisonResult) -> str:
    return json.dumps(
        {
            "step": result.step,
            "step_label": STEP_LABELS.get(result.step, result.step),
            "passed": result.passed,
            "before_label": result.before_label,
            "after_label": result.after_label,
            "rows": result.rows,
            "failures": result.failures,
            "warnings": result.warnings,
        },
        indent=2,
        ensure_ascii=False,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compare Iceberg maintenance metric snapshots")
    parser.add_argument("before", type=Path, help="Metrics file before step (CSV or JSON)")
    parser.add_argument("after", type=Path, help="Metrics file after step (CSV or JSON)")
    parser.add_argument(
        "--step",
        required=True,
        choices=sorted(STEP_EXPECTATIONS.keys()),
        help="Maintenance step id for expectation validation",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=1.0,
        help="Percent tolerance for approx_unchanged byte metrics",
    )
    args = parser.parse_args(argv)

    before = load_metrics(args.before)
    after = load_metrics(args.after)
    result = compare_metrics(
        before,
        after,
        args.step,
        before_label=str(args.before),
        after_label=str(args.after),
        tolerance_pct=args.tolerance_pct,
    )

    output = format_comparison_json(result) if args.format == "json" else format_comparison_text(result)
    print(output)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
