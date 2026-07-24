"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

GUIDE_PATH = (
    Path(__file__).resolve().parents[1]
    / "guide"
    / "SBI_Iceberg_Compaction_Maintenance_Guide_final_EN.html"
)
