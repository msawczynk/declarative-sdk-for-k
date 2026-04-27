from __future__ import annotations

import sys
from pathlib import Path

import yaml

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import identity  # noqa: E402
import sandbox  # noqa: E402
import smoke  # noqa: E402


def test_default_profile_matches_legacy_identity_constants() -> None:
    profile = identity.DEFAULT_PROFILE
    lab_root = Path.home() / "Downloads" / "Cursor tests" / "keeper-vault-rbi-pam-testenv"

    assert profile.id == "default"
    assert profile.target_email == "msawczyn+testuser2@acme-demo.com"
    assert profile.ksm_config == lab_root / "ksm-config.json"
    assert profile.admin_commander_config == lab_root / "commander-config.json"
    assert profile.sdktest_commander_config == (
        identity.SDK_ROOT / "scripts" / "smoke" / ".commander-config-testuser2.json"
    )
    assert profile.keeper_server == "keepersecurity.com"
    assert profile.channel_name == "sdk-declarative"
    assert profile.password == "AcmeDemo123!!"
    assert profile.default_admin_record_uid == "MyiZN4cw-wtEIpY1jHlhLw"
    assert profile.sdk_test_login_record_title == "SDK Test — testuser2 Login"
    assert profile.project_name == "sdk-smoke-testuser2"
    assert profile.title_prefix == "sdk-smoke"

    assert identity.KSM_CONFIG == profile.ksm_config
    assert identity.ADMIN_COMMANDER_CONFIG == profile.admin_commander_config
    assert identity.SDKTEST_COMMANDER_CONFIG == profile.sdktest_commander_config
    assert identity.KEEPER_SERVER == profile.keeper_server
    assert identity.TARGET_EMAIL == profile.target_email
    assert identity.ADMIN_CRED_RECORD_UID == profile.default_admin_record_uid
    assert identity.SDK_TEST_LOGIN_RECORD_TITLE == profile.sdk_test_login_record_title
    assert identity.CHANNEL_NAME == profile.channel_name
    assert identity.DEFAULT_PASSWORD == profile.password


def test_default_sandbox_config_matches_legacy_constants() -> None:
    config = sandbox.config_for_profile(identity.DEFAULT_PROFILE)

    assert config.sf_title == "SDK Test (ephemeral)"
    assert config.ksm_app_name == "SDK Test KSM"
    assert config.gateway_name == "Lab GW Rocky"


def test_load_default_profile_returns_singleton() -> None:
    assert identity.load_profile() is identity.DEFAULT_PROFILE
    assert identity.load_profile("default") is identity.DEFAULT_PROFILE


def test_default_smoke_invocation_preserves_legacy_manifest_shape() -> None:
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

    assert document["name"] == "sdk-smoke-testuser2"
    assert [resource["title"] for resource in document["resources"]] == [
        "sdk-smoke-host-1",
        "sdk-smoke-host-2",
    ]
    assert [resource["uid_ref"] for resource in document["resources"]] == [
        "sdk-smoke-host-1",
        "sdk-smoke-host-2",
    ]
