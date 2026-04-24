"""In-memory provider. Deterministic, zero-I/O, used by tests and dry runs.

State is kept in ``self._records``, keyed by the generated keeper_uid. Each
record carries an ownership marker so later runs see themselves as managed.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
    utc_timestamp,
)
from keeper_sdk.core.planner import Plan


class MockProvider(Provider):
    """In-memory provider suitable for tests and offline demos."""

    def __init__(self, manifest_name: str | None = None) -> None:
        self._records: dict[str, LiveRecord] = {}
        self._manifest_name = manifest_name

    # ------------------------------------------------------------------
    # Provider protocol

    def discover(self) -> list[LiveRecord]:
        return list(self._records.values())

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


__all__ = ["MockProvider"]
