"""Validation result types and report formatting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    severity: Severity
    category: str
    message: str
    section: str = ""
    context: str = ""


@dataclass
class ValidationReport:
    guide_path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def add(self, severity: Severity, category: str, message: str, **kwargs: str) -> None:
        self.findings.append(Finding(severity=severity, category=category, message=message, **kwargs))

    def merge(self, other: ValidationReport) -> None:
        self.findings.extend(other.findings)

    def to_text(self) -> str:
        lines = [
            f"Guide validation: {self.guide_path}",
            f"Findings: {len(self.findings)} total "
            f"({len(self.errors)} errors, {len(self.warnings)} warnings)",
            "",
        ]
        if self.passed and not self.warnings:
            lines.append("PASSED - no issues found.")
            return "\n".join(lines)

        for finding in self.findings:
            prefix = finding.severity.value.upper()
            location = f" [{finding.section}]" if finding.section else ""
            lines.append(f"{prefix}{location}: {finding.message}")
            if finding.context:
                lines.append(f"  context: {finding.context[:200]}")
        lines.append("")
        lines.append("RESULT: PASSED" if self.passed else "RESULT: FAILED")
        return "\n".join(lines)

    def to_json(self) -> str:
        payload = {
            "guide_path": self.guide_path,
            "passed": self.passed,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [asdict(f) for f in self.findings],
        }
        for item in payload["findings"]:
            item["severity"] = item["severity"].value if hasattr(item["severity"], "value") else item["severity"]
        return json.dumps(payload, indent=2, ensure_ascii=False)
