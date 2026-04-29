"""Commander Service Mode REST provider."""

from __future__ import annotations

import json
import os
import shlex
from collections.abc import Mapping
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker
from keeper_sdk.core.normalize import to_pam_import_json
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_cli import (
    _detect_unsupported_capabilities,
    _rotation_apply_is_enabled,
)
from keeper_sdk.providers.service_client import CommanderServiceClient

_SUCCESS_STATUSES = {"completed", "complete", "success", "succeeded", "done", ""}
_FAILED_STATUSES = {"failed", "failure", "error", "expired", "cancelled", "canceled"}
_UPDATE_SKIP_KEYS = {
    "uid_ref",
    "keeper_uid",
    "record_uid",
    "custom_fields",
    "custom",
    "type",
    "title",
}
_RESOURCE_COMMANDS = {
    "pamMachine": "machine",
    "pamDatabase": "database",
    "pamDirectory": "directory",
    "pamRemoteBrowser": "rbi",
    "pamUser": "user",
    "pam_configuration": "config",
    "gateway": "gateway",
}


class CommanderServiceProvider(Provider):
    """HTTP provider for Commander Service Mode REST API v2."""

    def __init__(
        self,
        base_url: str = "http://localhost:4020",
        api_key: str | None = None,
        timeout: int = 300,
        *,
        manifest_source: dict[str, Any] | None = None,
        client: CommanderServiceClient | None = None,
    ) -> None:
        api_key = api_key or os.environ.get("KEEPER_SERVICE_API_KEY") or ""
        if not api_key:
            raise CapabilityError(
                reason="Commander Service Mode API key is required",
                next_action="set KEEPER_SERVICE_API_KEY",
            )
        self.base_url = base_url or "http://localhost:4020"
        self.api_key = api_key
        self.timeout = timeout
        self._manifest_source = manifest_source or {}
        self._client = client or CommanderServiceClient(
            self.base_url,
            self.api_key,
            timeout=timeout,
        )

    def _execute(self, command: str, filedata: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST async, poll status, return result. Raise CapabilityError on failure."""
        request_id = self._client._post_async(command, filedata)
        status_payload = self._client._poll_status(request_id, self.timeout)
        status = _status(status_payload)
        if status in _FAILED_STATUSES:
            raise CapabilityError(
                reason=_failure_reason(status_payload, fallback=f"command {command!r} {status}"),
                next_action="inspect Commander Service Mode request logs and retry after fixing the command",
                context={"request_id": request_id, "status": status_payload},
            )
        if status not in _SUCCESS_STATUSES:
            raise CapabilityError(
                reason=f"Commander Service Mode returned unknown status {status!r}",
                next_action="check service-mode API v2 compatibility",
                context={"request_id": request_id, "status": status_payload},
            )
        result = self._client._get_result(request_id)
        result_status = _status(result)
        if result_status in _FAILED_STATUSES:
            raise CapabilityError(
                reason=_failure_reason(result, fallback=f"command {command!r} failed"),
                next_action="inspect Commander result output",
                context={"request_id": request_id, "result": result},
            )
        return result

    def discover(self) -> list[LiveRecord]:
        """`pam project list --format=json` -> parse live records."""
        result = self._execute("pam project list --format=json")
        payload = _extract_json_payload(result)
        rows = list(_iter_record_rows(payload))
        return [record for row in rows if (record := _live_record_from_row(row)) is not None]

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Execute plan changes through Commander Service Mode."""
        outcomes: list[ApplyOutcome] = []

        for change in plan.ordered():
            if change.kind is ChangeKind.CREATE:
                filedata = self._filedata_for_create(change, plan)
                command = "pam project import --filename=FILEDATA"
                if not dry_run:
                    result = self._execute(command, filedata=filedata)
                    keeper_uid = _keeper_uid_from_result(result) or change.keeper_uid or ""
                else:
                    keeper_uid = change.keeper_uid or ""
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="create",
                        details={"dry_run": dry_run, "command": command},
                    )
                )
                continue

            if change.kind is ChangeKind.UPDATE:
                command = _edit_command(change)
                if not dry_run:
                    result = self._execute(command)
                    keeper_uid = _keeper_uid_from_result(result) or change.keeper_uid or ""
                else:
                    keeper_uid = change.keeper_uid or ""
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"dry_run": dry_run, "command": command},
                    )
                )
                continue

            if change.kind is ChangeKind.DELETE:
                command = _delete_command(change)
                if not dry_run:
                    self._execute(command)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="delete",
                        details={"dry_run": dry_run, "command": command},
                    )
                )
                continue

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

    def unsupported_capabilities(self, manifest: Any = None) -> list[str]:
        """Same capability gaps as CLI provider; service mode adds transport only."""
        source = manifest if manifest is not None else self._manifest_source
        return _detect_unsupported_capabilities(
            source,
            allow_nested_rotation=_rotation_apply_is_enabled(),
        )

    def check_tenant_bindings(self, manifest: Any = None) -> list[str]:  # noqa: ARG002
        return []

    def _filedata_for_create(self, change: Change, plan: Plan) -> dict[str, Any]:
        if self._manifest_source:
            return to_pam_import_json(self._manifest_source)
        payload = dict(change.after)
        if change.resource_type == "pam_configuration":
            return {"project": plan.manifest_name, "pam_configuration": payload}
        if change.resource_type == "gateway":
            return {"project": plan.manifest_name, "gateways": [payload]}
        return {
            "project": plan.manifest_name,
            "pam_data": {"resources": [payload]},
        }


