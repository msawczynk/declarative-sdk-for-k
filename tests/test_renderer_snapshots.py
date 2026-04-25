"""RichRenderer snapshot tests.

These are layout-only regression guards. Downstream agents must use
``dsk plan --json`` for contracts.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from keeper_sdk.cli import renderer as renderer_module
from keeper_sdk.cli.renderer import RichRenderer
from keeper_sdk.core import build_graph, build_plan, compute_diff, execution_order, load_manifest
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.models import Manifest

SNAPSHOT_DIR = Path(__file__).resolve().parent / "fixtures" / "renderer_snapshots"


@pytest.fixture
def fixed_width_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        renderer_module,
        "_console",
        lambda: Console(file=io.StringIO(), width=120, force_terminal=False, record=True),
    )


def test_render_plan_snapshot(
    fixed_width_console: None,
    minimal_manifest_path: Path,
) -> None:
    renderer = RichRenderer()
    plan = _build_snapshot_plan(minimal_manifest_path)
    _assert_snapshot("render_plan", renderer.render_plan(plan))


def test_render_diff_snapshot(
    fixed_width_console: None,
    minimal_manifest_path: Path,
) -> None:
    renderer = RichRenderer()
    plan = _build_snapshot_plan(minimal_manifest_path)
    _assert_snapshot("render_diff", renderer.render_diff(plan))


def test_render_outcomes_snapshot(fixed_width_console: None) -> None:
    renderer = RichRenderer()
    outcomes = [
        ApplyOutcome(
            uid_ref="acme-lab-linux2",
            keeper_uid="UID-CREATE-001",
            action="create",
            details={"dry_run": True},
        ),
        ApplyOutcome(
            uid_ref="acme-lab-linux1-root",
            keeper_uid="UID-USER-001",
            action="update",
            details={"dry_run": True},
        ),
        ApplyOutcome(
            uid_ref="old-db",
            keeper_uid="UID-DELETE-001",
            action="delete",
            details={"dry_run": True},
        ),
        ApplyOutcome(
            uid_ref="acme-lab-linux3",
            keeper_uid="UID-CONFLICT-001",
            action="conflict",
            details={
                "reason": (
                    "unmanaged record with matching title; pass --adopt or use an import "
                    "workflow to claim it"
                )
            },
        ),
        ApplyOutcome(
            uid_ref="acme-lab-cfg",
            keeper_uid="UID-NOOP-001",
            action="noop",
        ),
    ]
    _assert_snapshot("render_outcomes", renderer.render_outcomes(outcomes))


def _build_snapshot_plan(minimal_manifest_path: Path):
    manifest = _manifest_with_extra_resources(minimal_manifest_path)
    graph = build_graph(manifest)
    order = execution_order(graph)
    changes = compute_diff(manifest, _snapshot_live_records(manifest), allow_delete=True)
    return build_plan(manifest.name, changes, order)


def _manifest_with_extra_resources(minimal_manifest_path: Path) -> Manifest:
    manifest = load_manifest(minimal_manifest_path)
    data = manifest.model_dump(mode="python", exclude_none=True)
    data["resources"].extend(
        [
            {
                "uid_ref": "acme-lab-linux2",
                "type": "pamMachine",
                "title": "lab-linux-2",
                "pam_configuration_uid_ref": "acme-lab-cfg",
                "shared_folder": "resources",
                "host": "10.16.9.11",
                "port": "22",
                "ssl_verification": True,
                "operating_system": "Linux",
            },
            {
                "uid_ref": "acme-lab-linux3",
                "type": "pamMachine",
                "title": "lab-linux-3",
                "pam_configuration_uid_ref": "acme-lab-cfg",
                "shared_folder": "resources",
                "host": "10.16.9.12",
                "port": "22",
                "ssl_verification": True,
                "operating_system": "Linux",
            },
        ]
    )
    return Manifest.model_validate(data)


def _snapshot_live_records(manifest: Manifest) -> list[LiveRecord]:
    cfg = manifest.pam_configurations[0].model_dump(mode="python", exclude_none=True)
    machine = manifest.resources[0].model_dump(mode="python", exclude_none=True)
    user = manifest.resources[0].users[0].model_dump(mode="python", exclude_none=True)

    live_user = dict(user)
    live_user["password"] = "old-password"
    live_user["otp"] = "123456"
    live_user["notes"] = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"

    conflict_payload = {
        "title": "lab-linux-3",
        "host": "10.16.9.12",
        "port": "22",
        "ssl_verification": True,
        "operating_system": "Linux",
    }
    orphan_payload = {
        "title": "old-db",
        "database_type": "mysql",
        "host": "old-db.example.com",
        "port": "3306",
    }

    return [
        _managed_record(
            keeper_uid="UID-CFG-001",
            title=manifest.pam_configurations[0].title or "acme-lab-cfg",
            resource_type="pam_configuration",
            uid_ref="acme-lab-cfg",
            manifest_name=manifest.name,
            payload=cfg,
        ),
        _managed_record(
            keeper_uid="UID-MACHINE-001",
            title=manifest.resources[0].title,
            resource_type="pamMachine",
            uid_ref="acme-lab-linux1",
            manifest_name=manifest.name,
            payload=machine,
        ),
        _managed_record(
            keeper_uid="UID-USER-001",
            title=manifest.resources[0].users[0].title,
            resource_type="pamUser",
            uid_ref="acme-lab-linux1-root",
            manifest_name=manifest.name,
            payload=live_user,
        ),
        LiveRecord(
            keeper_uid="UID-CONFLICT-001",
            title="lab-linux-3",
            resource_type="pamMachine",
            payload=conflict_payload,
            marker=None,
        ),
        _managed_record(
            keeper_uid="UID-DELETE-001",
            title="old-db",
            resource_type="pamDatabase",
            uid_ref="old-db",
            manifest_name=manifest.name,
            payload=orphan_payload,
        ),
    ]


def _managed_record(
    *,
    keeper_uid: str,
    title: str,
    resource_type: str,
    uid_ref: str,
    manifest_name: str,
    payload: dict[str, object],
) -> LiveRecord:
    return LiveRecord(
        keeper_uid=keeper_uid,
        title=title,
        resource_type=resource_type,
        payload=payload,
        marker=encode_marker(
            uid_ref=uid_ref,
            manifest=manifest_name,
            resource_type=resource_type,
        ),
    )


def _assert_snapshot(name: str, rendered: str) -> None:
    snapshot_path = SNAPSHOT_DIR / f"{name}.txt"
    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rendered, encoding="utf-8")
        pytest.skip(f"wrote snapshot: {snapshot_path}")
    assert rendered == snapshot_path.read_text(encoding="utf-8")
