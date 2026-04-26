"""Desired-vs-live diff for ``keeper-vault.v1`` (PR-V3).

Reuses the same matching and classification rules as :func:`compute_diff`
(marker ``uid_ref``, then ``(resource_type, title)``; orphan deletes) via
private helpers in :mod:`keeper_sdk.core.diff`. Desired rows are built from
:class:`~keeper_sdk.core.vault_models.VaultManifestV1` ``records[]`` only
(slice 1 / ``login``).

``MockProvider`` can apply vault plans: it writes the ownership marker into
``payload["custom_fields"]``, which :func:`keeper_sdk.core.diff._field_diff`
ignores, so re-plans stay clean when manifest records omit that key.
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
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.vault_models import VaultManifestV1


def _desired_vault_records(
    manifest: VaultManifestV1,
) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Yield ``(uid_ref, type, title, payload)`` for each manifest record."""
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    for rec in manifest.records:
        payload = rec.model_dump(mode="python", exclude_none=True)
        out.append((rec.uid_ref, rec.type, rec.title, payload))
    return out


def compute_vault_diff(
    manifest: VaultManifestV1,
    live_records: list[LiveRecord],
    *,
    manifest_name: str = "vault",
    allow_delete: bool = False,
    adopt: bool = False,
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
    return changes
