#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# ruff: noqa: E402 - sys.path bootstrap above must precede these imports
import identity
import sandbox
import scenarios as smoke_scenarios

from keeper_sdk.core.diff import compute_diff
from keeper_sdk.core.graph import build_graph, execution_order
from keeper_sdk.core.manifest import load_declarative_manifest, load_manifest
from keeper_sdk.core.metadata import MANAGER_NAME, MARKER_FIELD_LABEL
from keeper_sdk.core.planner import build_plan
from keeper_sdk.core.schema import PAM_FAMILY, validate_manifest
from keeper_sdk.core.vault_diff import compute_vault_diff
from keeper_sdk.core.vault_graph import vault_record_apply_order
from keeper_sdk.core.vault_models import VAULT_FAMILY, VaultManifestV1
from keeper_sdk.providers.commander_cli import CommanderCliProvider

log = logging.getLogger("sdk_smoke.smoke")

GATEWAY_UID_REF = "lab-gw"
GATEWAY_NAME = "Lab GW Rocky"
PAM_CONFIG_UID_REF = "lab-cfg"
PAM_CONFIG_TITLE = "Lab Rocky PAM Configuration"
SMOKE_PROJECT_NAME = "sdk-smoke-testuser2"
DEFAULT_SCENARIO_NAME = "pamMachine"
TITLE_PREFIX = "sdk-smoke"
SDK_OUTPUT_TAIL_LINES = 40

# Set by ``main`` based on ``--scenario``; default is pamMachine so the
# legacy one-command invocation (``python3 scripts/smoke/smoke.py``)
# continues to exercise the baseline two-host cycle unchanged.
_ACTIVE_SCENARIO: smoke_scenarios.ScenarioSpec = smoke_scenarios.get(DEFAULT_SCENARIO_NAME)
_ACTIVE_VAULT_SCENARIO: smoke_scenarios.VaultScenarioSpec | None = None
_ACTIVE_SCENARIO_FAMILY = PAM_FAMILY


def _active_resources() -> list[dict[str, Any]]:
    if _ACTIVE_SCENARIO_FAMILY != PAM_FAMILY:
        raise RuntimeError("active smoke scenario is not a PAM scenario")
    return _ACTIVE_SCENARIO.build_resources(PAM_CONFIG_UID_REF, TITLE_PREFIX)


def _active_titles() -> list[str]:
    return [str(res["title"]) for res in _active_resources()]


def _active_expected_records() -> set[tuple[str, str]]:
    return set(_ACTIVE_SCENARIO.expected_records(PAM_CONFIG_UID_REF, TITLE_PREFIX))


def _active_vault_scenario() -> smoke_scenarios.VaultScenarioSpec:
    if _ACTIVE_VAULT_SCENARIO is None:
        raise RuntimeError("active smoke scenario is not a vault scenario")
    return _ACTIVE_VAULT_SCENARIO


def _active_scenario_name() -> str:
    if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY:
        return _active_vault_scenario().name
    return _ACTIVE_SCENARIO.name


def _active_scenario_description() -> str:
    if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY:
        return _active_vault_scenario().description
    return _ACTIVE_SCENARIO.description


class SmokeError(Exception):
    pass


class PreflightError(Exception):
    pass


class TenantConstraintError(Exception):
    pass


def _scenario_choices() -> list[str]:
    return sorted(set(smoke_scenarios.names()) | set(smoke_scenarios.vault_names()))


def _scenario_family(name: str) -> str:
    if name in smoke_scenarios.names():
        return PAM_FAMILY
    if name in smoke_scenarios.vault_names():
        return VAULT_FAMILY
    available = ", ".join(_scenario_choices())
    raise KeyError(f"unknown smoke scenario {name!r}; available: {available}")


