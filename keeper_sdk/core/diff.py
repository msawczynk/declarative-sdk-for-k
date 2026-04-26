"""Change classification between desired (manifest) and observed (provider)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from keeper_sdk.core.errors import CollisionError, OwnershipError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MANAGER_NAME, MARKER_VERSION
from keeper_sdk.core.models import Manifest


class ChangeKind(StrEnum):
    """Classification of a single planned change.

    * ``CREATE`` — manifest describes a resource that does not exist in
      the vault yet.
    * ``UPDATE`` — manifest and vault both carry the resource but their
      fields drift. Only raised when drift is detected on declarative
      (manifest-owned) fields — SDK-internal placement metadata is
      ignored via :data:`_DIFF_IGNORED_FIELDS`.
    * ``DELETE`` — vault carries a record with an ownership marker whose
      ``uid_ref`` is absent from the manifest. Requires
      ``allow_delete=True`` on ``compute_diff``.
    * ``NOOP`` — manifest and vault agree; no action required.
    * ``CONFLICT`` — a situation the planner cannot resolve automatically
      (name collision, ambiguous marker, incompatible type). Operator
      must resolve before re-running.
    """

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"
    CONFLICT = "conflict"


@dataclass
class Change:
    """One row of a :class:`Plan`.

    Attributes:
        kind: Classification — see :class:`ChangeKind`.
        uid_ref: Manifest handle. ``None`` only for deletes on records
            that never had a declarative owner (should be rare).
        resource_type: Declarative type (``pamMachine``, ``gateway``, …).
        title: Human-facing identifier used by renderers and by
            Commander ``pam project import`` to match records.
        keeper_uid: Vault UID of the matched live record; ``None`` on
            pure creates.
        before / after: Normalised field dicts for diff rendering.
        reason: Optional human-readable explanation (used for NOOP /
            CONFLICT rows).
    """

    kind: ChangeKind
    uid_ref: str | None
    resource_type: str
    title: str
    keeper_uid: str | None = None
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


_MANAGED_TYPES = (
    "gateway",
    "pam_configuration",
    "pamMachine",
    "pamDatabase",
    "pamDirectory",
    "pamRemoteBrowser",
    "pamUser",
    "login",
)


def _desired_objects(manifest: Manifest) -> list[tuple[str, str, str, dict[str, Any]]]:
    """Yield (uid_ref, resource_type, title, payload) for every managed object."""
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    data = manifest.model_dump(mode="python", exclude_none=True)

    for gateway in data.get("gateways") or []:
        if gateway.get("mode") == "create":
            out.append((gateway["uid_ref"], "gateway", gateway.get("name", ""), gateway))
    for cfg in data.get("pam_configurations") or []:
        title = cfg.get("title") or cfg.get("uid_ref")
        out.append((cfg["uid_ref"], "pam_configuration", title, cfg))
    for res in data.get("resources") or []:
        out.append((res["uid_ref"], res["type"], res.get("title", ""), res))
        for user in res.get("users") or []:
            out.append((user.get("uid_ref") or "", user["type"], user.get("title", ""), user))
    for user in data.get("users") or []:
        out.append((user.get("uid_ref") or "", user["type"], user.get("title", ""), user))
    return out


def compute_diff(
    manifest: Manifest,
    live_records: list[LiveRecord],
    *,
    manifest_name: str | None = None,
    allow_delete: bool = False,
    adopt: bool = False,
) -> list[Change]:
    """Classify desired (manifest) vs observed (live) state.

    Matching rules:
      1. Prefer ``LiveRecord.marker.uid_ref == desired.uid_ref`` when present.
      2. Otherwise match by ``(resource_type, title)``.
      3. Records marked by a *different* manager are flagged as CONFLICT
         and never touched — the SDK owns only what it wrote.

    The function is deliberately a thin orchestrator: the three hard
    sub-problems (duplicate detection, desired-vs-live matching, orphan
    classification) live in private helpers so each can be read + tested
    in isolation.
    """
    manifest_name = manifest_name or manifest.name
    _raise_live_record_collisions(live_records)

    by_uid_ref, by_title = _index_live(live_records)

    changes: list[Change] = []
    matched: set[str] = set()

    for uid_ref, resource_type, title, payload in _desired_objects(manifest):
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


def _index_live(
    live_records: list[LiveRecord],
) -> tuple[dict[str, LiveRecord], dict[tuple[str, str], LiveRecord]]:
    """Return two lookup dicts over live records: by marker uid_ref, by (type, title)."""
    by_uid_ref: dict[str, LiveRecord] = {}
    by_title: dict[tuple[str, str], LiveRecord] = {}
    for live in live_records:
        marker_uid_ref = (live.marker or {}).get("uid_ref") if live.marker else None
        if marker_uid_ref:
            by_uid_ref[marker_uid_ref] = live
        by_title[(live.resource_type, live.title)] = live
    return by_uid_ref, by_title


def _pam_remote_browser_settings_equivalent(live_ps: Any, desired_ps: Any) -> bool:
    """True when every ``pam_settings`` option/connection key set on *desired* matches *live*."""
    if not isinstance(desired_ps, dict):
        return live_ps == desired_ps
    live_ps = live_ps if isinstance(live_ps, dict) else {}
    for section in ("options", "connection"):
        desired_sec = desired_ps.get(section)
        if not isinstance(desired_sec, dict):
            continue
        live_sec = live_ps.get(section)
        live_sec = live_sec if isinstance(live_sec, dict) else {}
        for k, want in desired_sec.items():
            if want is None:
                continue
            if live_sec.get(k) != want:
                return False
    return True


def _normalize_rotation_enabled(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return "on" if val else "off"
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return "on"
    if s in ("false", "0", "no", "off"):
        return "off"
    return s


def _normalize_rotation_schedule_tuple(sched: Any) -> tuple[Any, ...]:
    if sched is None:
        return ("",)
    if not isinstance(sched, dict):
        return ("raw", str(sched))
    st = sched.get("type")
    st_s = str(st).strip() if st is not None else ""
    slug = st_s.casefold().replace("_", "-").replace(" ", "")
    if slug == "cron":
        cron = sched.get("cron")
        if cron is None:
            cron = sched.get("expression")
        return ("CRON", str(cron or "").strip())
    rest = {k: v for k, v in sched.items() if k != "type"}
    return (slug or st_s, json.dumps(rest, sort_keys=True) if rest else "")


def _rotation_settings_equivalent(live: Any, desired: Any) -> bool:
    """Semantic equality for Commander vs manifest ``rotation_settings`` shape drift."""
    if live == desired:
        return True
    if not isinstance(desired, dict):
        return live == desired
    live_d = live if isinstance(live, dict) else {}

    def norm(rs: dict[str, Any]) -> tuple[Any, ...]:
        rot = rs.get("rotation")
        en = _normalize_rotation_enabled(rs.get("enabled"))
        sched_t = _normalize_rotation_schedule_tuple(rs.get("schedule"))
        pc = rs.get("password_complexity")
        if isinstance(pc, (dict, list)):
            pc = json.dumps(pc, sort_keys=True)
        else:
            pc = str(pc) if pc is not None else None
        return (rot, en, sched_t, pc)

    return norm(live_d) == norm(desired)


def _trust_missing_rotation_settings_readback(
    live: dict[str, Any],
    desired: dict[str, Any],
    *,
    marker: dict[str, Any] | None,
    uid_ref: str,
) -> bool:
    """Option A: trust SDK-owned pamUser rotation apply when Commander get omits readback.

    Repository fixtures and provider parsers have no proven
    ``keeper get --format json`` typed field for nested user rotation; apply
    writes it through ``pam rotation edit``. Until Commander exposes stable
    readback, a matching SDK marker is the offline proof that suppresses the
    desired-only re-plan drift.
    """
    if "rotation_settings" not in desired or "rotation_settings" in live:
        return False
    if desired.get("rotation_settings") is None:
        return False
    marker_d = marker or {}
    return (
        bool(uid_ref)
        and marker_d.get("manager") == MANAGER_NAME
        and marker_d.get("uid_ref") == uid_ref
        and marker_d.get("resource_type") in (None, "pamUser")
    )


def _field_diff_pam_user(
    live: dict[str, Any],
    desired: dict[str, Any],
    *,
    marker: dict[str, Any] | None = None,
    uid_ref: str = "",
) -> list[str]:
    keys: set[str] = set(live) | set(desired)
    changed: list[str] = []
    for key in keys:
        if key in _DIFF_IGNORED_FIELDS:
            continue
        if key not in desired:
            continue
        if key == "rotation_settings":
            if _trust_missing_rotation_settings_readback(
                live,
                desired,
                marker=marker,
                uid_ref=uid_ref,
            ):
                continue
            if not _rotation_settings_equivalent(live.get(key), desired.get(key)):
                changed.append(key)
        elif live.get(key) != desired.get(key):
            changed.append(key)
    return sorted(changed)


def _field_diff_pam_remote_browser(live: dict[str, Any], desired: dict[str, Any]) -> list[str]:
    """Like :func:`_field_diff` but treats ``pam_settings`` as a partial overlay for RBI."""
    keys: set[str] = set(live) | set(desired)
    changed: list[str] = []
    for key in keys:
        if key in _DIFF_IGNORED_FIELDS:
            continue
        if key not in desired:
            continue
        if key == "pam_settings":
            if not _pam_remote_browser_settings_equivalent(live.get(key), desired.get(key)):
                changed.append(key)
        elif live.get(key) != desired.get(key):
            changed.append(key)
    return sorted(changed)


def _classify_desired(
    *,
    uid_ref: str,
    resource_type: str,
    title: str,
    payload: dict[str, Any],
    live: LiveRecord | None,
    by_title: dict[tuple[str, str], LiveRecord],
    adopt: bool,
) -> Change:
    """Classify ONE desired resource against its best live match.

    Branches in order:
      * no live match → CREATE
      * foreign marker → CONFLICT (never adopt)
      * unsupported marker version → raise OwnershipError
      * unmanaged title collision → CONFLICT (or UPDATE with adoption
        reason when ``adopt`` is set)
      * field drift → UPDATE; otherwise NOOP
    """
    if live is None:
        return Change(
            kind=ChangeKind.CREATE,
            uid_ref=uid_ref or None,
            resource_type=resource_type,
            title=title,
            after=payload,
        )

    marker = live.marker or {}
    manager = marker.get("manager")
    if marker and manager and manager != MANAGER_NAME:
        return Change(
            kind=ChangeKind.CONFLICT,
            uid_ref=uid_ref or None,
            resource_type=resource_type,
            title=title,
            keeper_uid=live.keeper_uid,
            reason=f"record managed by '{manager}', refusing to touch",
        )
    if marker and marker.get("version") not in (None, MARKER_VERSION):
        raise OwnershipError(
            reason=f"marker version {marker.get('version')} not supported by core v{MARKER_VERSION}",
            uid_ref=uid_ref,
            resource_type=resource_type,
            live_identifier=live.keeper_uid,
            next_action="upgrade the declarative core or rewrite the marker",
        )
    if not marker and by_title.get((resource_type, title)) is live:
        if not adopt:
            return Change(
                kind=ChangeKind.CONFLICT,
                uid_ref=uid_ref or None,
                resource_type=resource_type,
                title=title,
                keeper_uid=live.keeper_uid,
                reason="unmanaged record with matching title; pass --adopt or use an import workflow to claim it",
            )
        return Change(
            kind=ChangeKind.UPDATE,
            uid_ref=uid_ref or None,
            resource_type=resource_type,
            title=title,
            keeper_uid=live.keeper_uid,
            before=live.payload,
            after=payload,
            reason="adoption: write ownership marker",
        )

    if resource_type == "pamRemoteBrowser":
        diff_fields = _field_diff_pam_remote_browser(live.payload, payload)
    elif resource_type == "pamUser":
        diff_fields = _field_diff_pam_user(
            live.payload,
            payload,
            marker=live.marker,
            uid_ref=uid_ref,
        )
    else:
        diff_fields = _field_diff(live.payload, payload)
    if not diff_fields:
        return Change(
            kind=ChangeKind.NOOP,
            uid_ref=uid_ref or None,
            resource_type=resource_type,
            title=title,
            keeper_uid=live.keeper_uid,
        )
    return Change(
        kind=ChangeKind.UPDATE,
        uid_ref=uid_ref or None,
        resource_type=resource_type,
        title=title,
        keeper_uid=live.keeper_uid,
        before={k: live.payload.get(k) for k in diff_fields},
        after={k: payload.get(k) for k in diff_fields},
    )


def _classify_orphans(
    live_records: list[LiveRecord],
    *,
    matched: set[str],
    manifest_name: str,
    allow_delete: bool,
) -> list[Change]:
    """Emit DELETE / CONFLICT rows for records that went unmatched.

    Only this-manifest-managed records are considered. Foreign-managed
    and unmanaged records silently fall through — the SDK refuses to
    remove anything it did not create.
    """
    out: list[Change] = []
    for live in live_records:
        if live.keeper_uid in matched:
            continue
        marker = live.marker or {}
        if marker.get("manager") != MANAGER_NAME:
            continue
        if marker.get("manifest") and manifest_name and marker.get("manifest") != manifest_name:
            continue
        if allow_delete:
            out.append(
                Change(
                    kind=ChangeKind.DELETE,
                    uid_ref=marker.get("uid_ref"),
                    resource_type=live.resource_type,
                    title=live.title,
                    keeper_uid=live.keeper_uid,
                    before=live.payload,
                )
            )
        else:
            out.append(
                Change(
                    kind=ChangeKind.CONFLICT,
                    uid_ref=marker.get("uid_ref"),
                    resource_type=live.resource_type,
                    title=live.title,
                    keeper_uid=live.keeper_uid,
                    reason="managed record missing from manifest; pass --allow-delete to remove",
                )
            )
    return out


def _raise_live_record_collisions(live_records: list[LiveRecord]) -> None:
    """Reject ambiguous live-record matches before diffing desired state."""
    marker_matches: dict[str, list[LiveRecord]] = {}
    title_matches: dict[tuple[str, str], list[LiveRecord]] = {}

    for live in live_records:
        marker_uid_ref = (live.marker or {}).get("uid_ref") if live.marker else None
        if marker_uid_ref:
            marker_matches.setdefault(marker_uid_ref, []).append(live)
        title_matches.setdefault((live.resource_type, live.title), []).append(live)

    for uid_ref, matches in marker_matches.items():
        if len(matches) < 2:
            continue
        raise CollisionError(
            reason=f"live tenant has {len(matches)} records claiming uid_ref='{uid_ref}'",
            uid_ref=uid_ref,
            next_action="reconcile the duplicate ownership markers manually before re-running apply",
            context={"live_identifiers": [live.keeper_uid for live in matches]},
        )

    for (resource_type, title), matches in title_matches.items():
        if len(matches) < 2:
            continue
        if any((live.marker or {}).get("uid_ref") for live in matches):
            continue
        raise CollisionError(
            reason=f"live tenant has {len(matches)} {resource_type} records titled '{title}' with no ownership markers",
            uid_ref=None,
            resource_type=resource_type,
            next_action="rename duplicates or add ownership markers so matching is unambiguous",
            context={"live_identifiers": [live.keeper_uid for live in matches]},
        )


_DIFF_IGNORED_FIELDS = frozenset(
    {
        "uid_ref",
        "attachments",
        "scripts",
        "custom_fields",
        "record_uid",
        # SDK-only placement/linkage metadata — not record fields and never
        # observable from Commander `get`. Keep them out of the planner diff so
        # re-plans are clean when fields match.
        "pam_configuration",
        "pam_configuration_uid_ref",
        "shared_folder",
        "users",
        "gateway",
        "gateway_uid_ref",
    }
)


def _field_diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return keys whose value differs. Only compare overlapping canonical keys."""
    keys: set[str] = set(before) | set(after)
    changed: list[str] = []
    for key in keys:
        if key in _DIFF_IGNORED_FIELDS:
            continue
        # only treat a key as changed if the desired side actually set it; this
        # avoids churn on fields the caller doesn't manage.
        if key not in after:
            continue
        if before.get(key) != after.get(key):
            changed.append(key)
    return sorted(changed)


__all__ = ["Change", "ChangeKind", "compute_diff", "CollisionError"]
