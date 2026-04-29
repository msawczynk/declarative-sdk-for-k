"""Phase 7 shared-folder coverage for keeper-vault-sharing.v1."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1
from keeper_sdk.providers import MockProvider
from keeper_sdk.providers.commander_cli import CommanderCliProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

_SF_REF = "keeper-vault-sharing:shared_folders:sf.ops"


def _run(args: list[str]):
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _write_shared_folder_manifest(path: Path) -> None:
    path.write_text(
        f"""\
schema: {SHARING_FAMILY}
shared_folders:
  - uid_ref: sf.ops
    path: /Shared/Ops
    defaults:
      manage_users: true
      manage_records: true
      can_edit: false
      can_share: false
""",
        encoding="utf-8",
    )


def _grantee_share(
    *,
    manage_records: bool,
    manage_users: bool = False,
) -> dict[str, object]:
    return {
        "kind": "grantee",
        "uid_ref": "sf.ops.alice",
        "shared_folder_uid_ref": _SF_REF,
        "grantee": {"kind": "user", "user_email": "alice@example.com"},
        "permissions": {"manage_records": manage_records, "manage_users": manage_users},
    }


def _share_manifest(share: dict[str, object]) -> SharingManifestV1:
    return SharingManifestV1.model_validate(
        {
            "schema": SHARING_FAMILY,
            "shared_folders": [{"uid_ref": "sf.ops", "path": "/Shared/Ops"}],
            "share_folders": [share],
        }
    )


def _sharing_manifest(*shares: dict[str, object]) -> SharingManifestV1:
    return SharingManifestV1.model_validate(
        {
            "schema": SHARING_FAMILY,
            "shared_folders": [{"uid_ref": "sf.ops", "path": "/Shared/Ops"}],
            "share_folders": list(shares),
        }
    )


def _live_shared_folder() -> dict[str, object]:
    return {
        "keeper_uid": "live-sf.ops",
        "resource_type": "sharing_shared_folder",
        "title": "/Shared/Ops",
        "payload": {"uid_ref": "sf.ops", "name": "/Shared/Ops"},
        "marker": encode_marker(
            uid_ref="sf.ops",
            manifest="vault-sharing",
            resource_type="sharing_shared_folder",
        ),
    }


def _live_share_folder(share: dict[str, object]) -> dict[str, object]:
    uid_ref = str(share["uid_ref"])
    return {
        **share,
        "keeper_uid": f"live-{uid_ref}",
        "marker": encode_marker(
            uid_ref=uid_ref,
            manifest="vault-sharing",
            resource_type="sharing_share_folder",
            parent_uid_ref=_SF_REF,
        ),
    }


def test_validate_accepts_shared_folder_manifest(tmp_path: Path) -> None:
    path = tmp_path / "sharing.yaml"
    _write_shared_folder_manifest(path)

    result = _run(["validate", str(path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == SHARING_FAMILY
    assert payload["uid_ref_count"] == 1


def test_plan_shared_folder_create_then_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "sharing.yaml"
    _write_shared_folder_manifest(path)
    provider = MockProvider(path.stem)
    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    plan_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert plan_result.exit_code == EXIT_CHANGES, plan_result.output
    plan = json.loads(plan_result.output)
    assert plan["summary"]["create"] == 1
    assert plan["changes"][0]["resource_type"] == "sharing_shared_folder"

    apply_result = _run(["apply", str(path), "--provider", "mock", "--yes"])
    assert apply_result.exit_code == 0, apply_result.output

    clean_result = _run(["plan", str(path), "--provider", "mock", "--json"])
    assert clean_result.exit_code == 0, clean_result.output
    clean_plan = json.loads(clean_result.output)
    assert clean_plan["summary"]["create"] == 0
    assert clean_plan["changes"] == []


def test_shared_folder_member_create_plan_and_mock_commander_share_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share = _grantee_share(manage_records=False)
    manifest = _sharing_manifest(share)
    changes = compute_sharing_diff(
        manifest,
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[],
    )
    plan = build_plan("vault-sharing", changes, ["sf.ops", "sf.ops.alice"])

    assert len(plan.creates) == 1
    create = plan.creates[0]
    assert create.resource_type == "sharing_share_folder"
    assert create.uid_ref == "sf.ops.alice"
    assert create.after["user_email"] == "alice@example.com"

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/bin/keeper",
    )
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli._ensure_keepercommander_version_for_apply",
        lambda: None,
    )
    provider = CommanderCliProvider(
        folder_uid="marker-folder",
        manifest_source={"schema": SHARING_FAMILY},
    )
    share_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        provider,
        "_sharing_resolve_ref",
        lambda _ref, *, expected_resource_type: "SF_UID",
    )
    monkeypatch.setattr(provider, "_sharing_upsert_sidecar", lambda **_kwargs: None)
    monkeypatch.setattr(
        provider,
        "_share_folder_to_grantee",
        lambda **kwargs: share_calls.append(dict(kwargs)),
    )

    outcomes = provider.apply_plan(plan)

    assert [outcome.action for outcome in outcomes] == ["create"]
    assert share_calls == [
        {
            "shared_folder_uid": "SF_UID",
            "grantee_kind": "user",
            "identifier": "alice@example.com",
            "manage_records": False,
            "manage_users": False,
        }
    ]


def test_shared_folder_member_remove_requires_allow_delete_then_plans_delete() -> None:
    live_member = _live_share_folder(_grantee_share(manage_records=False))

    guarded_changes = compute_sharing_diff(
        _sharing_manifest(),
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[live_member],
    )
    assert len(guarded_changes) == 1
    assert guarded_changes[0].kind is ChangeKind.SKIP
    assert guarded_changes[0].reason == "managed share_folder missing from manifest"

    delete_changes = compute_sharing_diff(
        _sharing_manifest(),
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[live_member],
        allow_delete=True,
    )
    plan = build_plan("vault-sharing", delete_changes, ["sf.ops", "sf.ops.alice"])

    assert len(plan.deletes) == 1
    assert plan.deletes[0].resource_type == "sharing_share_folder"
    assert plan.deletes[0].uid_ref == "sf.ops.alice"


def test_shared_folder_member_permission_update_read_only_to_manage_records() -> None:
    desired = _grantee_share(manage_records=True)
    live = _grantee_share(manage_records=False)

    changes = compute_sharing_diff(
        _sharing_manifest(desired),
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[_live_share_folder(live)],
    )
    plan = build_plan("vault-sharing", changes, ["sf.ops", "sf.ops.alice"])

    assert len(plan.updates) == 1
    update = plan.updates[0]
    assert update.resource_type == "sharing_share_folder"
    assert update.before == {"manage_records": False}
    assert update.after == {"manage_records": True}


def test_shared_folder_membership_permission_diff_updates() -> None:
    desired = _grantee_share(manage_records=False)
    live = _grantee_share(manage_records=True)

    changes = compute_sharing_diff(
        _share_manifest(desired),
        live_shared_folders=[],
        live_share_folders=[_live_share_folder(live)],
    )

    assert len(changes) == 2
    assert changes[0].resource_type == "sharing_shared_folder"
    assert changes[0].kind is ChangeKind.CREATE
    assert changes[1].resource_type == "sharing_share_folder"
    assert changes[1].kind is ChangeKind.UPDATE
    assert changes[1].before == {"manage_records": True}
    assert changes[1].after == {"manage_records": False}
