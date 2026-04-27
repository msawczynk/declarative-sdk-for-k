#!/usr/bin/env python3
"""Manage the SDK smoke shared-folder sandbox through Keeper Commander CLI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker  # noqa: E402

log = logging.getLogger("sdk_smoke.sandbox")

SANDBOX_SF_TITLE = "SDK Test (ephemeral)"
SANDBOX_KSM_APP_NAME = "SDK Test KSM"
GATEWAY_NAME = "<gateway-name>"


@dataclass(frozen=True)
class SandboxConfig:
    sf_title: str
    ksm_app_name: str
    gateway_name: str


DEFAULT_SANDBOX_CONFIG = SandboxConfig(
    sf_title=SANDBOX_SF_TITLE,
    ksm_app_name=SANDBOX_KSM_APP_NAME,
    gateway_name=GATEWAY_NAME,
)


def config_for_profile(profile: Any) -> SandboxConfig:
    profile_id = str(getattr(profile, "id", "default"))
    gateway_name = str(getattr(profile, "gateway_name", GATEWAY_NAME))
    if profile_id == "default":
        return SandboxConfig(
            sf_title=SANDBOX_SF_TITLE,
            ksm_app_name=SANDBOX_KSM_APP_NAME,
            gateway_name=gateway_name,
        )
    return SandboxConfig(
        sf_title=f"SDK Test (ephemeral) {profile_id}",
        ksm_app_name=f"SDK Test KSM {profile_id}",
        gateway_name=gateway_name,
    )


def _sandbox_or_default(sandbox: SandboxConfig | None) -> SandboxConfig:
    return sandbox if sandbox is not None else DEFAULT_SANDBOX_CONFIG


def ensure_sandbox(
    admin_params, *, testuser_email: str, sandbox: SandboxConfig | None = None
) -> dict:
    """Ensure the SDK smoke sandbox exists and is wired for reuse."""
    sandbox_config = _sandbox_or_default(sandbox)
    _sync_down(admin_params)
    _ensure_gateway_visible(admin_params, sandbox=sandbox_config)

    sf_uid = _find_shared_folder_uid(admin_params, sandbox_config.sf_title)
    if not sf_uid:
        log.info("Creating shared folder %s", sandbox_config.sf_title)
        _do(
            admin_params,
            f'mkdir -sf --manage-users --manage-records --can-edit --can-share "{sandbox_config.sf_title}"',
        )
        sf_uid = _find_shared_folder_uid(admin_params, sandbox_config.sf_title)
        if not sf_uid:
            raise RuntimeError(
                f"Created shared folder {sandbox_config.sf_title!r} but could not resolve its UID. "
                "Re-run `keeper ls -f --format json` as the admin and inspect the folder listing."
            )

    shared_to_testuser = _ensure_shared_to_user(
        admin_params, testuser_email=testuser_email, sandbox=sandbox_config
    )

    existing_app = _find_ksm_app(admin_params, sandbox_config.ksm_app_name)
    if existing_app is None:
        log.info("Creating KSM application %s", sandbox_config.ksm_app_name)
        _do(admin_params, f'secrets-manager app create "{sandbox_config.ksm_app_name}"')
        existing_app = _find_ksm_app(admin_params, sandbox_config.ksm_app_name)
        if existing_app is None:
            raise RuntimeError(
                f"Created KSM application {sandbox_config.ksm_app_name!r} but could not resolve its UID. "
                "Re-run `keeper secrets-manager app list --format json` and confirm Commander supports JSON output."
            )
    else:
        log.info(
            "KSM application %s already exists (%s)",
            sandbox_config.ksm_app_name,
            existing_app["uid"],
        )

    return {
        "sf_uid": sf_uid,
        "ksm_app_uid": existing_app["uid"],
        "gateway_name": sandbox_config.gateway_name,
        "shared_to_testuser": shared_to_testuser,
    }


def record_count(admin_params, sf_uid: str, *, sandbox: SandboxConfig | None = None) -> int:
    """Return how many records currently live in the shared folder."""
    entries = _list_folder_entries(admin_params, sf_uid)
    return sum(1 for entry in entries if _entry_type(entry) == "record")


def teardown_records(
    admin_params,
    sf_uid: str,
    *,
    manager: str,
    sandbox: SandboxConfig | None = None,
) -> list[str]:
    """Delete only SDK-managed records in the sandbox shared folder."""
    removed: list[str] = []
    for entry in _list_folder_entries(admin_params, sf_uid):
        if _entry_type(entry) != "record":
            continue
        record_uid = _entry_uid(entry)
        if not record_uid:
            continue
        marker = _record_marker(admin_params, record_uid)
        if not isinstance(marker, dict) or marker.get("manager") != manager:
            continue
        log.info("Removing managed sandbox record %s", record_uid)
        _do(admin_params, f"rm --force {record_uid}")
        removed.append(record_uid)
    return removed


def teardown_sandbox(
    admin_params, *, keep_sf: bool = True, sandbox: SandboxConfig | None = None
) -> None:
    """Remove the sandbox app binding and optionally the sandbox shared folder."""
    sandbox_config = _sandbox_or_default(sandbox)
    _sync_down(admin_params)

    sf_uid = _find_shared_folder_uid(admin_params, sandbox_config.sf_title)
    app = _find_ksm_app(admin_params, sandbox_config.ksm_app_name)

    if sf_uid and app:
        try:
            log.info("Removing sandbox shared-folder binding from %s", sandbox_config.ksm_app_name)
            _do(
                admin_params,
                f'secrets-manager share remove --app "{sandbox_config.ksm_app_name}" --secret {sf_uid}',
            )
        except Exception as exc:
            if not _looks_like_missing_share(str(exc)):
                raise
            log.info("Sandbox shared-folder binding already absent")

    if not keep_sf and sf_uid:
        log.info("Removing sandbox shared folder %s", sandbox_config.sf_title)
        _do(admin_params, f'rmdir "{sandbox_config.sf_title}"')


def _sync_down(admin_params) -> None:
    from keepercommander import api

    api.sync_down(admin_params)


def _do(admin_params, command: str) -> str:
    """Run a keeper CLI command via cli.do_command, capturing stdout.

    Commander CLI subcommands print results directly to stdout (tabulate /
    json.dump) and usually return None. We redirect stdout into a buffer so the
    caller sees the actual payload and the terminal stays clean.
    """
    import contextlib
    import io

    from keepercommander import cli

    log.info("CLI: %s", command)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = cli.do_command(admin_params, command)
    captured = buf.getvalue()
    if isinstance(result, str) and result:
        return result
    return captured


def _ensure_gateway_visible(admin_params, *, sandbox: SandboxConfig) -> None:
    output = _do(admin_params, "pam gateway list")
    if sandbox.gateway_name in output:
        return

    for record in getattr(admin_params, "record_cache", {}).values():
        try:
            raw = record.get("data_unencrypted", "{}")
            if sandbox.gateway_name in raw:
                return
        except Exception:
            continue

    raise RuntimeError(
        f"Required gateway {sandbox.gateway_name!r} is not visible after sync_down. "
        "Next action: log in as the tenant admin, run `keeper pam gateway list`, "
        "and confirm the gateway exists and is shared to that admin session before re-running smoke."
    )


def _find_shared_folder_uid(admin_params, title: str) -> str | None:
    for entry in _list_folders(admin_params):
        if _entry_name(entry) == title:
            return _entry_uid(entry)
    return None


def _list_folders(admin_params) -> list[dict[str, Any]]:
    payload = _do(admin_params, "ls -f --format json")
    data = _loads_json(payload, command="ls -f --format json")
    entries = _as_list(data)
    return [entry for entry in entries if isinstance(entry, dict)]


def _ensure_shared_to_user(admin_params, *, testuser_email: str, sandbox: SandboxConfig) -> bool:
    before = _share_folder_info(admin_params, sandbox=sandbox)
    if _share_info_mentions_user(before, testuser_email):
        log.info("Shared folder already granted to %s", testuser_email)
        return True

    # Commander 17.x share-folder flags: -e EMAIL, -p on|off (manage-records),
    # -o on|off (manage-users), -d on|off (can-edit), -s on|off (can-share),
    # -f to ignore default folder permissions on the initial sharing action.
    command = (
        f'share-folder "{sandbox.sf_title}" -a grant -e {testuser_email} -p on -o on -d on -s on -f'
    )
    try:
        output = _do(admin_params, command)
        if "already" in output.lower():
            return True
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise
        log.info("Share-folder grant already existed for %s", testuser_email)
        return True

    after = _share_folder_info(admin_params, sandbox=sandbox)
    return _share_info_mentions_user(after, testuser_email)


def _share_folder_info(admin_params, *, sandbox: SandboxConfig) -> str:
    # Commander 17.x has no `share-folder --info`; use `get <sf_uid>` which
    # includes the user_permissions and shared_folder_permissions blocks.
    sf_uid = _find_shared_folder_uid(admin_params, sandbox.sf_title)
    if not sf_uid:
        return ""
    return _do(admin_params, f"get {sf_uid}")


def _share_info_mentions_user(info: str, email: str) -> bool:
    return email.casefold() in info.casefold()


def _find_ksm_app(admin_params, name: str) -> dict[str, str] | None:
    payload = _do(admin_params, "secrets-manager app list --format json")
    data = _loads_json(payload, command="secrets-manager app list --format json")
    for entry in _as_list(data):
        if not isinstance(entry, dict):
            continue
        if _coalesce(entry, "title", "name", "app_name", "application_name") == name:
            uid = _coalesce(entry, "uid", "app_uid", "application_uid")
            if uid:
                return {"uid": uid, "name": name}
    return None


def _ensure_app_share(admin_params, *, sf_uid: str, sandbox: SandboxConfig) -> None:
    command = (
        f'secrets-manager share add --app "{sandbox.ksm_app_name}" --secret {sf_uid} --editable'
    )
    try:
        output = _do(admin_params, command)
        if "already" in output.lower():
            log.info("Shared folder %s already bound to %s", sf_uid, sandbox.ksm_app_name)
    except Exception as exc:
        if "already" not in str(exc).lower():
            raise
        log.info("Shared folder %s already bound to %s", sf_uid, sandbox.ksm_app_name)


def _list_folder_entries(admin_params, folder_ref: str) -> list[dict[str, Any]]:
    payload = _do(admin_params, f"ls {folder_ref} --format json")
    data = _loads_json(payload, command=f"ls {folder_ref} --format json")
    return [entry for entry in _as_list(data) if isinstance(entry, dict)]


def _record_marker(admin_params, record_uid: str) -> dict[str, Any] | None:
    payload = _do(admin_params, f"get {record_uid} --format json")
    data = _loads_json(payload, command=f"get {record_uid} --format json")
    if not isinstance(data, dict):
        return None
    raw = _extract_marker_field(data)
    return decode_marker(raw)


def _extract_marker_field(item: dict[str, Any]) -> str | None:
    for key in ("custom_fields", "custom"):
        block = item.get(key)
        if isinstance(block, dict) and MARKER_FIELD_LABEL in block:
            value = block[MARKER_FIELD_LABEL]
            if isinstance(value, list):
                return value[0] if value else None
            return value if isinstance(value, str) else None
        if isinstance(block, list):
            for entry in block:
                if not isinstance(entry, dict):
                    continue
                if (
                    entry.get("label") == MARKER_FIELD_LABEL
                    or entry.get("name") == MARKER_FIELD_LABEL
                ):
                    value = entry.get("value")
                    if isinstance(value, list):
                        return value[0] if value else None
                    return value if isinstance(value, str) else None
    return None


def _loads_json(payload: str, *, command: str) -> Any:
    # Commander 17.x emits empty output when listing an empty folder or empty
    # app list — treat that as [] so idempotent callers work on fresh sandboxes.
    if not payload or not payload.strip():
        return []
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise RuntimeError(
            f"Commander returned non-JSON from `{command}`. "
            "Next action: upgrade Keeper Commander or re-run the command manually to inspect the raw output."
        ) from exc


def _as_list(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("entries", "items", "folders", "records", "applications", "apps"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _entry_type(entry: dict[str, Any]) -> str:
    value = _coalesce(entry, "type", "record_type", "kind") or ""
    return str(value).replace("-", "_").casefold()


def _entry_uid(entry: dict[str, Any]) -> str | None:
    value = _coalesce(entry, "uid", "folder_uid", "shared_folder_uid", "record_uid")
    return str(value) if value else None


def _entry_name(entry: dict[str, Any]) -> str | None:
    value = _coalesce(entry, "name", "title", "folder")
    return str(value) if value else None


def _coalesce(entry: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = entry.get(key)
        if value not in (None, ""):
            return value
    return None


def _looks_like_missing_share(message: str) -> bool:
    lowered = message.casefold()
    return "not found" in lowered or "does not exist" in lowered or "not shared" in lowered


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure the SDK smoke sandbox exists")
    parser.add_argument(
        "--testuser", required=True, help="User email to share the sandbox shared folder with"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logger level for sdk_smoke.sandbox",
    )
    return parser.parse_args(argv)


def _load_admin_params_for_main():
    try:
        import identity  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Direct-run requires an importable `identity` module exposing `admin_login()`. "
            "Next action: add that helper to PYTHONPATH or invoke `ensure_sandbox()` from the existing smoke harness."
        ) from exc

    login = getattr(identity, "admin_login", None)
    if not callable(login):
        raise RuntimeError(
            "Direct-run requires `identity.admin_login()` but the imported `identity` module does not provide it."
        )
    return login()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    admin_params = _load_admin_params_for_main()
    result = ensure_sandbox(admin_params, testuser_email=args.testuser)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