def _set_active_scenario(name: str) -> str:
    global _ACTIVE_SCENARIO, _ACTIVE_VAULT_SCENARIO, _ACTIVE_SCENARIO_FAMILY

    family = _scenario_family(name)
    _ACTIVE_SCENARIO_FAMILY = family
    if family == VAULT_FAMILY:
        _ACTIVE_VAULT_SCENARIO = smoke_scenarios.vault_get(name)
        _ACTIVE_SCENARIO = smoke_scenarios.get(DEFAULT_SCENARIO_NAME)
    else:
        _ACTIVE_SCENARIO = smoke_scenarios.get(name)
        _ACTIVE_VAULT_SCENARIO = None
    return family


class SdkCommandError(Exception):
    def __init__(
        self,
        *,
        args: list[str],
        command: list[str],
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self.args_list = list(args)
        self.command = list(command)
        self.returncode = returncode
        self.stdout_tail = _tail_text(stdout)
        self.stderr_tail = _tail_text(stderr)
        super().__init__(
            _format_sdk_failure(
                "sdk command failed",
                command=self.command,
                returncode=returncode,
                stdout_tail=self.stdout_tail,
                stderr_tail=self.stderr_tail,
            )
        )


def run_smoke(
    *,
    keep_sf: bool = True,
    teardown_only: bool = False,
    keep_records: bool = False,
    login_helper: str = "deploy_watcher",
    state: dict[str, Any] | None = None,
) -> int:
    del keep_sf  # Shared-folder removal is intentionally not part of this runner.
    state = state if state is not None else {}

    try:
        admin_params = identity.admin_login()
        _mark(state, "admin auth OK")
        ident = identity.ensure_sdktest_identity()
        _mark(state, f"test identity OK ({ident['email']})")
        # `ensure_sdktest_identity()` performs its own admin login. On some
        # tenants that invalidates the earlier in-process session, so refresh
        # before sandbox provisioning uses `admin_params`.
        admin_params = identity.admin_login()
        _mark(state, "admin auth refreshed after identity bootstrap")
    except Exception as exc:  # pragma: no cover - live-only path
        raise PreflightError(f"auth bootstrap failed: {exc}") from exc

    state["admin_params"] = admin_params
    state["ident"] = ident

    try:
        sb = sandbox.ensure_sandbox(admin_params, testuser_email=ident["email"])
        sf_uid = sb["sf_uid"]
        state["sf_uid"] = sf_uid
        _mark(state, f"sandbox ready ({sf_uid})")
    except Exception as exc:  # pragma: no cover - live-only path
        if _looks_like_tenant_constraint(exc):
            raise TenantConstraintError(str(exc)) from exc
        raise PreflightError(f"sandbox provisioning failed: {exc}") from exc

    try:
        removed = sandbox.teardown_records(admin_params, sf_uid, manager=MANAGER_NAME)
        if removed:
            log.info("pre-clean removed %d orphan records: %s", len(removed), removed)
        _mark(state, f"pre-clean complete ({len(removed)} removed)")
    except Exception as exc:  # pragma: no cover - live-only path
        raise PreflightError(f"pre-clean failed: {exc}") from exc

    if teardown_only:
        log.info("teardown-only mode - done")
        return 0

    try:
        manifest_path = _write_manifest(sf_uid)
        empty_manifest_path = _write_empty_manifest(sf_uid)
        state["manifest_path"] = str(manifest_path)
        state["empty_manifest_path"] = str(empty_manifest_path)
        _mark(state, "temp manifests written")
    except Exception as exc:
        raise PreflightError(f"manifest generation failed: {exc}") from exc

    # SDK apply/plan/validate must run as the tenant admin: `pam project
    # import` is gated on a role-enforcement the smoke test user lacks
    # ("Communication Error: This feature has been disabled by your Keeper
    # administrator."). testuser2 still owns the sandbox share for the
    # visibility proof further down. The admin Commander config is already
    # authenticated by identity.admin_login().
    admin_config_path = getattr(admin_params, "config_filename", None) or str(
        identity.ADMIN_COMMANDER_CONFIG
    )
    admin_password = getattr(admin_params, "password", None)
    if not admin_password:
        # KeeperParams drops .password after login; re-fetch from KSM.
        admin_password = _load_admin_password()
    argv_prefix = ["keeper", "--config", admin_config_path]
    env = dict(os.environ)
    env["KEEPER_CONFIG"] = admin_config_path
    env["KEEPER_DECLARATIVE_FOLDER"] = sf_uid
    # Commander's --batch-mode still requires the master password to unlock the
    # local key on each subprocess invocation; KEEPER_PASSWORD short-circuits
    # the prompt without hitting stdin.
    env["KEEPER_PASSWORD"] = admin_password
    if login_helper == "env":
        email, _password, totp_secret = _load_admin_creds()
        env["KEEPER_EMAIL"] = email
        env["KEEPER_TOTP_SECRET"] = totp_secret
        env.pop("KEEPER_SDK_LOGIN_HELPER", None)
        os.environ.pop("KEEPER_SDK_LOGIN_HELPER", None)
        auth_path = _auth_path_message("env")
    else:
        # The SDK routes pam project import/extend + marker writes through the
        # in-process Commander API; point it at the lab's deploy_watcher.py so
        # _get_keeper_params() can bootstrap a KeeperParams session.
        helper_path = str(identity.LAB_ROOT / "scripts" / "deploy_watcher.py")
        env["KEEPER_SDK_LOGIN_HELPER"] = helper_path
        os.environ["KEEPER_SDK_LOGIN_HELPER"] = helper_path
        auth_path = _auth_path_message("deploy_watcher", helper_path=helper_path)
    log.info(auth_path)
    state["sdk_auth_path"] = auth_path
    _mark(state, auth_path)
    state["keeper_args"] = argv_prefix
    state["admin_config_path"] = admin_config_path
    if _ACTIVE_SCENARIO_FAMILY == PAM_FAMILY:
        _remove_project_tree(argv_prefix, env=env, project_name=SMOKE_PROJECT_NAME)
        _mark(state, "project tree pre-clean complete")
    else:
        _mark(state, "vault folder pre-clean complete")

    _sdk(["validate", str(manifest_path)], env=env)
    _mark(state, "sdk validate OK")

    rc_plan = _sdk_allow([2], ["plan", str(manifest_path)], env=env)
    if rc_plan != 2:
        raise SmokeError(f"expected plan exit 2 (changes present), got {rc_plan}")
    _mark(state, "initial plan shows creates")

    _sdk(["apply", "--auto-approve", str(manifest_path)], env=env)
    _mark(state, "apply OK")

    manifest_source = yaml.safe_load(manifest_path.read_text())
    if not isinstance(manifest_source, dict):
        manifest_source = {}
    if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY:
        prov = CommanderCliProvider(
            config_file=admin_config_path,
            keeper_password=admin_password,
            manifest_source=manifest_source,
            folder_uid=sf_uid,
        )
        resolved_sf_uid = sf_uid
        state["managed_folder_uid"] = resolved_sf_uid
        _mark(state, f"vault folder selected ({resolved_sf_uid})")

        live = prov.discover()
        typed = load_declarative_manifest(manifest_path)
        if not isinstance(typed, VaultManifestV1):
            raise SmokeError("vault verifier loaded a non-vault manifest")
        try:
            _active_vault_scenario().verify(typed, live, TITLE_PREFIX)
        except AssertionError as exc:
            raise SmokeError(f"scenario post-apply verifier failed: {exc}") from exc
        _mark(state, f"marker verification OK ({_active_vault_scenario().name})")
    else:
        prov = CommanderCliProvider(
            config_file=admin_config_path,
            keeper_password=admin_password,
            manifest_source=manifest_source,
        )
        resolved_sf_uid = prov._resolve_project_resources_folder(SMOKE_PROJECT_NAME)
        state["managed_folder_uid"] = resolved_sf_uid
        _mark(state, f"resources folder resolved ({resolved_sf_uid})")
        _share_ksm_app_folder(
            admin_params,
            app_uid=sb["ksm_app_uid"],
            folder_uid=resolved_sf_uid,
        )
        _mark(state, "resources folder shared to KSM app")

        if prov.last_resolved_folder_uid != resolved_sf_uid:
            raise SmokeError("provider did not cache the resolved Resources shared-folder UID")

        live = prov.discover()
        expected_records = _active_expected_records()
        expected_count = len(expected_records)
        owned = [
            record
            for record in live
            if (record.resource_type, record.title) in expected_records
            and record.marker
            and record.marker.get("manager") == MANAGER_NAME
        ]
        if len(owned) != expected_count:
            found = {(record.resource_type, record.title) for record in owned}
            missing = sorted(expected_records - found)
            raise SmokeError(
                f"expected {expected_count} SDK-managed scenario records, found {len(owned)}; "
                f"missing={missing}; live={_live_summary(live)}"
            )
        try:
            _ACTIVE_SCENARIO.verify(owned)
        except AssertionError as exc:
            raise SmokeError(f"scenario post-apply verifier failed: {exc}") from exc
        _mark(state, f"marker verification OK ({_ACTIVE_SCENARIO.name})")

    rc_plan2 = _sdk_allow([0], ["plan", "--json", str(manifest_path)], env=env)
    if rc_plan2 != 0:
        raise SmokeError(f"re-plan expected 0 (noop), got {rc_plan2}; drift present")
    _mark(state, "re-plan clean")

    if keep_records:
        log.info("keep-records mode - skipping destroy phase")
        return 0

    rc_destroy_plan = _sdk_allow([2], ["plan", "--allow-delete", str(empty_manifest_path)], env=env)
    if rc_destroy_plan != 2:
        raise SmokeError(f"destroy plan expected 2 (deletes present), got {rc_destroy_plan}")
    _mark(state, "destroy plan shows deletes")

    _sdk(["apply", "--allow-delete", "--auto-approve", str(empty_manifest_path)], env=env)
    _mark(state, "destroy apply OK")

    # Empty-manifest plans omit ``gateways`` / ``pam_configurations``; combined
    # with ``reference_existing`` scaffolds, Commander can leave SDK-marked
    # ``pam_configuration`` rows under the project Resources/Users folders that
    # never appear as DELETE rows. Sweep those folders the same way as
    # pre-clean, then re-discover with an empty ``manifest_source`` so
    # :meth:`discover` does not inject the synthetic reference-configuration
    # :class:`~keeper_sdk.core.interfaces.LiveRecord` (which always carries a
    # marker and would false-positive this check).
    for folder_uid in (resolved_sf_uid, prov.last_resolved_users_folder_uid or ""):
        if not folder_uid:
            continue
        try:
            extra = sandbox.teardown_records(admin_params, folder_uid, manager=MANAGER_NAME)
        except Exception as exc:
            # Destroy may remove the Users/Resources tree; UIDs cached before
            # apply are then stale. Missing-folder errors are non-fatal here.
            if "No such folder" in str(exc) or "No such folder or record" in str(exc):
                log.warning(
                    "post-destroy folder sweep skipped %s (%s)", folder_uid, exc.__class__.__name__
                )
                continue
            raise
        if extra:
            log.info(
                "post-destroy folder sweep removed %d SDK-managed record(s) under %s",
                len(extra),
                folder_uid,
            )

    empty_src = yaml.safe_load(empty_manifest_path.read_text())
    if not isinstance(empty_src, dict):
        empty_src = {}
    prov_verify = CommanderCliProvider(
        config_file=admin_config_path,
        keeper_password=admin_password,
        manifest_source=empty_src,
        folder_uid=sf_uid if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY else None,
    )
    live_after = prov_verify.discover()
    still_ours = [
        record
        for record in live_after
        if record.marker and record.marker.get("manager") == MANAGER_NAME
    ]
    if still_ours:
        raise SmokeError(
            f"destroy failed - {len(still_ours)} records still marked SDK-owned: {_live_summary(still_ours)}"
        )
    if _ACTIVE_SCENARIO_FAMILY == PAM_FAMILY:
        _remove_project_tree(argv_prefix, env=env, project_name=SMOKE_PROJECT_NAME)
        _mark(state, "project tree cleanup OK")
    else:
        _mark(state, "vault folder cleanup OK")

    log.info("SMOKE PASSED: create->verify->destroy cycle clean")
    return 0


def _write_manifest(sf_uid: str) -> Path:
    if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY:
        scenario = _active_vault_scenario()
        document = scenario.build_manifest(TITLE_PREFIX, sf_uid)
        _preflight_manifest(document)
        return _write_temp_manifest(document, suffix=f".smoke-{scenario.name}.yaml")
    document = _base_manifest(sf_uid)
    document["resources"] = _active_resources()
    _preflight_manifest(document)
    return _write_temp_manifest(document, suffix=f".smoke-{_ACTIVE_SCENARIO.name}.yaml")


def _write_empty_manifest(sf_uid: str) -> Path:
    if _ACTIVE_SCENARIO_FAMILY == VAULT_FAMILY:
        del sf_uid
        document = {"schema": VAULT_FAMILY, "records": []}
        _preflight_manifest(document)
        return _write_temp_manifest(document, suffix=".smoke-empty.yaml")
    document = _base_manifest(sf_uid)
    document.pop("shared_folders", None)
    document.pop("gateways", None)
    document.pop("pam_configurations", None)
    document["resources"] = []
    _preflight_manifest(document)
    return _write_temp_manifest(document, suffix=".smoke-empty.yaml")


def _base_manifest(sf_uid: str) -> dict[str, Any]:
    del sf_uid
    return {
        "version": "1",
        "name": SMOKE_PROJECT_NAME,
        "shared_folders": {
            "resources": {
                "uid_ref": "smoke-sf-resources",
                "manage_users": True,
                "manage_records": True,
                "can_edit": True,
                "can_share": True,
            }
        },
        "gateways": [
            {
                "uid_ref": GATEWAY_UID_REF,
                "name": GATEWAY_NAME,
                "mode": "reference_existing",
            }
        ],
        "pam_configurations": [
            {
                "uid_ref": PAM_CONFIG_UID_REF,
                "environment": "local",
                "title": PAM_CONFIG_TITLE,
                "gateway_uid_ref": GATEWAY_UID_REF,
            }
        ],
    }


def _preflight_manifest(document: dict[str, Any]) -> None:
    family = validate_manifest(document)
    path = _write_temp_manifest(document, suffix=".preflight.yaml")
    try:
        if family == VAULT_FAMILY:
            manifest_typed = load_declarative_manifest(path)
            if not isinstance(manifest_typed, VaultManifestV1):
                raise PreflightError("generated vault manifest did not load as VaultManifestV1")
            order = vault_record_apply_order(manifest_typed)
            changes = compute_vault_diff(
                manifest_typed,
                [],
                manifest_name=path.stem,
                allow_delete=True,
            )
            plan = build_plan(path.stem, changes, order)
            if document.get("records") and len(plan.creates) < 1:
                raise PreflightError("generated vault manifest did not produce a create plan")
        else:
            manifest = load_manifest(path)
            order = execution_order(build_graph(manifest))
            changes = compute_diff(manifest, [], allow_delete=True)
            plan = build_plan(manifest.name, changes, order)
            if document.get("resources") and len(plan.creates) < 2:
                raise PreflightError("generated manifest did not produce the expected create plan")
    finally:
        path.unlink(missing_ok=True)


def _write_temp_manifest(document: dict[str, Any], *, suffix: str) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="keeper-sdk-", suffix=suffix)
    path = Path(raw_path)
    os.close(fd)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _sdk(args: list[str], *, env: dict[str, str]) -> None:
    _sdk_allow([0], args, env=env)


