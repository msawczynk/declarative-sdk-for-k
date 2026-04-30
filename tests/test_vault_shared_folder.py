"""Phase 7 shared-folder coverage for keeper-vault-sharing.v1."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import EXIT_CHANGES, EXIT_REF
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_models import SHARING_FAMILY, SharingManifestV1
from keeper_sdk.core.vault_sharing_plan import build_vault_sharing_plan
from keeper_sdk.providers import MockProvider
from keeper_sdk.providers.commander_cli import CommanderCliProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")

_SF_REF = "keeper-vault-sharing:shared_folders:sf.ops"
_REC_REF = "keeper-vault:records:rec.ops"


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
    uid_ref: str = "sf.ops.alice",
    user_email: str = "alice@example.com",
    manage_records: bool = False,
    manage_users: bool = False,
) -> dict[str, object]:
    return {
        "kind": "grantee",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": _SF_REF,
        "grantee": {"kind": "user", "user_email": user_email},
        "permissions": {"manage_records": manage_records, "manage_users": manage_users},
    }


def _record_member_share(
    *,
    uid_ref: str = "sf.ops.rec.ops",
    can_edit: bool,
    can_share: bool = False,
) -> dict[str, object]:
    return {
        "kind": "record",
        "uid_ref": uid_ref,
        "shared_folder_uid_ref": _SF_REF,
        "record_uid_ref": _REC_REF,
        "permissions": {"can_edit": can_edit, "can_share": can_share},
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


def _sharing_plan(
    manifest: SharingManifestV1,
    provider: MockProvider,
    *,
    allow_delete: bool = False,
):
    return build_vault_sharing_plan(
        manifest,
        provider.discover(),
        manifest_name="vault-sharing",
        allow_delete=allow_delete,
    )


def _share_folder_rows(provider: MockProvider) -> list[dict[str, object]]:
    return [
        {"payload": record.payload, "marker": record.marker}
        for record in provider.discover()
        if record.resource_type == "sharing_share_folder"
    ]


def test_validate_accepts_shared_folder_manifest(tmp_path: Path) -> None:
    path = tmp_path / "sharing.yaml"
    _write_shared_folder_manifest(path)

    result = _run(["validate", str(path), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == SHARING_FAMILY
    assert payload["uid_ref_count"] == 1


def test_validate_rejects_unknown_shared_folder_member_uid_ref(tmp_path: Path) -> None:
    path = tmp_path / "bad-sharing-ref.yaml"
    path.write_text(
        f"""\
schema: {SHARING_FAMILY}
shared_folders:
  - uid_ref: sf.ops
    path: /Shared/Ops
share_folders:
  - kind: record
    uid_ref: sf.ops.rec.ops
    shared_folder_uid_ref: keeper-vault-sharing:shared_folders:sf.missing
    record_uid_ref: {_REC_REF}
    permissions:
      can_edit: false
      can_share: false
