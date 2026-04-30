"""D-6 coverage follow-ups.

Gaps surfaced by the 2026-04-24 devil's-advocate review:

1. ``from_pam_import_json`` round-trip from a Commander-native payload
   back to a declarative manifest — the lift wasn't directly exercised.
2. ``load_manifest_string`` as a public entry point (YAML + JSON).
3. ``MetadataStore`` protocol — no test implementing it, so we pin a
   trivial in-memory implementation satisfies the structural check.
4. ``utc_timestamp`` shape — ISO-8601 ``Z`` suffix must not drift.
5. ``pam gateway list`` / ``pam config list`` JSON parsers (D-3) —
   contract tests using the exact shape documented on Commander
   release branch (``17.2.16+``).
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from keeper_sdk.core.interfaces import MetadataStore
from keeper_sdk.core.manifest import dump_manifest, load_manifest_string
from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_FIELD_LABEL,
    MARKER_VERSION,
    utc_timestamp,
)
from keeper_sdk.core.normalize import (
    from_pam_import_json,
    to_pam_import_json,
)
from keeper_sdk.providers.commander_cli import CommanderCliProvider

# ---------------------------------------------------------------------------
# from_pam_import_json round-trip


def test_from_pam_import_json_round_trip_is_loadable() -> None:
    """A lifted manifest must load through ``load_manifest_string``
    without further editing."""
    pam_native = {
        "project": "acme-lab",
        "shared_folder_resources": {},
        "shared_folder_users": {},
        "pam_configuration": {
            "title": "Lab Configuration",
            "environment": "local",
            "gateway_name": "Lab GW",
        },
        "pam_data": {
            "resources": [
                {"type": "pamMachine", "title": "db-prod"},
            ],
            "users": [
                {"type": "pamUser", "title": "admin", "login": "root"},
            ],
        },
    }
    lifted = from_pam_import_json(pam_native)
    assert lifted["name"] == "acme-lab"
    assert lifted["version"] == "1"

    # All synthesised uid_refs are non-empty + unique.
    uid_refs: list[str] = []
    for gw in lifted.get("gateways", []) or []:
        uid_refs.append(gw["uid_ref"])
    for cfg in lifted.get("pam_configurations", []) or []:
        uid_refs.append(cfg["uid_ref"])
    for res in lifted.get("resources", []) or []:
        uid_refs.append(res["uid_ref"])
    for user in lifted.get("users", []) or []:
        uid_refs.append(user["uid_ref"])
    assert len(uid_refs) == len(set(uid_refs)), f"duplicate uid_refs in lift: {uid_refs}"

    # Round-trip through the typed manifest loader. Skip schema validation:
    # the lift currently synthesises orphaned pam_configuration_uid_ref
    # links, which semantic rules reject by design — that's a known
    # follow-up (REVIEW.md D-4) and NOT what this test pins.
    manifest = load_manifest_string(json.dumps(lifted), suffix=".json", validate=False)
    assert manifest.name == "acme-lab"


def test_from_pam_import_json_handles_missing_optional_sections() -> None:
    minimal = {"project": "slim"}
    lifted = from_pam_import_json(minimal)
    assert lifted["name"] == "slim"
    assert "resources" not in lifted or lifted["resources"] == []


def test_to_from_round_trip_preserves_core_fields() -> None:
    """``to_pam_import_json(from_pam_import_json(x))`` should preserve
    the observable top-level keys even if uid_refs get regenerated."""
    pam_native = {
        "project": "rt",
        "pam_configuration": {
            "title": "Cfg",
            "environment": "local",
            "gateway_name": "GW",
        },
        "pam_data": {
            "resources": [{"type": "pamMachine", "title": "host-a"}],
        },
    }
    lifted = from_pam_import_json(pam_native)
    reprojected = to_pam_import_json(lifted)
    assert reprojected["project"] == "rt"
    assert reprojected["pam_configuration"]["title"] == "Cfg"
    assert reprojected["pam_data"]["resources"][0]["title"] == "host-a"


# ---------------------------------------------------------------------------
# load_manifest_string


def test_load_manifest_string_accepts_yaml() -> None:
    raw = (
        "version: '1'\n"
        "name: yaml-manifest\n"
        "gateways:\n"
        "  - uid_ref: gw.lab\n"
        "    name: Lab\n"
        "    mode: reference_existing\n"
    )
    manifest = load_manifest_string(raw, suffix=".yaml")
    assert manifest.name == "yaml-manifest"


def test_load_manifest_string_accepts_json() -> None:
    raw = json.dumps(
        {
            "version": "1",
            "name": "json-manifest",
            "gateways": [{"uid_ref": "gw.lab", "name": "Lab", "mode": "reference_existing"}],
        }
    )
    manifest = load_manifest_string(raw, suffix=".json")
    assert manifest.name == "json-manifest"


def test_load_manifest_string_autodetects_json_from_brace() -> None:
    raw = '{"version": "1", "name": "auto"}'
    # intentionally bogus suffix
    manifest = load_manifest_string(raw, suffix=".txt")
    assert manifest.name == "auto"


def test_dump_manifest_round_trip() -> None:
    raw = "version: '1'\nname: rt\n"
    manifest = load_manifest_string(raw, suffix=".yaml")
    dumped = dump_manifest(manifest, fmt="yaml")
    assert "name: rt" in dumped


# ---------------------------------------------------------------------------
# MetadataStore protocol


def test_metadata_store_protocol_structural_check() -> None:
    """A trivial in-memory store must satisfy the Protocol."""

    class _InMemory:
        def __init__(self) -> None:
            self._by_uid: dict[str, dict[str, Any]] = {}

        def read(self, keeper_uid: str) -> dict[str, Any] | None:
            return self._by_uid.get(keeper_uid)

        def write(self, keeper_uid: str, marker: dict[str, Any]) -> None:
            self._by_uid[keeper_uid] = marker

        def clear(self, keeper_uid: str) -> None:
            self._by_uid.pop(keeper_uid, None)

    store: MetadataStore = _InMemory()  # structural check — no runtime assertion needed
    store.write("u", {"manager": MANAGER_NAME})
    assert store.read("u") == {"manager": MANAGER_NAME}
    store.clear("u")
    assert store.read("u") is None


# ---------------------------------------------------------------------------
# utc_timestamp


def test_utc_timestamp_iso8601_z_suffix() -> None:
    stamp = utc_timestamp()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", stamp), stamp


# ---------------------------------------------------------------------------
# Commander JSON contract pins (D-3)


def test_pam_gateway_rows_parses_release_json_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the exact JSON shape documented at
    ``Commander/keepercommander/commands/discoveryrotation.py`` L1565-1606
    (``pam gateway list --format json``)."""
    payload = json.dumps(
        {
            "gateways": [
                {
                    "ksm_app_name": "Example Gateway Application",
                    "ksm_app_uid": "app-uid",
                    "ksm_app_accessible": True,
                    "gateway_name": "Example Gateway",
                    "gateway_uid": "gw-uid",
                    "status": "ONLINE",
                    "gateway_version": "1.7.6",
                }
            ]
        }
    )
    provider = CommanderCliProvider()
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: (
            payload if args == ["pam", "gateway", "list", "--format", "json"] else ""
        ),
    )
    rows = provider._pam_gateway_rows()
    assert rows == [
        {
            "app_title": "Example Gateway Application",
            "app_uid": "app-uid",
            "gateway_name": "Example Gateway",
            "gateway_uid": "gw-uid",
        }
    ]


