"""Change classification between desired (manifest) and observed (provider)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from keeper_sdk.core.errors import CollisionError, OwnershipError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MANAGER_NAME, MARKER_VERSION
from keeper_sdk.core.models import Manifest


class ChangeKind(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"
    CONFLICT = "conflict"


@dataclass
class Change:
    kind: ChangeKind
    uid_ref: str | None
    resource_type: str
    title: str
    keeper_uid: str | None = None
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


_MANAGED_TYPES = (
    "gateway",
    "pam_configuration",
    "pamMachine",
    "pamDatabase",
    "pamDirectory",
    "pamRemoteBrowser",
    "pamUser",
    "login",
)


def _desired_objects(manifest: Manifest) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Yield (uid_ref, resource_type, title, payload) for every managed object."""
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    data = manifest.model_dump(mode="python", exclude_none=True)

    for gateway in data.get("gateways") or []:
        if gateway.get("mode") == "create":
            out.append((gateway["uid_ref"], "gateway", gateway.get("name", ""), gateway))
    for cfg in data.get("pam_configurations") or []:
        title = cfg.get("title") or cfg.get("uid_ref")
        out.append((cfg["uid_ref"], "pam_configuration", title, cfg))
    for res in data.get("resources") or []:
        out.append((res["uid_ref"], res["type"], res.get("title", ""), res))
        for user in res.get("users") or []:
            out.append((user.get("uid_ref") or "", user["type"], user.get("title", ""), user))
    for user in data.get("users") or []:
        out.append((user.get("uid_ref") or "", user["type"], user.get("title", ""), user))
    return out


def compute_diff(
    manifest: Manifest,
    live_records: list[LiveRecord],
    *,
    manifest_name: str | None = None,
    allow_delete: bool = False,
) -> list[Change]:
    """Classify desired vs observed.

    Matching rules:
      1. Prefer LiveRecord.marker.uid_ref == desired.uid_ref when present.
      2. Otherwise match by (resource_type, title).
      3. Live records with a marker whose ``manager != keeper_declarative`` are
         flagged as CONFLICT and never altered.
    """
    manifest_name = manifest_name or manifest.name
    changes: list[Change] = []

    by_uid_ref: dict[str, LiveRecord] = {}
    by_title: dict[tuple[str, str], LiveRecord] = {}
    for live in live_records:
        marker_uid_ref = (live.marker or {}).get("uid_ref") if live.marker else None
        if marker_uid_ref:
            by_uid_ref[marker_uid_ref] = live
        by_title[(live.resource_type, live.title)] = live

    matched: set[str] = set()  # keeper_uid
    desired = _desired_objects(manifest)

    for uid_ref, resource_type, title, payload in desired:
        live = by_uid_ref.get(uid_ref) or by_title.get((resource_type, title))
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.CREATE,
                    uid_ref=uid_ref or None,
                    resource_type=resource_type,
                    title=title,
                    after=payload,
                )
            )
            continue

        marker = live.marker or {}
        manager = marker.get("manager")
        if marker and manager and manager != MANAGER_NAME:
            changes.append(
                Change(
                    kind=ChangeKind.CONFLICT,
                    uid_ref=uid_ref or None,
                    resource_type=resource_type,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    reason=f"record managed by '{manager}', refusing to touch",
                )
            )
            continue
        if marker and marker.get("version") not in (None, MARKER_VERSION):
            raise OwnershipError(
                reason=f"marker version {marker.get('version')} not supported by core v{MARKER_VERSION}",
                uid_ref=uid_ref,
                resource_type=resource_type,
                live_identifier=live.keeper_uid,
                next_action="upgrade the declarative core or rewrite the marker",
            )
        if not marker and by_title.get((resource_type, title)) is live:
            # record exists with the right title but no marker — manifest
            # has not yet adopted it. Offer adoption via update.
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref or None,
                    resource_type=resource_type,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    after=payload,
                    reason="adoption: write ownership marker",
                )
            )
            matched.add(live.keeper_uid)
            continue

        diff_fields = _field_diff(live.payload, payload)
        if not diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.NOOP,
                    uid_ref=uid_ref or None,
                    resource_type=resource_type,
                    title=title,
                    keeper_uid=live.keeper_uid,
                )
            )
        else:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref or None,
                    resource_type=resource_type,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before={k: live.payload.get(k) for k in diff_fields},
                    after={k: payload.get(k) for k in diff_fields},
                )
            )
        matched.add(live.keeper_uid)

    # deletion candidates: live records owned by this manifest with no desired match
    if allow_delete:
        for live in live_records:
            if live.keeper_uid in matched:
                continue
            marker = live.marker or {}
            if marker.get("manager") != MANAGER_NAME:
                continue
            if marker.get("manifest_name") and manifest_name and marker.get("manifest_name") != manifest_name:
                continue
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=marker.get("uid_ref"),
                    resource_type=live.resource_type,
                    title=live.title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                )
            )
    else:
        for live in live_records:
            if live.keeper_uid in matched:
                continue
            marker = live.marker or {}
            if marker.get("manager") == MANAGER_NAME and marker.get("manifest_name") == manifest_name:
                changes.append(
                    Change(
                        kind=ChangeKind.CONFLICT,
                        uid_ref=marker.get("uid_ref"),
                        resource_type=live.resource_type,
                        title=live.title,
                        keeper_uid=live.keeper_uid,
                        reason="managed record missing from manifest; pass --allow-delete to remove",
                    )
                )

    return changes


_DIFF_IGNORED_FIELDS = frozenset({
    "uid_ref",
    "attachments",
    "scripts",
    "custom_fields",
    "record_uid",
})


def _field_diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return keys whose value differs. Only compare overlapping canonical keys."""
    keys: set[str] = set(before) | set(after)
    changed: list[str] = []
    for key in keys:
        if key in _DIFF_IGNORED_FIELDS:
            continue
        # only treat a key as changed if the desired side actually set it; this
        # avoids churn on fields the caller doesn't manage.
        if key not in after:
            continue
        if before.get(key) != after.get(key):
            changed.append(key)
    return sorted(changed)


__all__ = ["Change", "ChangeKind", "compute_diff", "CollisionError"]
