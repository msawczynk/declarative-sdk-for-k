"""Runtime Commander version detection and feature-gate predicates."""

from __future__ import annotations

import os
from functools import lru_cache

try:
    import importlib.metadata as _meta
except ImportError:
    import importlib_metadata as _meta  # type: ignore[import-not-found,no-redef]


@lru_cache(maxsize=1)
def get_commander_version() -> tuple[int, int, int]:
    """Return (major, minor, patch) of installed keepercommander, or (0, 0, 0) on error."""
    try:
        ver = _meta.version("keepercommander")
        parts = ver.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return (0, 0, 0)


def v18_or_later() -> bool:
    """True when Commander >=18.0.0 OR env override DSK_COMMANDER_V18=1."""
    if os.environ.get("DSK_COMMANDER_V18") == "1":
        return True
    major, _, _ = get_commander_version()
    return major >= 18


def v18_rotation_info_json() -> bool:
    """pam rotation info --format=json (PR #2003)."""
    return v18_or_later()


def v18_sm_token_add() -> bool:
    """secrets-manager token add <app_uid> (PR #2004)."""
    return v18_or_later()


def v18_project_import_server_dedup() -> bool:
    """pam project import server-side uid dedup guard (PR #2005)."""
    return v18_or_later()


def v18_project_export_native() -> bool:
    """pam project export native command (PR #2006)."""
    return v18_or_later()
