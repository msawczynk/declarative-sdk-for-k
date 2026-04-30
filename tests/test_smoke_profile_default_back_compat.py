from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import identity  # noqa: E402
import sandbox  # noqa: E402
import smoke  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "profiles" / "example-profile.json"


def _assert_email_or_placeholder(value: str, placeholder: str) -> None:
    assert isinstance(value, str)
    assert value == placeholder or "@" in value


def _assert_profile_contract(profile: identity.SmokeProfile) -> None:
    assert isinstance(profile.id, str) and profile.id
    _assert_email_or_placeholder(profile.admin_email, "admin@example.com")
    _assert_email_or_placeholder(profile.target_email, "target@example.com")
    assert isinstance(profile.ksm_config, Path)
    assert isinstance(profile.admin_commander_config, Path)
    assert isinstance(profile.sdktest_commander_config, Path)
    assert profile.keeper_server
    assert profile.channel_name
    assert profile.default_admin_record_uid
    assert profile.sdk_test_login_record_title
    assert profile.gateway_name
    assert profile.pam_config_title
    assert not hasattr(profile, "password")


def test_default_profile_shape_uses_placeholder_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(identity.EXTERNAL_PROFILE_ENV, raising=False)
    monkeypatch.setattr(identity, "DEFAULT_PROFILE_PATH", tmp_path / "missing.json")

    profile = identity.load_profile()

    assert profile is identity.DEFAULT_PROFILE
    _assert_profile_contract(profile)
    assert profile.admin_email == "admin@example.com"
    assert profile.target_email == "target@example.com"
    assert profile.default_admin_record_uid == "<ADMIN_RECORD_UID>"
    assert profile.gateway_name == "<gateway-name>"
    assert profile.pam_config_title == "<pam-config-name>"

    assert identity.KSM_CONFIG == profile.ksm_config
    assert identity.ADMIN_COMMANDER_CONFIG == profile.admin_commander_config
    assert identity.SDKTEST_COMMANDER_CONFIG == profile.sdktest_commander_config
    assert identity.KEEPER_SERVER == profile.keeper_server
    assert identity.TARGET_EMAIL == profile.target_email
    assert identity.ADMIN_CRED_RECORD_UID == profile.default_admin_record_uid
    assert identity.SDK_TEST_LOGIN_RECORD_TITLE == profile.sdk_test_login_record_title
    assert identity.CHANNEL_NAME == profile.channel_name


def test_example_profile_fixture_matches_shape(monkeypatch) -> None:
    monkeypatch.setenv(identity.EXTERNAL_PROFILE_ENV, str(_FIXTURE))

    profile = identity.load_profile()

    _assert_profile_contract(profile)
    assert profile.id == "default"


def test_default_sandbox_config_uses_profile_gateway() -> None:
    config = sandbox.config_for_profile(identity.DEFAULT_PROFILE)

    assert config.sf_title == "SDK Test (ephemeral)"
    assert config.ksm_app_name == "SDK Test KSM"
    assert config.gateway_name == identity.DEFAULT_PROFILE.gateway_name


def test_load_default_profile_returns_singleton(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(identity.EXTERNAL_PROFILE_ENV, raising=False)
    monkeypatch.setattr(identity, "DEFAULT_PROFILE_PATH", tmp_path / "missing.json")

    assert identity.load_profile() is identity.DEFAULT_PROFILE
    assert identity.load_profile("default") is identity.DEFAULT_PROFILE


def test_fixture_has_no_password_field() -> None:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    assert "password" not in raw


def test_default_smoke_manifest_uses_profile_identity() -> None:
    args = smoke._parse_args(["--scenario", "pamMachine"])
    profile = identity.load_profile(args.profile)
    context = smoke.SmokeRunContext(profile=profile, node_uid=args.node_uid)
    previous = smoke._ACTIVE_SCENARIO
    smoke._ACTIVE_SCENARIO = smoke.smoke_scenarios.get(args.scenario)

    try:
        manifest_path = smoke._write_manifest("unused", context=context)
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    finally:
        smoke._ACTIVE_SCENARIO = previous
        if "manifest_path" in locals():
            manifest_path.unlink(missing_ok=True)

    assert document["name"] == profile.project_name
    assert document["gateways"][0]["name"] == profile.gateway_name
    assert document["pam_configurations"][0]["title"] == profile.pam_config_title
    assert all(
        resource["title"].startswith(profile.title_prefix) for resource in document["resources"]
    )
