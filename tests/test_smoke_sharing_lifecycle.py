"""Offline smoke contracts for the vaultSharingLifecycle sharing scenario."""

from __future__ import annotations

import importlib
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.sharing_diff import (
    _RECORD_SHARE_RESOURCE,
    _SHARE_FOLDER_RESOURCE,
    _SHARED_FOLDER_RESOURCE,
    _SHARING_FOLDER_RESOURCE,
    compute_sharing_diff,
)
from keeper_sdk.core.sharing_models import (
    SHARING_FAMILY,
    SharingManifestV1,
    load_sharing_manifest,
)
from keeper_sdk.providers import MockProvider

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
if str(_SMOKE_DIR) not in sys.path:
    sys.path.insert(0, str(_SMOKE_DIR))

scenarios = pytest.importorskip("scripts.smoke.scenarios")

pytestmark = pytest.mark.skipif(
    not hasattr(scenarios, "VAULT_SHARING_LIFECYCLE"),
    reason="V8a not landed",
)

SCENARIO_NAME = "vaultSharingLifecycle"
TITLE_PREFIX = "sdk-smoke"
SF_UID = "sf-offline"
MANIFEST_NAME = f"{TITLE_PREFIX}-{SCENARIO_NAME}"
BLOCK_KEYS = ("folders", "shared_folders", "share_records", "share_folders")
RESOURCE_BLOCKS = {
    _SHARING_FOLDER_RESOURCE: "folders",
    _SHARED_FOLDER_RESOURCE: "shared_folders",
    _RECORD_SHARE_RESOURCE: "share_records",
    _SHARE_FOLDER_RESOURCE: "share_folders",
}


def _spec() -> Any:
    return scenarios.VAULT_SHARING_LIFECYCLE


def _resources(
    title_prefix: str = TITLE_PREFIX,
    sf_uid: str = SF_UID,
) -> list[dict[str, Any]]:
    result = _spec().resources_factory(title_prefix, sf_uid)
    assert isinstance(result, list), "resources_factory must return a list"
    assert all(isinstance(row, dict) for row in result)
    return result


def _build_document(
    title_prefix: str = TITLE_PREFIX,
    sf_uid: str = SF_UID,
) -> dict[str, Any]:
    document: dict[str, Any] = {"schema": SHARING_FAMILY, **dict.fromkeys(BLOCK_KEYS)}
    for key in BLOCK_KEYS:
        document[key] = []

    for resource in _resources(title_prefix, sf_uid):
        block = RESOURCE_BLOCKS.get(str(resource.get("resource_type")))
        if block is None:
            continue
        document[block].append(
            {field: value for field, value in resource.items() if field != "resource_type"}
        )
    return document


def _manifest() -> SharingManifestV1:
    return load_sharing_manifest(_build_document())


