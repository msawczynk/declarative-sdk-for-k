"""Desired-vs-live diff for ``msp-environment.v1`` managed companies.

Slice 1 compares the manifest's ``managed_companies[]`` against raw live
managed-company rows. Identity is the managed-company ``name`` using
case-insensitive matching, because Commander name/id lookup is case-insensitive.

Seat normalisation uses ``1_000_000_000`` as the canonical unlimited sentinel:
live Commander data may expose unlimited seats as ``-1`` or as a very large
integer, so both ``-1`` and any value ``>= 1_000_000_000`` map to that canonical
integer before equality checks.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.msp_models import MspManifestV1

_MANAGED_COMPANY_RESOURCE = "managed_company"
_UNLIMITED_SEATS = 1_000_000_000
_DELETE_SKIP_REASON = "unmanaged managed_company; pass allow_delete=True to remove"
_DIFF_FIELDS = ("plan", "seats", "file_plan", "addons")
_KIND_ORDER = {
    ChangeKind.CREATE: 0,
    ChangeKind.UPDATE: 1,
    ChangeKind.NOOP: 2,
    ChangeKind.DELETE: 3,
    ChangeKind.SKIP: 3,
    ChangeKind.CONFLICT: 4,
}

__all__ = ["compute_msp_diff"]


def compute_msp_diff(
    manifest: MspManifestV1,
    live_mcs: list[dict[str, Any]],
    *,
    allow_delete: bool = False,
    adopt: bool = False,
) -> list[Change]:
    """Classify desired managed-company state against raw live MSP rows."""
    desired_by_key = _desired_managed_companies(manifest)
    live_by_key, duplicate_live = _index_live_managed_companies(live_mcs)
    manifest_manager = _manifest_manager(manifest)

    changes: list[Change] = []

    for key, desired in desired_by_key.items():
        if key in duplicate_live:
            continue

        live = live_by_key.get(key)
        if live is None:
            changes.append(
                Change(
                    kind=ChangeKind.CREATE,
                    uid_ref=desired["name"],
                    resource_type=_MANAGED_COMPANY_RESOURCE,
                    title=desired["name"],
                    before={},
                    after=desired,
                )
            )
            continue

        live_manager = _live_manager(live)
        if live_manager is not None:
            if live_manager != manifest_manager:
                changes.append(
                    Change(
                        kind=ChangeKind.CONFLICT,
                        uid_ref=desired["name"],
                        resource_type=_MANAGED_COMPANY_RESOURCE,
                        title=desired["name"],
                        keeper_uid=_live_keeper_uid(live),
                        before=live,
                        after=desired,
                        reason=(
                            "managed by other manager "
                            f"{live_manager!r}; expected {manifest_manager!r}"
                        ),
                    )
                )
                continue
            if adopt:
                changes.append(
                    Change(
                        kind=ChangeKind.NOOP,
                        uid_ref=desired["name"],
                        resource_type=_MANAGED_COMPANY_RESOURCE,
                        title=desired["name"],
                        keeper_uid=_live_keeper_uid(live),
                        before=live,
                        after=desired,
                        reason="already managed by manifest manager",
                    )
                )
                continue

        if adopt:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=desired["name"],
                    resource_type=_MANAGED_COMPANY_RESOURCE,
                    title=desired["name"],
                    keeper_uid=_live_keeper_uid(live),
                    before=live,
                    after=_adoption_after(desired, manifest_manager),
                    reason="adoption: write ownership marker",
                )
            )
            continue

        diff_fields = _diff_fields(live, desired)
        if diff_fields:
            changes.append(
                Change(
                    kind=ChangeKind.UPDATE,
                    uid_ref=desired["name"],
                    resource_type=_MANAGED_COMPANY_RESOURCE,
                    title=desired["name"],
                    keeper_uid=_live_keeper_uid(live),
                    before=live,
                    after=desired,
                )
            )
            continue

        changes.append(
            Change(
                kind=ChangeKind.NOOP,
                uid_ref=desired["name"],
                resource_type=_MANAGED_COMPANY_RESOURCE,
                title=desired["name"],
                keeper_uid=_live_keeper_uid(live),
                before=live,
                after=desired,
                reason="no drift",
            )
        )

    for key, live in live_by_key.items():
        if key in desired_by_key or key in duplicate_live:
            continue
        kind = ChangeKind.DELETE if allow_delete else ChangeKind.SKIP
        changes.append(
            Change(
                kind=kind,
                uid_ref=live["name"],
                resource_type=_MANAGED_COMPANY_RESOURCE,
                title=live["name"],
                keeper_uid=_live_keeper_uid(live),
                before=live,
                reason=None if allow_delete else _DELETE_SKIP_REASON,
            )
        )

    for key, rows in duplicate_live.items():
        name = _duplicate_display_name(rows)
        changes.append(
            Change(
                kind=ChangeKind.CONFLICT,
                uid_ref=name,
                resource_type=_MANAGED_COMPANY_RESOURCE,
                title=name,
                before={"names": [str(row.get("name", "")) for row in rows]},
                reason=f"duplicate live managed_company name: {name}",
            )
        )

    return sorted(changes, key=_change_sort_key)


def _desired_managed_companies(manifest: MspManifestV1) -> dict[str, dict[str, Any]]:
    data = manifest.model_dump(mode="python", exclude_none=True)
    desired: dict[str, dict[str, Any]] = {}
    for row in data.get("managed_companies") or []:
        normalised = _normalise_managed_company(row)
        desired[_name_key(normalised["name"])] = normalised
    return desired


def _index_live_managed_companies(
    live_mcs: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in live_mcs:
        grouped[_name_key(row["name"])].append(row)

    live_by_key: dict[str, dict[str, Any]] = {}
    duplicate_live: dict[str, list[dict[str, Any]]] = {}
    for key, rows in grouped.items():
        if len(rows) > 1:
            duplicate_live[key] = rows
        else:
            live_by_key[key] = _normalise_managed_company(rows[0], include_live_id=True)
    return live_by_key, duplicate_live


def _normalise_managed_company(
    row: dict[str, Any],
    *,
    include_live_id: bool = False,
) -> dict[str, Any]:
    # TODO(P5): memo §10 Q7 — map Commander MSP_PLANS display/product ids.
    out: dict[str, Any] = {
        "name": str(row["name"]),
        "plan": str(row["plan"]).strip(),
        "seats": _canonical_seats(row["seats"]),
        "file_plan": _normalise_file_plan(row.get("file_plan")),
        "addons": _normalise_addons(row.get("addons")),
    }
    if include_live_id and row.get("mc_enterprise_id") is not None:
        out["mc_enterprise_id"] = row["mc_enterprise_id"]
    if include_live_id and _live_manager(row) is not None:
        out["manager"] = _live_manager(row)
    return out


def _canonical_seats(value: Any) -> int:
    seats = int(value)
    if seats == -1 or seats >= _UNLIMITED_SEATS:
        return _UNLIMITED_SEATS
    return seats


def _normalise_file_plan(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _normalise_addons(value: Any) -> list[dict[str, Any]]:
    addons = value if isinstance(value, list) else []
    normalised = [
        {
            "name": str(addon["name"]),
            "seats": _canonical_seats(addon["seats"]),
        }
        for addon in addons
    ]
    return sorted(normalised, key=lambda addon: addon["name"].casefold())


def _diff_fields(live: dict[str, Any], desired: dict[str, Any]) -> list[str]:
    return [field for field in _DIFF_FIELDS if live.get(field) != desired.get(field)]


def _name_key(name: Any) -> str:
    return str(name).casefold()


def _manifest_manager(manifest: MspManifestV1) -> str:
    manager = manifest.manager.strip() if isinstance(manifest.manager, str) else ""
    return manager or manifest.name


def _live_manager(row: dict[str, Any]) -> str | None:
    value = row.get("manager")
    if value is None:
        return None
    manager = str(value).strip()
    return manager or None


def _adoption_after(desired: dict[str, Any], manager: str) -> dict[str, Any]:
    out = dict(desired)
    out["manager"] = manager
    return out


def _live_keeper_uid(live: dict[str, Any]) -> str | None:
    value = live.get("mc_enterprise_id")
    return str(value) if value is not None else None


def _duplicate_display_name(rows: list[dict[str, Any]]) -> str:
    names = sorted((str(row.get("name", "")) for row in rows), key=lambda value: value.casefold())
    return names[0]


def _change_sort_key(change: Change) -> tuple[int, str]:
    return (_KIND_ORDER[change.kind], change.title.casefold())
