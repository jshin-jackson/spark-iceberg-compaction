"""Unit tests for SQL extractor."""

from guide_validator.sql_extractor import extract_sql_statements


REWRITE_DATA_FILES = """
CALL spark_catalog.system.rewrite_data_files(
  table => 'databases.table',
  strategy => 'binpack',
  where => 'business_date = DATE ''2026-07-21''',
  options => map(
    'target-file-size-bytes', '536870912',
    'min-input-files', '5',
    'partial-progress.enabled', 'false'
  )
);
"""

ALTER_PROPS = """
ALTER TABLE databases.table SET TBLPROPERTIES (
  'write.target-file-size-bytes' = '536870912'
);
"""


def test_extract_procedure_call():
    results = extract_sql_statements("compaction", REWRITE_DATA_FILES, 0)
    assert len(results) == 1
    call = results[0]
    assert call.procedure == "rewrite_data_files"
    assert call.named_args["strategy"] == "'binpack'"
    assert call.options["target-file-size-bytes"] == "536870912"
    assert call.options["partial-progress.enabled"] == "false"


def test_extract_alter_table_properties():
    results = extract_sql_statements("properties", ALTER_PROPS, 1)
    assert len(results) == 1
    alter = results[0]
    assert alter.properties["write.target-file-size-bytes"] == "536870912"


def test_extract_orphan_two_step():
    sql = """
-- 1단계
CALL spark_catalog.system.remove_orphan_files(
  table => 'databases.table',
  dry_run => true
);

-- 2단계
CALL spark_catalog.system.remove_orphan_files(
  table => 'databases.table'
);
"""
    results = extract_sql_statements("orphan", sql, 2)
    assert len(results) == 2
    assert results[0].named_args.get("dry_run") == "true"
    assert "dry_run" not in results[1].named_args
