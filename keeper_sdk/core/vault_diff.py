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
does not surface as ``UPDATE``.
"""

from __future__ import annotations

from typing import Any

from keeper_sdk.core.diff import (
    Change,
    ChangeKind,
    _classify_desired,
    _classify_orphans,
    _index_live,
    _raise_live_record_collisions,
)
from keeper_sdk.core.errors import OwnershipError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MANAGER_NAME, MARKER_FIELD_LABEL, MARKER_VERSION, decode_marker
from keeper_sdk.core.vault_models import VaultManifestV1

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
