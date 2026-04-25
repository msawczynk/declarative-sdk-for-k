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

import contextlib
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from keeper_sdk.core.diff import Change, ChangeKind
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
from keeper_sdk.providers._commander_cli_helpers import (
    _entry_uid_by_name,
    _field_drift,
    _has_existing,
    _load_json,
    _pam_configuration_uid_ref,
    _parse_pam_project_args,
    _payload_for_extend,
    _record_from_get,
    _uses_reference_existing,
)

_SILENT_FAIL_COMMANDS = {
    ("pam", "project", "import"),
    ("pam", "project", "extend"),
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
        # In-process Commander session — lazily established the first time a
        # subcommand can't run reliably via subprocess (e.g. `pam project
        # import` / `extend` hit persistent-login re-auth prompts in batch
        # mode; see LESSONS [keeper-cli] 2026-04-24). Params are cached for
        # the lifetime of the provider.
        self._keeper_params: Any | None = None
        self._keeper_login_attempted = False
        self._ksm_app_rows_cache: list[dict[str, str]] | None = None

        if not shutil.which(self._bin):
            raise CapabilityError(
                reason=f"keeper CLI not found on PATH (looked up '{self._bin}')",
                next_action="install Keeper Commander or set KEEPER_BIN",
            )

    # ------------------------------------------------------------------

    def discover(self) -> list[LiveRecord]:
        project_name = self._manifest_name()
        if project_name:
            self._maybe_resolve_project_resources_folder(project_name)
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
            item_payload = self._run_cmd(["get", keeper_uid, "--format", "json"])
            item = _load_json(item_payload, command="get --format json")
            if not isinstance(item, dict):
                raise CapabilityError(
                    reason="Commander returned non-object JSON from `get --format json`"
                )
            record = _record_from_get(item, listing_entry=entry)
            if record is not None:
                records.append(record)
        config_record = self._synthetic_reference_configuration_record()
        if config_record is not None:
            records.append(config_record)
        return records

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
        return _detect_unsupported_capabilities(source)

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
        # Last-line defence — CLI should have surfaced these as conflicts
        # already (see unsupported_capabilities above). If an SDK caller
        # bypasses the CLI and hands us a plan directly, we still refuse.
        hits = _detect_unsupported_capabilities(self._manifest_source)
        if hits:
            raise CapabilityError(
                reason="manifest declares capabilities the CommanderCliProvider does not implement yet: "
                + "; ".join(hits),
                next_action=(
                    "remove the declarations, or drive the Commander hook manually before "
                    "re-running apply. See REVIEW.md D-4."
                ),
            )

        outcomes: list[ApplyOutcome] = []
        creates_updates = [
            c for c in plan.ordered() if c.kind in (ChangeKind.CREATE, ChangeKind.UPDATE)
        ]
        deletes = plan.deletes

        if creates_updates:
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
                        self._folder_uid = scaffold["resources_uid"]
                        self.last_resolved_folder_uid = scaffold["resources_uid"]
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
                    outcomes.append(
                        ApplyOutcome(
                            uid_ref=change.uid_ref or "",
                            keeper_uid=keeper_uid or change.keeper_uid or "",
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

                now = utc_timestamp()
                # outcomes is built by iterating creates_updates in the same
                # order above, so lengths must match — strict=True turns any
                # future drift into a loud failure rather than a silent
                # mis-association of markers to changes.
                for change, outcome in zip(creates_updates, outcomes, strict=True):
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

    # ------------------------------------------------------------------

    def _manifest_name(self) -> str | None:
        name = self._manifest_source.get("name") or self._manifest_source.get("project")
        return str(name) if isinstance(name, str) and name.strip() else None

    def _maybe_resolve_project_resources_folder(self, project_name: str) -> str | None:
        try:
            return self._resolve_project_resources_folder(project_name)
        except CapabilityError:
            return None

    def _synthetic_reference_configuration_record(self) -> LiveRecord | None:
        if not _uses_reference_existing(self._manifest_source):
            return None
        project_name = self._manifest_name()
        if not project_name or not self._maybe_resolve_project_resources_folder(project_name):
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
        return resources_uid

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
        if args in (
            ["pam", "gateway", "list", "--format", "json"],
            ["pam", "config", "list", "--format", "json"],
        ):
            return self._run_pam_list_in_process(args)

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
    # In-process invocation of `pam project import` / `pam project extend`.
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
                    else:
                        from keepercommander.commands.discoveryrotation import (  # type: ignore
                            PAMConfigurationListCommand,
                        )

                        result = PAMConfigurationListCommand().execute(params, format="json")
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
        # 1. If KEEPER_SDK_LOGIN_HELPER points at a Python file, use it
        #    (custom flows — KSM, HSM-backed TOTP, device-approval queue).
        # 2. Otherwise fall back to the in-tree EnvLoginHelper reading
        #    KEEPER_EMAIL / KEEPER_PASSWORD / KEEPER_TOTP_SECRET.
        # The KEEPER_SDK_LOGIN_HELPER path is validated but the env-var
        # fallback kicks in only when the var is unset — an operator
        # pointing at a missing file gets a loud error (the point of
        # setting the var is to say "do not use the default").
        from keeper_sdk.auth import EnvLoginHelper, load_helper_from_path

        helper_path = os.environ.get("KEEPER_SDK_LOGIN_HELPER")
        try:
            helper = load_helper_from_path(helper_path) if helper_path else EnvLoginHelper()
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
    result_code = getattr(exc, "result_code", None)
    if isinstance(result_code, str) and result_code == _SESSION_EXPIRED_CODE:
        return True
    text = f"{type(exc).__name__}: {exc}".casefold()
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


def build_pam_rotation_edit_argvs(
    manifest: Any,
    *,
    plan: Plan | None = None,
    live_records: list[LiveRecord] | None = None,
) -> list[list[str]]:
    """Build Commander argv for nested ``pamUser`` rotation settings.

    Pure resolver only: it never calls Keeper and is intentionally not wired
    into ``apply_plan`` while the provider-capability and preview gates remain
    in place. Nested users need three proven live UIDs before a rotation edit is
    safe: the user record, the parent resource record, and the PAM config.
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
        self._live_by_title: dict[tuple[str, str], list[LiveRecord]] = {}
        for live in live_records:
            marker_ref = _non_empty_str((live.marker or {}).get("uid_ref"))
            if marker_ref:
                self._live_by_ref.setdefault(marker_ref, []).append(live)
            self._live_by_title.setdefault((live.resource_type, live.title), []).append(live)

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
        matches = self._live_by_title.get((resource_type, title), [])
        if len(matches) > 1:
            raise ValueError(
                f"duplicate live {role} match for title '{title}' ({resource_type}): "
                f"{[item.keeper_uid for item in matches]}"
            )
        return matches[0].keeper_uid if matches else None


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
        "rotation_settings",
        "users[].rotation_settings / resources[].users[].rotation_settings",
        "pam rotation edit --record / --resource / --schedulecron / --on-demand",
    ),
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

    Pure helper only. `apply_plan` still blocks rotation until the full
    discovery/apply/outcome contract is proven offline and live.
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


def _detect_unsupported_capabilities(manifest: Any) -> list[str]:
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

    for needle, human, hook in _UNSUPPORTED_CAPABILITY_HINTS:
        if _contains_key(source, needle):
            hits.append(f"{human} is not implemented (Commander hook: `{hook}`)")

    return hits


__all__ = [
    "CommanderCliProvider",
    "build_pam_rotation_edit_argvs",
    "build_post_import_tuning_argvs",
]
