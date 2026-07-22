"""Parse HTML guide structure and extract content blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag


@dataclass
class CodeBlock:
    section: str
    sql: str
    index: int


@dataclass
class ReferenceLink:
    area: str
    url: str
    usage: str


@dataclass
class ParsedGuide:
    title: str
    meta: dict[str, str]
    sections: list[str] = field(default_factory=list)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    reference_links: list[ReferenceLink] = field(default_factory=list)
    checklist_items: list[str] = field(default_factory=list)
    body_text: str = ""


def _section_title(tag: Tag) -> str:
    return tag.get_text(strip=True)


def _meta_from_header(header: Tag) -> dict[str, str]:
    meta: dict[str, str] = {}
    meta_div = header.find("div", class_="meta")
    if not meta_div:
        return meta
    for span in meta_div.find_all("span"):
        text = span.get_text(strip=True)
        if ":" in text:
            key, value = text.split(":", 1)
            meta[key.strip()] = value.strip()
        else:
            meta[text] = text
    return meta


def parse_guide(html_path: Path) -> ParsedGuide:
    content = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "lxml")

    header = soup.find("header")
    main = soup.find("main")
    if main is None:
        raise ValueError(f"No <main> element found in {html_path}")

    title = soup.find("h1")
    parsed = ParsedGuide(
        title=title.get_text(strip=True) if title else "",
        meta=_meta_from_header(header) if header else {},
        body_text=main.get_text("\n", strip=True),
    )

    current_section = "preamble"
    code_index = 0

    for element in main.children:
        if not isinstance(element, Tag):
            continue
        if element.name == "h2":
            current_section = _section_title(element)
            parsed.sections.append(current_section)
        elif element.name == "pre":
            code_tag = element.find("code")
            if code_tag:
                sql = code_tag.get_text()
                parsed.code_blocks.append(
                    CodeBlock(section=current_section, sql=sql, index=code_index)
                )
                code_index += 1
        elif element.name == "ol" and ("체크리스트" in current_section or "checklist" in current_section.lower()):
            parsed.checklist_items = [li.get_text(strip=True) for li in element.find_all("li")]
        elif element.name == "table" and "Reference" in current_section:
            rows = element.find_all("tr")
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                area = cells[0].get_text(strip=True)
                link = cells[1].find("a")
                usage = cells[2].get_text(strip=True)
                if link and link.get("href"):
                    parsed.reference_links.append(
                        ReferenceLink(area=area, url=link["href"], usage=usage)
                    )

    return parsed
