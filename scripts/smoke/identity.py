#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sdk_smoke.identity")
log.setLevel(logging.INFO)

SDK_ROOT = Path(__file__).resolve().parent.parent.parent
LAB_ROOT = Path.home() / "Downloads" / "Cursor tests" / "keeper-vault-rbi-pam-testenv"
KSM_CONFIG = LAB_ROOT / "ksm-config.json"
ADMIN_COMMANDER_CONFIG = LAB_ROOT / "commander-config.json"
SDKTEST_COMMANDER_CONFIG = SDK_ROOT / "scripts" / "smoke" / ".commander-config-testuser2.json"

KEEPER_SERVER = "keepersecurity.com"
TARGET_EMAIL = "msawczyn+testuser2@acme-demo.com"
ADMIN_CRED_RECORD_UID = "MyiZN4cw-wtEIpY1jHlhLw"
SDK_TEST_LOGIN_RECORD_TITLE = "SDK Test — testuser2 Login"
CHANNEL_NAME = "sdk-declarative"
# Lab-wide shared test password; matches provision_prospect_ots.py::DEFAULT_PASSWORD.
DEFAULT_PASSWORD = "AcmeDemo123!!"


def _dependency_error(exc: Exception) -> ImportError:
    err = ImportError(
        "Missing Keeper smoke dependencies; pip install keepercommander pyotp "
        "keeper_secrets_manager_core"
    )
    err.__cause__ = exc
    return err


def _load_lab_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _totp_guarded(secret_b32: str) -> str:
    try:
        import pyotp
    except ImportError as exc:
        raise _dependency_error(exc)

    remaining = 30 - int(time.time()) % 30
    if remaining < 6:
        time.sleep(remaining + 1)
    return pyotp.TOTP(secret_b32).now()


def _parse_otpauth_secret(otpauth_url: str) -> str:
    secret = parse_qs(urlparse(otpauth_url).query).get("secret", [])
    if not secret or not secret[0]:
        raise ValueError("stored oneTimeCode does not contain a TOTP secret")
    return secret[0]


def _record_data(params: Any, record_uid: str) -> dict[str, Any]:
    record = params.record_cache.get(record_uid) or {}
    try:
        return json.loads(record.get("data_unencrypted", "{}"))
    except Exception:
        return {}


def _field_value(record_data: dict[str, Any], field_type: str) -> str | None:
    for section in ("fields", "custom"):
        for field in record_data.get(section, []) or []:
            if field.get("type") != field_type:
                continue
            value = field.get("value") or []
            if value:
                text = str(value[0]).strip()
                if text:
                    return text
    return None


def _find_admin_record_uid(params: Any, title: str) -> str | None:
    for record_uid in params.record_cache:
        data = _record_data(params, record_uid)
        if data.get("title") == title:
            return record_uid
    return None


def _login_user(
    email: str,
    password: str,
    *,
    config_path: Path,
    totp_secret: str | None = None,
):
    try:
        from keepercommander import api
        from keepercommander.auth.login_steps import (
            DeviceApprovalChannel,
            LoginUi,
            TwoFactorDuration,
        )
        from keepercommander.config_storage.loader import load_config_properties
        from keepercommander.params import KeeperParams
    except ImportError as exc:
        raise _dependency_error(exc)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HOME", str(SDK_ROOT))
    if not config_path.is_file():
        config_path.write_text(json.dumps({"server": KEEPER_SERVER}), encoding="utf-8")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    params = KeeperParams(
        config_filename=str(config_path),
        config=config,
        server=config.get("server", KEEPER_SERVER),
    )
    params.user = email
    params.password = password
    load_config_properties(params)

    totp_obj = None
    if totp_secret:
        try:
            import pyotp
        except ImportError as exc:
            raise _dependency_error(exc)
        totp_obj = pyotp.TOTP(totp_secret)

    class AutoUI(LoginUi):
        def on_device_approval(self, step):
            if not totp_obj:
                raise RuntimeError("device approval requested but no TOTP secret available")
            remaining = 30 - int(time.time()) % 30
            if remaining < 8:
                time.sleep(remaining + 1)
            step.send_code(DeviceApprovalChannel.TwoFactor, totp_obj.now())

        def on_two_factor(self, step):
            if not totp_obj:
                raise RuntimeError("two-factor requested but no TOTP secret available")
            channels = step.get_channels()
            if channels:
                remaining = 30 - int(time.time()) % 30
                if remaining < 8:
                    time.sleep(remaining + 1)
                step.duration = TwoFactorDuration.Forever
                step.send_code(channels[0].channel_uid, totp_obj.now())

        def on_password(self, step):
            step.verify_password(password)

        def on_sso_redirect(self, step):
            step.login_with_password()

        def on_sso_data_key(self, step):
            step.cancel()

    remaining = 30 - int(time.time()) % 30
    if totp_obj and remaining < 15:
        time.sleep(remaining + 2)

    api.login(params, login_ui=AutoUI())
    if not params.session_token:
        raise RuntimeError(f"login failed for {email}")
    api.sync_down(params)
    return params


