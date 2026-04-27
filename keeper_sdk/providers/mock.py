"""In-memory provider. Deterministic, zero-I/O, used by tests and dry runs.

State is kept in ``self._records``, keyed by the generated keeper_uid. Each
record carries an ownership marker so later runs see themselves as managed.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import replace
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
    utc_timestamp,
)
from keeper_sdk.core.planner import Plan

_MANAGED_COMPANY_RESOURCE = "managed_company"


class MockProvider(Provider):
    """In-memory provider suitable for tests and offline demos."""

    def __init__(self, manifest_name: str | None = None) -> None:
        self._records: dict[str, LiveRecord] = {}
        self._managed_companies: dict[str, dict[str, Any]] = {}
        self._manifest_name = manifest_name

    # ------------------------------------------------------------------
    # Provider protocol

    def discover(self) -> list[LiveRecord]:
        return list(self._records.values())

    def unsupported_capabilities(self, manifest: object = None) -> list[str]:  # noqa: ARG002
        """Mock fiat: every schema-valid manifest is supported.

        The in-memory provider doesn't actually drive rotation/JIT/etc, it
        just stores payloads — so from the operator's perspective there's
        nothing the mock refuses that the schema allows. Real providers
        override this (see :class:`CommanderCliProvider`).
        """
        return []

    def check_tenant_bindings(self, manifest: object = None) -> list[str]:  # noqa: ARG002
        """In-memory provider has no tenant to bind against — always [].

        Real providers override this with gateway / pam_configuration /
        shared-folder existence checks; see
        :meth:`CommanderCliProvider.check_tenant_bindings`.
        """
        return []

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        outcomes: list[ApplyOutcome] = []
        manifest_name = plan.manifest_name

        for change in plan.ordered():
            if change.kind is ChangeKind.CREATE:
                keeper_uid = _stable_uid(f"{manifest_name}:{change.uid_ref or change.title}")
                marker = encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=manifest_name,
                    resource_type=change.resource_type,
                )
                payload = dict(change.after)
                custom_fields = payload.get("custom_fields") or {}
                custom_fields[MARKER_FIELD_LABEL] = serialize_marker(marker)
                payload["custom_fields"] = custom_fields
                if not dry_run:
                    self._records[keeper_uid] = LiveRecord(
                        keeper_uid=keeper_uid,
                        title=change.title,
                        resource_type=change.resource_type,
                        payload=payload,
                        marker=marker,
                    )
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="create",
                        details={"dry_run": dry_run},
                    )
                )

            elif change.kind is ChangeKind.UPDATE:
                keeper_uid = change.keeper_uid or ""
                existing = self._records.get(keeper_uid)
                if existing is None:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="update",
                            details={"dry_run": dry_run, "skipped": "record_missing"},
                        )
                    )
                    continue
                new_payload = {**existing.payload, **change.after}
                marker = existing.marker or encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=manifest_name,
                    resource_type=change.resource_type,
                )
                marker = {
                    **marker,
                    "manifest": manifest_name,
                    "resource_type": change.resource_type,
                    "last_applied_at": utc_timestamp(),
                }
                existing_cf = new_payload.get("custom_fields") or {}
                existing_cf[MARKER_FIELD_LABEL] = serialize_marker(marker)
                new_payload["custom_fields"] = existing_cf
                if not dry_run:
                    self._records[keeper_uid] = replace(
                        existing,
                        payload=new_payload,
                        marker=marker,
                    )
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"dry_run": dry_run},
                    )
                )

            elif change.kind is ChangeKind.DELETE:
                keeper_uid = change.keeper_uid or ""
                if not dry_run:
                    self._records.pop(keeper_uid, None)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="delete",
                        details={"dry_run": dry_run},
                    )
                )

            elif change.kind is ChangeKind.CONFLICT:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="conflict",
                        details={"reason": change.reason or "blocked"},
                    )
                )

            else:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                    )
                )
        return outcomes

    def discover_managed_companies(self) -> list[dict[str, Any]]:
        """Return raw MSP managed-company rows sorted by case-insensitive name."""
        return sorted(
            (deepcopy(row) for row in self._managed_companies.values()),
            key=lambda row: str(row["name"]).casefold(),
        )

    def seed_managed_companies(self, rows: list[dict[str, Any]]) -> None:
        """Replace mock MSP state, assigning deterministic mock enterprise ids."""
        self._managed_companies = {}
        for row in rows:
            payload = deepcopy(row)
            name = str(payload["name"])
            if payload.get("mc_enterprise_id") is None:
                payload["mc_enterprise_id"] = _stable_mc_id(name)
            self._managed_companies[_mc_key(name)] = payload

    def apply_msp_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Apply an MSP managed-company plan against raw row-dict mock state.

        Slice-1 contract (MSP_FAMILY_DESIGN.md §5.5): MSP rows live in
        ``self._managed_companies`` as raw dicts. **Do not** import or use
        ``MARKER_FIELD_LABEL`` / ``encode_marker`` / ``serialize_marker`` /
        ``LiveRecord`` / ``self._records`` here — those belong to the PAM /
        vault :meth:`apply_plan` path. Marker strategy for managed companies
        is intentionally deferred (memo §10 Q5).
        """
        offenders = sorted(
            str(change.uid_ref or change.title or "<unknown>")
            for change in plan.changes
            if change.resource_type != _MANAGED_COMPANY_RESOURCE
        )
        if offenders:
            joined = ", ".join(offenders)
            raise ValueError(
                "MSP mock apply only accepts managed_company rows; "
                f"offending uid_refs: {joined}; "
                "next_action: build an MSP-only plan or call apply_plan for PAM/vault rows"
            )

        outcomes: list[ApplyOutcome] = []
        for change in _msp_plan_changes(plan):
            name = _msp_change_name(change)
            key = _mc_key(name)

            if change.kind is ChangeKind.CREATE:
                create_mc_id = _stable_mc_id(name)
                payload = deepcopy(change.after)
                payload["mc_enterprise_id"] = create_mc_id
                if not dry_run:
                    self._managed_companies[key] = payload
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=str(create_mc_id),
                        action="create",
                        details={"dry_run": dry_run, "mc_enterprise_id": create_mc_id},
                    )
                )

            elif change.kind is ChangeKind.UPDATE:
                existing = self._managed_companies.get(key)
                if existing is None:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=name,
                            keeper_uid=change.keeper_uid or "",
                            action="update",
                            details={"dry_run": dry_run, "skipped": "record_missing"},
                        )
                    )
                    continue

                update_mc_id = _managed_company_id(existing, name)
                if not dry_run:
                    existing.update(deepcopy(change.after))
                    existing["mc_enterprise_id"] = update_mc_id
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=str(update_mc_id),
                        action="update",
                        details={"dry_run": dry_run, "mc_enterprise_id": update_mc_id},
                    )
                )

            elif change.kind is ChangeKind.DELETE:
                existing = self._managed_companies.get(key)
                if existing is None:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=name,
                            keeper_uid=change.keeper_uid or "",
                            action="delete",
                            details={"dry_run": dry_run, "skipped": "record_missing"},
                        )
                    )
                    continue

                delete_mc_id = _managed_company_id(existing, name)
                if not dry_run:
                    self._managed_companies.pop(key, None)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=str(delete_mc_id),
                        action="delete",
                        details={"dry_run": dry_run, "mc_enterprise_id": delete_mc_id},
                    )
                )

            elif change.kind is ChangeKind.CONFLICT:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=change.keeper_uid or "",
                        action="conflict",
                        details={"reason": change.reason},
                    )
                )

            else:
                details: dict[str, Any] = {"dry_run": dry_run}
                if change.reason is not None:
                    details["reason"] = change.reason
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                        details=details,
                    )
                )
        return outcomes

    # ------------------------------------------------------------------
    # Test helpers

    def seed(self, records: list[LiveRecord]) -> None:
        """Populate the store directly (test convenience)."""
        for record in records:
            self._records[record.keeper_uid] = record

    def seed_payload(
        self,
        *,
        title: str,
        resource_type: str,
        payload: dict[str, Any],
        marker_uid_ref: str | None = None,
        manifest_name: str | None = None,
    ) -> str:
        keeper_uid = _stable_uid(f"{resource_type}:{title}")
        marker = None
        if marker_uid_ref:
            marker = encode_marker(
                uid_ref=marker_uid_ref,
                manifest=manifest_name or self._manifest_name or "unknown",
                resource_type=resource_type,
            )
            custom_fields = payload.get("custom_fields") or {}
            custom_fields[MARKER_FIELD_LABEL] = serialize_marker(marker)
            payload["custom_fields"] = custom_fields
        self._records[keeper_uid] = LiveRecord(
            keeper_uid=keeper_uid,
            title=title,
            resource_type=resource_type,
            payload=payload,
            marker=marker,
        )
        return keeper_uid


def _stable_uid(seed: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"keeper-declarative://{seed}").hex[:22]


def _stable_mc_id(name: str) -> int:
    """Return deterministic MOCK enterprise id, not a real Commander id.

    Slice 1 derives the mock id from name. A rename therefore becomes a
    create+delete pair with a new mock id; live rename semantics are TBD.
    """
    return int(uuid.uuid5(uuid.NAMESPACE_URL, f"managed-company:{name.casefold()}").int) % (10**9)


def _mc_key(name: Any) -> str:
    return str(name).casefold()


def _managed_company_id(row: dict[str, Any], name: str) -> Any:
    value = row.get("mc_enterprise_id")
    return _stable_mc_id(name) if value is None else value


def _msp_change_name(change: Change) -> str:
    for payload in (change.after, change.before):
        value = payload.get("name")
        if value is not None:
            return str(value)
    return str(change.uid_ref or change.title)


def _msp_plan_changes(plan: Plan) -> list[Change]:
    ordered = plan.ordered()
    seen = {id(change) for change in ordered}
    return ordered + [change for change in plan.changes if id(change) not in seen]


__all__ = ["MockProvider"]
