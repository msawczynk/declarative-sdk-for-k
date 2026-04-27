from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import identity  # noqa: E402
import parallel_guard  # noqa: E402
import sandbox  # noqa: E402
import smoke  # noqa: E402

TENANT = "keepersecurity.com"


@pytest.fixture(autouse=True)
def _isolated_guard_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSK_SMOKE_LOCK_DIR", str(tmp_path))
    monkeypatch.delenv("KEEPER_CONFIG", raising=False)


def _profile(
    tmp_path: Path,
    profile_id: str = "p1",
    *,
    admin_config: Path | None = None,
) -> identity.SmokeProfile:
    return identity.SmokeProfile(
        id=profile_id,
        admin_email=f"admin-{profile_id}@example.com",
        target_email=f"target-{profile_id}@example.com",
        ksm_config=tmp_path / profile_id / "ksm-config.json",
        admin_commander_config=admin_config or tmp_path / profile_id / "commander-config.json",
        sdktest_commander_config=tmp_path / profile_id / "testuser-commander-config.json",
        keeper_server=TENANT,
        channel_name=f"sdk-declarative-{profile_id}",
        default_admin_record_uid=f"ADMIN_UID_{profile_id}",
        sdk_test_login_record_title=f"SDK Test {profile_id} Login",
        gateway_name=f"Gateway {profile_id}",
        pam_config_title=f"PAM Configuration {profile_id}",
    )


def _sandbox(profile: identity.SmokeProfile) -> sandbox.SandboxConfig:
    return sandbox.config_for_profile(profile)


