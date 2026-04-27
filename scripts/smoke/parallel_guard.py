#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import identity
import sandbox

ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE_VERSION = 1

_LOCK_GLOB = ".dsk-smoke-*.lock"
_STUCK_LOCK_AFTER = timedelta(hours=24)

log = logging.getLogger("sdk_smoke.parallel_guard")


class GuardError(Exception):
    pass


class StaleLockError(GuardError):
    pass


@dataclass(frozen=True)
class LockInfo:
    pid: int
    started_at: str
    tenant_fqdn: str
    profile_id: str
    admin_commander_config: str
    sf_title: str
    ksm_app_name: str
    project_name: str


def lock_dir() -> Path:
    override = os.environ.get("DSK_SMOKE_LOCK_DIR")
    if override:
        return Path(override).expanduser()
    return ROOT / ".dsk-smoke-locks"


def list_active_locks() -> list[LockInfo]:
    directory = lock_dir()
    if not directory.exists():
        return []

    locks: list[LockInfo] = []
    for path in sorted(directory.glob(_LOCK_GLOB)):
        info, started_at = _read_lock(path)
        if not _pid_alive(info.pid):
            _remove_stale_lock(path, info)
            continue
        if datetime.now(UTC) - started_at > _STUCK_LOCK_AFTER:
            raise StaleLockError(
                f"stuck lock {path}: pid {info.pid} is still alive and "
                f"started_at is older than 24h ({info.started_at}); remove the lock "
                "only after verifying no smoke run is active"
            )
        locks.append(info)
    return locks


def preflight_check(
    profile: identity.SmokeProfile,
    tenant_fqdn: str,
    sandbox_config: sandbox.SandboxConfig,
) -> None:
    profile_id = str(profile.id)
    if not profile_id or profile_id == "default":
        raise GuardError("--parallel-profile requires --profile to be set to a non-default profile")

    admin_config = _physical_path(profile.admin_commander_config)
    default_config = _physical_path(identity.ADMIN_COMMANDER_CONFIG)
    if admin_config == default_config:
        raise GuardError(
            "--parallel-profile refuses the default lab config; "
            f"profile {profile_id!r} admin_commander_config resolves to {default_config}"
        )

    keeper_config = os.environ.get("KEEPER_CONFIG")
    if keeper_config and _physical_path(keeper_config) != admin_config:
        raise GuardError(
            "KEEPER_CONFIG mismatch: env resolves to "
            f"{_physical_path(keeper_config)} but profile {profile_id!r} "
            f"admin_commander_config resolves to {admin_config}"
        )

    current_resources = {
        "sf_title": sandbox_config.sf_title,
        "ksm_app_name": sandbox_config.ksm_app_name,
        "project_name": profile.project_name,
    }
    for lock in list_active_locks():
        if (
            _physical_path(lock.admin_commander_config) == admin_config
            and lock.profile_id != profile_id
        ):
            raise GuardError(
                "admin_commander_config collision: "
                f"profile {profile_id!r} shares {admin_config} with active "
                f"profile {lock.profile_id!r}"
            )
        if lock.tenant_fqdn != tenant_fqdn:
            continue
        for field, value in current_resources.items():
            if getattr(lock, field) == value:
                raise GuardError(
                    f"{field} collision: profile {profile_id!r} uses {value!r}, "
                    f"already locked by active profile {lock.profile_id!r}"
                )


def acquire(
    profile: identity.SmokeProfile,
    tenant_fqdn: str,
    sandbox_config: sandbox.SandboxConfig,
    project_name: str,
) -> Path:
    directory = lock_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GuardError(f"could not create smoke lock directory {directory}: {exc}") from exc

    list_active_locks()
    path = _lock_path(tenant_fqdn, str(profile.id))
    payload = _lock_payload(profile, tenant_fqdn, sandbox_config, project_name)
    try:
        with path.open("x", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True)
            fh.write("\n")
    except FileExistsError as exc:
        raise GuardError(f"parallel profile lock already exists: {path}") from exc
    except OSError as exc:
        raise GuardError(f"could not create smoke lock {path}: {exc}") from exc
    log.info("acquired smoke parallel-profile lock %s", path)
    return path


def release(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        log.info("smoke parallel-profile lock already missing: %s", lock_path)
    except OSError as exc:
        log.warning("could not release smoke parallel-profile lock %s: %s", lock_path, exc)
    else:
        log.info("released smoke parallel-profile lock %s", lock_path)


def _lock_path(tenant_fqdn: str, profile_id: str) -> Path:
    tenant_safe = _safe_tenant_fqdn(tenant_fqdn)
    profile_safe = _safe_profile_id(profile_id)
    return lock_dir() / f".dsk-smoke-{tenant_safe}-{profile_safe}.lock"


def _lock_payload(
    profile: identity.SmokeProfile,
    tenant_fqdn: str,
    sandbox_config: sandbox.SandboxConfig,
    project_name: str,
) -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "started_at": _utc_now_iso(),
        "tenant_fqdn": tenant_fqdn,
        "profile_id": str(profile.id),
        "admin_commander_config": str(_physical_path(profile.admin_commander_config)),
        "sf_title": sandbox_config.sf_title,
        "ksm_app_name": sandbox_config.ksm_app_name,
        "project_name": project_name,
    }


def _read_lock(path: Path) -> tuple[LockInfo, datetime]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardError(f"corrupt lock {path}: invalid JSON") from exc
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise GuardError(f"could not read smoke lock {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise GuardError(f"corrupt lock {path}: expected JSON object")
    info = _lock_info_from_mapping(raw, path=path)
    started_at = _parse_started_at(info.started_at, path=path)
    return info, started_at


def _lock_info_from_mapping(raw: dict[str, Any], *, path: Path) -> LockInfo:
    required = {
        "pid",
        "started_at",
        "tenant_fqdn",
        "profile_id",
        "admin_commander_config",
        "sf_title",
        "ksm_app_name",
        "project_name",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise GuardError(f"corrupt lock {path}: missing {', '.join(missing)}")

    pid = raw["pid"]
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise GuardError(f"corrupt lock {path}: pid must be a positive integer")
    string_fields: dict[str, str] = {}
    for field in required - {"pid"}:
        value = raw[field]
        if not isinstance(value, str) or not value:
            raise GuardError(f"corrupt lock {path}: {field} must be a non-empty string")
        string_fields[field] = value

    return LockInfo(
        pid=pid,
        started_at=string_fields["started_at"],
        tenant_fqdn=string_fields["tenant_fqdn"],
        profile_id=string_fields["profile_id"],
        admin_commander_config=string_fields["admin_commander_config"],
        sf_title=string_fields["sf_title"],
        ksm_app_name=string_fields["ksm_app_name"],
        project_name=string_fields["project_name"],
    )


def _parse_started_at(value: str, *, path: Path) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise GuardError(f"corrupt lock {path}: invalid started_at {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _remove_stale_lock(path: Path, info: LockInfo) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise GuardError(f"could not remove stale smoke lock {path}: {exc}") from exc
    log.warning("removed stale smoke lock %s for dead pid %s", path, info.pid)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _physical_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _safe_tenant_fqdn(tenant_fqdn: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9-]", "_", tenant_fqdn)
    return safe or "unknown"


def _safe_profile_id(profile_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9-]", "_", profile_id)
    return safe or "unknown"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
