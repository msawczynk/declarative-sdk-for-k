"""Vault posture summary from Commander ``list-records`` JSON output."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import prepare_report_rows
from keeper_sdk.core.errors import CapabilityError

_COMMAND = "list-records"
_ISSUES = (
    "no_password",
    "weak_password",
    "shared_over_threshold",
    "no_rotation_policy",
    "stale",
)
_UID_KEYS = ("record_uid", "recordUid", "uid", "recordUID")
_TITLE_KEYS = ("title", "name")
_TYPE_KEYS = ("type", "record_type", "recordType")
_PASSWORD_KEYS = ("password", "Password")
_HAS_PASSWORD_KEYS = (
    "has_password",
    "hasPassword",
    "password_present",
    "passwordPresent",
    "hasPasswordField",
)
_WEAK_KEYS = (
    "weak",
    "weak_password",
    "weakPassword",
    "password_weak",
    "passwordWeak",
    "is_weak",
    "isWeak",
    "strength",
    "password_strength",
    "passwordStrength",
    "password_status",
    "passwordStatus",
    "password_score",
    "passwordScore",
    "score",
    "breachwatch_status",
    "breachwatchStatus",
)
_WEAK_SCORE_KEYS = {"password_score", "passwordScore", "score"}
_SHARED_COUNT_KEYS = (
    "shared_user_count",
    "sharedUserCount",
    "share_user_count",
    "shareUserCount",
    "user_share_count",
    "userShareCount",
)
_SHARED_CONTAINER_KEYS = (
    "shared_users",
    "sharedUsers",
    "user_shares",
    "userShares",
    "sharees",
    "shares",
    "permissions",
)
_ROTATION_KEYS = (
    "rotation_policy",
    "rotationPolicy",
    "rotation_settings",
    "rotationSettings",
    "rotation_schedule",
    "rotationSchedule",
    "pam_rotation",
    "pamRotation",
    "record_rotation",
    "recordRotation",
)
_ROTATION_ENABLED_KEYS = (
    "rotation_enabled",
    "rotationEnabled",
    "rotate_on_expiration",
    "rotateOnExpiration",
)
_MODIFIED_KEYS = (
    "modified",
    "modified_time",
    "modifiedTime",
    "last_modified",
    "lastModified",
    "client_modified_time",
    "clientModifiedTime",
    "updated_at",
    "updatedAt",
)
_EMPTY_STRINGS = {"", "-", "none", "null", "n/a", "na"}
_FALSE_STRINGS = _EMPTY_STRINGS | {"false", "off", "disabled", "no", "0"}
_WEAK_STRINGS = {
    "weak",
    "very weak",
    "poor",
    "low",
    "bad",
    "fail",
    "failed",
    "at risk",
    "risk",
    "compromised",
    "breached",
}


def run_vault_health_report(
    *,
    shared_threshold: int,
    stale_days: int,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run Commander ``list-records --format json`` and return posture findings."""
    raw = keeper_runner.run_keeper_batch(
        [_COMMAND, "--format", "json"],
        keeper_bin=keeper_bin,
        config_file=config_file,
        password=password,
    )
    rows = _parse_list_records(raw)
    checked_at = _coerce_utc(now or datetime.now(UTC))
    records = [
        finding
        for finding in (
            _record_finding(
                row,
                shared_threshold=shared_threshold,
                stale_days=stale_days,
                now=checked_at,
            )
            for row in rows
        )
        if finding is not None
    ]
    summary = _build_summary(total_records=len(rows), records=records)
    sanitized_records = prepare_report_rows(
        records,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("record_uid", "shared_folder_uid"),
    )
    return {
        "dsk_report_version": 1,
        "command": "vault-health",
        "summary": summary,
        "records": sanitized_records,
        "meta": {
            "shared_threshold": shared_threshold,
            "stale_days": stale_days,
            "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
            "quiet": quiet,
            "sanitize_uids": sanitize_uids,
        },
    }


