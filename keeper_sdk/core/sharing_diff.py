"""Desired-vs-live diff for ``keeper-vault-sharing.v1`` folders and ACL rows.

Mirrors
``keeper_sdk/core/schemas/keeper-vault-sharing/keeper-vault-sharing.v1.schema.json``.
Diff coverage includes ``$defs.folder``, ``$defs.shared_folder``,
``$defs.record_share``, ``$defs.shared_folder_grantee_share``,
``$defs.shared_folder_record_share``, and ``$defs.shared_folder_default_share``.
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
_SHARED_FOLDER_RESOURCE = "sharing_shared_folder"
_RECORD_SHARE_RESOURCE = "sharing_record_share"
_SHARE_FOLDER_RESOURCE = "sharing_share_folder"
_FOLDER_DIFF_FIELDS = ("path", "parent_folder_uid_ref", "color")
_SHARED_FOLDER_DIFF_FIELDS = (
    "name",
    "default_manage_records",
    "default_manage_users",
    "default_can_edit",
    "default_can_share",
)
_RECORD_SHARE_DIFF_FIELDS = ("can_edit", "can_share", "expires_at")
_SHARE_FOLDER_DIFF_FIELDS = (
    "target",
    "manage_records",
    "manage_users",
    "can_edit",
    "can_share",
    "expires_at",
)


@dataclass(frozen=True)
class _LiveFolder:
    index: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    marker: dict[str, Any] | None
    keeper_uid: str | None
    uid_ref: str | None
    path: str | None


@dataclass(frozen=True)
class _LiveSharedFolder:
    index: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    marker: dict[str, Any] | None
    keeper_uid: str | None
    uid_ref: str | None
    name: str | None


@dataclass(frozen=True)
class _LiveRecordShare:
    index: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    marker: dict[str, Any] | None
    keeper_uid: str | None
    uid_ref: str | None
    record_uid_ref: str | None
    grantee_kind: str | None
    grantee_identifier: str | None


@dataclass(frozen=True)
class _LiveShareFolder:
    index: int
    raw: dict[str, Any]
    payload: dict[str, Any]
    marker: dict[str, Any] | None
    keeper_uid: str | None
    uid_ref: str | None
    shared_folder_uid_ref: str | None
    kind: str | None
    identifier: str | None


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


def _check_marker_supported(
    marker: dict[str, Any],
    *,
    uid_ref: str | None,
    resource_type: str = _SHARING_FOLDER_RESOURCE,
) -> None:
    if marker.get("manager") != MANAGER_NAME:
        return
    if marker.get("version") not in (None, MARKER_VERSION):
        raise OwnershipError(
            reason=f"marker version {marker.get('version')} not supported by core v{MARKER_VERSION}",
            uid_ref=uid_ref,
            resource_type=resource_type,
            next_action="upgrade the declarative core or rewrite the marker",
        )


def _managed_by_manifest(
    marker: dict[str, Any] | None,
    *,
    uid_ref: str | None,
    manifest_name: str,
    resource_type: str,
) -> bool:
    if not marker:
        return False
    _check_marker_supported(marker, uid_ref=uid_ref, resource_type=resource_type)
    if marker.get("manager") != MANAGER_NAME:
        return False
    marker_manifest = marker.get("manifest")
    return not marker_manifest or marker_manifest == manifest_name


def _folder_managed_by_manifest(
    marker: dict[str, Any] | None,
    *,
    uid_ref: str | None,
    manifest_name: str,
) -> bool:
    return _managed_by_manifest(
        marker,
        uid_ref=uid_ref,
        manifest_name=manifest_name,
        resource_type=_SHARING_FOLDER_RESOURCE,
    )


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


_WRAPPER_KEYS = {
    "keeper_uid",
    "folder_uid",
    "shared_folder_uid",
    "share_uid",
    "record_uid",
    "uid",
    "resource_type",
    "title",
    "payload",
    "marker",
    "custom",
    "custom_fields",
}


def _sharing_row_payload(
    live_row: dict[str, Any], promoted_keys: tuple[str, ...]
) -> dict[str, Any]:
    nested = live_row.get("payload")
    if isinstance(nested, dict):
        payload = dict(nested)
        for key in promoted_keys:
            if key in live_row and key not in payload:
                payload[key] = live_row[key]
        return payload

    payload = dict(live_row)
    for key in _WRAPPER_KEYS:
        payload.pop(key, None)
    return payload


def _live_keeper_uid(live_row: dict[str, Any], extra_keys: tuple[str, ...] = ()) -> str | None:
    for key in ("keeper_uid", *extra_keys, "share_uid", "uid"):
        value = live_row.get(key)
        if value is not None:
            return str(value)
    return None


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return str(value) if value is not None else None


def _normalise_email(value: Any) -> str:
    return str(value).strip().casefold()


def _diff_fields(
    live_payload: dict[str, Any],
    desired_payload: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    changed: list[str] = []
    for field in fields:
        if field not in live_payload and field not in desired_payload:
            continue
        if live_payload.get(field) != desired_payload.get(field):
            changed.append(field)
    return changed


def _change_payload(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    return {field: payload.get(field) for field in fields}


def _shared_folder_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    name = payload.get("name") or payload.get("path") or payload.get("title")
    if name is not None:
        payload["name"] = str(name)

    defaults = payload.get("defaults")
    defaults = defaults if isinstance(defaults, dict) else {}
    default_map = {
        "default_manage_records": "manage_records",
        "default_manage_users": "manage_users",
        "default_can_edit": "can_edit",
        "default_can_share": "can_share",
    }
    for flat_key, nested_key in default_map.items():
        if flat_key not in payload and nested_key in defaults:
            payload[flat_key] = defaults[nested_key]
    return payload


def _shared_folder_name(payload: dict[str, Any]) -> str | None:
    return _payload_str(payload, "name") or _payload_str(payload, "path")


def _shared_folder_title(payload: dict[str, Any], uid_ref: str | None) -> str:
    return _shared_folder_name(payload) or str(payload.get("title") or uid_ref or "")


def _desired_shared_folder_payload(
    payload: dict[str, Any],
    *,
    manifest_name: str,
) -> dict[str, Any]:
    out = dict(payload)
    out["marker"] = encode_marker(
        uid_ref=str(payload["uid_ref"]),
        manifest=manifest_name,
        resource_type=_SHARED_FOLDER_RESOURCE,
    )
    return out


def _shared_folder_diff_fields(
    live_payload: dict[str, Any],
    desired_payload: dict[str, Any],
) -> list[str]:
    changed: list[str] = []
    for field in _SHARED_FOLDER_DIFF_FIELDS:
        if field.startswith("default_") and field not in desired_payload:
            continue
        if field not in live_payload and field not in desired_payload:
            continue
        if live_payload.get(field) != desired_payload.get(field):
            changed.append(field)
    return changed


def _index_manifest_shared_folders(manifest: SharingManifestV1) -> dict[str, dict[str, Any]]:
    by_uid_ref: dict[str, dict[str, Any]] = {}
    for shared_folder in manifest.shared_folders:
        if shared_folder.uid_ref in by_uid_ref:
            raise ValueError(f"duplicate manifest shared_folder uid_ref: {shared_folder.uid_ref}")
        by_uid_ref[shared_folder.uid_ref] = _shared_folder_payload(
            shared_folder.model_dump(mode="python", exclude_none=True)
        )
    return by_uid_ref


def _index_live_shared_folders(
    live_shared_folders: list[dict[str, Any]],
) -> tuple[dict[str, _LiveSharedFolder], dict[str, _LiveSharedFolder], list[_LiveSharedFolder]]:
    by_uid_ref: dict[str, _LiveSharedFolder] = {}
    by_name: dict[str, _LiveSharedFolder] = {}
    indexed: list[_LiveSharedFolder] = []
    for index, live_shared_folder in enumerate(live_shared_folders):
        payload = _shared_folder_payload(
            _sharing_row_payload(
                live_shared_folder,
                (
                    "uid_ref",
                    "path",
                    "name",
                    "defaults",
                    "default_manage_records",
                    "default_manage_users",
                    "default_can_edit",
                    "default_can_share",
                ),
            )
        )
        marker = _folder_marker(live_shared_folder)
        uid_ref = _folder_uid_ref(payload, marker)
        name = _shared_folder_name(payload)
        row = _LiveSharedFolder(
            index=index,
            raw=live_shared_folder,
            payload=payload,
            marker=marker,
            keeper_uid=_live_keeper_uid(live_shared_folder, ("shared_folder_uid", "folder_uid")),
            uid_ref=uid_ref,
            name=name,
        )
        indexed.append(row)
        if uid_ref and uid_ref not in by_uid_ref:
            by_uid_ref[uid_ref] = row
        if name and name not in by_name:
            by_name[name] = row
    return by_uid_ref, by_name, indexed


def _compute_shared_folders_changes(
    manifest: SharingManifestV1,
    live_shared_folders: list[dict[str, Any]],
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_uid_ref = _index_manifest_shared_folders(manifest)
    live_by_uid_ref, live_by_name, indexed_live = _index_live_shared_folders(live_shared_folders)

    changes: list[Change] = []
    matched: set[int] = set()

    for uid_ref, desired_payload in desired_by_uid_ref.items():
        name = _shared_folder_name(desired_payload)
        live = live_by_uid_ref.get(uid_ref) or (live_by_name.get(name) if name else None)
        title = _shared_folder_title(desired_payload, uid_ref)
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=uid_ref,
                    resource_type=_SHARED_FOLDER_RESOURCE,
                    title=title,
                    after=_desired_shared_folder_payload(
                        desired_payload,
                        manifest_name=manifest_name,
                    ),
                    manifest_name=manifest_name,
                )
            )
            continue

        matched.add(live.index)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=live.uid_ref,
            manifest_name=manifest_name,
            resource_type=_SHARED_FOLDER_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_SHARED_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged shared_folder",
                    manifest_name=manifest_name,
                )
            )
            continue

        diff_fields = _shared_folder_diff_fields(live.payload, desired_payload)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref,
                    resource_type=_SHARED_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=_change_payload(live.payload, diff_fields),
                    after=_change_payload(desired_payload, diff_fields),
                    manifest_name=manifest_name,
                )
            )

    for live in indexed_live:
        if live.index in matched:
            continue
        orphan_uid_ref = live.uid_ref or _shared_folder_name(live.payload)
        title = _shared_folder_title(live.payload, orphan_uid_ref)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=orphan_uid_ref,
            manifest_name=manifest_name,
            resource_type=_SHARED_FOLDER_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARED_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged shared_folder",
                    manifest_name=manifest_name,
                )
            )
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARED_FOLDER_RESOURCE,
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
                resource_type=_SHARED_FOLDER_RESOURCE,
                title=title,
                keeper_uid=live.keeper_uid,
                before=live.payload,
                reason="managed shared_folder missing from manifest",
                manifest_name=manifest_name,
            )
        )

    return changes


def _grantee_parts(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    grantee = payload.get("grantee")
    if isinstance(grantee, dict):
        kind = grantee.get("kind")
        if kind == "user" and grantee.get("user_email") is not None:
            return "user", _normalise_email(grantee["user_email"])
        if kind == "team" and grantee.get("team_uid_ref") is not None:
            return "team", str(grantee["team_uid_ref"])

    if payload.get("user_email") is not None:
        return "user", _normalise_email(payload["user_email"])
    if payload.get("team_uid_ref") is not None:
        return "team", str(payload["team_uid_ref"])
    return None, None


def _record_share_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    permissions = payload.get("permissions")
    permissions = permissions if isinstance(permissions, dict) else {}
    for field in ("can_edit", "can_share"):
        if field not in payload and field in permissions:
            payload[field] = permissions[field]

    grantee_kind, grantee_identifier = _grantee_parts(payload)
    if grantee_kind == "user" and grantee_identifier is not None:
        payload["user_email"] = grantee_identifier
    elif grantee_kind == "team" and grantee_identifier is not None:
        payload.setdefault("team_uid_ref", grantee_identifier)
    return payload


def _record_share_key(payload: dict[str, Any]) -> tuple[str, str]:
    record_uid_ref = _payload_str(payload, "record_uid_ref")
    if not record_uid_ref:
        raise ValueError("record_share missing record_uid_ref")
    _, grantee_identifier = _grantee_parts(payload)
    if not grantee_identifier:
        raise ValueError("record_share missing grantee")
    return (record_uid_ref, grantee_identifier)


def _record_share_title(payload: dict[str, Any]) -> str:
    record_uid_ref, grantee_identifier = _record_share_key(payload)
    return f"{record_uid_ref}:{grantee_identifier}"


def _desired_record_share_payload(
    payload: dict[str, Any],
    *,
    manifest_name: str,
) -> dict[str, Any]:
    out = dict(payload)
    out["marker"] = encode_marker(
        uid_ref=str(payload["uid_ref"]),
        manifest=manifest_name,
        resource_type=_RECORD_SHARE_RESOURCE,
        parent_uid_ref=str(payload["record_uid_ref"]),
    )
    return out


def _index_manifest_record_shares(
    manifest: SharingManifestV1,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_uid_ref: dict[str, dict[str, Any]] = {}
    for record_share in manifest.share_records:
        payload = _record_share_payload(record_share.model_dump(mode="python", exclude_none=True))
        uid_ref = str(payload["uid_ref"])
        if uid_ref in by_uid_ref:
            raise ValueError(f"duplicate manifest record_share uid_ref: {uid_ref}")
        key = _record_share_key(payload)
        if key in by_key:
            raise ValueError(f"duplicate manifest record_share key: {key}")
        by_uid_ref[uid_ref] = payload
        by_key[key] = payload
    return by_key, by_uid_ref


def _index_live_record_shares(
    live_record_shares: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, str], _LiveRecordShare], dict[str, _LiveRecordShare], list[_LiveRecordShare]
]:
    by_key: dict[tuple[str, str], _LiveRecordShare] = {}
    by_uid_ref: dict[str, _LiveRecordShare] = {}
    indexed: list[_LiveRecordShare] = []
    for index, live_record_share in enumerate(live_record_shares):
        payload = _record_share_payload(
            _sharing_row_payload(
                live_record_share,
                (
                    "uid_ref",
                    "record_uid_ref",
                    "user_email",
                    "team_uid_ref",
                    "grantee",
                    "permissions",
                    "can_edit",
                    "can_share",
                    "expires_at",
                ),
            )
        )
        marker = _folder_marker(live_record_share)
        uid_ref = _folder_uid_ref(payload, marker)
        record_uid_ref = _payload_str(payload, "record_uid_ref")
        grantee_kind, grantee_identifier = _grantee_parts(payload)
        row = _LiveRecordShare(
            index=index,
            raw=live_record_share,
            payload=payload,
            marker=marker,
            keeper_uid=_live_keeper_uid(live_record_share),
            uid_ref=uid_ref,
            record_uid_ref=record_uid_ref,
            grantee_kind=grantee_kind,
            grantee_identifier=grantee_identifier,
        )
        indexed.append(row)
        key = _record_share_key(payload)
        if key not in by_key:
            by_key[key] = row
        if uid_ref and uid_ref not in by_uid_ref:
            by_uid_ref[uid_ref] = row
    return by_key, by_uid_ref, indexed


def _record_share_grantee_label(live: _LiveRecordShare | None, desired: dict[str, Any]) -> str:
    if live is None:
        desired_kind, desired_identifier = _grantee_parts(desired)
        return f"{desired_kind}:{desired_identifier}"
    live_label = f"{live.grantee_kind}:{live.grantee_identifier}"
    desired_kind, desired_identifier = _grantee_parts(desired)
    desired_label = f"{desired_kind}:{desired_identifier}"
    return f"{live_label} -> {desired_label}"


def _compute_record_shares_changes(
    manifest: SharingManifestV1,
    live_record_shares: list[dict[str, Any]],
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_key, _ = _index_manifest_record_shares(manifest)
    live_by_key, live_by_uid_ref, indexed_live = _index_live_record_shares(live_record_shares)

    changes: list[Change] = []
    matched: set[int] = set()

    for key, desired_payload in desired_by_key.items():
        uid_ref = str(desired_payload["uid_ref"])
        live = live_by_key.get(key)
        title = _record_share_title(desired_payload)
        if live is None:
            uid_match = live_by_uid_ref.get(uid_ref)
            if uid_match is not None:
                matched.add(uid_match.index)
                changes.append(
                    Change(
                        kind=ChangeKind.CONFLICT,
                        uid_ref=uid_ref,
                        resource_type=_RECORD_SHARE_RESOURCE,
                        title=title,
                        keeper_uid=uid_match.keeper_uid,
                        before=uid_match.payload,
                        after=_desired_record_share_payload(
                            desired_payload,
                            manifest_name=manifest_name,
                        ),
                        reason=(
                            "record_share grantee changed "
                            f"({_record_share_grantee_label(uid_match, desired_payload)})"
                        ),
                        manifest_name=manifest_name,
                    )
                )
                continue

            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_SHARE_RESOURCE,
                    title=title,
                    after=_desired_record_share_payload(
                        desired_payload,
                        manifest_name=manifest_name,
                    ),
                    manifest_name=manifest_name,
                )
            )
            continue

        matched.add(live.index)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=live.uid_ref,
            manifest_name=manifest_name,
            resource_type=_RECORD_SHARE_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_SHARE_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged record_share",
                    manifest_name=manifest_name,
                )
            )
            continue

        diff_fields = _diff_fields(live.payload, desired_payload, _RECORD_SHARE_DIFF_FIELDS)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_SHARE_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=_change_payload(live.payload, diff_fields),
                    after=_change_payload(desired_payload, diff_fields),
                    manifest_name=manifest_name,
                )
            )

    for live in indexed_live:
        if live.index in matched:
            continue
        orphan_uid_ref = live.uid_ref or live.grantee_identifier
        title = _record_share_title(live.payload)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=orphan_uid_ref,
            manifest_name=manifest_name,
            resource_type=_RECORD_SHARE_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=orphan_uid_ref,
                    resource_type=_RECORD_SHARE_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged record_share",
                    manifest_name=manifest_name,
                )
            )
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=orphan_uid_ref,
                    resource_type=_RECORD_SHARE_RESOURCE,
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
                resource_type=_RECORD_SHARE_RESOURCE,
                title=title,
                keeper_uid=live.keeper_uid,
                before=live.payload,
                reason="managed record_share missing from manifest",
                manifest_name=manifest_name,
            )
        )

    return changes


def _share_folder_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    permissions = payload.get("permissions")
    permissions = permissions if isinstance(permissions, dict) else {}
    for field in ("manage_records", "manage_users", "can_edit", "can_share"):
        if field not in payload and field in permissions:
            payload[field] = permissions[field]

    grantee_kind, grantee_identifier = _grantee_parts(payload)
    if grantee_kind == "user" and grantee_identifier is not None:
        grantee = payload.get("grantee")
        if isinstance(grantee, dict):
            payload["grantee"] = {**grantee, "user_email": grantee_identifier}
        payload["user_email"] = grantee_identifier
    elif grantee_kind == "team" and grantee_identifier is not None:
        payload.setdefault("team_uid_ref", grantee_identifier)
    return payload


def _share_folder_identifier(payload: dict[str, Any]) -> str | None:
    kind = _payload_str(payload, "kind")
    if kind == "grantee":
        _, grantee_identifier = _grantee_parts(payload)
        return grantee_identifier
    if kind == "record":
        return _payload_str(payload, "record_uid_ref")
    if kind == "default":
        return "default"
    return None


def _share_folder_key(payload: dict[str, Any]) -> tuple[str, str, str]:
    shared_folder_uid_ref = _payload_str(payload, "shared_folder_uid_ref")
    if not shared_folder_uid_ref:
        raise ValueError("share_folder missing shared_folder_uid_ref")
    kind = _payload_str(payload, "kind")
    if not kind:
        raise ValueError("share_folder missing kind")
    identifier = _share_folder_identifier(payload)
    if not identifier:
        raise ValueError("share_folder missing grantee_or_record_identifier")
    return (shared_folder_uid_ref, kind, identifier)


def _share_folder_title(payload: dict[str, Any]) -> str:
    shared_folder_uid_ref, kind, identifier = _share_folder_key(payload)
    return f"{shared_folder_uid_ref}:{kind}:{identifier}"


def _desired_share_folder_payload(
    payload: dict[str, Any],
    *,
    manifest_name: str,
) -> dict[str, Any]:
    out = dict(payload)
    out["marker"] = encode_marker(
        uid_ref=str(payload["uid_ref"]),
        manifest=manifest_name,
        resource_type=_SHARE_FOLDER_RESOURCE,
        parent_uid_ref=str(payload["shared_folder_uid_ref"]),
    )
    return out


def _index_manifest_share_folders(
    manifest: SharingManifestV1,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    by_uid_ref: dict[str, dict[str, Any]] = {}
    for share_folder in manifest.share_folders:
        payload = _share_folder_payload(share_folder.model_dump(mode="python", exclude_none=True))
        uid_ref = str(payload["uid_ref"])
        if uid_ref in by_uid_ref:
            raise ValueError(f"duplicate manifest share_folder uid_ref: {uid_ref}")
        key = _share_folder_key(payload)
        if key in by_key:
            raise ValueError(f"duplicate manifest share_folder key: {key}")
        by_uid_ref[uid_ref] = payload
        by_key[key] = payload
    return by_key


def _index_live_share_folders(
    live_share_folders: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], _LiveShareFolder], list[_LiveShareFolder]]:
    by_key: dict[tuple[str, str, str], _LiveShareFolder] = {}
    indexed: list[_LiveShareFolder] = []
    for index, live_share_folder in enumerate(live_share_folders):
        payload = _share_folder_payload(
            _sharing_row_payload(
                live_share_folder,
                (
                    "kind",
                    "uid_ref",
                    "shared_folder_uid_ref",
                    "record_uid_ref",
                    "grantee",
                    "user_email",
                    "team_uid_ref",
                    "target",
                    "permissions",
                    "manage_records",
                    "manage_users",
                    "can_edit",
                    "can_share",
                    "expires_at",
                ),
            )
        )
        marker = _folder_marker(live_share_folder)
        uid_ref = _folder_uid_ref(payload, marker)
        row = _LiveShareFolder(
            index=index,
            raw=live_share_folder,
            payload=payload,
            marker=marker,
            keeper_uid=_live_keeper_uid(live_share_folder),
            uid_ref=uid_ref,
            shared_folder_uid_ref=_payload_str(payload, "shared_folder_uid_ref"),
            kind=_payload_str(payload, "kind"),
            identifier=_share_folder_identifier(payload),
        )
        indexed.append(row)
        key = _share_folder_key(payload)
        if key not in by_key:
            by_key[key] = row
    return by_key, indexed


def _compute_share_folders_changes(
    manifest: SharingManifestV1,
    live_share_folders: list[dict[str, Any]],
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_key = _index_manifest_share_folders(manifest)
    live_by_key, indexed_live = _index_live_share_folders(live_share_folders)

    changes: list[Change] = []
    matched: set[int] = set()

    for key, desired_payload in desired_by_key.items():
        uid_ref = str(desired_payload["uid_ref"])
        live = live_by_key.get(key)
        title = _share_folder_title(desired_payload)
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=uid_ref,
                    resource_type=_SHARE_FOLDER_RESOURCE,
                    title=title,
                    after=_desired_share_folder_payload(
                        desired_payload,
                        manifest_name=manifest_name,
                    ),
                    manifest_name=manifest_name,
                )
            )
            continue

        matched.add(live.index)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=live.uid_ref,
            manifest_name=manifest_name,
            resource_type=_SHARE_FOLDER_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_SHARE_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged share_folder",
                    manifest_name=manifest_name,
                )
            )
            continue

        diff_fields = _diff_fields(live.payload, desired_payload, _SHARE_FOLDER_DIFF_FIELDS)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref,
                    resource_type=_SHARE_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=_change_payload(live.payload, diff_fields),
                    after=_change_payload(desired_payload, diff_fields),
                    manifest_name=manifest_name,
                )
            )

    for live in indexed_live:
        if live.index in matched:
            continue
        orphan_uid_ref = live.uid_ref or live.identifier
        title = _share_folder_title(live.payload)
        if not _managed_by_manifest(
            live.marker,
            uid_ref=orphan_uid_ref,
            manifest_name=manifest_name,
            resource_type=_SHARE_FOLDER_RESOURCE,
        ):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARE_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    reason="unmanaged share_folder",
                    manifest_name=manifest_name,
                )
            )
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=orphan_uid_ref,
                    resource_type=_SHARE_FOLDER_RESOURCE,
                    title=title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                    manifest_name=manifest_name,
                )
            )
            continue
        is_record_member = live.kind == "record"
        changes.append(
            Change(
                kind=ChangeKind.CONFLICT if is_record_member else ChangeKind.SKIP,
                uid_ref=orphan_uid_ref,
                resource_type=_SHARE_FOLDER_RESOURCE,
                title=title,
                keeper_uid=live.keeper_uid,
                before=live.payload,
                reason=(
                    "managed share_folder record member missing from manifest; "
                    "pass --allow-delete to remove"
                    if is_record_member
                    else "managed share_folder missing from manifest"
                ),
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

    Provider sibling blocks are opt-in: each live block is diffed only when the
    corresponding ``live_*`` argument is supplied.
    """

    changes: list[Change] = []
    if live_folders is not None:
        changes.extend(
            _compute_folders_changes(
                manifest,
                live_folders,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    if live_shared_folders is not None:
        changes.extend(
            _compute_shared_folders_changes(
                manifest,
                live_shared_folders,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    if live_share_records is not None:
        changes.extend(
            _compute_record_shares_changes(
                manifest,
                live_share_records,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    if live_share_folders is not None:
        changes.extend(
            _compute_share_folders_changes(
                manifest,
                live_share_folders,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    return changes


__all__ = [
    "_RECORD_SHARE_RESOURCE",
    "_SHARED_FOLDER_RESOURCE",
    "_SHARING_FOLDER_RESOURCE",
    "_SHARE_FOLDER_RESOURCE",
    "_compute_folders_changes",
    "_compute_record_shares_changes",
    "_compute_share_folders_changes",
    "_compute_shared_folders_changes",
    "compute_sharing_diff",
]
