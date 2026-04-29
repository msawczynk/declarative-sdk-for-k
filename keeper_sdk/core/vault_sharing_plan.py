"""Plan builder for ``keeper-vault-sharing.v1`` manifests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from keeper_sdk.core.diff import Change
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.models_vault_sharing import VaultSharingManifestV1
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.core.sharing_diff import compute_sharing_diff

_SHARING_RESOURCE_TYPES = (
    "sharing_folder",
    "sharing_shared_folder",
    "sharing_record_share",
    "sharing_share_folder",
)


def vault_sharing_apply_order(manifest: VaultSharingManifestV1) -> list[str]:
    """Return deterministic create/update order for sharing rows."""

    return [
        *(folder.uid_ref for folder in manifest.folders),
        *(folder.uid_ref for folder in manifest.shared_folders),
        *(share.uid_ref for share in manifest.share_records),
        *(share.uid_ref for share in manifest.share_folders),
    ]


def build_vault_sharing_changes(
    manifest: VaultSharingManifestV1,
    live_records: Iterable[LiveRecord] | None = None,
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> list[Change]:
    """Compute desired-vs-live sharing changes from provider ``LiveRecord`` rows."""

    live_by_type = _live_rows_by_type(live_records or ())
    return compute_sharing_diff(
        manifest,
        live_folders=live_by_type["sharing_folder"],
        manifest_name=manifest_name,
        allow_delete=allow_delete,
        live_shared_folders=live_by_type["sharing_shared_folder"],
        live_share_records=live_by_type["sharing_record_share"],
        live_share_folders=live_by_type["sharing_share_folder"],
    )


def build_vault_sharing_plan(
    manifest: VaultSharingManifestV1,
    live_records: Iterable[LiveRecord] | None = None,
    *,
    manifest_name: str = "vault-sharing",
    allow_delete: bool = False,
) -> Plan:
    """Build a guarded sharing lifecycle plan.

    Missing live membership rows produce creates. Permission drift produces
    updates. Removed managed members produce guarded ``skip`` rows unless
    ``allow_delete=True``.
    """

    return build_plan(
        manifest_name,
        build_vault_sharing_changes(
            manifest,
            live_records,
            manifest_name=manifest_name,
            allow_delete=allow_delete,
        ),
        vault_sharing_apply_order(manifest),
    )


def _live_rows_by_type(live_records: Iterable[LiveRecord]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        resource_type: [] for resource_type in _SHARING_RESOURCE_TYPES
    }
    for record in live_records:
        if record.resource_type not in rows:
            continue
        rows[record.resource_type].append(
            {
                "keeper_uid": record.keeper_uid,
                "resource_type": record.resource_type,
                "title": record.title,
                "payload": dict(record.payload),
                "marker": dict(record.marker) if record.marker else None,
            }
        )
    return rows


__all__ = [
    "build_vault_sharing_changes",
    "build_vault_sharing_plan",
    "vault_sharing_apply_order",
]
