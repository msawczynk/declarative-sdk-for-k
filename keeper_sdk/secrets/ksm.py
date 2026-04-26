"""Keeper Secrets Manager (KSM) consumer for SDK-side credential pulls.

See :mod:`keeper_sdk.secrets` for the package-level rationale.

Public surface
--------------

- :class:`KsmSecretStore` — thin façade over
  ``keeper_secrets_manager_core.SecretsManager`` with field-value caching
  scoped to a single store instance. Callers that need a long-lived
  cache should hold the store; callers that need fresh reads after a
  rotation should construct a new store.

- :class:`KsmLoginCreds` — the three values the Commander login flow
  needs, returned by :func:`load_keeper_login_from_ksm`.

- :func:`load_keeper_login_from_ksm` — the convenience wrapper used by
  :class:`keeper_sdk.auth.KsmLoginHelper`. Lives here so SDK callers
  building their own login flows can reuse it without depending on
  ``keeper_sdk.auth``.

Configuration
-------------

The store accepts an explicit ``config_path``; otherwise it walks the
following list (first usable wins):

1. ``$KEEPER_SDK_KSM_CONFIG``
2. ``$KSM_CONFIG`` (kept for parity with operator-side daybook scripts)
3. ``~/.keeper/caravan-ksm-config.json``
4. ``~/.keeper/ksm-config.json``

Different KSM applications see different shared-folder grants; the
caller is expected to know which application owns the records they want
to read. ``KsmSecretStore.config_path`` exposes the resolved choice for
auditing / logging.

Field-name conventions
----------------------

The Commander admin-login record produced by the Keeper Web UI carries
typed fields ``login`` (email), ``password``, and ``oneTimeCode``
(``otpauth://`` URI). :func:`load_keeper_login_from_ksm` defaults to
those names but accepts overrides via the ``KEEPER_SDK_KSM_*_FIELD``
env vars listed below — useful when the operator wants to pin a
different record schema (e.g. a ``custom`` field labelled ``svc-admin-totp``).

| Env var                                | Default        |
|----------------------------------------|----------------|
| ``KEEPER_SDK_KSM_LOGIN_FIELD``         | ``login``      |
| ``KEEPER_SDK_KSM_PASSWORD_FIELD``      | ``password``   |
| ``KEEPER_SDK_KSM_TOTP_FIELD``          | ``oneTimeCode``|
| ``KEEPER_SDK_KSM_CREDS_RECORD_UID``    | (no default)   |

The TOTP value is normalised to a base32 secret (the ``secret=``
parameter of an ``otpauth://`` URI) so callers can drop it straight into
``pyotp.TOTP``. If the field already holds a bare base32 string the
parser passes it through; the heuristic only converts ``otpauth://``
inputs.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from keeper_sdk.core.errors import CapabilityError

KSM_CONFIG_ENV = "KEEPER_SDK_KSM_CONFIG"
"""Primary env var an operator sets to point the SDK at a KSM app config.

Independent from ``KSM_CONFIG`` so SDK consumers can co-exist with the
daybook ``ksm_lib.py`` operator-side helper without fighting over a
shared variable. If both are unset the auto-discovery probes fire.
"""

KSM_TOTP_ENV_PARSE_FALLBACK = "KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH"
"""When set to a truthy value, :func:`load_keeper_login_from_ksm` will
return the raw ``otpauth://`` URI for callers that prefer to parse it
themselves. Default behaviour (env unset / ``"0"``) extracts the
``secret`` query param so the value drops straight into ``pyotp.TOTP``.
"""

DEFAULT_CONFIG_PROBES: tuple[Path, ...] = (
    Path.home() / ".keeper" / "caravan-ksm-config.json",
    Path.home() / ".keeper" / "ksm-config.json",
)
"""Standard locations checked when no explicit ``config_path`` is given.