def _status(payload: Mapping[str, Any]) -> str:
    value = payload.get("status") or payload.get("state") or payload.get("request_status")
    return str(value or "").strip().lower()


def _failure_reason(payload: Mapping[str, Any], *, fallback: str) -> str:
    for key in ("reason", "message", "error", "stderr"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _extract_json_payload(result: Any) -> Any:
    if isinstance(result, str):
        return _json_or_value(result)
    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return result
    for key in ("records", "resources", "projects", "data"):
        value = result.get(key)
        if value is not None:
            return value
    for key in ("stdout", "output", "result", "response"):
        value = result.get(key)
        if value is not None:
            return _extract_json_payload(_json_or_value(value) if isinstance(value, str) else value)
    return result


def _json_or_value(value: str) -> Any:
    if not value.strip():
        return []
    try:
        return json.loads(value)
    except ValueError:
        return value


def _iter_record_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            rows.extend(_iter_record_rows(item))
        return rows
    if not isinstance(payload, dict):
        return rows

    if _looks_like_record(payload):
        rows.append(payload)

    for key in ("records", "resources", "users"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                rows.extend(_iter_record_rows(item))

    pam_data = payload.get("pam_data")
    if isinstance(pam_data, dict):
        rows.extend(_iter_record_rows(pam_data))
    projects = payload.get("projects")
    if isinstance(projects, list):
        for project in projects:
            rows.extend(_iter_record_rows(project))
    return rows


def _looks_like_record(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("keeper_uid")
        or row.get("record_uid")
        or row.get("uid")
        or row.get("resource_uid")
        or row.get("pam_resource_uid")
    ) and bool(row.get("resource_type") or row.get("type") or row.get("record_type"))


def _live_record_from_row(row: dict[str, Any]) -> LiveRecord | None:
    keeper_uid = (
        row.get("keeper_uid")
        or row.get("record_uid")
        or row.get("uid")
        or row.get("resource_uid")
        or row.get("pam_resource_uid")
    )
    if not keeper_uid:
        return None
    title = str(row.get("title") or row.get("name") or row.get("record_title") or keeper_uid)
    resource_type = str(row.get("resource_type") or row.get("record_type") or row.get("type") or "")
    if resource_type == "record":
        resource_type = str(row.get("record_type") or row.get("record_type_name") or "")
    if not resource_type:
        return None
    marker = _marker_from_row(row)
    payload = dict(row.get("payload") or row)
    payload.pop("payload", None)
    return LiveRecord(
        keeper_uid=str(keeper_uid),
        title=title,
        resource_type=resource_type,
        folder_uid=_optional_str(row.get("folder_uid") or row.get("shared_folder_uid")),
        payload=payload,
        marker=marker,
    )


def _marker_from_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    direct = row.get(MARKER_FIELD_LABEL)
    if isinstance(direct, str):
        return decode_marker(direct)
    custom = row.get("custom_fields") or row.get("custom") or row.get("fields")
    if isinstance(custom, Mapping):
        value = custom.get(MARKER_FIELD_LABEL)
        if isinstance(value, str):
            return decode_marker(value)
    if isinstance(custom, list):
        for item in custom:
            if not isinstance(item, Mapping):
                continue
            if item.get("label") != MARKER_FIELD_LABEL and item.get("name") != MARKER_FIELD_LABEL:
                continue
            value = item.get("value")
            if isinstance(value, list) and value:
                value = value[0]
            if isinstance(value, str):
                return decode_marker(value)
    return None


def _edit_command(change: Change) -> str:
    uid = change.keeper_uid
    if not uid:
        raise CapabilityError(
            reason="service update change missing keeper_uid",
            uid_ref=change.uid_ref,
            resource_type=change.resource_type,
            next_action="re-run plan after a fresh discover",
        )
    argv = ["pam", _commander_resource(change.resource_type), "edit", uid]
    for key, value in sorted((change.after or {}).items()):
        if key in _UPDATE_SKIP_KEYS or value is None:
            continue
        argv.append(f"--{key}={_command_value(value)}")
    return shlex.join(argv)


def _delete_command(change: Change) -> str:
    uid = change.keeper_uid
    if not uid:
        raise CapabilityError(
            reason="service delete change missing keeper_uid",
            uid_ref=change.uid_ref,
            resource_type=change.resource_type,
            next_action="re-run plan after a fresh discover",
        )
    return shlex.join(["pam", _commander_resource(change.resource_type), "delete", uid])


def _commander_resource(resource_type: str) -> str:
    return _RESOURCE_COMMANDS.get(resource_type, resource_type)


def _command_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _keeper_uid_from_result(result: Mapping[str, Any]) -> str | None:
    for key in ("keeper_uid", "record_uid", "uid", "resource_uid"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    nested = result.get("result")
    if isinstance(nested, Mapping):
        return _keeper_uid_from_result(nested)
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = ["CommanderServiceProvider"]
