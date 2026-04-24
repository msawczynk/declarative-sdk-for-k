"""Pure helper functions for :mod:`keeper_sdk.providers.commander_cli`.

These helpers were extracted from ``commander_cli.py`` during the
``sdk-completion`` branch's D-1 partial split (REVIEW.md). They are
intentionally all module-level functions with no dependency on the
``CommanderCliProvider`` class state — moving them out of the main module
shrinks it from 1082 LOC to the provider class itself (~770 LOC) and lets
reviewers navigate the class without scrolling past ~300 LOC of parsers.

Anything stateful (subprocess plumbing, KeeperParams bootstrap, marker
writes, scaffold) stays inside ``commander_cli.py`` for now. A full
per-concern split (subprocess.py, pam_project_in_process.py, scaffold.py,
discover.py, apply.py) remains deferred — see REVIEW.md D-1.
"""

from __future__ import annotations

import json
from typing import Any

from keeper_sdk.core.diff import _DIFF_IGNORED_FIELDS, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker


def _parse_pam_project_args(tail: list[str]) -> dict[str, Any]:
    """Lightweight parser for the argv tail after 'pam project <import|extend>'.

    Recognises: --name/-n, --file/--filename/-f, --config/-c, --dry-run/-d.
    Long forms accept both `--flag value` and `--flag=value`.
    """
    parsed: dict[str, Any] = {"dry_run": False}
    i = 0
    while i < len(tail):
        token = tail[i]
        if token in ("--dry-run", "-d"):
            parsed["dry_run"] = True
            i += 1
            continue
        if "=" in token:
            key, _, value = token.partition("=")
        else:
            key = token
            value = tail[i + 1] if i + 1 < len(tail) else ""
            i += 1
        i += 1
        if key in ("--name", "-n"):
            parsed["name"] = value
        elif key in ("--file", "--filename", "-f"):
            parsed["file"] = value
        elif key in ("--config", "-c"):
            parsed["config"] = value
    return parsed


def _has_existing(changes: list[Any]) -> bool:
    return any(c.kind is ChangeKind.UPDATE for c in changes)


def _uses_reference_existing(manifest: dict[str, Any]) -> bool:
    gateways = manifest.get("gateways")
    if not isinstance(gateways, list):
        return False
    return any(
        isinstance(gateway, dict) and gateway.get("mode") == "reference_existing"
        for gateway in gateways
    )


def _pam_configuration_uid_ref(manifest: dict[str, Any]) -> str | None:
    configs = manifest.get("pam_configurations")
    if not isinstance(configs, list) or not configs:
        return None
    first = configs[0]
    if not isinstance(first, dict):
        return None
    uid_ref = first.get("uid_ref")
    return str(uid_ref) if isinstance(uid_ref, str) and uid_ref.strip() else None


def _payload_for_extend(
    payload: dict[str, Any],
    *,
    resources_folder_name: str,
    users_folder_name: str,
) -> dict[str, Any]:
    extend_payload = {"pam_data": json.loads(json.dumps(payload.get("pam_data") or {}))}
    pam_data = extend_payload["pam_data"]

    for resource in pam_data.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        resource["folder_path"] = resources_folder_name
        for user in resource.get("users") or []:
            if isinstance(user, dict):
                user["folder_path"] = users_folder_name

    for user in pam_data.get("users") or []:
        if isinstance(user, dict):
            user["folder_path"] = users_folder_name
    return extend_payload


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
        "pam_configuration",
        "pam_configuration_uid_ref",
        "shared_folder",
        "users",
        "gateway",
        "gateway_uid_ref",
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
    keeper_uid = (
        item.get("record_uid")
        or item.get("uid")
        or item.get("keeper_uid")
        or listing_entry.get("uid")
    )
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
    for field in item.get("custom") or []:
        if not isinstance(field, dict):
            continue
        payload.update(_canonical_payload_from_field(field))
    return payload


_FIELD_LABEL_ALIASES = {
    "operatingSystem": "operating_system",
    "sslVerification": "ssl_verification",
    "instanceId": "instance_id",
    "instanceName": "instance_name",
    "providerGroup": "provider_group",
    "providerRegion": "provider_region",
}


def _canonical_payload_from_field(field: dict[str, Any]) -> dict[str, Any]:
    field_type = field.get("type")
    values = field.get("value")
    if not field_type or not isinstance(values, list):
        return {}
    if field_type in {"host", "pamHostname"}:
        return _host_payload(values)
    label = field.get("label") or ""
    if not values:
        return {}
    value = values[0] if len(values) == 1 else values
    key = _FIELD_LABEL_ALIASES.get(label) or label or field_type
    if isinstance(value, (str, int, float, bool)):
        return {key: value}
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


def _resource_type_from_get(
    item: dict[str, Any], *, listing_entry: dict[str, Any]
) -> tuple[str | None, bool]:
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
    tail = details[len(prefix) :].strip()
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


__all__ = [
    "_parse_pam_project_args",
    "_has_existing",
    "_uses_reference_existing",
    "_pam_configuration_uid_ref",
    "_payload_for_extend",
    "_field_drift",
    "_port_value",
    "_load_json",
    "_entry_uid_by_name",
    "_record_from_get",
    "_payload_from_get",
    "_canonical_payload_from_field",
    "_host_payload",
    "_resource_type_from_get",
    "_type_from_listing_details",
    "_title_from_item",
    "_kind_from_collection",
    "_extract_marker_field",
    "_FIELD_LABEL_ALIASES",
]
