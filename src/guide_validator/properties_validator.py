"""Validate ALTER TABLE TBLPROPERTIES statements."""

from __future__ import annotations

from guide_validator.report import Severity, ValidationReport
from guide_validator.spec_loader import load_table_properties_spec
from guide_validator.sql_extractor import AlterTableProperties


def validate_table_properties(alters: list[AlterTableProperties], guide_path: str) -> ValidationReport:
    report = ValidationReport(guide_path=guide_path)
    spec = load_table_properties_spec()
    known_keys = set(spec.get("properties", {}))
    metadata_pairs = set(spec.get("metadata_pairs", []))
    expected_compaction = set(spec.get("guide_expected_properties", {}).get("compaction", []))
    expected_metadata = set(spec.get("guide_expected_properties", {}).get("metadata_retention", []))

    found_compaction: set[str] = set()
    found_metadata: set[str] = set()

    for alter in alters:
        for key, value in alter.properties.items():
            if key not in known_keys:
                report.add(
                    Severity.WARNING,
                    "properties",
                    f"Property '{key}' not in known Iceberg 1.5.2 table properties spec",
                    section=alter.section,
                )

            prop_spec = spec.get("properties", {}).get(key, {})
            enum_values = prop_spec.get("enum")
            if enum_values and value not in enum_values:
                report.add(
                    Severity.ERROR,
                    "properties",
                    f"Invalid value '{value}' for property '{key}' (allowed: {enum_values})",
                    section=alter.section,
                )

            if key in expected_compaction:
                found_compaction.add(key)
            if key in expected_metadata:
                found_metadata.add(key)

        metadata_in_stmt = metadata_pairs & set(alter.properties)
        if metadata_in_stmt and metadata_in_stmt != metadata_pairs:
            missing = metadata_pairs - metadata_in_stmt
            report.add(
                Severity.ERROR,
                "properties",
                f"Metadata retention properties must appear together; missing: {sorted(missing)}",
                section=alter.section,
            )

    if expected_compaction - found_compaction:
        report.add(
            Severity.WARNING,
            "properties",
            f"Missing expected compaction properties: {sorted(expected_compaction - found_compaction)}",
        )

    if expected_metadata - found_metadata:
        report.add(
            Severity.ERROR,
            "properties",
            f"Missing metadata retention properties: {sorted(expected_metadata - found_metadata)}",
        )

    return report
