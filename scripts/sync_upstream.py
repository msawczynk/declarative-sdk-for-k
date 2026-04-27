"""Extract the Keeper Commander capability surface into pinned snapshots.

Reads a sibling ``Commander`` checkout and emits two artifacts under
``docs/``:

* ``CAPABILITY_MATRIX.md`` — human-readable, committed so reviewers see
  what the SDK is modelling against.
* ``capability-snapshot.json`` — stable machine-readable companion, used
  by ``--check`` (CI drift detector) and by downstream tooling.

The script is best-effort: any extraction step that fails logs a
``WARNING`` and is recorded in the output under ``## Extraction
warnings`` so the parent agent can spot-check manually. Only stdlib
imports are used so the script stays runnable even when the SDK's
optional dev deps are missing.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import importlib
import json
import logging
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

LOG = logging.getLogger("sync_upstream")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMANDER = REPO_ROOT.parent / "Commander"
DOCS_DIR = REPO_ROOT / "docs"
MATRIX_PATH = DOCS_DIR / "CAPABILITY_MATRIX.md"
SNAPSHOT_PATH = DOCS_DIR / "capability-snapshot.json"

# Enforcements we care about in the SDK's validate-stage-4 role check.
# All names starting with ``ALLOW_PAM`` plus this explicit allowlist.
_EXPLICIT_ENFORCEMENTS = frozenset(
    {
        "ALLOW_SECRETS_MANAGER",
        "ALLOW_PAM_ROTATION",
        "ALLOW_PAM_GATEWAY",
        "ALLOW_CONFIGURE_ROTATION_SETTINGS",
        "ALLOW_ROTATE_CREDENTIALS",
    }
)

# Resource types whose JSON shapes we extract from the Commander README.
_RESOURCE_TYPE_HINTS = (
    "pamMachine",
    "pamDatabase",
    "pamDirectory",
    "pamRemoteBrowser",
    "pamUser",
    "login",
)

# P18b — `keeper-vault` / `keeper-vault-sharing` / integrations-adjacent CLI
# surfaces (explicit registry; see docs/P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md).
_VAULT_FAMILY_COMMAND_LABELS: frozenset[str] = frozenset(
    {"get", "search", "record-add", "record-update", "list-sf", "ls"}
)


# ---------------------------------------------------------------------------
# Commander pin
# ---------------------------------------------------------------------------


def extract_commander_pin(commander_path: Path) -> dict[str, str]:
    """Return ``{"sha": <short>, "branch": <name>}`` for a checkout.

    Falls back to ``"unknown"`` on failure so the matrix still renders.
    """

    def _run(args: Sequence[str]) -> str:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=str(commander_path),
                check=True,
                capture_output=True,
                text=True,
            )
            return out.stdout.strip() or "unknown"
        except (OSError, subprocess.CalledProcessError) as exc:
            LOG.warning("git %s failed in %s: %s", " ".join(args), commander_path, exc)
            return "unknown"

    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        # Detached-HEAD (CI clones by SHA). Pick the first branch or
        # remote ref that points at this commit so the snapshot stays
        # stable across local vs CI runs. Fall back to ``detached``.
        pointed_at = _run(
            [
                "for-each-ref",
                "--points-at=HEAD",
                "--format=%(refname:short)",
                "refs/heads/",
                "refs/remotes/",
            ]
        )
        for candidate in pointed_at.splitlines():
            candidate = candidate.strip()
            if not candidate or candidate == "unknown":
                continue
            if candidate.startswith("origin/"):
                candidate = candidate[len("origin/") :]
            branch = candidate
            break
        else:
            branch = "detached"
    return {
        "sha": _run(["rev-parse", "--short", "HEAD"]),
        "branch": branch,
    }


# ---------------------------------------------------------------------------
# Argparse / command extraction
# ---------------------------------------------------------------------------


def _action_type_label(action: argparse.Action) -> str:
    """Human-friendly label for an argparse action's value type."""
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "flag"
    if isinstance(action, argparse._CountAction):
        return "count"
    if isinstance(action, argparse._AppendAction):
        inner = getattr(action.type, "__name__", None) or "str"
        return f"append[{inner}]"
    t = action.type
    if t is None:
        return "str"
    return getattr(t, "__name__", str(t))


