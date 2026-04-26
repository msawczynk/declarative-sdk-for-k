"""KSM-backed secret access for SDK consumers.

Why this module exists
----------------------

Operators routinely store the SDK's runtime credentials (Commander admin
login, TOTP base32 secret, optional Commander config) in a Keeper Secrets
Manager record so a single service-admin record can supply every agent,
CI runner, and ad-hoc operator on the team. Without an in-tree consumer
for that record, every adopter rebuilt the same wrapper around
``keeper_secrets_manager_core``.

This package ships:

- :class:`~keeper_sdk.secrets.ksm.KsmSecretStore` — thin, lazily-initialised
  client that reads any field from any KSM record the application has
  shared-folder access to. Useful for callers that already authenticate
  to Keeper and want to pull adjacent service secrets (DB passwords,
  webhook tokens, SSH keys, ...) from the same vault surface.

- :class:`~keeper_sdk.secrets.ksm.KsmLoginCreds` — a frozen view of the
  three fields the Commander login flow needs (``email``, ``password``,
  ``totp_secret``). Returned by
  :func:`~keeper_sdk.secrets.ksm.load_keeper_login_from_ksm` for use by
  :class:`keeper_sdk.auth.KsmLoginHelper`.

The ``keeper_secrets_manager_core`` dependency is **optional** — install
``pip install 'declarative-sdk-for-k[ksm]'`` to opt in. Importing this
package without it raises a :class:`keeper_sdk.core.errors.CapabilityError`
on first use with a ``next_action`` pointing at the extras install
command. The SDK's other code paths (``EnvLoginHelper``, MockProvider,
plan/apply against a pre-authenticated session) work without the extra.

Hardening
---------

- Field values are returned to the caller verbatim. The library never
  logs them. Callers that print or persist values are responsible for
  redaction; ``keeper_sdk.core.redact`` already handles ``ksm_one_time_token``
  patterns and is the place to add new patterns when needed.

- The KSM client is re-instantiated per
  :class:`KsmSecretStore` because ``keeper_secrets_manager_core`` rotates
  app keys on its own cadence and we don't want a single long-lived
  process to hold a stale storage handle.

- Multiple KSM applications are common (one personal, one tenant, one
  CI). The store accepts an explicit ``config_path`` so callers can
  pick the right shared-folder boundary. Auto-discovery reads the
  optional env var ``KEEPER_SDK_KSM_CONFIG`` first, then falls back to
  the standard probes; see :data:`DEFAULT_CONFIG_PROBES`.
"""

from __future__ import annotations

from keeper_sdk.secrets.ksm import (
    DEFAULT_CONFIG_PROBES,
    KSM_CONFIG_ENV,
    KSM_TOTP_ENV_PARSE_FALLBACK,
    KsmLoginCreds,
    KsmSecretStore,
    load_keeper_login_from_ksm,
)

__all__ = [
    "DEFAULT_CONFIG_PROBES",
    "KSM_CONFIG_ENV",
    "KSM_TOTP_ENV_PARSE_FALLBACK",
    "KsmLoginCreds",
    "KsmSecretStore",
    "load_keeper_login_from_ksm",
]