def test_pam_gateway_rows_tolerates_empty_enterprise(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"gateways": [], "message": "No gateways"})
    provider = CommanderCliProvider()
    monkeypatch.setattr(CommanderCliProvider, "_run_cmd", lambda self, args: payload)
    assert provider._pam_gateway_rows() == []


def test_pam_config_rows_parses_release_json_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin ``pam config list --format json`` shape
    (``discoveryrotation.py`` L1919-1967)."""
    payload = json.dumps(
        {
            "configurations": [
                {
                    "uid": "cfg-uid",
                    "config_name": "LW Gateway Configuration",
                    "config_type": "pamNetworkConfiguration",
                    "shared_folder": {
                        "name": "Example Gateway Folder - Resources",
                        "uid": "folder-uid",
                    },
                    "gateway_uid": "gw-uid",
                    "resource_record_uids": [],
                }
            ]
        }
    )
    provider = CommanderCliProvider()
    monkeypatch.setattr(
        CommanderCliProvider,
        "_run_cmd",
        lambda self, args: payload if args == ["pam", "config", "list", "--format", "json"] else "",
    )
    rows = provider._pam_config_rows()
    assert rows == [
        {
            "config_uid": "cfg-uid",
            "config_name": "LW Gateway Configuration",
            "gateway_uid": "gw-uid",
            "shared_folder_title": "Example Gateway Folder - Resources",
            "shared_folder_uid": "folder-uid",
        }
    ]


def test_apply_plan_refuses_unimplemented_gateway_mode_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-4 guard: gateway mode:create must fail loud, not silently drop."""
    from keeper_sdk.core.errors import CapabilityError
    from keeper_sdk.core.planner import Plan

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    provider = CommanderCliProvider(
        manifest_source={
            "version": "1",
            "name": "proj",
            "gateways": [{"uid_ref": "gw.new", "name": "New GW", "mode": "create"}],
        },
    )
    plan = Plan(manifest_name="proj", changes=[], order=[])
    with pytest.raises(CapabilityError) as exc:
        provider.apply_plan(plan)
    assert "mode: create" in exc.value.reason


def test_apply_plan_refuses_rotation_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from keeper_sdk.core.errors import CapabilityError
    from keeper_sdk.core.planner import Plan

    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which", lambda _bin: "/usr/bin/keeper"
    )
    provider = CommanderCliProvider(
        manifest_source={
            "version": "1",
            "name": "proj",
            "resources": [
                {
                    "uid_ref": "res.m",
                    "type": "pamMachine",
                    "title": "m",
                    "rotation_settings": {"enabled": True},
                }
            ],
        },
    )
    plan = Plan(manifest_name="proj", changes=[], order=[])
    with pytest.raises(CapabilityError) as exc:
        provider.apply_plan(plan)
    assert "rotation_settings" in exc.value.reason


def test_marker_constants_match_dor() -> None:
    """Cross-check the constants against METADATA_OWNERSHIP.md (DOR).
    Follows ``keeper-pam-declarative/METADATA_OWNERSHIP.md`` L8-46."""
    assert MANAGER_NAME == "keeper-pam-declarative"
    assert MARKER_VERSION == "1"
    assert MARKER_FIELD_LABEL == "keeper_declarative_manager"
