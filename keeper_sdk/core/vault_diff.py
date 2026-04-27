"""Desired-vs-live diff for ``keeper-vault.v1`` (PR-V3).

Reuses the same matching and classification rules as :func:`compute_diff`
(marker ``uid_ref``, then ``(resource_type, title)``; orphan deletes) via
private helpers in :mod:`keeper_sdk.core.diff`. Desired rows are built from
:class:`~keeper_sdk.core.vault_models.VaultManifestV1` ``records[]`` only
(slice 1 / ``login``).

``MockProvider`` can apply vault plans: it writes the ownership marker into
``payload["custom_fields"]``, which :func:`keeper_sdk.core.diff._field_diff`
ignores, so re-plans stay clean when manifest records omit that key.

:func:`compute_vault_diff` uses a **vault login** diff: manifest ``fields[]`` is
compared to Commander-flattened top-level login scalars so benign shape drift
does not surface as ``UPDATE``. When providers pass ``live_record_type_defs``,
it also diffs the sibling ``record_types[]`` block by custom type ``$id``.
When providers pass ``live_attachments``, it diffs the sibling ``attachments[]``
block by ``(record_uid_ref, name)``. When providers pass ``live_keeper_fill``,
it diffs the singular ``keeper_fill`` tenant config block by per-setting
``domain``.
"""

from __future__ import annotations

from pathlib import PurePath
from typing import Any

from keeper_sdk.core.diff import (
    Change,
    ChangeKind,
    _classify_desired,
    _classify_orphans,
    _field_diff,
    _index_live,
    _raise_live_record_collisions,
)
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import (
    MANAGER_NAME,
    MARKER_FIELD_LABEL,
    MARKER_VERSION,
    decode_marker,
    encode_marker,
)
from keeper_sdk.core.vault_models import VaultManifestV1

_RECORD_TYPE_RESOURCE = "record_type"
_RECORD_TYPE_WRAPPER_KEYS = frozenset({"keeper_uid", "title", "resource_type", "payload", "marker"})
_ATTACHMENT_RESOURCE_TYPE = "attachment"
_ATTACHMENT_DIFF_FIELDS = ("content_hash", "size", "mime_type")
_MISSING = object()
_KEEPER_FILL_UID_REF = "keeper_fill:tenant"
_KEEPER_FILL_RESOURCE_TYPE = "keeper_fill"
_KEEPER_FILL_SETTING_RESOURCE_TYPE = "keeper_fill_setting"