def _block(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = document.get(key)
    assert isinstance(value, list), f"{key} must be present as a list"
    assert all(isinstance(item, dict) for item in value)
    return value


def _sharing_order(manifest: SharingManifestV1) -> list[str]:
    return [
        *(folder.uid_ref for folder in manifest.folders),
        *(folder.uid_ref for folder in manifest.shared_folders),
        *(share.uid_ref for share in manifest.share_records),
        *(share.uid_ref for share in manifest.share_folders),
    ]


def _live_row(record: LiveRecord) -> dict[str, Any]:
    return {
        "keeper_uid": record.keeper_uid,
        "resource_type": record.resource_type,
        "title": record.title,
        "payload": dict(record.payload),
        "marker": dict(record.marker) if record.marker else None,
    }


def _live_rows_by_type(records: list[LiveRecord]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        _SHARING_FOLDER_RESOURCE: [],
        _SHARED_FOLDER_RESOURCE: [],
        _RECORD_SHARE_RESOURCE: [],
        _SHARE_FOLDER_RESOURCE: [],
    }
    for record in records:
        if record.resource_type in rows:
            rows[record.resource_type].append(_live_row(record))
    return rows


def _changes(
    manifest: SharingManifestV1,
    provider: MockProvider,
    *,
    allow_delete: bool = False,
) -> list[Change]:
    live = _live_rows_by_type(provider.discover())
    return compute_sharing_diff(
        manifest,
        live[_SHARING_FOLDER_RESOURCE],
        manifest_name=MANIFEST_NAME,
        allow_delete=allow_delete,
        live_shared_folders=live[_SHARED_FOLDER_RESOURCE],
        live_share_records=live[_RECORD_SHARE_RESOURCE],
        live_share_folders=live[_SHARE_FOLDER_RESOURCE],
    )


def _resource_count(manifest: SharingManifestV1) -> int:
    return (
        len(manifest.folders)
        + len(manifest.shared_folders)
        + len(manifest.share_records)
        + len(manifest.share_folders)
    )


def _apply_manifest(manifest: SharingManifestV1) -> tuple[MockProvider, list[LiveRecord]]:
    provider = MockProvider(MANIFEST_NAME)
    changes = _changes(manifest, provider)
    plan = build_plan(MANIFEST_NAME, changes, _sharing_order(manifest))
    provider.apply_plan(plan)
    return provider, provider.discover()


def _verify(live_records: list[LiveRecord]) -> None:
    _spec().verifier(live_records)


def _remove_first(records: list[LiveRecord], resource_type: str) -> list[LiveRecord]:
    removed = False
    kept: list[LiveRecord] = []
    for record in records:
        if record.resource_type == resource_type and not removed:
            removed = True
            continue
        kept.append(record)
    assert removed, f"happy-path records did not include {resource_type}"
    return kept


def _replace_first_markerless_folder(records: list[LiveRecord]) -> list[LiveRecord]:
    replaced = False
    out: list[LiveRecord] = []
    for record in records:
        if record.resource_type != _SHARING_FOLDER_RESOURCE or replaced:
            out.append(record)
            continue
        payload = dict(record.payload)
        payload.pop("marker", None)
        custom_fields = dict(payload.get("custom_fields") or {})
        custom_fields.pop(MARKER_FIELD_LABEL, None)
        if custom_fields:
            payload["custom_fields"] = custom_fields
        else:
            payload.pop("custom_fields", None)
        out.append(replace(record, payload=payload, marker=None))
        replaced = True
    assert replaced, "happy-path records did not include a sharing folder"
    return out


def test_scenario_constant_contract() -> None:
    spec = _spec()

    assert spec.name == SCENARIO_NAME
    assert spec.family == SHARING_FAMILY
    assert callable(spec.resources_factory)
    assert callable(spec.verifier)
    assert isinstance(spec.description, str)
    assert callable(spec.build_manifest)
    assert callable(spec.verify)
    assert not hasattr(spec, "build_resources")


def test_resource_factory_builds_expected_payload_shape() -> None:
    resources = _resources()
    document = _build_document()
    by_type = Counter(row["resource_type"] for row in resources)

    assert document["schema"] == SHARING_FAMILY
    folders = _block(document, "folders")
    shared_folders = _block(document, "shared_folders")
    record_shares = _block(document, "share_records")
    share_folders = _block(document, "share_folders")
    login_records = [row for row in resources if row.get("resource_type") == "login"]

    assert by_type == {
        _SHARING_FOLDER_RESOURCE: 1,
        _SHARED_FOLDER_RESOURCE: 1,
        "login": 1,
        _RECORD_SHARE_RESOURCE: 1,
        _SHARE_FOLDER_RESOURCE: 1,
    }
    assert len(folders) == 1
    assert len(shared_folders) == 1
    assert len(record_shares) == 1
    assert len(share_folders) == 1
    assert len(login_records) == 1
    assert all(row.get("uid_ref") for key in BLOCK_KEYS for row in _block(document, key))
    assert {row["kind"] for row in share_folders} == {"default"}
    assert all(row["record_uid_ref"].startswith("keeper-vault:records:") for row in record_shares)
    assert all(
        row["shared_folder_uid_ref"].startswith("keeper-vault-sharing:shared_folders:")
        for row in share_folders
    )
    assert login_records[0]["type"] == "login"
    assert login_records[0]["folder_ref"].startswith("keeper-vault-sharing:folders:")


def test_manifest_typed_load_accepts_factory_output() -> None:
    manifest = _manifest()

    assert isinstance(manifest, SharingManifestV1)
    assert manifest.vault_schema == SHARING_FAMILY
    assert _resource_count(manifest) > 0


def test_initial_diff_creates_all_lifecycle_blocks() -> None:
    manifest = _manifest()
    changes = _changes(manifest, MockProvider(MANIFEST_NAME))
    counts = Counter(change.resource_type for change in changes)

    assert all(change.kind is ChangeKind.CREATE for change in changes)
    assert counts[_SHARING_FOLDER_RESOURCE] == len(manifest.folders)
    assert counts[_SHARED_FOLDER_RESOURCE] == len(manifest.shared_folders)
    assert counts[_RECORD_SHARE_RESOURCE] == len(manifest.share_records)
    assert counts[_SHARE_FOLDER_RESOURCE] == len(manifest.share_folders)


def test_verifier_accepts_happy_path_record_list() -> None:
    manifest = _manifest()
    _provider, live_records = _apply_manifest(manifest)

    _verify(live_records)


def test_verifier_raises_on_missing_folder_marker() -> None:
    manifest = _manifest()
    _provider, live_records = _apply_manifest(manifest)

    with pytest.raises(AssertionError, match="folder|marker|drift|unmanaged"):
        _verify(_replace_first_markerless_folder(live_records))


def test_verifier_raises_on_missing_shared_folder() -> None:
    manifest = _manifest()
    _provider, live_records = _apply_manifest(manifest)

    with pytest.raises(AssertionError, match="shared_folder|shared folder|drift"):
        _verify(_remove_first(live_records, _SHARED_FOLDER_RESOURCE))


def test_verifier_raises_on_missing_record_share_grantee() -> None:
    manifest = _manifest()
    _provider, live_records = _apply_manifest(manifest)

    with pytest.raises(AssertionError, match="record_share|record share|grantee|drift"):
        _verify(_remove_first(live_records, _RECORD_SHARE_RESOURCE))


def test_verifier_raises_on_missing_share_folder() -> None:
    manifest = _manifest()
    _provider, live_records = _apply_manifest(manifest)

    with pytest.raises(AssertionError, match="share_folder|share folder|drift"):
        _verify(_remove_first(live_records, _SHARE_FOLDER_RESOURCE))


def test_mock_provider_round_trip_rediff_clean() -> None:
    manifest = _manifest()
    provider = MockProvider(MANIFEST_NAME)
    changes = _changes(manifest, provider)

    outcomes = provider.apply_plan(build_plan(MANIFEST_NAME, changes, _sharing_order(manifest)))

    assert [outcome.action for outcome in outcomes] == ["create"] * _resource_count(manifest)
    assert _changes(manifest, provider) == []


def test_clean_round_trip_allow_delete_has_zero_changes() -> None:
    manifest = _manifest()
    provider, _live_records = _apply_manifest(manifest)

    assert _changes(manifest, provider, allow_delete=True) == []


def test_record_share_same_record_different_grantees_round_trips() -> None:
    record_uid_ref = "keeper-vault:records:rec.shared-web"
    manifest = load_sharing_manifest(
        {
            "schema": SHARING_FAMILY,
            "share_records": [
                {
                    "uid_ref": "share.web.alice",
                    "record_uid_ref": record_uid_ref,
                    "user_email": "alice@example.com",
                    "permissions": {"can_edit": True, "can_share": False},
                },
                {
                    "uid_ref": "share.web.bob",
                    "record_uid_ref": record_uid_ref,
                    "user_email": "bob@example.com",
                    "permissions": {"can_edit": False, "can_share": False},
                },
            ],
        }
    )
    provider = MockProvider(MANIFEST_NAME)
    changes = _changes(manifest, provider)

    provider.apply_plan(build_plan(MANIFEST_NAME, changes, _sharing_order(manifest)))
    live = _live_rows_by_type(provider.discover())[_RECORD_SHARE_RESOURCE]

    assert [change.kind for change in changes] == [ChangeKind.CREATE, ChangeKind.CREATE]
    assert {row["payload"]["user_email"] for row in live} == {
        "alice@example.com",
        "bob@example.com",
    }
    assert _changes(manifest, provider) == []


def test_smoke_runner_exposes_choice_and_factory_writes_sharing_manifest() -> None:
    smoke = importlib.import_module("scripts.smoke.smoke")
    manifest_doc = yaml.safe_load(yaml.safe_dump(_build_document(), sort_keys=False))
    empty_doc = yaml.safe_load(
        yaml.safe_dump({"schema": SHARING_FAMILY, **{key: [] for key in BLOCK_KEYS}})
    )

    assert SCENARIO_NAME in smoke._scenario_choices()
    assert smoke._scenario_family(SCENARIO_NAME) == SHARING_FAMILY
    assert manifest_doc["schema"] == SHARING_FAMILY
    assert isinstance(load_sharing_manifest(manifest_doc), SharingManifestV1)
    assert empty_doc["schema"] == SHARING_FAMILY
    assert all(not empty_doc.get(key) for key in BLOCK_KEYS)
