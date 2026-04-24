"""Commander-CLI backed provider.

Wraps the ``keeper`` CLI (Commander) via subprocess. This provider is the
production path today: Commander already implements record I/O, rotation
wiring, KSM binding, gateway registration, and share graph, so we reuse it
instead of re-implementing.

Commands used:
    keeper pam project import --file <manifest>.pam_import.json
    keeper pam project extend --file <manifest>.pam_import.json
    keeper ls <folder_uid> --format json
    keeper get <uid> --format json
    keeper rm <uid>

The provider:
    1. Lists the target folder (if configured) and fetches each record.
    2. Decodes ownership markers from the custom field.
    3. Applies plans by writing a temp ``pam_import`` JSON document and
       invoking ``keeper pam project import`` or ``extend``.
    4. Deletes records via ``keeper rm <uid>``; ``compute_diff`` restricts
       deletes to records whose ownership marker matches ``MANAGER_NAME``.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from keeper_sdk.core.diff import _DIFF_IGNORED_FIELDS, ChangeKind
from keeper_sdk.core.errors import CapabilityError, CollisionError, DeleteUnsupportedError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    decode_marker,
    encode_marker,
    serialize_marker,
)
from keeper_sdk.core.normalize import to_pam_import_json
from keeper_sdk.core.planner import Plan

_DELETE_UNSUPPORTED_ERROR = DeleteUnsupportedError


class CommanderCliProvider(Provider):
    """Delegates to the ``keeper`` Commander CLI via subprocess."""

    def __init__(
        self,
        *,
        keeper_bin: str | None = None,
        folder_uid: str | None = None,
        config_file: str | None = None,
        manifest_source: dict[str, Any] | None = None,
        keeper_password: str | None = None,
    ) -> None:
        self._bin = keeper_bin or os.environ.get("KEEPER_BIN", "keeper")
        self._folder_uid = folder_uid or os.environ.get("KEEPER_DECLARATIVE_FOLDER")
        self.last_resolved_folder_uid: str | None = None
        self._config = config_file or os.environ.get("KEEPER_CONFIG")
        # Commander's persistent-login still needs the master password on
        # subprocess invocation to unlock the local key; honor --batch-mode by
        # sourcing it from constructor or KEEPER_PASSWORD rather than prompting.
        self._password = keeper_password or os.environ.get("KEEPER_PASSWORD")
        self._manifest_source = manifest_source or {}

        if not shutil.which(self._bin):
            raise CapabilityError(
                reason=f"keeper CLI not found on PATH (looked up '{self._bin}')",
                next_action="install Keeper Commander or set KEEPER_BIN",
            )

    # ------------------------------------------------------------------

    def discover(self) -> list[LiveRecord]:
        if not self._folder_uid:
            raise CapabilityError(
                reason=(
                    "CommanderCliProvider has no folder_uid for discover(); "
                    "pass an explicit folder_uid or run apply_plan() first so "
                    "the provider can resolve the project Resources folder"
                ),
                next_action="pass --folder-uid (or KEEPER_DECLARATIVE_FOLDER), or call apply_plan() first",
            )
        payload = self._run_cmd(["ls", self._folder_uid, "--format", "json"])
        entries = _load_json(payload, command="ls --format json")
        if not isinstance(entries, list):
            raise CapabilityError(reason="Commander returned non-array JSON from `ls --format json`")

        records: list[LiveRecord] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "record":
                continue
            keeper_uid = entry.get("uid")
            if not keeper_uid:
                continue
            item_payload = self._run_cmd(["get", keeper_uid, "--format", "json"])
            item = _load_json(item_payload, command="get --format json")
            if not isinstance(item, dict):
                raise CapabilityError(reason="Commander returned non-object JSON from `get --format json`")
            record = _record_from_get(item, listing_entry=entry)
            if record is not None:
                records.append(record)
        return records

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        outcomes: list[ApplyOutcome] = []
        creates_updates = [c for c in plan.ordered() if c.kind in (ChangeKind.CREATE, ChangeKind.UPDATE)]
        deletes = plan.deletes

        if creates_updates:
            payload = to_pam_import_json(self._manifest_source)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as handle:
                json.dump(payload, handle, indent=2)
                temp_path = Path(handle.name)
            try:
                cmd = ["pam", "project", "extend" if _has_existing(creates_updates) else "import",
                       "--file", str(temp_path)]
                if dry_run:
                    cmd.append("--dry-run")
                self._run_cmd(cmd)
                if not dry_run:
                    self._resolve_project_resources_folder(plan.manifest_name)
                for change in creates_updates:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=change.keeper_uid or "",
                            action=change.kind.value,
                            details={"dry_run": dry_run},
                        )
                    )
            finally:
                temp_path.unlink(missing_ok=True)

            if not dry_run:
                live_records = self.discover()
                live_by_key: dict[tuple[str, str], list[LiveRecord]] = {}
                for live in live_records:
                    live_by_key.setdefault((live.resource_type, live.title), []).append(live)

                now = _utc_now()
                for change, outcome in zip(creates_updates, outcomes, strict=False):
                    matches = live_by_key.get((change.resource_type, change.title), [])
                    if len(matches) > 1:
                        raise CollisionError(
                            reason=(
                                f"live tenant has {len(matches)} {change.resource_type} records titled "
                                f"'{change.title}' after apply"
                            ),
                            uid_ref=change.uid_ref,
                            resource_type=change.resource_type,
                            next_action="rename duplicates or add ownership markers so matching is unambiguous",
                            context={"live_identifiers": [live.keeper_uid for live in matches]},
                        )
                    if not matches:
                        outcome.details.update(
                            {
                                "marker_written": False,
                                "reason": "record not found after apply",
                            }
                        )
                        continue

                    live = matches[0]
                    marker = encode_marker(
                        uid_ref=change.uid_ref or change.title,
                        manifest=plan.manifest_name,
                        resource_type=change.resource_type,
                        last_applied_at=now,
                    )
                    self._write_marker(live.keeper_uid, marker)
                    outcome.details.update(
                        {
                            "marker_written": True,
                            "keeper_uid": live.keeper_uid,
                        }
                    )
                    drift = _field_drift(change.after or {}, live.payload)
                    if drift:
                        outcome.details["field_drift"] = drift
                    else:
                        outcome.details["verified"] = True

        for change in deletes:
            if not change.keeper_uid:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid="",
                        action="delete",
                        details={
                            "skipped": True,
                            "reason": "no keeper_uid on delete change",
                            "warning": "dependency checks are enforced by Keeper CLI/server, not client-side",
                        },
                    )
                )
                continue

            if dry_run:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid,
                        action="delete",
                        details={
                            "dry_run": True,
                            "keeper_uid": change.keeper_uid,
                            "warning": "dependency checks are enforced by Keeper CLI/server, not client-side",
                        },
                    )
                )
                continue

            outcome = ApplyOutcome(
                uid_ref=change.uid_ref or "",
                keeper_uid=change.keeper_uid,
                action="delete",
                details={
                    "keeper_uid": change.keeper_uid,
                    "removed": False,
                    "warning": "dependency checks are enforced by Keeper CLI/server, not client-side",
                },
            )
            outcomes.append(outcome)
            try:
                self._run_cmd(["rm", change.keeper_uid])
            except CapabilityError:
                raise
            outcome.details["removed"] = True

        for change in plan.conflicts:
            outcomes.append(
                ApplyOutcome(
                    uid_ref=change.uid_ref or "",
                    keeper_uid=change.keeper_uid or "",
                    action="conflict",
                    details={"reason": change.reason or ""},
                )
            )
        for change in plan.noops:
            outcomes.append(
                ApplyOutcome(
                    uid_ref=change.uid_ref or "",
                    keeper_uid=change.keeper_uid or "",
                    action="noop",
                )
            )
        return outcomes

    # ------------------------------------------------------------------

    def _write_marker(self, keeper_uid: str, marker: dict[str, Any]) -> None:
        payload = serialize_marker(marker)
        self._run_cmd(
            [
                "record-update",
                "--record",
                keeper_uid,
                "-cf",
                f"{MARKER_FIELD_LABEL}={payload}",
            ]
        )

    def _resolve_project_resources_folder(self, project_name: str) -> str:
        root_entries = _load_json(
            self._run_cmd(["ls", "--format", "json", "PAM Environments"]),
            command="ls --format json PAM Environments",
        )
        root_uid = _entry_uid_by_name(root_entries, "PAM Environments")
        if not root_uid:
            raise CapabilityError(
                reason="Commander did not return the PAM Environments root folder UID",
                next_action="re-run apply and inspect `keeper ls --format json PAM Environments`",
            )

        project_entries = _load_json(
            self._run_cmd(["ls", "--format", "json", root_uid]),
            command=f"ls --format json {root_uid}",
        )
        project_uid = _entry_uid_by_name(project_entries, project_name)
        if not project_uid:
            raise CapabilityError(
                reason=f"Commander did not return project folder '{project_name}' under PAM Environments",
                next_action=f"inspect `keeper ls --format json {root_uid}` and confirm import created the project folder",
            )

        resources_entries = _load_json(
            self._run_cmd(["ls", "--format", "json", project_uid]),
            command=f"ls --format json {project_uid}",
        )
        resources_name = f"{project_name} - Resources"
        resources_uid = _entry_uid_by_name(resources_entries, resources_name)
        if not resources_uid:
            raise CapabilityError(
                reason=f"Commander did not return resources folder '{resources_name}' under project '{project_name}'",
                next_action=f"inspect `keeper ls --format json {project_uid}` and confirm import created the Resources folder",
            )
        self._folder_uid = resources_uid
        self.last_resolved_folder_uid = resources_uid
        return resources_uid

    def _run_cmd(self, args: list[str]) -> str:
        # --batch-mode suppresses interactive prompts (password, 2FA,
        # confirmations). stdin=DEVNULL is belt-and-braces — if Commander ever
        # tries to read stdin despite --batch-mode we want EOF, not a hang.
        base = [self._bin, "--batch-mode"]
        if self._config:
            base += ["--config", self._config]
        env = os.environ.copy()
        if self._password:
            env["KEEPER_PASSWORD"] = self._password
        result = subprocess.run(
            base + args,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=env,
        )
        if result.returncode != 0:
            raise CapabilityError(
                reason=f"keeper {' '.join(args)} failed (rc={result.returncode})",
                context={"stdout": result.stdout[-400:], "stderr": result.stderr[-400:]},
                next_action="inspect the Commander output above and retry",
            )
        return result.stdout


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _has_existing(changes: list[Any]) -> bool:
    return any(c.kind is ChangeKind.UPDATE for c in changes)


def _field_drift(expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only fields whose expected/observed values differ."""
    ignored = _DIFF_IGNORED_FIELDS | {
        "keeper_uid",
        "record_uid",
        "record_title",
        "custom_fields",
        "custom",
        "type",
        "title",
        "_legacy_type_fallback",
        "_note",
    }
    drift: dict[str, dict[str, Any]] = {}
    for key, expected_value in expected.items():
        if key in ignored or expected_value is None:
            continue
        observed_value = observed.get(key)
        if key == "port" and _port_value(expected_value) == _port_value(observed_value):
            continue
        if expected_value != observed_value:
            drift[key] = {
                "expected": expected_value,
                "observed": observed_value,
            }
    return drift