def _sdk_allow(ok_codes: list[int], args: list[str], *, env: dict[str, str]) -> int:
    cmd = [sys.executable, "-m", "keeper_sdk.cli", "--provider", "commander", *args]
    log.info("SDK: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode not in ok_codes:
        stdout_tail = _tail_text(result.stdout)
        stderr_tail = _tail_text(result.stderr)
        if result.returncode == 5:
            raise TenantConstraintError(
                _format_sdk_failure(
                    "sdk command reported tenant/provider constraint",
                    command=cmd,
                    returncode=result.returncode,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
            )
        raise SdkCommandError(
            args=args,
            command=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    if result.stdout:
        log.debug("SDK stdout tail:\n%s", _tail_text(result.stdout))
    if result.stderr:
        log.debug("SDK stderr tail:\n%s", _tail_text(result.stderr))
    return result.returncode


def _auth_path_message(login_helper: str, *, helper_path: str | None = None) -> str:
    if login_helper == "env":
        return (
            "sdk auth path: public EnvLoginHelper env path "
            "(KEEPER_EMAIL/KEEPER_PASSWORD/KEEPER_TOTP_SECRET; "
            "KEEPER_SDK_LOGIN_HELPER unset)"
        )
    if login_helper == "deploy_watcher":
        suffix = f" ({helper_path})" if helper_path else ""
        return f"sdk auth path: deploy_watcher helper path via KEEPER_SDK_LOGIN_HELPER{suffix}"
    raise ValueError(f"unknown login helper: {login_helper}")


def _tail_text(text: str | None, *, max_lines: int = SDK_OUTPUT_TAIL_LINES) -> str:
    if not text:
        return "<empty>"
    lines = text.splitlines()
    omitted = max(0, len(lines) - max_lines)
    tail = "\n".join(lines[-max_lines:])
    if omitted:
        return f"... ({omitted} line(s) omitted)\n{tail}"
    return tail


def _format_sdk_failure(
    prefix: str,
    *,
    command: list[str],
    returncode: int,
    stdout_tail: str,
    stderr_tail: str,
) -> str:
    return "\n".join(
        [
            f"{prefix}: exit_code={returncode}",
            f"command: {_quote_cmd(command)}",
            "stdout_tail:",
            stdout_tail,
            "stderr_tail:",
            stderr_tail,
        ]
    )


def _quote_cmd(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _load_admin_creds() -> tuple[str, str, str]:
    """Re-fetch admin creds via deploy_watcher.load_keeper_creds().

    KeeperParams zeroes .password after successful login, so we can't pull
    the password off admin_params. Re-reading from KSM is cheap (~1s) and
    lets the smoke runner exercise either login-helper path without
    plumbing secrets through identity.admin_login()'s return.
    """
    module_path = identity.LAB_ROOT / "scripts" / "deploy_watcher.py"
    deploy_watcher = identity._load_lab_module("sdk_smoke_admin_creds", module_path)
    email, password, totp_secret = deploy_watcher.load_keeper_creds()
    return email, password, totp_secret


def _load_admin_password() -> str:
    return _load_admin_creds()[1]


def _share_ksm_app_folder(admin_params: Any, *, app_uid: str, folder_uid: str) -> None:
    config_path = getattr(admin_params, "config_filename", None) or str(
        identity.ADMIN_COMMANDER_CONFIG
    )
    env = dict(os.environ)
    password = getattr(admin_params, "password", None) or _load_admin_password()
    env["KEEPER_PASSWORD"] = password
    cmd = [
        "keeper",
        "--config",
        config_path,
        "--batch-mode",
        "secrets-manager",
        "share",
        "add",
        "--app",
        app_uid,
        "--secret",
        folder_uid,
        "--editable",
    ]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    text_cf = text.casefold()
    if result.returncode == 0:
        if "is not a record nor shared folder" in text_cf:
            raise SmokeError(
                f"share-add rejected folder {folder_uid} for app {app_uid}: "
                f"sync/cache issue (keeper stdout). Try `keeper sync-down` then re-run smoke."
            )
        return
    if "already" in text_cf:
        log.info("KSM app %s already bound to folder %s", app_uid, folder_uid)
        return
    raise SmokeError(
        f"share-add failed for app {app_uid} -> folder {folder_uid} (rc={result.returncode}); "
        f"stderr={result.stderr!r} stdout_tail={text[-800:]!r}"
    )


def _remove_project_tree(argv_prefix: list[str], *, env: dict[str, str], project_name: str) -> None:
    cmd = [*argv_prefix, "rmdir", "-f", f"PAM Environments/{project_name}"]
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        return
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).casefold()
    if "not found" in text or "cannot be resolved" in text or "does not exist" in text:
        log.info("project tree already absent: PAM Environments/%s", project_name)
        return
    log.warning(
        "project tree cleanup failed rc=%s for PAM Environments/%s",
        result.returncode,
        project_name,
    )


def _candidate_cleanup_folder_uids(state: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("managed_folder_uid", "sf_uid"):
        value = state.get(key)
        if isinstance(value, str) and value and value not in candidates:
            candidates.append(value)
    return candidates


def _teardown_records_with_fallback(state: dict[str, Any]) -> list[Any]:
    admin_params = state["admin_params"]
    errors: list[str] = []
    for folder_uid in _candidate_cleanup_folder_uids(state):
        try:
            return sandbox.teardown_records(admin_params, folder_uid, manager=MANAGER_NAME)
        except Exception as exc:  # pragma: no cover - exercised via unit test with fake sandbox
            errors.append(f"{folder_uid}: {exc}")
            log.warning("cleanup failed for folder %s; trying fallback if available", folder_uid)
    raise SmokeError("cleanup failed for all candidate folders: " + "; ".join(errors))


def _mark(state: dict[str, Any], message: str) -> None:
    state.setdefault("passed", []).append(message)


def _live_summary(records: list[Any]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for record in records:
        marker = record.marker or {}
        summary.append(
            {
                "uid": record.keeper_uid,
                "title": record.title,
                "type": record.resource_type,
                "manager": marker.get("manager"),
                "marker_field": MARKER_FIELD_LABEL if marker else None,
            }
        )
    return summary


def _current_sf_contents(admin_params: Any, sf_uid: str) -> list[dict[str, Any]]:
    try:
        entries = sandbox._list_folder_entries(admin_params, sf_uid)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - live-only path
        return [{"error": str(exc)}]

    out: list[dict[str, Any]] = []
    for entry in entries:
        item = {
            "uid": sandbox._entry_uid(entry),  # type: ignore[attr-defined]
            "name": sandbox._entry_name(entry),  # type: ignore[attr-defined]
            "type": sandbox._entry_type(entry),  # type: ignore[attr-defined]
        }
        record_uid = item["uid"]
        if item["type"] == "record" and record_uid:
            try:
                marker = sandbox._record_marker(admin_params, record_uid)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - live-only path
                marker = {"error": str(exc)}
            item["marker"] = marker
        out.append(item)
    return out


def _looks_like_tenant_constraint(exc: BaseException) -> bool:
    text = str(exc).casefold()
    hints = (
        "gateway",
        "not visible",
        "not found",
        "shared to that admin session",
        "permission",
        "capability",
        "provider",
    )
    return any(hint in text for hint in hints)


def _print_post_mortem(state: dict[str, Any], exc: BaseException) -> None:
    payload = {
        "passed": state.get("passed", []),
        "failed": str(exc),
    }
    admin_params = state.get("admin_params")
    for sf_uid in _candidate_cleanup_folder_uids(state):
        if not admin_params:
            break
        contents = _current_sf_contents(admin_params, sf_uid)
        payload["shared_folder_contents"] = contents
        if not (len(contents) == 1 and "error" in contents[0]):
            break
    print(json.dumps(payload, indent=2), file=sys.stderr)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live Keeper SDK smoke runner")
    parser.add_argument("--teardown", action="store_true", help="only remove SDK-managed records")
    parser.add_argument(
        "--keep-records", action="store_true", help="skip destroy phase for debugging"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logger level for sdk_smoke.smoke",
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO_NAME,
        choices=_scenario_choices(),
        help=(
            "Which resource shape to exercise. Each scenario uses the "
            "same identity+sandbox+destroy flow; only the resources[] "
            "payload + post-apply verifier differ. See "
            "scripts/smoke/scenarios.py for the registry."
        ),
    )
    parser.add_argument(
        "--login-helper",
        default="deploy_watcher",
        choices=["deploy_watcher", "env"],
        help=(
            "How SDK subprocesses authenticate. 'deploy_watcher' exports "
            "KEEPER_SDK_LOGIN_HELPER; 'env' clears that variable and relies on "
            "KEEPER_EMAIL/KEEPER_PASSWORD/KEEPER_TOTP_SECRET for the "
            "EnvLoginHelper fallback."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    log.setLevel(getattr(logging, args.log_level))
    scenario_family = _set_active_scenario(args.scenario)
    log.info(
        "smoke scenario: %s (%s) — %s",
        _active_scenario_name(),
        scenario_family,
        _active_scenario_description(),
    )
    state: dict[str, Any] = {"passed": []}
    exit_code = 0
    needs_cleanup = False

    try:
        exit_code = run_smoke(
            keep_sf=True,
            teardown_only=args.teardown,
            keep_records=args.keep_records,
            login_helper=args.login_helper,
            state=state,
        )
        return exit_code
    except KeyboardInterrupt as exc:  # pragma: no cover - live-only path
        needs_cleanup = True
        _print_post_mortem(state, exc)
        return 2
    except TenantConstraintError as exc:
        needs_cleanup = True
        _print_post_mortem(state, exc)
        return 4
    except PreflightError as exc:
        _print_post_mortem(state, exc)
        return 3
    except (SmokeError, SdkCommandError) as exc:
        needs_cleanup = True
        _print_post_mortem(state, exc)
        return 2
    finally:
        if needs_cleanup and state.get("admin_params") and state.get("sf_uid"):
            try:
                removed = _teardown_records_with_fallback(state)
                if removed:
                    log.info("cleanup removed %d record(s): %s", len(removed), removed)
            except Exception as cleanup_exc:  # pragma: no cover - live-only path
                print(f"cleanup failed: {cleanup_exc}", file=sys.stderr)
            admin_config_path = state.get("admin_config_path")
            admin_params = state.get("admin_params")
            admin_password = None
            if admin_params:
                admin_password = getattr(admin_params, "password", None)
            if admin_config_path and not admin_password:
                try:
                    admin_password = _load_admin_password()
                except Exception:
                    admin_password = None
            if (
                _ACTIVE_SCENARIO_FAMILY == PAM_FAMILY
                and admin_config_path
                and admin_password
                and not os.environ.get("SMOKE_NO_CLEANUP")
            ):
                try:
                    cleanup_env = dict(os.environ)
                    cleanup_env["KEEPER_CONFIG"] = admin_config_path
                    cleanup_env["KEEPER_DECLARATIVE_FOLDER"] = state.get("sf_uid", "")
                    cleanup_env["KEEPER_PASSWORD"] = admin_password
                    _remove_project_tree(
                        ["keeper", "--config", admin_config_path],
                        env=cleanup_env,
                        project_name=SMOKE_PROJECT_NAME,
                    )
                except Exception as cleanup_exc:  # pragma: no cover - live-only path
                    print(f"project cleanup failed: {cleanup_exc}", file=sys.stderr)
            elif os.environ.get("SMOKE_NO_CLEANUP"):
                print(
                    "SMOKE_NO_CLEANUP=1 → skipping project tree cleanup for debugging",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())
