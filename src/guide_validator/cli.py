"""CLI entry point for guide validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from guide_validator.validator import validate_guide

DEFAULT_GUIDE = (
    Path(__file__).resolve().parents[2]
    / "guide"
    / "SBI_Iceberg_Compaction_Maintenance_Guide_reviewed.html"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate SBI Iceberg Compaction & Maintenance Operational Guide"
    )
    parser.add_argument(
        "--guide",
        type=Path,
        default=DEFAULT_GUIDE,
        help="Path to the HTML guide",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--skip-links",
        action="store_true",
        help="Skip reference URL checks (offline/CI)",
    )
    parser.add_argument(
        "--link-timeout",
        type=float,
        default=10.0,
        help="HTTP timeout for link checks (seconds)",
    )

    args = parser.parse_args(argv)

    if not args.guide.exists():
        print(f"Guide not found: {args.guide}", file=sys.stderr)
        return 2

    report = validate_guide(
        args.guide,
        check_links=not args.skip_links,
        link_timeout=args.link_timeout,
    )

    output = report.to_json() if args.format == "json" else report.to_text()
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