def _wait_for_next_totp_window(*, log_label: str = "next TOTP window") -> None:
    """Sleep until the start of the next 30-second TOTP window plus 2s safety."""
    remaining = 30 - int(time.time()) % 30
    nap = remaining + 2
    log.info("waiting %ds for %s", nap, log_label)
    time.sleep(nap)


def _retry_totp_login(
    email: str,
    password: str,
    *,
    config_path: Path,
    totp_secret: str,
    attempts: int = 3,
):
    """Wrap _login_user with retries on KeeperApiError 'two_factor_code_invalid'.

    Keeper invalidates a consumed TOTP code for the remainder of its window.
    The safest recovery is to wait for the next window and try again.
    """
    try:
        from keepercommander.error import KeeperApiError
    except ImportError as exc:
        raise _dependency_error(exc)

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _login_user(
                email,
                password,
                config_path=config_path,
                totp_secret=totp_secret,
            )
        except KeeperApiError as exc:
            last_exc = exc
            if "two_factor_code_invalid" not in str(exc).lower():
                raise
            log.warning(
                "TOTP rejected on attempt %d/%d; waiting for next window", attempt, attempts
            )
            _wait_for_next_totp_window(log_label=f"retry {attempt + 1}")
    raise RuntimeError(f"TOTP login for {email} failed after {attempts} attempts") from last_exc


def _enroll_totp(params) -> tuple[str, str, str]:
    try:
        from keepercommander import api, utils
        from keepercommander.proto import APIRequest_pb2
    except ImportError as exc:
        raise _dependency_error(exc)

    rs = api.communicate_rest(
        params,
        None,
        "authentication/2fa_list",
        rs_type=APIRequest_pb2.TwoFactorListResponse,
    )
    for channel in rs.channels:
        if channel.channelName == CHANNEL_NAME:
            rq_del = APIRequest_pb2.TwoFactorDeleteRequest()
            rq_del.channel_uid = channel.channel_uid
            try:
                api.communicate_rest(params, rq_del, "authentication/2fa_delete")
                log.info("deleted stale 2FA channel '%s'", CHANNEL_NAME)
            except Exception as exc:
                log.warning("could not delete stale channel: %s", exc)

    rq = APIRequest_pb2.TwoFactorAddRequest()
    rq.channel_uid = utils.base64_url_decode(utils.generate_uid())
    rq.channelName = CHANNEL_NAME
    rq.channelType = APIRequest_pb2.TWO_FA_CT_TOTP
    rs_add = api.communicate_rest(
        params,
        rq,
        "authentication/2fa_add",
        rs_type=APIRequest_pb2.TwoFactorAddResponse,
    )
    secret = rs_add.challenge
    otpauth = f"otpauth://totp/Keeper:{params.user}?secret={secret}&issuer=Keeper"

    rq_val = APIRequest_pb2.TwoFactorValidateRequest()
    rq_val.valueType = APIRequest_pb2.TWO_FA_CODE_TOTP
    rq_val.expireIn = APIRequest_pb2.TWO_FA_EXP_IMMEDIATELY
    rq_val.channel_uid = rq.channel_uid
    rq_val.value = _totp_guarded(secret)
    api.communicate_rest(params, rq_val, "authentication/2fa_add_validate")
    log.info("TOTP channel '%s' validated and active", CHANNEL_NAME)

    return utils.base64_url_encode(rq.channel_uid), secret, otpauth


