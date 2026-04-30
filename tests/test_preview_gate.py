"""Preview-gate behaviour.

Pins three invariants:

1. With ``DSK_PREVIEW`` unset, a manifest carrying a preview key
   (unsupported rotation locations, ``default_rotation_schedule``,
   top-level ``projects[]``) is
   rejected at load time with :class:`SchemaError` and a remediation that
   names the env var.
2. With ``DSK_PREVIEW=1``, the same manifest loads cleanly.
3. The detector is pure and does not consult the env var.

Regression: without these, the only signal that a preview key is a
no-op is a ``CONFLICT`` row at plan time, which operators miss until
apply.
"""

from __future__ import annotations

import os

import pytest

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.manifest import load_manifest_string
from keeper_sdk.core.preview import (
    PREVIEW_ENV_VAR,
    assert_preview_keys_allowed,
    detect_preview_keys,
    preview_is_enabled,
)

_MANIFEST_WITH_ROTATION = """\
version: "1"
name: rot
shared_folders:
  resources:
    uid_ref: sf-res
gateways:
  - uid_ref: gw
    name: gw
    mode: reference_existing
resources:
  - uid_ref: res-db
    type: pamMachine
    title: DB
    shared_folder: resources
    host: db.example.com
    users:
      - uid_ref: res-db-root
        type: pamUser
        title: db-root
        login: root
        password: x
        rotation_settings:
          rotation: general
          enabled: "on"
"""

_MANIFEST_CLEAN = """\
version: "1"
name: clean
shared_folders:
  resources:
    uid_ref: sf-res
gateways:
  - uid_ref: gw
    name: gw
    mode: reference_existing
resources:
  - uid_ref: res-db
    type: pamMachine
    title: DB
    shared_folder: resources
    host: db.example.com
"""

_MANIFEST_WITH_GATEWAY_CREATE = """\
version: "1"
name: gateway-create
gateways:
  - uid_ref: gw-new
    name: gw-new
    mode: create
    ksm_application_name: sdk-test-ksm
"""

_MANIFEST_WITH_PROJECTS = """\
version: "1"
name: project-shape
projects:
  - uid_ref: proj.lab
    project: project-shape
"""


@pytest.fixture
def preview_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PREVIEW_ENV_VAR, raising=False)


@pytest.fixture
def preview_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PREVIEW_ENV_VAR, "1")


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        (_MANIFEST_WITH_PROJECTS, "top-level projects[]"),
    ],
)
def test_gate_rejects_preview_key_without_opt_in(
    preview_disabled: None, raw: str, needle: str
) -> None:
    with pytest.raises(SchemaError) as exc:
        load_manifest_string(raw, suffix=".yaml")
    message = str(exc.value)
    assert "preview" in message.lower()
    assert needle in message
    assert PREVIEW_ENV_VAR in message


@pytest.mark.parametrize(
    ("raw", "expected_ref"),
    [
        (_MANIFEST_WITH_ROTATION, "res-db"),
        (_MANIFEST_WITH_GATEWAY_CREATE, "gw-new"),
        (_MANIFEST_WITH_PROJECTS, "proj.lab"),
    ],
)
def test_gate_accepts_preview_key_with_opt_in(
    preview_enabled: None, raw: str, expected_ref: str
) -> None:
    manifest = load_manifest_string(raw, suffix=".yaml")
    refs = {uid_ref for uid_ref, _kind in manifest.iter_uid_refs()}
    assert expected_ref in refs


def test_gateway_create_is_supported_without_preview(preview_disabled: None) -> None:
    manifest = load_manifest_string(_MANIFEST_WITH_GATEWAY_CREATE, suffix=".yaml")

    assert manifest.gateways[0].mode == "create"
    assert manifest.gateways[0].ksm_application_name == "sdk-test-ksm"


def test_nested_rotation_is_supported_without_preview(preview_disabled: None) -> None:
    manifest = load_manifest_string(_MANIFEST_WITH_ROTATION, suffix=".yaml")

    resource = manifest.resources[0]
    assert resource.users
    assert resource.users[0].rotation_settings is not None


def test_gate_is_noop_for_clean_manifest(preview_disabled: None) -> None:
    manifest = load_manifest_string(_MANIFEST_CLEAN, suffix=".yaml")
    assert manifest.resources[0].uid_ref == "res-db"


def test_detector_is_pure_and_ignores_env(preview_enabled: None) -> None:
    hits = detect_preview_keys(
        {
            "gateways": [{"uid_ref": "gw.new", "mode": "create"}],
            "projects": [{"uid_ref": "proj.lab", "project": "lab"}],
            "users": [{"uid_ref": "usr.top", "rotation_settings": {}}],
        }
    )
    joined = " ".join(hits)
    assert "mode: create" not in joined
    assert "top-level projects[]" in joined
    assert "rotation_settings" in joined


def test_detector_ignores_supported_nested_rotation(preview_disabled: None) -> None:
    hits = detect_preview_keys(
        {
            "resources": [
                {
                    "uid_ref": "res.db",
                    "type": "pamMachine",
                    "users": [{"uid_ref": "usr.db", "rotation_settings": {}}],
                }
            ],
        }
    )

    assert hits == []


def test_detector_uses_exact_keys_for_default_rotation(preview_enabled: None) -> None:
    hits = detect_preview_keys(
        {
            "pam_configurations": [
                {
                    "default_rotation_schedule": {
                        "type": "CRON",
                        "cron": "30 18 * * *",
                    }
                }
            ]
        }
    )

    assert hits == ["pam_configurations[].default_rotation_schedule (planned for 1.1)"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("", False),
        ("anything-else", False),
    ],
)
def test_env_var_truthiness(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv(PREVIEW_ENV_VAR, value)
    assert preview_is_enabled() is expected


def test_assert_helper_matches_gate(preview_disabled: None) -> None:
    # Direct call raises for preview-containing docs, no-ops for clean ones
    with pytest.raises(SchemaError):
        assert_preview_keys_allowed({"users": [{"rotation_settings": {}}]})
    assert_preview_keys_allowed(
        {"resources": [{"type": "pamMachine", "users": [{"rotation_settings": {}}]}]}
    )
    assert os.environ.get(PREVIEW_ENV_VAR) is None
