"""Extract and parse SQL statements from guide code blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CALL_PATTERN = re.compile(
    r"CALL\s+(?P<catalog>[\w.]+)\.system\.(?P<procedure>[\w_]+)\s*\(",
    re.IGNORECASE | re.DOTALL,
)
ALTER_PATTERN = re.compile(
    r"ALTER\s+TABLE\s+[\w.]+\s+SET\s+TBLPROPERTIES\s*\(",
    re.IGNORECASE | re.DOTALL,
)
NAMED_ARG_PATTERN = re.compile(
    r"(?P<name>[\w.]+)\s*=>\s*(?P<value>.+?)(?=,\s*[\w.]+\s*=>|\s*\)\s*;|\s*\)\s*$)",
    re.DOTALL,
)
MAP_PATTERN = re.compile(r"map\s*\((.+)\)", re.IGNORECASE | re.DOTALL)
PROPERTY_PATTERN = re.compile(
    r"'(?P<key>[^']+)'\s*=\s*'(?P<value>[^']*)'",
)


@dataclass
class ProcedureCall:
    catalog: str
    procedure: str
    raw_sql: str
    section: str
    index: int
    named_args: dict[str, str] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    is_comment_only: bool = False


@dataclass
class AlterTableProperties:
    raw_sql: str
    section: str
    index: int
    properties: dict[str, str] = field(default_factory=dict)


def _strip_comments(sql: str) -> tuple[str, bool]:
    lines = []
    has_only_comments = True
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("--"):
            continue
        has_only_comments = False
        lines.append(line)
    return "\n".join(lines).strip(), has_only_comments and bool(sql.strip())


def _parse_named_args(call_body: str) -> dict[str, str]:
    args: dict[str, str] = {}
    for match in NAMED_ARG_PATTERN.finditer(call_body):
        name = match.group("name").strip()
        value = match.group("value").strip().rstrip(",").strip()
        args[name] = value
    return args


def _parse_map_options(value: str) -> dict[str, str]:
    map_match = MAP_PATTERN.search(value)
    if not map_match:
        return {}
    inner = map_match.group(1)
    options: dict[str, str] = {}
    for part in re.findall(r"'([^']+)'\s*,\s*'([^']*)'", inner):
        options[part[0]] = part[1]
    return options


def extract_sql_statements(section: str, sql: str, index: int) -> list[ProcedureCall | AlterTableProperties]:
    cleaned, comment_only = _strip_comments(sql)
    results: list[ProcedureCall | AlterTableProperties] = []

    if not cleaned:
        return results

    for stmt in re.split(r";\s*\n", cleaned):
        stmt = stmt.strip()
        if not stmt:
            continue
        if not stmt.endswith(";"):
            stmt += ";"

        call_match = CALL_PATTERN.search(stmt)
        if call_match:
            call_body_start = call_match.end() - 1
            call_body = stmt[call_body_start:]
            named_args = _parse_named_args(call_body)
            options = {}
            if "options" in named_args:
                options = _parse_map_options(named_args["options"])

            results.append(
                ProcedureCall(
                    catalog=call_match.group("catalog"),
                    procedure=call_match.group("procedure"),
                    raw_sql=stmt,
                    section=section,
                    index=index,
                    named_args=named_args,
                    options=options,
                    is_comment_only=comment_only,
                )
            )
            continue

        if ALTER_PATTERN.search(stmt):
            properties = {
                match.group("key"): match.group("value")
                for match in PROPERTY_PATTERN.finditer(stmt)
            }
            results.append(
                AlterTableProperties(
                    raw_sql=stmt,
                    section=section,
                    index=index,
                    properties=properties,
                )
            )

    return results


def extract_all_from_blocks(code_blocks: list) -> tuple[list[ProcedureCall], list[AlterTableProperties]]:
    calls: list[ProcedureCall] = []
    alters: list[AlterTableProperties] = []
    for block in code_blocks:
        for item in extract_sql_statements(block.section, block.sql, block.index):
            if isinstance(item, ProcedureCall):
                calls.append(item)
            else:
                alters.append(item)
    return calls, alters