def _upsert_admin_record(
    params,
    *,
    user_email: str,
    user_password: str,
    otpauth_url: str,
) -> str:
    try:
        from keepercommander import api, cli, utils
    except ImportError as exc:
        raise _dependency_error(exc)

    existing_uid = _find_admin_record_uid(params, SDK_TEST_LOGIN_RECORD_TITLE)
    if existing_uid:
        try:
            cli.do_command(params, f"rm --force {existing_uid}")
            log.info("removed existing admin record %s (rewrite)", existing_uid)
        except Exception as exc:
            log.warning("could not remove existing admin record: %s", exc)
        api.sync_down(params)

    note = (
        "Autoprovisioned by keeper-declarative-sdk/scripts/smoke/identity.py at "
        f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )
    data = {
        "title": SDK_TEST_LOGIN_RECORD_TITLE,
        "type": "login",
        "notes": note,
        "fields": [
            {"type": "login", "value": [user_email]},
            {"type": "password", "value": [user_password]},
            {"type": "oneTimeCode", "value": [otpauth_url]},
        ],
    }
    record_rq = {
        "record_uid": utils.generate_uid(),
        "record_key_unencrypted": utils.generate_aes_key(),
        "data_unencrypted": json.dumps(data),
        "version": 3,
        "client_modified_time": utils.current_milli_time(),
    }
    result = api.add_record_v3(params, record_rq, silent=True)
    if result is None:
        raise RuntimeError("add_record_v3 returned None (invalid record schema)")
    api.sync_down(params)
    record_uid = record_rq["record_uid"]
    if record_uid not in params.record_cache:
        raise RuntimeError(f"record {record_uid} not present after sync-down")
    return record_uid


