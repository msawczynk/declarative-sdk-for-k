"""Commander-driven provisioning for the SDK's first KSM application.

The bootstrap flow creates or reuses a Keeper Secrets Manager application,
shares the Commander admin record into it, generates a one-time client token,
redeems that token into a local ``ksm-config.json``, and verifies that the
resulting KSM client can see the admin record shape required by
``KsmLoginHelper``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from keepercommander import api as commander_api
from keepercommander.commands.ksm import KSMCommand
from keepercommander.commands.recordv3 import RecordAddCommand

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.secrets.ksm import KsmSecretStore


@dataclass(frozen=True)
class BootstrapResult:
    """Shape returned after a successful KSM bootstrap run.

    The result intentionally contains identifiers and paths only. It never
    contains the one-time token, KSM config JSON, or Keeper record field values.
    """

    app_uid: str
    app_name: str
    admin_record_uid: str
    config_path: str
    bus_directory_uid: str | None
    client_token_redeemed: bool
    expires_at_iso: str | None
    created_admin_record: bool
    created_bus_directory: bool


def bootstrap_ksm_application(
    *,
    params: Any,
    app_name: str,
    admin_record_uid: str | None = None,
    create_admin_record: bool = False,
    config_out: Path,
    first_access_minutes: int = 10,
    unlock_ip: bool = False,
    create_bus_directory: bool = False,
    bus_directory_title: str = "dsk-agent-bus-directory",
    overwrite: bool = False,
) -> BootstrapResult:
    """Provision a KSM application and redeemed client config for SDK login.

    ``params`` must already be an authenticated ``KeeperParams`` instance. This
    function never performs Commander login and never shells out to ``keeper``.
    Commander output is captured so one-time tokens and record values cannot
    escape through stdout or stderr.
    """

    config_path = _validate_inputs(
        app_name=app_name,
        admin_record_uid=admin_record_uid,
        create_admin_record=create_admin_record,
        config_out=config_out,
        first_access_minutes=first_access_minutes,
        overwrite=overwrite,
    )

    partial: dict[str, Any] = {
        "app_uid": None,
        "record_uid": admin_record_uid,
        "config_path": str(config_path),
    }

    admin_uid, created_admin = _resolve_admin_record(
        params=params,
        app_name=app_name,
        admin_record_uid=admin_record_uid,
        create_admin_record=create_admin_record,
        partial=partial,
    )
    partial["record_uid"] = admin_uid

    app_uid = _create_or_reuse_app(params=params, app_name=app_name, partial=partial)
    partial["app_uid"] = app_uid

    _share_record_with_app(
        params=params,
        app_uid=app_uid,
        record_uid=admin_uid,
        editable=False,
        partial=partial,
    )

    bus_uid: str | None = None
    created_bus = False
    if create_bus_directory:
        bus_uid, created_bus = _create_or_reuse_bus_directory(
            params=params,
            title=bus_directory_title,
            partial=partial,
        )
        _share_record_with_app(
            params=params,
            app_uid=app_uid,
            record_uid=bus_uid,
            editable=True,
            partial=partial,
        )

    _sync_down(params=params, partial=partial)

    token = _generate_one_time_token(
        params=params,
        app_uid=app_uid,
        first_access_minutes=first_access_minutes,
        unlock_ip=unlock_ip,
        partial=partial,
    )

    _redeem_one_time_token(
        token=token, config_path=config_path, overwrite=overwrite, partial=partial
    )
    _verify_redeemed_config(config_path=config_path, admin_record_uid=admin_uid, partial=partial)

    expires_at = None
    if first_access_minutes > 0:
        expires_at = (datetime.now(UTC) + timedelta(minutes=first_access_minutes)).isoformat(
            timespec="seconds"
        )

    return BootstrapResult(
        app_uid=app_uid,
        app_name=app_name,
        admin_record_uid=admin_uid,
        config_path=str(config_path),
        bus_directory_uid=bus_uid,
        client_token_redeemed=True,
        expires_at_iso=expires_at,
        created_admin_record=created_admin,
        created_bus_directory=created_bus,
    )


def _validate_inputs(
    *,
    app_name: str,
    admin_record_uid: str | None,
    create_admin_record: bool,
    config_out: Path,
    first_access_minutes: int,
    overwrite: bool,
) -> Path:
    if not app_name or not app_name.strip():
        raise CapabilityError(
            reason="KSM bootstrap app_name must be non-empty",
            next_action="pass --app-name with a non-empty application name",
        )
    if "/" in app_name or "\\" in app_name:
        raise CapabilityError(
            reason="KSM bootstrap app_name must not contain path separators",
            next_action="choose an application name, not a filesystem path",
        )
    if len(app_name) > 64:
        raise CapabilityError(
            reason="KSM bootstrap app_name must be 64 characters or fewer",
            next_action="choose a shorter --app-name",
        )
    if bool(admin_record_uid) == create_admin_record:
        raise CapabilityError(
            reason="KSM bootstrap requires exactly one of admin_record_uid or create_admin_record",
            next_action="pass --admin-record-uid UID or --create-admin-record, but not both",
        )
    if first_access_minutes < 0:
        raise CapabilityError(
            reason="KSM bootstrap first_access_minutes must be non-negative",
            next_action="pass --first-access-minutes between 0 and 1440",
        )

    config_path = Path(config_out).expanduser()
    if not config_path.parent.is_dir():
        raise CapabilityError(
            reason=f"KSM bootstrap config parent does not exist: {config_path.parent}",
            next_action="create the parent directory or choose a different --config-out path",
        )
    if config_path.exists() and not overwrite:
        raise CapabilityError(
            reason=f"KSM bootstrap config already exists at {config_path}",
            next_action="pass --overwrite or choose a different --config-out path",
        )
    return config_path


def _resolve_admin_record(
    *,
    params: Any,
    app_name: str,
    admin_record_uid: str | None,
    create_admin_record: bool,
    partial: dict[str, Any],
) -> tuple[str, bool]:
    if admin_record_uid:
        _sync_down(params=params, partial=partial)
        if not _record_cache_entry(params, admin_record_uid):
            raise CapabilityError(
                reason=f"admin record {admin_record_uid[:6]}... not found in the logged-in vault",
                next_action="verify --admin-record-uid belongs to the authenticated Keeper account",
                context=dict(partial),
            )
        return admin_record_uid, False

    if not create_admin_record:
        raise CapabilityError(
            reason="KSM bootstrap cannot resolve an admin record",
            next_action="pass --admin-record-uid UID or --create-admin-record",
            context=dict(partial),
        )

    record_data = {
        "type": "login",
        "title": f"{app_name} admin login",
        "fields": [
            {"type": "login", "value": [""]},
            {"type": "password", "value": [""]},
            {"type": "oneTimeCode", "value": [""]},
        ],
        "custom": [],
    }
    return _create_record(params=params, record_data=record_data, partial=partial), True


def _create_or_reuse_app(*, params: Any, app_name: str, partial: dict[str, Any]) -> str:
    _sync_down(params=params, partial=partial)
    existing = KSMCommand.get_app_record(params, app_name)
    if existing:
        uid = existing.get("record_uid")
        if uid:
            return str(uid)

    try:
        result = _quiet_call(
            KSMCommand.add_new_v5_app,
            params,
            app_name,
            False,
            "json",
        )
    except Exception as exc:
        raise _bootstrap_error(
            "creating KSM application failed",
            "verify the authenticated Keeper account can create KSM applications",
            partial,
            exc,
        ) from exc

    app_uid = _app_uid_from_create_result(result)
    if not app_uid:
        _sync_down(params=params, partial=partial)
        created = KSMCommand.get_app_record(params, app_name)
        app_uid = str(created.get("record_uid")) if created and created.get("record_uid") else ""
    if not app_uid:
        raise CapabilityError(
            reason=f"KSM application {app_name!r} was not created and could not be found",
            next_action="verify Commander KSM app create support for this tenant",
            context=dict(partial),
        )

    _sync_down(params=params, partial={**partial, "app_uid": app_uid})
    return app_uid


def _share_record_with_app(
    *,
    params: Any,
    app_uid: str,
    record_uid: str,
    editable: bool,
    partial: dict[str, Any],
) -> None:
    try:
        _quiet_call(KSMCommand.add_app_share, params, [record_uid], app_uid, editable)
    except Exception as exc:
        raise _bootstrap_error(
            "sharing record into KSM application failed",
            "verify the record is accessible to the authenticated account and retry once after cleanup",
            partial,
            exc,
        ) from exc


def _create_or_reuse_bus_directory(
    *,
    params: Any,
    title: str,
    partial: dict[str, Any],
) -> tuple[str, bool]:
    _sync_down(params=params, partial=partial)
    existing_uid = _find_record_uid_by_title(params, title)
    if existing_uid:
        return existing_uid, False

    record_data = {
        "type": "encryptedNotes",
        "title": title,
        "fields": [],
        "custom": [{"type": "json", "label": "topics", "value": ["{}"]}],
    }
    return _create_record(params=params, record_data=record_data, partial=partial), True


def _generate_one_time_token(
    *,
    params: Any,
    app_uid: str,
    first_access_minutes: int,
    unlock_ip: bool,
    partial: dict[str, Any],
) -> str:
    try:
        tokens = _quiet_call(
            KSMCommand.add_client,
            params,
            app_uid,
            1,
            unlock_ip,
            first_access_minutes,
            None,
            silent=True,
        )
    except Exception as exc:
        raise _bootstrap_error(
            "creating KSM client token failed",
            "remove the partial KSM app if needed, then rerun bootstrap once",
            partial,
            exc,
        ) from exc

    if not tokens or not isinstance(tokens, list):
        raise CapabilityError(
            reason="Commander did not return a KSM client token",
            next_action="verify keepercommander KSM client creation support for this tenant",
            context=dict(partial),
        )
    token = tokens[0].get("oneTimeToken") if isinstance(tokens[0], dict) else None
    if not token:
        raise CapabilityError(
            reason="Commander returned a KSM client response without a one-time token",
            next_action="verify keepercommander KSM client creation support for this tenant",
            context=dict(partial),
        )
    return str(token)


def _redeem_one_time_token(
    *,
    token: str,
    config_path: Path,
    overwrite: bool,
    partial: dict[str, Any],
) -> None:
    try:
        from keeper_secrets_manager_core import SecretsManager  # type: ignore[import-not-found]
        from keeper_secrets_manager_core.storage import (  # type: ignore[import-not-found]
            FileKeyValueStorage,
        )
    except ImportError as exc:
        raise CapabilityError(
            reason=f"keeper_secrets_manager_core is required to redeem the KSM client token: {exc}",
            next_action="pip install 'declarative-sdk-for-k[ksm]'",
            context=dict(partial),
        ) from exc

    if config_path.exists() and overwrite:
        config_path.unlink()

    try:
        client = _quiet_call(
            SecretsManager, token=token, config=FileKeyValueStorage(str(config_path))
        )
        _quiet_call(client.get_secrets)
    except Exception as exc:
        raise _bootstrap_error(
            "redeeming KSM client token failed",
            "discard the partial config, then rerun bootstrap with --overwrite after cleanup",
            partial,
            exc,
        ) from exc


VERIFY_RETRY_SECONDS_ENV = "KEEPER_SDK_KSM_BOOTSTRAP_VERIFY_TIMEOUT"
"""Total budget (seconds) for the post-redeem verification retry loop.

