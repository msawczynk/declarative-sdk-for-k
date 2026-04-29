"""Commander-backed provider.

Wraps Commander via subprocess for simple commands and direct in-process
command classes for PAM commands that need the logged-in session. This provider
is the production path today: Commander already implements record I/O, rotation
wiring, KSM binding, gateway registration, and share graph, so we reuse it
instead of re-implementing.

Commands used:
    keeper pam project import --file <manifest>.pam_import.json
    keeper pam project extend --file <manifest>.pam_import.json
    keeper ls <folder_uid> --format json
    keeper get <uid> --format json
    keeper rm <uid>
    keeper-vault.v1 (slice 1): in-process ``RecordAddCommand`` (record-add) for
    ``login`` creates; ``RecordEditCommand`` merges manifest drift into existing
    v3 JSON then :meth:`_write_marker` refreshes ownership metadata; same ``ls`` /
    ``get`` discover path filtered to ``login`` rows.
    keeper-vault-sharing.v1 (provider helpers): ``mkdir -uf``, ``mkdir -sf``,
    ``mv --user-folder/--shared-folder``, ``rmdir -f``, ``share-record``,
    ``share-folder``, and ``get <shared_folder_uid> --format json``.

The provider:
    1. Lists the target folder (if configured) and fetches each record.
    2. Decodes ownership markers from the custom field.
    3. Applies PAM plans by writing a temp ``pam_import`` JSON document and
       invoking ``keeper pam project import`` or ``extend``. Applies vault
       slice-1 plans via record-add + marker writes (see :meth:`_apply_vault_plan`).
    4. Deletes records via ``keeper rm <uid>``; ``compute_diff`` restricts
       deletes to records whose ownership marker matches ``MANAGER_NAME``.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from keeper_sdk.core.diff import _DIFF_IGNORED_FIELDS, Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError, CollisionError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    encode_marker,
    serialize_marker,
    utc_timestamp,
)
from keeper_sdk.core.normalize import to_pam_import_json
from keeper_sdk.core.planner import Plan
from keeper_sdk.core.vault_diff import (
    _KEEPER_FILL_RESOURCE_TYPE,
    _KEEPER_FILL_SETTING_RESOURCE_TYPE,
    _KEEPER_FILL_UID_REF,
)
from keeper_sdk.providers._commander_cli_helpers import (
    _entry_uid_by_name,
    _field_drift,
    _has_existing,
    _load_json,
    _merge_rbi_dag_options_into_pam_settings,
    _pam_configuration_uid_ref,
    _parse_pam_project_args,
    _payload_for_extend,
    _record_from_get,
    _uses_reference_existing,
)

ConflictError = CollisionError


def _is_keeper_fill_change(change: Change) -> bool:
    """Detect whether a vault diff Change targets the keeper_fill block.

    Used by ``_apply_vault_plan`` to route create/update through dedicated
    keeper_fill helpers rather than silently using ``_vault_add_login_record``
    (which would drop the keeper_fill payload). See W3-AB schema-honesty slice.
    """
    rt = change.resource_type
    if rt in (_KEEPER_FILL_RESOURCE_TYPE, _KEEPER_FILL_SETTING_RESOURCE_TYPE):
        return True
    uid = change.uid_ref or ""
    return uid == _KEEPER_FILL_UID_REF or uid.startswith(_KEEPER_FILL_UID_REF + ":")


_SILENT_FAIL_COMMANDS = {
    ("pam", "project", "import"),
    ("pam", "project", "extend"),
    ("pam", "connection", "edit"),
    ("pam", "rbi", "edit"),
    ("ls",),
    ("get",),
    ("record-update",),
    ("rm",),
}
_SILENT_FAIL_MARKERS = (
    "Project name is required",
    "No such folder or record",
    "cannot be resolved",
)
_SESSION_EXPIRED_CODE = "session_token_expired"
_ROTATION_APPLY_ENV_VAR = "DSK_EXPERIMENTAL_ROTATION_APPLY"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
# In-process PAM import / marker writes require a floor documented in docs/COMMANDER.md.
_MIN_KEEPERCOMMANDER_VERSION = (17, 2, 13)
_MSP_APPLY_UNSUPPORTED_REASON = (
    "MSP managed-company apply is not implemented on CommanderCliProvider "
    "(Commander: `msp-add` / `msp-update` / `msp-remove`; see docs/COMMANDER.md)"
)
_MSP_CREATE_ONLY_UNSUPPORTED_REASON = (
    "CommanderCliProvider MSP apply only supports managed-company create/update/delete via "
    "`msp-add`, `msp-update`, and `msp-remove`; import marker writes remain unsupported"
)
_MSP_MANAGED_COMPANY_RESOURCE_TYPES = {"managed_company", "managedCompany"}
_MSP_UNLIMITED_SEATS = 1_000_000_000


def _msp_plan_slug_from_product_id(product_id: Any) -> str:
    """Map Commander ``product_id`` (int slug id or string slug) to MSP plan code."""
    try:
        from keepercommander import constants  # type: ignore
    except ImportError:
        return str(product_id) if product_id is not None else ""
    if product_id is None:
        return ""
    if isinstance(product_id, str):
        s = product_id.strip()
        for row in constants.MSP_PLANS:
            if row[1] == s or row[1].lower() == s.lower():
                return str(row[1])
        return s
    if isinstance(product_id, int):
        for row in constants.MSP_PLANS:
            if row[0] == product_id:
                return str(row[1])
    return str(product_id)


def _msp_file_plan_display(file_plan_type: Any) -> str | None:
    if file_plan_type is None or file_plan_type == "":
        return None
    try:
        from keepercommander import constants  # type: ignore
    except ImportError:
        return str(file_plan_type)
    fpt = str(file_plan_type)
    for row in constants.MSP_FILE_PLANS:
        if row[1] == fpt:
            return str(row[2])
    return fpt


def _commander_mc_dict_to_sdk_row(mc: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise one ``params.enterprise['managed_companies']`` row for MSP diff."""
    name = str(mc.get("mc_enterprise_name") or "").strip()
    if not name:
        raise ValueError("managed company missing mc_enterprise_name")
    plan = _msp_plan_slug_from_product_id(mc.get("product_id"))
    if not plan:
        plan = "business"
    seats_raw = int(mc.get("number_of_seats") or 0)
    if seats_raw > 2147483646 or seats_raw < 0:
        seats_raw = -1
    addons_out: list[dict[str, Any]] = []
    for addon in mc.get("add_ons") or []:
        if not isinstance(addon, dict) or addon.get("name") is None:
            continue
        a_seats = int(addon.get("seats") or 0)
        if a_seats > 2147483646 or a_seats < 0:
            a_seats = -1
        addons_out.append({"name": str(addon["name"]), "seats": a_seats})
    addons_out.sort(key=lambda x: str(x["name"]).casefold())
    out: dict[str, Any] = {
        "name": name,
        "plan": plan,
        "seats": seats_raw,
        "file_plan": _msp_file_plan_display(mc.get("file_plan_type")),
        "addons": addons_out,
    }
    eid = mc.get("mc_enterprise_id")
    if eid is not None:
        out["mc_enterprise_id"] = eid
    return out


def _msp_plan_changes(plan: Plan) -> list[Change]:
    ordered = plan.ordered()
    seen = {id(change) for change in ordered}
    return ordered + [change for change in plan.changes if id(change) not in seen]


def _msp_change_name(change: Change) -> str:
    for payload in (change.after, change.before):
        value = payload.get("name")
        if value is not None:
            return str(value)
    return str(change.uid_ref or change.title)


def _msp_commander_seats(value: Any) -> int:
    seats = int(value)
    return -1 if seats >= _MSP_UNLIMITED_SEATS else seats


def _msp_addon_arg(addon: Mapping[str, Any]) -> str:
    name = str(addon["name"])
    seats = _msp_commander_seats(addon.get("seats", 0))
    return f"{name}:{seats}" if seats else name


def _msp_add_command_kwargs(change: Change) -> dict[str, Any]:
    after = change.after
    name = after.get("name") or change.uid_ref or change.title
    if not name:
        raise CapabilityError(
            reason="MSP managed-company create change is missing after.name",
            uid_ref=change.uid_ref,
            resource_type=change.resource_type,
            next_action="rebuild the MSP plan from a valid msp-environment.v1 manifest",
        )
    kwargs: dict[str, Any] = {"name": str(name)}
    if after.get("plan") is not None:
        kwargs["plan"] = str(after["plan"])
    if after.get("seats") is not None:
        kwargs["seats"] = _msp_commander_seats(after["seats"])
    if after.get("file_plan") not in (None, ""):
        kwargs["file_plan"] = str(after["file_plan"])
    if after.get("node") not in (None, ""):
        kwargs["node"] = str(after["node"])
    addons = after.get("addons")
    if isinstance(addons, list):
        addon_args = [_msp_addon_arg(addon) for addon in addons if isinstance(addon, Mapping)]
        if addon_args:
            kwargs["addon"] = addon_args
    return kwargs


def _msp_mc_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("mc_enterprise_id")
    if value in (None, ""):
        return None
    return str(value)


def _msp_target_mc(change: Change, existing: Mapping[str, Any] | None = None) -> str:
    for value in (
        change.keeper_uid,
        _msp_mc_id_from_payload(change.before),
        _msp_mc_id_from_payload(change.after),
        _msp_mc_id_from_payload(existing or {}),
    ):
        if value not in (None, ""):
            return str(value)
    return _msp_change_name(change)


def _msp_same_mc(row: Mapping[str, Any], *, target_id: str | None, target_names: set[str]) -> bool:
    row_id = _msp_mc_id_from_payload(row)
    if target_id is not None and row_id == target_id:
        return True
    row_name = str(row.get("name") or "")
    return row_name.casefold() in target_names


def _msp_find_target(
    live_rows: list[dict[str, Any]],
    change: Change,
    *,
    name: str,
) -> dict[str, Any] | None:
    target_ids = {
        value
        for value in (
            change.keeper_uid,
            _msp_mc_id_from_payload(change.before),
            _msp_mc_id_from_payload(change.after),
        )
        if value not in (None, "")
    }
    if target_ids:
        existing = next(
            (
                row
                for row in live_rows
                if _msp_mc_id_from_payload(row) in {str(value) for value in target_ids}
            ),
            None,
        )
        if existing is not None:
            return existing

    target_names = {
        str(value).casefold()
        for value in (
            change.before.get("name"),
            change.after.get("name"),
            change.uid_ref,
            change.title,
            name,
        )
        if value not in (None, "")
    }
    return next(
        (row for row in live_rows if str(row.get("name") or "").casefold() in target_names),
        None,
    )


def _msp_guard_update_name_collision(
    *,
    live_rows: list[dict[str, Any]],
    change: Change,
    existing: Mapping[str, Any] | None,
    name: str,
) -> None:
    new_name = str(change.after.get("name") or name)
    target_id = _msp_mc_id_from_payload(existing or {}) or change.keeper_uid
    target_names = {
        str(value).casefold()
        for value in (
            (existing or {}).get("name"),
            change.before.get("name"),
            change.uid_ref,
            change.title,
            name,
        )
        if value not in (None, "")
    }
    conflict = next(
        (
            row
            for row in live_rows
            if str(row.get("name") or "").casefold() == new_name.casefold()
            and not _msp_same_mc(row, target_id=target_id, target_names=target_names)
        ),
        None,
    )
    if conflict is None:
        return
    raise ConflictError(
        reason=f"managed company {new_name!r} already exists; refusing update rename",
        uid_ref=change.uid_ref or name,
        resource_type=change.resource_type,
        live_identifier=str(conflict.get("mc_enterprise_id") or conflict.get("name") or new_name),
        next_action="refresh plan from live MSP state or choose a unique managed-company name",
        context={"live": conflict},
    )


