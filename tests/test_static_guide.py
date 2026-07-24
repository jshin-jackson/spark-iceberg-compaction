"""End-to-end static validation of the bundled guide."""

from pathlib import Path

import pytest

from guide_validator.validator import validate_guide

GUIDE = Path(__file__).resolve().parents[1] / "guide" / "index.html"


def test_static_guide_validation_passes_without_links():
    report = validate_guide(GUIDE, check_links=False)
    assert report.passed, report.to_text()


@pytest.mark.network
def test_static_guide_validation_with_links():
    report = validate_guide(GUIDE, check_links=True)
    assert report.passed, report.to_text()