def _desired_vault_records(
    manifest: VaultManifestV1,
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Yield ``(uid_ref, type, title, payload)`` for each manifest record."""
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    for rec in manifest.records:
        payload = rec.model_dump(mode="python", exclude_none=True)
        out.append((rec.uid_ref, rec.type, rec.title, payload))
    return out


def _record_type_payload(record_type_def: dict[str, Any]) -> dict[str, Any]:
    """Return provider-normalised payload from a raw or LiveRecord-like dict."""
    payload = record_type_def.get("payload")
    if isinstance(payload, dict):
        return dict(payload)
    return {k: v for k, v in record_type_def.items() if k not in _RECORD_TYPE_WRAPPER_KEYS}


def _record_type_marker(record_type_def: dict[str, Any]) -> dict[str, Any] | None:
    marker = record_type_def.get("marker")
    return marker if isinstance(marker, dict) else None


def _record_type_key(record_type_def: dict[str, Any]) -> str:
    payload = _record_type_payload(record_type_def)
    content = payload.get("content")
    content = content if isinstance(content, dict) else {}
    for candidate in (
        payload.get("$id"),
        content.get("$id"),
        payload.get("name"),
        content.get("name"),
    ):
        if candidate:
            return str(candidate)
    raise ValueError("record type definition missing '$id' or 'name'")


def _record_type_change_payload(
    payload: dict[str, Any],
    *,
    uid_ref: str | None,
    manifest_name: str,
) -> dict[str, Any]:
    out = dict(payload)
    if uid_ref:
        out["marker"] = encode_marker(
            uid_ref=uid_ref,
            manifest=manifest_name,
            resource_type=_RECORD_TYPE_RESOURCE,
        )
    return out


def _record_type_live_uid(live: dict[str, Any]) -> str | None:
    for key in ("keeper_uid", "record_type_id", "id", "uid"):
        value = live.get(key)
        if value is not None:
            return str(value)
    return None


def _record_type_title(record_type_def: dict[str, Any]) -> str:
    return _record_type_key(record_type_def)


def _index_record_types(
    record_type_defs: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record_type_def in record_type_defs:
        key = _record_type_key(record_type_def)
        if key in indexed:
            raise ValueError(f"duplicate {source} record type key: {key}")
        indexed[key] = record_type_def
    return indexed


def _compute_record_types_changes(
    manifest: VaultManifestV1,
    live_record_type_defs: list[dict[str, Any]],
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_key = _index_record_types(manifest.record_types, source="manifest")
    live_by_key = _index_record_types(live_record_type_defs, source="live")

    changes: list[Change] = []
    matched: set[str] = set()

    for key, desired in desired_by_key.items():
        desired_payload = _record_type_payload(desired)
        uid_ref = desired_payload.get("uid_ref")
        uid_ref = str(uid_ref) if uid_ref else key
        title = _record_type_title(desired)
        live = live_by_key.get(key)
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    after=_record_type_change_payload(
                        desired_payload,
                        uid_ref=uid_ref,
                        manifest_name=manifest_name,
                    ),
                )
            )
            continue

        marker = _record_type_marker(live) or {}
        keeper_uid = _record_type_live_uid(live)
        matched.add(key)
        if marker.get("manager") != MANAGER_NAME:
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    keeper_uid=keeper_uid,
                    before=_record_type_payload(live),
                    reason="unmanaged record type",
                )
            )
            continue

        live_payload = _record_type_payload(live)
        diff_fields = _field_diff(live_payload, desired_payload)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    keeper_uid=keeper_uid,
                    before={k: live_payload.get(k) for k in diff_fields},
                    after=_record_type_change_payload(
                        {k: desired_payload.get(k) for k in diff_fields},
                        uid_ref=uid_ref,
                        manifest_name=manifest_name,
                    ),
                )
            )

    for key, live in live_by_key.items():
        if key in matched or key in desired_by_key:
            continue
        marker = _record_type_marker(live) or {}
        uid_ref = marker.get("uid_ref") or _record_type_payload(live).get("uid_ref") or key
        uid_ref = str(uid_ref)
        keeper_uid = _record_type_live_uid(live)
        title = _record_type_title(live)
        before = _record_type_payload(live)
        if marker.get("manager") != MANAGER_NAME:
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    keeper_uid=keeper_uid,
                    before=before,
                    reason="unmanaged record type",
                )
            )
            continue
        if marker.get("manifest") and manifest_name and marker.get("manifest") != manifest_name:
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    keeper_uid=keeper_uid,
                    before=before,
                )
            )
        else:
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=uid_ref,
                    resource_type=_RECORD_TYPE_RESOURCE,
                    title=title,
                    keeper_uid=keeper_uid,
                    before=before,
                    reason="managed record type missing from manifest; pass --allow-delete to remove",
                )
            )
    return changes


def _attachment_name(payload: dict[str, Any]) -> str:
    name = payload.get("name")
    if name:
        return str(name)
    source_path = payload.get("source_path")
    if source_path:
        return PurePath(str(source_path)).name
    raise ValueError("attachment missing name")


def _attachment_key(payload: dict[str, Any]) -> tuple[str, str]:
    record_uid_ref = payload.get("record_uid_ref")
    if not record_uid_ref:
        raise ValueError("attachment missing record_uid_ref")
    return (str(record_uid_ref), _attachment_name(payload))


def _attachment_marker(payload: dict[str, Any]) -> dict[str, Any] | None:
    marker = payload.get("marker")
    return marker if isinstance(marker, dict) else None


def _attachment_payload(row: dict[str, Any]) -> dict[str, Any]:
    nested = row.get("payload")
    if isinstance(nested, dict):
        payload = dict(nested)
        for key in (
            "uid_ref",
            "record_uid_ref",
            "name",
            "title",
            "size",
            "mime_type",
            "content_hash",
            "content_sha256",
        ):
            if key in row and key not in payload:
                payload[key] = row[key]
        return payload
    payload = dict(row)
    payload.pop("marker", None)
    payload.pop("payload", None)
    return payload


def _attachment_uid_ref(
    payload: dict[str, Any],
    marker: dict[str, Any] | None = None,
) -> str | None:
    uid_ref = payload.get("uid_ref") or (marker or {}).get("uid_ref")
    return str(uid_ref) if uid_ref else None


def _attachment_keeper_uid(live: dict[str, Any]) -> str | None:
    keeper_uid = live.get("keeper_uid") or live.get("file_uid") or live.get("attachment_uid")
    return str(keeper_uid) if keeper_uid else None


def _attachment_title(payload: dict[str, Any]) -> str:
    title = payload.get("title") or payload.get("name")
    return str(title) if title else _attachment_name(payload)


def _attachment_field(payload: dict[str, Any], field: str) -> Any:
    if field == "content_hash":
        if "content_hash" in payload:
            return payload["content_hash"]
        if "content_sha256" in payload:
            return payload["content_sha256"]
        return _MISSING
    if field in payload:
        return payload[field]
    return _MISSING


def _attachment_diff_fields(live: dict[str, Any], desired: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for field in _ATTACHMENT_DIFF_FIELDS:
        desired_value = _attachment_field(desired, field)
        if desired_value is _MISSING:
            continue
        live_value = _attachment_field(live, field)
        if live_value is _MISSING:
            live_value = None
        if live_value != desired_value:
            changed.append(field)
    return changed


def _attachment_diff_payload(payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in fields:
        value = _attachment_field(payload, field)
        out[field] = None if value is _MISSING else value
    return out


def _attachment_change_payload(payload: dict[str, Any], manifest_name: str) -> dict[str, Any]:
    out = dict(payload)
    out["manifest_name"] = manifest_name
    return out


def _attachment_desired_marker(payload: dict[str, Any], manifest_name: str) -> dict[str, Any]:
    return {
        "manager": MANAGER_NAME,
        "version": MARKER_VERSION,
        "uid_ref": _attachment_uid_ref(payload),
        "manifest": manifest_name,
        "resource_type": _ATTACHMENT_RESOURCE_TYPE,
        "parent_uid_ref": payload.get("record_uid_ref"),
    }


def _attachment_is_managed(marker: dict[str, Any] | None) -> bool:
    return bool(marker and marker.get("manager") == MANAGER_NAME)


def _attachment_manifest_matches(marker: dict[str, Any] | None, manifest_name: str) -> bool:
    marker_manifest = (marker or {}).get("manifest")
    return not marker_manifest or marker_manifest == manifest_name


def _compute_attachment_changes(
    manifest: VaultManifestV1,
    live_attachments: list[dict[str, Any]],
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
) -> list[Change]:
    desired_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in manifest.attachments:
        payload = dict(raw)
        key = _attachment_key(payload)
        if key in desired_by_key:
            record_uid_ref, name = key
            raise ValueError(
                f"duplicate attachment for record_uid_ref={record_uid_ref!r}, name={name!r}"
            )
        payload["name"] = key[1]
        payload["marker"] = _attachment_desired_marker(payload, manifest_name)
        desired_by_key[key] = payload

    live_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    live_payload_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for live_row in live_attachments:
        payload = _attachment_payload(live_row)
        key = _attachment_key(payload)
        payload["name"] = key[1]
        live_by_key[key] = live_row
        live_payload_by_key[key] = payload

    changes: list[Change] = []
    matched: set[tuple[str, str]] = set()

    for key, desired in desired_by_key.items():
        matched_live = live_by_key.get(key)
        if matched_live is None:
            changes.append(
                Change(
                    kind=ChangeKind.ADD,
                    uid_ref=_attachment_uid_ref(desired),
                    resource_type=_ATTACHMENT_RESOURCE_TYPE,
                    title=_attachment_title(desired),
                    after=_attachment_change_payload(desired, manifest_name),
                )
            )
            continue

        matched.add(key)
        marker = _attachment_marker(matched_live)
        live_payload = live_payload_by_key[key]
        if not _attachment_is_managed(marker):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=_attachment_uid_ref(desired),
                    resource_type=_ATTACHMENT_RESOURCE_TYPE,
                    title=_attachment_title(desired),
                    keeper_uid=_attachment_keeper_uid(matched_live),
                    before=_attachment_change_payload(live_payload, manifest_name),
                    reason="unmanaged attachment",
                )
            )
            continue

        diff_fields = _attachment_diff_fields(live_payload, desired)
        if diff_fields:
            before = _attachment_diff_payload(live_payload, diff_fields)
            after = _attachment_diff_payload(desired, diff_fields)
            before["manifest_name"] = manifest_name
            after["manifest_name"] = manifest_name
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=_attachment_uid_ref(desired),
                    resource_type=_ATTACHMENT_RESOURCE_TYPE,
                    title=_attachment_title(desired),
                    keeper_uid=_attachment_keeper_uid(matched_live),
                    before=before,
                    after=after,
                )
            )
            continue

        changes.append(
            Change(
                kind=ChangeKind.NOOP,
                uid_ref=_attachment_uid_ref(desired),
                resource_type=_ATTACHMENT_RESOURCE_TYPE,
                title=_attachment_title(desired),
                keeper_uid=_attachment_keeper_uid(matched_live),
            )
        )

    for key, live in live_by_key.items():
        if key in matched:
            continue
        marker = _attachment_marker(live)
        live_payload = live_payload_by_key[key]
        if not _attachment_is_managed(marker):
            changes.append(
                Change(
                    kind=ChangeKind.SKIP,
                    uid_ref=_attachment_uid_ref(live_payload, marker),
                    resource_type=_ATTACHMENT_RESOURCE_TYPE,
                    title=_attachment_title(live_payload),
                    keeper_uid=_attachment_keeper_uid(live),
                    before=_attachment_change_payload(live_payload, manifest_name),
                    reason="unmanaged attachment",
                )
            )
            continue
        if not _attachment_manifest_matches(marker, manifest_name):
            continue
        if allow_delete:
            changes.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=_attachment_uid_ref(live_payload, marker),
                    resource_type=_ATTACHMENT_RESOURCE_TYPE,
                    title=_attachment_title(live_payload),
                    keeper_uid=_attachment_keeper_uid(live),
                    before=_attachment_change_payload(live_payload, manifest_name),
                )
            )

    return changes


def _defined_keeper_fill(block: dict[str, Any] | None) -> bool:
    return isinstance(block, dict) and bool(block)


def _marker_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return decode_marker(value)
    return None


def _keeper_fill_marker(live_keeper_fill: dict[str, Any]) -> dict[str, Any] | None:
    marker = _marker_value(live_keeper_fill.get("marker"))
    if marker:
        return marker

    custom = live_keeper_fill.get("custom")
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


def _keeper_fill_keeper_uid(live_keeper_fill: dict[str, Any]) -> str | None:
    value = live_keeper_fill.get("keeper_uid") or live_keeper_fill.get("uid")
    return str(value) if value else None


def _keeper_fill_change(
    *,
    kind: ChangeKind,
    title: str,
    uid_ref: str,
    manifest_name: str,
    keeper_uid: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    resource_type: str = _KEEPER_FILL_RESOURCE_TYPE,
) -> Change:
    return Change(
        kind=kind,
        uid_ref=uid_ref,
        resource_type=resource_type,
        title=title,
        keeper_uid=keeper_uid,
        before=before or {},
        after=after or {},
        reason=reason,
        manifest_name=manifest_name,
    )


def _keeper_fill_setting_key(setting: dict[str, Any]) -> str:
    for field in ("domain", "record_uid_ref"):
        value = setting.get(field)
        if value is not None:
            return str(value)
    return ""


def _keeper_fill_setting_uid_ref(key: str) -> str:
    return f"{_KEEPER_FILL_UID_REF}:{key}"


def _index_keeper_fill_settings(
    settings: Any,
    *,
    side: str,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(settings, list):
        return out
    for setting in settings:
        if not isinstance(setting, dict):
            continue
        key = _keeper_fill_setting_key(setting)
        if key in out:
            raise ValueError(f"duplicate keeper_fill setting key in {side}: {key!r}")
        out[key] = setting
    return out


def _keeper_fill_setting_diff(
    live_setting: dict[str, Any],
    desired_setting: dict[str, Any],
) -> list[str]:
    changed: list[str] = []
    for key in sorted(set(live_setting) | set(desired_setting)):
        if key in ("domain", "record_uid_ref"):
            continue
        if key not in desired_setting:
            continue
        if live_setting.get(key) != desired_setting.get(key):
            changed.append(key)
    return changed


def _compute_keeper_fill_changes(
    manifest: VaultManifestV1,
    live_keeper_fill: dict[str, Any] | None,
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
) -> list[Change]:
    """Diff the singular tenant KeeperFill sibling block."""
    desired = manifest.keeper_fill
    desired_defined = _defined_keeper_fill(desired)
    live_defined = _defined_keeper_fill(live_keeper_fill)
    live_block = live_keeper_fill or {}

    if not desired_defined and not live_defined:
        return []

    if desired_defined and not live_defined:
        assert desired is not None
        return [
            _keeper_fill_change(
                kind=ChangeKind.CREATE,
                uid_ref=_KEEPER_FILL_UID_REF,
                title="tenant",
                after=desired,
                manifest_name=manifest_name,
            )
        ]

    marker = _keeper_fill_marker(live_block)
    if marker is None:
        return [
            _keeper_fill_change(
                kind=ChangeKind.SKIP,
                uid_ref=_KEEPER_FILL_UID_REF,
                title="tenant",
                keeper_uid=_keeper_fill_keeper_uid(live_block),
                before=live_block,
                reason="unmanaged keeper_fill",
                manifest_name=manifest_name,
            )
        ]

    manager = marker.get("manager")
    if manager and manager != MANAGER_NAME:
        return [
            _keeper_fill_change(
                kind=ChangeKind.CONFLICT,
                uid_ref=_KEEPER_FILL_UID_REF,
                title="tenant",
                keeper_uid=_keeper_fill_keeper_uid(live_block),
                reason=f"keeper_fill managed by '{manager}', refusing to touch",
                manifest_name=manifest_name,
            )
        ]
    if marker.get("version") not in (None, MARKER_VERSION):
        raise OwnershipError(
            reason=f"marker version {marker.get('version')} not supported by core v{MARKER_VERSION}",
            uid_ref=_KEEPER_FILL_UID_REF,
            resource_type=_KEEPER_FILL_RESOURCE_TYPE,
            live_identifier=_keeper_fill_keeper_uid(live_block),
            next_action="upgrade the declarative core or rewrite the marker",
        )

    if not desired_defined:
        if allow_delete:
            return [
                _keeper_fill_change(
                    kind=ChangeKind.DELETE,
                    uid_ref=_KEEPER_FILL_UID_REF,
                    title="tenant",
                    keeper_uid=_keeper_fill_keeper_uid(live_block),
                    before=live_block,
                    manifest_name=manifest_name,
                )
            ]
        return [
            _keeper_fill_change(
                kind=ChangeKind.CONFLICT,
                uid_ref=_KEEPER_FILL_UID_REF,
                title="tenant",
                keeper_uid=_keeper_fill_keeper_uid(live_block),
                before=live_block,
                reason="managed keeper_fill missing from manifest; pass --allow-delete to remove",
                manifest_name=manifest_name,
            )
        ]

    assert desired is not None
    desired_settings = _index_keeper_fill_settings(desired.get("settings"), side="manifest")
    live_settings = _index_keeper_fill_settings(live_block.get("settings"), side="live")

    changes: list[Change] = []
    for key in sorted(desired_settings):
        desired_setting = desired_settings[key]
        live_setting = live_settings.get(key)
        if live_setting is None:
            changes.append(
                _keeper_fill_change(
                    kind=ChangeKind.CREATE,
                    uid_ref=_keeper_fill_setting_uid_ref(key),
                    title=key,
                    after=desired_setting,
                    manifest_name=manifest_name,
                    resource_type=_KEEPER_FILL_SETTING_RESOURCE_TYPE,
                )
            )
            continue
        diff_fields = _keeper_fill_setting_diff(live_setting, desired_setting)
        if diff_fields:
            changes.append(
                _keeper_fill_change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=_keeper_fill_setting_uid_ref(key),
                    title=key,
                    before={field: live_setting.get(field) for field in diff_fields},
                    after={field: desired_setting.get(field) for field in diff_fields},
                    manifest_name=manifest_name,
                    resource_type=_KEEPER_FILL_SETTING_RESOURCE_TYPE,
                )
            )

    for key in sorted(set(live_settings) - set(desired_settings)):
        live_setting = live_settings[key]
        if allow_delete:
            changes.append(
                _keeper_fill_change(
                    kind=ChangeKind.DELETE,
                    uid_ref=_keeper_fill_setting_uid_ref(key),
                    title=key,
                    before=live_setting,
                    manifest_name=manifest_name,
                    resource_type=_KEEPER_FILL_SETTING_RESOURCE_TYPE,
                )
            )
        else:
            changes.append(
                _keeper_fill_change(
                    kind=ChangeKind.CONFLICT,
                    uid_ref=_keeper_fill_setting_uid_ref(key),
                    title=key,
                    before=live_setting,
                    reason=(
                        "managed keeper_fill setting missing from manifest; "
                        "pass --allow-delete to remove"
                    ),
                    manifest_name=manifest_name,
                    resource_type=_KEEPER_FILL_SETTING_RESOURCE_TYPE,
                )
            )
    return changes


def compute_vault_diff(
    manifest: VaultManifestV1,
    live_records: list[LiveRecord],
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
    adopt: bool = False,
    live_record_type_defs: list[dict[str, Any]] | None = None,
    live_attachments: list[dict[str, Any]] | None = None,
    live_keeper_fill: dict[str, Any] | None = None,
) -> list[Change]:
    """Classify vault manifest records vs provider ``LiveRecord`` rows.

    Same semantics as :func:`keeper_sdk.core.diff.compute_diff` for the
    overlapping concerns (foreign marker, adoption, orphans).
    """
    _raise_live_record_collisions(live_records)
    by_uid_ref, by_title = _index_live(live_records)

    changes: list[Change] = []
    matched: set[str] = set()

    for uid_ref, resource_type, title, payload in _desired_vault_records(manifest):
        live = by_uid_ref.get(uid_ref) or by_title.get((resource_type, title))
        change = _classify_desired(
            uid_ref=uid_ref,
            resource_type=resource_type,
            title=title,
            payload=payload,
            live=live,
            by_title=by_title,
            adopt=adopt,
            vault_login_diff=True,
        )
        changes.append(change)
        if change.kind in (ChangeKind.UPDATE, ChangeKind.NOOP) and live is not None:
            matched.add(live.keeper_uid)

    changes.extend(
        _classify_orphans(
            live_records,
            matched=matched,
            manifest_name=manifest_name,
            allow_delete=allow_delete,
        )
    )
    if live_record_type_defs is not None:
        changes.extend(
            _compute_record_types_changes(
                manifest,
                live_record_type_defs,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    if live_attachments is not None:
        changes.extend(
            _compute_attachment_changes(
                manifest,
                live_attachments,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    if manifest.keeper_fill is not None or live_keeper_fill is not None:
        changes.extend(
            _compute_keeper_fill_changes(
                manifest,
                live_keeper_fill,
                manifest_name=manifest_name,
                allow_delete=allow_delete,
            )
        )
    return changes
