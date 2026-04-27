from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import identity  # noqa: E402


def test_load_profile_default_returns_default_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(identity.EXTERNAL_PROFILE_ENV, raising=False)
    monkeypatch.setattr(identity, "DEFAULT_PROFILE_PATH", tmp_path / "missing.json")

    assert identity.load_profile("default") is identity.DEFAULT_PROFILE


def test_load_profile_reads_profile_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path = tmp_path / "profile.json"
    monkeypatch.setenv(identity.EXTERNAL_PROFILE_ENV, str(profile_path))

    payload = {
        "id": "p1",
        "admin_email": "admin-p1@example.com",
        "target_email": "target-p1@example.com",
        "ksm_config": str(tmp_path / "ksm-config.json"),
        "admin_commander_config": str(tmp_path / "commander-config.json"),
        "sdktest_commander_config": "scripts/smoke/.commander-config-target-p1.json",
        "keeper_server": "keepersecurity.eu",
        "channel_name": "sdk-declarative-p1",
        "default_admin_record_uid": "ADMIN_UID",
        "sdk_test_login_record_title": "SDK Test Target Login",
        "gateway_name": "Example Gateway",
        "pam_config_title": "Example PAM Configuration",
    }
    profile_path.write_text(json.dumps(payload), encoding="utf-8")

    profile = identity.load_profile("p1")

    assert profile.id == "p1"
    assert profile.admin_email == "admin-p1@example.com"
    assert profile.target_email == "target-p1@example.com"
    assert profile.ksm_config == tmp_path / "ksm-config.json"
    assert profile.admin_commander_config == tmp_path / "commander-config.json"
    assert profile.sdktest_commander_config == (
        identity.SDK_ROOT / "scripts" / "smoke" / ".commander-config-target-p1.json"
    )
    assert profile.keeper_server == "keepersecurity.eu"
    assert profile.channel_name == "sdk-declarative-p1"
    assert profile.default_admin_record_uid == "ADMIN_UID"
    assert profile.sdk_test_login_record_title == "SDK Test Target Login"
    assert profile.gateway_name == "Example Gateway"
    assert profile.pam_config_title == "Example PAM Configuration"
    assert not hasattr(profile, "password")
    assert profile.project_name == "sdk-smoke-p1"
    assert profile.title_prefix == "sdk-smoke-p1"


def test_load_profile_missing_file_mentions_profiles_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(identity.EXTERNAL_PROFILE_ENV, str(tmp_path / "missing.json"))

    with pytest.raises(FileNotFoundError, match=r"README\.md § Profiles"):
        identity.load_profile("does-not-exist")
