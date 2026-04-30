"""Regression tests: pamConfiguration permission-flag drift is NOT silently dropped.

Covers the full CommonOptions / PamSettings.options flag set:
  connections, tunneling, rotation, remote_browser_isolation,
  graphical_session_recording, text_session_recording,
  ai_threat_detection, ai_terminate_session_on_detection.

Each test builds a live LiveRecord with one flag at the live-state value and a
manifest that declares a *different* value for that flag, then asserts the
diff engine reports ChangeKind.UPDATE (not NOOP).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from keeper_sdk.core import compute_diff, load_manifest
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.models import Manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _live_pam_cfg(
    uid_ref: str,
    manifest_name: str,
    title: str,
    options: dict[str, Any],
) -> LiveRecord:
    """Build a live pam_configuration record with the given options."""
    return LiveRecord(
        keeper_uid="LIVE_CFG_UID",
        title=title,
        resource_type="pam_configuration",
        payload={
            "uid_ref": uid_ref,
            "environment": "local",
            "title": title,
            "options": options,
        },
        marker=encode_marker(
            uid_ref=uid_ref,
            manifest=manifest_name,
            resource_type="pam_configuration",
        ),
    )


def _live_pam_machine(
    uid_ref: str,
    manifest_name: str,
    title: str,
    pam_settings_options: dict[str, Any],
) -> LiveRecord:
    """Build a live pamMachine record with the given pam_settings.options."""
    return LiveRecord(
        keeper_uid="LIVE_MACHINE_UID",
        title=title,
        resource_type="pamMachine",
        payload={
            "uid_ref": uid_ref,
            "type": "pamMachine",
            "title": title,
            "host": "10.0.0.1",
            "pam_settings": {
                "options": pam_settings_options,
                "connection": {"protocol": "ssh"},
            },
        },
        marker=encode_marker(
            uid_ref=uid_ref,
            manifest=manifest_name,
            resource_type="pamMachine",
        ),
    )


def _minimal_pam_cfg_manifest(options: dict[str, Any]) -> Manifest:
    """Build a minimal Manifest containing only a pam_configuration with given options."""
    return Manifest.model_validate(
        {
            "version": "1",
            "name": "drift-test",
            "pam_configurations": [
                {
                    "uid_ref": "cfg.test",
                    "environment": "local",
                    "title": "Test Config",
                    "options": options,
                }
            ],
        }
    )


def _minimal_machine_manifest(pam_settings: dict[str, Any]) -> Manifest:
    """Build a Manifest with one pamMachine with the given pam_settings."""
    return Manifest.model_validate(
        {
            "version": "1",
            "name": "drift-test",
            "pam_configurations": [
                {
                    "uid_ref": "cfg.test",
                    "environment": "local",
                    "title": "Test Config",
                }
            ],
            "resources": [
                {
                    "uid_ref": "res.machine",
                    "type": "pamMachine",
                    "title": "test-machine",
                    "host": "10.0.0.1",
                    "pam_settings": pam_settings,
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# pam_configuration.options drift
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag,live_val,manifest_val",
    [
        ("connections", "on", "off"),
        ("tunneling", "on", "off"),
        ("rotation", "on", "off"),
        ("remote_browser_isolation", "off", "on"),
        ("graphical_session_recording", "off", "on"),
        ("text_session_recording", "off", "on"),
        ("ai_threat_detection", "off", "on"),
        ("ai_terminate_session_on_detection", "off", "on"),
    ],
)
def test_pam_configuration_options_drift_detected(
    flag: str, live_val: str, manifest_val: str
) -> None:
    """Drift in pam_configuration.options.<flag> must surface as UPDATE, not NOOP."""
    manifest = _minimal_pam_cfg_manifest({flag: manifest_val})
    live = [
        _live_pam_cfg(
            uid_ref="cfg.test",
            manifest_name="drift-test",
            title="Test Config",
            options={flag: live_val},
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    cfg_changes = [c for c in changes if c.resource_type == "pam_configuration"]
    assert cfg_changes, "Expected at least one pam_configuration change row"
    cfg_change = cfg_changes[0]
    assert cfg_change.kind is ChangeKind.UPDATE, (
        f"Expected UPDATE for pam_configuration.options.{flag} drift "
        f"(live={live_val!r}, manifest={manifest_val!r}), got {cfg_change.kind}"
    )


def test_pam_configuration_options_noop_when_identical() -> None:
    """Same options on both sides must be NOOP."""
    opts = {
        "connections": "on",
        "tunneling": "on",
        "rotation": "on",
        "remote_browser_isolation": "off",
        "graphical_session_recording": "off",
        "text_session_recording": "off",
        "ai_threat_detection": "off",
        "ai_terminate_session_on_detection": "off",
    }
    manifest = _minimal_pam_cfg_manifest(opts)
    live = [
        _live_pam_cfg(
            uid_ref="cfg.test",
            manifest_name="drift-test",
            title="Test Config",
            options=dict(opts),
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    cfg_changes = [c for c in changes if c.resource_type == "pam_configuration"]
    assert cfg_changes
    assert cfg_changes[0].kind is ChangeKind.NOOP, (
        "Identical options must be NOOP"
    )


# ---------------------------------------------------------------------------
# pamMachine.pam_settings.options drift — flags not in _CONNECTION_TUNING_OPTION_KEYS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag,live_val,manifest_val",
    [
        # Flags handled by pam connection edit
        ("connections", "on", "off"),
        ("graphical_session_recording", "off", "on"),
        ("text_session_recording", "off", "on"),
        # Flags NOT handled by pam connection edit (import-only path)
        ("tunneling", "on", "off"),
        ("rotation", "on", "off"),
        ("remote_browser_isolation", "off", "on"),
        ("ai_threat_detection", "off", "on"),
        ("ai_terminate_session_on_detection", "off", "on"),
    ],
)
def test_pam_machine_pam_settings_options_drift_detected(
    flag: str, live_val: str, manifest_val: str
) -> None:
    """Drift in pamMachine.pam_settings.options.<flag> must surface as UPDATE."""
    manifest = _minimal_machine_manifest(
        {"options": {flag: manifest_val}, "connection": {"protocol": "ssh"}}
    )
    live = [
        _live_pam_machine(
            uid_ref="res.machine",
            manifest_name="drift-test",
            title="test-machine",
            pam_settings_options={flag: live_val},
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    machine_changes = [c for c in changes if c.uid_ref == "res.machine"]
    assert machine_changes, "Expected a change row for res.machine"
    machine_change = machine_changes[0]
    assert machine_change.kind is ChangeKind.UPDATE, (
        f"Expected UPDATE for pamMachine.pam_settings.options.{flag} drift "
        f"(live={live_val!r}, manifest={manifest_val!r}), got {machine_change.kind}"
    )


def test_pam_machine_options_noop_when_commander_injects_unowned_defaults() -> None:
    """Commander-injected option defaults not owned by the manifest must not cause UPDATE.

    P2.1 regression guard: if manifest only sets ``connections`` and Commander
    adds ``tunneling``, ``rotation`` etc. as defaults, re-plan must be NOOP.
    """
    manifest = _minimal_machine_manifest(
        {
            "options": {"connections": "on"},
            "connection": {"protocol": "ssh"},
        }
    )
    # Simulate Commander backfilling extra option defaults post-import.
    live = [
        _live_pam_machine(
            uid_ref="res.machine",
            manifest_name="drift-test",
            title="test-machine",
            pam_settings_options={
                "connections": "on",
                "rotation": "on",          # injected default — not owned
                "tunneling": "on",          # injected default — not owned
                "ai_threat_detection": "off",   # injected default — not owned
                "ai_terminate_session_on_detection": "off",  # injected default
            },
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    machine_changes = [c for c in changes if c.uid_ref == "res.machine"]
    assert machine_changes
    # The manifest only owns "connections: on" which matches live → should be NOOP
    # (extra live keys ignored by overlay match).
    assert machine_changes[0].kind is ChangeKind.NOOP, (
        "Unowned Commander-injected defaults must not trigger UPDATE"
    )
