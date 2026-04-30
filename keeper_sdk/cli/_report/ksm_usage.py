"""KSM app usage report from offline mock state or Commander JSON."""

from __future__ import annotations

import io
import json
from collections import Counter
from collections.abc import Mapping
from typing import Any

from rich.console import Console
from rich.table import Table

import keeper_sdk.cli._report.runner as keeper_runner
from keeper_sdk.cli._report.common import prepare_report_rows
from keeper_sdk.core.errors import CapabilityError

_APP_LIST_COMMAND = ["secrets-manager", "app", "list", "--format", "json"]
_KSM_UNAVAILABLE_WARNING = "ksm_unavailable"
_APP_ROW_KEYS = ("applications", "apps", "items", "rows", "data")
_APP_NAME_KEYS = ("name", "app_name", "title", "application_name", "appTitle")
_APP_UID_KEYS = ("app_uid", "uid", "application_uid", "keeper_uid", "appUid")
_APP_UID_REF_KEYS = ("uid_ref", "app_uid_ref", "ref")
_KEY_COUNT_KEYS = (
    "key_count",
    "keys_count",
    "secret_count",
    "record_count",
    "shared_record_count",
    "records_count",
)
_KEY_LIST_KEYS = ("keys", "secrets", "records", "record_uids", "recordUids")
_LAST_ACCESS_KEYS = (
    "last_access_at",
    "last_access",
    "last_used_at",
    "last_used",
    "lastAccess",
)


