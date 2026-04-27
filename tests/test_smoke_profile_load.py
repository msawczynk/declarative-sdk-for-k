from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import identity  # noqa: E402


def test_load_profile_default_returns_default_profile() -> None:
    assert identity.load_profile("default") is identity.DEFAULT_PROFILE


def test_load_profile_reads_profile_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(identity, "PROFILES_DIR", profile_dir)

    payload = {
        "id": "p1",
        "target_email": "msawczyn+sdk-p1@acme-demo.com",
        "ksm_config": str(tmp_path / "ksm-config.json"),
        "admin_commander_config": str(tmp_path / "commander-config.json"),
        "sdktest_commander_config": "scripts/smoke/.commander-config-sdk-p1.json",
        "keeper_server": "keepersecurity.eu",
        "channel_name": "sdk-declarative-p1",
        "password": "example-password",
        "default_admin_record_uid": "ADMIN_UID",
        "sdk_test_login_record_title": "SDK Test — sdk-p1 Login",
    }
    (profile_dir / "p1.json").write_text(json.dumps(payload), encoding="utf-8")

    profile = identity.load_profile("p1")

    assert profile.id == "p1"
    assert profile.target_email == "msawczyn+sdk-p1@acme-demo.com"
    assert profile.ksm_config == tmp_path / "ksm-config.json"
    assert profile.admin_commander_config == tmp_path / "commander-config.json"
    assert profile.sdktest_commander_config == (
        identity.SDK_ROOT / "scripts" / "smoke" / ".commander-config-sdk-p1.json"
    )
    assert profile.keeper_server == "keepersecurity.eu"
    assert profile.channel_name == "sdk-declarative-p1"
    assert profile.password == "example-password"
    assert profile.default_admin_record_uid == "ADMIN_UID"
    assert profile.sdk_test_login_record_title == "SDK Test — sdk-p1 Login"
    assert profile.project_name == "sdk-smoke-p1"
    assert profile.title_prefix == "sdk-smoke-p1"


def test_load_profile_missing_file_mentions_profiles_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(identity, "PROFILES_DIR", profile_dir)

    with pytest.raises(FileNotFoundError, match=r"README\.md § Profiles"):
        identity.load_profile("does-not-exist")
