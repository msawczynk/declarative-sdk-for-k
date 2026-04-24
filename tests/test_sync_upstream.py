"""Tests for ``scripts/sync_upstream.py``.

All tests use stubs / monkeypatch so they stay green even when the
Commander sibling checkout has been deleted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_upstream.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("sync_upstream", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_upstream"] = module
    spec.loader.exec_module(module)
    return module


sync_upstream = _load_script()


# ---------------------------------------------------------------------------
# extract_enforcements
# ---------------------------------------------------------------------------


def test_extract_enforcements_filters_to_pam_relevant_rows() -> None:
    stub = types.SimpleNamespace(
        _ENFORCEMENTS=[
            ("RESTRICT_BREACH_WATCH", 201, "BOOLEAN", "VAULT_FEATURES"),
            ("ALLOW_SECRETS_MANAGER", 212, "BOOLEAN", "VAULT_FEATURES"),
            ("ALLOW_PAM_ROTATION", 218, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
            ("ALLOW_PAM_GATEWAY", 225, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
            ("ALLOW_CONFIGURE_ROTATION_SETTINGS", 226, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
            ("ALLOW_ROTATE_CREDENTIALS", 227, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
            ("ALLOW_PAM_DISCOVERY", 219, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
            ("SOMETHING_ELSE", 999, "BOOLEAN", "OTHER"),
        ]
    )

    rows = sync_upstream.extract_enforcements(stub)

    names = [r["name"] for r in rows]
    assert "ALLOW_SECRETS_MANAGER" in names
    assert "ALLOW_PAM_ROTATION" in names
    assert "ALLOW_PAM_GATEWAY" in names
    assert "ALLOW_CONFIGURE_ROTATION_SETTINGS" in names
    assert "ALLOW_ROTATE_CREDENTIALS" in names
    assert "ALLOW_PAM_DISCOVERY" in names  # caught by ALLOW_PAM* prefix
    assert "RESTRICT_BREACH_WATCH" not in names
    assert "SOMETHING_ELSE" not in names
    # Ordered deterministically.
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# extract_argparse_flags
# ---------------------------------------------------------------------------


def test_extract_argparse_flags_returns_flag_names_and_help() -> None:
    class StubCommand:
        parser = argparse.ArgumentParser(prog="stub")

        @classmethod
        def _build(cls) -> None:
            cls.parser.add_argument("--name", "-n", help="Project name.")
            cls.parser.add_argument("--dry-run", action="store_true", help="Test mode.")
            cls.parser.add_argument("positional", help="Required positional.")

    StubCommand._build()

    flags = sync_upstream.extract_argparse_flags(StubCommand)

    by_name = {f["name"]: f for f in flags}
    assert "--name" in by_name
    assert by_name["--name"]["help"] == "Project name."
    assert by_name["--dry-run"]["type"] == "flag"
    assert "<positional>" in by_name
    assert by_name["<positional>"]["required"] is True


# ---------------------------------------------------------------------------
# parse_readme_shapes
# ---------------------------------------------------------------------------


_README_OK = """
<details>
<summary>pam_data.resources.pamMachine (RDP)</summary>

```json
{
    "type": "pamMachine",
    "title": "example",
    "host": "127.0.0.1",
    "pam_settings": {
        "options": {"rotation": "on", "connections": "on"},
        "port_forward": {"port": "2222"},
        "connection": {"protocol": "rdp", "port": "2222"}
    }
}
```
</details>
"""

_README_BROKEN = """
<details>
<summary>pam_data.resources.pamDatabase</summary>

```json
{ not valid json at all
```
</details>
"""


def test_parse_readme_shapes_extracts_keys_for_known_resource_type() -> None:
    shapes = sync_upstream.parse_readme_shapes(_README_OK)

    assert "pamMachine" in shapes
    pm = shapes["pamMachine"]
    assert "host" in pm["top_level_keys"]
    assert "pam_settings" in pm["top_level_keys"]
    assert "rotation" in pm["pam_settings"]["options"]
    assert "port" in pm["pam_settings"]["port_forward"]
    assert "protocol" in pm["pam_settings"]["connection"]


def test_parse_readme_shapes_handles_malformed_block(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="sync_upstream"):
        shapes = sync_upstream.parse_readme_shapes(_README_BROKEN)

    assert shapes == {}
    assert any("could not parse json" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# check_mode_detects_drift
# ---------------------------------------------------------------------------


def _base_snapshot() -> dict:
    return {
        "commander_sha": "deadbee",
        "commander_branch": "main",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "groups": [{"group": "pam project", "class": "X", "subcommands": []}],
        "commands": [],
        "enforcements": [
            {"name": "ALLOW_PAM_ROTATION", "id": 218, "type": "BOOLEAN", "category": "X"}
        ],
        "record_types": {},
    }


def test_check_mode_detects_drift_on_value_change() -> None:
    committed = _base_snapshot()
    current = _base_snapshot()
    current["enforcements"][0]["id"] = 999

    drift, diff = sync_upstream.check_mode_detects_drift(current, committed)

    assert drift is True
    assert "218" in diff and "999" in diff


def test_check_mode_ignores_generated_at() -> None:
    committed = _base_snapshot()
    current = _base_snapshot()
    current["generated_at"] = "2099-12-31T23:59:59+00:00"

    drift, diff = sync_upstream.check_mode_detects_drift(current, committed)

    assert drift is False
    assert diff == ""


# ---------------------------------------------------------------------------
# Smoke test for main()
# ---------------------------------------------------------------------------


def test_main_smoke_writes_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_commander = tmp_path / "Commander"
    (fake_commander / "keepercommander" / "commands" / "pam_import").mkdir(parents=True)
    (fake_commander / "keepercommander" / "commands" / "pam_import" / "README.md").write_text(
        _README_OK, encoding="utf-8"
    )

    # Stub the Commander imports so build_snapshot() can't reach the real
    # sibling checkout.
    def fake_import(name: str):
        if name == "keepercommander.constants":
            return types.SimpleNamespace(
                _ENFORCEMENTS=[
                    ("ALLOW_PAM_ROTATION", 218, "BOOLEAN", "ACCOUNT_ENFORCEMENTS"),
                    ("ALLOW_SECRETS_MANAGER", 212, "BOOLEAN", "VAULT_FEATURES"),
                ]
            )
        raise ImportError(name)

    monkeypatch.setattr(sync_upstream.importlib, "import_module", fake_import)

    # Stub subprocess.run so we don't need a real git repo at the fake path.
    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        return types.SimpleNamespace(stdout="abc1234\n", returncode=0)

    monkeypatch.setattr(sync_upstream.subprocess, "run", fake_run)

    docs_dir = tmp_path / "docs"
    rc = sync_upstream.main(
        [
            "--commander",
            str(fake_commander),
            "--docs-dir",
            str(docs_dir),
            "--format",
            "both",
        ]
    )

    assert rc == 0
    matrix = docs_dir / "CAPABILITY_MATRIX.md"
    snap = docs_dir / "capability-snapshot.json"
    assert matrix.is_file()
    assert snap.is_file()
    data = json.loads(snap.read_text())
    assert data["commander_sha"] == "abc1234"
    assert any(r["name"] == "ALLOW_PAM_ROTATION" for r in data["enforcements"])
    assert "pamMachine" in data["record_types"]
