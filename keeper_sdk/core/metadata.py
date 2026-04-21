"""Ownership metadata encoded on Keeper records.

Canonical payload matches METADATA_OWNERSHIP.md:

    {
      "version": "1",
      "manager": "keeper_declarative",
      "uid_ref": "pc.domain-local-admin",
      "manifest_name": "acme-prod",
      "created_at": "2025-11-20T18:22:10Z",
      "updated_at": "2025-11-20T18:22:10Z",
      "extra": { ... }
    }

Stored as a JSON string in a custom record field labelled
``keeper_declarative_manager`` (single-line text).
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any

MANAGER_NAME = "keeper_declarative"
MARKER_VERSION = "1"
MARKER_FIELD_LABEL = "keeper_declarative_manager"


def encode_marker(
    *,
    uid_ref: str,
    manifest_name: str,
    created_at: str | None = None,
    updated_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "version": MARKER_VERSION,
        "manager": MANAGER_NAME,
        "uid_ref": uid_ref,
        "manifest_name": manifest_name,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
        **({"extra": extra} if extra else {}),
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


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "MANAGER_NAME",
    "MARKER_FIELD_LABEL",
    "MARKER_VERSION",
    "decode_marker",
    "encode_marker",
    "serialize_marker",
]
