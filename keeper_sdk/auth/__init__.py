"""Login-helper contract for the Commander in-process code path.

Why this module exists
----------------------

``CommanderCliProvider._get_keeper_params`` needs a logged-in
``KeeperParams`` object for the two subcommands that Commander refuses
to run cleanly in a subprocess (``pam project import`` and
``pam project extend``). Before v1.0 that login was assumed to come
from ``KEEPER_SDK_LOGIN_HELPER`` pointing at a private workstation
script. That's a dead end for every adopter who isn't the author.

This module ships two things:

1. The ``LoginHelper`` Protocol — the two functions a custom helper
   must expose (``load_keeper_creds`` and ``keeper_login``).
2. ``EnvLoginHelper`` — a working reference implementation that reads
   credentials from environment variables. Enough to get started.
   Production operators still typically wire something smarter (KSM
   pull, HSM-backed TOTP, device-approval queue, …) and point
   ``KEEPER_SDK_LOGIN_HELPER`` at their own module.

Design notes for agent authors
------------------------------

- Every function in this module is pure and side-effect-free until
  ``keeper_login`` is actually called. You can instantiate helpers
  during validation / plan without touching the network.
- Errors raise ``CapabilityError`` with a concrete ``next_action`` so
  the CLI's exit-code-5 path gives the operator a copy-pasteable fix.
- No credential ever lands on disk; ``EnvLoginHelper`` reads env vars
  once and throws the references away after ``keeper_login`` returns.
"""

from __future__ import annotations

from keeper_sdk.auth.helper import (
    EnvLoginHelper,
    LoginHelper,
    load_helper_from_path,
)

__all__ = ["EnvLoginHelper", "LoginHelper", "load_helper_from_path"]
