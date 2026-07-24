"""Unit tests for HTML parser."""

from pathlib import Path

from guide_validator.html_parser import parse_guide

GUIDE = Path(__file__).resolve().parents[2] / "guide" / "SBI_Iceberg_Compaction_Maintenance_Guide_final_EN.html"


def test_parse_guide_extracts_title_and_sections():
    parsed = parse_guide(GUIDE)
    assert "Iceberg Compaction" in parsed.title
    assert len(parsed.sections) >= 10
    assert any("rewrite_data_files" in s for s in parsed.sections)


def test_parse_guide_extracts_code_blocks():
    parsed = parse_guide(GUIDE)
    assert len(parsed.code_blocks) >= 6
    procedures = " ".join(block.sql for block in parsed.code_blocks)
    assert "rewrite_data_files" in procedures
    assert "expire_snapshots" in procedures


def test_parse_guide_extracts_reference_links():
    parsed = parse_guide(GUIDE)
    assert len(parsed.reference_links) >= 8
    urls = [link.url for link in parsed.reference_links]
    assert any("iceberg.apache.org" in url for url in urls)


def test_parse_guide_extracts_checklist():
    parsed = parse_guide(GUIDE)
    assert len(parsed.checklist_items) >= 7
