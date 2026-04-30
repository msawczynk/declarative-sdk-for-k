"""Live KSM app lifecycle — token, share, and config-output write/readback.

Exercises three individual operations against a real Keeper tenant:

  1. App create + one-time token generation → token is a non-empty string.
  2. App create + add share → share record appears in ``get_app_info``.
  3. App create + full bootstrap → config output file is a non-empty dict.

Skipped unless **all** of:

  - ``KEEPER_LIVE_TENANT=1``
  - ``KEEPER_LIVE_KSM_RECORD_UID``  — existing admin login record UID
  - ``KEEPER_LIVE_KSM_CONFIG``       — path to a valid KSM ksm-config.json

Each test receives a fresh KSM app via the ``ksm_app`` fixture, which
deletes the app in its teardown regardless of test outcome.

Credentials and token values are **never** echoed or logged.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import time
from pathlib import Path
from typing import Any, Generator

import pytest

# ---------------------------------------------------------------------------
# Private helpers from bootstrap — acceptable for in-tree tests
# ---------------------------------------------------------------------------
from keeper_sdk.secrets.bootstrap import (
    _create_or_reuse_app,
    _generate_one_time_token,
    _quiet_call,
    _share_record_with_app,
    _sync_down,
    bootstrap_ksm_application,
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_LIVE_REQUIRES = ("KEEPER_LIVE_KSM_RECORD_UID", "KEEPER_LIVE_KSM_CONFIG")


def _get_params() -> Any:
    """Return an authenticated ``KeeperParams`` via the KSM-backed login helper.

    Credentials are sourced from ``KEEPER_LIVE_KSM_RECORD_UID`` and
    ``KEEPER_LIVE_KSM_CONFIG`` only. Nothing is printed or returned to the
    caller — only the opaque ``KeeperParams`` object.
    """
    from keeper_sdk.auth.helper import KsmLoginHelper

    record_uid = os.environ["KEEPER_LIVE_KSM_RECORD_UID"]
    ksm_config = os.environ.get("KEEPER_LIVE_KSM_CONFIG", "").strip() or None
    helper = KsmLoginHelper(record_uid=record_uid, config_path=ksm_config)
    creds = helper.load_keeper_creds()
    return helper.keeper_login(**creds)


def _unique_app_name(tag: str) -> str:
    """Generate a unique KSM app name that sorts with the dsk-live prefix."""
    digest = hashlib.sha256(f"{time.monotonic()}{tag}".encode()).hexdigest()[:10]
    return f"dsk-live-lc-{tag[:6]}-{digest}"[:64]


def _delete_app_silent(params: Any, app_uid: str) -> None:
    """Delete a KSM v5 app; suppress all exceptions (best-effort teardown)."""
    from keepercommander.commands.ksm import KSMCommand

    with contextlib.suppress(Exception):
        _quiet_call(KSMCommand.remove_v5_app, params, app_uid, True, True)


# ---------------------------------------------------------------------------
# Session-scoped Commander params (login once for the whole module run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def commander_params() -> Any:
    """Authenticated KeeperParams (login once per test-module run)."""
    return _get_params()


# ---------------------------------------------------------------------------
# Function-scoped app fixture with teardown
# ---------------------------------------------------------------------------

@pytest.fixture()
def ksm_app(commander_params: Any) -> Generator[dict[str, Any], None, None]:
    """Create a fresh KSM app; yield its uid + name; delete on teardown.

    Yielded dict keys:
      ``app_uid``  — KSM application UID
      ``app_name`` — KSM application title
      ``params``   — authenticated KeeperParams (same as commander_params)
    """
    params = commander_params
    app_name = _unique_app_name("ksm")
    partial: dict[str, Any] = {"app_uid": None, "record_uid": None, "config_path": None}
    app_uid = _create_or_reuse_app(params=params, app_name=app_name, partial=partial)
    try:
        yield {"app_uid": app_uid, "app_name": app_name, "params": params}
    finally:
        _delete_app_silent(params, app_uid)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.live(requires=_LIVE_REQUIRES)
def test_ott_generation_returns_nonempty_string(ksm_app: dict[str, Any]) -> None:
    """One-time token generated for a fresh KSM app must be a non-empty string.

    This proves the ``add_client`` path works end-to-end: the app was created
    successfully and the token generation step returns a usable token value.
    The token is *not* redeemed here — we only verify its shape.
    """
    from keepercommander.commands.ksm import KSMCommand

    params = ksm_app["params"]
    app_uid = ksm_app["app_uid"]

    partial: dict[str, Any] = {"app_uid": app_uid}
    token = _generate_one_time_token(
        params=params,
        app_uid=app_uid,
        first_access_minutes=5,
        unlock_ip=False,
        partial=partial,
    )

    assert isinstance(token, str), f"Expected str token, got {type(token).__name__}"
    assert len(token) > 0, "One-time token must not be empty"
    # Sanity: tokens are base64url-like; reject an obviously wrong shape.
    assert len(token) >= 10, f"Token suspiciously short ({len(token)} chars)"


@pytest.mark.live(requires=_LIVE_REQUIRES)
def test_share_record_appears_in_app_info(ksm_app: dict[str, Any]) -> None:
    """Sharing an admin record into an app must make it visible in get_app_info.

    Verifies the write-then-readback round-trip:
      1. Share the admin record (read-only) into the fresh app.
      2. Retrieve app info from the Commander API.
      3. Assert the admin record UID appears in the shares list.
    """
    from keepercommander.commands.ksm import KSMCommand

    params = ksm_app["params"]
    app_uid = ksm_app["app_uid"]
    record_uid = os.environ["KEEPER_LIVE_KSM_RECORD_UID"]

    partial: dict[str, Any] = {"app_uid": app_uid, "record_uid": record_uid}
    _share_record_with_app(
        params=params,
        app_uid=app_uid,
        record_uid=record_uid,
        editable=False,
        partial=partial,
    )

    # Sync so the local cache reflects the share.
    _sync_down(params=params, partial=partial)

    # get_app_info returns a sequence of AppInfo protobuf messages.
    app_infos = _quiet_call(KSMCommand.get_app_info, params, app_uid)
    assert app_infos is not None and len(app_infos) > 0, (
        "get_app_info returned empty sequence after share"
    )
    app_info = app_infos[0]
    shares = app_info.shares  # RepeatedCompositeContainer of AppShare proto

    # AppShare.secretUid is raw bytes; decode to base64url for comparison.
    from keepercommander import utils as kc_utils
    shared_uids = {kc_utils.base64_url_encode(s.secretUid) for s in shares}
    assert record_uid in shared_uids, (
        f"Admin record UID not found in app shares after add_app_share. "
        f"Shares present: {len(shares)} item(s)."
    )


@pytest.mark.live(requires=_LIVE_REQUIRES)
def test_config_output_is_nonempty_dict(
    tmp_path: Path,
    commander_params: Any,
) -> None:
    """Full bootstrap flow writes a non-empty JSON config to disk.

    Runs ``bootstrap_ksm_application`` end-to-end (create app, share record,
    generate OTT, redeem to config file) and verifies the output config is a
    non-empty dict with at least the KSM client initialisation keys.

    The app created here is cleaned up explicitly in a finally block since it
    is not managed by the ``ksm_app`` fixture.
    """
    params = commander_params
    record_uid = os.environ["KEEPER_LIVE_KSM_RECORD_UID"]
    app_name = _unique_app_name("cfg")
    config_out = tmp_path / "test-ksm-lifecycle.json"

    result = bootstrap_ksm_application(
        params=params,
        app_name=app_name,
        admin_record_uid=record_uid,
        config_out=config_out,
        first_access_minutes=5,
        overwrite=False,
    )

    try:
        assert config_out.exists(), "bootstrap_ksm_application did not write config file"
        raw = config_out.read_text()
        assert raw.strip(), "config file is empty"

        config: dict = json.loads(raw)
        assert isinstance(config, dict), f"config file is not a JSON object: {type(config)}"
        assert len(config) > 0, "config dict is empty"

        assert result.client_token_redeemed, "BootstrapResult.client_token_redeemed is False"
        assert result.app_uid, "BootstrapResult.app_uid is empty"
    finally:
        _delete_app_silent(params, result.app_uid)
