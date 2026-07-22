"""Validate operational policy consistency in the guide."""

from __future__ import annotations

import re

from guide_validator.html_parser import ParsedGuide
from guide_validator.report import Severity, ValidationReport
from guide_validator.spec_loader import load_procedure_spec
from guide_validator.sql_extractor import ProcedureCall


def validate_policies(
    guide: ParsedGuide,
    calls: list[ProcedureCall],
    guide_path: str,
) -> ValidationReport:
    report = ValidationReport(guide_path=guide_path)
    spec = load_procedure_spec()
    body = guide.body_text

    version_checks = [
        ("Spark 3.5.4", r"Spark\s+3\.5\.4"),
        ("Iceberg 1.5.2", r"Iceberg\s+1\.5\.2"),
        ("CDP 7.3.1.600", r"7\.3\.1\.600"),
    ]
    for label, pattern in version_checks:
        if not re.search(pattern, body):
            report.add(
                Severity.ERROR,
                "policy",
                f"Version baseline '{label}' not found consistently in guide",
            )

    flow_procedures = spec.get("execution_order", [])
    flow_section = next((s for s in guide.sections if "실행 순서" in s or "execution" in s.lower()), "")
    if flow_section:
        for proc in flow_procedures:
            if proc not in body:
                report.add(
                    Severity.ERROR,
                    "policy",
                    f"Execution order section missing procedure '{proc}'",
                    section=flow_section,
                )

    table_scope = set(spec.get("table_scope_procedures", []))
    for call in calls:
        if call.procedure in table_scope and "where" in call.named_args:
            report.add(
                Severity.ERROR,
                "policy",
                f"Table-scope procedure '{call.procedure}' example uses 'where' "
                f"(contradicts guide policy)",
                section=call.section,
            )

    if "rewrite_position_delete_files" in body and "where" in body:
        pos_delete_calls = [c for c in calls if c.procedure == "rewrite_position_delete_files"]
        for call in pos_delete_calls:
            if "where" in call.raw_sql.lower():
                report.add(
                    Severity.ERROR,
                    "policy",
                    "rewrite_position_delete_files example must not include where clause",
                    section=call.section,
                )

    checklist_section = next((s for s in guide.sections if "체크리스트" in s or "checklist" in s.lower()), "")
    if checklist_section:
        if len(guide.checklist_items) < 5:
            report.add(
                Severity.WARNING,
                "policy",
                f"Deployment checklist may be incomplete (found {len(guide.checklist_items)} items)",
                section=checklist_section,
            )

        keywords = ["catalog", "Ranger", "partition", "dry-run", "YARN"]
        checklist_text = " ".join(guide.checklist_items).lower()
        for kw in keywords:
            normalized = kw.lower().replace("-", "")
            if kw.lower() not in checklist_text and normalized not in checklist_text:
                report.add(
                    Severity.WARNING,
                    "policy",
                    f"Checklist may be missing keyword related to '{kw}'",
                    section=checklist_section,
                )

    if "partial-progress.enabled" in body and "'false'" not in body and "false" not in body:
        report.add(
            Severity.WARNING,
            "policy",
            "Guide should document partial-progress.enabled=false as default/recommendation",
        )

    if "512 MB" not in body and "536870912" not in body:
        report.add(
            Severity.WARNING,
            "policy",
            "Guide should reference 512 MB target file size baseline",
        )

    return report
