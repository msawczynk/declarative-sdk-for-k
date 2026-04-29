"""Desired-vs-live diff for ``keeper-ksm.v1`` offline manifests."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.models_ksm import KsmManifestV1

_BLOCK_ORDER = ("apps", "tokens", "record_shares", "config_outputs")
_RESOURCE_BY_BLOCK = {
    "apps": "ksm_app",
    "tokens": "ksm_token",
    "record_shares": "ksm_record_share",
    "config_outputs": "ksm_config_output",
}
_DELETE_SKIP_REASON = "unmanaged KSM object; pass allow_delete=True to remove"
_KIND_ORDER = {
    ChangeKind.CREATE: 0,
    ChangeKind.UPDATE: 1,
    ChangeKind.NOOP: 2,
    ChangeKind.DELETE: 3,
    ChangeKind.SKIP: 3,
    ChangeKind.CONFLICT: 4,
}


def compute_ksm_diff(
    manifest: KsmManifestV1,
    live_ksm: KsmManifestV1 | Mapping[str, Any] | None = None,
    *,
    manifest_name: str | None = None,
    allow_delete: bool = False,
) -> list[Change]:
    """Classify desired KSM state against an offline live snapshot."""
    desired = _index_objects(_payload_from_manifest(manifest))
    live, duplicate_live = _index_live(_payload_from_live(live_ksm))
    manifest_name = manifest_name or "keeper-ksm"

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

        before, after = _field_delta(live_obj.payload, desired_obj.payload)
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
                before={"uid_ref": first.uid_ref, "count": len(rows)},
                reason=f"duplicate live KSM key: {first.key}",
                manifest_name=manifest_name,
            )
        )

    return sorted(changes, key=_change_sort_key)


class _KsmObject:
    def __init__(self, *, block: str, payload: dict[str, Any]) -> None:
        self.block = block
        self.payload = _normalise_payload(payload)
        self.key = _key_for(block, self.payload)
        self.uid_ref = _uid_ref_for(block, self.payload)
        self.resource_type = _RESOURCE_BY_BLOCK[block]
        self.title = _title_for(block, self.payload)
        keeper_uid = self.payload.get("keeper_uid")
        self.keeper_uid = str(keeper_uid) if keeper_uid is not None else None


def _payload_from_manifest(manifest: KsmManifestV1) -> dict[str, Any]:
    return manifest.model_dump(mode="python", exclude_none=True, by_alias=True)


def _payload_from_live(live_ksm: KsmManifestV1 | Mapping[str, Any] | None) -> dict[str, Any]:
    if live_ksm is None:
        return {block: [] for block in _BLOCK_ORDER}
    if isinstance(live_ksm, KsmManifestV1):
        return live_ksm.model_dump(mode="python", exclude_none=True, by_alias=True)
    return dict(live_ksm)


def _index_objects(payload: Mapping[str, Any]) -> dict[str, _KsmObject]:
    out: dict[str, _KsmObject] = {}
    for block in _BLOCK_ORDER:
        for row in payload.get(block) or []:
            if not isinstance(row, Mapping):
                continue
            obj = _KsmObject(block=block, payload=dict(row))
            out[obj.key] = obj
    return out


def _index_live(
    payload: Mapping[str, Any],
) -> tuple[dict[str, _KsmObject], dict[str, list[_KsmObject]]]:
    grouped: dict[str, list[_KsmObject]] = defaultdict(list)
    for block in _BLOCK_ORDER:
        for row in payload.get(block) or []:
            if not isinstance(row, Mapping):
                continue
            obj = _KsmObject(block=block, payload=dict(row))
            grouped[obj.key].append(obj)

    live: dict[str, _KsmObject] = {}
    duplicate: dict[str, list[_KsmObject]] = {}
    for key, rows in grouped.items():
        if len(rows) > 1:
            duplicate[key] = rows
        else:
            live[key] = rows[0]
    return live, duplicate


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = {key: _normalise_value(value) for key, value in payload.items() if value is not None}
    out.pop("keeper_uid", None)
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = sorted(set(live_payload) | set(desired_payload))
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for key in keys:
        if key == "uid_ref":
            continue
        if live_payload.get(key) == desired_payload.get(key):
            continue
        before[key] = live_payload.get(key)
        after[key] = desired_payload.get(key)
    return before, after


def _key_for(block: str, payload: dict[str, Any]) -> str:
    if block in ("apps", "tokens"):
        return f"{block}:{payload['uid_ref']}"
    if block == "record_shares":
        return f"{block}:{payload['app_uid_ref']}|{payload['record_uid_ref']}"
    if block == "config_outputs":
        return f"{block}:{payload['app_uid_ref']}|{payload['output_path']}"
    raise KeyError(block)


def _uid_ref_for(block: str, payload: dict[str, Any]) -> str:
    if block in ("apps", "tokens"):
        return str(payload["uid_ref"])
    if block == "record_shares":
        return f"share:{payload['app_uid_ref']}:{payload['record_uid_ref']}"
    if block == "config_outputs":
        return f"config:{payload['app_uid_ref']}:{payload['output_path']}"
    raise KeyError(block)


def _title_for(block: str, payload: dict[str, Any]) -> str:
    if block in ("apps", "tokens"):
        return str(payload.get("name") or payload["uid_ref"])
    if block == "record_shares":
        return f"{payload['app_uid_ref']} -> {payload['record_uid_ref']}"
    if block == "config_outputs":
        return str(payload["output_path"])
    return str(payload.get("uid_ref") or _key_for(block, payload))


def _change_sort_key(change: Change) -> tuple[int, int, str]:
    block_rank = {
        resource: index for index, resource in enumerate(_RESOURCE_BY_BLOCK.values())
    }.get(change.resource_type, len(_RESOURCE_BY_BLOCK))
    return (_KIND_ORDER[change.kind], block_rank, change.uid_ref or change.title)


__all__ = ["compute_ksm_diff"]