The lab tenant's ``ksm-config.json`` lives in a sibling repo and is NOT
included here on purpose — production adopters should drop their KSM
client config under ``~/.keeper/`` (the same convention Commander uses)
rather than relying on a path the SDK guesses. Override via
``KEEPER_SDK_KSM_CONFIG`` for ad-hoc runs.
"""


def _resolve_config_path(config_path: str | os.PathLike[str] | None) -> Path:
    if config_path:
        candidate = Path(config_path).expanduser()
        if not candidate.is_file():
            raise CapabilityError(
                reason=f"KSM config not found at {candidate}",
                next_action=(
                    f"create the KSM client config at {candidate} or pass a "
                    "different config_path / set KEEPER_SDK_KSM_CONFIG"
                ),
            )
        return candidate
    for env_name in (KSM_CONFIG_ENV, "KSM_CONFIG"):
        env_val = os.environ.get(env_name)
        if not env_val:
            continue
        candidate = Path(env_val).expanduser()
        if candidate.is_file():
            return candidate
    for probe in DEFAULT_CONFIG_PROBES:
        if probe.is_file():
            return probe
    raise CapabilityError(
        reason="no KSM client config found",
        next_action=(
            f"set {KSM_CONFIG_ENV} to your ksm-config.json path, or place the "
            f"file at one of: {', '.join(str(p) for p in DEFAULT_CONFIG_PROBES)}"
        ),
    )


def _import_ksm_core() -> Any:
    """Import ``keeper_secrets_manager_core`` lazily.

    Raises :class:`CapabilityError` with a copy-pasteable next-action when
    the optional extra is missing — keeps the rest of the SDK importable
    without the heavy KSM dep.
    """
    try:
        import keeper_secrets_manager_core  # type: ignore[import-not-found]
        from keeper_secrets_manager_core.storage import (  # type: ignore[import-not-found]
            FileKeyValueStorage,
        )
    except ImportError as exc:
        raise CapabilityError(
            reason=f"keeper_secrets_manager_core is required for KSM-backed access: {exc}",
            next_action="pip install 'declarative-sdk-for-k[ksm]' (or pip install keeper-secrets-manager-core>=17)",
        ) from exc
    return keeper_secrets_manager_core, FileKeyValueStorage


_OTPAUTH_URI = re.compile(r"^otpauth://", re.IGNORECASE)


def _coerce_totp_secret(value: str) -> str:
    """Return a base32 TOTP secret, parsing ``otpauth://`` URIs if needed.

    Pass-through behaviour is suppressed when
    ``KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH`` is truthy — useful for
    callers that prefer to consume the URI shape directly (e.g. mobile
    enrolment flows).
    """
    if not isinstance(value, str) or not value:
        raise CapabilityError(
            reason="KSM TOTP field is empty",
            next_action="populate the record's oneTimeCode field with a TOTP URI or base32 secret",
        )
    if _is_truthy(os.environ.get(KSM_TOTP_ENV_PARSE_FALLBACK, "")):
        return value
    if not _OTPAUTH_URI.match(value):
        return value
    qs = parse_qs(urlparse(value).query)
    secrets = qs.get("secret") or []
    if not secrets:
        raise CapabilityError(
            reason="KSM TOTP otpauth:// URI has no `secret` query parameter",
            next_action="re-enrol the TOTP factor or store the base32 secret directly in the field",
        )
    return secrets[0]


def _is_truthy(s: str | None) -> bool:
    return (s or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class KsmLoginCreds:
    """Frozen credential bundle returned by :func:`load_keeper_login_from_ksm`.

    Mirrors the dict shape :class:`keeper_sdk.auth.LoginHelper` produces
    so the result can be unpacked directly into
    :meth:`keeper_sdk.auth.LoginHelper.keeper_login` callsites.
    """

    email: str
    password: str
    totp_secret: str
    config_path: str = ""
    server: str = ""

    def as_helper_dict(self) -> dict[str, str]:
        """Return the dict form expected by ``LoginHelper.load_keeper_creds``."""
        out = {
            "email": self.email,
            "password": self.password,
            "totp_secret": self.totp_secret,
            "config_path": self.config_path,
        }
        if self.server:
            out["server"] = self.server
        return out


class KsmSecretStore:
    """Lazily-initialised reader for a single KSM application config.

    The store is intentionally minimal — it does NOT cache decrypted
    values across instances and does NOT attempt to refresh on schedule.
    Callers that want long-lived caching wrap it; callers that want
    fresh reads construct a new store. This keeps the SDK from holding
    decrypted credentials in process memory longer than the caller's
    apply / plan loop.

    Example::

        store = KsmSecretStore()  # auto-discovers config
        password = store.field("MyiZN4...","password")

    Multi-app deployments::

        lab = KsmSecretStore(config_path="/path/to/lab/ksm-config.json")
        prod = KsmSecretStore(config_path="/path/to/prod/ksm-config.json")
    """

    def __init__(
        self,
        *,
        config_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self._explicit_config_path = config_path
        self._client: Any | None = None
        self._resolved_config_path: Path | None = None

    @property
    def config_path(self) -> Path:
        """Resolved config path (lazy; raises until first access)."""
        if self._resolved_config_path is None:
            self._resolved_config_path = _resolve_config_path(self._explicit_config_path)
        return self._resolved_config_path

    def client(self) -> Any:
        """Return the cached :class:`SecretsManager` instance.

        Construction is deferred to first use so importing the SDK
        without setting up KSM does not crash.
        """
        if self._client is None:
            ksm_core, FileKeyValueStorage = _import_ksm_core()
            self._client = ksm_core.SecretsManager(
                config=FileKeyValueStorage(str(self.config_path))
            )
        return self._client

    def get_record(self, uid: str) -> Any:
        """Return the raw KSM record object for ``uid``.

        Raises :class:`CapabilityError` (rather than ``LookupError``) so
        the SDK's CLI surface can map it to exit-code 5 with a concrete
        next-action — most "no record" errors are config-mismatch bugs
        the operator can fix in 30 seconds.
        """
        records = self.client().get_secrets([uid])
        if not records:
            raise CapabilityError(
                reason=(
                    f"KSM record {uid[:6]}... not visible to client at {self.config_path} "
                    "(wrong KSM application or no shared-folder grant)"
                ),
                next_action=(
                    "verify the KSM application has the record's shared folder, or "
                    "point KEEPER_SDK_KSM_CONFIG at the application that does"
                ),
            )
        return records[0]

    def field(
        self,
        uid: str,
        field_type: str,
        *,
        label: str | None = None,
        single: bool = True,
    ) -> Any:
        """Return one field value from a record.

        ``field_type`` matches Keeper's typed-field names (``login``,
        ``password``, ``oneTimeCode``, ``url`` ...). When multiple
        fields share a type, pass ``label`` to disambiguate against
        either the typed or the custom block.
        """
        record = self.get_record(uid)
        if label is None:
            return record.field(field_type, single=single)
        for source in (record.dict.get("fields", []), record.dict.get("custom", [])):
            for entry in source or []:
                if entry.get("type") == field_type and (entry.get("label") or "") == label:
                    values = entry.get("value") or []
                    return (values[0] if values else None) if single else values
        raise CapabilityError(
            reason=(f"KSM record {uid[:6]}... has no field type={field_type!r} label={label!r}"),
            next_action=(
                "verify the field exists on the record (Keeper Web UI → record → fields), "
                "or drop the label to take the first matching typed field"
            ),
        )

    def describe(self, uid: str) -> dict[str, Any]:
        """Return shape-only metadata for a record (no values).

        Useful for audit logging or for wiring custom helpers to verify
        a record carries the expected fields before attempting a login.
        """
        record = self.get_record(uid)
        return {
            "uid_prefix": uid[:6] + "..." if len(uid) > 6 else uid,
            "title_prefix": (record.title or "")[:8] + "..." if record.title else "(no title)",
            "fields": [
                {
                    "type": entry.get("type"),
                    "label": entry.get("label") or "",
                    "has_value": bool(entry.get("value")),
                }
                for entry in record.dict.get("fields", [])
            ],
            "custom": [
                {
                    "type": entry.get("type"),
                    "label": entry.get("label") or "",
                    "has_value": bool(entry.get("value")),
                }
                for entry in record.dict.get("custom", [])
            ],
        }


def load_keeper_login_from_ksm(
    record_uid: str,
    *,
    config_path: str | os.PathLike[str] | None = None,
    login_field: str = "login",
    password_field: str = "password",
    totp_field: str = "oneTimeCode",
    server: str | None = None,
    config_path_for_login: str = "",
) -> KsmLoginCreds:
    """Read a Commander admin-login record from KSM.

    ``record_uid`` is the KSM record holding the typed fields
    ``login`` / ``password`` / ``oneTimeCode``. Field names may be
    overridden if the operator stores credentials under custom labels.

    The TOTP value is normalised to a base32 secret unless
    ``KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH`` is truthy.

    ``config_path_for_login`` and ``server`` are passed through to the
    returned :class:`KsmLoginCreds` so callers can pre-populate the
    Commander config-load path / explicit server (the KSM record
    itself does not own those — they're per-machine).
    """
    store = KsmSecretStore(config_path=config_path)
    email = store.field(record_uid, login_field)
    password = store.field(record_uid, password_field)
    totp_raw = store.field(record_uid, totp_field)

    if not (email and password and totp_raw):
        raise CapabilityError(
            reason=(
                f"KSM record {record_uid[:6]}... missing one of "
                f"{login_field!r} / {password_field!r} / {totp_field!r}"
            ),
            next_action=(
                "populate the record's typed fields via Keeper Web UI, or override "
                "field names via KEEPER_SDK_KSM_LOGIN_FIELD / "
                "KEEPER_SDK_KSM_PASSWORD_FIELD / KEEPER_SDK_KSM_TOTP_FIELD"
            ),
        )

    return KsmLoginCreds(
        email=email,
        password=password,
        totp_secret=_coerce_totp_secret(totp_raw),
        config_path=config_path_for_login,
        server=server or "",
    )
