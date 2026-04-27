"""Live-smoke scenarios — parametrise the smoke run by resource shape.

Each :class:`ScenarioSpec` is the *payload* half of the smoke cycle —
the identity / sandbox / verification / destroy flow is invariant and
lives in ``smoke.py``. Adding a new resource type to the live-smoke
matrix means adding one ``ScenarioSpec`` here, not touching the runner.

A scenario provides:

1. A canonical name (``pamMachine``, ``pamDatabase``, …) used on the
   ``--scenario`` CLI flag and for title namespacing.
2. The Keeper-side primary ``resource_type`` — must match the
   ``keepercommander.commands.pam_import`` accepted strings verbatim
   (see ``docs/CAPABILITY_MATRIX.md``).
3. A ``build_resources(pam_config_uid_ref)`` callable that returns the
   ``resources[]`` fragment for the manifest. Every resource must set
   ``uid_ref``, ``title``, ``type``, and ``pam_configuration_uid_ref``
   — shared by all scenarios — plus whatever type-specific fields the
   upstream schema requires.
4. A ``verify(records)`` callable that inspects discovered live
   records and raises :class:`AssertionError` if the type-specific
   post-apply invariants are violated (e.g. pamDatabase must expose
   ``database_type`` on the managed payload).

The live-smoke runner iterates the registry; unit tests in
``tests/test_smoke_scenarios.py`` validate every scenario's manifest
fragment passes schema + planner without a live tenant.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.metadata import MANAGER_NAME
from keeper_sdk.core.vault_diff import compute_vault_diff

ExpectedRecord = tuple[str, str]
ExpectedVaultRecord = dict[str, str]


@dataclass(frozen=True)
class ScenarioSpec:
    """One live-smoke scenario."""

    name: str
    resource_type: str
    build_resources: Callable[[str, str], list[dict[str, Any]]]
    verify: Callable[[Sequence[Any]], None] = field(default_factory=lambda: _verify_noop)
    description: str = ""

    def expected_records(self, pam_config_uid_ref: str, title_prefix: str) -> list[ExpectedRecord]:
        """Return ``(resource_type, title)`` pairs this scenario should create."""
        return expected_records_from_resources(
            self.build_resources(pam_config_uid_ref, title_prefix)
        )


def _verify_noop(_records: Sequence[Any]) -> None:
    """Default verifier — no type-specific post-apply checks."""


def expected_records_from_resources(resources: Sequence[dict[str, Any]]) -> list[ExpectedRecord]:
    """Flatten top-level resources plus nested ``users[]`` into expected records."""
    expected: list[ExpectedRecord] = []
    for resource in resources:
        expected.append((str(resource["type"]), str(resource["title"])))
        for user in resource.get("users") or []:
            expected.append((str(user["type"]), str(user["title"])))
    return expected


# ---------------------------------------------------------------------------
# Resource builders. Keep them pure: given uid_ref + title_prefix, return
# a deterministic payload list. No tenant state leaks in.


def _machine_resources(pam_config_uid_ref: str, title_prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "uid_ref": f"{title_prefix}-host-1",
            "type": "pamMachine",
            "title": f"{title_prefix}-host-1",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "host": "10.0.0.201",
            "port": "22",
            "ssl_verification": True,
            "operating_system": "Linux",
        },
        {
            "uid_ref": f"{title_prefix}-host-2",
            "type": "pamMachine",
            "title": f"{title_prefix}-host-2",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "host": "10.0.0.202",
            "port": "22",
            "ssl_verification": True,
            "operating_system": "Linux",
        },
    ]


def _database_resources(pam_config_uid_ref: str, title_prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "uid_ref": f"{title_prefix}-db-1",
            "type": "pamDatabase",
            "title": f"{title_prefix}-db-1",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "host": "10.0.0.210",
            "port": "5432",
            "database_type": "postgresql",
            "database_id": "smoke-db",
        },
    ]


def _directory_resources(pam_config_uid_ref: str, title_prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "uid_ref": f"{title_prefix}-dir-1",
            "type": "pamDirectory",
            "title": f"{title_prefix}-dir-1",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "host": "10.0.0.220",
            "port": "389",
            "directory_type": "openldap",
            "directory_id": "smoke-dir",
        },
    ]


def _remote_browser_resources(pam_config_uid_ref: str, title_prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "uid_ref": f"{title_prefix}-rbi-1",
            "type": "pamRemoteBrowser",
            "title": f"{title_prefix}-rbi-1",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "url": "https://example.invalid/smoke",
            "pam_settings": {
                "options": {
                    "remote_browser_isolation": "on",
                    "graphical_session_recording": "on",
                },
                "connection": {
                    "protocol": "http",
                    "allow_url_manipulation": False,
                    "disable_copy": False,
                    "disable_paste": False,
                    "ignore_server_cert": False,
                },
            },
        },
    ]


def _pam_user_nested_resources(pam_config_uid_ref: str, title_prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "uid_ref": f"{title_prefix}-host-with-user",
            "type": "pamMachine",
            "title": f"{title_prefix}-host-with-user",
            "pam_configuration_uid_ref": pam_config_uid_ref,
            "shared_folder": "resources",
            "host": "10.0.0.230",
            "port": "22",
            "ssl_verification": True,
            "operating_system": "Linux",
            "users": [
                {
                    "uid_ref": f"{title_prefix}-pam-user-1",
                    "type": "pamUser",
                    "title": f"{title_prefix}-pam-user-1",
                    "login": "sdk-smoke-user",
                    "password": "offline-smoke-password",
                    "managed": False,
                }
            ],
        },
    ]


def _pam_user_nested_rotation_resources(
    pam_config_uid_ref: str, title_prefix: str
) -> list[dict[str, Any]]:
    resources = _pam_user_nested_resources(pam_config_uid_ref, title_prefix)
    admin_uid_ref = f"{title_prefix}-pam-admin-1"
    resources[0]["pam_settings"] = {
        "options": {"connections": "on", "rotation": "on"},
        "connection": {
            "protocol": "ssh",
            "port": "22",
            "administrative_credentials_uid_ref": admin_uid_ref,
        },
    }
    user = resources[0]["users"][0]
    user["uid_ref"] = admin_uid_ref
    user["title"] = f"{title_prefix}-pam-admin-1"
    user["login"] = "sdk-smoke-admin"
    user["password"] = "offline-smoke-admin-password"
    user["rotation_settings"] = {
        "rotation": "general",
        "enabled": "on",
        "schedule": {"type": "CRON", "cron": "30 18 * * *"},
        "password_complexity": "32,5,5,5,5",
    }
    return resources


# ---------------------------------------------------------------------------
# Post-apply verifiers. Called with discovered LiveRecord list; raise
# AssertionError on type-specific invariant violation.


def _verify_database(records: Sequence[Any]) -> None:
    for record in records:
        if getattr(record, "resource_type", None) != "pamDatabase":
            continue
        payload = getattr(record, "payload", {}) or {}
        if not payload.get("database_type"):
            raise AssertionError(
                f"pamDatabase {record.title} has no database_type in discovered payload"
            )


def _verify_directory(records: Sequence[Any]) -> None:
    for record in records:
        if getattr(record, "resource_type", None) != "pamDirectory":
            continue
        payload = getattr(record, "payload", {}) or {}
        if not payload.get("directory_type"):
            raise AssertionError(
                f"pamDirectory {record.title} has no directory_type in discovered payload"
            )


def _verify_remote_browser(records: Sequence[Any]) -> None:
    for record in records:
        if getattr(record, "resource_type", None) != "pamRemoteBrowser":
            continue
        payload = getattr(record, "payload", {}) or {}
        options = (payload.get("pam_settings") or {}).get("options") or {}
        if options.get("remote_browser_isolation") != "on":
            raise AssertionError(
                f"pamRemoteBrowser {record.title} did not retain remote_browser_isolation=on"
            )


def _verify_pam_user_nested(records: Sequence[Any]) -> None:
    seen_pam_user = False
    for record in records:
        if getattr(record, "resource_type", None) != "pamUser":
            continue
        seen_pam_user = True
        payload = getattr(record, "payload", {}) or {}
        if not payload.get("login"):
            raise AssertionError(f"pamUser {record.title} has no login in discovered payload")
    if not seen_pam_user:
        raise AssertionError("nested pamUser record was not discovered")


# ---------------------------------------------------------------------------
# Registry — canonical source of what lives in the live-smoke matrix.


_SCENARIOS: dict[str, ScenarioSpec] = {
    "pamMachine": ScenarioSpec(
        name="pamMachine",
        resource_type="pamMachine",
        build_resources=_machine_resources,
        description=(
            "Two-host Linux machine cycle. The legacy smoke default; every "
            "other scenario diffs against this one."
        ),
    ),
    "pamDatabase": ScenarioSpec(
        name="pamDatabase",
        resource_type="pamDatabase",
        build_resources=_database_resources,
        verify=_verify_database,
        description="Postgres database cycle with database_type + database_id.",
    ),
    "pamDirectory": ScenarioSpec(
        name="pamDirectory",
        resource_type="pamDirectory",
        build_resources=_directory_resources,
        verify=_verify_directory,
        description="OpenLDAP directory cycle with directory_type + directory_id.",
    ),
    "pamRemoteBrowser": ScenarioSpec(
        name="pamRemoteBrowser",
        resource_type="pamRemoteBrowser",
        build_resources=_remote_browser_resources,
        verify=_verify_remote_browser,
        description=(
            "HTTP RBI cycle with session recording + isolation toggled on. "
            "Exercises the pam_settings.options/connection sub-schemas."
        ),
    ),
    "pamUserNested": ScenarioSpec(
        name="pamUserNested",
        resource_type="pamMachine",
        build_resources=_pam_user_nested_resources,
        verify=_verify_pam_user_nested,
        description=(
            "Nested pamUser shape: a Linux machine with resources[].users[]. "
            "Offline gate proves schema/model/planner/normalize support without "
            "claiming standalone top-level pamUser live support."
        ),
    ),
    "pamUserNestedRotation": ScenarioSpec(
        name="pamUserNestedRotation",
        resource_type="pamMachine",
        build_resources=_pam_user_nested_rotation_resources,
        verify=_verify_pam_user_nested,
        description=(
            "Experimental nested admin pamUser rotation shape with the parent "
            "admin credential bound through pam_settings.connection. Requires "
            "DSK_PREVIEW plus DSK_EXPERIMENTAL_ROTATION_APPLY; not a live "
            "support claim."
        ),
    ),
}


@dataclass(frozen=True)
class VaultScenarioSpec:
    name: str
    family: str  # always "keeper-vault.v1" for this class
    build_manifest: Callable[[str, str], dict[str, Any]]
    expected_records: Callable[[str], list[ExpectedVaultRecord]]
    verify: Callable[[Any, Sequence[Any], str], None]
    description: str = ""


def _generate_throwaway_password() -> str:
    return secrets.token_urlsafe(16)


def _vault_one_login_manifest(title_prefix: str, sf_uid: str) -> dict[str, Any]:
    del sf_uid
    return {
        "schema": "keeper-vault.v1",
        "records": [
            {
                "uid_ref": f"{title_prefix}-vault-one",
                "type": "login",
                "title": f"{title_prefix}-vault-one",
                "fields": [
                    {"type": "login", "label": "Login", "value": ["smoke@example.invalid"]},
                    {
                        "type": "password",
                        "label": "Password",
                        "value": [_generate_throwaway_password()],
                    },
                ],
            }
        ],
    }


def _vault_one_login_expected_records(title_prefix: str) -> list[ExpectedVaultRecord]:
    return [
        {
            "resource_type": "login",
            "title": f"{title_prefix}-vault-one",
            "uid_ref": f"{title_prefix}-vault-one",
        }
    ]


def _verify_vault_one_login(manifest: Any, live_records: Sequence[Any], title_prefix: str) -> None:
    expected_title = f"{title_prefix}-vault-one"
    owned = [
        record
        for record in live_records
        if (getattr(record, "marker", None) or {}).get("manager") == MANAGER_NAME
    ]
    if len(owned) != 1:
        raise AssertionError(f"expected exactly 1 SDK-owned vault record, found {len(owned)}")

    record = owned[0]
    got_pair = (getattr(record, "resource_type", None), getattr(record, "title", None))
    if got_pair != ("login", expected_title):
        raise AssertionError(f"expected managed login {expected_title!r}, found {got_pair!r}")

    marker = getattr(record, "marker", None) or {}
    if marker.get("resource_type") != "login":
        raise AssertionError(
            f"vault marker resource_type is not login: {marker.get('resource_type')!r}"
        )

    changes = compute_vault_diff(
        manifest,
        list(live_records),
        manifest_name=f"{title_prefix}-vaultOneLogin",
    )
    blocking = [
        change
        for change in changes
        if change.kind in (ChangeKind.CREATE, ChangeKind.UPDATE, ChangeKind.CONFLICT)
    ]
    if blocking:
        summary = [(change.kind.value, change.title, change.reason) for change in blocking]
        raise AssertionError(f"vaultOneLogin verifier found drift/conflict rows: {summary}")


_VAULT_SCENARIOS: dict[str, VaultScenarioSpec] = {
    "vaultOneLogin": VaultScenarioSpec(
        name="vaultOneLogin",
        family="keeper-vault.v1",
        build_manifest=_vault_one_login_manifest,
        expected_records=_vault_one_login_expected_records,
        verify=_verify_vault_one_login,
        description="Single keeper-vault.v1 login record with Login + Password scalar fields.",
    )
}


def get(name: str) -> ScenarioSpec:
    """Look up a scenario by name; raise :class:`KeyError` if absent.

    Names are the canonical Keeper resource types (``pamMachine`` etc.)
    so the ``--scenario`` CLI flag reads naturally.
    """
    try:
        return _SCENARIOS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_SCENARIOS))
        raise KeyError(f"unknown smoke scenario {name!r}; available: {available}") from exc


def names() -> list[str]:
    """Return all registered scenario names, sorted alphabetically."""
    return sorted(_SCENARIOS)


def all_scenarios() -> list[ScenarioSpec]:
    """Return every registered scenario in name order."""
    return [_SCENARIOS[name] for name in names()]


def vault_get(name: str) -> VaultScenarioSpec:
    """Look up a vault scenario by name; raise :class:`KeyError` if absent."""
    try:
        return _VAULT_SCENARIOS[name]
    except KeyError as exc:
        available = ", ".join(sorted(_VAULT_SCENARIOS))
        raise KeyError(f"unknown vault smoke scenario {name!r}; available: {available}") from exc


def vault_names() -> list[str]:
    """Return all registered vault scenario names, sorted alphabetically."""
    return sorted(_VAULT_SCENARIOS)


def all_vault_scenarios() -> list[VaultScenarioSpec]:
    """Return every registered vault scenario in name order."""
    return [_VAULT_SCENARIOS[name] for name in vault_names()]


@dataclass(frozen=True)
class SharingScenarioSpec:
    """One keeper-vault-sharing.v1 live-smoke scenario.

    V8b wires this into the harness; keep it out of the PAM/vault registries here.
    """

    name: str
    family: str
    resources_factory: Callable[[str, str], list[dict[str, Any]]]
    verifier: Callable[[Sequence[Any]], None]
    description: str = ""


def _sharing_lifecycle_context(primary: str, secondary: str | None) -> tuple[str, str]:
    default_grantee = "smoke@example.invalid"
    if secondary is None:
        return primary, default_grantee
    if "@" in primary and "@" not in secondary:
        return secondary, primary
    if "@" in secondary:
        return primary, secondary
    if secondary.startswith("sdk-smoke") and not primary.startswith("sdk-smoke"):
        return secondary, default_grantee
    return primary, default_grantee


def _sharing_lifecycle_resources(
    primary: str, secondary: str | None = None
) -> list[dict[str, Any]]:
    title_prefix, grantee_email = _sharing_lifecycle_context(primary, secondary)
    folder_uid_ref = f"{title_prefix}-sharing-folder"
    shared_folder_uid_ref = f"{title_prefix}-sharing-shared-folder"
    record_uid_ref = f"{title_prefix}-sharing-record"

    return [
        {
            "resource_type": "sharing_folder",
            "uid_ref": folder_uid_ref,
            "path": f"/{title_prefix}/sharing-user-folder",
            "color": "blue",
        },
        {
            "resource_type": "sharing_shared_folder",
            "uid_ref": shared_folder_uid_ref,
            "path": f"/{title_prefix}/sharing-shared-folder",
            "defaults": {
                "manage_users": False,
                "manage_records": True,
                "can_edit": True,
                "can_share": False,
            },
        },
        {
            "resource_type": "login",
            "uid_ref": record_uid_ref,
            "type": "login",
            "title": f"{title_prefix}-sharing-login",
            "folder_ref": f"keeper-vault-sharing:folders:{folder_uid_ref}",
            "fields": [
                {"type": "login", "label": "Login", "value": ["sharing@example.invalid"]},
                {
                    "type": "password",
                    "label": "Password",
                    "value": [_generate_throwaway_password()],
                },
            ],
        },
        {
            "resource_type": "sharing_record_share",
            "uid_ref": f"{title_prefix}-sharing-record-share",
            "record_uid_ref": f"keeper-vault:records:{record_uid_ref}",
            "user_email": grantee_email,
            "permissions": {"can_edit": False, "can_share": False},
        },
        {
            "resource_type": "sharing_share_folder",
            "kind": "default",
            "uid_ref": f"{title_prefix}-sharing-default-share",
            "shared_folder_uid_ref": (
                f"keeper-vault-sharing:shared_folders:{shared_folder_uid_ref}"
            ),
            "target": "grantee",
            "permissions": {"manage_records": True, "manage_users": False},
        },
    ]


def _sharing_payload(record: Any) -> dict[str, Any]:
    raw_payload = (
        record.get("payload") if isinstance(record, dict) else getattr(record, "payload", None)
    )
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(record, dict):
        return record
    return {}


def _sharing_marker(record: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker

    raw_marker = (
        record.get("marker") if isinstance(record, dict) else getattr(record, "marker", None)
    )
    if isinstance(raw_marker, dict):
        return raw_marker
    if isinstance(raw_marker, str):
        return decode_marker(raw_marker)

    custom_fields = payload.get("custom_fields") or payload.get("custom") or {}
    if isinstance(custom_fields, dict):
        raw_marker = custom_fields.get(MARKER_FIELD_LABEL)
        if isinstance(raw_marker, dict):
            return raw_marker
        if isinstance(raw_marker, str):
            return decode_marker(raw_marker)
    return None


def _sharing_value(
    record: Any, payload: dict[str, Any], marker: dict[str, Any] | None, key: str
) -> Any:
    if isinstance(record, dict) and key in record:
        return record[key]
    value = getattr(record, key, None)
    if value is not None:
        return value
    if key in payload:
        return payload[key]
    return (marker or {}).get(key)


def _sharing_grantee_identifier(payload: dict[str, Any]) -> str | None:
    for key in ("user_email", "team_uid_ref", "grantee_identifier", "identifier"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    grantee = payload.get("grantee")
    if isinstance(grantee, dict):
        for key in ("user_email", "team_uid_ref"):
            value = grantee.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _verify_sharing_lifecycle(records: Sequence[Any]) -> None:
    folder_marker_seen = False
    shared_folder_seen = False
    record_share_grantee_seen = False
    share_folder_seen = False

    for record in records:
        payload = _sharing_payload(record)
        marker = _sharing_marker(record, payload)
        resource_type = _sharing_value(record, payload, marker, "resource_type")

        if resource_type == "sharing_folder" and marker:
            marker_manager = marker.get("manager")
            if marker_manager in (None, MANAGER_NAME):
                folder_marker_seen = True
        elif resource_type == "sharing_shared_folder":
            shared_folder_seen = True
        elif resource_type == "sharing_record_share":
            record_uid_ref = payload.get("record_uid_ref")
            if record_uid_ref and _sharing_grantee_identifier(payload):
                record_share_grantee_seen = True
        elif resource_type == "sharing_share_folder":
            kind = payload.get("kind")
            if kind in (None, "default") or payload.get("target") == "grantee":
                share_folder_seen = True

    missing: list[str] = []
    if not folder_marker_seen:
        missing.append("sharing_folder marker")
    if not shared_folder_seen:
        missing.append("sharing_shared_folder")
    if not record_share_grantee_seen:
        missing.append("sharing_record_share grantee")
    if not share_folder_seen:
        missing.append("sharing_share_folder")
    if missing:
        raise AssertionError(f"vaultSharingLifecycle verifier missing: {', '.join(missing)}")


VAULT_SHARING_LIFECYCLE = SharingScenarioSpec(
    name="vaultSharingLifecycle",
    family="keeper-vault-sharing.v1",
    resources_factory=_sharing_lifecycle_resources,
    verifier=_verify_sharing_lifecycle,
    description=(
        "Sharing lifecycle fixture with one user folder, one shared folder, "
        "one vault login record, one direct record share, and one default "
        "shared-folder share row."
    ),
)
