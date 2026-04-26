"""Keeper PAM Declarative CLI.

Subcommands:
    validate   - schema + typed-model validation
    export     - Commander JSON export -> declarative YAML manifest
    plan       - compute and render an execution plan
    import     - adopt unmanaged matching records and write ownership markers
    diff       - plan + field-by-field render
    apply      - execute a plan via the selected provider
    report     - read-only Commander reports: password-report, compliance-report,
                 security-audit-report (JSON, redacted)

Exit codes:
    0 success, clean
    1 unexpected error
    2 validation error
    3 unresolved uid_ref / cycle
    4 plan produced conflicts (non-zero actionable conflicts)
    5 capability / provider error
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import click

from keeper_sdk.auth import KsmLoginHelper, LoginHelper, load_helper_from_path
from keeper_sdk.cli.renderer import RichRenderer
from keeper_sdk.core import (
    CapabilityError,
    ChangeKind,
    ManifestError,
    OwnershipError,
    RefError,
    SchemaError,
    build_graph,
    build_plan,
    compute_diff,
    dump_manifest,
    execution_order,
    from_pam_import_json,
    load_manifest,
    redact,
)
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers import CommanderCliProvider, MockProvider
from keeper_sdk.secrets import bootstrap_ksm_application

EXIT_OK = 0
EXIT_GENERIC = 1
# Exit code 2 is intentionally overloaded per DOR (DELIVERY_PLAN.md + ARCHITECTURE.md):
#   - `plan` / `diff`: 2 = "changes present" (actionable, not a failure)
#   - `validate`: 2 = "schema invalid" (failure)
# Operators distinguish via the subcommand. Do NOT split these into
# different numbers without a spec update — CI pipelines depend on 2.
EXIT_CHANGES = 2
EXIT_SCHEMA = 2
EXIT_REF = 3
EXIT_CONFLICT = 4
EXIT_CAPABILITY = 5


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option()
@click.option(
    "--provider", type=click.Choice(["mock", "commander"]), default="mock", show_default=True
)
@click.option(
    "--folder-uid", default=None, help="Keeper shared-folder UID scope (for commander provider)"
)
@click.pass_context
def main(ctx: click.Context, provider: str, folder_uid: str | None) -> None:
    """Keeper PAM Declarative SDK."""
    ctx.ensure_object(dict)
    ctx.obj["provider"] = provider
    ctx.obj["folder_uid"] = folder_uid
    ctx.obj["renderer"] = RichRenderer()


# ---------------------------------------------------------------------------
# validate


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True, path_type=Path))
@click.option("--emit-canonical", is_flag=True, help="Print the canonicalised document")
@click.option("--online", is_flag=True, help="Run tenant-connectivity checks (stage 4-5)")
@click.pass_context
def validate(ctx: click.Context, manifest_path: Path, emit_canonical: bool, online: bool) -> None:
    """Validate the manifest against the v1 schema."""
    try:
        manifest = load_manifest(manifest_path)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except ManifestError as exc:
        click.echo(f"manifest error: {exc}", err=True)
        sys.exit(EXIT_GENERIC)

    # uid_ref graph sanity
    try:
        build_graph(manifest)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)

    online_suffix = ""
    if online:
        provider = _make_provider(ctx, manifest_path, manifest=manifest)
        try:
            live = provider.discover()
        except CapabilityError as exc:
            click.echo(f"discovery failed: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)

        gaps: list[str] = getattr(provider, "unsupported_capabilities", lambda _m: [])(manifest)
        stage4_failed = False
        if gaps:
            click.echo("capability gaps (will appear as plan conflicts):", err=True)
            for reason in gaps:
                click.echo(f"  - {reason}", err=True)
            stage4_failed = True

        live_gateway_names = {record.title for record in live if record.resource_type == "gateway"}
        for gateway in manifest.gateways:
            if gateway.mode != "reference_existing":
                continue
            if gateway.name in live_gateway_names:
                continue
            click.echo(f"stage 4: gateway '{gateway.name}' not found in tenant", err=True)
            stage4_failed = True

        try:
            changes = compute_diff(manifest, live, adopt=False)
        except OwnershipError as exc:
            click.echo(f"ownership error: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)

        create_count = sum(1 for change in changes if change.kind.value == "create")
        update_count = sum(1 for change in changes if change.kind.value == "update")
        delete_count = sum(1 for change in changes if change.kind.value == "delete")
        conflict_count = sum(1 for change in changes if change.kind.value == "conflict")
        click.echo(
            "stage 5: "
            f"{create_count} create, "
            f"{update_count} update, "
            f"{delete_count} delete-candidates, "
            f"{conflict_count} conflicts"
        )

        binding_issues: list[str] = getattr(provider, "check_tenant_bindings", lambda _m: [])(
            manifest
        )
        stage5_failed = False
        if binding_issues:
            stage5_failed = True
            click.echo("stage 5: tenant binding failures:", err=True)
            for issue in binding_issues:
                click.echo(f"  - {issue}", err=True)

        online_suffix = f"; online: {len(live)} live records"
        if stage4_failed or stage5_failed:
            sys.exit(EXIT_CAPABILITY)

    click.echo(f"ok: {manifest.name} ({len(manifest.iter_uid_refs())} uid_refs){online_suffix}")
    if emit_canonical:
        click.echo(dump_manifest(manifest, fmt="yaml"))


# ---------------------------------------------------------------------------
# export


@main.command(name="export")
@click.argument("commander_json", type=click.Path(exists=True, path_type=Path))
@click.option("--name", default=None, help="Manifest name (defaults to file stem)")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write YAML to file (else stdout)",
)
def export_cmd(commander_json: Path, name: str | None, output: Path | None) -> None:
    """Lift a ``keeper pam project export`` JSON document into a manifest."""
    data = json.loads(commander_json.read_text(encoding="utf-8"))
    manifest_dict = from_pam_import_json(data, name=name or commander_json.stem)
    # validate + type
    from keeper_sdk.core.manifest import load_manifest_string

    manifest = load_manifest_string(json.dumps(manifest_dict), suffix=".json")
    rendered = dump_manifest(manifest, fmt="yaml")
    if output:
        output.write_text(rendered, encoding="utf-8")
        click.echo(f"wrote {output}")
    else:
        click.echo(rendered)


# ---------------------------------------------------------------------------
# bootstrap-ksm


@main.command("bootstrap-ksm")
@click.option("--app-name", required=True, help="KSM application name, 64 characters max")
@click.option("--admin-record-uid", default=None, help="Existing admin login record UID")
@click.option("--create-admin-record", is_flag=True, help="Create a placeholder admin login record")
@click.option(
    "--config-out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output ksm-config.json path (defaults to ~/.keeper/<app-name>-ksm-config.json)",
)
@click.option(
    "--first-access-minutes",
    type=click.IntRange(0, 1440),
    default=10,
    show_default=True,
    help="Client token first-access expiry in minutes",
)
@click.option("--unlock-ip", is_flag=True, help="Create the KSM client without IP lock")
@click.option("--with-bus", is_flag=True, help="Create or reuse the Phase B bus directory record")
@click.option("--bus-title", default="dsk-agent-bus-directory", show_default=True)
@click.option("--overwrite", is_flag=True, help="Overwrite an existing --config-out file")
@click.option(
    "--login-helper",
    default="commander",
    show_default=True,
    help="Source admin session: commander, ksm, or /path/to/custom_helper.py",
)
def bootstrap_ksm_cmd(
    app_name: str,
    admin_record_uid: str | None,
    create_admin_record: bool,
    config_out: Path | None,
    first_access_minutes: int,
    unlock_ip: bool,
    with_bus: bool,
    bus_title: str,
    overwrite: bool,
    login_helper: str,
) -> None:
    """Provision a KSM application, admin-record share, client token, and config."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            params = _params_for_bootstrap(login_helper)
            config_path = config_out or (Path.home() / ".keeper" / f"{app_name}-ksm-config.json")
            result = bootstrap_ksm_application(
                params=params,
                app_name=app_name,
                admin_record_uid=admin_record_uid,
                create_admin_record=create_admin_record,
                config_out=config_path.expanduser().resolve(),
                first_access_minutes=first_access_minutes,
                unlock_ip=unlock_ip,
                create_bus_directory=with_bus,
                bus_directory_title=bus_title,
                overwrite=overwrite,
            )
    except CapabilityError as exc:
        click.echo(
            json.dumps(
                {
                    "status": "fail",
                    "reason": exc.reason,
                    "next_action": exc.next_action or "",
                },
                separators=(",", ":"),
            )
        )
        sys.exit(EXIT_CAPABILITY)

    payload = {
        "status": "ok",
        "app_uid": _uid_prefix(result.app_uid),
        "record_uid": _uid_prefix(result.admin_record_uid),
        "config_path": str(Path(result.config_path).expanduser().resolve()),
        "bus_uid": _uid_prefix(result.bus_directory_uid) if result.bus_directory_uid else None,
        "expires_at": result.expires_at_iso,
        "created_admin_record": result.created_admin_record,
        "created_bus_directory": result.created_bus_directory,
    }
    if result.created_admin_record:
        payload["warning"] = (
            "admin record created with placeholder fields; populate login/password/oneTimeCode "
            "in Web UI"
        )
    click.echo(json.dumps(payload, separators=(",", ":")))
    sys.exit(EXIT_OK)