def _msp_addons_by_name(addons: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(addons, list):
        return {}
    return {
        str(addon["name"]).casefold(): addon
        for addon in addons
        if isinstance(addon, Mapping) and addon.get("name") is not None
    }


def _msp_update_command_kwargs(
    change: Change,
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    after = change.after
    kwargs: dict[str, Any] = {"mc": _msp_target_mc(change, existing)}
    if after.get("name") not in (None, ""):
        kwargs["name"] = str(after["name"])
    if after.get("plan") is not None:
        kwargs["plan"] = str(after["plan"])
    if after.get("seats") is not None:
        kwargs["seats"] = _msp_commander_seats(after["seats"])
    if after.get("file_plan") not in (None, ""):
        kwargs["file_plan"] = str(after["file_plan"])
    if after.get("node") not in (None, ""):
        kwargs["node"] = str(after["node"])

    before_addons = _msp_addons_by_name(change.before.get("addons"))
    after_addons = _msp_addons_by_name(after.get("addons"))
    add_addon = [
        _msp_addon_arg(addon)
        for key, addon in sorted(after_addons.items())
        if key not in before_addons
        or _msp_commander_seats(before_addons[key].get("seats", 0))
        != _msp_commander_seats(addon.get("seats", 0))
    ]
    remove_addon = [
        str(addon["name"])
        for key, addon in sorted(before_addons.items())
        if key not in after_addons
    ]
    if add_addon:
        kwargs["add_addon"] = add_addon
    if remove_addon:
        kwargs["remove_addon"] = remove_addon
    return kwargs


def _semver_tuple_at_least(installed: tuple[int, ...], minimum: tuple[int, ...]) -> bool:
    span = max(len(installed), len(minimum))
    for i in range(span):
        a = installed[i] if i < len(installed) else 0
        b = minimum[i] if i < len(minimum) else 0
        if a > b:
            return True
        if a < b:
            return False
    return True


def _keepercommander_installed_tuple() -> tuple[int, ...]:
    from importlib.metadata import PackageNotFoundError, version

    try:
        raw = version("keepercommander")
    except PackageNotFoundError:
        return ()
    parts: list[int] = []
    for segment in raw.strip().split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _commander_on_off(value: bool) -> str:
    return "on" if value else "off"


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _ensure_keepercommander_version_for_apply() -> None:
    installed = _keepercommander_installed_tuple()
    if not installed:
        raise CapabilityError(
            reason="keepercommander Python package is not installed",
            next_action="pip install 'keepercommander>=17.2.13,<18'",
        )
    if not _semver_tuple_at_least(installed, _MIN_KEEPERCOMMANDER_VERSION):
        iv = ".".join(str(x) for x in installed)
        mv = ".".join(str(x) for x in _MIN_KEEPERCOMMANDER_VERSION)
        raise CapabilityError(
            reason=(
                f"keepercommander {iv} is below the minimum {mv} required for "
                "CommanderCliProvider in-process apply paths"
            ),
            next_action=(
                "upgrade with pip install -U 'keepercommander>=17.2.13,<18' "
                "and read docs/COMMANDER.md for the pin rationale"
            ),
            context={"installed": installed, "required": _MIN_KEEPERCOMMANDER_VERSION},
        )


def _manifest_source_is_vault(source: Any) -> bool:
    """True when the provider was constructed with a ``keeper-vault.v1`` document."""
    if source is None:
        return False
    if hasattr(source, "model_dump"):
        data = source.model_dump(mode="python", exclude_none=True, by_alias=True)
    elif isinstance(source, dict):
        data = source
    else:
        return False
    return data.get("schema") == "keeper-vault.v1"


def _manifest_source_is_sharing(source: Any) -> bool:
    """True when the provider was constructed with a ``keeper-vault-sharing.v1`` document."""
    if source is None:
        return False
    if hasattr(source, "model_dump"):
        data = source.model_dump(mode="python", exclude_none=True, by_alias=True)
    elif isinstance(source, dict):
        data = source
    else:
        return False
    return data.get("schema") == "keeper-vault-sharing.v1"


_SHARING_RESOURCE_TYPES = {
    "sharing_folder",
    "sharing_shared_folder",
    "sharing_record_share",
    "sharing_share_folder",
}
_VAULT_SHARED_FOLDER_RESOURCE_TYPE = "shared_folder"
_SHARING_PAYLOAD_FIELD_LABEL = "keeper_declarative_payload"
_SHARING_MARKER_TITLE_PREFIX = "DSK sharing marker"


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
        self.last_resolved_users_folder_uid: str | None = None
        self._config = config_file or os.environ.get("KEEPER_CONFIG")
        # Commander's persistent-login still needs the master password on
        # subprocess invocation to unlock the local key; honor --batch-mode by
        # sourcing it from constructor or KEEPER_PASSWORD rather than prompting.
        self._password = keeper_password or os.environ.get("KEEPER_PASSWORD")
        self._manifest_source = manifest_source or {}
        self._manifest_name = self._manifest_name_from_source()
        # In-process Commander session — lazily established the first time a
        # subcommand can't run reliably via subprocess (e.g. `pam project
        # import` / `extend` hit persistent-login re-auth prompts in batch
        # mode). Params are cached for
        # the lifetime of the provider.
        self._keeper_params: Any | None = None
        self._keeper_login_attempted = False
        self._ksm_app_rows_cache: list[dict[str, str]] | None = None

        if not shutil.which(self._bin):
            raise CapabilityError(
                reason=f"keeper CLI not found on PATH (looked up '{self._bin}')",
                next_action="install Keeper Commander or set KEEPER_BIN",
            )

    def _manifest_has_resource_entries(self) -> bool:
        """True when ``manifest_source`` includes a non-empty ``resources`` list."""
        ms = self._manifest_source
        if not isinstance(ms, dict):
            return False
        resources = ms.get("resources")
        return isinstance(resources, list) and bool(resources)

    # ------------------------------------------------------------------

    def discover(self) -> list[LiveRecord]:
        if _manifest_source_is_sharing(self._manifest_source):
            return self._discover_sharing_rows()

        folder_uids = self._discover_folder_uids()
        if not folder_uids:
            raise CapabilityError(
                reason=(
                    "CommanderCliProvider has no folder_uid for discover(); "
                    "pass an explicit folder_uid or run apply_plan() first so "
                    "the provider can resolve the project Resources folder"
                ),
                next_action="pass --folder-uid (or KEEPER_DECLARATIVE_FOLDER), or call apply_plan() first",
            )

        records: list[LiveRecord] = []
        seen_uids: set[str] = set()
        for folder_uid in folder_uids:
            payload = self._run_cmd(["ls", folder_uid, "--format", "json"])
            entries = _load_json(payload, command="ls --format json")
            if not isinstance(entries, list):
                raise CapabilityError(
                    reason="Commander returned non-array JSON from `ls --format json`"
                )
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("type") != "record":
                    continue
                keeper_uid = entry.get("uid")
                if not keeper_uid:
                    continue
                keeper_uid = str(keeper_uid)
                if keeper_uid in seen_uids:
                    continue
                seen_uids.add(keeper_uid)
                listing_entry = dict(entry)
                listing_entry.setdefault("folder_uid", folder_uid)
                item_payload = self._run_cmd(["get", keeper_uid, "--format", "json"])
                item = _load_json(item_payload, command="get --format json")
                if not isinstance(item, dict):
                    raise CapabilityError(
                        reason="Commander returned non-object JSON from `get --format json`"
                    )
                record = _record_from_get(item, listing_entry=listing_entry)
                if record is not None:
                    records.append(record)
        if _manifest_source_is_vault(self._manifest_source):
            records = [r for r in records if r.resource_type == "login"]
        elif (config_record := self._synthetic_reference_configuration_record()) is not None:
            records.append(config_record)
        if any(r.resource_type == "pamRemoteBrowser" for r in records):
            if self._keeper_params is None and self._manifest_has_resource_entries():
                try:
                    self._get_keeper_params()
                except CapabilityError:
                    # Subprocess-only discover remains valid; TunnelDAG merge is best-effort.
                    pass
        if self._keeper_params is not None:
            self._enrich_pam_remote_browser_dag_options(records)
        self._enrich_pam_user_rotation_settings(records)
        return records

    def discover_managed_companies(self) -> list[dict[str, Any]]:
        """Load managed companies via in-process ``api.query_enterprise`` (MSP admin)."""
        try:
            from keepercommander import api  # type: ignore
        except ImportError as exc:
            raise CapabilityError(
                reason=f"MSP discover requires keepercommander: {exc}",
                next_action="pip install 'keepercommander>=17.2.13,<18'",
            ) from exc

        def _run_discover() -> list[dict[str, Any]]:
            params = self._get_keeper_params()
            api.query_enterprise(params)
            ent = getattr(params, "enterprise", None) or {}
            raw = ent.get("managed_companies")
            if not isinstance(raw, list):
                return []
            rows: list[dict[str, Any]] = []
            for mc in raw:
                if not isinstance(mc, dict):
                    continue
                try:
                    rows.append(_commander_mc_dict_to_sdk_row(mc))
                except (KeyError, TypeError, ValueError):
                    continue
            rows.sort(key=lambda r: str(r["name"]).casefold())
            return rows

        try:
            return self._with_keeper_session_refresh(_run_discover)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"MSP managed-company discover failed: {type(exc).__name__}: {exc}",
                next_action="ensure MSP admin session; run `keeper msp-down` then retry",
            ) from exc

    def _resolve_pam_configuration_keeper_uid(
        self, live: LiveRecord, records: list[LiveRecord]
    ) -> str | None:
        """Resolve manifest ``pam_configuration_uid_ref`` to a live pam_configuration UID."""
        marker = live.marker or {}
        uid_ref = marker.get("uid_ref")
        if not isinstance(uid_ref, str) or not uid_ref.strip():
            return None
        ms = self._manifest_source
        if not isinstance(ms, dict):
            return None
        pam_cfg_ref: str | None = None
        for res in ms.get("resources") or []:
            if isinstance(res, dict) and res.get("uid_ref") == uid_ref:
                pref = res.get("pam_configuration_uid_ref")
                if isinstance(pref, str) and pref.strip():
                    pam_cfg_ref = pref.strip()
                break
        if not pam_cfg_ref:
            return None
        for lr in records:
            if lr.resource_type != "pam_configuration":
                continue
            m = lr.marker or {}
            if m.get("uid_ref") == pam_cfg_ref:
                return str(lr.keeper_uid)
        return None

    def _enrich_pam_remote_browser_dag_options(self, records: list[LiveRecord]) -> None:
        """Merge DAG ``allowedSettings`` into discovered RBI ``pam_settings.options``.

        Commander's ``pam rbi edit --remote-browser-isolation`` persists the RBI
        toggle on the resource vertex as ``allowedSettings.connections``; session
        recording uses ``allowedSettings.sessionRecording``. When an in-process
        ``KeeperParams`` session exists (for example after apply), map those
        tri-states back onto manifest-shaped ``pam_settings.options`` so smoke
        verify and re-plan can see post-tuning state without direct DAG writes
        from the SDK. :meth:`discover` may call :meth:`_get_keeper_params` once
        when RBI records are present and ``manifest_source`` lists resources so
        ``pam_configuration_uid_ref`` can resolve for TunnelDAG.
        """
        try:
            from keepercommander.commands.tunnel.port_forward.tunnel_helpers import (  # type: ignore
                get_keeper_tokens,
            )
            from keepercommander.commands.tunnel.port_forward.TunnelGraph import (  # type: ignore
                TunnelDAG,
            )
        except ImportError:
            return
        if self._keeper_params is None:
            return
        params = self._keeper_params
        encrypted_session_token, encrypted_transmission_key, transmission_key = get_keeper_tokens(
            params
        )
        tdag_cache: dict[str, Any] = {}
        for live in records:
            if live.resource_type != "pamRemoteBrowser":
                continue
            cfg_uid = self._resolve_pam_configuration_keeper_uid(live, records)
            if not cfg_uid:
                continue
            if cfg_uid not in tdag_cache:
                tdag_cache[cfg_uid] = TunnelDAG(
                    params,
                    encrypted_session_token,
                    encrypted_transmission_key,
                    cfg_uid,
                    transmission_key=transmission_key,
                )
            tdag = tdag_cache[cfg_uid]
            if tdag is None or not getattr(tdag.linking_dag, "has_graph", False):
                continue
            rid = str(live.keeper_uid)
            connections = tdag.get_resource_setting(rid, "allowedSettings", "connections")
            session_rec = tdag.get_resource_setting(rid, "allowedSettings", "sessionRecording")
            ps = live.payload.setdefault("pam_settings", {})
            _merge_rbi_dag_options_into_pam_settings(
                ps, connections=connections, session_recording=session_rec
            )

    def _enrich_pam_user_rotation_settings(self, records: list[LiveRecord]) -> None:
        """Attach Commander rotation readback to discovered nested ``pamUser`` rows."""
        source = _manifest_source_dict(self._manifest_source)
        targets = _nested_rotation_user_targets(source)
        if not targets.refs and not targets.titles:
            return

        for live in records:
            if live.resource_type != "pamUser":
                continue
            marker_ref = None
            if isinstance(live.marker, dict):
                marker_ref = live.marker.get("uid_ref")
            if marker_ref not in targets.refs and live.title not in targets.titles:
                continue
            rotation_settings = self._get_pam_rotation_state(str(live.keeper_uid))
            if rotation_settings:
                live.payload["rotation_settings"] = rotation_settings

    def _get_pam_rotation_state(self, uid: str) -> dict[str, Any]:
        raw = self._run_cmd(["pam", "rotation", "list", "--record-uid", uid, "--format", "json"])
        data = _load_json(raw, command="pam rotation list --record-uid <uid> --format json")
        return _rotation_settings_from_readback(data, uid=uid)

    def unsupported_capabilities(self, manifest: Any = None) -> list[str]:
        """Enumerate manifest-declared capabilities this provider cannot drive.

        Called by the CLI at plan / dry-run / apply time. Each item becomes a
        CONFLICT row in the plan so ``plan == apply --dry-run == apply``
        (DELIVERY_PLAN.md L94). Previously this ran only inside ``apply_plan``
        as a late-apply guard, producing green plans followed by red applies
        for the same input — see REVIEW.md "Update — second pass / D-4".

        ``manifest`` argument is accepted for protocol parity; the provider
        introspects its own ``self._manifest_source`` in practice.
        """
        source = manifest if manifest is not None else self._manifest_source
        return _detect_unsupported_capabilities(
            source,
            allow_nested_rotation=_rotation_apply_is_enabled(),
        )

    def check_tenant_bindings(self, manifest: Any = None) -> list[str]:
        """Stage-5 online checks: verify every declared binding resolves.

        For each ``reference_existing`` gateway, confirm a live gateway with
        that name exists. For each PAM configuration declared in the manifest,
        confirm a live PAM configuration with the same title resolves and
        carries a valid ``shared_folder_uid`` + ``gateway_uid`` pairing.
        When a ``gateway_uid_ref`` is declared on a PAM configuration, verify
        the live config is actually paired with that gateway. When a gateway
        declares ``ksm_application_name``, verify the tenant's bound KSM app
        matches it or report that the CLI output cannot prove the binding.

        Each returned string is a human-readable binding failure ready for
        ``click.echo(..., err=True)`` and maps 1:1 to a stage-5 violation
        documented in ``docs/VALIDATION_STAGES.md``. Returning ``[]`` means
        stage-5 passed.

        Accepts either the typed :class:`Manifest` (preferred; used by the
        CLI) or the raw manifest dict (for SDK callers bypassing typed
        loading). One round-trip to ``pam gateway list`` + ``pam config list``
        per call; no caching — validate is short-lived.
        """

        def _as_list(value: Any, attr: str) -> list[Any]:
            if value is None:
                return []
            if hasattr(value, attr):
                return list(getattr(value, attr))
            if isinstance(value, dict):
                return list(value.get(attr) or [])
            return []

        source: Any = manifest if manifest is not None else self._manifest_source
        gateways = _as_list(source, "gateways")
        pam_configs = _as_list(source, "pam_configurations")

        def _get(item: Any, key: str) -> Any:
            if hasattr(item, key):
                return getattr(item, key)
            if isinstance(item, dict):
                return item.get(key)
            return None

        if not gateways and not pam_configs:
            return []

        try:
            gateway_rows = self._pam_gateway_rows()
        except (CapabilityError, OSError) as exc:
            return [f"could not list tenant gateways: {exc}"]
        try:
            config_rows = self._pam_config_rows()
        except (CapabilityError, OSError) as exc:
            return [f"could not list tenant PAM configurations: {exc}"]

        live_gateways_by_name: dict[str, dict[str, str]] = {
            row["gateway_name"]: row for row in gateway_rows if row.get("gateway_name")
        }
        live_configs_by_title: dict[str, dict[str, str]] = {
            row["config_name"]: row for row in config_rows if row.get("config_name")
        }

        gateway_uid_by_ref: dict[str, str] = {}
        issues: list[str] = []

        for gateway in gateways:
            mode = _get(gateway, "mode") or "reference_existing"
            name = _get(gateway, "name") or ""
            uid_ref = _get(gateway, "uid_ref") or ""
            if mode != "reference_existing":
                continue
            row = live_gateways_by_name.get(name)
            if row is None:
                issues.append(
                    f"gateway '{name}' (uid_ref={uid_ref}) not found on tenant; "
                    "check the enterprise's `pam gateway list --format json` output"
                )
                continue
            gateway_uid_by_ref[uid_ref] = row["gateway_uid"]
            declared_app = _get(gateway, "ksm_application_name")
            if declared_app:
                actual_app, binding_issue = self._gateway_bound_app_name(row)
                if actual_app and declared_app != actual_app:
                    issues.append(
                        f"gateway '{name}' declares ksm_application_name='{declared_app}' "
                        f"but tenant has it bound to '{actual_app}'"
                    )
                elif binding_issue:
                    issues.append(
                        f"gateway '{name}' declares ksm_application_name='{declared_app}' "
                        f"but the tenant binding could not be verified: {binding_issue}"
                    )

        for config in pam_configs:
            title = _get(config, "title")
            uid_ref = _get(config, "uid_ref") or ""
            if not title:
                continue
            row = live_configs_by_title.get(title)
            if row is None:
                issues.append(
                    f"pam_configuration '{title}' (uid_ref={uid_ref}) not found on tenant; "
                    "declare a matching title or create the configuration in Keeper first"
                )
                continue
            if not row.get("shared_folder_uid"):
                issues.append(
                    f"pam_configuration '{title}' has no shared_folder on tenant — "
                    "apply cannot write resources without a bound shared folder"
                )
            gateway_ref = _get(config, "gateway_uid_ref")
            if gateway_ref:
                expected_gateway_uid = gateway_uid_by_ref.get(gateway_ref)
                actual_gateway_uid = row.get("gateway_uid") or ""
                if (
                    expected_gateway_uid
                    and actual_gateway_uid
                    and expected_gateway_uid != actual_gateway_uid
                ):
                    issues.append(
                        f"pam_configuration '{title}' declares gateway_uid_ref='{gateway_ref}' "
                        f"(uid={expected_gateway_uid}) but tenant pairs it with gateway uid "
                        f"'{actual_gateway_uid}'"
                    )

        return issues

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        if _manifest_source_is_vault(self._manifest_source):
            return self._apply_vault_plan(plan, dry_run=dry_run)
        if _manifest_source_is_sharing(self._manifest_source):
            return self._apply_sharing_plan(plan, dry_run=dry_run)
        # Last-line defence — CLI should have surfaced these as conflicts
        # already (see unsupported_capabilities above). If an SDK caller
        # bypasses the CLI and hands us a plan directly, we still refuse.
        hits = _detect_unsupported_capabilities(
            self._manifest_source,
            allow_nested_rotation=_rotation_apply_is_enabled(),
        )
        if hits:
            raise CapabilityError(
                reason="manifest declares capabilities the CommanderCliProvider does not implement yet: "
                + "; ".join(hits),
                next_action=(
                    "remove the declarations, or drive the Commander hook manually before "
                    "re-running apply. See REVIEW.md D-4."
                ),
            )

        _ensure_keepercommander_version_for_apply()

        outcomes: list[ApplyOutcome] = []
        creates_updates = [
            c for c in plan.ordered() if c.kind in (ChangeKind.CREATE, ChangeKind.UPDATE)
        ]
        deletes = plan.deletes

        if creates_updates:
            rotation_preview_argvs = (
                _preview_rotation_argvs_by_ref(self._manifest_source)
                if dry_run and _rotation_apply_is_enabled()
                else {}
            )
            payload = to_pam_import_json(self._manifest_source)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
                cmd = ["pam", "project", "extend" if _has_existing(creates_updates) else "import"]
                synthetic_config = None
                if _uses_reference_existing(self._manifest_source):
                    synthetic_config = self._resolve_reference_configuration(payload)
                    if not dry_run:
                        scaffold = self._ensure_reference_project_scaffold(
                            project_name=plan.manifest_name,
                            gateway_app_uid=synthetic_config["app_uid"],
                        )
                        # Scaffold uses subprocess `keeper` while earlier stage-5
                        # work may have warmed in-process KeeperParams. Idle or
                        # alternate sessions can leave cached params stale for the
                        # graph-heavy `pam project extend` call (session_token_expired).
                        self._invalidate_keeper_params()
                        self._folder_uid = scaffold["resources_uid"]
                        self.last_resolved_folder_uid = scaffold["resources_uid"]
                        self.last_resolved_users_folder_uid = scaffold["users_uid"]
                        payload = _payload_for_extend(
                            payload,
                            resources_folder_name=scaffold["resources_name"],
                            users_folder_name=scaffold["users_name"],
                        )
                    else:
                        payload = _payload_for_extend(
                            payload,
                            resources_folder_name=f"{plan.manifest_name} - Resources",
                            users_folder_name=f"{plan.manifest_name} - Users",
                        )
                    cmd = [
                        "pam",
                        "project",
                        "extend",
                        "--config",
                        synthetic_config["config_name"],
                        "--file",
                    ]
                json.dump(payload, handle, indent=2)
                temp_path = Path(handle.name)
            try:
                if cmd[:3] == ["pam", "project", "import"]:
                    cmd += ["--file", str(temp_path)]
                    cmd += ["--name", plan.manifest_name]
                else:
                    cmd.append(str(temp_path))
                if dry_run:
                    cmd.append("--dry-run")
                self._run_cmd(cmd)
                if not dry_run and not synthetic_config:
                    self._resolve_project_resources_folder(plan.manifest_name)
                for change in creates_updates:
                    keeper_uid = ""
                    if synthetic_config and change.resource_type == "pam_configuration":
                        keeper_uid = synthetic_config["config_uid"]
                    details: dict[str, Any] = {"dry_run": dry_run}
                    if dry_run:
                        preview_argvs = _preview_post_import_tuning_argvs(
                            change, self._manifest_source
                        )
                        if preview_argvs:
                            details["post_import_tuning_argvs"] = preview_argvs
                            details["post_import_tuning_dry_run"] = True
                        rotation_argvs = rotation_preview_argvs.get(change.uid_ref or change.title)
                        if rotation_argvs:
                            details["rotation_argvs"] = rotation_argvs
                            details["rotation_dry_run"] = True
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid or change.keeper_uid or "",
                            action=change.kind.value,
                            details=details,
                        )
                    )
            finally:
                temp_path.unlink(missing_ok=True)

            if not dry_run:
                try:
                    live_records = self.discover()
                except CapabilityError as exc:
                    raise CapabilityError(
                        reason=f"discover() after pam import/extend failed: {exc.reason}",
                        next_action=exc.next_action,
                        context={**exc.context, "partial_outcomes": list(outcomes)},
                    ) from exc
                live_by_key, live_by_title = _index_live_records_for_title_matching(live_records)

                now = utc_timestamp()
                # outcomes is built by iterating creates_updates in the same
                # order above, so lengths must match — strict=True turns any
                # future drift into a loud failure rather than a silent
                # mis-association of markers to changes.
                for change, outcome in zip(creates_updates, outcomes, strict=True):
                    try:
                        if synthetic_config and change.resource_type == "pam_configuration":
                            outcome.details.update(
                                {
                                    "marker_written": True,
                                    "keeper_uid": synthetic_config["config_uid"],
                                    "verified": True,
                                    "reused_existing": True,
                                }
                            )
                            continue
                        exact_matches = live_by_key.get((change.resource_type, change.title), [])
                        matches = exact_matches or _live_matches_by_identity(
                            live_by_key=live_by_key,
                            live_by_title=live_by_title,
                            resource_type=change.resource_type,
                            title=change.title,
                        )
                        if len(matches) > 1:
                            match_label = (
                                f"{change.resource_type} records" if exact_matches else "records"
                            )
                            raise CollisionError(
                                reason=(
                                    f"live tenant has {len(matches)} {match_label} titled "
                                    f"'{change.title}' after apply"
                                ),
                                uid_ref=change.uid_ref,
                                resource_type=change.resource_type,
                                next_action=(
                                    "rename duplicates or add ownership markers so matching "
                                    "is unambiguous"
                                ),
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
                        post_import_argvs = _resolve_post_import_tuning_argvs(
                            self._manifest_source,
                            plan=plan,
                            live_records=live_records,
                            changes=[change],
                        ).get(change.uid_ref or "", [])
                        for argv in post_import_argvs:
                            self._run_cmd(argv)
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
                        if post_import_argvs:
                            outcome.details["post_import_tuning_argvs"] = post_import_argvs
                            outcome.details["post_import_tuning_executed"] = True
                        drift = _field_drift(change.after or {}, live.payload)
                        if drift:
                            outcome.details["field_drift"] = drift
                        else:
                            outcome.details["verified"] = True
                    except CapabilityError as exc:
                        outcome.details["apply_failed"] = True
                        outcome.details["apply_failure_reason"] = exc.reason
                        if exc.next_action:
                            outcome.details["apply_failure_next_action"] = exc.next_action
                        raise CapabilityError(
                            reason=(
                                f"apply stopped mid-batch while processing "
                                f"{change.resource_type} uid_ref={change.uid_ref!r}: {exc.reason}"
                            ),
                            uid_ref=change.uid_ref,
                            resource_type=change.resource_type,
                            next_action=exc.next_action,
                            context={**exc.context, "partial_outcomes": list(outcomes)},
                        ) from exc

                try:
                    outcomes.extend(self._apply_rotation_settings(plan, live_records))
                except CapabilityError as exc:
                    raise CapabilityError(
                        reason=f"rotation apply failed after resource writes: {exc.reason}",
                        next_action=exc.next_action,
                        context={**exc.context, "partial_outcomes": list(outcomes)},
                    ) from exc

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
                self._run_cmd(["rm", "--force", change.keeper_uid])
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

    def apply_msp_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        changes = _msp_plan_changes(plan)
        if not changes:
            raise CapabilityError(_MSP_APPLY_UNSUPPORTED_REASON)

        unsupported = [
            change
            for change in changes
            if change.resource_type not in _MSP_MANAGED_COMPANY_RESOURCE_TYPES
        ]
        if unsupported:
            first = unsupported[0]
            raise CapabilityError(
                reason=_MSP_CREATE_ONLY_UNSUPPORTED_REASON,
                uid_ref=first.uid_ref,
                resource_type=first.resource_type,
                next_action=(
                    "apply only managed_company create/update/delete rows with Commander; "
                    "use mock provider for unsupported MSP family rows"
                ),
            )

        _ensure_keepercommander_version_for_apply()
        outcomes: list[ApplyOutcome] = []
        for change in changes:
            name = _msp_change_name(change)

            if change.kind is ChangeKind.CONFLICT:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or name,
                        keeper_uid=change.keeper_uid or "",
                        action="conflict",
                        details={"reason": change.reason or ""},
                    )
                )
                continue

            if change.kind not in (ChangeKind.CREATE, ChangeKind.UPDATE, ChangeKind.DELETE):
                details: dict[str, Any] = {"dry_run": dry_run}
                if change.reason is not None:
                    details["reason"] = change.reason
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or name,
                        keeper_uid=change.keeper_uid or "",
                        action="noop",
                        details=details,
                    )
                )
                continue

            live_rows = self.discover_managed_companies()
            existing = _msp_find_target(live_rows, change, name=name)

            if change.kind is ChangeKind.CREATE:
                duplicate = next(
                    (
                        row
                        for row in live_rows
                        if str(row.get("name", "")).casefold() == name.casefold()
                    ),
                    None,
                )
                if duplicate is not None:
                    raise ConflictError(
                        reason=f"managed company {name!r} already exists; refusing create",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        live_identifier=str(
                            duplicate.get("mc_enterprise_id") or duplicate.get("name") or name
                        ),
                        next_action="refresh plan from live MSP state or rename the managed company",
                        context={"live": duplicate},
                    )

                kwargs = _msp_add_command_kwargs(change)
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or name,
                            keeper_uid="",
                            action="create",
                            details={"dry_run": True, "kwargs": kwargs},
                        )
                    )
                    continue

                try:
                    from keepercommander.commands.msp import (
                        MSPAddCommand,  # type: ignore
                    )
                except (ImportError, AttributeError) as exc:
                    raise CapabilityError(
                        reason=f"Commander MSPAddCommand is unavailable: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action="upgrade keepercommander to a version that provides keepercommander.commands.msp.MSPAddCommand",
                    ) from exc

                def _run_create() -> Any:
                    params = self._get_keeper_params()
                    command = MSPAddCommand()
                    if not hasattr(command, "execute"):
                        raise CapabilityError(
                            reason="Commander MSPAddCommand has no execute(params, **kwargs) API",
                            uid_ref=change.uid_ref or name,
                            resource_type=change.resource_type,
                            next_action=(
                                "need MSPAddCommand.execute(params, name, plan, seats, "
                                "file_plan, addon, node)"
                            ),
                        )
                    return command.execute(params, **kwargs)

                try:
                    mc_id = self._with_keeper_session_refresh(_run_create)
                except CapabilityError:
                    raise
                except Exception as exc:
                    raise CapabilityError(
                        reason=f"MSP managed-company create failed: {type(exc).__name__}: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action=(
                            "verify MSP admin permissions, plan/file_plan/addon permits, "
                            "and root node access"
                        ),
                    ) from exc

                if mc_id is None:
                    raise CapabilityError(
                        reason="Commander MSPAddCommand returned no managed-company id",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action=(
                            "inspect Commander warnings for invalid plan/file_plan/addon permits "
                            "or missing MSP root node"
                        ),
                    )
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or name,
                        keeper_uid=str(mc_id),
                        action="create",
                        details={"dry_run": False, "mc_enterprise_id": mc_id, "kwargs": kwargs},
                    )
                )

            elif change.kind is ChangeKind.UPDATE:
                _msp_guard_update_name_collision(
                    live_rows=live_rows,
                    change=change,
                    existing=existing,
                    name=name,
                )
                kwargs = _msp_update_command_kwargs(change, existing)
                mc_id = _msp_target_mc(change, existing)
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or name,
                            keeper_uid=mc_id,
                            action="update",
                            details={"dry_run": True, "kwargs": kwargs},
                        )
                    )
                    continue

                try:
                    from keepercommander.commands.msp import (
                        MSPUpdateCommand,  # type: ignore
                    )
                except (ImportError, AttributeError) as exc:
                    raise CapabilityError(
                        reason=f"Commander MSPUpdateCommand is unavailable: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action="upgrade keepercommander to a version that provides keepercommander.commands.msp.MSPUpdateCommand",
                    ) from exc

                def _run_update() -> Any:
                    params = self._get_keeper_params()
                    command = MSPUpdateCommand()
                    if not hasattr(command, "execute"):
                        raise CapabilityError(
                            reason="Commander MSPUpdateCommand has no execute(params, **kwargs) API",
                            uid_ref=change.uid_ref or name,
                            resource_type=change.resource_type,
                            next_action=(
                                "need MSPUpdateCommand.execute(params, mc, name, plan, seats, "
                                "file_plan, add_addon, remove_addon, node)"
                            ),
                        )
                    return command.execute(params, **kwargs)

                try:
                    self._with_keeper_session_refresh(_run_update)
                except CapabilityError:
                    raise
                except Exception as exc:
                    raise CapabilityError(
                        reason=f"MSP managed-company update failed: {type(exc).__name__}: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action=(
                            "verify MSP admin permissions, target managed-company id/name, "
                            "and plan/file_plan/addon permits"
                        ),
                    ) from exc

                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or name,
                        keeper_uid=mc_id,
                        action="update",
                        details={"dry_run": False, "mc_enterprise_id": mc_id, "kwargs": kwargs},
                    )
                )

            elif change.kind is ChangeKind.DELETE:
                if getattr(plan, "allow_delete", True) is False:
                    raise CapabilityError(
                        reason="MSP managed-company delete requires allow_delete=True",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action="rerun plan/apply with --allow-delete before deleting MSP managed companies",
                    )

                kwargs = {"mc": _msp_target_mc(change, existing), "force": True}
                mc_id = str(kwargs["mc"])
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or name,
                            keeper_uid=mc_id,
                            action="delete",
                            details={"dry_run": True, "kwargs": kwargs},
                        )
                    )
                    continue

                try:
                    from keepercommander.commands.msp import (
                        MSPRemoveCommand,  # type: ignore
                    )
                except (ImportError, AttributeError) as exc:
                    raise CapabilityError(
                        reason=f"Commander MSPRemoveCommand is unavailable: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action="upgrade keepercommander to a version that provides keepercommander.commands.msp.MSPRemoveCommand",
                    ) from exc

                def _run_delete() -> Any:
                    params = self._get_keeper_params()
                    command = MSPRemoveCommand()
                    if not hasattr(command, "execute"):
                        raise CapabilityError(
                            reason="Commander MSPRemoveCommand has no execute(params, **kwargs) API",
                            uid_ref=change.uid_ref or name,
                            resource_type=change.resource_type,
                            next_action="need MSPRemoveCommand.execute(params, mc, force)",
                        )
                    return command.execute(params, **kwargs)

                try:
                    self._with_keeper_session_refresh(_run_delete)
                except CapabilityError:
                    raise
                except Exception as exc:
                    raise CapabilityError(
                        reason=f"MSP managed-company delete failed: {type(exc).__name__}: {exc}",
                        uid_ref=change.uid_ref or name,
                        resource_type=change.resource_type,
                        next_action=(
                            "verify MSP admin permissions and target managed-company id/name "
                            "before retrying with --allow-delete"
                        ),
                    ) from exc

                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or name,
                        keeper_uid=mc_id,
                        action="delete",
                        details={"dry_run": False, "mc_enterprise_id": mc_id, "kwargs": kwargs},
                    )
                )
        return outcomes

    def _apply_vault_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Apply ``keeper-vault.v1`` slice-1 (``login``) via record-add + marker + ``rm``."""
        hits = _detect_unsupported_capabilities(
            self._manifest_source,
            allow_nested_rotation=_rotation_apply_is_enabled(),
        )
        if hits:
            raise CapabilityError(
                reason="manifest declares capabilities the CommanderCliProvider does not implement yet: "
                + "; ".join(hits),
                next_action=(
                    "remove the declarations, or drive the Commander hook manually before "
                    "re-running apply. See REVIEW.md D-4."
                ),
            )
        _ensure_keepercommander_version_for_apply()
        if not self._folder_uid:
            raise CapabilityError(
                reason="keeper-vault apply requires a shared folder uid (discover scope)",
                next_action="pass --folder-uid or set KEEPER_DECLARATIVE_FOLDER",
            )
        self._vault_guard_shared_folder_membership_removals(plan)

        outcomes: list[ApplyOutcome] = []
        now = utc_timestamp()
        for change in plan.ordered():
            if change.kind is ChangeKind.CREATE:
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid="",
                            action="create",
                            details={"dry_run": True},
                        )
                    )
                    continue
                if change.resource_type == "record_type":
                    self._vault_apply_record_type_reject()
                if change.resource_type == _VAULT_SHARED_FOLDER_RESOURCE_TYPE:
                    keeper_uid = self._vault_add_shared_folder(change.after or {})
                    membership = self._vault_apply_shared_folder_membership_update(
                        keeper_uid,
                        before_members=[],
                        after_members=change.after.get("members") if change.after else None,
                    )
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="create",
                            details={"marker_written": False, **membership},
                        )
                    )
                    continue
                if _is_keeper_fill_change(change):
                    keeper_uid = self._vault_apply_keeper_fill_create(change.after or {})
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="create",
                            details={"marker_written": False},
                        )
                    )
                    continue
                keeper_uid = self._vault_add_login_record(change.after or {})
                marker = encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=plan.manifest_name,
                    resource_type=change.resource_type,
                    last_applied_at=now,
                )
                self._write_marker(keeper_uid, marker)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="create",
                        details={"marker_written": True},
                    )
                )
            elif change.kind is ChangeKind.UPDATE:
                keeper_uid = change.keeper_uid or ""
                if not keeper_uid:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid="",
                            action="update",
                            details={"skipped": True, "reason": "no keeper_uid on update change"},
                        )
                    )
                    continue
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="update",
                            details={"dry_run": True},
                        )
                    )
                    continue
                if change.resource_type == "record_type":
                    self._vault_apply_record_type_reject()
                patch = dict(change.after or {})
                if change.resource_type == _VAULT_SHARED_FOLDER_RESOURCE_TYPE:
                    membership = self._vault_apply_shared_folder_membership_update(
                        keeper_uid,
                        before_members=change.before.get("members"),
                        after_members=patch.get("members"),
                    )
                    default_permissions_updated = (
                        self._vault_apply_shared_folder_permissions_update(
                            keeper_uid,
                            patch.get("permissions"),
                        )
                    )
                    if patch.get("title") not in (None, ""):
                        self._run_cmd(["rndir", "-n", str(patch["title"]), keeper_uid])
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="update",
                            details={
                                "marker_written": False,
                                "record_updated": bool(patch),
                                **membership,
                                "default_permissions_updated": default_permissions_updated,
                            },
                        )
                    )
                    continue
                if _is_keeper_fill_change(change):
                    self._vault_apply_keeper_fill_update(keeper_uid, patch)
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid,
                            action="update",
                            details={"marker_written": False, "record_updated": bool(patch)},
                        )
                    )
                    continue
                if patch:
                    self._vault_apply_login_body_update(keeper_uid, patch)
                marker = encode_marker(
                    uid_ref=change.uid_ref or change.title,
                    manifest=plan.manifest_name,
                    resource_type=change.resource_type,
                    last_applied_at=now,
                )
                self._write_marker(keeper_uid, marker)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"marker_written": True, "record_updated": bool(patch)},
                    )
                )

        for change in plan.deletes:
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
            if change.resource_type == _VAULT_SHARED_FOLDER_RESOURCE_TYPE:
                if getattr(plan, "allow_delete", False) is not True:
                    raise CapabilityError(
                        reason="shared_folder delete requires --allow-delete",
                        uid_ref=change.uid_ref,
                        resource_type=change.resource_type,
                        next_action="rerun plan/apply with --allow-delete before deleting shared folders",
                    )
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
                self._delete_folder(path_or_uid=change.keeper_uid)
                outcome.details["removed"] = True
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
                self._run_cmd(["rm", "--force", change.keeper_uid])
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

    @staticmethod
    def _vault_shared_folder_permissions(
        permissions: Any,
    ) -> tuple[bool, bool]:
        if not isinstance(permissions, Mapping):
            return False, False
        return bool(permissions.get("manage_records")), bool(permissions.get("manage_users"))

    @staticmethod
    def _vault_shared_folder_role_permissions(role: Any) -> tuple[bool, bool]:
        if role == "manage":
            return True, True
        if role in {"edit", "manage_records"}:
            return True, False
        if role == "manage_users":
            return False, True
        return False, False

    @staticmethod
    def _vault_shared_folder_member_permission(member: Mapping[str, Any]) -> str:
        permission = member.get("permission")
        if permission is not None:
            return str(permission).strip()
        role = str(member.get("role") or "").strip()
        if role == "read":
            return "read_only"
        if role == "edit":
            return "manage_records"
        if role:
            return role
        if "manage_records" in member or "manage_users" in member:
            manage_records = bool(member.get("manage_records"))
            manage_users = bool(member.get("manage_users"))
            if manage_records and manage_users:
                return "manage"
            if manage_records:
                return "manage_records"
            if manage_users:
                return "manage_users"
            return "read_only"
        return ""

    @staticmethod
    def _vault_shared_folder_members_by_email(members: Any) -> dict[str, dict[str, str]]:
        if not isinstance(members, list):
            return {}
        out: dict[str, dict[str, str]] = {}
        for member in members:
            if not isinstance(member, Mapping):
                continue
            email = str(member.get("email") or "").strip()
            permission = CommanderCliProvider._vault_shared_folder_member_permission(member)
            if email and permission:
                out[email.casefold()] = {"email": email, "permission": permission}
        return out

    @staticmethod
    def _vault_shared_folder_removed_member_count(
        before_members: Any,
        after_members: Any,
    ) -> int:
        if not isinstance(before_members, list) or not isinstance(after_members, list):
            return 0
        before_by_email = CommanderCliProvider._vault_shared_folder_members_by_email(before_members)
        after_by_email = CommanderCliProvider._vault_shared_folder_members_by_email(after_members)
        return len(set(before_by_email) - set(after_by_email))

    def _vault_guard_shared_folder_membership_removals(self, plan: Plan) -> None:
        removed_count = 0
        first_change: Change | None = None
        for change in plan.ordered():
            if (
                change.kind is not ChangeKind.UPDATE
                or change.resource_type != _VAULT_SHARED_FOLDER_RESOURCE_TYPE
            ):
                continue
            count = self._vault_shared_folder_removed_member_count(
                change.before.get("members"),
                change.after.get("members"),
            )
            if count:
                removed_count += count
                first_change = first_change or change
        if not removed_count:
            return
        setattr(plan, "requires_allow_delete", True)
        if getattr(plan, "allow_delete", False) is True:
            return
        assert first_change is not None
        raise CapabilityError(
            reason="shared_folder membership removal requires --allow-delete",
            uid_ref=first_change.uid_ref,
            resource_type=first_change.resource_type,
            next_action=(
                "rerun plan/apply with --allow-delete before removing shared-folder members"
            ),
            context={
                "requires_allow_delete": True,
                "removed_member_count": removed_count,
            },
        )

    def _vault_add_shared_folder(self, after: dict[str, Any]) -> str:
        """Create a Keeper shared folder using Commander's folder-add equivalent."""
        title = str(after.get("title") or "").strip()
        if not title:
            raise CapabilityError(
                reason="shared_folder create is missing after.title",
                resource_type=_VAULT_SHARED_FOLDER_RESOURCE_TYPE,
                next_action="rebuild the vault plan from a manifest with shared_folders[].title",
            )
        manage_records, manage_users = self._vault_shared_folder_permissions(
            after.get("permissions")
        )
        try:
            from keepercommander import api  # type: ignore
            from keepercommander.commands import folder as folder_module  # type: ignore
        except ImportError as exc:
            raise CapabilityError(
                reason=f"cannot create shared folder: keepercommander unavailable: {exc}",
                next_action="install Commander Python package in the same interpreter as the SDK",
            ) from exc

        command_cls = getattr(folder_module, "FolderAddCommand", None) or getattr(
            folder_module,
            "FolderMakeCommand",
            None,
        )
        if command_cls is None:
            raise CapabilityError(
                reason="Commander shared-folder create command is unavailable",
                resource_type=_VAULT_SHARED_FOLDER_RESOURCE_TYPE,
                next_action=(
                    "upgrade keepercommander to a version with "
                    "keepercommander.commands.folder.FolderMakeCommand"
                ),
            )

        def _run_add() -> Any:
            params = self._get_keeper_params()
            api.sync_down(params)
            old_current = getattr(params, "current_folder", None)
            had_current = hasattr(params, "current_folder")
            target_current = self._vault_shared_folder_create_parent(params)
            setattr(params, "current_folder", target_current)
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    uid = command_cls().execute(
                        params,
                        folder=title,
                        shared_folder=True,
                        user_folder=False,
                        grant=False,
                        manage_records=manage_records,
                        manage_users=manage_users,
                        can_edit=False,
                        can_share=False,
                    )
            finally:
                if had_current:
                    setattr(params, "current_folder", old_current)
                elif hasattr(params, "current_folder"):
                    delattr(params, "current_folder")
            api.sync_down(params)
            return uid

        try:
            uid = self._with_keeper_session_refresh(_run_add)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"shared_folder create failed: {type(exc).__name__}: {exc}",
                next_action="verify shared-folder create permission and Commander folder cache, then retry",
            ) from exc

        uid_str = ""
        if isinstance(uid, str):
            uid_str = uid.strip()
        elif isinstance(uid, bytes):
            uid_str = uid.decode("utf-8", errors="replace").strip()
        elif uid is not None:
            uid_str = str(uid).strip()
        if not uid_str:
            raise CapabilityError(
                reason="Commander shared-folder create did not return a folder UID",
                resource_type=_VAULT_SHARED_FOLDER_RESOURCE_TYPE,
                next_action="inspect Commander folder-add/mkdir output and retry",
            )
        return uid_str

    def _vault_shared_folder_create_parent(self, params: Any) -> str:
        """Return a user/root folder parent for a new shared folder.

        keeper-vault L1 uses ``folder_uid`` as the record scope, normally a
        shared folder. Commander refuses nested shared folders, so create at
        root unless the configured scope is visibly a user/root folder.
        """
        if not self._folder_uid:
            return ""
        folder_cache = getattr(params, "folder_cache", None)
        if not isinstance(folder_cache, Mapping):
            return ""
        folder = folder_cache.get(self._folder_uid)
        if folder is None:
            return ""
        folder_type = getattr(folder, "type", None)
        if folder_type is None and isinstance(folder, Mapping):
            folder_type = folder.get("type")
        if folder_type in {"shared_folder", "shared_folder_folder"}:
            return ""
        return self._folder_uid

    def _vault_apply_shared_folder_membership_update(
        self,
        keeper_uid: str,
        *,
        before_members: Any,
        after_members: Any,
    ) -> dict[str, int]:
        if not isinstance(after_members, list):
            return {"members_granted": 0, "members_removed": 0}
        before_by_email = self._vault_shared_folder_members_by_email(before_members)
        after_by_email = self._vault_shared_folder_members_by_email(after_members)
        granted = 0
        removed = 0
        for key in sorted(set(before_by_email) - set(after_by_email)):
            self._revoke_folder_grantee(
                shared_folder_uid=keeper_uid,
                grantee_kind="user",
                identifier=before_by_email[key]["email"],
            )
            removed += 1
        for key in sorted(after_by_email):
            desired = after_by_email[key]
            if before_by_email.get(key) == desired:
                continue
            manage_records, manage_users = self._vault_shared_folder_role_permissions(
                desired["permission"]
            )
            self._share_folder_to_grantee(
                shared_folder_uid=keeper_uid,
                grantee_kind="user",
                identifier=desired["email"],
                manage_records=manage_records,
                manage_users=manage_users,
            )
            granted += 1
        return {"members_granted": granted, "members_removed": removed}

    def _vault_apply_shared_folder_permissions_update(
        self,
        keeper_uid: str,
        permissions: Any,
    ) -> bool:
        if not isinstance(permissions, Mapping):
            return False
        manage_records, manage_users = self._vault_shared_folder_permissions(permissions)
        self._share_folder_to_grantee(
            shared_folder_uid=keeper_uid,
            grantee_kind="default",
            manage_records=manage_records,
            manage_users=manage_users,
        )
        return True

    @staticmethod
    def _sharing_delete_order(changes: list[Change]) -> list[Change]:
        rank = {
            "sharing_share_folder": 0,
            "sharing_record_share": 1,
            "sharing_shared_folder": 2,
            "sharing_folder": 3,
        }
        return sorted(
            changes, key=lambda change: (rank.get(change.resource_type, 99), change.title)
        )

    def _apply_sharing_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Apply ``keeper-vault-sharing.v1`` folder + ACL rows.

        Keeper folders/ACL rows do not expose record custom fields. For this
        first Commander-backed sharing slice we persist ownership metadata in
        small sidecar records in the configured declarative folder, while the
        actual folders and ACLs are driven through Commander folder/share
        commands.
        """
        _ensure_keepercommander_version_for_apply()
        if not self._folder_uid:
            raise CapabilityError(
                reason="keeper-vault-sharing apply requires a marker shared folder uid",
                next_action="pass --folder-uid or set KEEPER_DECLARATIVE_FOLDER",
            )

        outcomes: list[ApplyOutcome] = []
        for change in plan.ordered():
            if change.kind is ChangeKind.CREATE:
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid="",
                            action="create",
                            details={"dry_run": True},
                        )
                    )
                    continue
                keeper_uid = self._sharing_apply_create_or_update(change)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="create",
                        details={"marker_sidecar_written": True},
                    )
                )
            elif change.kind is ChangeKind.UPDATE:
                if dry_run:
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=change.keeper_uid or "",
                            action="update",
                            details={"dry_run": True},
                        )
                    )
                    continue
                keeper_uid = self._sharing_apply_create_or_update(change)
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=keeper_uid,
                        action="update",
                        details={"marker_sidecar_written": True},
                    )
                )

        for change in self._sharing_delete_order(plan.deletes):
            if dry_run:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=change.uid_ref or "",
                        keeper_uid=change.keeper_uid or "",
                        action="delete",
                        details={"dry_run": True},
                    )
                )
                continue
            self._sharing_apply_delete(change)
            outcomes.append(
                ApplyOutcome(
                    uid_ref=change.uid_ref or "",
                    keeper_uid=change.keeper_uid or "",
                    action="delete",
                    details={"removed": True},
                )
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

    def _sharing_apply_create_or_update(self, change: Change) -> str:
        payload = self._sharing_full_payload(change)
        marker = self._sharing_marker_for_change(change, payload)
        resource_type = change.resource_type

        if resource_type == "sharing_folder":
            path = self._require_payload_str(payload, "path", change)
            keeper_uid = self._create_user_folder(
                path=path,
                parent_uid=payload.get("parent_folder_uid_ref"),
                color=payload.get("color"),
            )
            payload["keeper_uid"] = keeper_uid
        elif resource_type == "sharing_shared_folder":
            path = self._require_payload_str(payload, "path", change)
            keeper_uid = self._create_shared_folder(
                path=path,
                manage_records=self._payload_bool(payload, "default_manage_records", True),
                manage_users=self._payload_bool(payload, "default_manage_users", True),
                can_edit=self._payload_bool(payload, "default_can_edit", True),
                can_share=self._payload_bool(payload, "default_can_share", True),
            )
            payload["keeper_uid"] = keeper_uid
            payload.setdefault("name", payload.get("path"))
        elif resource_type == "sharing_share_folder":
            self._sharing_apply_share_folder_acl(payload, change=change)
            keeper_uid = (
                str(payload.get("keeper_uid"))
                if payload.get("keeper_uid")
                else f"{payload.get('shared_folder_uid_ref')}:{change.uid_ref or change.title}"
            )
            payload["keeper_uid"] = keeper_uid
        elif resource_type == "sharing_record_share":
            self._sharing_apply_record_share(payload, change=change)
            keeper_uid = (
                str(payload.get("keeper_uid"))
                if payload.get("keeper_uid")
                else f"{payload.get('record_uid_ref')}:{payload.get('user_email')}"
            )
            payload["keeper_uid"] = keeper_uid
        else:
            raise CapabilityError(
                reason=f"unsupported keeper-vault-sharing resource type {resource_type!r}",
                uid_ref=change.uid_ref,
                resource_type=resource_type,
                next_action="remove the unsupported sharing row and retry",
            )

        self._sharing_upsert_sidecar(payload=payload, marker=marker, title=change.title)
        return str(payload["keeper_uid"])

    def _sharing_apply_delete(self, change: Change) -> None:
        sidecar = self._sharing_sidecar_for(change.uid_ref, change.resource_type)
        payload = dict(sidecar.payload if sidecar is not None else change.before or {})
        if change.resource_type == "sharing_share_folder":
            self._sharing_revoke_share_folder_acl(payload, change=change)
        elif change.resource_type == "sharing_record_share":
            self._sharing_revoke_record_share(payload, change=change)
        elif change.resource_type in {"sharing_folder", "sharing_shared_folder"}:
            path_or_uid = str(payload.get("keeper_uid") or change.keeper_uid or payload.get("path"))
            if path_or_uid:
                self._delete_folder(path_or_uid=path_or_uid)
        else:
            raise CapabilityError(
                reason=f"unsupported keeper-vault-sharing delete type {change.resource_type!r}",
                uid_ref=change.uid_ref,
                resource_type=change.resource_type,
                next_action="remove the unsupported sharing row and retry",
            )
        self._sharing_delete_sidecar(change.uid_ref, change.resource_type)

    def _sharing_full_payload(self, change: Change) -> dict[str, Any]:
        payload = dict(change.after or {})
        if change.kind is ChangeKind.UPDATE:
            sidecar = self._sharing_sidecar_for(change.uid_ref, change.resource_type)
            if sidecar is not None:
                merged = dict(sidecar.payload)
                merged.update(payload)
                payload = merged
        return payload

    def _sharing_marker_for_change(self, change: Change, payload: dict[str, Any]) -> dict[str, Any]:
        raw_marker = payload.get("marker")
        if isinstance(raw_marker, dict):
            return dict(raw_marker)
        return encode_marker(
            uid_ref=change.uid_ref or change.title,
            manifest=change.manifest_name or "vault-sharing",
            resource_type=change.resource_type,
            parent_uid_ref=(
                str(payload.get("shared_folder_uid_ref") or payload.get("record_uid_ref"))
                if payload.get("shared_folder_uid_ref") or payload.get("record_uid_ref")
                else None
            ),
        )

    @staticmethod
    def _require_payload_str(payload: Mapping[str, Any], key: str, change: Change) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise CapabilityError(
                reason=f"{change.resource_type} {change.uid_ref or change.title} missing {key}",
                uid_ref=change.uid_ref,
                resource_type=change.resource_type,
                next_action=f"fix {key} in the sharing manifest and retry",
            )
        return value

    @staticmethod
    def _payload_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
        value = payload.get(key)
        return default if value is None else bool(value)

    def _sharing_apply_share_folder_acl(self, payload: dict[str, Any], *, change: Change) -> None:
        sf_uid = self._sharing_resolve_ref(
            self._require_payload_str(payload, "shared_folder_uid_ref", change),
            expected_resource_type="sharing_shared_folder",
        )
        payload["shared_folder_uid"] = sf_uid
        kind = self._require_payload_str(payload, "kind", change)
        if kind == "grantee":
            grantee_kind, identifier = self._sharing_grantee(payload)
            self._share_folder_to_grantee(
                shared_folder_uid=sf_uid,
                grantee_kind=grantee_kind,
                identifier=identifier,
                manage_records=self._payload_bool(payload, "manage_records", False),
                manage_users=self._payload_bool(payload, "manage_users", False),
            )
            return
        if kind == "default":
            target = self._require_payload_str(payload, "target", change)
            if target == "grantee":
                self._share_folder_to_grantee(
                    shared_folder_uid=sf_uid,
                    grantee_kind="default",
                    manage_records=self._payload_bool(payload, "manage_records", False),
                    manage_users=self._payload_bool(payload, "manage_users", False),
                )
                return
            if target == "record":
                self._set_shared_folder_default_record_share(
                    shared_folder_uid=sf_uid,
                    can_edit=self._payload_bool(payload, "can_edit", False),
                    can_share=self._payload_bool(payload, "can_share", False),
                )
                return
        raise CapabilityError(
            reason=f"unsupported share_folder ACL row kind/target: {kind}/{payload.get('target')}",
            uid_ref=change.uid_ref,
            resource_type=change.resource_type,
            next_action="use a grantee row or a default grantee/record row for V9a",
        )

    def _sharing_revoke_share_folder_acl(self, payload: dict[str, Any], *, change: Change) -> None:
        sf_uid = str(payload.get("shared_folder_uid") or "")
        if not sf_uid and payload.get("shared_folder_uid_ref"):
            sf_uid = self._sharing_resolve_ref(
                str(payload["shared_folder_uid_ref"]),
                expected_resource_type="sharing_shared_folder",
            )
        if not sf_uid:
            return
        kind = str(payload.get("kind") or "")
        if kind == "grantee":
            grantee_kind, identifier = self._sharing_grantee(payload)
            try:
                self._revoke_folder_grantee(
                    shared_folder_uid=sf_uid,
                    grantee_kind=grantee_kind,
                    identifier=identifier,
                )
            except CapabilityError as exc:
                if not self._sharing_missing_folder_error(exc):
                    raise
        elif kind == "default":
            try:
                self._revoke_folder_grantee(shared_folder_uid=sf_uid, grantee_kind="default")
            except CapabilityError as exc:
                if not self._sharing_missing_folder_error(exc):
                    raise

    @staticmethod
    def _sharing_missing_folder_error(exc: CapabilityError) -> bool:
        text = f"{exc.reason}\n{exc.context.get('stderr', '')}"
        return "Enter name of at least one existing folder" in text

    def _sharing_apply_record_share(self, payload: dict[str, Any], *, change: Change) -> None:
        record_uid = self._sharing_resolve_record_ref(
            self._require_payload_str(payload, "record_uid_ref", change)
        )
        user_email = self._require_payload_str(payload, "user_email", change)
        payload["record_uid"] = record_uid
        self._share_record_to_user(
            record_uid=record_uid,
            user_email=user_email,
            can_edit=self._payload_bool(payload, "can_edit", False),
            can_share=self._payload_bool(payload, "can_share", False),
            expiration_iso=payload.get("expires_at")
            if isinstance(payload.get("expires_at"), str)
            else None,
        )

    def _sharing_revoke_record_share(self, payload: dict[str, Any], *, change: Change) -> None:
        record_uid = str(payload.get("record_uid") or "")
        if not record_uid and payload.get("record_uid_ref"):
            record_uid = self._sharing_resolve_record_ref(str(payload["record_uid_ref"]))
        user_email = str(payload.get("user_email") or "")
        if record_uid and user_email:
            self._revoke_record_share_from_user(record_uid=record_uid, user_email=user_email)

    @staticmethod
    def _sharing_grantee(payload: Mapping[str, Any]) -> tuple[Literal["user", "team"], str]:
        grantee = payload.get("grantee")
        if isinstance(grantee, Mapping):
            kind = grantee.get("kind")
            if kind == "user" and grantee.get("user_email"):
                return "user", str(grantee["user_email"])
            if kind == "team" and grantee.get("team_uid_ref"):
                return "team", str(grantee["team_uid_ref"])
        if payload.get("user_email"):
            return "user", str(payload["user_email"])
        if payload.get("team_uid_ref"):
            return "team", str(payload["team_uid_ref"])
        raise CapabilityError(
            reason="share_folder grantee row is missing a user_email or team_uid_ref",
            next_action="add grantee.user_email or grantee.team_uid_ref and retry",
        )

    @staticmethod
    def _sharing_uid_ref_from_ref(ref: str) -> str:
        return ref.rsplit(":", 1)[-1]

    def _sharing_resolve_ref(self, ref: str, *, expected_resource_type: str) -> str:
        uid_ref = self._sharing_uid_ref_from_ref(ref)
        sidecar = self._sharing_sidecar_for(uid_ref, expected_resource_type)
        if sidecar is None:
            raise CapabilityError(
                reason=f"could not resolve {ref} from sharing marker sidecars",
                uid_ref=uid_ref,
                resource_type=expected_resource_type,
                next_action="apply the referenced sharing folder first, then retry",
            )
        return sidecar.keeper_uid

    def _sharing_resolve_record_ref(self, ref: str) -> str:
        uid_ref = self._sharing_uid_ref_from_ref(ref)
        for record in self._discover_marker_records():
            marker = record.marker or {}
            if marker.get("uid_ref") == uid_ref and marker.get("resource_type") == "login":
                return record.keeper_uid
        raise CapabilityError(
            reason=f"could not resolve record ref {ref} from scoped marker records",
            uid_ref=uid_ref,
            resource_type="sharing_record_share",
            next_action="create the keeper-vault record in the same declarative scope first",
        )

    def _sharing_upsert_sidecar(
        self,
        *,
        payload: dict[str, Any],
        marker: dict[str, Any],
        title: str,
    ) -> str:
        self._sharing_delete_sidecar(
            str(marker.get("uid_ref") or ""),
            str(marker.get("resource_type") or ""),
        )
        payload_for_record = dict(payload)
        payload_for_record.pop("marker", None)
        sidecar_title = self._sharing_sidecar_title(marker, title)
        payload_json = json.dumps(payload_for_record, separators=(",", ":"), sort_keys=True)
        sidecar_uid = self._vault_add_login_record(
            {
                "type": "login",
                "title": sidecar_title,
                "fields": [
                    {
                        "type": "login",
                        "label": "Login",
                        "value": ["dsk-sharing-marker"],
                    }
                ],
                "custom": [
                    {
                        "type": "text",
                        "label": _SHARING_PAYLOAD_FIELD_LABEL,
                        "value": [payload_json],
                    }
                ],
            }
        )
        self._write_marker(sidecar_uid, marker)
        return sidecar_uid

    @staticmethod
    def _sharing_sidecar_title(marker: Mapping[str, Any], fallback: str) -> str:
        manifest = str(marker.get("manifest") or "vault-sharing")
        uid_ref = str(marker.get("uid_ref") or fallback)
        return f"{_SHARING_MARKER_TITLE_PREFIX}: {manifest}: {uid_ref}"

    def _sharing_delete_sidecar(self, uid_ref: str | None, resource_type: str | None) -> None:
        if not uid_ref or not resource_type:
            return
        for sidecar in self._discover_sharing_sidecars():
            marker = sidecar.marker or {}
            if marker.get("uid_ref") != uid_ref or marker.get("resource_type") != resource_type:
                continue
            sidecar_uid = str(sidecar.payload.get("_sidecar_uid") or "")
            if sidecar_uid:
                self._run_cmd(["rm", "--force", sidecar_uid])
            return

    def _sharing_sidecar_for(
        self,
        uid_ref: str | None,
        resource_type: str | None,
    ) -> LiveRecord | None:
        if not uid_ref or not resource_type:
            return None
        for sidecar in self._discover_sharing_sidecars():
            marker = sidecar.marker or {}
            if marker.get("uid_ref") == uid_ref and marker.get("resource_type") == resource_type:
                return sidecar
        return None

    def _discover_sharing_rows(self) -> list[LiveRecord]:
        return self._discover_sharing_sidecars()

    def _discover_sharing_sidecars(self) -> list[LiveRecord]:
        rows: list[LiveRecord] = []
        for record in self._discover_marker_records():
            marker = record.marker or {}
            resource_type = marker.get("resource_type")
            if resource_type not in _SHARING_RESOURCE_TYPES:
                continue
            raw_payload = record.payload.get(_SHARING_PAYLOAD_FIELD_LABEL)
            if isinstance(raw_payload, list):
                raw_payload = raw_payload[0] if raw_payload else None
            payload: dict[str, Any]
            if isinstance(raw_payload, str) and raw_payload.strip():
                try:
                    loaded = json.loads(raw_payload)
                    payload = loaded if isinstance(loaded, dict) else {}
                except ValueError:
                    payload = {}
            else:
                payload = {}
            payload.setdefault("uid_ref", marker.get("uid_ref"))
            payload.setdefault("resource_type", resource_type)
            payload["_sidecar_uid"] = record.keeper_uid
            keeper_uid = str(payload.get("keeper_uid") or record.keeper_uid)
            rows.append(
                LiveRecord(
                    keeper_uid=keeper_uid,
                    title=str(payload.get("path") or payload.get("name") or record.title),
                    resource_type=str(resource_type),
                    folder_uid=record.folder_uid,
                    payload=payload,
                    marker=marker,
                )
            )
        return rows

    def _discover_marker_records(self) -> list[LiveRecord]:
        if not self._folder_uid:
            return []
        payload = self._run_cmd(["ls", self._folder_uid, "--format", "json"])
        entries = _load_json(payload, command="ls --format json")
        if not isinstance(entries, list):
            raise CapabilityError(
                reason="Commander returned non-array JSON from `ls --format json`"
            )
        records: list[LiveRecord] = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "record":
                continue
            keeper_uid = entry.get("uid")
            if not keeper_uid:
                continue
            item_payload = self._run_cmd(["get", str(keeper_uid), "--format", "json"])
            item = _load_json(item_payload, command="get --format json")
            if not isinstance(item, dict):
                continue
            record = _record_from_get(item, listing_entry={**entry, "folder_uid": self._folder_uid})
            if record is not None and record.marker:
                records.append(record)
        return records

    @staticmethod
    def _vault_custom_field_label(entry: dict[str, Any]) -> str:
        return str(entry.get("label") or entry.get("name") or "").casefold()

    @classmethod
    def _vault_merge_custom_for_update(
        cls,
        existing_list: list[Any],
        patch_list: list[Any],
    ) -> list[dict[str, Any]]:
        """Overlay ``patch_list`` entries onto ``existing_list`` by field label.

        Preserves the SDK ownership marker entry if the manifest ``custom`` patch
        omits it (declarative manifests normally do not carry the live marker).
        """
        marker_key = MARKER_FIELD_LABEL.casefold()
        patch_by = {
            cls._vault_custom_field_label(e): copy.deepcopy(e)
            for e in patch_list
            if isinstance(e, dict) and cls._vault_custom_field_label(e)
        }
        out: list[dict[str, Any]] = []
        used_patch: set[str] = set()
        for e in existing_list:
            if not isinstance(e, dict):
                continue
            lab = cls._vault_custom_field_label(e)
            if lab in patch_by:
                out.append(copy.deepcopy(patch_by[lab]))
                used_patch.add(lab)
            else:
                out.append(copy.deepcopy(e))
        for lab, ent in patch_by.items():
            if lab not in used_patch:
                out.append(ent)
        labels_present = {cls._vault_custom_field_label(x) for x in out}
        if marker_key not in labels_present:
            marker_keep = next(
                (
                    copy.deepcopy(x)
                    for x in existing_list
                    if isinstance(x, dict) and cls._vault_custom_field_label(x) == marker_key
                ),
                None,
            )
            if marker_keep is not None:
                out.append(marker_keep)
        return out

    @staticmethod
    def _vault_patch_login_record_data(
        existing: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge planner ``patch`` (subset of manifest record) into v3 ``data`` JSON."""
        out = copy.deepcopy(existing)
        for key, val in patch.items():
            if key in _DIFF_IGNORED_FIELDS:
                continue
            if key == "custom":
                if not isinstance(val, list):
                    continue
                out["custom"] = CommanderCliProvider._vault_merge_custom_for_update(
                    out.get("custom") or [],
                    val,
                )
            else:
                out[key] = copy.deepcopy(val)
        return out

    def _vault_apply_keeper_fill_create(self, after: dict[str, Any]) -> str:
        """Reject keeper_fill create: no Commander verb writes the keeper_fill record-type yet.

        Keeper Commander 17.2.x exposes ``record-add`` only for typed records; the
        ``keeper_fill`` block has no analogous create verb. The W3-AB schema-honesty
        slice routes the change here rather than silently dropping it through the
        login-record path. See audit `notes/dsk-improvement-audit-2026-04-27.md` F2;
        schema marker for ``keeper_fill`` flipped to ``scaffold-only`` in the same
        slice. Raise rather than fake support.
        """
        del after  # not used; retained so the signature matches the call site
        raise CapabilityError(
            reason=(
                "keeper_fill create has no Commander writer in the pinned upstream "
                "(17.2.x); manifest declares a keeper_fill block but apply cannot "
                "land it without a tenant-side verb."
            ),
            next_action=(
                "remove the keeper_fill block from the manifest, or wait for the "
                "Commander team to publish a typed keeper_fill writer; track via "
                "schema status `scaffold-only`."
            ),
        )

    def _vault_apply_keeper_fill_update(self, keeper_uid: str, patch: dict[str, Any]) -> None:
        """Reject keeper_fill update for the same reason as create (see above)."""
        del keeper_uid, patch
        raise CapabilityError(
            reason=(
                "keeper_fill update has no Commander writer in the pinned upstream "
                "(17.2.x); apply cannot land manifest drift onto the live keeper_fill "
                "record-type."
            ),
            next_action=(
                "remove the keeper_fill block from the manifest, or wait for upstream "
                "support; schema status is `scaffold-only`."
            ),
        )

    def _vault_apply_record_type_reject(self) -> None:
        """Reject record_type create/update: no Commander writer for type definitions (W3-AB)."""
        raise CapabilityError(
            reason=(
                "no Commander writer for record_type definitions in the pinned upstream "
                "(17.2.x); plan can surface `record_types[]` but apply cannot land them in-vault."
            ),
            next_action=(
                "treat `record_types` as preview-gated (schema status `preview-gated`); use "
                "plan/mock/discovery only until an upstream record-type apply verb exists."
            ),
            resource_type="record_type",
        )

    def _vault_apply_login_body_update(self, keeper_uid: str, patch: dict[str, Any]) -> None:
        """Push manifest field drift onto an existing v3 ``login`` via RecordEditCommand."""
        if not patch:
            return
        try:
            from keepercommander import api  # type: ignore
            from keepercommander.commands.recordv3 import (
                RecordEditCommand,  # type: ignore
            )
        except ImportError as exc:
            raise CapabilityError(
                reason=f"cannot update vault record body: keepercommander unavailable: {exc}",
                next_action="install Commander Python package in the same interpreter as the SDK",
            ) from exc

        def run_edit() -> None:
            params = self._get_keeper_params()
            api.sync_down(params)
            cache = getattr(params, "record_cache", None) or {}
            if keeper_uid not in cache:
                raise CapabilityError(
                    reason=f"vault update: record {keeper_uid} not found in Commander cache after sync",
                    next_action="confirm the record uid and folder scope, then retry",
                )
            rec = cache[keeper_uid]
            version = int(rec.get("version") or 0)
            # Commander ``RecordEditCommand`` only accepts ``rv == 3`` for the
            # ``--data`` JSON path we use (see keepercommander ``recordv3.py``).
            if version != 3:
                raise CapabilityError(
                    reason=(
                        f"vault update: record {keeper_uid} must be record version 3 for JSON edit "
                        f"(got version={version})"
                    ),
                    next_action="use v3 typed login records in the scoped folder for keeper-vault L1",
                )
            raw = rec.get("data_unencrypted")
            if raw is None:
                raise CapabilityError(
                    reason=f"vault update: record {keeper_uid} has no decrypted data in cache",
                    next_action="retry after a successful Commander sync_down",
                )
            raw_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            existing = json.loads(raw_str or "{}")
            merged = self._vault_patch_login_record_data(existing, patch)
            if merged == existing:
                return
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            return_result: dict[str, Any] = {}
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                RecordEditCommand().execute(
                    params,
                    record=keeper_uid,
                    data=json.dumps(merged),
                    return_result=return_result,
                )
            if not return_result.get("update_record_v3"):
                err_tail = (buf_err.getvalue() or "").strip()
                reason = (
                    "vault update: RecordEditCommand returned without applying a v3 update "
                    "(Commander may have logged an error and exited)"
                )
                if err_tail:
                    reason = f"{reason}; stderr: {err_tail[:800]}"
                raise CapabilityError(
                    reason=reason,
                    next_action=(
                        "inspect Commander stderr for edit validation errors; "
                        "confirm record type, v3 JSON shape, and account record-types policy, then retry"
                    ),
                )

        try:
            self._with_keeper_session_refresh(run_edit)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"vault record body update failed: {type(exc).__name__}: {exc}",
                next_action="inspect Commander stderr/stdout and the manifest patch fields, then retry",
            ) from exc

    def _vault_add_login_record(self, after: dict[str, Any]) -> str:
        """Create a vault ``login`` record in the configured shared folder (in-process)."""
        try:
            from keepercommander.commands.recordv3 import (
                RecordAddCommand,  # type: ignore
            )
        except ImportError as exc:
            raise CapabilityError(
                reason=f"cannot create vault record: keepercommander unavailable: {exc}",
                next_action="install Commander Python package in the same interpreter as the SDK",
            ) from exc

        record_data: dict[str, Any] = {
            "type": str(after.get("type") or "login"),
            "title": str(after.get("title") or ""),
            "fields": list(after.get("fields") or []),
            "custom": list(after.get("custom") or []),
        }
        notes = after.get("notes")
        if isinstance(notes, str) and notes.strip():
            record_data["notes"] = notes

        def _run_add() -> Any:
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                return RecordAddCommand().execute(
                    params,
                    data=json.dumps(record_data),
                    force=False,
                    folder=self._folder_uid,
                    attach=[],
                )

        try:
            uid = self._with_keeper_session_refresh(_run_add)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"vault record-add failed: {type(exc).__name__}: {exc}",
                next_action="verify folder permissions and login session, then retry",
            ) from exc

        uid_str = ""
        if isinstance(uid, str):
            uid_str = uid.strip()
        elif isinstance(uid, bytes):
            uid_str = uid.decode("utf-8", errors="replace").strip()
        elif uid is not None:
            uid_str = str(uid).strip()
        if not uid_str:
            raise CapabilityError(
                reason="Commander record-add did not return a record UID",
                next_action="verify keepercommander record-add for login records in shared folders",
            )
        return uid_str

    # ------------------------------------------------------------------

    def _apply_rotation_settings(
        self,
        plan: Plan,
        live_records: list[LiveRecord],
    ) -> list[ApplyOutcome]:
        if not _rotation_apply_is_enabled():
            return []
        try:
            argvs = build_pam_rotation_edit_argvs(
                self._manifest_source,
                plan=plan,
                live_records=live_records,
            )
        except ValueError as exc:
            raise CapabilityError(
                reason=f"cannot apply resources[].users[].rotation_settings: {exc}",
                next_action=(
                    "confirm pam project import/extend created the nested pamUser, "
                    "parent resource, admin user, and PAM configuration; then rerun plan/apply"
                ),
            ) from exc

        live_by_uid = {record.keeper_uid: record for record in live_records}
        outcomes: list[ApplyOutcome] = []
        for argv in argvs:
            self._run_cmd(argv)
            record_uid = _argv_value(argv, "--record") or ""
            live = live_by_uid.get(record_uid)
            uid_ref = _non_empty_str((live.marker or {}).get("uid_ref")) if live else ""
            outcomes.append(
                ApplyOutcome(
                    uid_ref=uid_ref or "",
                    keeper_uid=record_uid,
                    action="rotation",
                    details={"command": argv},
                )
            )
        return outcomes

    # ------------------------------------------------------------------

    def _manifest_name_from_source(self) -> str | None:
        name = self._manifest_source.get("name") or self._manifest_source.get("project")
        return str(name) if isinstance(name, str) and name.strip() else None

    def _maybe_resolve_project_resources_folder(self, project_name: str) -> str | None:
        try:
            return self._resolve_project_resources_folder(project_name)
        except CapabilityError:
            return None

    def _discover_folder_uids(self) -> list[str]:
        project_name = self._manifest_name
        if project_name:
            self._maybe_resolve_project_resources_folder(project_name)

        folder_uids: list[str] = []
        for folder_uid in (self._folder_uid, self.last_resolved_users_folder_uid):
            if folder_uid and folder_uid not in folder_uids:
                folder_uids.append(folder_uid)
        return folder_uids

    def _synthetic_reference_configuration_record(self) -> LiveRecord | None:
        if not _uses_reference_existing(self._manifest_source):
            return None
        project_name = self._manifest_name
        if not project_name:
            return None
        if not self.last_resolved_folder_uid and not self._maybe_resolve_project_resources_folder(
            project_name
        ):
            return None

        payload = to_pam_import_json(self._manifest_source)
        config = self._resolve_reference_configuration(payload)
        uid_ref = _pam_configuration_uid_ref(self._manifest_source)
        marker = encode_marker(
            uid_ref=uid_ref or config["config_name"],
            manifest=project_name,
            resource_type="pam_configuration",
        )
        # Reflect the manifest's declared fields onto the synthetic payload so
        # the planner's field diff treats a reused reference config as noop.
        # We don't actually own the record — we're just asserting the caller
        # declared it identically to what's already in the vault.
        declared: dict[str, Any] = {}
        configs = self._manifest_source.get("pam_configurations") or []
        if isinstance(configs, list) and configs and isinstance(configs[0], dict):
            for key, value in configs[0].items():
                if key in {"uid_ref", "mode"}:
                    continue
                declared[key] = value
        declared.setdefault("title", config["config_name"])
        return LiveRecord(
            keeper_uid=config["config_uid"],
            title=config["config_name"],
            resource_type="pam_configuration",
            folder_uid=None,
            payload=declared,
            marker=marker,
        )

    def _ensure_reference_project_scaffold(
        self, *, project_name: str, gateway_app_uid: str
    ) -> dict[str, str]:
        root_name = "PAM Environments"
        project_path = f"{root_name}/{project_name}"
        resources_name = f"{project_name} - Resources"
        users_name = f"{project_name} - Users"
        resources_path = f"{project_path}/{resources_name}"
        users_path = f"{project_path}/{users_name}"

        self._ensure_folder_exists(root_name)
        self._ensure_folder_exists(project_path)
        self._ensure_shared_folder_exists(resources_path)
        self._ensure_shared_folder_exists(users_path)

        project_entries = _load_json(
            self._run_cmd(["ls", "--format", "json", project_path]),
            command=f"ls --format json {project_path}",
        )
        resources_uid = _entry_uid_by_name(project_entries, resources_name)
        users_uid = _entry_uid_by_name(project_entries, users_name)
        if not resources_uid or not users_uid:
            raise CapabilityError(
                reason=f"Commander did not return the shared folders for {project_path}",
                next_action=f'inspect `keeper ls --format json "{project_path}"` and confirm scaffold creation succeeded',
            )

        self._share_folder_to_ksm_app(folder_uid=resources_uid, app_uid=gateway_app_uid)
        self._share_folder_to_ksm_app(folder_uid=users_uid, app_uid=gateway_app_uid)
        return {
            "resources_uid": resources_uid,
            "users_uid": users_uid,
            "resources_name": resources_name,
            "users_name": users_name,
        }

    def _ensure_folder_exists(self, path: str) -> None:
        try:
            self._run_cmd(["ls", "--format", "json", path])
        except CapabilityError:
            self._run_cmd(["mkdir", "-uf", path])

    def _create_user_folder(
        self,
        *,
        path: str,
        parent_uid: str | None = None,
        color: str | None = None,
    ) -> str:
        _ = parent_uid
        args = ["mkdir", "-uf", path]
        if color is not None:
            args.extend(["--color", color])
        self._run_cmd(args)
        return self._resolve_folder_uid_by_path(path)

    def _create_shared_folder(
        self,
        *,
        path: str,
        manage_records: bool = True,
        manage_users: bool = True,
        can_edit: bool = True,
        can_share: bool = True,
    ) -> str:
        args = ["mkdir", "-sf"]
        if manage_records:
            args.append("--manage-records")
        if manage_users:
            args.append("--manage-users")
        if can_edit:
            args.append("--can-edit")
        if can_share:
            args.append("--can-share")
        args.append(path)
        self._run_cmd(args)
        return self._resolve_folder_uid_by_path(path)

    def _move_folder(self, *, source: str, destination: str, is_shared: bool = False) -> None:
        folder_flag = "--shared-folder" if is_shared else "--user-folder"
        self._run_cmd(["mv", folder_flag, source, destination])

    def _delete_folder(self, *, path_or_uid: str) -> None:
        self._run_cmd(["rmdir", "-f", path_or_uid])

    def _resolve_folder_uid_by_path(self, path: str) -> str:
        def resolve_once() -> str | None:
            from keepercommander import api  # type: ignore[import-not-found]
            from keepercommander.subfolder import (
                get_folder_uids,  # type: ignore[import-not-found]
            )

            params = self._get_keeper_params()
            api.sync_down(params)
            uids = sorted(uid for uid in get_folder_uids(params, path) if uid)
            return str(uids[0]) if uids else None

        try:
            uid = self._with_keeper_session_refresh(resolve_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"could not resolve folder path {path!r}: {type(exc).__name__}: {exc}",
                next_action="inspect the Commander folder tree and retry",
            ) from exc
        if uid:
            return uid
        raise CapabilityError(
            reason=f"Commander did not return folder UID for {path!r} after create",
            next_action="inspect `keeper ls -f --format json` and retry",
        )

    def _ensure_shared_folder_exists(self, path: str) -> None:
        try:
            self._run_cmd(["ls", "--format", "json", path])
        except CapabilityError:
            self._run_cmd(
                [
                    "mkdir",
                    "-sf",
                    "--manage-users",
                    "--manage-records",
                    "--can-edit",
                    "--can-share",
                    path,
                ]
            )

    def _share_record_to_user(
        self,
        *,
        record_uid: str,
        user_email: str,
        can_edit: bool,
        can_share: bool,
        expiration_iso: str | None = None,
    ) -> None:
        args = ["share-record", "-a", "grant", "-e", user_email, "-f"]
        if can_edit:
            args.append("-w")
        if can_share:
            args.append("-s")
        if expiration_iso is not None:
            args.extend(["--expire-at", expiration_iso])
        args.append(record_uid)
        self._run_cmd(args)

    def _revoke_record_share_from_user(self, *, record_uid: str, user_email: str) -> None:
        self._run_cmd(["share-record", "-a", "revoke", "-e", user_email, record_uid])

    def _share_folder_to_grantee(
        self,
        *,
        shared_folder_uid: str,
        grantee_kind: Literal["user", "team", "default"],
        identifier: str | None = None,
        manage_records: bool,
        manage_users: bool,
    ) -> None:
        grantee = self._share_folder_grantee_arg(
            grantee_kind=grantee_kind,
            identifier=identifier,
        )
        self._run_cmd(
            [
                "share-folder",
                "-a",
                "grant",
                "-e",
                grantee,
                "-f",
                "-p",
                _commander_on_off(manage_records),
                "-o",
                _commander_on_off(manage_users),
                shared_folder_uid,
            ]
        )

    def _revoke_folder_grantee(
        self,
        *,
        shared_folder_uid: str,
        grantee_kind: Literal["user", "team", "default"],
        identifier: str | None = None,
    ) -> None:
        grantee = self._share_folder_grantee_arg(
            grantee_kind=grantee_kind,
            identifier=identifier,
        )
        self._run_cmd(["share-folder", "-a", "remove", "-e", grantee, "-f", shared_folder_uid])

    def _share_record_to_shared_folder(
        self,
        *,
        shared_folder_uid: str,
        record_uid: str,
        can_edit: bool,
        can_share: bool,
    ) -> None:
        self._run_cmd(
            [
                "share-folder",
                "-a",
                "grant",
                "-r",
                record_uid,
                "-f",
                "-d",
                _commander_on_off(can_edit),
                "-s",
                _commander_on_off(can_share),
                shared_folder_uid,
            ]
        )

    def _set_shared_folder_default_record_share(
        self,
        *,
        shared_folder_uid: str,
        can_edit: bool,
        can_share: bool,
    ) -> None:
        self._run_cmd(
            [
                "share-folder",
                "-a",
                "grant",
                "-r",
                "*",
                "-f",
                "-d",
                _commander_on_off(can_edit),
                "-s",
                _commander_on_off(can_share),
                shared_folder_uid,
            ]
        )

    def _discover_shared_folder_acl(self, *, shared_folder_uid: str) -> dict[str, Any]:
        payload = self._run_cmd(["get", shared_folder_uid, "--format", "json"])
        item = _load_json(payload, command="get --format json")
        if not isinstance(item, dict):
            raise CapabilityError(
                reason="Commander returned non-object JSON from `get --format json`"
            )
        return {
            "users": _dict_items(item.get("users")),
            "teams": _dict_items(item.get("teams")),
            "records": _dict_items(item.get("records")),
            "default": {
                "manage_records": item.get("manage_records", item.get("default_manage_records")),
                "manage_users": item.get("manage_users", item.get("default_manage_users")),
                "can_edit": item.get("can_edit", item.get("default_can_edit")),
                "can_share": item.get("can_share", item.get("default_can_share")),
            },
        }

    @staticmethod
    def _share_folder_grantee_arg(
        *,
        grantee_kind: Literal["user", "team", "default"],
        identifier: str | None,
    ) -> str:
        if grantee_kind == "default":
            if identifier is not None:
                raise ValueError("default shared-folder grantee must not specify identifier")
            return "*"
        if grantee_kind in {"user", "team"}:
            if not identifier:
                raise ValueError(f"{grantee_kind} shared-folder grantee requires identifier")
            return identifier
        raise ValueError(f"unsupported shared-folder grantee kind: {grantee_kind}")

    def _share_folder_to_ksm_app(self, *, folder_uid: str, app_uid: str) -> None:
        try:
            self._run_cmd(
                [
                    "secrets-manager",
                    "share",
                    "add",
                    "--app",
                    app_uid,
                    "--secret",
                    folder_uid,
                    "--editable",
                ]
            )
        except CapabilityError as exc:
            text = "\n".join(
                str(value) for value in (exc.context or {}).values() if isinstance(value, str)
            ).casefold()
            if "already" not in text:
                raise

    def _resolve_reference_configuration(self, payload: dict[str, Any]) -> dict[str, str]:
        config_name = str((payload.get("pam_configuration") or {}).get("title", "")).strip()
        gateway_name = str((payload.get("pam_configuration") or {}).get("gateway_name", "")).strip()

        gateway_rows = self._pam_gateway_rows()
        config_rows = self._pam_config_rows()

        gateway_row = next(
            (row for row in gateway_rows if row["gateway_name"] == gateway_name), None
        )
        config_row = next((row for row in config_rows if row["config_name"] == config_name), None)
        if config_row is None and gateway_row is not None:
            matches = [
                row for row in config_rows if row["gateway_uid"] == gateway_row["gateway_uid"]
            ]
            if len(matches) == 1:
                config_row = matches[0]

        if gateway_row is None:
            raise CapabilityError(
                reason=f"reference-existing gateway '{gateway_name}' not found in `keeper pam gateway list`",
                next_action="update the manifest to a real gateway name or create the gateway first",
            )
        if config_row is None:
            raise CapabilityError(
                reason=(
                    f"reference-existing PAM configuration '{config_name}' not found and no unique configuration "
                    f"was attached to gateway '{gateway_name}'"
                ),
                next_action="update the manifest title or bind the gateway to exactly one PAM configuration",
            )
        return {
            "gateway_name": gateway_row["gateway_name"],
            "gateway_uid": gateway_row["gateway_uid"],
            "app_uid": gateway_row["app_uid"],
            "config_uid": config_row["config_uid"],
            "config_name": config_row["config_name"],
        }

    def _pam_gateway_rows(self) -> list[dict[str, str]]:
        """Return gateway rows using Commander's JSON output.

        Commander release `17.2.13+` exposes ``pam gateway list --format json``
        (``keepercommander/commands/discoveryrotation.py`` L1373-1606). The
        response is ``{"gateways": [{gateway_name, gateway_uid, ksm_app_name,
        ksm_app_uid, ksm_app_accessible, status, gateway_version, ...}, ...]}``.
        Empty enterprises return ``{"gateways": [], "message": ...}``.
        """
        raw = self._run_cmd(["pam", "gateway", "list", "--format", "json"])
        data = _load_json(raw, command="pam gateway list --format json")
        if isinstance(data, dict):
            items = data.get("gateways") or []
        else:
            items = []
        rows: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "app_title": str(item.get("ksm_app_name") or ""),
                    "app_uid": str(item.get("ksm_app_uid") or ""),
                    "gateway_name": str(item.get("gateway_name") or ""),
                    "gateway_uid": str(item.get("gateway_uid") or ""),
                }
            )
        return rows

    def _ksm_app_rows(self) -> list[dict[str, str]]:
        """Return KSM application rows, caching the JSON payload per provider."""
        if self._ksm_app_rows_cache is not None:
            return self._ksm_app_rows_cache
        raw = self._run_cmd(["secrets-manager", "app", "list", "--format", "json"])
        data = _load_json(raw, command="secrets-manager app list --format json")
        if isinstance(data, dict):
            items = data.get("applications") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        rows: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "app_title": str(
                        item.get("app_name")
                        or item.get("title")
                        or item.get("name")
                        or item.get("application_name")
                        or ""
                    ),
                    "app_uid": str(
                        item.get("app_uid") or item.get("uid") or item.get("application_uid") or ""
                    ),
                }
            )
        self._ksm_app_rows_cache = rows
        return rows

    def _gateway_bound_app_name(self, row: dict[str, str]) -> tuple[str | None, str | None]:
        """Resolve the KSM app title for a gateway row, or explain why not."""
        app_title = row.get("app_title") or ""
        if app_title:
            return app_title, None

        app_uid = row.get("app_uid") or ""
        next_action = (
            "next_action=confirm the gateway's bound KSM application in the Keeper UI "
            "(PAM Gateway details / Secrets Manager Applications) and update the manifest "
            "or tenant to match"
        )
        if not app_uid:
            return (
                None,
                "CLI output exposed neither a KSM app name nor a KSM app UID for this gateway; "
                f"`secrets-manager app list --format json` is application-only and cannot link "
                f"an unlabelled gateway to an app. {next_action}",
            )

        try:
            app_rows = self._ksm_app_rows()
        except (CapabilityError, OSError) as exc:
            return (
                None,
                "CLI output exposed only KSM app UID "
                f"'{app_uid}', and `secrets-manager app list --format json` could not be read: "
                f"{exc}. {next_action}",
            )

        app_by_uid = {item["app_uid"]: item for item in app_rows if item.get("app_uid")}
        resolved = app_by_uid.get(app_uid)
        if resolved and resolved.get("app_title"):
            return resolved["app_title"], None
        return (
            None,
            "CLI output exposed only KSM app UID "
            f"'{app_uid}', and `secrets-manager app list --format json` did not resolve it "
            f"to a visible application name. {next_action}",
        )

    def _pam_config_rows(self) -> list[dict[str, str]]:
        """Return PAM configuration rows using Commander's JSON output.

        Commander release `17.2.13+` exposes ``pam config list --format json``
        (``keepercommander/commands/discoveryrotation.py`` L1729-1967).
        Response: ``{"configurations": [{uid, config_name, config_type,
        shared_folder: {name, uid}, gateway_uid, resource_record_uids,
        ...}, ...]}``.
        """
        raw = self._run_cmd(["pam", "config", "list", "--format", "json"])
        data = _load_json(raw, command="pam config list --format json")
        if isinstance(data, dict):
            items = data.get("configurations") or []
        else:
            items = []
        rows: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sf = item.get("shared_folder") or {}
            rows.append(
                {
                    "config_uid": str(item.get("uid") or ""),
                    "config_name": str(item.get("config_name") or ""),
                    "gateway_uid": str(item.get("gateway_uid") or ""),
                    "shared_folder_title": str(sf.get("name") or "")
                    if isinstance(sf, dict)
                    else "",
                    "shared_folder_uid": str(sf.get("uid") or "") if isinstance(sf, dict) else "",
                }
            )
        return rows

    def _write_marker(self, keeper_uid: str, marker: dict[str, Any]) -> None:
        """Persist the ownership marker custom field on a record.

        Prefer the in-process Commander vault API — the bundled macOS
        `keeper` binary (17.1.14) doesn't know `record-update`, and Commander
        17.2.13's CLI uses a field-syntax (`custom.label=value`) that's
        fragile across versions. We already have KeeperParams available for
        the pam project import/extend path; reuse them.
        """
        payload = serialize_marker(marker)
        try:
            from keepercommander import api, record_management, vault  # type: ignore
        except ImportError as exc:
            raise CapabilityError(
                reason=f"cannot write ownership marker: keepercommander unavailable: {exc}",
                next_action="install Commander Python package in the same interpreter as the SDK",
            ) from exc

        def write_once() -> None:
            params = self._get_keeper_params()
            api.sync_down(params)
            record = vault.KeeperRecord.load(params, keeper_uid)
            if not isinstance(record, vault.TypedRecord):
                raise CapabilityError(
                    reason=f"cannot write ownership marker: record {keeper_uid} is not a TypedRecord",
                    next_action="confirm the record type and retry",
                )

            existing = None
            for field in record.custom:
                if (field.label or "") == MARKER_FIELD_LABEL:
                    existing = field
                    break
            if existing is not None:
                existing.type = "text"
                existing.value = [payload]
            else:
                new_field = vault.TypedField.new_field("text", payload, MARKER_FIELD_LABEL)
                record.custom.append(new_field)

            record_management.update_record(params, record)
            api.sync_down(params)

        try:
            self._with_keeper_session_refresh(write_once)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"cannot write ownership marker: {type(exc).__name__}: {exc}",
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _resolve_project_resources_folder(self, project_name: str) -> str:
        return self._resolve_project_scaffold_folders(project_name)["resources_uid"]

    def _resolve_project_scaffold_folders(self, project_name: str) -> dict[str, str]:
        # Commander's `ls <path>` returns the CHILDREN of that path, not the
        # path entry itself. So `ls "PAM Environments"` already gives us the
        # project folders directly — no extra layer to strip.
        project_entries = _load_json(
            self._run_cmd(["ls", "--format", "json", "PAM Environments"]),
            command="ls --format json PAM Environments",
        )
        project_uid = _entry_uid_by_name(project_entries, project_name)
        if not project_uid:
            raise CapabilityError(
                reason=f"Commander did not return project folder '{project_name}' under PAM Environments",
                next_action='inspect `keeper ls --format json "PAM Environments"` and confirm import created the project folder',
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
        users_name = f"{project_name} - Users"
        users_uid = _entry_uid_by_name(resources_entries, users_name)
        self.last_resolved_users_folder_uid = users_uid
        return {
            "resources_uid": resources_uid,
            "users_uid": users_uid or "",
        }

    def _run_cmd(self, args: list[str]) -> str:
        # `pam project import` / `pam project extend` can't run reliably under
        # `keeper --batch-mode` in subprocess: persistent-login works for
        # sibling commands like `pam gateway list`, but for these two the
        # Commander binary drops back to an interactive `Email:` prompt even
        # with a warmed config + KEEPER_PASSWORD set. Root cause: the bundled
        # macOS binary at /usr/local/bin/keeper is 17.1.14 (doesn't know
        # `pam project extend`) and `python3 -m keepercommander` 17.2.13 in
        # subprocess can't resume the session for this specific subcommand.
        # In-process invocation via the Commander Python API works cleanly
        # once we've done one api.login() with full TOTP, so we delegate.
        if (
            len(args) >= 3
            and args[0] == "pam"
            and args[1] == "project"
            and args[2] in {"import", "extend"}
        ):
            return self._run_pam_project_in_process(args)
        if args[:3] == ["pam", "rotation", "edit"]:
            return self._run_pam_rotation_edit_in_process(args)
        if args[:3] == ["pam", "rotation", "list"]:
            return self._run_pam_list_in_process(args)
        if args in (
            ["pam", "gateway", "list", "--format", "json"],
            ["pam", "config", "list", "--format", "json"],
        ):
            return self._run_pam_list_in_process(args)
        # ``ls <FOLDER_UID> --format json`` / ``get <UID> --format json`` are
        # the read-side of every discover() round-trip. Subprocess execution
        # against ``/usr/local/bin/keeper`` uses ``~/.keeper/commander-config.json``
        # which can hold a stale device_token (e.g. on dev workstations) and
        # then fails to resync just-applied records on a post-apply re-plan
        # — even though the in-process Commander 17.2.13 session that ran
        # the apply itself is fresh. Route through the same in-process
        # session when login config is detectable so discover() shares the
        # apply-time auth context. Falls through to subprocess when no
        # in-process login is configured (plain installs).
        if (
            len(args) >= 2
            and args[0] == "ls"
            and "--format" in args
            and args[args.index("--format") + 1 : args.index("--format") + 2] == ["json"]
            and self._can_attempt_in_process_login()
        ):
            return self._run_ls_in_process(args)
        if (
            len(args) >= 2
            and args[0] == "get"
            and "--format" in args
            and args[args.index("--format") + 1 : args.index("--format") + 2] == ["json"]
            and self._can_attempt_in_process_login()
        ):
            return self._run_record_get_in_process(args)

        # --batch-mode suppresses interactive prompts (password, 2FA,
        # confirmations). stdin=DEVNULL is belt-and-braces — if Commander ever
        # tries to read stdin despite --batch-mode we want EOF, not a hang.
        base = [self._bin, "--batch-mode"]
        if self._config:
            base += ["--config", self._config]
        env = os.environ.copy()
        if self._password:
            env["KEEPER_PASSWORD"] = self._password
        result = None
        for attempt in range(2):
            result = subprocess.run(
                base + args,
                check=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            if result.returncode == 0 or attempt == 1:
                break
            if not _is_retryable_keeper_session_text(result.stdout, result.stderr):
                break
        assert result is not None
        if result.returncode != 0:
            raise CapabilityError(
                reason=f"keeper {' '.join(args)} failed (rc={result.returncode})",
                context={"stdout": result.stdout[-6000:], "stderr": result.stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            )
        stderr = (result.stderr or "").strip()
        if self._is_silent_failure(args, stdout=result.stdout, stderr=stderr):
            stderr_head = stderr[:200]
            raise CapabilityError(
                reason=f"keeper {' '.join(args)} silent-fail: {stderr_head}",
                context={"stdout": result.stdout[-400:], "stderr": result.stderr[-400:]},
                next_action="inspect the Commander output above and retry",
            )
        return result.stdout

    @staticmethod
    def _is_silent_failure(args: list[str], *, stdout: str, stderr: str) -> bool:
        if stdout.strip() or not stderr:
            return False
        if not any(args[: len(prefix)] == list(prefix) for prefix in _SILENT_FAIL_COMMANDS):
            return False
        return any(marker in stderr for marker in _SILENT_FAIL_MARKERS)

    # ------------------------------------------------------------------
    # In-process invocation of PAM commands that need a live Commander session.
    # ------------------------------------------------------------------

    def _run_pam_list_in_process(self, args: list[str]) -> str:
        """Run PAM list commands in-process so they share refreshable auth."""
        stdout = ""
        stderr = ""

        def run_once() -> str:
            nonlocal stdout, stderr
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            err_log_handler = logging.StreamHandler(buf_err)
            err_log_handler.setLevel(logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(err_log_handler)
            result: Any = None
            try:
                from keepercommander import api  # type: ignore[import-not-found]

                api.sync_down(params)
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    if args[:3] == ["pam", "gateway", "list"]:
                        from keepercommander.commands.discoveryrotation import (  # type: ignore
                            PAMGatewayListCommand,
                        )

                        result = PAMGatewayListCommand().execute(params, format="json")
                    elif args[:3] == ["pam", "config", "list"]:
                        from keepercommander.commands.discoveryrotation import (  # type: ignore
                            PAMConfigurationListCommand,
                        )

                        result = PAMConfigurationListCommand().execute(params, format="json")
                    else:
                        from keepercommander.commands.discoveryrotation import (  # type: ignore
                            PAMListRecordRotationCommand,
                        )

                        cmd = PAMListRecordRotationCommand()
                        parsed = vars(cmd.get_parser().parse_args(args[3:]))
                        result = cmd.execute(params, **parsed)
            finally:
                stdout = buf_out.getvalue()
                stderr = buf_err.getvalue()
                root_logger.removeHandler(err_log_handler)
            return result if isinstance(result, str) and result else stdout

        try:
            return self._with_keeper_session_refresh(run_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process keeper {' '.join(args)} failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _run_pam_project_in_process(self, args: list[str]) -> str:
        """Parse argv for pam project {import,extend} and call the
        Commander class directly with a logged-in KeeperParams. Returns
        whatever the command printed to stdout, so callers that greppy the
        output (e.g. for access_token) keep working.
        """
        subcmd = args[2]
        parsed = _parse_pam_project_args(args[3:])

        stdout = ""
        stderr = ""

        def run_once() -> str:
            nonlocal stdout, stderr
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            err_log_handler = logging.StreamHandler(buf_err)
            err_log_handler.setLevel(logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(err_log_handler)
            try:
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    if subcmd == "import":
                        from keepercommander.commands.pam_import.edit import (
                            PAMProjectImportCommand,
                        )

                        cmd = PAMProjectImportCommand()
                        cmd.execute(
                            params,
                            project_name=parsed.get("name"),
                            file_name=parsed.get("file"),
                            dry_run=parsed.get("dry_run", False),
                        )
                    else:
                        from keepercommander.commands.pam_import.extend import (
                            PAMProjectExtendCommand,
                        )

                        cmd = PAMProjectExtendCommand()
                        cmd.execute(
                            params,
                            config=parsed.get("config"),
                            file_name=parsed.get("file"),
                            dry_run=parsed.get("dry_run", False),
                        )
            finally:
                stdout = buf_out.getvalue()
                stderr = buf_err.getvalue()
                root_logger.removeHandler(err_log_handler)
            return stdout

        try:
            return self._with_keeper_session_refresh(run_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process keeper pam project {subcmd} failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _run_pam_rotation_edit_in_process(self, args: list[str]) -> str:
        """Run ``pam rotation edit`` against the cached Commander session."""
        stdout = ""
        stderr = ""

        def run_once() -> str:
            nonlocal stdout, stderr
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            err_log_handler = logging.StreamHandler(buf_err)
            err_log_handler.setLevel(logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(err_log_handler)
            try:
                from keepercommander import api  # type: ignore[import-not-found]
                from keepercommander.commands.discoveryrotation import (  # type: ignore[import-not-found]
                    PAMCreateRecordRotationCommand,
                )

                cmd = PAMCreateRecordRotationCommand()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    parsed = vars(cmd.get_parser().parse_args(args[3:]))
                    api.sync_down(params)
                    cmd.execute(params, **parsed)
            finally:
                stdout = buf_out.getvalue()
                stderr = buf_err.getvalue()
                root_logger.removeHandler(err_log_handler)
            return stdout

        try:
            return self._with_keeper_session_refresh(run_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process keeper pam rotation edit failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _run_ls_in_process(self, args: list[str]) -> str:
        """Run ``ls <pattern> --format json`` in-process so discover() shares apply auth.

        Mirrors :meth:`_run_pam_rotation_edit_in_process`: parse argv via the
        Commander command's own argparse, sync_down once, capture stdout.
        Output shape is identical to subprocess ``keeper ls --format json``
        because the same command class produces it.
        """
        stdout = ""
        stderr = ""

        def run_once() -> str:
            nonlocal stdout, stderr
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            err_log_handler = logging.StreamHandler(buf_err)
            err_log_handler.setLevel(logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(err_log_handler)
            try:
                from keepercommander import api  # type: ignore[import-not-found]
                from keepercommander.commands.folder import (  # type: ignore[import-not-found]
                    FolderListCommand,
                )

                cmd = FolderListCommand()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    parsed = vars(cmd.get_parser().parse_args(args[1:]))
                    api.sync_down(params)
                    buf_out.seek(0)
                    buf_out.truncate(0)
                    result = cmd.execute(params, **parsed)
                    if isinstance(result, str):
                        print(result, end="")
            finally:
                stdout = buf_out.getvalue()
                stderr = buf_err.getvalue()
                root_logger.removeHandler(err_log_handler)
            return stdout

        try:
            return self._with_keeper_session_refresh(run_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process keeper ls failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _run_record_get_in_process(self, args: list[str]) -> str:
        """Run ``get <uid> --format json`` in-process; same auth context as apply."""
        stdout = ""
        stderr = ""

        def run_once() -> str:
            nonlocal stdout, stderr
            params = self._get_keeper_params()
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            err_log_handler = logging.StreamHandler(buf_err)
            err_log_handler.setLevel(logging.WARNING)
            root_logger = logging.getLogger()
            root_logger.addHandler(err_log_handler)
            try:
                from keepercommander import api  # type: ignore[import-not-found]
                from keepercommander.commands.record import (  # type: ignore[import-not-found]
                    RecordGetUidCommand,
                )

                cmd = RecordGetUidCommand()
                with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                    parsed = vars(cmd.get_parser().parse_args(args[1:]))
                    api.sync_down(params)
                    buf_out.seek(0)
                    buf_out.truncate(0)
                    result = cmd.execute(params, **parsed)
                    if isinstance(result, str):
                        print(result, end="")
            finally:
                stdout = buf_out.getvalue()
                stderr = buf_err.getvalue()
                root_logger.removeHandler(err_log_handler)
            return stdout

        try:
            return self._with_keeper_session_refresh(run_once)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process keeper get failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc

    def _can_attempt_in_process_login(self) -> bool:
        """True when in-process Commander login is plausibly available.

        Checked before routing read-side commands (``ls``/``get``) through
        the in-process path. When False the dispatcher falls through to
        subprocess so plain installs (no helper, no env creds) keep working.
        """
        if self._keeper_params is not None:
            return True
        if self._keeper_login_attempted:
            return False
        if os.environ.get("KEEPER_SDK_LOGIN_HELPER"):
            return True
        env_creds = ("KEEPER_EMAIL", "KEEPER_PASSWORD", "KEEPER_TOTP_SECRET")
        if all(os.environ.get(v) for v in env_creds):
            return True
        return False

    def _with_keeper_session_refresh(self, operation: Callable[[], Any]) -> Any:
        """Run an in-process Commander operation, re-login once on session expiry."""
        try:
            return operation()
        except Exception as exc:
            if not _is_retryable_keeper_session_error(exc):
                raise
            self._invalidate_keeper_params()
        return operation()

    def _invalidate_keeper_params(self) -> None:
        self._keeper_params = None
        self._keeper_login_attempted = False

    def _get_keeper_params(self) -> Any:
        if self._keeper_params is not None:
            return self._keeper_params
        if self._keeper_login_attempted:
            raise CapabilityError(
                reason="in-process Commander login previously failed; cannot retry without a new provider",
                next_action="re-run with a valid admin config + KSM credentials available",
            )
        self._keeper_login_attempted = True

        # Resolution order:
        # 1. Setting KEEPER_SDK_LOGIN_HELPER=ksm triggers the in-tree KSM
        #    helper, which reads KEEPER_SDK_KSM_CREDS_RECORD_UID and pulls
        #    login/password/oneTimeCode from that KSM record.
        # 2. If KEEPER_SDK_LOGIN_HELPER points at a Python file, use it
        #    (custom flows — HSM-backed TOTP, device-approval queue).
        # 3. Otherwise fall back to the in-tree EnvLoginHelper reading
        #    KEEPER_EMAIL / KEEPER_PASSWORD / KEEPER_TOTP_SECRET.
        # The KEEPER_SDK_LOGIN_HELPER path is validated but the env-var
        # fallback kicks in only when the var is unset — an operator
        # pointing at a missing file gets a loud error (the point of
        # setting the var is to say "do not use the default").
        from keeper_sdk.auth import (
            EnvLoginHelper,
            KsmLoginHelper,
            LoginHelper,
            load_helper_from_path,
        )

        helper_path = os.environ.get("KEEPER_SDK_LOGIN_HELPER")
        helper: LoginHelper
        try:
            if helper_path == "ksm":
                helper = KsmLoginHelper()
            elif helper_path:
                helper = load_helper_from_path(helper_path)
            else:
                helper = EnvLoginHelper()
            creds = helper.load_keeper_creds()
            email = creds["email"] if isinstance(creds, dict) else creds[0]
            password = creds["password"] if isinstance(creds, dict) else creds[1]
            totp_secret = creds["totp_secret"] if isinstance(creds, dict) else creds[2]
            extra = {
                k: v
                for k, v in (creds.items() if isinstance(creds, dict) else [])
                if k not in {"email", "password", "totp_secret"}
            }
            params = helper.keeper_login(email, password, totp_secret, **extra)
        except CapabilityError:
            raise
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process Commander login failed: {type(exc).__name__}: {exc}",
                next_action=(
                    "verify credentials are reachable; see docs/LOGIN.md for the "
                    "helper contract + a 30-line skeleton"
                ),
            ) from exc
        self._keeper_params = params
        return params


def _is_retryable_keeper_session_error(exc: BaseException) -> bool:
    """True when *exc* or its ``__cause__`` chain signals a refreshable session."""
    parts: list[str] = []
    cur: BaseException | None = exc
    for _ in range(8):
        if cur is None:
            break
        result_code = getattr(cur, "result_code", None)
        if isinstance(result_code, str) and result_code == _SESSION_EXPIRED_CODE:
            return True
        parts.append(f"{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or getattr(cur, "original_error", None)
    text = "\n".join(parts).casefold()
    return _SESSION_EXPIRED_CODE in text or ("session token" in text and "expired" in text)


def _is_retryable_keeper_session_text(stdout: str | None, stderr: str | None) -> bool:
    text = f"{stdout or ''}\n{stderr or ''}".casefold()
    return _SESSION_EXPIRED_CODE in text or ("session token" in text and "expired" in text)


def build_post_import_tuning_argvs(
    record: str,
    resource: Mapping[str, Any],
    *,
    resolved_refs: Mapping[str, str] | None = None,
) -> list[list[str]]:
    """Build Commander argv for safe post-import tuning fields.

    Pure helper only: it does not resolve refs, inspect live records, or execute
    Commander. ``resolved_refs`` must map manifest ``*_uid_ref`` values to the
    UID/path strings accepted by the target Commander edit command.
    """
    if not record:
        raise ValueError("record is required to build post-import tuning argv")

    refs = resolved_refs or {}
    resource_type = resource.get("type")
    if resource_type == "pamRemoteBrowser":
        argv = _build_pam_rbi_edit_argv(record, resource, refs)
    else:
        argv = _build_pam_connection_edit_argv(record, resource, refs)
    return [argv] if argv is not None else []


def _resolve_post_import_tuning_argvs(
    manifest: Any,
    *,
    plan: Plan,
    live_records: list[LiveRecord],
    changes: list[Change],
) -> dict[str, list[list[str]]]:
    """Resolve and build post-import tuning argv for changed resources.

    Pure resolver: no Commander calls. It requires live rediscovery because
    create rows do not carry Keeper UIDs until after import / extend runs.
    """
    source = _manifest_source_dict(manifest)
    if not source:
        return {}
    resources = _manifest_resources_by_ref(source)
    refs = _RotationRefResolver(plan=plan, live_records=live_records)
    argvs_by_ref: dict[str, list[list[str]]] = {}

    for change in changes:
        if not change.uid_ref:
            continue
        resource = resources.get(change.uid_ref)
        if resource is None or not _has_post_import_tuning_fields(resource):
            continue
        try:
            record_uid = refs.resolve(
                uid_ref=change.uid_ref,
                title=change.title,
                resource_type=change.resource_type,
                role="post-import tuning record",
            )
            resolved_refs = _resolve_post_import_tuning_refs(source, resource, refs)
            argvs = build_post_import_tuning_argvs(
                record_uid,
                resource,
                resolved_refs=resolved_refs,
            )
        except ValueError as exc:
            raise CapabilityError(
                reason=f"post-import tuning could not resolve refs: {exc}",
                uid_ref=change.uid_ref,
                resource_type=change.resource_type,
                next_action=(
                    "ensure every *_uid_ref used by pam_settings is declared in the "
                    "manifest and visible after import, then re-run apply"
                ),
            ) from exc
        if argvs:
            argvs_by_ref[change.uid_ref] = argvs
    return argvs_by_ref


def _resolve_post_import_tuning_refs(
    source: Mapping[str, Any],
    resource: Mapping[str, Any],
    refs: _RotationRefResolver,
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for uid_ref in _post_import_tuning_uid_refs(resource):
        resource_type, title = _desired_identity(source, uid_ref)
        resolved[uid_ref] = refs.resolve(
            uid_ref=uid_ref,
            title=title,
            resource_type=resource_type or "resource",
            role="post-import tuning reference",
        )
    return resolved


def _preview_post_import_tuning_argvs(change: Change, manifest: Any) -> list[list[str]]:
    if not change.uid_ref:
        return []
    resource = _manifest_resources_by_ref(_manifest_source_dict(manifest)).get(change.uid_ref)
    if resource is None or not _has_post_import_tuning_fields(resource):
        return []
    resolved_refs = {
        uid_ref: f"<uid_ref:{uid_ref}>" for uid_ref in _post_import_tuning_uid_refs(resource)
    }
    try:
        return build_post_import_tuning_argvs(
            f"<record:{change.uid_ref}>",
            resource,
            resolved_refs=resolved_refs,
        )
    except ValueError:
        return []


def _preview_rotation_argvs_by_ref(manifest: Any) -> dict[str, list[list[str]]]:
    source = _manifest_source_dict(manifest)
    if not source:
        return {}
    argvs_by_ref: dict[str, list[list[str]]] = {}
    try:
        _reject_top_level_user_rotation(source)
    except ValueError:
        return {}

    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        parent_ref = _non_empty_str(resource.get("uid_ref"))
        parent_title = _non_empty_str(resource.get("title"))
        if not (parent_ref or parent_title):
            continue
        try:
            config_ref, config_title = _rotation_config_ref(source, resource)
        except ValueError:
            continue
        config_uid = _preview_ref(config_ref, config_title, role="config")
        resource_uid = _preview_ref(parent_ref, parent_title, role="resource")

        for user in resource.get("users") or []:
            if (
                not isinstance(user, Mapping)
                or user.get("type") != "pamUser"
                or user.get("rotation_settings") is None
            ):
                continue
            user_ref = _non_empty_str(user.get("uid_ref"))
            user_title = _non_empty_str(user.get("title"))
            if not (user_ref or user_title):
                continue
            argv = _build_pam_rotation_edit_args(
                record_uid=_preview_ref(user_ref, user_title, role="record"),
                settings=user["rotation_settings"],
                resource_uid=resource_uid,
                config_uid=config_uid,
                admin_uid=_preview_rotation_admin_uid(user["rotation_settings"]),
            )
            argvs_by_ref.setdefault(user_ref or user_title or "", []).append(argv)
    return argvs_by_ref


def _preview_ref(uid_ref: str | None, title: str | None, *, role: str) -> str:
    if uid_ref:
        if role == "record":
            return f"<record:{uid_ref}>"
        return f"<uid_ref:{uid_ref}>"
    if title:
        return f"<{role}:{title}>"
    return f"<{role}:unresolved>"


def _preview_rotation_admin_uid(settings: Any) -> str | None:
    data = _model_dump_dict(settings)
    admin_ref = next(
        (
            _non_empty_str(data.get(key))
            for key in (
                "admin_uid_ref",
                "admin_user_uid_ref",
                "administrative_credentials_uid_ref",
            )
            if _non_empty_str(data.get(key))
        ),
        None,
    )
    return f"<uid_ref:{admin_ref}>" if admin_ref else None


def _manifest_source_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python", exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return value if isinstance(value, dict) else {}


def _manifest_resources_by_ref(source: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    resources: dict[str, Mapping[str, Any]] = {}
    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        uid_ref = _non_empty_str(resource.get("uid_ref"))
        if uid_ref:
            resources[uid_ref] = resource
    return resources


class _NestedRotationUserTargets:
    def __init__(self, *, refs: set[str], titles: set[str]) -> None:
        self.refs = refs
        self.titles = titles


def _nested_rotation_user_targets(source: Mapping[str, Any]) -> _NestedRotationUserTargets:
    refs: set[str] = set()
    titles: set[str] = set()
    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        for user in resource.get("users") or []:
            if (
                not isinstance(user, Mapping)
                or user.get("type") != "pamUser"
                or user.get("rotation_settings") is None
            ):
                continue
            uid_ref = _non_empty_str(user.get("uid_ref"))
            title = _non_empty_str(user.get("title"))
            if uid_ref:
                refs.add(uid_ref)
            if title:
                titles.add(title)
    return _NestedRotationUserTargets(refs=refs, titles=titles)


def _rotation_settings_from_readback(data: Any, *, uid: str) -> dict[str, Any]:
    for row in _rotation_readback_rows(data):
        row_uid = _first_non_empty(row, ("record_uid", "recordUid", "Record UID", "uid", "record"))
        if row_uid and row_uid != uid:
            continue
        settings = _rotation_settings_from_row(row)
        if settings:
            return settings
    return {}


def _rotation_readback_rows(data: Any) -> list[Mapping[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if not isinstance(data, Mapping):
        return []
    for key in ("rotations", "rotation_schedules", "schedules", "records", "items", "data"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    return [data]


def _rotation_settings_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    nested = row.get("rotation_settings") or row.get("rotationSettings")
    source: dict[str, Any] = dict(row)
    if isinstance(nested, Mapping):
        source.update(nested)

    settings: dict[str, Any] = {}
    rotation = _first_non_empty(
        source,
        (
            "rotation",
            "rotation_profile",
            "rotationProfile",
            "Rotation Profile",
            "profile",
            "profile_name",
        ),
    )
    if rotation:
        settings["rotation"] = rotation

    enabled = _rotation_enabled_value(
        _first_present(
            source,
            (
                "enabled",
                "rotation_enabled",
                "rotationEnabled",
                "Rotation Enabled",
                "Enabled",
                "status",
            ),
        )
    )
    if enabled:
        settings["enabled"] = enabled

    schedule = _rotation_schedule_from_row(source)
    if schedule:
        settings["schedule"] = schedule

    complexity = _first_non_empty(
        source,
        ("password_complexity", "passwordComplexity", "complexity", "Password Complexity"),
    )
    if complexity:
        settings["password_complexity"] = complexity
    return settings


def _first_present(source: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


def _first_non_empty(source: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None or value == "":
            continue
        return str(value)
    return None


def _rotation_enabled_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on", "enabled", "active"}:
        return "on"
    if text in {"false", "0", "no", "off", "disabled", "inactive"}:
        return "off"
    return text or None


def _rotation_schedule_from_row(row: Mapping[str, Any]) -> dict[str, str] | None:
    schedule = row.get("schedule") or row.get("Schedule")
    if isinstance(schedule, Mapping):
        schedule_type = str(schedule.get("type") or "").strip()
        if schedule_type.casefold() == "on-demand":
            return {"type": "on-demand"}
        cron = schedule.get("cron") or schedule.get("expression")
        if cron:
            return {"type": "CRON", "cron": str(cron)}
    if _truthy(row.get("no_schedule")) or _truthy(row.get("noSchedule")):
        return {"type": "on-demand"}

    cron = _first_non_empty(
        row,
        ("cron", "schedule_cron", "scheduleCron", "schedule_data", "scheduleData"),
    )
    if cron:
        parsed = _rotation_cron_from_string(cron)
        if parsed:
            return {"type": "CRON", "cron": parsed}
    if isinstance(schedule, str):
        if "manual" in schedule.casefold() or "on-demand" in schedule.casefold():
            return {"type": "on-demand"}
        parsed = _rotation_cron_from_string(schedule)
        if parsed:
            return {"type": "CRON", "cron": parsed}
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in _TRUTHY_ENV_VALUES


def _rotation_cron_from_string(value: str) -> str | None:
    text = value.strip()
    if text.startswith("RotateActionJob|"):
        text = text.split("|", 1)[1]
        parts = text.split(".")
        if len(parts) >= 2 and parts[0].casefold() == "cron":
            text = parts[1]
    parts = text.split()
    if len(parts) in {5, 6, 7}:
        return text
    return None


_CONNECTION_TUNING_OPTION_KEYS = frozenset(
    {
        "connections",
        "graphical_session_recording",
        "text_session_recording",
    }
)
_CONNECTION_TUNING_CONNECTION_KEYS = frozenset(
    {
        "administrative_credentials_uid_ref",
        "launch_credentials_uid_ref",
        "protocol",
        "port",
        "recording_include_keys",
    }
)
_RBI_TUNING_OPTION_KEYS = frozenset(
    {
        "remote_browser_isolation",
        "graphical_session_recording",
    }
)
_RBI_TUNING_CONNECTION_KEYS = frozenset(
    {
        "autofill_credentials_uid_ref",
        "autofill_targets",
        "allow_url_manipulation",
        "allowed_url_patterns",
        "allowed_resource_url_patterns",
        "recording_include_keys",
        "disable_copy",
        "disable_paste",
        "ignore_server_cert",
    }
)


def _has_post_import_tuning_fields(resource: Mapping[str, Any]) -> bool:
    pam_settings = _as_mapping(resource.get("pam_settings"))
    options = _as_mapping(pam_settings.get("options"))
    connection = _as_mapping(pam_settings.get("connection"))
    if resource.get("type") == "pamRemoteBrowser":
        option_keys = _RBI_TUNING_OPTION_KEYS
        connection_keys = _RBI_TUNING_CONNECTION_KEYS
    else:
        option_keys = _CONNECTION_TUNING_OPTION_KEYS
        connection_keys = _CONNECTION_TUNING_CONNECTION_KEYS
    return any(key in options for key in option_keys) or any(
        key in connection for key in connection_keys
    )


def _post_import_tuning_uid_refs(resource: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    config_ref = _non_empty_str(resource.get("pam_configuration_uid_ref"))
    if config_ref:
        refs.append(config_ref)
    pam_settings = _as_mapping(resource.get("pam_settings"))
    connection = _as_mapping(pam_settings.get("connection"))
    keys: tuple[str, ...]
    if resource.get("type") == "pamRemoteBrowser":
        keys = ("autofill_credentials_uid_ref",)
    else:
        keys = (
            "administrative_credentials_uid_ref",
            "launch_credentials_uid_ref",
        )
    for key in keys:
        uid_ref = _non_empty_str(connection.get(key))
        if uid_ref and uid_ref not in refs:
            refs.append(uid_ref)
    return refs


def build_pam_rotation_edit_argvs(
    manifest: Any,
    *,
    plan: Plan | None = None,
    live_records: list[LiveRecord] | None = None,
) -> list[list[str]]:
    """Build Commander argv for nested ``pamUser`` rotation settings.

    Pure resolver: it never calls Keeper. ``apply_plan`` only uses it behind
    the Commander-only ``DSK_EXPERIMENTAL_ROTATION_APPLY`` opt-in while the
    public provider-capability and preview gates remain in place. Nested users
    need three proven live UIDs before a rotation edit is safe: the user
    record, the parent resource record, and the PAM config.
    """
    source = _manifest_dict(manifest)
    _reject_top_level_user_rotation(source)

    refs = _RotationRefResolver(plan=plan, live_records=live_records or [])
    argvs: list[list[str]] = []
    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        rotating_users = [
            user
            for user in resource.get("users") or []
            if isinstance(user, Mapping)
            and user.get("type") == "pamUser"
            and user.get("rotation_settings") is not None
        ]
        if not rotating_users:
            continue

        parent_ref = _non_empty_str(resource.get("uid_ref"))
        parent_title = _non_empty_str(resource.get("title"))
        parent_type = _non_empty_str(resource.get("type")) or "resource"
        if not parent_ref or not parent_title:
            raise ValueError(
                "resources[].users[].rotation_settings requires a parent resource with uid_ref and title"
            )

        config_ref, config_title = _rotation_config_ref(source, resource)
        config_uid = refs.resolve(
            uid_ref=config_ref,
            title=config_title,
            resource_type="pam_configuration",
            role="PAM configuration",
        )
        resource_uid = refs.resolve(
            uid_ref=parent_ref,
            title=parent_title,
            resource_type=parent_type,
            role="parent resource",
        )

        for user in rotating_users:
            settings = user["rotation_settings"]
            user_ref = _non_empty_str(user.get("uid_ref"))
            user_title = _non_empty_str(user.get("title"))
            user_uid = refs.resolve(
                uid_ref=user_ref,
                title=user_title,
                resource_type="pamUser",
                role="nested pamUser",
            )
            admin_uid = _rotation_admin_uid(settings, refs, source)
            argvs.append(
                _build_pam_rotation_edit_args(
                    record_uid=user_uid,
                    settings=settings,
                    resource_uid=resource_uid,
                    config_uid=config_uid,
                    admin_uid=admin_uid,
                )
            )
    return argvs


class _RotationRefResolver:
    def __init__(self, *, plan: Plan | None, live_records: list[LiveRecord]) -> None:
        self._plan_by_ref: dict[str, Change] = {}
        self._plan_by_title: dict[tuple[str, str], Change] = {}
        if plan is not None:
            for change in plan.changes:
                if change.uid_ref:
                    self._plan_by_ref[change.uid_ref] = change
                self._plan_by_title[(change.resource_type, change.title)] = change

        self._live_by_ref: dict[str, list[LiveRecord]] = {}
        self._live_by_title, self._live_by_any_title = _index_live_records_for_title_matching(
            live_records
        )
        for live in live_records:
            marker_ref = _non_empty_str((live.marker or {}).get("uid_ref"))
            if marker_ref:
                self._live_by_ref.setdefault(marker_ref, []).append(live)

    def resolve(
        self,
        *,
        uid_ref: str | None,
        title: str | None,
        resource_type: str,
        role: str,
    ) -> str:
        if uid_ref:
            uid = self._resolve_live_ref(uid_ref, role)
            if uid:
                return uid
            change = self._plan_by_ref.get(uid_ref)
            if change and change.keeper_uid:
                return change.keeper_uid

        if title:
            uid = self._resolve_live_title(resource_type, title, role)
            if uid:
                return uid
            change = self._plan_by_title.get((resource_type, title))
            if change and change.keeper_uid:
                return change.keeper_uid

        ident = f"uid_ref='{uid_ref}'" if uid_ref else f"title='{title}'"
        raise ValueError(
            f"missing live {role} ({ident}, type={resource_type}); "
            "run import/apply first, then pass discovered live records with Keeper UIDs"
        )

    def _resolve_live_ref(self, uid_ref: str, role: str) -> str | None:
        matches = self._live_by_ref.get(uid_ref, [])
        if len(matches) > 1:
            raise ValueError(
                f"duplicate live {role} match for uid_ref '{uid_ref}': "
                f"{[item.keeper_uid for item in matches]}"
            )
        return matches[0].keeper_uid if matches else None

    def _resolve_live_title(self, resource_type: str, title: str, role: str) -> str | None:
        matches = _live_matches_by_identity(
            live_by_key=self._live_by_title,
            live_by_title=self._live_by_any_title,
            resource_type=resource_type,
            title=title,
        )
        if len(matches) > 1:
            raise ValueError(
                f"duplicate live {role} match for title '{title}' ({resource_type}): "
                f"{[item.keeper_uid for item in matches]}"
            )
        return matches[0].keeper_uid if matches else None


def _index_live_records_for_title_matching(
    live_records: list[LiveRecord],
) -> tuple[dict[tuple[str, str], list[LiveRecord]], dict[str, list[LiveRecord]]]:
    live_by_key: dict[tuple[str, str], list[LiveRecord]] = {}
    live_by_title: dict[str, list[LiveRecord]] = {}
    for live in live_records:
        live_by_key.setdefault((live.resource_type, live.title), []).append(live)
        if live.title:
            live_by_title.setdefault(live.title, []).append(live)
    return live_by_key, live_by_title


def _live_matches_by_identity(
    *,
    live_by_key: dict[tuple[str, str], list[LiveRecord]],
    live_by_title: dict[str, list[LiveRecord]],
    resource_type: str,
    title: str,
) -> list[LiveRecord]:
    exact = live_by_key.get((resource_type, title), [])
    if exact:
        return exact
    return live_by_title.get(title, []) if title else []


def _build_pam_connection_edit_argv(
    record: str, resource: Mapping[str, Any], refs: Mapping[str, str]
) -> list[str] | None:
    pam_settings = _as_mapping(resource.get("pam_settings"))
    options = _as_mapping(pam_settings.get("options"))
    connection = _as_mapping(pam_settings.get("connection"))

    argv = ["pam", "connection", "edit"]
    _append_ref(argv, "--configuration", resource.get("pam_configuration_uid_ref"), refs)
    _append_option(argv, "--connections", options.get("connections"))
    _append_option(
        argv,
        "--connections-recording",
        options.get("graphical_session_recording"),
    )
    _append_option(argv, "--typescript-recording", options.get("text_session_recording"))
    _append_ref(
        argv,
        "--admin-user",
        connection.get("administrative_credentials_uid_ref"),
        refs,
    )
    _append_ref(argv, "--launch-user", connection.get("launch_credentials_uid_ref"), refs)
    _append_option(argv, "--protocol", connection.get("protocol"))
    _append_option(argv, "--connections-override-port", connection.get("port"))
    _append_option(argv, "--key-events", _on_off(connection.get("recording_include_keys")))

    if len(argv) == 3:
        return None
    argv.append(record)
    return argv


def _build_pam_rbi_edit_argv(
    record: str, resource: Mapping[str, Any], refs: Mapping[str, str]
) -> list[str] | None:
    pam_settings = _as_mapping(resource.get("pam_settings"))
    options = _as_mapping(pam_settings.get("options"))
    connection = _as_mapping(pam_settings.get("connection"))

    argv = ["pam", "rbi", "edit", "--record", record]
    _append_ref(argv, "--configuration", resource.get("pam_configuration_uid_ref"), refs)
    _append_option(
        argv,
        "--remote-browser-isolation",
        options.get("remote_browser_isolation"),
    )
    _append_option(
        argv,
        "--connections-recording",
        options.get("graphical_session_recording"),
    )
    _append_ref(
        argv,
        "--autofill-credentials",
        connection.get("autofill_credentials_uid_ref"),
        refs,
    )
    _append_repeated(argv, "--autofill-targets", connection.get("autofill_targets"))
    _append_option(
        argv,
        "--allow-url-navigation",
        _on_off(connection.get("allow_url_manipulation")),
    )
    _append_repeated(argv, "--allowed-urls", connection.get("allowed_url_patterns"))
    _append_repeated(
        argv,
        "--allowed-resource-urls",
        connection.get("allowed_resource_url_patterns"),
    )
    _append_option(argv, "--key-events", _on_off(connection.get("recording_include_keys")))
    _append_option(argv, "--allow-copy", _inverse_on_off(connection.get("disable_copy")))
    _append_option(argv, "--allow-paste", _inverse_on_off(connection.get("disable_paste")))
    _append_option(argv, "--ignore-server-cert", _on_off(connection.get("ignore_server_cert")))

    if len(argv) == 5:
        return None
    return argv


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _on_off(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _inverse_on_off(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "off" if value else "on"
    if value == "on":
        return "off"
    if value == "off":
        return "on"
    return str(value)


def _append_option(argv: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    rendered = str(value)
    if rendered:
        argv.extend([flag, rendered])


def _append_ref(
    argv: list[str],
    flag: str,
    uid_ref: Any,
    refs: Mapping[str, str],
) -> None:
    if uid_ref is None:
        return
    if not isinstance(uid_ref, str) or not uid_ref:
        return
    resolved = refs.get(uid_ref)
    if not resolved:
        raise ValueError(f"unresolved uid_ref '{uid_ref}' for {flag}")
    argv.extend([flag, resolved])


def _append_repeated(argv: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list | tuple):
        values = [values]
    for item in values:
        rendered = str(item)
        if rendered:
            argv.extend([flag, rendered])


_UNSUPPORTED_CAPABILITY_HINTS: tuple[tuple[str, str, str], ...] = (
    # (dotted manifest path fragment, human name, Commander hook the SDK
    # should eventually drive to fulfil this capability)
    (
        "default_rotation_schedule",
        "pam_configurations[].default_rotation_schedule",
        "no confirmed Commander CLI setter; pam rotation edit --schedule-config only reads config default",
    ),
    (
        "jit_settings",
        "jit_settings (per-resource or per-config)",
        "pam_launch/jit.py + DAG jit_settings writer",
    ),
    ("rotation_schedule", "rotation_schedule (embedded)", "pam rotation edit --schedulecron"),
)


def _model_dump_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python", exclude_none=True)
        return dumped if isinstance(dumped, dict) else {}
    return value if isinstance(value, dict) else {}


def _manifest_dict(value: Any) -> dict[str, Any]:
    data = _model_dump_dict(value)
    if not data:
        raise ValueError("manifest data is required to build pam rotation edit argv")
    return data


def _non_empty_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _reject_top_level_user_rotation(source: Mapping[str, Any]) -> None:
    for user in source.get("users") or []:
        if (
            isinstance(user, Mapping)
            and user.get("type") == "pamUser"
            and user.get("rotation_settings")
        ):
            ident = user.get("uid_ref") or user.get("title") or "<unknown>"
            raise ValueError(
                f"top-level users[].rotation_settings is unsupported for pamUser '{ident}'; "
                "nest the pamUser under resources[].users[] so the parent resource UID can be resolved"
            )


def _has_top_level_user_rotation(source: Mapping[str, Any]) -> bool:
    return any(
        isinstance(user, Mapping)
        and user.get("type") == "pamUser"
        and user.get("rotation_settings") is not None
        for user in source.get("users") or []
    )


def _has_nested_user_rotation(source: Mapping[str, Any]) -> bool:
    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        for user in resource.get("users") or []:
            if (
                isinstance(user, Mapping)
                and user.get("type") == "pamUser"
                and user.get("rotation_settings") is not None
            ):
                return True
    return False


def _rotation_config_ref(
    source: Mapping[str, Any],
    resource: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    config_ref = _non_empty_str(resource.get("pam_configuration_uid_ref"))
    configs = [cfg for cfg in source.get("pam_configurations") or [] if isinstance(cfg, Mapping)]
    if config_ref:
        config = next((cfg for cfg in configs if cfg.get("uid_ref") == config_ref), None)
        config_title = _non_empty_str(config.get("title")) if config is not None else None
        return config_ref, config_title
    if len(configs) == 1:
        config = configs[0]
        return _non_empty_str(config.get("uid_ref")), _non_empty_str(config.get("title"))
    raise ValueError(
        f"missing parent PAM configuration for resource '{resource.get('uid_ref') or resource.get('title')}'; "
        "set resources[].pam_configuration_uid_ref or declare exactly one pam_configurations[] entry"
    )


def _rotation_admin_uid(
    settings: Any,
    refs: _RotationRefResolver,
    source: Mapping[str, Any],
) -> str | None:
    data = _model_dump_dict(settings)
    admin_ref = next(
        (
            _non_empty_str(data.get(key))
            for key in (
                "admin_uid_ref",
                "admin_user_uid_ref",
                "administrative_credentials_uid_ref",
            )
            if _non_empty_str(data.get(key))
        ),
        None,
    )
    if not admin_ref:
        return None
    admin_type, admin_title = _desired_identity(source, admin_ref)
    return refs.resolve(
        uid_ref=admin_ref,
        title=admin_title,
        resource_type=admin_type or "pamUser",
        role="rotation admin user",
    )


def _desired_identity(source: Mapping[str, Any], uid_ref: str) -> tuple[str | None, str | None]:
    for cfg in source.get("pam_configurations") or []:
        if isinstance(cfg, Mapping) and cfg.get("uid_ref") == uid_ref:
            return "pam_configuration", _non_empty_str(cfg.get("title"))
    for resource in source.get("resources") or []:
        if not isinstance(resource, Mapping):
            continue
        if resource.get("uid_ref") == uid_ref:
            return _non_empty_str(resource.get("type")), _non_empty_str(resource.get("title"))
        for user in resource.get("users") or []:
            if isinstance(user, Mapping) and user.get("uid_ref") == uid_ref:
                return _non_empty_str(user.get("type")) or "pamUser", _non_empty_str(
                    user.get("title")
                )
    for user in source.get("users") or []:
        if isinstance(user, Mapping) and user.get("uid_ref") == uid_ref:
            return _non_empty_str(user.get("type")) or "pamUser", _non_empty_str(user.get("title"))
    return None, None


def _has_resource_rotation(source: Mapping[str, Any]) -> bool:
    for resource in source.get("resources") or []:
        if isinstance(resource, Mapping) and resource.get("rotation_settings") is not None:
            return True
    return False


def _contains_key(node: Any, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_contains_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_contains_key(item, key) for item in node)
    return False


def _rotation_schedule_args(schedule: Any) -> list[str]:
    data = _model_dump_dict(schedule)
    schedule_type = str(data.get("type") or "").strip().lower()
    if schedule_type == "on-demand":
        return ["--on-demand"]
    if schedule_type == "cron" and data.get("cron"):
        return ["--schedulecron", str(data["cron"])]
    return []


def _build_pam_rotation_edit_args(
    *,
    record_uid: str,
    settings: Any,
    resource_uid: str | None = None,
    config_uid: str | None = None,
    admin_uid: str | None = None,
    schedule_only: bool = False,
    force: bool = True,
) -> list[str]:
    """Map declarative rotation settings to Commander's `pam rotation edit` argv.

    Pure helper only. `apply_plan` calls it only behind the Commander-only
    `DSK_EXPERIMENTAL_ROTATION_APPLY` opt-in.
    """
    data = _model_dump_dict(settings)
    args = ["pam", "rotation", "edit", "--record", record_uid]
    if config_uid:
        args += ["--config", config_uid]
    if resource_uid:
        args += ["--resource", resource_uid]
    if admin_uid:
        args += ["--admin-user", admin_uid]
    if data.get("rotation"):
        args += ["--rotation-profile", str(data["rotation"])]
    args += _rotation_schedule_args(data.get("schedule"))
    if data.get("password_complexity"):
        args += ["--complexity", str(data["password_complexity"])]
    enabled = str(data.get("enabled") or "").strip().lower()
    if enabled == "on":
        args.append("--enable")
    elif enabled == "off":
        args.append("--disable")
    if schedule_only:
        args.append("--schedule-only")
    if force:
        args.append("--force")
    return args


def _detect_unsupported_capabilities(
    manifest: Any,
    *,
    allow_nested_rotation: bool = False,
) -> list[str]:
    """Return human-readable reasons the manifest exceeds this provider.

    Pure detector — does not raise. Returns a list of strings suitable for
    CONFLICT rows in a plan or for a late-apply CapabilityError. Handles
    both ``dict`` manifests (the provider's normalised form) and Pydantic
    ``Manifest`` instances (what the CLI has on hand before building a
    plan); callers pass whichever is convenient.
    """
    if manifest is None:
        return []
    if hasattr(manifest, "model_dump"):
        source = manifest.model_dump(mode="python", exclude_none=True)
    elif isinstance(manifest, dict):
        source = manifest
    else:
        return []

    if source.get("schema") == "keeper-vault.v1" or source.get("vault_schema") == "keeper-vault.v1":
        return []

    hits: list[str] = []

    gateways = source.get("gateways")
    if isinstance(gateways, list):
        for gateway in gateways:
            if isinstance(gateway, dict) and gateway.get("mode") == "create":
                hits.append(
                    f"gateway '{gateway.get('uid_ref') or gateway.get('name')}': "
                    "mode: create is not implemented (use Commander `pam gateway new "
                    "--application <ksm_app> --config-init json` and switch to "
                    "mode: reference_existing)"
                )

    if _has_top_level_user_rotation(source):
        hits.append(
            "top-level users[].rotation_settings is not implemented for pamUser "
            "(Commander hook needs a parent resource; nest the pamUser under resources[].users[])"
        )
    if _has_resource_rotation(source):
        hits.append(
            "resources[].rotation_settings is not implemented "
            "(Commander hook for resource rotation requires a proven mapping)"
        )
    if _has_nested_user_rotation(source) and not allow_nested_rotation:
        hits.append(
            "resources[].users[].rotation_settings is not implemented "
            "(Commander hook: `pam rotation edit --record / --resource / --schedulecron / --on-demand`; "
            f"offline experimental path requires {_ROTATION_APPLY_ENV_VAR}=1)"
        )

    for needle, human, hook in _UNSUPPORTED_CAPABILITY_HINTS:
        if _contains_key(source, needle):
            hits.append(f"{human} is not implemented (Commander hook: `{hook}`)")

    return hits


def _rotation_apply_is_enabled() -> bool:
    raw = os.environ.get(_ROTATION_APPLY_ENV_VAR, "")
    return raw.strip().lower() in _TRUTHY_ENV_VALUES


def _argv_value(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


__all__ = [
    "CommanderCliProvider",
    "build_pam_rotation_edit_argvs",
    "build_post_import_tuning_argvs",
]
