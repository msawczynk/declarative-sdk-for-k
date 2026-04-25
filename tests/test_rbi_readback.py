"""Tests for pamRemoteBrowser discover readback and diff semantics."""

from __future__ import annotations

from keeper_sdk.core.diff import ChangeKind, compute_diff
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.models import Manifest
from keeper_sdk.providers._commander_cli_helpers import (
    _merge_rbi_dag_options_into_pam_settings,
    _record_from_get,
)


def test_record_from_get_merges_pam_remote_browser_settings() -> None:
    item = {
        "record_uid": "abc22abc22abc22abc22",
        "title": "rbi-1",
        "type": "pamRemoteBrowser",
        "fields": [
            {
                "type": "pamRemoteBrowserSettings",
                "value": [
                    {
                        "connection": {
                            "protocol": "http",
                            "httpCredentialsUid": "loginuid22loginuid22",
                            "allowUrlManipulation": False,
                        }
                    }
                ],
            }
        ],
        "custom": [],
    }
    listing = {
        "type": "record",
        "uid": "abc22abc22abc22abc22",
        "folder_uid": "folduid22folduid22folduid22",
    }
    rec = _record_from_get(item, listing_entry=listing)
    assert rec is not None
    ps = rec.payload.get("pam_settings") or {}
    conn = ps.get("connection") or {}
    assert conn.get("protocol") == "http"
    assert conn.get("autofill_credentials_uid_ref") == "loginuid22loginuid22"
    assert conn.get("allow_url_manipulation") is False


def test_merge_rbi_dag_options_skips_default_and_empty() -> None:
    ps: dict = {"options": {"remote_browser_isolation": "on"}}
    _merge_rbi_dag_options_into_pam_settings(ps, connections="default", session_recording=None)
    assert ps["options"]["remote_browser_isolation"] == "on"
    assert "graphical_session_recording" not in ps["options"]

    ps2: dict = {}
    _merge_rbi_dag_options_into_pam_settings(ps2, connections="", session_recording="default")
    assert "remote_browser_isolation" not in ps2.get("options", {})
    assert "graphical_session_recording" not in ps2.get("options", {})


def test_merge_rbi_dag_options_sets_both_tristates() -> None:
    ps: dict = {}
    _merge_rbi_dag_options_into_pam_settings(ps, connections="on", session_recording="off")
    assert ps["options"]["remote_browser_isolation"] == "on"
    assert ps["options"]["graphical_session_recording"] == "off"


def test_compute_diff_pam_remote_browser_partial_pam_settings() -> None:
    manifest = Manifest.model_validate(
        {
            "version": "1",
            "name": "smoke",
            "pam_configurations": [
                {
                    "uid_ref": "cfg1",
                    "environment": "local",
                    "title": "Cfg",
                    "gateway_uid_ref": "gw1",
                    "options": {
                        "connections": "on",
                        "rotation": "on",
                        "tunneling": "on",
                        "remote_browser_isolation": "on",
                        "graphical_session_recording": "on",
                        "text_session_recording": "off",
                        "ai_threat_detection": "off",
                        "ai_terminate_session_on_detection": "off",
                    },
                }
            ],
            "resources": [
                {
                    "uid_ref": "rbi1",
                    "type": "pamRemoteBrowser",
                    "title": "rbi-1",
                    "pam_configuration_uid_ref": "cfg1",
                    "url": "https://example.com/x",
                    "pam_settings": {
                        "options": {
                            "remote_browser_isolation": "on",
                            "graphical_session_recording": "on",
                        },
                        "connection": {"protocol": "http", "allow_url_manipulation": False},
                    },
                }
            ],
        }
    )
    marker = encode_marker(uid_ref="rbi1", manifest="smoke", resource_type="pamRemoteBrowser")
    cfg_marker = encode_marker(uid_ref="cfg1", manifest="smoke", resource_type="pam_configuration")
    live = [
        LiveRecord(
            keeper_uid="CONFIGUIDCONFIGUIDCONFIGUID",
            title="Cfg",
            resource_type="pam_configuration",
            folder_uid=None,
            payload={"title": "Cfg"},
            marker=cfg_marker,
        ),
        LiveRecord(
            keeper_uid="RBIRBIRBIRBIRBIRBIRBIRBI",
            title="rbi-1",
            resource_type="pamRemoteBrowser",
            folder_uid=None,
            payload={
                "title": "rbi-1",
                "type": "pamRemoteBrowser",
                "url": "https://example.com/x",
                "pam_settings": {
                    "options": {
                        "remote_browser_isolation": "on",
                        "graphical_session_recording": "on",
                    },
                    "connection": {"protocol": "http", "allow_url_manipulation": False},
                },
            },
            marker=marker,
        ),
    ]
    changes = compute_diff(manifest, live)
    rbi_changes = [c for c in changes if c.resource_type == "pamRemoteBrowser"]
    assert len(rbi_changes) == 1
    assert rbi_changes[0].kind is ChangeKind.NOOP
