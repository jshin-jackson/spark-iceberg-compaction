"""Check reference URLs in the guide."""

from __future__ import annotations

import httpx

from guide_validator.html_parser import ReferenceLink
from guide_validator.report import Severity, ValidationReport


def check_reference_links(links: list[ReferenceLink], guide_path: str, timeout: float = 10.0) -> ValidationReport:
    report = ValidationReport(guide_path=guide_path)

    if not links:
        report.add(
            Severity.WARNING,
            "links",
            "No reference links found in guide",
        )
        return report

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        for link in links:
            try:
                response = client.head(link.url)
                if response.status_code >= 400:
                    response = client.get(link.url)
                if response.status_code >= 400:
                    report.add(
                        Severity.ERROR,
                        "links",
                        f"Reference URL returned HTTP {response.status_code}: {link.url}",
                        section=link.area,
                    )
                else:
                    report.add(
                        Severity.INFO,
                        "links",
                        f"OK ({response.status_code}): {link.url}",
                        section=link.area,
                    )
            except httpx.RequestError as exc:
                report.add(
                    Severity.ERROR,
                    "links",
                    f"Failed to reach {link.url}: {exc}",
                    section=link.area,
                )

    return report
