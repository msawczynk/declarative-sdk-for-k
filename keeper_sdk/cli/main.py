"""Keeper PAM Declarative CLI.

Subcommands:
    validate   - schema + typed-model validation
    export     - Commander JSON export -> declarative YAML manifest
    plan       - compute and render an execution plan
    import     - adopt unmanaged matching records and write ownership markers
    diff       - plan + field-by-field render
    apply      - execute a plan via the selected provider

Exit codes:
    0 success, clean
    1 unexpected error
    2 validation error
    3 unresolved uid_ref / cycle
    4 plan produced conflicts (non-zero actionable conflicts)
    5 capability / provider error
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from keeper_sdk.cli.renderer import RichRenderer
from keeper_sdk.core import (
    CapabilityError,
    ChangeKind,
    DeleteUnsupportedError,
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
@click.option("--provider", type=click.Choice(["mock", "commander"]), default="mock", show_default=True)
@click.option("--folder-uid", default=None, help="Keeper shared-folder UID scope (for commander provider)")
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

        live_gateway_names = {
            record.title for record in live if record.resource_type == "gateway"
        }
        stage4_failed = False
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
        online_suffix = f"; online: {len(live)} live records"
        if stage4_failed:
            sys.exit(EXIT_CAPABILITY)

    click.echo(f"ok: {manifest.name} ({len(manifest.iter_uid_refs())} uid_refs){online_suffix}")
    if emit_canonical:
        click.echo(dump_manifest(manifest, fmt="yaml"))


# ---------------------------------------------------------------------------
# export

@main.command(name="export")
@click.argument("commander_json", type=click.Path(exists=True, path_type=Path))
@click.option("--name", default=None, help="Manifest name (defaults to file stem)")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None,
              help="Write YAML to file (else stdout)")
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
    manifest, order, live = _load_plan_context(ctx, manifest_path)
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
    except DeleteUnsupportedError as exc:
        click.echo(f"delete unsupported: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
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
    except DeleteUnsupportedError as exc:
        click.echo(f"delete unsupported: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
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
    manifest, order, live = _load_plan_context(ctx, manifest_path)
    try:
        changes = compute_diff(manifest, live, allow_delete=allow_delete)
    except OwnershipError as exc:
        click.echo(f"ownership error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

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

    return manifest, order, live


def _make_provider(ctx: click.Context, manifest_path: Path, *, manifest=None):
    provider_name = ctx.obj.get("provider", "mock")
    folder_uid = ctx.obj.get("folder_uid")
    if provider_name == "mock":
        return ctx.obj.setdefault("_provider_instance", MockProvider(manifest.name if manifest else None))
    if provider_name == "commander":
        manifest_source = {}
        if manifest is not None:
            manifest_source = manifest.model_dump(mode="python", exclude_none=True)
        return CommanderCliProvider(
            folder_uid=folder_uid or os.environ.get("KEEPER_DECLARATIVE_FOLDER"),
            manifest_source=manifest_source,
        )
    raise click.ClickException(f"unknown provider '{provider_name}'")


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


if __name__ == "__main__":
    main()
