"""Commander-CLI backed provider.

Wraps the ``keeper`` CLI (Commander) via subprocess. This provider is the
production path today: Commander already implements record I/O, rotation
wiring, KSM binding, gateway registration, and share graph, so we reuse it
instead of re-implementing.

Commands used:
    keeper pam project import --file <manifest>.pam_import.json
    keeper pam project extend --file <manifest>.pam_import.json
    keeper pam project export --folder <uid>

The provider:
    1. Exports the target folder (if configured) and parses records.
    2. Decodes ownership markers from the custom field.
    3. Applies plans by writing a temp ``pam_import`` JSON document and
       invoking ``keeper pam project import`` or ``extend``.

NOTE: Deletion is not yet supported end-to-end by Commander's declarative
commands; DELETE changes will be reported back as unsupported outcomes so the
operator can act explicitly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import CapabilityError, DeleteUnsupportedError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker
from keeper_sdk.core.normalize import to_pam_import_json
from keeper_sdk.core.planner import Plan


class CommanderCliProvider(Provider):
    """Delegates to the ``keeper`` Commander CLI via subprocess."""

    def __init__(
        self,
        *,
        keeper_bin: str | None = None,
        folder_uid: str | None = None,
        config_file: str | None = None,
        manifest_source: dict[str, Any] | None = None,
    ) -> None:
        self._bin = keeper_bin or os.environ.get("KEEPER_BIN", "keeper")
        self._folder_uid = folder_uid or os.environ.get("KEEPER_DECLARATIVE_FOLDER")
        self._config = config_file or os.environ.get("KEEPER_CONFIG")
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
                    "CommanderCliProvider requires folder_uid "
                    "(or KEEPER_DECLARATIVE_FOLDER) to discover live state"
                ),
                next_action="set --folder-uid on the CLI or KEEPER_DECLARATIVE_FOLDER env var",
            )
        payload = self._run_cmd(["pam", "project", "export", "--folder", self._folder_uid, "--format", "json"])
        if not payload.strip():
            raise CapabilityError(reason="keeper pam project export produced no output")
        try:
            data = json.loads(payload)
        except ValueError as exc:
            raise CapabilityError(
                reason="Commander returned non-JSON from `pam project export`",
                next_action="upgrade Commander to a version that supports --format json",
            ) from exc
        return list(_records_from_export(data))

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

        if deletes:
            raise DeleteUnsupportedError(
                reason="Commander declarative apply does not support deletion yet",
                next_action=(
                    "remove the records manually (e.g. `keeper record-delete <uid>`) or rerun "
                    "without --allow-delete"
                ),
                context={"pending_deletes": [c.keeper_uid for c in deletes]},
            )

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

    def _run_cmd(self, args: list[str]) -> str:
        base = [self._bin]
        if self._config:
            base += ["--config", self._config]
        result = subprocess.run(
            base + args,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CapabilityError(
                reason=f"keeper {' '.join(args)} failed (rc={result.returncode})",
                context={"stdout": result.stdout[-400:], "stderr": result.stderr[-400:]},
                next_action="inspect the Commander output above and retry",
            )
        return result.stdout


def _has_existing(changes: list[Any]) -> bool:
    return any(c.kind is ChangeKind.UPDATE for c in changes)


def _records_from_export(data: Any) -> list[LiveRecord]:
    records: list[LiveRecord] = []
    export = _unwrap_export_payload(data)
    if not isinstance(export, dict):
        return records
    for collection_key in ("resources", "users", "pam_configurations", "gateways"):
        for item in export.get(collection_key) or []:
            if not isinstance(item, dict):
                continue
            keeper_uid = item.get("record_uid") or item.get("uid") or item.get("keeper_uid")
            if not keeper_uid:
                continue
            title = _title_from_item(item)
            payload = {k: v for k, v in item.items() if k not in {"record_uid"}}
            if title == "":
                payload["_note"] = "empty title"
            resource_type = item.get("type")
            if not resource_type:
                resource_type = _kind_from_collection(collection_key)
                if not resource_type:
                    continue
                payload["_legacy_type_fallback"] = True
            marker_raw = _extract_marker_field(item)
            marker = decode_marker(marker_raw)
            records.append(
                LiveRecord(
                    keeper_uid=keeper_uid,
                    title=title,
                    resource_type=resource_type,
                    payload=payload,
                    marker=marker,
                )
            )
    return records


def _unwrap_export_payload(data: Any) -> Any:
    if isinstance(data, list):
        for item in data:
            unwrapped = _unwrap_export_payload(item)
            if isinstance(unwrapped, dict):
                return unwrapped
        return None
    if not isinstance(data, dict):
        return None
    project = data.get("project")
    if isinstance(project, dict):
        return project
    return data


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
