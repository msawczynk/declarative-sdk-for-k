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
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
    utc_timestamp,
)
from keeper_sdk.core.planner import Plan

_MANAGED_COMPANY_RESOURCE = "managed_company"
_ENTERPRISE_BLOCKS = ("nodes", "users", "roles", "teams", "enforcements", "aliases")
_ENTERPRISE_BLOCK_BY_RESOURCE = {
    "enterprise_node": "nodes",
    "enterprise_user": "users",
    "enterprise_role": "roles",
    "enterprise_team": "teams",
    "enterprise_enforcement": "enforcements",
    "enterprise_alias": "aliases",
}
_ENTERPRISE_RESOURCE_BY_BLOCK = {
    block: resource for resource, block in _ENTERPRISE_BLOCK_BY_RESOURCE.items()
}
_KSM_BLOCKS = ("apps", "tokens", "record_shares", "config_outputs")
_KSM_BLOCK_BY_RESOURCE = {
    "ksm_app": "apps",
    "ksm_token": "tokens",
    "ksm_record_share": "record_shares",
    "ksm_config_output": "config_outputs",
}
_KSM_RESOURCE_BY_BLOCK = {block: resource for resource, block in _KSM_BLOCK_BY_RESOURCE.items()}
_VAULT_SHARING_RESOURCE_TYPES = {
    "sharing_folder",
    "sharing_shared_folder",
    "sharing_record_share",
    "sharing_share_folder",
}
_SHARING_PERMISSION_FIELDS = (
    "manage_records",
    "manage_users",
    "can_edit",
    "can_share",
    "read_only",
)


class MockProvider(Provider):
    """In-memory provider suitable for tests and offline demos."""

    def __init__(self, manifest_name: str | None = None) -> None:
        self._records: dict[str, LiveRecord] = {}
        self._managed_companies: dict[str, dict[str, Any]] = {}
        self._enterprise_state: dict[str, dict[str, dict[str, Any]]] = {
            block: {} for block in _ENTERPRISE_BLOCKS
        }
        self._enterprise_markers: dict[str, dict[str, Any]] = {}
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

        if not dry_run:
            _guard_vault_sharing_deletes(plan)

        for change in plan.ordered():
            if change.kind is ChangeKind.CREATE:
                keeper_uid = _stable_uid(f"{manifest_name}:{change.uid_ref or change.title}")
                marker = encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=manifest_name,
                    resource_type=change.resource_type,
                )
                payload = _normalise_mock_payload(change.resource_type, dict(change.after))
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
                new_payload = _normalise_mock_payload(
                    change.resource_type,
                    {**existing.payload, **change.after},
                )
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

    def discover_enterprise(self) -> dict[str, list[dict[str, Any]]]:
        """Return raw keeper-enterprise.v1 mock rows sorted by uid_ref."""
        return {
            block: sorted(
                (deepcopy(row) for row in self._enterprise_state[block].values()),
                key=lambda row: str(row.get("uid_ref") or ""),
            )
            for block in _ENTERPRISE_BLOCKS
        }

    def seed_enterprise_state(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        """Replace mock enterprise state, assigning deterministic mock ids."""
        self._enterprise_state = {block: {} for block in _ENTERPRISE_BLOCKS}
        self._enterprise_markers = {}
        manifest_name = self._manifest_name or "keeper-enterprise"
        for block in _ENTERPRISE_BLOCKS:
            for row in rows.get(block) or []:
                payload = deepcopy(row)
                keeper_uid = str(
                    payload.get("keeper_uid")
                    or _stable_uid(
                        f"enterprise:{manifest_name}:{_ENTERPRISE_RESOURCE_BY_BLOCK[block]}:"
                        f"{_enterprise_uid_ref_for_payload(payload)}"
                    )
                )
                payload["keeper_uid"] = keeper_uid
                marker = _enterprise_marker_from_payload(
                    payload,
                    block=block,
                    manifest_name=manifest_name,
                )
                if marker is not None:
                    payload["marker"] = marker
                    if marker.get("manager") is not None:
                        payload["manager"] = marker["manager"]
                    self._enterprise_markers[keeper_uid] = marker
                self._enterprise_state[block][_enterprise_key_for_payload(payload)] = payload

    def adopt_enterprise_plan(
        self,
        plan: Plan,
        *,
        dry_run: bool = False,
    ) -> list[ApplyOutcome]:
        """Write ownership markers for keeper-enterprise.v1 import rows."""
        offenders = sorted(
            str(change.uid_ref or change.title or "<unknown>")
            for change in plan.changes
            if change.resource_type not in _ENTERPRISE_BLOCK_BY_RESOURCE
        )
        if offenders:
            joined = ", ".join(offenders)
            raise ValueError(
                "enterprise mock adoption only accepts enterprise rows; "
                f"offending uid_refs: {joined}; "
                "next_action: build an enterprise-only adoption plan"
            )

        outcomes: list[ApplyOutcome] = []
        for change in _all_plan_changes(plan):
            if change.kind is ChangeKind.CONFLICT:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="conflict",
                        details={"reason": change.reason or "blocked"},
                    )
                )
                continue
            if change.kind is ChangeKind.NOOP:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                        details={"reason": change.reason or "no drift"},
                    )
                )
                continue
            if change.kind is not ChangeKind.UPDATE:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                        details={"reason": change.reason or "non-adoption-row"},
                    )
                )
                continue

            block = _ENTERPRISE_BLOCK_BY_RESOURCE[change.resource_type]
            keeper_uid = change.keeper_uid or ""
            existing_key = _enterprise_key_by_keeper_uid(self._enterprise_state[block], keeper_uid)
            if existing_key is None:
                candidate_key = _enterprise_key_for_change(change)
                if candidate_key is not None and candidate_key in self._enterprise_state[block]:
                    existing_key = candidate_key
                    keeper_uid = str(self._enterprise_state[block][existing_key]["keeper_uid"])
            if existing_key is None:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"dry_run": dry_run, "skipped": "record_missing"},
                    )
                )
                continue

            marker = encode_marker(
                uid_ref=change.uid_ref or change.title,
                manifest=plan.manifest_name,
                resource_type=change.resource_type,
            )
            if not dry_run:
                payload = {**deepcopy(self._enterprise_state[block][existing_key]), **change.after}
                payload["keeper_uid"] = keeper_uid
                payload["marker"] = marker
                payload["manager"] = marker["manager"]
                self._enterprise_state[block].pop(existing_key, None)
                self._enterprise_state[block][_enterprise_key_for_payload(payload)] = payload
                self._enterprise_markers[keeper_uid] = marker
            outcomes.append(
                ApplyOutcome(
                    uid_ref=change.uid_ref or "",
                    keeper_uid=keeper_uid,
                    action="update",
                    details={"dry_run": dry_run, "marker_written": not dry_run},
                )
            )
        return outcomes

    def enterprise_markers(self) -> dict[str, dict[str, Any]]:
        """Return decoded enterprise ownership markers for assertions."""
        return deepcopy(self._enterprise_markers)

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