def _port_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return value


def _load_json(payload: str, *, command: str) -> Any:
    # Commander 17.x emits an empty string when listing an empty folder;
    # treat that as an empty list so discover() on a fresh sandbox works.
    if not payload or not payload.strip():
        return []
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise CapabilityError(
            reason=f"Commander returned non-JSON from `{command}`",
            next_action="upgrade Commander to a version that supports --format json",
        ) from exc


def _entry_uid_by_name(entries: Any, name: str) -> str | None:
    if not isinstance(entries, list):
        raise CapabilityError(
            reason="Commander returned non-array JSON while resolving folder entries",
            next_action="upgrade Commander to a version that supports --format json",
        )
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == name or entry.get("title") == name:
            uid = entry.get("uid") or entry.get("folder_uid") or entry.get("shared_folder_uid")
            if uid:
                return str(uid)
    return None


def _record_from_get(item: dict[str, Any], *, listing_entry: dict[str, Any]) -> LiveRecord | None:
    keeper_uid = item.get("record_uid") or item.get("uid") or item.get("keeper_uid") or listing_entry.get("uid")
    if not keeper_uid:
        return None

    title = _title_from_item(item)
    payload = _payload_from_get(item)
    if title == "":
        payload["_note"] = "empty title"

    resource_type, legacy_type_fallback = _resource_type_from_get(item, listing_entry=listing_entry)
    if not resource_type:
        return None
    if legacy_type_fallback:
        payload["_legacy_type_fallback"] = True

    marker_raw = _extract_marker_field(item)
    marker = decode_marker(marker_raw)
    return LiveRecord(
        keeper_uid=keeper_uid,
        title=title,
        resource_type=resource_type,
        folder_uid=listing_entry.get("folder_uid"),
        payload=payload,
        marker=marker,
    )


