"""Validate Iceberg procedure CALL statements against spec."""

from __future__ import annotations

from guide_validator.report import Severity, ValidationReport
from guide_validator.spec_loader import load_procedure_spec
from guide_validator.sql_extractor import ProcedureCall


def validate_procedures(calls: list[ProcedureCall], guide_path: str) -> ValidationReport:
    report = ValidationReport(guide_path=guide_path)
    spec = load_procedure_spec()
    procedures = spec.get("procedures", {})
    expected_order = spec.get("execution_order", [])

    seen_procedures: set[str] = set()

    for call in calls:
        proc_spec = procedures.get(call.procedure)
        if proc_spec is None:
            report.add(
                Severity.ERROR,
                "procedure",
                f"Unknown procedure '{call.procedure}' (not in Iceberg 1.5.2 spec)",
                section=call.section,
                context=call.raw_sql[:120],
            )
            continue

        seen_procedures.add(call.procedure)

        allowed = set(proc_spec.get("required_args", [])) | set(proc_spec.get("optional_args", []))
        forbidden = set(proc_spec.get("forbidden_args", []))

        for arg_name in call.named_args:
            if arg_name in forbidden:
                report.add(
                    Severity.ERROR,
                    "procedure",
                    f"Procedure '{call.procedure}' must not use argument '{arg_name}' "
                    f"(Iceberg 1.5.2)",
                    section=call.section,
                    context=call.raw_sql[:120],
                )
            elif arg_name not in allowed and arg_name != "options":
                report.add(
                    Severity.ERROR,
                    "procedure",
                    f"Unknown argument '{arg_name}' for procedure '{call.procedure}'",
                    section=call.section,
                    context=call.raw_sql[:120],
                )

        if "table" not in call.named_args and "table" in proc_spec.get("required_args", []):
            report.add(
                Severity.ERROR,
                "procedure",
                f"Missing required 'table' argument for '{call.procedure}'",
                section=call.section,
            )

        valid_options = set(proc_spec.get("option_keys", []))
        for opt_key in call.options:
            if opt_key not in valid_options:
                report.add(
                    Severity.ERROR,
                    "procedure",
                    f"Unknown option '{opt_key}' for '{call.procedure}'",
                    section=call.section,
                    context=str(call.options),
                )

        defaults = proc_spec.get("defaults", {})
        for opt_key, opt_value in call.options.items():
            if opt_key in defaults and opt_value != defaults[opt_key]:
                report.add(
                    Severity.INFO,
                    "procedure",
                    f"Option '{opt_key}'={opt_value!r} overrides Iceberg default {defaults[opt_key]!r}",
                    section=call.section,
                )

        if proc_spec.get("table_scope") and "where" in call.named_args:
            report.add(
                Severity.ERROR,
                "procedure",
                f"Table-scope procedure '{call.procedure}' must not use 'where' in examples",
                section=call.section,
            )

    for proc_name in expected_order:
        if proc_name not in seen_procedures:
            report.add(
                Severity.WARNING,
                "procedure",
                f"Expected procedure '{proc_name}' not found in guide code examples",
            )

    orphan_dry = [
        c
        for c in calls
        if c.procedure == "remove_orphan_files"
        and c.named_args.get("dry_run", "").strip().strip("'").lower() == "true"
    ]
    orphan_live = [c for c in calls if c.procedure == "remove_orphan_files" and "dry_run" not in c.named_args]
    if not orphan_dry:
        report.add(
            Severity.WARNING,
            "procedure",
            "Guide should include remove_orphan_files dry_run=true example (§8 step 1)",
        )
    if not orphan_live:
        report.add(
            Severity.WARNING,
            "procedure",
            "Guide should include remove_orphan_files live delete example (§8 step 2)",
        )

    return report