The vault-side ``add_app_share`` write and the KSM-side client fetch hit
two different services with independent caches; in practice the new KSM
client's first ``get_secrets`` call can race the share propagation. We
poll with exponential-ish backoff until the admin record's typed fields
become visible or this budget elapses. Default 20s is enough for the lab
tenant; raise via env for slower deployments.
"""


def _verify_redeemed_config(
    *,
    config_path: Path,
    admin_record_uid: str,
    partial: dict[str, Any],
) -> None:
    """Verify the redeemed KSM client can read the admin record's fields.

    The ``add_app_share`` (vault) → ``add_client`` (KSM) → ``SecretsManager
    (token=...)`` (KSM client) chain crosses a service boundary. The new
    client's first fetch can race the share propagation; we poll with
    bounded backoff so transient invisibility becomes a delay, not a
    bootstrap failure.
    """
    budget_s = _verify_budget_seconds()
    deadline = time.monotonic() + budget_s
    delay = 0.5
    last_error: Exception | None = None
    last_field_count = 0
    while True:
        try:
            store = KsmSecretStore(config_path=config_path)
            described = store.describe(admin_record_uid)
            fields = described.get("fields") or []
            last_field_count = len(fields)
            if last_field_count >= 3:
                return
            last_error = CapabilityError(
                reason="redeemed KSM config cannot see the expected admin record fields",
                next_action="verify the admin record has login/password/oneTimeCode and app sharing succeeded",
            )
        except CapabilityError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc
        if time.monotonic() + delay > deadline:
            break
        time.sleep(delay)
        delay = min(delay * 2.0, 4.0)

    if isinstance(last_error, CapabilityError):
        raise CapabilityError(
            reason=(
                f"KSM config verification failed after {budget_s:.0f}s "
                f"(observed {last_field_count} fields): {last_error.reason}"
            ),
            next_action=(
                "remove any partial KSM app if desired, then rerun bootstrap with --overwrite; "
                f"raise {VERIFY_RETRY_SECONDS_ENV} if your tenant needs longer share-propagation"
            ),
            context=dict(partial),
        ) from last_error
    raise _bootstrap_error(
        f"KSM config verification failed after {budget_s:.0f}s",
        (
            "remove any partial KSM app if desired, then rerun bootstrap with --overwrite; "
            f"raise {VERIFY_RETRY_SECONDS_ENV} if your tenant needs longer share-propagation"
        ),
        partial,
        last_error
        if last_error is not None
        else RuntimeError("verification loop exited without an error"),
    )


def _verify_budget_seconds() -> float:
    """Read the verification timeout budget; clamp to a safe range."""
    raw = os.environ.get(VERIFY_RETRY_SECONDS_ENV, "")
    if not raw:
        return 20.0
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    if value < 0.0:
        return 0.0
    if value > 300.0:
        return 300.0
    return value


def _create_record(*, params: Any, record_data: dict[str, Any], partial: dict[str, Any]) -> str:
    try:
        uid = _quiet_call(
            RecordAddCommand().execute,
            params,
            data=json.dumps(record_data),
            force=False,
            folder=None,
            attach=[],
        )
    except Exception as exc:
        raise _bootstrap_error(
            "creating Keeper vault record failed",
            "verify the authenticated account can create vault records",
            partial,
            exc,
        ) from exc
    if not uid:
        raise CapabilityError(
            reason=f"Commander did not return a UID for record {record_data.get('title')!r}",
            next_action="verify keepercommander record-add support for this tenant",
            context=dict(partial),
        )
    _sync_down(params=params, partial={**partial, "record_uid": str(uid)})
    return str(uid)


def _sync_down(*, params: Any, partial: dict[str, Any]) -> None:
    try:
        _quiet_call(commander_api.sync_down, params)
    except Exception as exc:
        raise _bootstrap_error(
            "Commander sync_down failed",
            "refresh the source Commander session, then rerun bootstrap once",
            partial,
            exc,
        ) from exc


def _record_cache_entry(params: Any, uid: str) -> Any | None:
    cache = getattr(params, "record_cache", {}) or {}
    if uid in cache:
        return cache[uid]
    for value in cache.values():
        if isinstance(value, dict) and value.get("record_uid") == uid:
            return value
    return None


def _find_record_uid_by_title(params: Any, title: str) -> str | None:
    for entry in (getattr(params, "record_cache", {}) or {}).values():
        if not isinstance(entry, dict) or entry.get("version") == 5:
            continue
        data = _record_data(entry)
        if data.get("title") == title:
            return str(entry.get("record_uid") or "")
    return None


def _record_data(entry: dict[str, Any]) -> dict[str, Any]:
    raw = entry.get("data_unencrypted") or "{}"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _app_uid_from_create_result(result: Any) -> str:
    if not result:
        return ""
    if isinstance(result, bytes):
        result = result.decode("utf-8")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return ""
    if isinstance(result, dict):
        return str(result.get("app_uid") or "")
    return ""


def _quiet_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        return func(*args, **kwargs)


def _bootstrap_error(
    reason: str,
    next_action: str,
    partial: dict[str, Any],
    exc: Exception,
) -> CapabilityError:
    detail = f"{reason}: {type(exc).__name__}: {exc}"
    return CapabilityError(reason=detail, next_action=next_action, context=dict(partial))
