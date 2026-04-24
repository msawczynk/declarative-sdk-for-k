"""Ownership metadata encoded on Keeper records.

Canonical payload matches METADATA_OWNERSHIP.md:

    {
      "manager": "keeper-pam-declarative",
      "version": "1",
      "uid_ref": "pc.domain-local-admin",
      "manifest": "acme-prod",
      "resource_type": "pamUser",
      "parent_uid_ref": null,
      "first_applied_at": "2026-04-15T18:22:11Z",
      "last_applied_at": "2026-04-16T02:05:44Z",
      "applied_by": "commander/unknown"
    }

Stored as a JSON string in a custom record field labelled
``keeper_declarative_manager`` (single-line text).
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

MANAGER_NAME = "keeper-pam-declarative"
MARKER_VERSION = "1"
MARKER_FIELD_LABEL = "keeper_declarative_manager"


def encode_marker(
    *,
    uid_ref: str,
    manifest: str,
    resource_type: str,
    parent_uid_ref: str | None = None,
    first_applied_at: str | None = None,
    last_applied_at: str | None = None,
    applied_by: str = "commander/unknown",
) -> dict[str, Any]:
    now = _utc_now()
    first_seen = first_applied_at or now
    return {
        "manager": MANAGER_NAME,
        "version": MARKER_VERSION,
        "uid_ref": uid_ref,
        "manifest": manifest,
        "resource_type": resource_type,
        "parent_uid_ref": parent_uid_ref,
        "first_applied_at": first_seen,
        "last_applied_at": last_applied_at or first_seen,
        "applied_by": applied_by,
    }


def serialize_marker(marker: dict[str, Any]) -> str:
    return json.dumps(marker, separators=(",", ":"), sort_keys=True)


def decode_marker(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("manager") != MANAGER_NAME:
        return data  # still return so diff can flag as foreign-managed
    return data


def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 ``Z``-suffixed string.

    The format matches what :func:`encode_marker` writes into
    ``first_applied_at`` / ``last_applied_at``; exposed as a public
    helper so providers can stamp ``last_applied_at`` without
    round-tripping through :func:`encode_marker` just for the
    timestamp.
    """
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# Backwards-compatible alias; internal-only, will be removed in a future release.
_utc_now = utc_timestamp


__all__ = [
    "MANAGER_NAME",
    "MARKER_FIELD_LABEL",
    "MARKER_VERSION",
    "decode_marker",
    "encode_marker",
    "serialize_marker",
    "utc_timestamp",
]