def _payload_from_get(item: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in item.items() if k not in {"record_uid"}}
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        payload.update(_canonical_payload_from_field(field))
    return payload


def _canonical_payload_from_field(field: dict[str, Any]) -> dict[str, Any]:
    field_type = field.get("type")
    values = field.get("value")
    if not field_type or not isinstance(values, list):
        return {}
    if field_type == "host":
        return _host_payload(values)
    if len(values) != 1:
        return {}
    value = values[0]
    if isinstance(value, (str, int, float, bool)):
        return {field_type: value}
    return {}


def _host_payload(values: list[Any]) -> dict[str, Any]:
    if len(values) != 1 or not isinstance(values[0], dict):
        return {}
    value = values[0]
    payload: dict[str, Any] = {}
    if value.get("hostName") is not None:
        payload["host"] = value["hostName"]
    if value.get("port") is not None:
        payload["port"] = value["port"]
    return payload


def _resource_type_from_get(item: dict[str, Any], *, listing_entry: dict[str, Any]) -> tuple[str | None, bool]:
    resource_type = item.get("type")
    if resource_type:
        return resource_type, False
    resource_type = _type_from_listing_details(listing_entry.get("details"))
    if resource_type:
        return resource_type, False
    resource_type = _kind_from_collection(item.get("collection", ""))
    if resource_type:
        item.setdefault("type", resource_type)
        return resource_type, True
    return None, False