# ---------------------------------------------------------------------------
# plan / diff


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True, path_type=Path))
@click.option("--allow-delete", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Emit plan as JSON")
@click.pass_context
def plan(ctx: click.Context, manifest_path: Path, allow_delete: bool, as_json: bool) -> None:
    """Compute an execution plan against the configured provider.

    Exits 0 when the plan is clean, 2 when changes are present, 4 when conflicts exist.
    """
    plan_obj = _build_plan(ctx, manifest_path, allow_delete=allow_delete)
    if as_json:
        click.echo(json.dumps(_plan_to_dict(plan_obj), indent=2))
    else:
        click.echo(ctx.obj["renderer"].render_plan(plan_obj))
    sys.exit(_exit_from_plan(plan_obj))


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True, path_type=Path))
@click.option("--allow-delete", is_flag=True)
@click.pass_context
def diff(ctx: click.Context, manifest_path: Path, allow_delete: bool) -> None:
    """Show a full field-level diff (secrets redacted)."""
    plan_obj = _build_plan(ctx, manifest_path, allow_delete=allow_delete)
    click.echo(ctx.obj["renderer"].render_diff(plan_obj))
    sys.exit(_exit_from_plan(plan_obj))


@main.command(name="import")
@click.argument("manifest_path", type=click.Path(exists=True, path_type=Path))
@click.option("--auto-approve", is_flag=True)
@click.option("--dry-run", is_flag=True, help="Show what would be adopted without writing markers")
@click.pass_context
def import_(
    ctx: click.Context,
    manifest_path: Path,
    auto_approve: bool,
    dry_run: bool,
) -> None:
    """Adopt unmanaged live records matching the manifest (writes ownership markers).

    Shows the adoption plan first, then writes markers only after confirmation.
    """
    manifest, order, live, _provider = _load_plan_context(ctx, manifest_path)
    try:
        changes = compute_diff(manifest, live, adopt=True)
    except OwnershipError as exc:
        click.echo(f"ownership error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    adopt_changes = [
        change
        for change in changes
        if change.kind is ChangeKind.UPDATE and "adoption" in (change.reason or "")
    ]
    plan_obj = build_plan(manifest.name, adopt_changes, order)

    click.echo(ctx.obj["renderer"].render_plan(plan_obj))
    if plan_obj.is_clean:
        click.echo("no records to adopt.")
        sys.exit(EXIT_OK)
    if dry_run:
        sys.exit(EXIT_OK)
    if not auto_approve:
        click.confirm("Proceed?", abort=True)

    provider = _make_provider(ctx, manifest_path, manifest=manifest)
    try:
        outcomes = provider.apply_plan(plan_obj, dry_run=False)
    except CapabilityError as exc:
        click.echo(f"provider error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    click.echo(ctx.obj["renderer"].render_outcomes(outcomes))
    sys.exit(EXIT_OK)


# ---------------------------------------------------------------------------
# apply


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True, path_type=Path))
@click.option("--allow-delete", is_flag=True)
@click.option("--auto-approve", is_flag=True)
@click.option("--dry-run", is_flag=True, help="Render what would run without mutating")
@click.pass_context
def apply(
    ctx: click.Context,
    manifest_path: Path,
    allow_delete: bool,
    auto_approve: bool,
    dry_run: bool,
) -> None:
    """Apply a manifest via the selected provider."""
    try:
        manifest = load_manifest(manifest_path)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    plan_obj = _build_plan(ctx, manifest_path, allow_delete=allow_delete)
    if dry_run:
        click.echo(ctx.obj["renderer"].render_plan(plan_obj))
        sys.exit(_exit_from_plan(plan_obj))

    click.echo(ctx.obj["renderer"].render_plan(plan_obj))
    if plan_obj.is_clean:
        click.echo("nothing to do.")
        sys.exit(EXIT_OK)
    if plan_obj.conflicts and not allow_delete:
        click.echo(f"{len(plan_obj.conflicts)} conflict(s) must be resolved first.", err=True)
        sys.exit(EXIT_CONFLICT)
    if not auto_approve and not dry_run:
        click.confirm("Proceed?", abort=True)
    provider = _make_provider(ctx, manifest_path, manifest=manifest)
    try:
        outcomes = provider.apply_plan(plan_obj, dry_run=dry_run)
    except CapabilityError as exc:
        click.echo(f"provider error: {exc}", err=True)
        if exc.context:
            for key, value in exc.context.items():
                click.echo(f"  {key}: {value}", err=True)
        sys.exit(EXIT_CAPABILITY)
    click.echo(ctx.obj["renderer"].render_outcomes(outcomes))
    sys.exit(EXIT_OK)


