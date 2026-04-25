"""Preview-gate behaviour.

Pins three invariants:

1. With ``DSK_PREVIEW`` unset, a manifest carrying a preview key
   (``rotation_settings``, ``jit_settings``, gateway ``mode: create``,
   ``default_rotation_schedule``) is rejected at load time with
   :class:`SchemaError` and a remediation that names the env var.
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


@pytest.fixture
def preview_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PREVIEW_ENV_VAR, raising=False)


@pytest.fixture
def preview_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PREVIEW_ENV_VAR, "1")


def test_gate_rejects_preview_key_without_opt_in(preview_disabled: None) -> None:
    with pytest.raises(SchemaError) as exc:
        load_manifest_string(_MANIFEST_WITH_ROTATION, suffix=".yaml")
    message = str(exc.value)
    assert "preview" in message.lower()
    assert "rotation_settings" in message
    assert PREVIEW_ENV_VAR in message


def test_gate_accepts_preview_key_with_opt_in(preview_enabled: None) -> None:
    manifest = load_manifest_string(_MANIFEST_WITH_ROTATION, suffix=".yaml")
    assert manifest.resources[0].uid_ref == "res-db"


def test_gate_is_noop_for_clean_manifest(preview_disabled: None) -> None:
    manifest = load_manifest_string(_MANIFEST_CLEAN, suffix=".yaml")
    assert manifest.resources[0].uid_ref == "res-db"


def test_detector_is_pure_and_ignores_env(preview_enabled: None) -> None:
    hits = detect_preview_keys(
        {
            "gateways": [{"uid_ref": "gw.new", "mode": "create"}],
            "resources": [{"users": [{"rotation_settings": {}}]}],
        }
    )
    joined = " ".join(hits)
    assert "mode: create" in joined
    assert "rotation_settings" in joined


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
    assert_preview_keys_allowed({"resources": [{"type": "pamMachine"}]})
    assert os.environ.get(PREVIEW_ENV_VAR) is None
