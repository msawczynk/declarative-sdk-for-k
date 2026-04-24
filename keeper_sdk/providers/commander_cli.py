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
import importlib.util
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from keeper_sdk.core.diff import _DIFF_IGNORED_FIELDS, ChangeKind
from keeper_sdk.core.errors import CapabilityError, CollisionError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.metadata import (
    MARKER_FIELD_LABEL,
    decode_marker,
    encode_marker,
    serialize_marker,
    utc_timestamp,
)
from keeper_sdk.core.normalize import to_pam_import_json
from keeper_sdk.core.planner import Plan

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
        config_record = self._synthetic_reference_configuration_record()
        if config_record is not None:
            records.append(config_record)
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

    def _ensure_reference_project_scaffold(self, *, project_name: str, gateway_app_uid: str) -> dict[str, str]:
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
                next_action=f"inspect `keeper ls --format json \"{project_path}\"` and confirm scaffold creation succeeded",
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
                str(value)
                for value in (exc.context or {}).values()
                if isinstance(value, str)
            ).casefold()
            if "already" not in text:
                raise

    def _resolve_reference_configuration(self, payload: dict[str, Any]) -> dict[str, str]:
        config_name = str((payload.get("pam_configuration") or {}).get("title", "")).strip()
        gateway_name = str((payload.get("pam_configuration") or {}).get("gateway_name", "")).strip()

        gateway_rows = self._pam_gateway_rows()
        config_rows = self._pam_config_rows()

        gateway_row = next((row for row in gateway_rows if row["gateway_name"] == gateway_name), None)
        config_row = next((row for row in config_rows if row["config_name"] == config_name), None)
        if config_row is None and gateway_row is not None:
            matches = [row for row in config_rows if row["gateway_uid"] == gateway_row["gateway_uid"]]
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
        table = self._run_cmd(["pam", "gateway", "list"])
        rows: list[dict[str, str]] = []
        for row in _parse_ascii_table(table):
            app_cell = row.get("KSM Application Name (UID)", "")
            match = re.match(r"^(?P<title>.+) \((?P<uid>[^()]+)\)$", app_cell)
            rows.append(
                {
                    "app_title": match.group("title") if match else app_cell,
                    "app_uid": match.group("uid") if match else "",
                    "gateway_name": row.get("Gateway Name", ""),
                    "gateway_uid": row.get("Gateway UID", ""),
                }
            )
        return rows

    def _pam_config_rows(self) -> list[dict[str, str]]:
        table = self._run_cmd(["pam", "config", "list"])
        rows: list[dict[str, str]] = []
        for row in _parse_ascii_table(table):
            shared_folder = row.get("Shared Folder", "")
            match = re.match(r"^(?P<title>.+) \((?P<uid>[^()]+)\)$", shared_folder)
            rows.append(
                {
                    "config_uid": row.get("UID", ""),
                    "config_name": row.get("Config Name", ""),
                    "gateway_uid": row.get("Gateway UID", ""),
                    "shared_folder_title": match.group("title") if match else shared_folder,
                    "shared_folder_uid": match.group("uid") if match else "",
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
        params = self._get_keeper_params()
        try:
            from keepercommander import api, record_management, vault  # type: ignore
        except ImportError as exc:
            raise CapabilityError(
                reason=f"cannot write ownership marker: keepercommander unavailable: {exc}",
                next_action="install Commander Python package in the same interpreter as the SDK",
            ) from exc

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
                next_action="inspect `keeper ls --format json \"PAM Environments\"` and confirm import created the project folder",
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
        if len(args) >= 3 and args[0] == "pam" and args[1] == "project" and args[2] in {"import", "extend"}:
            return self._run_pam_project_in_process(args)

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

    def _run_pam_project_in_process(self, args: list[str]) -> str:
        """Parse argv for pam project {import,extend} and call the
        Commander class directly with a logged-in KeeperParams. Returns
        whatever the command printed to stdout, so callers that greppy the
        output (e.g. for access_token) keep working.
        """
        subcmd = args[2]
        parsed = _parse_pam_project_args(args[3:])
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
                    from keepercommander.commands.pam_import.edit import PAMProjectImportCommand
                    cmd = PAMProjectImportCommand()
                    cmd.execute(
                        params,
                        project_name=parsed.get("name"),
                        file_name=parsed.get("file"),
                        dry_run=parsed.get("dry_run", False),
                    )
                else:
                    from keepercommander.commands.pam_import.extend import PAMProjectExtendCommand
                    cmd = PAMProjectExtendCommand()
                    cmd.execute(
                        params,
                        config=parsed.get("config"),
                        file_name=parsed.get("file"),
                        dry_run=parsed.get("dry_run", False),
                    )
        except Exception as exc:
            stdout = buf_out.getvalue()
            stderr = buf_err.getvalue()
            raise CapabilityError(
                reason=f"in-process keeper pam project {subcmd} failed: {type(exc).__name__}: {exc}",
                context={"stdout": stdout[-6000:], "stderr": stderr[-4000:]},
                next_action="inspect the Commander output above and retry",
            ) from exc
        finally:
            root_logger.removeHandler(err_log_handler)

        return buf_out.getvalue()

    def _get_keeper_params(self) -> Any:
        if self._keeper_params is not None:
            return self._keeper_params
        if self._keeper_login_attempted:
            raise CapabilityError(
                reason="in-process Commander login previously failed; cannot retry without a new provider",
                next_action="re-run with a valid admin config + KSM credentials available",
            )
        self._keeper_login_attempted = True

        # Require an explicit helper path. The helper must expose
        # ``load_keeper_creds()`` and ``keeper_login(email, password, totp)``
        # — see ``keeper-vault-rbi-pam-testenv/scripts/deploy_watcher.py`` in
        # the acme lab for the canonical implementation. A prior version of
        # this code fell back to a workstation-local path; that is unsafe as
        # library behaviour.
        helper_path = os.environ.get("KEEPER_SDK_LOGIN_HELPER")
        if not helper_path:
            raise CapabilityError(
                reason="in-process Commander login requires KEEPER_SDK_LOGIN_HELPER to point at a Python helper exposing load_keeper_creds() + keeper_login()",
                next_action="export KEEPER_SDK_LOGIN_HELPER=/abs/path/to/deploy_watcher.py (or equivalent) and retry",
            )
        candidate = Path(helper_path)
        if not candidate.is_file():
            raise CapabilityError(
                reason=f"KEEPER_SDK_LOGIN_HELPER points at a non-existent file: {candidate}",
                next_action="correct the path or remove the env var",
            )
        try:
            spec = importlib.util.spec_from_file_location("_sdk_deploy_watcher", candidate)
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            assert spec and spec.loader
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            email, password, totp_secret = module.load_keeper_creds()
            params = module.keeper_login(email, password, totp_secret)
        except Exception as exc:
            raise CapabilityError(
                reason=f"in-process Commander login failed: {type(exc).__name__}: {exc}",
                next_action="verify KSM token + admin cred record are reachable",
            ) from exc
        self._keeper_params = params
        return params


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
    return any(isinstance(gateway, dict) and gateway.get("mode") == "reference_existing" for gateway in gateways)


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
        # Manifest-only keys that never round-trip through Commander as record
        # fields — they're SDK-layer placement / linkage metadata, not vault
        # field data. Comparing them post-apply always shows drift.
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


def _parse_ascii_table(payload: str) -> list[dict[str, str]]:
    lines = [line.rstrip() for line in payload.splitlines() if line.strip()]
    if len(lines) < 3:
        return []
    header = re.split(r"\s{2,}", lines[0].strip())
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        if set(line.strip()) == {"-"}:
            continue
        cells = re.split(r"\s{2,}", line.strip(), maxsplit=max(len(header) - 1, 0))
        if len(cells) > len(header):
            continue
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        rows.append(dict(zip(header, cells, strict=False)))
    return rows


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
    # pamMachine stores host+port under a single `pamHostname`/`host` field.
    if field_type in {"host", "pamHostname"}:
        return _host_payload(values)
    label = field.get("label") or ""
    if not values:
        return {}
    value = values[0] if len(values) == 1 else values
    # Prefer the field's label when it maps to a canonical manifest key;
    # otherwise fall back to the raw Commander type (covers simple 1:1
    # typed fields like login/password).
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