# ---------------------------------------------------------------------------
# shared helpers


def _build_plan(ctx: click.Context, manifest_path: Path, *, allow_delete: bool) -> Plan:
    manifest, order, live, provider = _load_plan_context(ctx, manifest_path)
    try:
        changes = compute_diff(manifest, live, allow_delete=allow_delete)
    except OwnershipError as exc:
        click.echo(f"ownership error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    # Surface provider capability gaps as CONFLICT rows so plan / dry-run /
    # apply are behaviourally identical (DELIVERY_PLAN.md: "plan == apply
    # --dry-run"). Without this, CommanderCliProvider.apply_plan would only
    # raise at real-apply time — operators would see green plans. See
    # REVIEW.md "Update — second pass / C3".
    try:
        capability_gaps = provider.unsupported_capabilities(manifest)
    except AttributeError:
        # Older third-party providers may not implement the hook; treat
        # as "no gaps" rather than breaking their integration.
        capability_gaps = []
    for reason in capability_gaps:
        from keeper_sdk.core.diff import Change, ChangeKind

        changes.insert(
            0,
            Change(
                kind=ChangeKind.CONFLICT,
                uid_ref=None,
                resource_type="capability",
                title="unsupported-by-provider",
                reason=reason,
            ),
        )

    return build_plan(manifest.name, changes, order)


def _load_plan_context(ctx: click.Context, manifest_path: Path):
    try:
        manifest = load_manifest(manifest_path)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    try:
        graph = build_graph(manifest)
        order = execution_order(graph)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)

    provider = _make_provider(ctx, manifest_path, manifest=manifest)
    try:
        live = provider.discover()
    except CapabilityError as exc:
        click.echo(f"discovery failed: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    return manifest, order, live, provider


def _make_provider(ctx: click.Context, manifest_path: Path, *, manifest=None):
    provider_name = ctx.obj.get("provider", "mock")
    folder_uid = ctx.obj.get("folder_uid")
    if provider_name == "mock":
        return ctx.obj.setdefault(
            "_provider_instance", MockProvider(manifest.name if manifest else None)
        )
    if provider_name == "commander":
        manifest_source = {}
        if manifest is not None:
            manifest_source = manifest.model_dump(mode="python", exclude_none=True)
        return CommanderCliProvider(
            folder_uid=folder_uid or os.environ.get("KEEPER_DECLARATIVE_FOLDER"),
            manifest_source=manifest_source,
        )
    raise click.ClickException(f"unknown provider '{provider_name}'")


def _params_for_bootstrap(login_helper: str):
    if login_helper == "commander":
        return _load_commander_config_params()
    helper: LoginHelper
    if login_helper == "ksm":
        helper = KsmLoginHelper()
    else:
        helper = load_helper_from_path(login_helper)
    creds = helper.load_keeper_creds()
    params = helper.keeper_login(**creds)
    if not getattr(params, "session_token", None):
        raise CapabilityError(
            reason="login helper returned no Commander session token",
            next_action="verify the helper authenticates successfully before running bootstrap-ksm",
        )
    return params


def _load_commander_config_params():
    try:
        from keepercommander.config_storage.loader import load_config_properties
        from keepercommander.params import KeeperParams
    except ImportError as exc:
        raise CapabilityError(
            reason=f"keepercommander is required for bootstrap-ksm commander login mode: {exc}",
            next_action="pip install keepercommander>=17.2.13,<18",
        ) from exc

    config_path = Path.home() / ".keeper" / "config.json"
    config: dict[str, object] = {}
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CapabilityError(
                reason=f"cannot parse Commander config at {config_path}: {exc}",
                next_action="run 'keeper login' again to refresh the source admin session",
            ) from exc

    params = KeeperParams(config_filename=str(config_path), config=config)
    load_config_properties(params)
    if not getattr(params, "session_token", None):
        raise CapabilityError(
            reason="Commander config has no authenticated session token",
            next_action="run 'keeper login' first to authenticate the source admin session",
        )
    return params


def _uid_prefix(uid: str | None) -> str:
    if not uid:
        return ""
    return uid[:6] + "..." if len(uid) > 6 else uid


def _exit_from_plan(plan_obj: Plan) -> int:
    if plan_obj.conflicts:
        return EXIT_CONFLICT
    if plan_obj.is_clean:
        return EXIT_OK
    return EXIT_CHANGES


def _plan_to_dict(plan_obj: Plan) -> dict:
    return {
        "manifest_name": plan_obj.manifest_name,
        "summary": {
            "create": len(plan_obj.creates),
            "update": len(plan_obj.updates),
            "delete": len(plan_obj.deletes),
            "conflict": len(plan_obj.conflicts),
            "noop": len(plan_obj.noops),
        },
        "order": plan_obj.order,
        "changes": [
            {
                "kind": change.kind.value,
                "uid_ref": change.uid_ref,
                "resource_type": change.resource_type,
                "title": change.title,
                "keeper_uid": change.keeper_uid,
                "before": redact(change.before),
                "after": redact(change.after),
                "reason": change.reason,
            }
            for change in plan_obj.changes
        ],
    }


def _emit_report_json(payload: dict[str, Any]) -> None:
    """Print report envelope; exit 1 if ``secret_leak_check`` flags output."""
    from keeper_sdk.cli._report.common import ReportOutputLeakError, serialize_report_payload

    try:
        click.echo(serialize_report_payload(payload))
    except ReportOutputLeakError as exc:
        click.echo(f"report refused: output failed leak check: {exc.warnings!r}", err=True)
        sys.exit(EXIT_GENERIC)
    sys.exit(EXIT_OK)


@main.group("report")
def report_cli() -> None:
    """Run read-only Commander reports; prints redacted JSON to stdout."""


@report_cli.command("password-report")
@click.option(
    "--policy",
    default="12,2,2,2,0",
    show_default=True,
    help="Password policy Length,Lower,Upper,Digits,Special (Commander format)",
)
@click.option(
    "--folder",
    default=None,
    help="Optional folder path or UID to scope the report",
)
@click.option("-v", "--verbose", is_flag=True, help="Verbose Commander columns")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint record_uid values instead of printing raw UIDs",
)
@click.option(
    "--sanitize-uids",
    is_flag=True,
    help="Fingerprint UID-like substrings in all string fields (live-transcript mode)",
)
@click.option(
    "--keeper-bin",
    default=None,
    envvar="KEEPER_BIN",
    help="Path to keeper CLI (default: keeper on PATH)",
)
def report_password_report(
    policy: str,
    folder: str | None,
    verbose: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Weak-password rows from Commander ``password-report`` (JSON envelope)."""
    from keeper_sdk.cli._report.password import run_password_report

    try:
        payload = run_password_report(
            policy=policy,
            folder=folder,
            verbose=verbose,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=keeper_bin,
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    except CapabilityError as exc:
        click.echo(f"report error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    _emit_report_json(payload)


@report_cli.command("compliance-report")
@click.option("--node", default=None, help="Node ID or name (Commander --node)")
@click.option("--username", multiple=True, help="Filter by username (repeatable)")
@click.option("--team", multiple=True, help="Filter by team name or UID (repeatable)")
@click.option("--rebuild", is_flag=True, help="Rebuild local compliance cache from source")
@click.option("--no-cache", is_flag=True, help="Remove local compliance cache after report")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint record_uid values in JSON output",
)
@click.option(
    "--sanitize-uids",
    is_flag=True,
    help="Fingerprint UID-like substrings in all string fields (live-transcript mode)",
)
@click.option(
    "--keeper-bin",
    default=None,
    envvar="KEEPER_BIN",
    help="Path to keeper CLI (default: keeper on PATH)",
)
def report_compliance_report(
    node: str | None,
    username: tuple[str, ...],
    team: tuple[str, ...],
    rebuild: bool,
    no_cache: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Default enterprise compliance table via ``keeper compliance report``."""
    from keeper_sdk.cli._report.compliance import run_compliance_report

    try:
        payload = run_compliance_report(
            node=node,
            username=username,
            team=team,
            rebuild=rebuild,
            no_cache=no_cache,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=keeper_bin,
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    except CapabilityError as exc:
        click.echo(f"report error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    _emit_report_json(payload)


@report_cli.command("security-audit-report")
@click.option("--node", multiple=True, help="Node name or UID filter (repeatable)")
@click.option(
    "--record-details",
    is_flag=True,
    help="Per-record password strength rows (when incremental data exists)",
)
@click.option("--breachwatch", is_flag=True, help="Include BreachWatch columns when licensed")
@click.option(
    "--score-type",
    type=click.Choice(["default", "strong_passwords"]),
    default="default",
    show_default=True,
)
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Skip confirmation prompts (Commander non-interactive)",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint record_uid when using --record-details",
)
@click.option(
    "--sanitize-uids",
    is_flag=True,
    help="Fingerprint UID-like substrings in all string fields (live-transcript mode)",
)
@click.option(
    "--keeper-bin",
    default=None,
    envvar="KEEPER_BIN",
    help="Path to keeper CLI (default: keeper on PATH)",
)
def report_security_audit_report(
    node: tuple[str, ...],
    record_details: bool,
    breachwatch: bool,
    score_type: str,
    force: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Enterprise security audit summary via ``keeper security-audit report``."""
    from keeper_sdk.cli._report.security_audit import run_security_audit_report

    try:
        payload = run_security_audit_report(
            nodes=node,
            record_details=record_details,
            breachwatch=breachwatch,
            score_type=score_type,
            force=force,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=keeper_bin,
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    except CapabilityError as exc:
        click.echo(f"report error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    _emit_report_json(payload)


@main.command("live-smoke")
@click.option(
    "--ksm-record-uid",
    required=True,
    envvar="KEEPER_LIVE_KSM_RECORD_UID",
    help="UID of the Keeper record holding the KSM bootstrap config",
)
@click.option(
    "--ksm-config",
    type=click.Path(path_type=Path),
    envvar="KEEPER_LIVE_KSM_CONFIG",
    help="Optional path to a KSM config file (alternative to --ksm-record-uid)",
)
@click.option(
    "--manifest",
    "manifest_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Smoke manifest to apply + diff",
)
@click.option(
    "--workdir",
    type=click.Path(path_type=Path),
    default=Path("./.live-smoke"),
    show_default=True,
    help="Working directory for transcripts + per-run artefacts",
)
@click.option(
    "--evidence-out",
    type=click.Path(path_type=Path),
    required=True,
    help="Where to write the sanitized proof transcript JSON",
)
@click.option(
    "--schema-family",
    required=True,
    help="Schema family being proven (e.g. pam-environment, keeper-vault)",
)
@click.option(
    "--schema-version",
    default="v1",
    show_default=True,
    help="Schema version being proven",
)
@click.option(
    "--commander-pin",
    default=None,
    help="Commander pin SHA; defaults to reading .commander-pin",
)
@click.pass_context
def live_smoke(
    ctx: click.Context,
    ksm_record_uid: str,
    ksm_config: Path | None,
    manifest_path: Path,
    workdir: Path,
    evidence_out: Path,
    schema_family: str,
    schema_version: str,
    commander_pin: str | None,
) -> None:
    """Run the live-tenant smoke loop and write a sanitized proof transcript.

    Phases: bootstrap-ksm → login → apply → diff (clean re-plan) → cleanup.

    Skipped without an active KSM-provisioned tenant. Sanitization in
    `keeper_sdk.cli._live.transcript` strips secrets, fingerprints UIDs;
    `secret_leak_check` is the post-write belt-and-braces grep.
    """
    from keeper_sdk.cli._live.runbook import iter_default_phases
    from keeper_sdk.cli._live.transcript import (
        Transcript,
        secret_leak_check,
    )

    if commander_pin is None:
        pin_path = Path(__file__).resolve().parents[2] / ".commander-pin"
        commander_pin = pin_path.read_text().strip() if pin_path.exists() else "unknown"

    workdir.mkdir(parents=True, exist_ok=True)
    empty = workdir / "_smoke_empty.yml"
    if not empty.exists():
        empty.write_text("schema: pam-environment.v1\n")

    transcript = Transcript(
        schema_family=schema_family,
        schema_version=schema_version,
        commander_pin=commander_pin,
    )
    for phase in iter_default_phases(
        ksm_record_uid=ksm_record_uid,
        ksm_config_path=ksm_config,
        manifest_path=manifest_path,
        workdir=workdir,
    ):
        transcript.add_phase(phase)
        click.echo(f"[live-smoke] {phase.name}: {phase.status} ({phase.elapsed_ms}ms)")

    transcript.finalize()
    written_path = transcript.write(evidence_out)
    leaks = secret_leak_check(
        written_path.read_text(),
        env_keys=("KEEPER_CONFIG", "KEEPER_LIVE_KSM_CONFIG", "KEEPER_LOGIN_TOKEN"),
    )
    if leaks:
        click.echo(
            f"live-smoke: SECRET LEAK DETECTED — refusing to leave evidence file. warnings={leaks}",
            err=True,
        )
        written_path.unlink(missing_ok=True)
        sys.exit(EXIT_GENERIC)
    click.echo(f"[live-smoke] transcript: {written_path}")
    summary = transcript.summary()
    if summary["failed"] > 0:
        sys.exit(EXIT_GENERIC)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