def run_ksm_usage_report(
    *,
    provider: Any | None = None,
    sanitize_uids: bool = False,
    quiet: bool = False,
    keeper_bin: str | None = None,
    config_file: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Return KSM app usage rows.

    ``provider`` is the offline path used by ``KsmMockProvider``. Without a
    provider, the function reads Commander's KSM app list JSON best-effort.
    """
    if provider is not None:
        apps = _apps_from_provider(provider)
        source = "mock"
    else:
        try:
            raw = keeper_runner.run_keeper_batch(
                _APP_LIST_COMMAND,
                keeper_bin=keeper_bin,
                config_file=config_file,
                password=password,
            )
            apps = _apps_from_commander(raw)
        except CapabilityError:
            return _ksm_unavailable_envelope()
        source = "commander"

    apps = sorted(apps, key=lambda row: (str(row.get("name") or ""), str(row.get("uid_ref") or "")))
    total_keys = sum(int(app.get("key_count") or 0) for app in apps)
    safe_apps = prepare_report_rows(
        apps,
        sanitize_uids=sanitize_uids,
        quiet=quiet,
        fingerprint_keys=("app_uid", "keeper_uid"),
    )
    return {
        "dsk_report_version": 1,
        "command": "ksm-usage",
        "apps": safe_apps,
        "total_keys": total_keys,
        "meta": {
            "source": source,
            "sanitize_uids": sanitize_uids,
        },
    }


def _ksm_unavailable_envelope() -> dict[str, Any]:
    return {"apps": [], "total_keys": 0, "warning": _KSM_UNAVAILABLE_WARNING}


def render_ksm_usage_table(payload: Mapping[str, Any]) -> str:
    """Render a compact KSM app usage table."""
    console = Console(file=io.StringIO(), force_terminal=False, record=True)
    table = Table(title="KSM Usage")
    table.add_column("Application")
    table.add_column("App UID")
    table.add_column("Keys", justify="right")
    table.add_column("Last Access")

    apps = [row for row in payload.get("apps") or [] if isinstance(row, Mapping)]
    for app in apps:
        table.add_row(
            _display(app.get("name")),
            _display(app.get("app_uid")),
            str(app.get("key_count") or 0),
            _display(app.get("last_access_at")),
        )
    console.print(table)
    console.print(f"{len(apps)} apps, {payload.get('total_keys') or 0} keys")
    return console.export_text()


def _apps_from_provider(provider: Any) -> list[dict[str, Any]]:
    if hasattr(provider, "discover_ksm_state"):
        state = provider.discover_ksm_state()
        if not isinstance(state, Mapping):
            raise CapabilityError(
                reason="KSM provider returned non-object state",
                next_action="use a provider with discover_ksm_state() returning KSM blocks",
            )
        return _apps_from_state(state)
    if hasattr(provider, "discover_ksm_apps"):
        apps = provider.discover_ksm_apps()
        if not isinstance(apps, list):
            raise CapabilityError(
                reason="KSM provider returned non-list app rows",
                next_action="use a provider with discover_ksm_apps() returning app rows",
            )
        return [_normalise_app_row(row) for row in apps if isinstance(row, Mapping)]
    raise CapabilityError(
        reason="provider does not expose KSM app discovery",
        next_action="use --provider mock or a Commander-backed KSM provider",
    )


def _apps_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    apps = [row for row in state.get("apps") or [] if isinstance(row, Mapping)]
    shares = [row for row in state.get("record_shares") or [] if isinstance(row, Mapping)]
    share_counts = Counter(str(share.get("app_uid_ref") or "") for share in shares)
    out: list[dict[str, Any]] = []
    for app in apps:
        row = _normalise_app_row(app)
        uid_ref = str(app.get("uid_ref") or "")
        app_uid = str(app.get("keeper_uid") or app.get("app_uid") or app.get("uid") or "")
        app_ref = f"keeper-ksm:apps:{uid_ref}" if uid_ref else ""
        row["key_count"] = (
            share_counts[app_ref]
            + share_counts[uid_ref]
            + share_counts[app_uid]
            + int(row.get("key_count") or 0)
        )
        out.append(row)
    return out


def _apps_from_commander(raw: str) -> list[dict[str, Any]]:
    parsed = _parse_json(raw)
    rows: list[Any]
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        selected_rows = _first_list_value(parsed, _APP_ROW_KEYS)
        if selected_rows is None:
            raise CapabilityError(
                reason="KSM app list JSON object did not contain applications/apps/items/rows/data",
                context={"keys": sorted(str(key) for key in parsed.keys())[:20]},
                next_action="inspect `keeper secrets-manager app list --format json` output",
            )
        rows = selected_rows
    else:
        raise CapabilityError(
            reason="KSM app list JSON was not an array or object",
            context={"sample": str(parsed)[:200]},
            next_action="upgrade Keeper Commander to a compatible version",
        )
    return [_normalise_app_row(row) for row in rows if isinstance(row, Mapping)]


def _parse_json(raw: str) -> Any:
    text = (raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char not in "[{":
                continue
            try:
                parsed, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            return parsed
        raise CapabilityError(
            reason="KSM app list returned non-JSON stdout",
            context={"head": text[:400]},
            next_action="run `keeper secrets-manager app list --format json` manually",
        )


def _normalise_app_row(row: Mapping[str, Any]) -> dict[str, Any]:
    app_uid = _first_value(row, _APP_UID_KEYS)
    uid_ref = _first_value(row, _APP_UID_REF_KEYS)
    name = _first_value(row, _APP_NAME_KEYS) or uid_ref or app_uid or "<unnamed>"
    return {
        "name": str(name),
        "uid_ref": str(uid_ref) if uid_ref is not None else None,
        "app_uid": str(app_uid) if app_uid is not None else None,
        "key_count": _key_count(row),
        "last_access_at": _string_or_none(_first_value(row, _LAST_ACCESS_KEYS)),
    }


def _key_count(row: Mapping[str, Any]) -> int:
    value = _first_value(row, _KEY_COUNT_KEYS)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    for key in _KEY_LIST_KEYS:
        item = row.get(key)
        if isinstance(item, list | tuple | set):
            return len(item)
    return 0


def _first_list_value(data: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return None


def _first_value(data: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _display(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value)
