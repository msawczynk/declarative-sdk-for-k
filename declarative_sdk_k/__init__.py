"""Forward-compatible package name for the declarative SDK.

During the v1.x overlap window this package forwards to ``keeper_sdk`` so users
can migrate imports before the implementation package is renamed in v2.0.
"""

from __future__ import annotations

import importlib
import sys
import warnings

_WARNING_MARKER = "_declarative_sdk_k_shim_warning_emitted"
_WARNING_MESSAGE = (
    "declarative_sdk_k is a v1.x compatibility shim over keeper_sdk; the "
    "implementation package moves to declarative_sdk_k in v2.0."
)


def _warn_once() -> None:
    if getattr(sys, _WARNING_MARKER, False):
        return
    warnings.warn(_WARNING_MESSAGE, DeprecationWarning, stacklevel=2)
    setattr(sys, _WARNING_MARKER, True)


_warn_once()

from keeper_sdk import *  # noqa: E402,F401,F403
from keeper_sdk import __all__  # noqa: E402,F401

__version__ = "2.0.0"

_SUBMODULE_ALIASES = ("auth", "cli", "core", "providers", "secrets")

for _name in _SUBMODULE_ALIASES:
    _module = importlib.import_module(f"keeper_sdk.{_name}")
    sys.modules.setdefault(f"{__name__}.{_name}", _module)
    globals()[_name] = _module

del importlib, _name, _module