def extract_argparse_flags(cls: type) -> list[dict[str, Any]]:
    """Return a sorted list of flag dicts for a Commander ``Command`` class.

    Instantiates the class (per the task spec) and falls back to the
    class-level ``parser`` attribute if instantiation raises. Positional
    arguments are included too — they show up with an empty ``name``
    rendered as the action's ``dest``.
    """
    parser: argparse.ArgumentParser | None = None
    try:
        instance = cls()
        parser = (
            getattr(instance, "parser", None) or getattr(instance, "get_parser", lambda: None)()
        )
    except Exception as exc:  # pragma: no cover - defensive
        LOG.warning("could not instantiate %s: %s", cls.__name__, exc)
    if parser is None:
        parser = getattr(cls, "parser", None)
    if parser is None:
        return []

    flags: list[dict[str, Any]] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        name = action.option_strings[0] if action.option_strings else f"<{action.dest}>"
        flags.append(
            {
                "name": name,
                "aliases": sorted(action.option_strings[1:]) if action.option_strings else [],
                "dest": action.dest,
                "required": bool(action.required),
                "type": _action_type_label(action),
                "help": (action.help or "").strip(),
            }
        )
    flags.sort(key=lambda f: f["name"])
    return flags


def extract_group_subcommands(group_cls: type) -> list[dict[str, str]]:
    """Enumerate subcommands registered on a ``GroupCommand`` subclass."""
    try:
        instance = group_cls()
    except Exception as exc:
        LOG.warning("could not instantiate group %s: %s", group_cls.__name__, exc)
        return []

    subcommands = (
        getattr(instance, "_commands", None) or getattr(instance, "subcommands", None) or {}
    )
    descriptions = (
        getattr(instance, "_command_info", None)
        or getattr(instance, "subcommand_descriptions", None)
        or {}
    )

    rows: list[dict[str, str]] = []
    for name, sub in sorted(subcommands.items()):
        rows.append(
            {
                "name": name,
                "class": type(sub).__name__,
                "module": type(sub).__module__,
                "help": str(descriptions.get(name, "")).strip(),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Enforcements
# ---------------------------------------------------------------------------


def extract_enforcements(constants_module: Any) -> list[dict[str, Any]]:
    """Filter the Commander enforcements list for PAM-relevant rows.

    Commander historically exposed ``_ENFORCEMENTS`` (list of tuples) and
    a derived ``ENFORCEMENTS`` dict. We try both so older Commander pins
    continue to work.
    """
    raw: Iterable[Any] | None = getattr(constants_module, "_ENFORCEMENTS", None)
    if raw is None:
        raw = getattr(constants_module, "ENFORCEMENTS", None)
    if raw is None:
        LOG.warning("constants module has no _ENFORCEMENTS/ENFORCEMENTS attribute")
        return []

    rows: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, tuple) or not entry:
            continue
        name = str(entry[0])
        if not (name.startswith("ALLOW_PAM") or name in _EXPLICIT_ENFORCEMENTS):
            continue
        rows.append(
            {
                "name": name,
                "id": entry[1] if len(entry) > 1 else None,
                "type": entry[2] if len(entry) > 2 else None,
                "category": entry[3] if len(entry) > 3 else None,
            }
        )
    rows.sort(key=lambda r: r["name"])
    return rows


# ---------------------------------------------------------------------------
# README record-type extraction
# ---------------------------------------------------------------------------


_DETAILS_RE = re.compile(
    r"<details[^>]*>\s*<summary[^>]*>(?P<summary>.*?)</summary>(?P<body>.*?)</details>",
    re.DOTALL | re.IGNORECASE,
)
_JSON_FENCE_RE = re.compile(r"```json\s*(?P<json>.*?)```", re.DOTALL)


def _collect_pam_settings_keys(record: dict[str, Any], bucket: dict[str, set[str]]) -> None:
    settings = record.get("pam_settings")
    if not isinstance(settings, dict):
        return
    for sub in ("options", "port_forward", "connection"):
        node = settings.get(sub)
        if isinstance(node, dict):
            bucket.setdefault(sub, set()).update(k for k in node if not k.startswith("_"))


def parse_readme_shapes(readme_text: str) -> dict[str, dict[str, Any]]:
    """Collect top-level and ``pam_settings.*`` keys per resource type.

    Returns ``{resource_type: {"top_level_keys": [...], "pam_settings":
    {"options": [...], "port_forward": [...], "connection": [...]}}}``.
    Malformed sections are skipped with a warning, never raised.
    """
    shapes: dict[str, dict[str, Any]] = {}
    working: dict[str, dict[str, set[str]]] = {}

    for match in _DETAILS_RE.finditer(readme_text):
        summary = match.group("summary").strip()
        body = match.group("body")

        resource_hint: str | None = None
        for hint in _RESOURCE_TYPE_HINTS:
            if hint.lower() in summary.lower():
                resource_hint = hint
                break
        if resource_hint is None:
            continue

        json_match = _JSON_FENCE_RE.search(body)
        if not json_match:
            LOG.warning("no json fence for summary %r", summary)
            continue

        raw_json = json_match.group("json")
        # README JSON blocks use tab indentation and occasionally
        # trail commas; normalise those but do NOT strip "//" since the
        # `otpauth://` literals contain real forward slashes.
        cleaned = raw_json.replace("\t", "    ")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            LOG.warning("could not parse json for summary %r: %s", summary, exc)
            continue

        if not isinstance(parsed, dict):
            LOG.warning("json for %r is not an object", summary)
            continue

        resource_type = str(parsed.get("type") or resource_hint)
        slot = working.setdefault(
            resource_type,
            {"top_level_keys": set(), "options": set(), "port_forward": set(), "connection": set()},
        )
        slot["top_level_keys"].update(k for k in parsed if not k.startswith("_"))
        sub_bucket: dict[str, set[str]] = {}
        _collect_pam_settings_keys(parsed, sub_bucket)
        for sub_name, sub_keys in sub_bucket.items():
            slot[sub_name].update(sub_keys)

    for resource_type, buckets in sorted(working.items()):
        shapes[resource_type] = {
            "top_level_keys": sorted(buckets["top_level_keys"]),
            "pam_settings": {
                "options": sorted(buckets["options"]),
                "port_forward": sorted(buckets["port_forward"]),
                "connection": sorted(buckets["connection"]),
            },
        }
    return shapes


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


# Order: module path, attribute name, display label used in the matrix.
_GROUPS: tuple[tuple[str, str, str], ...] = (
    (
        "keepercommander.commands.pam_import.commands",
        "PAMProjectCommand",
        "pam project",
    ),
    (
        "keepercommander.commands.tunnel_and_connections",
        "PAMRbiCommand",
        "pam rbi",
    ),
    # P18b — integrations (`keeper-integrations-*`) + vault trash lifecycle.
    (
        "keepercommander.commands.scim",
        "ScimCommand",
        "scim",
    ),
    (
        "keepercommander.commands.automator",
        "AutomatorCommand",
        "automator",
    ),
    (
        "keepercommander.commands.record",
        "TrashCommand",
        "trash",
    ),
)

_COMMAND_CLASSES: tuple[tuple[str, str, str], ...] = (
    (
        "keepercommander.commands.pam_import.edit",
        "PAMProjectImportCommand",
        "pam project import",
    ),
    (
        "keepercommander.commands.pam_import.extend",
        "PAMProjectExtendCommand",
        "pam project extend",
    ),
    (
        "keepercommander.commands.tunnel_and_connections",
        "PAMRbiEditCommand",
        "pam rbi edit",
    ),
    (
        "keepercommander.commands.tunnel_and_connections",
        "PAMConnectionEditCommand",
        "pam connection edit",
    ),
    # P18a — enterprise surface for keeper-enterprise.v1 (explicit registry; see
    # docs/P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md).
    (
        "keepercommander.commands.enterprise",
        "GetEnterpriseDataCommand",
        "enterprise-down",
    ),
    (
        "keepercommander.commands.enterprise",
        "EnterpriseInfoCommand",
        "enterprise-info",
    ),
    (
        "keepercommander.commands.enterprise",
        "EnterpriseNodeCommand",
        "enterprise-node",
    ),
    (
        "keepercommander.commands.enterprise",
        "EnterpriseUserCommand",
        "enterprise-user",
    ),
    (
        "keepercommander.commands.enterprise",
        "EnterpriseRoleCommand",
        "enterprise-role",
    ),
    (
        "keepercommander.commands.enterprise",
        "EnterpriseTeamCommand",
        "enterprise-team",
    ),
    # P18b — vault record + folder listing (keeper-vault / keeper-vault-sharing).
    (
        "keepercommander.commands.record",
        "RecordGetUidCommand",
        "get",
    ),
    (
        "keepercommander.commands.record",
        "SearchCommand",
        "search",
    ),
    (
        "keepercommander.commands.record_edit",
        "RecordAddCommand",
        "record-add",
    ),
    (
        "keepercommander.commands.record_edit",
        "RecordUpdateCommand",
        "record-update",
    ),
    (
        "keepercommander.commands.record",
        "RecordListSfCommand",
        "list-sf",
    ),
    (
        "keepercommander.commands.folder",
        "FolderListCommand",
        "ls",
    ),
)


def _import_commander(commander_path: Path) -> None:
    """Prepend the Commander checkout to ``sys.path`` so imports resolve."""
    commander_str = str(commander_path)
    if commander_str not in sys.path:
        sys.path.insert(0, commander_str)


def build_snapshot(commander_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Return ``(snapshot, warnings)`` for the given Commander checkout."""
    warnings: list[str] = []

    def _warn(msg: str) -> None:
        LOG.warning(msg)
        warnings.append(msg)

    pin = extract_commander_pin(commander_path)

    groups: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    enforcements: list[dict[str, Any]] = []
    record_types: dict[str, Any] = {}

    _import_commander(commander_path)

    for module_path, attr, label in _GROUPS:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, attr)
        except Exception as exc:
            _warn(f"could not import group {module_path}.{attr}: {exc}")
            continue
        groups.append(
            {"group": label, "class": attr, "subcommands": extract_group_subcommands(cls)}
        )

    for module_path, attr, label in _COMMAND_CLASSES:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, attr, None)
            if cls is None:
                _warn(f"command class not present in upstream: {module_path}.{attr}")
                continue
        except Exception as exc:
            _warn(f"could not import command {module_path}.{attr}: {exc}")
            continue
        commands.append(
            {
                "group_command": label,
                "class": attr,
                "module": module_path,
                "flags": extract_argparse_flags(cls),
            }
        )

    try:
        constants_mod = importlib.import_module("keepercommander.constants")
        enforcements = extract_enforcements(constants_mod)
    except Exception as exc:
        _warn(f"could not extract enforcements: {exc}")

    try:
        readme = (commander_path / "keepercommander/commands/pam_import/README.md").read_text(
            encoding="utf-8"
        )
        record_types = parse_readme_shapes(readme)
    except Exception as exc:
        _warn(f"could not parse pam_import README: {exc}")

    snapshot: dict[str, Any] = {
        "commander_sha": pin["sha"],
        "commander_branch": pin["branch"],
        "generated_at": _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
        "groups": sorted(groups, key=lambda g: g["group"]),
        "commands": sorted(commands, key=lambda c: c["group_command"]),
        "enforcements": enforcements,
        "record_types": record_types,
    }
    return snapshot, warnings


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(str(cell)) for cell in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(snapshot: dict[str, Any], warnings: Sequence[str]) -> str:
    sha = snapshot["commander_sha"]
    branch = snapshot["commander_branch"]
    lines: list[str] = [
        f"# Capability Matrix — Commander {sha} ({branch})",
        "",
        "Generated by `scripts/sync_upstream.py`. Do not hand-edit."
        " Regenerate on every upstream bump.",
        "",
        f"_Generated at {snapshot['generated_at']}._",
        "",
        "## Registered PAM command groups",
        "",
    ]

    pam_group_rows: list[list[str]] = []
    integ_group_rows: list[list[str]] = []
    vault_group_rows: list[list[str]] = []
    for group in snapshot["groups"]:
        label = str(group["group"])
        for sub in group["subcommands"]:
            row = [group["group"], sub["name"], sub["class"], sub["help"]]
            if label.startswith("pam"):
                pam_group_rows.append(row)
            elif label in ("scim", "automator"):
                integ_group_rows.append(row)
            elif label == "trash":
                vault_group_rows.append(row)
            else:
                pam_group_rows.append(row)

    if pam_group_rows:
        lines.append(_md_table(["Group", "Subcommand", "Class", "Help"], pam_group_rows))
    else:
        lines.append("_No PAM groups extracted — see extraction warnings below._")
    lines.append("")

    if integ_group_rows:
        lines.append("## Integrations command groups (extracted, P18b)")
        lines.append("")
        lines.append(
            "_SCIM + Automator roots for `keeper-integrations-identity.v1` / "
            "`keeper-integrations-events.v1` — explicit registry only._"
        )
        lines.append("")
        lines.append(_md_table(["Group", "Subcommand", "Class", "Help"], integ_group_rows))
        lines.append("")

    if vault_group_rows:
        lines.append("## Vault / trash command groups (extracted, P18b)")
        lines.append("")
        lines.append(
            "_`trash` group for deleted records / shared-folder trash flows "
            "adjacent to `keeper-vault-sharing`._"
        )
        lines.append("")
        lines.append(_md_table(["Group", "Subcommand", "Class", "Help"], vault_group_rows))
        lines.append("")

    ent_cmds = [c for c in snapshot["commands"] if str(c["group_command"]).startswith("enterprise")]
    vault_cmds = [
        c for c in snapshot["commands"] if c["group_command"] in _VAULT_FAMILY_COMMAND_LABELS
    ]
    pam_cmds = [
        c
        for c in snapshot["commands"]
        if not str(c["group_command"]).startswith("enterprise")
        and c["group_command"] not in _VAULT_FAMILY_COMMAND_LABELS
    ]

    def _append_command_flag_section(cmd: dict[str, Any]) -> None:
        lines.append(f"### {cmd['group_command']}")
        lines.append("")
        lines.append(f"_Class: `{cmd['module']}.{cmd['class']}`_")
        lines.append("")
        rows = [
            [
                flag["name"],
                "required" if flag["required"] else "optional",
                flag["type"],
                flag["help"],
            ]
            for flag in cmd["flags"]
        ]
        if rows:
            lines.append(_md_table(["Flag", "Required", "Type", "Help"], rows))
        else:
            lines.append("_No flags extracted._")
        lines.append("")

    lines.append("## Command flags (PAM)")
    lines.append("")
    for cmd in pam_cmds:
        _append_command_flag_section(cmd)

    if vault_cmds:
        lines.append("## Vault / folder CLI flags (extracted, P18b)")
        lines.append("")
        lines.append(
            "_Record + shared-folder + folder listing commands for `keeper-vault.v1` / "
            "`keeper-vault-sharing.v1` — see `docs/P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md`._"
        )
        lines.append("")
        for cmd in sorted(vault_cmds, key=lambda c: c["group_command"]):
            _append_command_flag_section(cmd)

    if ent_cmds:
        lines.append("## Enterprise commands (extracted, P18a)")
        lines.append("")
        lines.append(
            "_Explicit `sync_upstream.py` registry rows for `keeper-enterprise.v1` "
            "— see `docs/P18_SYNC_UPSTREAM_EXTRACTOR_DECISION.md`._"
        )
        lines.append("")
        for cmd in ent_cmds:
            _append_command_flag_section(cmd)

    lines.append("## Role enforcements checked at validate-stage-4")
    lines.append("")
    enf_rows = [
        [str(r["name"]), str(r["id"]), str(r["type"]), str(r["category"])]
        for r in snapshot["enforcements"]
    ]
    if enf_rows:
        lines.append(_md_table(["Name", "ID", "Type", "Category"], enf_rows))
    else:
        lines.append("_No enforcements extracted._")
    lines.append("")

    lines.append("## Upstream JSON shapes (from pam_import/README.md)")
    lines.append("")
    for resource_type, info in snapshot["record_types"].items():
        lines.append(f"### {resource_type}")
        lines.append("")
        top_keys = ", ".join(info["top_level_keys"]) or "_(none)_"
        lines.append(f"- keys observed: {top_keys}")
        for sub_name in ("options", "port_forward", "connection"):
            keys = info.get("pam_settings", {}).get(sub_name, [])
            if keys:
                lines.append(f"- pam_settings.{sub_name} keys observed: {', '.join(keys)}")
        lines.append("")

    lines.append("## NOT in upstream (do not model declaratively)")
    lines.append("")
    known_subs = {sub["name"] for g in snapshot["groups"] for sub in g["subcommands"]}
    # Document common asks that are intentionally absent from Commander.
    missing_hints = [
        ("pam project export", "not registered on PAMProjectCommand"),
        ("pam project remove", "not registered on PAMProjectCommand"),
    ]
    for label, reason in missing_hints:
        sub_name = label.split()[-1]
        if sub_name not in known_subs:
            lines.append(f"- {label} ({reason})")
    lines.append("")

    if warnings:
        lines.append("## Extraction warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


def _snapshot_for_compare(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Strip volatile fields before a drift comparison.

    ``generated_at`` is always stripped (pure timestamp).
    ``commander_branch`` is also stripped: in CI we clone Commander by
    SHA (``actions/checkout@v4`` with ``ref: <sha>`` and
    ``fetch-depth: 0``) and the resulting working tree has no local
    ``refs/heads/*`` or ``refs/remotes/origin/*`` pointing at HEAD, so
    ``git for-each-ref --points-at=HEAD`` falls through to ``detached``.
    Locally a human-readable branch name (``release`` for the pinned
    upstream) survives. The SHA is the real identity for drift
    purposes — branch name is an environment artefact.
    """
    stripped = dict(snapshot)
    stripped.pop("generated_at", None)
    stripped.pop("commander_branch", None)
    return stripped


def check_mode_detects_drift(
    current: dict[str, Any], committed: dict[str, Any]
) -> tuple[bool, str]:
    """Return ``(drift_detected, unified_diff)`` for two snapshots."""
    a = json.dumps(_snapshot_for_compare(committed), indent=2, sort_keys=True).splitlines()
    b = json.dumps(_snapshot_for_compare(current), indent=2, sort_keys=True).splitlines()
    diff = list(difflib.unified_diff(a, b, fromfile="committed", tofile="regenerated", lineterm=""))
    return (bool(diff), "\n".join(diff))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commander",
        type=Path,
        default=DEFAULT_COMMANDER,
        help="Path to the Commander checkout (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare regenerated snapshot against the committed one and exit 1 on drift.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json", "both"),
        default="both",
        help="Which artifacts to write when not in --check mode.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=DOCS_DIR,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)

    commander_path = args.commander.resolve()
    if not commander_path.is_dir():
        LOG.error("commander path does not exist: %s", commander_path)
        return 2

    snapshot, warnings = build_snapshot(commander_path)

    matrix_path = args.docs_dir / "CAPABILITY_MATRIX.md"
    snapshot_path = args.docs_dir / "capability-snapshot.json"

    if args.check:
        if not snapshot_path.is_file():
            print(f"no committed snapshot at {snapshot_path}", file=sys.stderr)
            return 1
        try:
            committed = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"committed snapshot is not valid JSON: {exc}", file=sys.stderr)
            return 1
        drift, diff = check_mode_detects_drift(snapshot, committed)
        if drift:
            print(diff, file=sys.stderr)
            return 1
        return 0

    args.docs_dir.mkdir(parents=True, exist_ok=True)
    if args.format in ("json", "both"):
        snapshot_path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.format in ("markdown", "both"):
        matrix_path.write_text(render_markdown(snapshot, warnings), encoding="utf-8")

    if warnings:
        for w in warnings:
            LOG.warning("extraction warning: %s", w)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