def _write_commander_config(params, config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    filtered = {
        key: value
        for key, value in params.config.items()
        if key in ("user", "server", "device_token", "clone_code", "private_key")
    }
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(filtered, fh)


def _build_identity_result(
    *,
    email: str,
    password: str,
    totp_secret: str,
    otpauth_url: str,
    params,
    admin_record_uid: str,
) -> dict[str, Any]:
    return {
        "email": email,
        "password": password,
        "totp_secret": totp_secret,
        "otpauth_url": otpauth_url,
        "params": params,
        "commander_config_path": str(SDKTEST_COMMANDER_CONFIG),
        "admin_record_uid": admin_record_uid,
        "ksm_record_uid": ADMIN_CRED_RECORD_UID,
    }


def admin_login():
    """Log in as the lab admin using KSM + TOTP from ADMIN_CRED_RECORD_UID.
    Uses the exact same pattern as deploy_watcher.keeper_login — import it
    via sys.path if practical, otherwise inline the helper. Prefer
    importing to avoid drift.
    """
    module_path = LAB_ROOT / "scripts" / "deploy_watcher.py"
    if not module_path.is_file():
        raise FileNotFoundError(f"missing lab helper: {module_path}")

    try:
        deploy_watcher = _load_lab_module("sdk_smoke_deploy_watcher", module_path)
        email, password, totp_secret = deploy_watcher.load_keeper_creds()
        params = deploy_watcher.keeper_login(email, password, totp_secret)
        from keepercommander import api
    except ImportError as exc:
        raise _dependency_error(exc)

    api.query_enterprise(params)
    log.info(
        "admin session OK (%s); enterprise users=%d",
        email,
        len(params.enterprise.get("users", [])) if params.enterprise else 0,
    )
    return params


def ensure_sdktest_identity(*, force_reenroll: bool = False) -> dict[str, Any]:
    """Ensure testuser2 has a known TOTP the SDK can use. Idempotent.
    Returns {'email', 'password', 'totp_secret', 'otpauth_url',
             'params' (live KeeperParams for testuser2),
             'commander_config_path' (str), 'admin_record_uid' (str)}.
    Flow:
      1. admin_login()
      2. Look up admin record titled SDK_TEST_LOGIN_RECORD_TITLE in the admin
         vault (search via api.query_enterprise or cli.do_command get-matter).
         If the record exists AND force_reenroll is False AND
         its login/password/oneTimeCode all resolve AND
         testuser2 login with (password, TOTP-now) succeeds,
         return immediately with the stored creds.
      3. Otherwise: run `enterprise-user --disable-2fa --force testuser2` via
         cli.do_command on the admin session.
      4. Log in as testuser2 (password only, no 2FA).
      5. REST-enroll a fresh TOTP channel named 'sdk-declarative' via
         authentication/2fa_add + /2fa_add_validate.
         Reuse the exact REST pattern from provision_prospect_ots._enroll_totp.
      6. Upsert the admin record.
      7. Re-login as testuser2 using the newly-stored creds to verify.
      8. Write the resulting params.config to
         scripts/smoke/.commander-config-testuser2.json.
      9. Return the dict.
    """
    try:
        from keepercommander import api, cli
    except ImportError as exc:
        raise _dependency_error(exc)

    log.info("=== admin login (KSM-backed) ===")
    admin_params = admin_login()
    api.sync_down(admin_params)

    existing_uid = _find_admin_record_uid(admin_params, SDK_TEST_LOGIN_RECORD_TITLE)
    if existing_uid and not force_reenroll:
        data = _record_data(admin_params, existing_uid)
        email = _field_value(data, "login")
        password = _field_value(data, "password")
        otpauth_url = _field_value(data, "oneTimeCode")
        if email and password and otpauth_url:
            try:
                totp_secret = _parse_otpauth_secret(otpauth_url)
                params = _login_user(
                    email,
                    password,
                    config_path=SDKTEST_COMMANDER_CONFIG,
                    totp_secret=totp_secret,
                )
                _write_commander_config(params, SDKTEST_COMMANDER_CONFIG)
                log.info("reused stored SDK smoke identity from admin record %s", existing_uid)
                return _build_identity_result(
                    email=email,
                    password=password,
                    totp_secret=totp_secret,
                    otpauth_url=otpauth_url,
                    params=params,
                    admin_record_uid=existing_uid,
                )
            except Exception as exc:
                log.info("stored SDK smoke identity unusable; re-enrolling: %s", exc)

    log.info("=== admin clears target 2FA ===")
    cli.do_command(admin_params, f"enterprise-user --disable-2fa --force {TARGET_EMAIL}")
    log.info("admin cleared 2FA on %s", TARGET_EMAIL)

    log.info("=== target login (password only) ===")
    unenrolled_params = _login_user(
        TARGET_EMAIL,
        DEFAULT_PASSWORD,
        config_path=SDKTEST_COMMANDER_CONFIG,
    )
    log.info("target session OK before TOTP enrollment")

    _, totp_secret, otpauth_url = _enroll_totp(unenrolled_params)

    log.info("=== admin record upsert ===")
    api.sync_down(admin_params)
    admin_record_uid = _upsert_admin_record(
        admin_params,
        user_email=TARGET_EMAIL,
        user_password=DEFAULT_PASSWORD,
        otpauth_url=otpauth_url,
    )

    log.info("=== target relogin (verify stored creds) ===")
    # After /2fa_add_validate Keeper marks the consumed TOTP code as used; the
    # next window must be clean before /2fa_validate will accept a fresh code.
    # Sleep to the start of the next 30-second window + 2s safety.
    _wait_for_next_totp_window(log_label="post-enrollment settle")
    verified_params = _retry_totp_login(
        TARGET_EMAIL,
        DEFAULT_PASSWORD,
        config_path=SDKTEST_COMMANDER_CONFIG,
        totp_secret=totp_secret,
        attempts=3,
    )
    _write_commander_config(verified_params, SDKTEST_COMMANDER_CONFIG)

    return _build_identity_result(
        email=TARGET_EMAIL,
        password=DEFAULT_PASSWORD,
        totp_secret=totp_secret,
        otpauth_url=otpauth_url,
        params=verified_params,
        admin_record_uid=admin_record_uid,
    )


def sdktest_keeper_args() -> list[str]:
    """Return the argv prefix for invoking the keeper CLI as testuser2:
       ['keeper', '--config', '<scripts/smoke/.commander-config-testuser2.json>', '--batch-mode']
    Caller appends subcommand + args.
    """
    return ["keeper", "--config", str(SDKTEST_COMMANDER_CONFIG), "--batch-mode"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensure SDK smoke identity for testuser2.")
    parser.add_argument("--force", action="store_true", help="force TOTP re-enrollment")
    args = parser.parse_args(argv)

    ident = ensure_sdktest_identity(force_reenroll=args.force)
    preview = hashlib.sha256(ident["totp_secret"].encode("utf-8")).hexdigest()
    summary = {
        "email": ident["email"],
        "admin_record_uid": ident["admin_record_uid"],
        "commander_config_path": ident["commander_config_path"],
        "totp_secret_preview": f"sha256:{preview}",
    }
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
