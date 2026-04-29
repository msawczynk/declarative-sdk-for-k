"""Phase 7 shared-folder coverage for keeper-vault-sharing.v1."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1
from keeper_sdk.providers import MockProvider

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