class KsmMockProvider:
    """In-memory keeper-ksm.v1 provider for offline plan/apply tests."""

    def __init__(self, manifest_name: str | None = None) -> None:
        self._manifest_name = manifest_name or "keeper-ksm"
        self._ksm_state: dict[str, dict[str, dict[str, Any]]] = {block: {} for block in _KSM_BLOCKS}
        self._ksm_markers: dict[str, dict[str, Any]] = {}

    def discover_ksm_apps(self) -> list[dict[str, Any]]:
        """Return the live mock app rows; fresh providers return ``[]``."""
        return [deepcopy(row) for row in self._ksm_state["apps"].values()]

    def discover_ksm_state(self) -> dict[str, list[dict[str, Any]]]:
        """Return a Commander-like keeper-ksm.v1 live snapshot."""
        return {
            block: [deepcopy(row) for row in self._ksm_state[block].values()]
            for block in _KSM_BLOCKS
        }

    def unsupported_capabilities(self, manifest: object = None) -> list[str]:  # noqa: ARG002
        """Mock KSM provider supports every schema-valid offline KSM row."""
        return []

    def check_tenant_bindings(self, manifest: object = None) -> list[str]:  # noqa: ARG002
        """Offline KSM provider has no tenant-side binding checks."""
        return []

    def apply_ksm_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Apply keeper-ksm.v1 plan rows to in-memory state."""
        outcomes: list[ApplyOutcome] = []
        for change in _all_plan_changes(plan):
            if change.kind is ChangeKind.CONFLICT:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="conflict",
                        details={"reason": change.reason or "blocked"},
                    )
                )
                continue

            block = _KSM_BLOCK_BY_RESOURCE.get(change.resource_type)
            if block is None:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                        details={"reason": change.reason or "non-ksm-plan-row"},
                    )
                )
                continue

            if change.kind is ChangeKind.CREATE:
                keeper_uid = _stable_uid(
                    f"ksm:{plan.manifest_name}:{change.resource_type}:"
                    f"{change.uid_ref or change.title}"
                )
                payload = deepcopy(change.after)
                payload["keeper_uid"] = keeper_uid
                marker = encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=plan.manifest_name,
                    resource_type=change.resource_type,
                )
                if not dry_run:
                    self._ksm_state[block][_ksm_key_for_payload(block, payload)] = payload
                    self._ksm_markers[keeper_uid] = marker
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="create",
                        details={"dry_run": dry_run, "marker_written": not dry_run},
                    )
                )
                continue

            if change.kind is ChangeKind.UPDATE:
                keeper_uid = change.keeper_uid or ""
                existing_key = _ksm_key_by_keeper_uid(self._ksm_state[block], keeper_uid)
                if existing_key is None:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="update",
                            details={"dry_run": dry_run, "skipped": "record_missing"},
                        )
                    )
                    continue

                existing = self._ksm_state[block][existing_key]
                payload = {**deepcopy(existing), **deepcopy(change.after)}
                payload["keeper_uid"] = keeper_uid
                marker = self._ksm_markers.get(keeper_uid) or encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=plan.manifest_name,
                    resource_type=change.resource_type,
                )
                marker = {
                    **marker,
                    "manifest": plan.manifest_name,
                    "resource_type": change.resource_type,
                    "last_applied_at": utc_timestamp(),
                }
                if not dry_run:
                    self._ksm_state[block].pop(existing_key, None)
                    self._ksm_state[block][_ksm_key_for_payload(block, payload)] = payload
                    self._ksm_markers[keeper_uid] = marker
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"dry_run": dry_run, "marker_written": not dry_run},
                    )
                )
                continue

            if change.kind is ChangeKind.DELETE:
                keeper_uid = change.keeper_uid or ""
                existing_key = _ksm_key_by_keeper_uid(self._ksm_state[block], keeper_uid)
                if existing_key is None:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="delete",
                            details={"dry_run": dry_run, "skipped": "record_missing"},
                        )
                    )
                    continue
                if not dry_run:
                    self._ksm_state[block].pop(existing_key, None)
                    self._ksm_markers.pop(keeper_uid, None)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="delete",
                        details={"dry_run": dry_run},
                    )
                )
                continue

            details: dict[str, Any] = {"dry_run": dry_run}
            if change.reason is not None:
                details["reason"] = change.reason
            outcomes.append(
                ApplyOutcome(
                    uid_ref=change.uid_ref or "",
                    keeper_uid=change.keeper_uid or "",
                    action="noop",
                    details=details,
                )
            )
        return outcomes

    def seed_ksm_state(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        """Replace mock KSM state; test helper."""
        self._ksm_state = {block: {} for block in _KSM_BLOCKS}
        self._ksm_markers = {}
        for block in _KSM_BLOCKS:
            for row in rows.get(block) or []:
                payload = deepcopy(row)
                keeper_uid = str(
                    payload.get("keeper_uid")
                    or _stable_uid(
                        f"ksm:{self._manifest_name}:"
                        f"{_KSM_RESOURCE_BY_BLOCK[block]}:{_ksm_uid_ref_for_payload(block, payload)}"
                    )
                )
                payload["keeper_uid"] = keeper_uid
                marker = encode_marker(
                    uid_ref=_ksm_uid_ref_for_payload(block, payload),
                    manifest=self._manifest_name,
                    resource_type=_KSM_RESOURCE_BY_BLOCK[block],
                )
                self._ksm_state[block][_ksm_key_for_payload(block, payload)] = payload
                self._ksm_markers[keeper_uid] = marker

    def ksm_markers(self) -> dict[str, dict[str, Any]]:
        """Return decoded ownership markers for assertions."""
        return deepcopy(self._ksm_markers)


def _guard_vault_sharing_deletes(plan: Plan) -> None:
    guarded_delete = next(
        (
            change
            for change in plan.deletes
            if change.resource_type in _VAULT_SHARING_RESOURCE_TYPES
        ),
        None,
    )
    if guarded_delete is None or not hasattr(plan, "allow_delete"):
        return
    if getattr(plan, "allow_delete", False) is True:
        return
    raise CapabilityError(
        reason="keeper-vault-sharing delete requires --allow-delete",
        uid_ref=guarded_delete.uid_ref,
        resource_type=guarded_delete.resource_type,
        next_action="rerun plan/apply with --allow-delete before deleting sharing rows",
    )


def _normalise_mock_payload(resource_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if resource_type in {"sharing_record_share", "sharing_share_folder"}:
        payload = _normalise_mock_sharing_email(payload)
    if resource_type == "sharing_share_folder":
        payload = _sync_mock_sharing_permissions(payload)
    return payload


def _normalise_mock_sharing_email(payload: dict[str, Any]) -> dict[str, Any]:
    grantee = payload.get("grantee")
    if isinstance(grantee, dict) and grantee.get("kind") == "user":
        email = grantee.get("user_email")
        if email is not None:
            normalised = str(email).strip().casefold()
            payload["grantee"] = {**grantee, "user_email": normalised}
            payload["user_email"] = normalised
            return payload

    if payload.get("user_email") is not None:
        payload["user_email"] = str(payload["user_email"]).strip().casefold()
    return payload


def _sync_mock_sharing_permissions(payload: dict[str, Any]) -> dict[str, Any]:
    permissions = payload.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    for field in _SHARING_PERMISSION_FIELDS:
        if field not in payload and field in permissions:
            payload[field] = permissions[field]
        if field in payload:
            permissions[field] = payload[field]
    if permissions:
        payload["permissions"] = permissions
    return payload


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


def _enterprise_marker_from_payload(
    payload: dict[str, Any],
    *,
    block: str,
    manifest_name: str,
) -> dict[str, Any] | None:
    marker = payload.get("marker")
    if isinstance(marker, dict):
        return deepcopy(marker)
    manager = payload.get("manager")
    if manager is None or not str(manager).strip():
        return None
    return {
        "manager": str(manager).strip(),
        "uid_ref": _enterprise_uid_ref_for_payload(payload),
        "manifest": str(payload.get("manifest") or manifest_name),
        "resource_type": _ENTERPRISE_RESOURCE_BY_BLOCK[block],
    }


def _enterprise_key_by_keeper_uid(
    rows: dict[str, dict[str, Any]],
    keeper_uid: str,
) -> str | None:
    for key, row in rows.items():
        if row.get("keeper_uid") == keeper_uid:
            return key
    return None


def _enterprise_key_for_change(change: Change) -> str | None:
    for payload in (change.after, change.before):
        value = payload.get("uid_ref")
        if value is not None:
            return str(value)
    if change.uid_ref:
        return change.uid_ref
    return None


def _enterprise_key_for_payload(payload: dict[str, Any]) -> str:
    return str(payload["uid_ref"])


def _enterprise_uid_ref_for_payload(payload: dict[str, Any]) -> str:
    return str(payload["uid_ref"])


def _msp_change_name(change: Change) -> str:
    for payload in (change.after, change.before):
        value = payload.get("name")
        if value is not None:
            return str(value)
    return str(change.uid_ref or change.title)


def _msp_plan_changes(plan: Plan) -> list[Change]:
    return _all_plan_changes(plan)


def _all_plan_changes(plan: Plan) -> list[Change]:
    ordered = plan.ordered()
    seen = {id(change) for change in ordered}
    return ordered + [change for change in plan.changes if id(change) not in seen]


def _ksm_key_by_keeper_uid(rows: dict[str, dict[str, Any]], keeper_uid: str) -> str | None:
    for key, row in rows.items():
        if row.get("keeper_uid") == keeper_uid:
            return key
    return None


def _ksm_key_for_payload(block: str, payload: dict[str, Any]) -> str:
    if block in ("apps", "tokens"):
        return f"{block}:{payload['uid_ref']}"
    if block == "record_shares":
        return f"{block}:{payload['app_uid_ref']}|{payload['record_uid_ref']}"
    if block == "config_outputs":
        return f"{block}:{payload['app_uid_ref']}|{payload['output_path']}"
    raise KeyError(block)


def _ksm_uid_ref_for_payload(block: str, payload: dict[str, Any]) -> str:
    if block in ("apps", "tokens"):
        return str(payload["uid_ref"])
    if block == "record_shares":
        return f"share:{payload['app_uid_ref']}:{payload['record_uid_ref']}"
    if block == "config_outputs":
        return f"config:{payload['app_uid_ref']}:{payload['output_path']}"
    raise KeyError(block)


__all__ = ["KsmMockProvider", "MockProvider"]
