"""Unit tests for procedure validator."""

from pathlib import Path

from guide_validator.html_parser import parse_guide
from guide_validator.procedure_validator import validate_procedures
from guide_validator.sql_extractor import extract_all_from_blocks

GUIDE = Path(__file__).resolve().parents[2] / "guide" / "SBI_Iceberg_Compaction_Maintenance_Guide_reviewed.html"


def test_guide_procedures_pass_validation():
    parsed = parse_guide(GUIDE)
    calls, _ = extract_all_from_blocks(parsed.code_blocks)
    report = validate_procedures(calls, str(GUIDE))
    assert report.passed, report.to_text()


def test_invalid_procedure_is_flagged():
    from guide_validator.sql_extractor import ProcedureCall

    calls = [
        ProcedureCall(
            catalog="spark_catalog",
            procedure="nonexistent_proc",
            raw_sql="CALL spark_catalog.system.nonexistent_proc(table => 'db.t');",
            section="test",
            index=0,
            named_args={"table": "'db.t'"},
        )
    ]
    report = validate_procedures(calls, "test.html")
    assert not report.passed
    assert any("Unknown procedure" in f.message for f in report.errors)
