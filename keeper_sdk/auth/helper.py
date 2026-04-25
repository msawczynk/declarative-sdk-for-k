"""Reference login helper + Protocol for custom ones.

See :mod:`keeper_sdk.auth` for the module-level rationale.
"""

from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from keeper_sdk.core.errors import CapabilityError


@runtime_checkable
class LoginHelper(Protocol):
    """Contract a custom helper must honour.

    The two functions are separated because most deployments fetch
    credentials from a secret store (``load_keeper_creds``) at a
    different cadence than they call the Commander login
    (``keeper_login``). Splitting them lets operators cache the former
    aggressively while re-running the latter on every session.
    """

    def load_keeper_creds(self) -> dict[str, str]:
        """Return a dict with ``email``, ``password``, and ``totp_secret`` keys.

        Implementations may add extra keys (``config_path``,
        ``device_token``, …) — ``keeper_login`` is expected to know
        which ones it needs. ``totp_secret`` is the base32 secret
        (``?secret=...`` portion of the ``otpauth://`` URI), NOT a
        six-digit code.
        """
        ...

    def keeper_login(self, email: str, password: str, totp_secret: str, **kwargs: Any) -> Any:
        """Return a logged-in ``keepercommander.params.KeeperParams`` instance.

        Raise ``CapabilityError`` with a clear ``next_action`` if any
        step fails (MFA, device approval, expired TOTP, …). Never
        silently fall through — the caller can't distinguish "login
        failed" from "login succeeded but session is stale" without a
        loud signal.
        """
        ...


class EnvLoginHelper:
    """Reads credentials from the environment. Enough for quickstarts.

    Required env vars:

    - ``KEEPER_EMAIL``
    - ``KEEPER_PASSWORD``
    - ``KEEPER_TOTP_SECRET`` (base32; the ``secret=`` param from the
      ``otpauth://totp/...`` URI you stored when 2FA was enabled)

    Optional:

    - ``KEEPER_SERVER`` (default ``keepersecurity.com``)
    - ``KEEPER_CONFIG`` (path to a Commander config JSON to warm)

    This helper honours the :class:`LoginHelper` Protocol, so you can
    point ``KEEPER_SDK_LOGIN_HELPER`` at a Python file that imports and
    re-exports ``EnvLoginHelper().load_keeper_creds`` + ``.keeper_login``
    for a zero-code custom shim.
    """

    TOTP_SAFETY_MARGIN_SECONDS = 5
    """If we're inside the last N seconds of a TOTP window, sleep to the
    next one before logging in — Commander sometimes sends a code that
    expires mid-flight and the login silently fails. See LESSONS.md
    2026-04-23 `[keeper] TOTP expiry race`.
    """

    def load_keeper_creds(self) -> dict[str, str]:
        missing = [
            var
            for var in ("KEEPER_EMAIL", "KEEPER_PASSWORD", "KEEPER_TOTP_SECRET")
            if not os.environ.get(var)
        ]
        if missing:
            raise CapabilityError(
                reason=f"EnvLoginHelper missing env vars: {', '.join(missing)}",
                next_action=(
                    "export KEEPER_EMAIL / KEEPER_PASSWORD / KEEPER_TOTP_SECRET "
                    "(base32 secret, not a 6-digit code), or point "
                    "KEEPER_SDK_LOGIN_HELPER at a custom helper"
                ),
            )
        creds = {
            "email": os.environ["KEEPER_EMAIL"],
            "password": os.environ["KEEPER_PASSWORD"],
            "totp_secret": os.environ["KEEPER_TOTP_SECRET"],
            "config_path": os.environ.get("KEEPER_CONFIG", ""),
        }
        if os.environ.get("KEEPER_SERVER"):
            creds["server"] = os.environ["KEEPER_SERVER"]
        return creds

    def keeper_login(self, email: str, password: str, totp_secret: str, **kwargs: Any) -> Any:
        """Perform a Commander login. Imports ``keepercommander`` lazily
        so the SDK can be imported and used against ``MockProvider``
        without Commander installed.

        When ``config_path`` is supplied (``KEEPER_CONFIG`` env), the
        on-disk Commander config is loaded via ``load_config_properties``
        so persistent-login state (``device_token``, ``clone_code``) is
        reused. Without this load, every invocation triggers a fresh
        device registration that blocks on the tenant's device-approval
        queue — see LESSONS.md 2026-04-25 ``[keeper] EnvLoginHelper
        persistent-login``.
        """
        try:
            import json

            import pyotp  # type: ignore[import-not-found]
            from keepercommander import api  # type: ignore[import-not-found]
            from keepercommander.auth.login_steps import (  # type: ignore[import-not-found]
                DeviceApprovalChannel,
                LoginUi,
                TwoFactorDuration,
            )
            from keepercommander.config_storage.loader import (  # type: ignore[import-not-found]
                load_config_properties,
            )
            from keepercommander.params import KeeperParams  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CapabilityError(
                reason=f"EnvLoginHelper requires keepercommander + pyotp: {exc}",
                next_action="pip install 'declarative-sdk-for-k[commander]' or pip install keepercommander pyotp",
            ) from exc

        self._sleep_past_totp_edge(totp_secret, pyotp)

        config_path = kwargs.get("config_path") or ""
        config_dict: dict[str, Any] = {}
        if config_path:
            try:
                config_dict = json.loads(Path(config_path).read_text(encoding="utf-8"))
            except FileNotFoundError:
                config_dict = {}
            except Exception as exc:
                raise CapabilityError(
                    reason=f"EnvLoginHelper: cannot parse KEEPER_CONFIG at {config_path}: {exc}",
                    next_action=(
                        "ensure KEEPER_CONFIG points at a valid Commander JSON config "
                        "(or unset it to register a fresh device)"
                    ),
                ) from exc

        explicit_server = kwargs.get("server") or ""
        params = KeeperParams(config_filename=config_path, config=config_dict)
        if config_path:
            load_config_properties(params)
        config_server = getattr(params, "server", None) or config_dict.get("server") or ""
        params.user = email
        params.password = password
        params.server = explicit_server or config_server or "keepersecurity.com"

        try:
            ui = _AutoLoginUi(
                password=password,
                totp_secret=totp_secret,
                login_ui_base=LoginUi,
                device_approval_channel=DeviceApprovalChannel.TwoFactor,
                two_factor_duration=TwoFactorDuration.Forever,
            )
            api.login(params, login_ui=ui)
        except Exception as exc:
            raise CapabilityError(
                reason=f"EnvLoginHelper Commander login failed: {type(exc).__name__}: {exc}",
                next_action=(
                    "verify KEEPER_EMAIL / KEEPER_PASSWORD / KEEPER_TOTP_SECRET, "
                    "then re-run. If the tenant requires device approval, switch "
                    "to a custom helper that consents to the approval queue."
                ),
            ) from exc

        if not getattr(params, "session_token", None):
            raise CapabilityError(
                reason="EnvLoginHelper: Commander login returned no session token",
                next_action="retry; if persistent, inspect ~/.keeper/ config state and purge stale tokens",
            )
        return params

    @classmethod
    def _sleep_past_totp_edge(cls, totp_secret: str, pyotp_module: Any) -> None:
        totp = pyotp_module.TOTP(totp_secret)
        # TOTP windows are 30s wide; the boundary is where the secret
        # flips under us. Align to the safe interior of the window.
        seconds_into_window = int(time.time()) % 30
        remaining = 30 - seconds_into_window
        if remaining <= cls.TOTP_SAFETY_MARGIN_SECONDS:
            time.sleep(remaining + 1)
        _ = totp.now()  # also warms pyotp's internal state