def _parse_list_records(raw: str) -> list[dict[str, Any]]:
    text = keeper_runner.extract_json_array_stdout(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CapabilityError(
            reason=f"{_COMMAND} returned non-JSON stdout: {exc}",
            context={"head": (raw or "")[:400]},
            next_action="run `keeper list-records --format json` manually and inspect output",
        ) from exc

    rows: list[Any]
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        maybe_rows = _first_list_value(parsed, ("records", "items", "rows", "data"))
        if maybe_rows is None:
            raise CapabilityError(
                reason=f"{_COMMAND} JSON object did not contain records/items/rows/data",
                context={"keys": sorted(str(k) for k in parsed.keys())[:20]},
                next_action="upgrade Keeper Commander or inspect `keeper list-records --format json`",
            )
        rows = maybe_rows
    else:
        raise CapabilityError(
            reason=f"{_COMMAND} JSON was not an array or object",
            context={"sample": str(parsed)[:200]},
            next_action="upgrade Keeper Commander to a compatible version",
        )

    out: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            out.append(dict(item))
        else:
            out.append({"value": item})
    return out


def _first_list_value(data: Mapping[str, Any], keys: Iterable[str]) -> list[Any] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return None


def _record_finding(
    row: dict[str, Any],
    *,
    shared_threshold: int,
    stale_days: int,
    now: datetime,
) -> dict[str, Any] | None:
    issues: list[str] = []
    if not _has_password(row):
        issues.append("no_password")
    if _has_weak_password_indicator(row):
        issues.append("weak_password")
    shared_user_count = _shared_user_count(row)
    if shared_user_count > shared_threshold:
        issues.append("shared_over_threshold")
    if not _has_rotation_policy(row):
        issues.append("no_rotation_policy")
    modified_at = _modified_at(row)
    if modified_at is not None and now - modified_at > timedelta(days=stale_days):
        issues.append("stale")

    if not issues:
        return None
    return {
        "record_uid": _string_or_empty(_first_value(row, _UID_KEYS)),
        "title": _string_or_empty(_first_value(row, _TITLE_KEYS)),
        "record_type": _string_or_empty(_first_value(row, _TYPE_KEYS)),
        "issues": issues,
        "shared_user_count": shared_user_count,
        "modified_at": modified_at.isoformat().replace("+00:00", "Z") if modified_at else "",
    }


def _build_summary(*, total_records: int, records: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"total_records": total_records, "flagged_records": len(records)}
    summary.update({issue: 0 for issue in _ISSUES})
    for record in records:
        for issue in record.get("issues", []):
            if issue in summary:
                summary[issue] += 1
    return summary


def _has_password(row: Mapping[str, Any]) -> bool:
    for key in _HAS_PASSWORD_KEYS:
        if key in row:
            return _truthy(row[key])
    for key in _PASSWORD_KEYS:
        if key in row:
            return not _is_empty(row[key])
    for field in _iter_field_dicts(row):
        if _field_is_password(field):
            return not _is_empty(field.get("value"))
    return False


def _has_weak_password_indicator(row: Mapping[str, Any]) -> bool:
    for key in _WEAK_KEYS:
        if key in row and _value_indicates_weak(row[key], numeric_score=key in _WEAK_SCORE_KEYS):
            return True
    for field in _iter_field_dicts(row):
        label = _string_or_empty(_first_value(field, ("label", "name", "key", "type")))
        if "strength" in label.casefold() or "weak" in label.casefold():
            if _value_indicates_weak(field.get("value"), numeric_score=True):
                return True
    return False


def _shared_user_count(row: Mapping[str, Any]) -> int:
    for key in _SHARED_COUNT_KEYS:
        value = row.get(key)
        if value is not None:
            return _count_value(value)
    for key in _SHARED_CONTAINER_KEYS:
        value = row.get(key)
        if value is not None:
            return _count_value(value)
    shared = row.get("shared")
    if isinstance(shared, bool):
        return 1 if shared else 0
    if isinstance(shared, str) and shared.strip().casefold() == "true":
        return 1
    return 0


def _has_rotation_policy(row: Mapping[str, Any]) -> bool:
    for key in _ROTATION_ENABLED_KEYS:
        if key in row and _truthy(row[key]):
            return True
    for key in _ROTATION_KEYS:
        if key in row and _rotation_value_enabled(row[key]):
            return True
    return False


def _modified_at(row: Mapping[str, Any]) -> datetime | None:
    for key in _MODIFIED_KEYS:
        parsed = _parse_datetime(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _iter_field_dicts(row: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    for source in _field_sources(row):
        for key in ("fields", "custom", "custom_fields", "customFields"):
            block = source.get(key)
            if not isinstance(block, list):
                continue
            for field in block:
                if isinstance(field, dict):
                    yield field


def _field_sources(row: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    yield row
    for key in ("data", "data_unencrypted", "dataUnencrypted"):
        value = row.get(key)
        if isinstance(value, dict):
            yield value
        elif isinstance(value, str) and value.strip().startswith("{"):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                yield parsed


def _field_is_password(field: Mapping[str, Any]) -> bool:
    field_type = _string_or_empty(field.get("type")).replace("_", "").casefold()
    if field_type == "password":
        return True
    for key in ("label", "name", "key"):
        if "password" in _string_or_empty(field.get(key)).casefold():
            return True
    return False


def _first_value(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _string_or_empty(value: Any) -> str:
    return "" if value is None else str(value)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _EMPTY_STRINGS
    if isinstance(value, list | tuple | set):
        return all(_is_empty(item) for item in value)
    if isinstance(value, dict):
        return not value or all(_is_empty(item) for item in value.values())
    return False


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() not in _FALSE_STRINGS
    if isinstance(value, int | float):
        return value != 0
    return not _is_empty(value)


def _value_indicates_weak(value: Any, *, numeric_score: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().casefold()
        return lower in _WEAK_STRINGS or lower.startswith("weak")
    if isinstance(value, int | float):
        if numeric_score:
            return 0 <= value <= 2 or 0 < value <= 40
        return value != 0
    if isinstance(value, list | tuple | set):
        return any(_value_indicates_weak(item, numeric_score=numeric_score) for item in value)
    if isinstance(value, dict):
        return any(
            _value_indicates_weak(item, numeric_score=numeric_score) for item in value.values()
        )
    return False


def _count_value(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
        return 1 if value.strip().casefold() == "true" else 0
    if isinstance(value, list | tuple | set):
        user_entries = [item for item in value if _looks_like_user_share(item)]
        return len(user_entries) if user_entries else len(value)
    if isinstance(value, dict):
        for key in ("users", "shared_users", "sharedUsers", "members"):
            nested = value.get(key)
            if nested is not None:
                return _count_value(nested)
        return len(value)
    return 0


def _looks_like_user_share(item: Any) -> bool:
    if isinstance(item, str):
        return True
    if not isinstance(item, dict):
        return False
    share_type = _string_or_empty(
        _first_value(item, ("type", "share_type", "shareType", "kind"))
    ).casefold()
    if share_type and "team" in share_type:
        return False
    if share_type and "user" in share_type:
        return True
    return any(key in item for key in ("username", "email", "account_uid", "accountUid"))


def _rotation_value_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() not in _FALSE_STRINGS
    if isinstance(value, list | tuple | set):
        return any(_rotation_value_enabled(item) for item in value)
    if isinstance(value, dict):
        if _truthy(value.get("disabled")) or _truthy(value.get("is_disabled")):
            return False
        for key in ("enabled", "rotation_enabled", "rotationEnabled"):
            if key in value:
                return _truthy(value[key])
        return not _is_empty(value)
    return not _is_empty(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if text.casefold() in _EMPTY_STRINGS:
        return None
    if text.isdigit():
        return _parse_datetime(int(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _coerce_utc(parsed)


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
