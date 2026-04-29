"""Desired-vs-live diff for ``keeper-integrations-events.v1`` offline manifests."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.models_integrations_events import EventsManifestV1

_BLOCK_ORDER = ("automator_rules", "audit_alerts", "api_keys", "event_routes")
_RESOURCE_BY_BLOCK = {
    "automator_rules": "events_automator_rule",
    "audit_alerts": "events_audit_alert",
    "api_keys": "events_api_key",
    "event_routes": "events_event_route",
}
_DELETE_SKIP_REASON = "unmanaged events object; pass allow_delete=True to remove"
_KIND_ORDER = {
    ChangeKind.CREATE: 0,
    ChangeKind.UPDATE: 1,
    ChangeKind.NOOP: 2,
    ChangeKind.DELETE: 3,
    ChangeKind.SKIP: 3,
    ChangeKind.CONFLICT: 4,
}


def compute_events_diff(
    manifest: EventsManifestV1,
    live_events: EventsManifestV1 | Mapping[str, Any] | None = None,
    *,
    manifest_name: str | None = None,
    allow_delete: bool = False,
) -> list[Change]:
    """Classify desired events state against an offline live snapshot."""
    desired = _index_objects(_payload_from_manifest(manifest))
    live, duplicate_live = _index_live(_payload_from_live(live_events))
    manifest_name = manifest_name or manifest.name

    changes: list[Change] = []
    for key, desired_obj in desired.items():
        if key in duplicate_live:
            continue
        live_obj = live.get(key)
        if live_obj is None:
            changes.append(
                Change(
                    kind=ChangeKind.CREATE,
                    uid_ref=desired_obj.uid_ref,
                    resource_type=desired_obj.resource_type,
                    title=desired_obj.title,
                    before={},
                    after=desired_obj.payload,
                    manifest_name=manifest_name,
                )
            )
            continue

        before, after = _field_delta(live_obj.payload, desired_obj.payload, desired_obj.key_field)
        if before or after:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=desired_obj.uid_ref,
                    resource_type=desired_obj.resource_type,
                    title=desired_obj.title,
                    keeper_uid=live_obj.keeper_uid,
                    before=before,
                    after=after,
                    manifest_name=manifest_name,
                )
            )
            continue

        changes.append(
            Change(
                kind=ChangeKind.NOOP,
                uid_ref=desired_obj.uid_ref,
                resource_type=desired_obj.resource_type,
                title=desired_obj.title,
                keeper_uid=live_obj.keeper_uid,
                before=live_obj.payload,
                after=desired_obj.payload,
                reason="no drift",
                manifest_name=manifest_name,
            )
        )

    for key, live_obj in live.items():
        if key in desired or key in duplicate_live:
            continue
        kind = ChangeKind.DELETE if allow_delete else ChangeKind.SKIP
        changes.append(
            Change(
                kind=kind,
                uid_ref=live_obj.uid_ref,
                resource_type=live_obj.resource_type,
                title=live_obj.title,
                keeper_uid=live_obj.keeper_uid,
                before=live_obj.payload,
                reason=None if allow_delete else _DELETE_SKIP_REASON,
                manifest_name=manifest_name,
            )
        )

    for rows in duplicate_live.values():
        first = rows[0]
        changes.append(
            Change(
                kind=ChangeKind.CONFLICT,
                uid_ref=first.uid_ref,
                resource_type=first.resource_type,
                title=first.title,
                before={"key": first.key, "count": len(rows)},
                reason=f"duplicate live events object key: {first.key}",
                manifest_name=manifest_name,
            )
        )

    return sorted(changes, key=_change_sort_key)


class _EventsObject:
    def __init__(self, *, block: str, payload: dict[str, Any]) -> None:
        self.block = block
        self.payload = _normalise_payload(block, payload)
        self.resource_type = _RESOURCE_BY_BLOCK[block]
        self.key_field = "uid_ref"
        self.key = f"{block}:{self.payload['uid_ref']}"
        self.uid_ref = str(self.payload["uid_ref"])
        self.title = str(self.payload.get("name") or self.uid_ref)
        keeper_uid = self.payload.get("keeper_uid")
        self.keeper_uid = str(keeper_uid) if keeper_uid is not None else None


def _payload_from_manifest(manifest: EventsManifestV1) -> dict[str, Any]:
    return manifest.model_dump(mode="python", exclude_none=True, by_alias=True)


def _payload_from_live(
    live_events: EventsManifestV1 | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if live_events is None:
        return {block: [] for block in _BLOCK_ORDER}
    if isinstance(live_events, EventsManifestV1):
        return live_events.model_dump(mode="python", exclude_none=True, by_alias=True)
    return dict(live_events)


def _index_objects(payload: Mapping[str, Any]) -> dict[str, _EventsObject]:
    out: dict[str, _EventsObject] = {}
    for block in _BLOCK_ORDER:
        for row in payload.get(block) or []:
            if not isinstance(row, Mapping):
                continue
            obj = _EventsObject(block=block, payload=dict(row))
            out[obj.key] = obj
    return out


def _index_live(
    payload: Mapping[str, Any],
) -> tuple[dict[str, _EventsObject], dict[str, list[_EventsObject]]]:
    grouped: dict[str, list[_EventsObject]] = defaultdict(list)
    for block in _BLOCK_ORDER:
        for row in payload.get(block) or []:
            if not isinstance(row, Mapping):
                continue
            obj = _EventsObject(block=block, payload=dict(row))
            grouped[obj.key].append(obj)

    live: dict[str, _EventsObject] = {}
    duplicate: dict[str, list[_EventsObject]] = {}
    for key, rows in grouped.items():
        if len(rows) > 1:
            duplicate[key] = rows
        else:
            live[key] = rows[0]
    return live, duplicate


def _normalise_payload(block: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = {key: _normalise_value(value) for key, value in payload.items() if value is not None}
    out.pop("keeper_uid", None)
    if block == "automator_rules":
        out.setdefault("filter_tags", [])
    if block == "audit_alerts":
        out.setdefault("severity", "medium")
    if block == "api_keys":
        out.setdefault("scopes", [])
        out.setdefault("ip_allowlist", [])
    return out


def _normalise_value(value: Any) -> Any:
    if isinstance(value, list):
        normalised = [_normalise_value(item) for item in value]
        if all(not isinstance(item, dict | list) for item in normalised):
            return sorted(normalised, key=lambda item: str(item))
        return sorted(normalised, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, dict):
        return {key: _normalise_value(value[key]) for key in sorted(value)}
    return value


def _field_delta(
    live_payload: dict[str, Any],
    desired_payload: dict[str, Any],
    key_field: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = sorted(set(live_payload) | set(desired_payload))
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for key in keys:
        if key == key_field:
            continue
        if live_payload.get(key) == desired_payload.get(key):
            continue
        before[key] = live_payload.get(key)
        after[key] = desired_payload.get(key)
    return before, after


def _change_sort_key(change: Change) -> tuple[int, int, str]:
    block_rank = {
        resource: index for index, resource in enumerate(_RESOURCE_BY_BLOCK.values())
    }.get(change.resource_type, len(_RESOURCE_BY_BLOCK))
    return (_KIND_ORDER[change.kind], block_rank, change.uid_ref or change.title)


__all__ = ["compute_events_diff"]
