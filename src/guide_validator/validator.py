"""Orchestrate all static validations for the guide."""

from __future__ import annotations

from pathlib import Path

from guide_validator.html_parser import parse_guide
from guide_validator.link_checker import check_reference_links
from guide_validator.policy_validator import validate_policies
from guide_validator.procedure_validator import validate_procedures
from guide_validator.properties_validator import validate_table_properties
from guide_validator.report import ValidationReport
from guide_validator.sql_extractor import extract_all_from_blocks


def validate_guide(
    guide_path: Path,
    *,
    check_links: bool = True,
    link_timeout: float = 10.0,
) -> ValidationReport:
    guide_path = guide_path.resolve()
    parsed = parse_guide(guide_path)
    calls, alters = extract_all_from_blocks(parsed.code_blocks)

    report = ValidationReport(guide_path=str(guide_path))

    report.merge(validate_procedures(calls, str(guide_path)))
    report.merge(validate_table_properties(alters, str(guide_path)))
    report.merge(validate_policies(parsed, calls, str(guide_path)))

    if check_links:
        report.merge(
            check_reference_links(parsed.reference_links, str(guide_path), timeout=link_timeout)
        )

    return report
