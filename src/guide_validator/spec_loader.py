"""Load YAML specification files bundled with the project."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SPEC_DIR = Path(__file__).resolve().parents[2] / "spec"


@lru_cache
def load_procedure_spec() -> dict[str, Any]:
    path = SPEC_DIR / "iceberg-1.5.2-procedures.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache
def load_table_properties_spec() -> dict[str, Any]:
    path = SPEC_DIR / "table-properties.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
