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
block by ``(record_uid_ref, name)``.
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
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MANAGER_NAME, MARKER_VERSION, encode_marker
from keeper_sdk.core.vault_models import VaultManifestV1

_RECORD_TYPE_RESOURCE = "record_type"
_RECORD_TYPE_WRAPPER_KEYS = frozenset({"keeper_uid", "title", "resource_type", "payload", "marker"})
_ATTACHMENT_RESOURCE_TYPE = "attachment"
_ATTACHMENT_DIFF_FIELDS = ("content_hash", "size", "mime_type")
_MISSING = object()


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


def compute_vault_diff(
    manifest: VaultManifestV1,
    live_records: list[LiveRecord],
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
    adopt: bool = False,
    live_record_type_defs: list[dict[str, Any]] | None = None,
    live_attachments: list[dict[str, Any]] | None = None,
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
    return changes
