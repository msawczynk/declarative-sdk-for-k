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
        return {
            "email": os.environ["KEEPER_EMAIL"],
            "password": os.environ["KEEPER_PASSWORD"],
            "totp_secret": os.environ["KEEPER_TOTP_SECRET"],
            "server": os.environ.get("KEEPER_SERVER", "keepersecurity.com"),
            "config_path": os.environ.get("KEEPER_CONFIG", ""),
        }

    def keeper_login(self, email: str, password: str, totp_secret: str, **kwargs: Any) -> Any:
        """Perform a Commander login. Imports ``keepercommander`` lazily
        so the SDK can be imported and used against ``MockProvider``
        without Commander installed."""
        try:
            import pyotp  # type: ignore[import-not-found]
            from keepercommander import api  # type: ignore[import-not-found]
            from keepercommander.params import KeeperParams  # type: ignore[import-not-found]
        except ImportError as exc:
            raise CapabilityError(
                reason=f"EnvLoginHelper requires keepercommander + pyotp: {exc}",
                next_action="pip install 'declarative-sdk-for-k[commander]' or pip install keepercommander pyotp",
            ) from exc

        self._sleep_past_totp_edge(totp_secret, pyotp)

        params = KeeperParams()
        params.server = kwargs.get("server") or "keepersecurity.com"
        if kwargs.get("config_path"):
            params.config_filename = kwargs["config_path"]
        params.user = email
        params.password = password

        try:
            ui = _AutoLoginUi(totp_secret=totp_secret)
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
    """Answers Commander's two-factor + device-approval prompts headlessly.

    Extracted as a nested helper so operators who want different
    prompt behaviour (e.g. fail on device-approval instead of
    auto-accepting) can subclass ``EnvLoginHelper`` and override
    ``_make_ui``.
    """

    def __init__(self, totp_secret: str) -> None:
        self._totp_secret = totp_secret

    def on_two_factor(self, *_args: Any, **_kwargs: Any) -> str:
        import pyotp  # type: ignore[import-not-found]

        return pyotp.TOTP(self._totp_secret).now()

    def on_device_approval(self, *_args: Any, **_kwargs: Any) -> bool:
        return True


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