""",
        encoding="utf-8",
    )

    result = _run(["validate", str(path)])

    assert result.exit_code == EXIT_REF, result.output
    assert "reference error:" in result.output
    assert "sf.missing" in result.output
    assert "sf.ops.rec.ops" in result.output


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


def test_mock_apply_refuses_share_folder_delete_plan_without_allow_delete() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(_grantee_share(manage_records=False))
    provider.apply_plan(_sharing_plan(manifest, provider))
    reduced = _sharing_manifest()

    delete_plan = _sharing_plan(reduced, provider, allow_delete=True)
    setattr(delete_plan, "allow_delete", False)

    assert [change.kind for change in delete_plan.changes] == [ChangeKind.DELETE]
    with pytest.raises(CapabilityError, match="--allow-delete"):
        provider.apply_plan(delete_plan)
    assert len(_share_folder_rows(provider)) == 1


def test_mock_apply_deletes_share_folder_member_with_allow_delete() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(_grantee_share(manage_records=False))
    provider.apply_plan(_sharing_plan(manifest, provider))
    reduced = _sharing_manifest()

    delete_plan = _sharing_plan(reduced, provider, allow_delete=True)
    outcomes = provider.apply_plan(delete_plan)
    clean_plan = _sharing_plan(reduced, provider)

    assert [change.kind for change in delete_plan.changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in outcomes] == ["delete"]
    assert _share_folder_rows(provider) == []
    assert clean_plan.changes == []


def test_shared_folder_record_member_permission_update_read_only_to_can_edit() -> None:
    desired = _record_member_share(can_edit=True)
    live = _record_member_share(can_edit=False)

    changes = compute_sharing_diff(
        _sharing_manifest(desired),
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[_live_share_folder(live)],
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].resource_type == "sharing_share_folder"
    assert changes[0].before == {"can_edit": False}
    assert changes[0].after == {"can_edit": True}


def test_mock_permission_update_syncs_nested_permissions_and_converges() -> None:
    provider = MockProvider("vault-sharing")
    read_only_manifest = _sharing_manifest(_record_member_share(can_edit=False))
    provider.apply_plan(_sharing_plan(read_only_manifest, provider))
    can_edit_manifest = _sharing_manifest(_record_member_share(can_edit=True))

    update_plan = _sharing_plan(can_edit_manifest, provider)
    outcomes = provider.apply_plan(update_plan)
    [row] = _share_folder_rows(provider)
    clean_plan = _sharing_plan(can_edit_manifest, provider)

    assert [change.kind for change in update_plan.changes] == [ChangeKind.UPDATE]
    assert [outcome.action for outcome in outcomes] == ["update"]
    assert row["payload"]["can_edit"] is True
    assert row["payload"]["permissions"]["can_edit"] is True
    assert clean_plan.changes == []


def test_mock_record_member_add_replans_clean() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(_record_member_share(can_edit=False))

    create_plan = _sharing_plan(manifest, provider)
    outcomes = provider.apply_plan(create_plan)
    clean_plan = _sharing_plan(manifest, provider)

    assert [change.resource_type for change in create_plan.changes] == [
        "sharing_shared_folder",
        "sharing_share_folder",
    ]
    assert [change.kind for change in create_plan.changes] == [ChangeKind.CREATE, ChangeKind.CREATE]
    assert [outcome.action for outcome in outcomes] == ["create", "create"]
    assert clean_plan.changes == []


def test_mock_record_member_remove_conflicts_without_allow_delete_then_deletes() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(_record_member_share(can_edit=False))
    provider.apply_plan(_sharing_plan(manifest, provider))
    reduced = _sharing_manifest()

    guarded_plan = _sharing_plan(reduced, provider)
    delete_plan = _sharing_plan(reduced, provider, allow_delete=True)

    assert [change.kind for change in guarded_plan.changes] == [ChangeKind.CONFLICT]
    assert guarded_plan.conflicts[0].resource_type == "sharing_share_folder"
    assert (
        guarded_plan.conflicts[0].reason
        == "managed share_folder record member missing from manifest; pass --allow-delete to remove"
    )
    assert [change.kind for change in delete_plan.changes] == [ChangeKind.DELETE]
    assert delete_plan.deletes[0].resource_type == "sharing_share_folder"


def test_mock_multi_member_apply_three_members_converges_clean() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(
        _grantee_share(uid_ref="sf.ops.alice", user_email="alice@example.com"),
        _grantee_share(uid_ref="sf.ops.bob", user_email="bob@example.com"),
        _grantee_share(uid_ref="sf.ops.carol", user_email="carol@example.com"),
    )

    create_plan = _sharing_plan(manifest, provider)
    outcomes = provider.apply_plan(create_plan)
    clean_plan = _sharing_plan(manifest, provider)

    assert [change.kind for change in create_plan.changes] == [
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
        ChangeKind.CREATE,
    ]
    assert [outcome.action for outcome in outcomes] == ["create", "create", "create", "create"]
    assert {row["payload"]["user_email"] for row in _share_folder_rows(provider)} == {
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    }
    assert clean_plan.changes == []


def test_mock_multi_member_remove_one_without_allow_delete_keeps_member() -> None:
    provider = MockProvider("vault-sharing")
    full_manifest = _sharing_manifest(
        _grantee_share(uid_ref="sf.ops.alice", user_email="alice@example.com"),
        _grantee_share(uid_ref="sf.ops.bob", user_email="bob@example.com"),
        _grantee_share(uid_ref="sf.ops.carol", user_email="carol@example.com"),
    )
    provider.apply_plan(_sharing_plan(full_manifest, provider))
    reduced_manifest = _sharing_manifest(
        _grantee_share(uid_ref="sf.ops.alice", user_email="alice@example.com"),
        _grantee_share(uid_ref="sf.ops.bob", user_email="bob@example.com"),
    )

    guarded_plan = _sharing_plan(reduced_manifest, provider)
    outcomes = provider.apply_plan(guarded_plan)

    assert [change.kind for change in guarded_plan.changes] == [ChangeKind.SKIP]
    assert guarded_plan.changes[0].reason == "managed share_folder missing from manifest"
    assert outcomes == []
    assert {row["payload"]["user_email"] for row in _share_folder_rows(provider)} == {
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
    }


def test_mock_multi_member_remove_one_with_allow_delete_then_reapply_noop() -> None:
    provider = MockProvider("vault-sharing")
    full_manifest = _sharing_manifest(
        _grantee_share(uid_ref="sf.ops.alice", user_email="alice@example.com"),
        _grantee_share(uid_ref="sf.ops.bob", user_email="bob@example.com"),
        _grantee_share(uid_ref="sf.ops.carol", user_email="carol@example.com"),
    )
    provider.apply_plan(_sharing_plan(full_manifest, provider))
    reduced_manifest = _sharing_manifest(
        _grantee_share(uid_ref="sf.ops.alice", user_email="alice@example.com"),
        _grantee_share(uid_ref="sf.ops.bob", user_email="bob@example.com"),
    )

    delete_plan = _sharing_plan(reduced_manifest, provider, allow_delete=True)
    delete_outcomes = provider.apply_plan(delete_plan)
    clean_plan = _sharing_plan(reduced_manifest, provider)
    clean_outcomes = provider.apply_plan(clean_plan)

    assert [change.kind for change in delete_plan.changes] == [ChangeKind.DELETE]
    assert [outcome.action for outcome in delete_outcomes] == ["delete"]
    assert {row["payload"]["user_email"] for row in _share_folder_rows(provider)} == {
        "alice@example.com",
        "bob@example.com",
    }
    assert clean_plan.changes == []
    assert clean_outcomes == []


def test_member_email_case_is_normalised_for_matching() -> None:
    desired = _grantee_share(user_email="ALICE@EXAMPLE.COM")
    live = _grantee_share(user_email="alice@example.com")

    changes = compute_sharing_diff(
        _sharing_manifest(desired),
        live_shared_folders=[_live_shared_folder()],
        live_share_folders=[_live_share_folder(live)],
    )

    assert changes == []


def test_mock_create_normalises_uppercase_member_email_and_converges() -> None:
    provider = MockProvider("vault-sharing")
    manifest = _sharing_manifest(_grantee_share(user_email="ALICE@EXAMPLE.COM"))

    provider.apply_plan(_sharing_plan(manifest, provider))
    [row] = _share_folder_rows(provider)
    clean_plan = _sharing_plan(manifest, provider)

    assert row["payload"]["user_email"] == "alice@example.com"
    assert row["payload"]["grantee"]["user_email"] == "alice@example.com"
    assert clean_plan.changes == []