class _AutoLoginUi:
    """Answers Commander's full ``LoginUi`` protocol headlessly.

    Commander's ``api.login`` invokes step-based callbacks
    (``on_password``, ``on_two_factor``, ``on_device_approval``,
    ``on_sso_redirect``, ``on_sso_data_key``). Earlier versions of this
    helper only stubbed two of them and returned strings/bools, which
    matched no real protocol method and caused ``api.login`` to hang
    waiting for a step that never completed. The current implementation
    mirrors the lab's ``deploy_watcher.AutoUI`` (proven against this
    tenant) — see LESSONS.md 2026-04-25 ``[keeper] EnvLoginHelper UI
    contract``.

    The class is constructed dynamically so the SDK doesn't import
    ``keepercommander.auth.login_steps`` at module load time
    (Commander is an optional extra).
    """

    def __init__(
        self,
        *,
        password: str,
        totp_secret: str,
        login_ui_base: type,
        device_approval_channel: Any,
        two_factor_duration: Any,
    ) -> None:
        self._password = password
        self._totp_secret = totp_secret
        self._device_approval_channel = device_approval_channel
        self._two_factor_duration = two_factor_duration
        # Re-parent at construction so isinstance(self, LoginUi) holds
        # for Commander's runtime checks.
        self.__class__ = type(  # type: ignore[assignment]
            "_AutoLoginUiBound", (_AutoLoginUi, login_ui_base), {}
        )

    def _fresh_totp(self) -> str:
        import pyotp  # type: ignore[import-not-found]

        remaining = 30 - int(time.time()) % 30
        if remaining < 8:
            time.sleep(remaining + 1)
        return pyotp.TOTP(self._totp_secret).now()

    def on_password(self, step: Any) -> None:
        step.verify_password(self._password)

    def on_two_factor(self, step: Any) -> None:
        channels = step.get_channels()
        if not channels:
            return
        step.duration = self._two_factor_duration
        step.send_code(channels[0].channel_uid, self._fresh_totp())

    def on_device_approval(self, step: Any) -> None:
        step.send_code(self._device_approval_channel, self._fresh_totp())

    def on_sso_redirect(self, step: Any) -> None:
        step.login_with_password()

    def on_sso_data_key(self, step: Any) -> None:
        step.cancel()


def load_helper_from_path(path: str | Path) -> LoginHelper:
    """Import a user-supplied Python file and return its helper.

    The file must expose ``load_keeper_creds`` and ``keeper_login``
    either as module-level functions or on an instance named ``helper``.
    """
    candidate = Path(path)
    if not candidate.is_file():
        raise CapabilityError(
            reason=f"login helper path not found: {candidate}",
            next_action="correct KEEPER_SDK_LOGIN_HELPER or drop it to use EnvLoginHelper",
        )
    spec = importlib.util.spec_from_file_location("_dsk_user_helper", candidate)
    if spec is None or spec.loader is None:
        raise CapabilityError(
            reason=f"cannot load login helper from {candidate}",
            next_action="ensure the file is a valid importable Python module",
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    helper = getattr(module, "helper", module)
    if not (hasattr(helper, "load_keeper_creds") and hasattr(helper, "keeper_login")):
        raise CapabilityError(
            reason=(
                f"login helper at {candidate} does not expose load_keeper_creds + keeper_login"
            ),
            next_action="see docs/LOGIN.md for the minimal contract (~30 lines)",
        )
    return helper  # type: ignore[return-value]
