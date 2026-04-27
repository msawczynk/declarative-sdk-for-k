"""Desired-vs-live diff for ``keeper-vault-sharing.v1`` folders.

Mirrors
``keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json``.
Sprint 7h-40 scope is ``folders[]`` only; ``shared_folders[]``,
``share_records[]``, and ``share_folders[]`` are deferred to 7h-41.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_FIELD_LABEL,
    MARKER_VERSION,
    decode_marker,
    encode_marker,
)
from keeper_sdk.core.sharing_models import SharingManifestV1

_SHARING_FOLDER_RESOURCE = "sharing_folder"
_FOLDER_DIFF_FIELDS = ("path", "parent_folder_uid_ref", "color")


@dataclass(frozen=True)
class _LiveFolder:
    index: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    marker: dict[str, Any] | None
    keeper_uid: str | None
    uid_ref: str | None
    path: str | None


def _marker_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return decode_marker(value)
    return None


def _folder_marker(live_folder: dict[str, Any]) -> dict[str, Any] | None:
    marker = _marker_value(live_folder.get("marker"))
    if marker:
        return marker

    custom = live_folder.get("custom") or live_folder.get("custom_fields")
    if isinstance(custom, dict):
        if custom.get("manager") or custom.get("uid_ref"):
            return custom
        marker = _marker_value(custom.get(MARKER_FIELD_LABEL))
        if marker:
            return marker
    elif isinstance(custom, list):
        for entry in custom:
            if not isinstance(entry, dict):
                continue
            if entry.get("label") != MARKER_FIELD_LABEL and entry.get("name") != MARKER_FIELD_LABEL:
                continue
            marker = _marker_value(entry.get("value"))
            if marker:
                return marker
    return None


def _folder_payload(live_folder: dict[str, Any]) -> dict[str, Any]:
    nested = live_folder.get("payload")
    if isinstance(nested, dict):
        payload = dict(nested)
        for key in ("uid_ref", "path", "parent_folder_uid_ref", "color"):
            if key in live_folder and key not in payload:
                payload[key] = live_folder[key]
        return payload

    payload = dict(live_folder)
    for key in (
        "keeper_uid",
        "folder_uid",
        "uid",
        "resource_type",
        "title",
        "payload",
        "marker",
        "custom",
        "custom_fields",
    ):
        payload.pop(key, None)
    return payload


def _folder_keeper_uid(live_folder: dict[str, Any]) -> str | None:
    value = live_folder.get("keeper_uid") or live_folder.get("folder_uid") or live_folder.get("uid")
    return str(value) if value else None


def _folder_uid_ref(
    payload: dict[str, Any],
    marker: dict[str, Any] | None,
) -> str | None:
    value = payload.get("uid_ref") or (marker or {}).get("uid_ref")
    return str(value) if value else None


def _folder_path(payload: dict[str, Any]) -> str | None:
    value = payload.get("path")
    return str(value) if value else None


def _folder_title(payload: dict[str, Any], uid_ref: str | None) -> str:
    return _folder_path(payload) or str(payload.get("title") or uid_ref or "")


def _desired_folder_payload(
    payload: dict[str, Any],
    *,
    manifest_name: str,
) -> dict[str, Any]:
    out = dict(payload)
    out["marker"] = encode_marker(
        uid_ref=str(payload["uid_ref"]),
        manifest=manifest_name,
        resource_type=_SHARING_FOLDER_RESOURCE,
        parent_uid_ref=payload.get("parent_folder_uid_ref"),
    )
    return out


def _check_marker_supported(marker: dict[str, Any], *, uid_ref: str | None) -> None:
    if marker.get("manager") != MANAGER_NAME:
        return
    if marker.get("version") not in (None, MARKER_VERSION):
        raise OwnershipError(
            reason=f"marker version {marker.get('version')} not supported by core v{MARKER_VERSION}",
            uid_ref=uid_ref,
            resource_type=_SHARING_FOLDER_RESOURCE,
            next_action="upgrade the declarative core or rewrite the marker",
        )


def _folder_managed_by_manifest(
    marker: dict[str, Any] | None,
    *,
    uid_ref: str | None,
    manifest_name: str,
) -> bool:
    if not marker:
        return False
    _check_marker_supported(marker, uid_ref=uid_ref)
    if marker.get("manager") != MANAGER_NAME:
        return False
    marker_manifest = marker.get("manifest")
    return not marker_manifest or marker_manifest == manifest_name


def _index_manifest_folders(manifest: SharingManifestV1) -> dict[str, dict[str, Any]]:
    by_uid_ref: dict[str, dict[str, Any]] = {}
    for folder in manifest.folders:
        if folder.uid_ref in by_uid_ref:
            raise ValueError(f"duplicate manifest folder uid_ref: {folder.uid_ref}")
        by_uid_ref[folder.uid_ref] = folder.model_dump(mode="python", exclude_none=True)
    return by_uid_ref


def _index_live_folders(
    live_folders: list[dict[str, Any]],
) -> tuple[dict[str, _LiveFolder], dict[str, _LiveFolder], list[_LiveFolder]]:
    by_uid_ref: dict[str, _LiveFolder] = {}
    by_path: dict[str, _LiveFolder] = {}
    indexed: list[_LiveFolder] = []
    for index, live_folder in enumerate(live_folders):
        payload = _folder_payload(live_folder)
        marker = _folder_marker(live_folder)
        uid_ref = _folder_uid_ref(payload, marker)
        path = _folder_path(payload)
        row = _LiveFolder(
            index=index,
            raw=live_folder,
            payload=payload,
            marker=marker,
            keeper_uid=_folder_keeper_uid(live_folder),
            uid_ref=uid_ref,
            path=path,
        )
        indexed.append(row)
        if uid_ref and uid_ref not in by_uid_ref:
            by_uid_ref[uid_ref] = row
        if path and path not in by_path:
            by_path[path] = row
    return by_uid_ref, by_path, indexed


def _folder_diff_fields(live_payload: dict[str, Any], desired_payload: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for field in _FOLDER_DIFF_FIELDS:
        if live_payload.get(field) != desired_payload.get(field):
            changed.append(field)
    return changed


def _compute_folders_changes(
    manifest: SharingManifestV1,
    live_folders: list[dict[str, Any]],
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_uid_ref = _index_manifest_folders(manifest)
    live_by_uid_ref, live_by_path, indexed_live = _index_live_folders(live_folders)

    changes: list[Change] = []
    matched: set[int] = set()

    for uid_ref, desired_payload in desired_by_uid_ref.items():
        path = _folder_path(desired_payload)
        live = live_by_uid_ref.get(uid_ref) or (live_by_path.get(path) if path else None)
        title = _folder_title(desired_payload, uid_ref)
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=uid_ref,
                    resource_type=_SHARING_FOLDER_RESOURCE,
                    title=title,
                    after=_desired_folder_payload(
                        desired_payload,
                        manifest_name=manifest_name,
                    ),
                    manifest_name=manifest_name,
                )
            )
            continue

        matched.add(live.index)
        if not _folder_managed_by_manifest(
            live.marker,
            uid_ref=live.uid_ref,
            manifest_name=manifest_name,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_SHARING_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged folder",
                    manifest_name=manifest_name,
                )
            )
            continue

        diff_fields = _folder_diff_fields(live.payload, desired_payload)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref,
                    resource_type=_SHARING_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before={field: live.payload.get(field) for field in diff_fields},
                    after={field: desired_payload.get(field) for field in diff_fields},
                    manifest_name=manifest_name,
                )
            )

    for live in indexed_live:
        if live.index in matched:
            continue
        orphan_uid_ref = live.uid_ref or _folder_path(live.payload)
        title = _folder_title(live.payload, orphan_uid_ref)
        if not _folder_managed_by_manifest(
            live.marker,
            uid_ref=orphan_uid_ref,
            manifest_name=manifest_name,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARING_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged folder",
                    manifest_name=manifest_name,
                )
            )
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARING_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    manifest_name=manifest_name,
                )
            )
            continue
        changes.append(
            Change(
                kind=ChangeKind.SKIP,
                uid_ref=orphan_uid_ref,
                resource_type=_SHARING_FOLDER_RESOURCE,
                title=title,
                keeper_uid=live.keeper_uid,
                before=live.payload,
                reason="managed folder missing from manifest; pass --allow-delete to remove",
                manifest_name=manifest_name,
            )
        )

    return changes


def compute_sharing_diff(
    manifest: SharingManifestV1,
    live_folders: list[dict[str, Any]] | None = None,
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
    live_shared_folders: list[dict[str, Any]] | None = None,
    live_share_records: list[dict[str, Any]] | None = None,
    live_share_folders: list[dict[str, Any]] | None = None,
) -> list[Change]:
    """Classify sharing manifest state vs provider rows.

    Only ``folders[]`` is implemented in this slice. Passing any future block's
    live rows raises so callers do not mistake schema coverage for diff/apply
    coverage.
    """

    if live_shared_folders is not None:
        raise NotImplementedError("shared_folders[] diff is deferred to 7h-41")
    if live_share_records is not None:
        raise NotImplementedError("share_records[] diff is deferred to 7h-41")
    if live_share_folders is not None:
        raise NotImplementedError("share_folders[] diff is deferred to 7h-41")
    if live_folders is not None:
        return _compute_folders_changes(
            manifest,
            live_folders,
            manifest_name=manifest_name,
            allow_delete=allow_delete,
        )
    return []


__all__ = [
    "_SHARING_FOLDER_RESOURCE",
    "_compute_folders_changes",
    "compute_sharing_diff",
]