def _type_from_listing_details(details: Any) -> str | None:
    if not isinstance(details, str):
        return None
    prefix = "Type:"
    if not details.startswith(prefix):
        return None
    tail = details[len(prefix):].strip()
    if not tail:
        return None
    return tail.split(",", 1)[0].strip() or None


def _title_from_item(item: dict[str, Any]) -> str:
    for key in ("title", "record_title", "name"):
        value = item.get(key)
        if value is not None:
            return value
    return ""


def _kind_from_collection(collection: str) -> str | None:
    return {
        "users": "pamUser",
        "pam_configurations": "pam_configuration",
        "gateways": "gateway",
    }.get(collection)


def _extract_marker_field(item: dict[str, Any]) -> str | None:
    # Commander exports may expose custom fields under a few shapes.
    for key in ("custom_fields", "custom"):
        block = item.get(key)
        if isinstance(block, dict) and MARKER_FIELD_LABEL in block:
            value = block[MARKER_FIELD_LABEL]
            if isinstance(value, list):
                return value[0] if value else None
            return value
        if isinstance(block, list):
            for entry in block:
                if not isinstance(entry, dict):
                    continue
                if entry.get("label") == MARKER_FIELD_LABEL or entry.get("name") == MARKER_FIELD_LABEL:
                    value = entry.get("value")
                    if isinstance(value, list):
                        return value[0] if value else None
                    return value
    return None


__all__ = ["CommanderCliProvider"]
