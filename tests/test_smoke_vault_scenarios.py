"""Offline tests for keeper-vault.v1 smoke scenarios."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import scenarios as smoke_scenarios  # noqa: E402
import smoke  # noqa: E402

from keeper_sdk.core import build_plan, compute_vault_diff, vault_record_apply_order  # noqa: E402
from keeper_sdk.core.diff import ChangeKind  # noqa: E402
from keeper_sdk.core.interfaces import LiveRecord  # noqa: E402
from keeper_sdk.core.manifest import load_declarative_manifest  # noqa: E402
from keeper_sdk.core.metadata import encode_marker  # noqa: E402
from keeper_sdk.core.vault_models import VaultManifestV1  # noqa: E402
from keeper_sdk.providers import MockProvider  # noqa: E402

TITLE_PREFIX = "sdk-smoke"


def _manifest() -> dict:
    return smoke_scenarios._vault_one_login_manifest(TITLE_PREFIX, "sf-offline")


def _schema() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "keeper_sdk/core/schemas/keeper-vault/keeper-vault.v1.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _typed_manifest(tmp_path: Path) -> VaultManifestV1:
    path = tmp_path / "vaultOneLogin.yaml"
    path.write_text(yaml.safe_dump(_manifest(), sort_keys=False), encoding="utf-8")
    loaded = load_declarative_manifest(path)
    assert isinstance(loaded, VaultManifestV1)
    return loaded


def test_vault_one_login_manifest_shape() -> None:
    manifest = _manifest()
    assert set(manifest) == {"schema", "records"}
    assert manifest["schema"] == "keeper-vault.v1"
    assert len(manifest["records"]) == 1

    record = manifest["records"][0]
    assert record["uid_ref"] == "sdk-smoke-vault-one"
    assert record["type"] == "login"
    assert record["title"] == "sdk-smoke-vault-one"

    fields = record["fields"]
    assert all(isinstance(field["value"], list) for field in fields)
    labels = {field["label"] for field in fields}
    assert labels == {"Login", "Password"}
    assert fields[0]["value"] == ["smoke@example.invalid"]
    assert fields[1]["value"][0]


def test_vault_one_login_manifest_schema_validates(tmp_path: Path) -> None:
    manifest = _manifest()
    json_path = tmp_path / "vaultOneLogin.json"
    json_path.write_text(json.dumps(manifest), encoding="utf-8")

    subprocess.run(
        [sys.executable, "-m", "json.tool", str(json_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    jsonschema.validate(instance=manifest, schema=_schema())


def test_vault_one_login_manifest_typed_load(tmp_path: Path) -> None:
    loaded = _typed_manifest(tmp_path)
    assert isinstance(loaded, VaultManifestV1)
    assert loaded.records[0].type == "login"


def test_vault_one_login_diff_create_then_clean(tmp_path: Path) -> None:
    manifest = _typed_manifest(tmp_path)
    provider = MockProvider("vaultOneLogin")
    order = vault_record_apply_order(manifest)

    changes = compute_vault_diff(manifest, provider.discover(), manifest_name="vaultOneLogin")
    creates = [change for change in changes if change.kind is ChangeKind.CREATE]
    assert len(creates) == 1

    plan = build_plan("vaultOneLogin", changes, order)
    outcomes = provider.apply_plan(plan)
    assert [outcome.action for outcome in outcomes] == ["create"]

    changes_after = compute_vault_diff(manifest, provider.discover(), manifest_name="vaultOneLogin")
    assert [change for change in changes_after if change.kind is not ChangeKind.NOOP] == []


def test_vault_one_login_verifier_pass_and_fail(tmp_path: Path) -> None:
    manifest = _typed_manifest(tmp_path)
    record = manifest.records[0]
    marker = encode_marker(
        uid_ref=record.uid_ref,
        manifest="vaultOneLogin",
        resource_type="login",
    )
    live = LiveRecord(
        keeper_uid="uid-1",
        title=record.title,
        resource_type=record.type,
        payload={
            "type": record.type,
            "title": record.title,
            "fields": record.fields,
        },
        marker=marker,
    )

    smoke_scenarios._verify_vault_one_login(manifest, [live], TITLE_PREFIX)

    wrong_title = LiveRecord(
        keeper_uid="uid-1",
        title="wrong-title",
        resource_type=record.type,
        payload={
            "type": record.type,
            "title": "wrong-title",
            "fields": record.fields,
        },
        marker=marker,
    )
    with pytest.raises(AssertionError, match="expected managed login"):
        smoke_scenarios._verify_vault_one_login(manifest, [wrong_title], TITLE_PREFIX)


def test_smoke_argparse_accepts_vault_scenario() -> None:
    args = smoke._parse_args(["--scenario", "vaultOneLogin"])
    assert args.scenario == "vaultOneLogin"
    assert smoke._scenario_family(args.scenario) == "keeper-vault.v1"


def test_smoke_family_dispatch_writes_vault_manifests() -> None:
    previous_family = smoke._ACTIVE_SCENARIO_FAMILY
    previous_pam = smoke._ACTIVE_SCENARIO
    previous_vault = smoke._ACTIVE_VAULT_SCENARIO
    try:
        assert smoke._set_active_scenario("vaultOneLogin") == "keeper-vault.v1"
        manifest_path = smoke._write_manifest("sf-offline")
        empty_path = smoke._write_empty_manifest("sf-offline")
        same_stem_empty_path = smoke._write_empty_manifest(
            "sf-offline",
            stem=manifest_path.stem,
        )
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            empty = yaml.safe_load(empty_path.read_text(encoding="utf-8"))
            same_stem_empty = yaml.safe_load(
                same_stem_empty_path.read_text(encoding="utf-8")
            )
        finally:
            manifest_path.unlink(missing_ok=True)
            empty_path.unlink(missing_ok=True)
            same_stem_empty_path.unlink(missing_ok=True)

        assert manifest["schema"] == "keeper-vault.v1"
        assert len(manifest["records"]) == 1
        assert empty == {"schema": "keeper-vault.v1", "records": []}
        assert same_stem_empty == empty
        assert same_stem_empty_path.stem == manifest_path.stem
    finally:
        smoke._ACTIVE_SCENARIO_FAMILY = previous_family
        smoke._ACTIVE_SCENARIO = previous_pam
        smoke._ACTIVE_VAULT_SCENARIO = previous_vault
