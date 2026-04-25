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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

ExpectedRecord = tuple[str, str]


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
