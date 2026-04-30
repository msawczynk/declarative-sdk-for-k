#!/usr/bin/env python3
"""Report Commander command coverage by DSK plan/apply/validate paths.

The extractor is intentionally offline. It reads committed docs/snapshots and
the CommanderCliProvider source; it never imports or runs Keeper Commander.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDER_DOC = REPO_ROOT / "docs" / "COMMANDER.md"
SNAPSHOT_PATH = REPO_ROOT / "docs" / "capability-snapshot.json"
PROVIDER_PATH = REPO_ROOT / "keeper_sdk" / "providers" / "commander_cli.py"

COMMAND_ROOTS = frozenset(
    {
        "enterprise-down",
        "enterprise-info",
        "enterprise-node",
        "enterprise-role",
        "enterprise-team",
        "enterprise-user",
        "get",
        "list-sf",
        "login",
        "mkdir",
        "msp-add",
        "msp-remove",
        "msp-update",
        "mv",
        "password-report",
        "record-add",
        "record-update",
        "rm",
        "rmdir",
        "rndir",
        "search",
        "security-audit-report",
        "share-folder",
        "share-record",
        "sync-down",
        "ls",
    }
)
CLASS_COMMANDS = {
    "PAMConfigurationListCommand": "pam config list",
    "PAMCreateRecordRotationCommand": "pam rotation edit",
    "PAMGatewayListCommand": "pam gateway list",
    "PAMListRecordRotationCommand": "pam rotation list",
    "PAMProjectExtendCommand": "pam project extend",
    "PAMProjectImportCommand": "pam project import",
    "PAMRbiEditCommand": "pam rbi edit",
    "RecordAddCommand": "record-add",
}
VERB_HINTS = {
    "get": "validate --online / plan / apply",
    "ls": "validate --online / plan / apply",
    "mkdir": "apply",
    "mv": "apply",
    "pam config list": "validate --online / plan",
    "pam connection edit": "apply",
    "pam gateway list": "validate --online / plan",
    "pam project extend": "apply",
    "pam project import": "apply",
    "pam rbi edit": "apply",
    "pam rotation edit": "apply",
    "pam rotation list": "validate --online / plan",
    "record-add": "apply",
    "rm": "apply --allow-delete",
    "rmdir": "apply --allow-delete",
    "secrets-manager app list": "validate --online / plan",
    "secrets-manager share add": "apply",
    "share-folder": "apply",
    "share-record": "apply",
}
NOTES = {
    "login": "interactive Commander login is deliberately not a DSK plan/apply/validate path",
    "msp-add": "listed as future MSP write hook; CommanderCliProvider apply still fails closed",
    "msp-remove": "listed as future MSP write hook; CommanderCliProvider apply still fails closed",
    "msp-update": "listed as future MSP write hook; CommanderCliProvider apply still fails closed",
    "pam project destroy": "not registered in the pinned Commander matrix",
    "pam project export": "not registered in Commander 17.2.16; dsk export reads JSON files",
    "pam project remove": "not registered in the pinned Commander matrix",
    "record-update": "not called as a Commander command; DSK uses in-process RecordEditCommand",
    "sync-down": "interactive sync is not used as a DSK plan/apply/validate command",
}


@dataclass
class CommandInfo:
    command: str
    sources: set[str] = field(default_factory=set)


def _split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    cells = _split_md_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _iter_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index < len(lines) - 1:
        if "|" not in lines[index] or not _is_table_sep(lines[index + 1]):
            index += 1
            continue
        headers = _split_md_row(lines[index])
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index] and lines[index].strip().startswith("|"):
            row = _split_md_row(lines[index])
            if len(row) == len(headers):
                rows.append(row)
            index += 1
        tables.append((headers, rows))
    return tables


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("**", "").replace("`", "").strip()


def _normalize_command_text(raw: str) -> str | None:
    text = _strip_markdown(raw)
    text = text.replace("keeper ", "", 1) if text.startswith("keeper ") else text
    text = text.strip(" .,:;()")
    if not text or text.lower() in {"none", "n/a"}:
        return None
    tokens = text.split()
    if not tokens:
        return None
    if tokens[0] in {"python3", "keepercommander"}:
        return None
    if tokens[0] == "pam":
        if len(tokens) >= 3 and (tokens[2].startswith("-") or "/" in tokens[2]):
            return None
        if len(tokens) >= 3:
            return " ".join(tokens[:3])
        return " ".join(tokens[:2]) if len(tokens) >= 2 else None
    if tokens[0] == "secrets-manager":
        if len(tokens) >= 3 and tokens[2].startswith("-"):
            return None
        if len(tokens) >= 3:
            return " ".join(tokens[:3])
        return " ".join(tokens[:2]) if len(tokens) >= 2 else None
    if tokens[0] in {"automator", "scim", "trash"}:
        return " ".join(tokens[:2]) if len(tokens) >= 2 else None
    if tokens[0] in COMMAND_ROOTS:
        return tokens[0]
    return None


def _command_candidates(raw: str) -> list[str]:
    backticks = re.findall(r"`([^`]+)`", raw)
    chunks = backticks or [raw]
    commands: list[str] = []
    base_prefix: str | None = None
    for chunk in chunks:
        subchunks = [part.strip() for part in chunk.split(" / ")] if " / " in chunk else [chunk]
        for subchunk in subchunks:
            compact_slash = re.fullmatch(r"(.+\s)([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", subchunk)
            if compact_slash:
                prefix, left, right = compact_slash.groups()
                subcommands = [prefix + left, prefix + right]
            else:
                subcommands = [subchunk]
            for subcommand in subcommands:
                command = _normalize_command_text(subcommand)
                if (
                    command is None
                    and base_prefix in {"pam project", "pam rbi"}
                    and subcommand in {"destroy", "edit", "extend", "import", "remove"}
                ):
                    command = _normalize_command_text(f"{base_prefix} {subcommand}")
                if command is None:
                    continue
                parts = command.split()
                if len(parts) > 1:
                    base_prefix = " ".join(parts[:-1])
                commands.append(command)
    return commands


def _add_command(commands: dict[str, CommandInfo], raw: str, source: str) -> None:
    for command in _command_candidates(raw):
        commands.setdefault(command, CommandInfo(command)).sources.add(source)


def _commands_from_commander_doc(path: Path) -> dict[str, CommandInfo]:
    commands: dict[str, CommandInfo] = {}
    text = path.read_text(encoding="utf-8")
    for headers, rows in _iter_markdown_tables(text):
        lowered = [header.casefold() for header in headers]
        for row in rows:
            if lowered[0] == "command":
                _add_command(commands, row[0], f"{path.name}:table")
            if "commander surface" in lowered:
                idx = lowered.index("commander surface")
                _add_command(commands, row[idx], f"{path.name}:table")
            if "commander command / hook" in lowered:
                idx = lowered.index("commander command / hook")
                _add_command(commands, row[idx], f"{path.name}:table")
            if "group" in lowered and "subcommand" in lowered:
                group = row[lowered.index("group")]
                subcommand = row[lowered.index("subcommand")]
                _add_command(commands, f"{group} {subcommand}", f"{path.name}:table")
    for match in re.finditer(r"`([^`]+)`", text):
        _add_command(commands, match.group(0), f"{path.name}:backtick")
    return commands


def _commands_from_snapshot(path: Path) -> dict[str, CommandInfo]:
    commands: dict[str, CommandInfo] = {}
    if not path.exists():
        return commands
    data = json.loads(path.read_text(encoding="utf-8"))
    for row in data.get("commands", []):
        _add_command(commands, str(row.get("group_command", "")), path.name)
    for group in data.get("groups", []):
        group_name = str(group.get("group", ""))
        for row in group.get("subcommands", []):
            _add_command(commands, f"{group_name} {row.get('name', '')}", path.name)
    return commands


def _merge_commands(*sets: dict[str, CommandInfo]) -> dict[str, CommandInfo]:
    merged: dict[str, CommandInfo] = {}
    for command_set in sets:
        for command, info in command_set.items():
            merged.setdefault(command, CommandInfo(command)).sources.update(info.sources)
    return dict(sorted(merged.items()))


def _literal_command_from_node(node: ast.AST) -> str | None:
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    tokens: list[str] = []
    for item in node.elts:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            tokens.append(item.value)
            continue
        if tokens:
            tokens.append("<arg>")
        break
    return _normalize_command_text(" ".join(tokens))


def _provider_command_uses(path: Path) -> dict[str, set[str]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    uses: dict[str, set[str]] = {}

    def add(command: str | None, source: str) -> None:
        if command is not None:
            uses.setdefault(command, set()).add(source)

    for node in ast.walk(tree):
        add(_literal_command_from_node(node), f"{path.name}:{getattr(node, 'lineno', '?')}")
    for class_name, command in CLASS_COMMANDS.items():
        for match in re.finditer(rf"\b{re.escape(class_name)}\b", text):
            line = text.count("\n", 0, match.start()) + 1
            add(command, f"{path.name}:{line}")
    uses.pop("record-update", None)
    return uses


def _entry(command: str, uses: dict[str, set[str]]) -> dict[str, Any]:
    covered = command in uses and command != "record-update"
    if covered:
        use_lines = ", ".join(sorted(uses[command])[:3])
        notes = f"seen in CommanderCliProvider ({use_lines})"
    else:
        notes = NOTES.get(command, "no plan/apply/validate call found in CommanderCliProvider")
    if command.startswith(("automator ", "scim ", "trash ")):
        notes = "mirrored Commander surface; no DSK lifecycle coverage"
    return {
        "command": command,
        "covered_by_dsk": covered,
        "dsk_verb": VERB_HINTS.get(command, "plan/apply/validate" if covered else ""),
        "notes": notes,
    }


def _render_markdown(entries: list[dict[str, Any]]) -> str:
    total = len(entries)
    covered = sum(1 for entry in entries if entry["covered_by_dsk"])
    pct = (covered / total * 100) if total else 0.0
    not_covered = [entry for entry in entries if not entry["covered_by_dsk"]]
    lines = [
        "# Commander Coverage",
        "",
        "Generated by `python3 scripts/coverage/commander_coverage.py`.",
        "",
        "Source: `docs/COMMANDER.md` plus committed `docs/capability-snapshot.json` "
        "when present. No Keeper Commander process is invoked.",
        "",
        "| total commands | covered | coverage | not covered |",
        "|---:|---:|---:|---:|",
        f"| {total} | {covered} | {pct:.1f}% | {len(not_covered)} |",
        "",
        "## Not Covered",
        "",
        "| command | notes |",
        "|---|---|",
    ]
    for entry in not_covered:
        lines.append(f"| `{entry['command']}` | {entry['notes']} |")
    lines.extend(
        [
            "",
            "## JSON",
            "",
            "```json",
            json.dumps(entries, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_report() -> str:
    commands = _merge_commands(
        _commands_from_commander_doc(COMMANDER_DOC),
        _commands_from_snapshot(SNAPSHOT_PATH),
    )
    uses = _provider_command_uses(PROVIDER_PATH)
    entries = [_entry(command, uses) for command in commands]
    return _render_markdown(entries)


def main() -> int:
    try:
        print(build_report())
    except Exception as exc:  # pragma: no cover - informational script must not fail CI.
        payload = [{"command": "", "covered_by_dsk": False, "dsk_verb": "", "notes": str(exc)}]
        print("# Commander Coverage")
        print()
        print(f"Extractor warning: {type(exc).__name__}: {exc}")
        print()
        print("```json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