def _lock_path(tmp_path: Path, profile_id: str = "p1", tenant: str = TENANT) -> Path:
    tenant_safe = tenant.replace(".", "_")
    return tmp_path / f".dsk-smoke-{tenant_safe}-{profile_id}.lock"


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_lock(
    path: Path,
    *,
    pid: int,
    started_at: str,
    profile_id: str,
    admin_config: Path,
    sf_title: str,
    ksm_app_name: str,
    project_name: str,
    tenant: str = TENANT,
) -> None:
    payload = {
        "pid": pid,
        "started_at": started_at,
        "tenant_fqdn": tenant,
        "profile_id": profile_id,
        "admin_commander_config": str(admin_config.expanduser().resolve()),
        "sf_title": sf_title,
        "ksm_app_name": ksm_app_name,
        "project_name": project_name,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_refuses_default_profile() -> None:
    with pytest.raises(parallel_guard.GuardError, match="default"):
        parallel_guard.preflight_check(
            identity.DEFAULT_PROFILE,
            TENANT,
            sandbox.DEFAULT_SANDBOX_CONFIG,
        )


def test_refuses_default_lab_config(tmp_path: Path) -> None:
    profile = _profile(tmp_path, admin_config=identity.ADMIN_COMMANDER_CONFIG)

    with pytest.raises(parallel_guard.GuardError, match="default lab config"):
        parallel_guard.preflight_check(profile, TENANT, _sandbox(profile))


def test_refuses_admin_config_collision(tmp_path: Path) -> None:
    shared_admin_config = tmp_path / "shared" / "commander-config.json"
    profile2 = _profile(tmp_path, "p2", admin_config=shared_admin_config)
    parallel_guard.acquire(profile2, TENANT, _sandbox(profile2), profile2.project_name)
    profile1 = _profile(tmp_path, "p1", admin_config=shared_admin_config)

    with pytest.raises(parallel_guard.GuardError, match="admin_commander_config collision"):
        parallel_guard.preflight_check(profile1, TENANT, _sandbox(profile1))


def test_refuses_resource_collision(tmp_path: Path) -> None:
    profile2 = _profile(tmp_path, "p2")
    locked_sandbox = sandbox.SandboxConfig(
        sf_title="shared-smoke-folder",
        ksm_app_name="ksm-app-p2",
        gateway_name=sandbox.GATEWAY_NAME,
    )
    parallel_guard.acquire(profile2, TENANT, locked_sandbox, profile2.project_name)
    profile1 = _profile(tmp_path, "p1")
    current_sandbox = sandbox.SandboxConfig(
        sf_title="shared-smoke-folder",
        ksm_app_name="ksm-app-p1",
        gateway_name=sandbox.GATEWAY_NAME,
    )

    with pytest.raises(parallel_guard.GuardError, match="sf_title"):
        parallel_guard.preflight_check(profile1, TENANT, current_sandbox)


def test_refuses_keeper_config_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _profile(tmp_path, admin_config=Path("/etc/bar"))
    monkeypatch.setenv("KEEPER_CONFIG", "/etc/foo")

    with pytest.raises(parallel_guard.GuardError, match="KEEPER_CONFIG"):
        parallel_guard.preflight_check(profile, TENANT, _sandbox(profile))


def test_acquires_and_releases(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    lock_path = parallel_guard.acquire(profile, TENANT, _sandbox(profile), profile.project_name)

    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "pid",
        "started_at",
        "tenant_fqdn",
        "profile_id",
        "admin_commander_config",
        "sf_title",
        "ksm_app_name",
        "project_name",
    }
    assert payload["pid"] == os.getpid()
    assert payload["tenant_fqdn"] == TENANT
    assert payload["profile_id"] == "p1"
    assert payload["admin_commander_config"] == str(
        profile.admin_commander_config.expanduser().resolve()
    )
    assert payload["sf_title"] == "SDK Test (ephemeral) p1"
    assert payload["ksm_app_name"] == "SDK Test KSM p1"
    assert payload["project_name"] == "sdk-smoke-p1"

    parallel_guard.release(lock_path)
    assert not lock_path.exists()


def test_recovers_stale_pid(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    try:
        os.kill(999999, 0)
    except OSError:
        pass
    else:
        pytest.skip("pid 999999 is alive on this machine")
    profile = _profile(tmp_path)
    stale_path = _lock_path(tmp_path)
    cfg = _sandbox(profile)
    _write_lock(
        stale_path,
        pid=999999,
        started_at=_iso_now(),
        profile_id=profile.id,
        admin_config=profile.admin_commander_config,
        sf_title=cfg.sf_title,
        ksm_app_name=cfg.ksm_app_name,
        project_name=profile.project_name,
    )

    caplog.set_level(logging.WARNING, logger="sdk_smoke.parallel_guard")
    lock_path = parallel_guard.acquire(profile, TENANT, cfg, profile.project_name)

    assert lock_path == stale_path
    assert json.loads(lock_path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert "removed stale smoke lock" in caplog.text


def test_refuses_stuck_lock_24h(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    cfg = _sandbox(profile)
    old_started_at = (
        (datetime.now(UTC) - timedelta(hours=25))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_lock(
        _lock_path(tmp_path),
        pid=os.getpid(),
        started_at=old_started_at,
        profile_id=profile.id,
        admin_config=profile.admin_commander_config,
        sf_title=cfg.sf_title,
        ksm_app_name=cfg.ksm_app_name,
        project_name=profile.project_name,
    )

    with pytest.raises(parallel_guard.StaleLockError, match="stuck"):
        parallel_guard.list_active_locks()


def test_refuses_corrupt_lock(tmp_path: Path) -> None:
    _lock_path(tmp_path).write_text('{"pid":', encoding="utf-8")

    with pytest.raises(parallel_guard.GuardError, match="corrupt"):
        parallel_guard.list_active_locks()


def test_atomic_create_collision(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    cfg = _sandbox(profile)
    _write_lock(
        _lock_path(tmp_path),
        pid=os.getpid(),
        started_at=_iso_now(),
        profile_id=profile.id,
        admin_config=profile.admin_commander_config,
        sf_title=cfg.sf_title,
        ksm_app_name=cfg.ksm_app_name,
        project_name=profile.project_name,
    )

    with pytest.raises(parallel_guard.GuardError):
        parallel_guard.acquire(profile, TENANT, cfg, profile.project_name)


def test_smoke_argparse_accepts_parallel_profile_flag() -> None:
    args = smoke._parse_args(["--scenario", "pamMachine", "--parallel-profile", "--profile", "p1"])

    assert args.parallel_profile is True
    assert args.profile == "p1"


def test_lock_filename_sanitizes_fqdn(tmp_path: Path) -> None:
    profile = _profile(tmp_path)

    lock_path = parallel_guard.acquire(profile, TENANT, _sandbox(profile), profile.project_name)

    assert "keepersecurity_com" in lock_path.name


def test_lock_payload_has_no_secrets(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    lock_path = parallel_guard.acquire(profile, TENANT, _sandbox(profile), profile.project_name)
    payload: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))

    forbidden_fields = {"password", "totp", "secret", "token", "session", "config_json"}
    assert forbidden_fields.isdisjoint(payload)
    payload_text = json.dumps(payload)
    assert profile.default_admin_record_uid not in payload_text
