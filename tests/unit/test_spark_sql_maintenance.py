import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "spark_sql_maintenance",
    ROOT / "scripts" / "spark_sql_maintenance.py",
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
split_statements = _mod.split_statements
result_row_limit = _mod.result_row_limit


def test_split_statements_multiple():
    sql = """
USE spark_catalog;
SELECT count(*) FROM iceberg_compaction_test.txn_events;
"""
    assert split_statements(sql) == [
        "USE spark_catalog",
        "SELECT count(*) FROM iceberg_compaction_test.txn_events",
    ]


def test_split_statements_skips_empty_and_comment_only():
    sql = "SELECT 1;;\n-- comment only\n;\nSELECT 2;"
    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]


def test_result_row_limit_describe_and_show():
    assert result_row_limit("DESCRIBE TABLE EXTENDED db.t") == 1000
    assert result_row_limit("SHOW TBLPROPERTIES db.t") == 1000
    assert result_row_limit("SELECT 1") == 20
