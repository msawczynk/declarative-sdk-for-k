"""Keeper PAM Declarative CLI.

Subcommands:
    validate   - JSON Schema (all families); vault graph + optional online; PAM graph + online
    export     - Commander JSON export -> declarative YAML manifest
    plan       - compute and render a plan (pam-environment.v1 or keeper-vault.v1 + mock)
    import     - adopt unmanaged matching records and write ownership markers
    diff       - plan + field-by-field render
    apply      - execute a plan via the selected provider
    report     - read-only Commander reports: password-report, compliance-report,
                 security-audit-report, vault-health, ksm-usage, team-roles,
                 team-report, role-report (JSON, redacted)
    run        - Commander passthrough with redaction and exit-code passthrough

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
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from keeper_sdk.auth import KsmLoginHelper, LoginHelper, load_helper_from_path
from keeper_sdk.cli.renderer import RichRenderer
from keeper_sdk.core import (
    IDENTITY_FAMILY,
    K8S_ESO_FAMILY,
    MSP_FAMILY,
    SIEM_FAMILY,
    VAULT_MANIFEST_FAMILY,
    CapabilityError,
    Change,
    ChangeKind,
    IdentityManifestV1,
    K8sEsoManifestV1,
    Manifest,
    ManifestError,
    MspManifestV1,
    OwnershipError,
    RefError,
    SchemaError,
    UnsupportedFamilyError,
    build_graph,
    build_plan,
    build_vault_graph,
    compute_diff,
    compute_identity_diff,
    compute_msp_diff,
    compute_sharing_diff,
    compute_siem_diff,
    compute_vault_diff,
    dump_manifest,
    execution_order,
    from_pam_import_json,
    load_declarative_manifest,
    load_msp_manifest,
    msp_apply_order,
    redact,
    vault_record_apply_order,
)
from keeper_sdk.core.enterprise_diff import compute_enterprise_diff
from keeper_sdk.core.enterprise_graph import build_enterprise_graph, enterprise_apply_order
from keeper_sdk.core.epm_diff import compute_epm_diff
from keeper_sdk.core.integrations_events_diff import compute_events_diff
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord
from keeper_sdk.core.ksm_diff import compute_ksm_diff
from keeper_sdk.core.ksm_graph import ksm_apply_order
from keeper_sdk.core.manifest import read_manifest_document
from keeper_sdk.core.models_enterprise import (
    ENTERPRISE_FAMILY,
    EnterpriseManifestV1,
    load_enterprise_manifest,
)
from keeper_sdk.core.models_epm import EPM_FAMILY, EpmManifestV1
from keeper_sdk.core.models_integrations_events import EVENTS_FAMILY, EventsManifestV1
from keeper_sdk.core.models_ksm import KSM_FAMILY, KsmManifestV1
from keeper_sdk.core.models_pam_extended import PAM_EXTENDED_FAMILY, PamExtendedManifestV1
from keeper_sdk.core.models_siem import SiemManifestV1
from keeper_sdk.core.models_terraform import TERRAFORM_FAMILY, TerraformIntegrationManifestV1
from keeper_sdk.core.pam_extended_diff import compute_pam_extended_diff
from keeper_sdk.core.planner import Plan
from keeper_sdk.core.preview import assert_preview_keys_allowed
from keeper_sdk.core.schema import PAM_FAMILY, SHARING_FAMILY, validate_manifest
from keeper_sdk.core.sharing_graph import sharing_apply_order
from keeper_sdk.core.sharing_models import SharingManifestV1, load_sharing_manifest
from keeper_sdk.core.vault_models import VaultManifestV1
from keeper_sdk.providers import (
    CommanderCliProvider,
    CommanderServiceProvider,
    KsmMockProvider,
    MockProvider,
)
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
_REPORT_HELP = """Run read-only Commander reports; prints redacted JSON to stdout.

Available reports:
  password-report        Weak-password rows from Commander password-report.
  compliance-report      Enterprise compliance table with graceful empty-cache handling.
  security-audit-report  Enterprise security-audit summary.
  vault-health           Vault posture findings from list-records metadata.
  ksm-usage              KSM app/share usage summary.
  team-roles             Enterprise team/role relationships from enterprise-info.
  team-report            Enterprise team rows from enterprise-info.
  role-report            Enterprise role rows from enterprise-info.
"""
_MSP_COMMANDER_UNSUPPORTED_REASON = (
    "MSP import and adoption are not implemented on commander provider "
    "(no declarative ownership marker writer for managed companies; see docs/MSP_FAMILY_DESIGN.md)"
)
_ENTERPRISE_IMPORT_UNSUPPORTED_REASON = (
    "keeper-enterprise.v1 import is supported for the mock provider only "
    "(Commander enterprise ownership marker writes are not implemented)"
)
_MSP_MANAGED_COMPANY_RESOURCE = "managed_company"
_ENTERPRISE_COLLECTIONS = ("nodes", "users", "roles", "teams", "enforcements", "aliases")


def _enterprise_live_object_count(live: dict[str, Any]) -> int:
    return sum(len(live.get(collection) or []) for collection in _ENTERPRISE_COLLECTIONS)


def _mock_adopt_managed_companies(self: MockProvider, plan: Plan) -> list[ApplyOutcome]:
    offenders = sorted(
        str(change.uid_ref or change.title or "<unknown>")
        for change in plan.changes
        if change.resource_type != _MSP_MANAGED_COMPANY_RESOURCE
    )
    if offenders:
        joined = ", ".join(offenders)
        raise ValueError(
            "MSP mock adoption only accepts managed_company rows; "
            f"offending uid_refs: {joined}; "
            "next_action: build an MSP-only adoption plan"
        )

    current = {str(row["name"]).casefold(): dict(row) for row in self.discover_managed_companies()}
    outcomes: list[ApplyOutcome] = []
    changed = False
    for change in _msp_plan_changes(plan):
        name = _msp_change_name(change)
        existing = current.get(name.casefold())

        if change.kind is ChangeKind.UPDATE:
            if existing is None:
                outcomes.append(
                    ApplyOutcome(
                        uid_ref=name,
                        keeper_uid=change.keeper_uid or "",
                        action="update",
                        details={"skipped": "record_missing"},
                    )
                )
                continue
            payload = {**existing, **change.after}
            payload["manager"] = str(change.after.get("manager") or plan.manifest_name)
            current[name.casefold()] = payload
            changed = True
            outcomes.append(
                ApplyOutcome(
                    uid_ref=name,
                    keeper_uid=str(payload.get("mc_enterprise_id") or change.keeper_uid or ""),
                    action="update",
                    details={"marker_written": True},
                )
            )
            continue

        if change.kind is ChangeKind.CONFLICT:
            outcomes.append(
                ApplyOutcome(
                    uid_ref=name,
                    keeper_uid=change.keeper_uid or "",
                    action="conflict",
                    details={"reason": change.reason or "blocked"},
                )
            )
            continue

        details: dict[str, Any] = {}
        if change.reason is not None:
            details["reason"] = change.reason
        outcomes.append(
            ApplyOutcome(
                uid_ref=name,
                keeper_uid=change.keeper_uid or "",
                action="noop",
                details=details,
            )
        )

    if changed:
        self.seed_managed_companies(list(current.values()))
    return outcomes


def _commander_adopt_managed_companies(
    self: CommanderCliProvider,
    plan: Plan,
) -> list[ApplyOutcome]:
    raise CapabilityError(_MSP_COMMANDER_UNSUPPORTED_REASON)


def _msp_change_name(change: Change) -> str:
    for payload in (change.after, change.before):
        value = payload.get("name")
        if value is not None:
            return str(value)
    return str(change.uid_ref or change.title)


def _msp_plan_changes(plan: Plan) -> list[Change]:
    ordered = plan.ordered()
    seen = {id(change) for change in ordered}
    return ordered + [change for change in plan.changes if id(change) not in seen]


if not hasattr(MockProvider, "adopt_managed_companies"):
    setattr(MockProvider, "adopt_managed_companies", _mock_adopt_managed_companies)
if not hasattr(CommanderCliProvider, "adopt_managed_companies"):
    setattr(CommanderCliProvider, "adopt_managed_companies", _commander_adopt_managed_companies)


@dataclass
class PlanLoadBundle:
    """Result of loading a manifest for plan/diff/apply."""

    pam: Manifest | None
    vault: VaultManifestV1 | None
    sharing: SharingManifestV1 | None
    msp: MspManifestV1 | None
    identity: IdentityManifestV1 | None
    ksm: KsmManifestV1 | None
    pam_extended: PamExtendedManifestV1 | None
    epm: EpmManifestV1 | None
    terraform: TerraformIntegrationManifestV1 | None
    k8s_eso: K8sEsoManifestV1 | None
    siem: SiemManifestV1 | None
    manifest_name: str
    order: list[str]
    live: list[LiveRecord]
    live_msp: list[dict[str, Any]]
    live_ksm: dict[str, list[dict[str, Any]]]
    live_record_type_defs: list[dict[str, Any]]
    provider: Any
    events: EventsManifestV1 | None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option()
@click.option(
    "--provider",
    type=click.Choice(["mock", "commander", "service"]),
    default="mock",
    show_default=True,
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
@click.option("--json", "as_json", is_flag=True, help="Emit validation summary as JSON on stdout")
@click.option(
    "--online",
    is_flag=True,
    help=(
        "Tenant checks: PAM discover+diff; keeper-vault.v1 discover+diff; "
        "MSP discover+diff; keeper-enterprise.v1 enterprise-info discover+diff"
    ),
)
@click.pass_context
def validate(
    ctx: click.Context,
    manifest_path: Path,
    emit_canonical: bool,
    as_json: bool,
    online: bool,
) -> None:
    """Validate JSON Schema for any packaged family; typed graph / online checks where wired."""
    try:
        document = read_manifest_document(manifest_path)
        family = validate_manifest(document)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except UnsupportedFamilyError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except ManifestError as exc:
        click.echo(f"manifest error: {exc}", err=True)
        sys.exit(EXIT_GENERIC)

    if family != PAM_FAMILY:
        if online and family not in (VAULT_MANIFEST_FAMILY, MSP_FAMILY, ENTERPRISE_FAMILY):
            click.echo(
                "`--online` is supported for pam-environment.v1, keeper-vault.v1, "
                "msp-environment.v1, and keeper-enterprise.v1 only.",
                err=True,
            )
            sys.exit(EXIT_CAPABILITY)

        if family == VAULT_MANIFEST_FAMILY:
            from keeper_sdk.core.vault_models import load_vault_manifest

            vm = load_vault_manifest(document)
            build_vault_graph(vm)
            uid_n = len(vm.iter_uid_refs())

            live: list[LiveRecord] | None = None
            online_suffix = ""
            create_count = update_count = delete_count = conflict_count = 0
            stage4_failed = False
            stage5_failed = False

            if online:
                if ctx.obj.get("provider") != "commander":
                    click.echo(
                        "`keeper-vault.v1` --online requires --provider commander "
                        "(tenant discover + diff smoke).",
                        err=True,
                    )
                    sys.exit(EXIT_CAPABILITY)
                folder_uid = ctx.obj.get("folder_uid") or os.environ.get(
                    "KEEPER_DECLARATIVE_FOLDER"
                )
                if not folder_uid:
                    click.echo(
                        "vault --online requires --folder-uid or KEEPER_DECLARATIVE_FOLDER.",
                        err=True,
                    )
                    sys.exit(EXIT_CAPABILITY)
                manifest_source = vm.model_dump(mode="python", exclude_none=True, by_alias=True)
                provider = CommanderCliProvider(
                    folder_uid=folder_uid, manifest_source=manifest_source
                )
                try:
                    live = provider.discover()
                except CapabilityError as exc:
                    click.echo(f"discovery failed: {exc}", err=True)
                    sys.exit(EXIT_CAPABILITY)

                gaps: list[str] = getattr(provider, "unsupported_capabilities", lambda _m: [])(vm)
                if gaps:
                    stage4_failed = True
                    if not as_json:
                        click.echo("capability gaps (will appear as plan conflicts):", err=True)
                        for reason in gaps:
                            click.echo(f"  - {reason}", err=True)

                try:
                    assert live is not None
                    live_records, live_record_type_defs = _vault_live_inputs(live)
                    changes = compute_vault_diff(
                        vm,
                        live_records,
                        manifest_name=manifest_path.stem,
                        adopt=False,
                        live_record_type_defs=live_record_type_defs,
                    )
                except OwnershipError as exc:
                    click.echo(f"ownership error: {exc}", err=True)
                    sys.exit(EXIT_CAPABILITY)

                create_count = sum(1 for c in changes if c.kind.value == "create")
                update_count = sum(1 for c in changes if c.kind.value == "update")
                delete_count = sum(1 for c in changes if c.kind.value == "delete")
                conflict_count = sum(1 for c in changes if c.kind.value == "conflict")
                if not as_json:
                    click.echo(
                        "stage 5: "
                        f"{create_count} create, "
                        f"{update_count} update, "
                        f"{delete_count} delete-candidates, "
                        f"{conflict_count} conflicts"
                    )

                binding_issues: list[str] = getattr(
                    provider, "check_tenant_bindings", lambda _m: []
                )(vm)
                if binding_issues:
                    stage5_failed = True
                    if not as_json:
                        click.echo("stage 5: tenant binding failures:", err=True)
                        for issue in binding_issues:
                            click.echo(f"  - {issue}", err=True)

                online_suffix = f"; online: {len(live)} live records"
                if stage4_failed or stage5_failed:
                    sys.exit(EXIT_CAPABILITY)

            if emit_canonical and not as_json:
                import yaml

                click.echo(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            if as_json:
                vpayload: dict[str, Any] = {
                    "ok": True,
                    "family": family,
                    "mode": "vault_online" if online else "vault_offline",
                    "manifest_path": str(manifest_path.resolve()),
                    "stages_completed": [
                        "json_schema",
                        "semantic_rules",
                        "typed_model",
                        "uid_ref_graph",
                    ],
                    "uid_ref_count": uid_n,
                    "online": online,
                }
                if online and live is not None:
                    vpayload["stages_completed"].extend(
                        ["tenant_capability", "tenant_bindings", "diff_smoke"]
                    )
                    vpayload["live_record_count"] = len(live)
                    vpayload["stage5_summary"] = {
                        "create": create_count,
                        "update": update_count,
                        "delete": delete_count,
                        "conflict": conflict_count,
                    }
                if emit_canonical:
                    import yaml

                    vpayload["canonical_yaml"] = yaml.safe_dump(
                        document, sort_keys=False, allow_unicode=True
                    )
                click.echo(json.dumps(vpayload, indent=2))
            else:
                msg = f"ok: vault ({uid_n} uid_refs)"
                if online_suffix:
                    msg += online_suffix
                click.echo(msg)
            return

        if family == ENTERPRISE_FAMILY:
            try:
                enterprise_manifest = load_enterprise_manifest(document)
                build_enterprise_graph(enterprise_manifest)
                order = enterprise_apply_order(enterprise_manifest)
            except SchemaError as exc:
                click.echo(f"validation failed: {exc}", err=True)
                sys.exit(EXIT_SCHEMA)
            except RefError as exc:
                click.echo(f"reference error: {exc}", err=True)
                sys.exit(EXIT_REF)

            live_enterprise: dict[str, Any] | None = None
            online_suffix = ""
            create_count = update_count = delete_count = conflict_count = 0
            noop_count = skip_count = 0

            if online:
                if ctx.obj.get("provider") != "commander":
                    click.echo(
                        "`keeper-enterprise.v1` --online requires --provider commander "
                        "(Commander CLI enterprise-info discover + diff smoke).",
                        err=True,
                    )
                    sys.exit(EXIT_CAPABILITY)
                provider = CommanderCliProvider()
                try:
                    live_enterprise = provider.discover_enterprise()
                except CapabilityError as exc:
                    click.echo(f"discovery failed: {exc}", err=True)
                    sys.exit(EXIT_CAPABILITY)

                changes = compute_enterprise_diff(
                    enterprise_manifest,
                    live_enterprise,
                    manifest_name=manifest_path.stem,
                )
                create_count = sum(1 for c in changes if c.kind.value == "create")
                update_count = sum(1 for c in changes if c.kind.value == "update")
                delete_count = sum(1 for c in changes if c.kind.value == "delete")
                conflict_count = sum(1 for c in changes if c.kind.value == "conflict")
                noop_count = sum(1 for c in changes if c.kind.value == "noop")
                skip_count = sum(1 for c in changes if c.kind.value == "skip")
                if not as_json:
                    click.echo(
                        "stage 5: "
                        f"{create_count} create, "
                        f"{update_count} update, "
                        f"{delete_count} delete-candidates, "
                        f"{conflict_count} conflicts, "
                        f"{noop_count} noop, "
                        f"{skip_count} skip"
                    )
                online_suffix = (
                    f"; online: {_enterprise_live_object_count(live_enterprise)} enterprise objects"
                )

            if emit_canonical and not as_json:
                import yaml

                click.echo(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            if as_json:
                epayload: dict[str, Any] = {
                    "ok": True,
                    "family": family,
                    "mode": "enterprise_online" if online else "enterprise_offline",
                    "manifest_path": str(manifest_path.resolve()),
                    "stages_completed": [
                        "json_schema",
                        "semantic_rules",
                        "typed_model",
                        "uid_ref_graph",
                    ],
                    "uid_ref_count": len(enterprise_manifest.iter_uid_refs()),
                    "online": online,
                }
                if online and live_enterprise is not None:
                    epayload["stages_completed"].append("diff_smoke")
                    epayload["live_enterprise_object_count"] = _enterprise_live_object_count(
                        live_enterprise
                    )
                    epayload["stage5_summary"] = {
                        "create": create_count,
                        "update": update_count,
                        "delete": delete_count,
                        "conflict": conflict_count,
                        "noop": noop_count,
                        "skip": skip_count,
                    }
                if emit_canonical:
                    import yaml

                    epayload["canonical_yaml"] = yaml.safe_dump(
                        document, sort_keys=False, allow_unicode=True
                    )
                click.echo(json.dumps(epayload, indent=2))
            else:
                click.echo(f"ok: {ENTERPRISE_FAMILY} ({len(order)} uid_refs){online_suffix}")
            return

        if family == MSP_FAMILY:
            try:
                msp_manifest = load_msp_manifest(document)
                order = msp_apply_order(msp_manifest)
            except SchemaError as exc:
                click.echo(f"validation failed: {exc}", err=True)
                sys.exit(EXIT_SCHEMA)
            except RefError as exc:
                click.echo(f"reference error: {exc}", err=True)
                sys.exit(EXIT_REF)

            live_msp: list[dict[str, Any]] | None = None
            online_suffix = ""
            create_count = update_count = delete_count = conflict_count = 0
            noop_count = skip_count = 0

            if online:
                provider = _make_provider(ctx, manifest_path, msp=msp_manifest)
                try:
                    live_msp = provider.discover_managed_companies()
                except CapabilityError as exc:
                    click.echo(f"discovery failed: {exc}", err=True)
                    sys.exit(EXIT_CAPABILITY)

                changes = compute_msp_diff(msp_manifest, live_msp)
                create_count = sum(1 for c in changes if c.kind.value == "create")
                update_count = sum(1 for c in changes if c.kind.value == "update")
                delete_count = sum(1 for c in changes if c.kind.value == "delete")
                conflict_count = sum(1 for c in changes if c.kind.value == "conflict")
                noop_count = sum(1 for c in changes if c.kind.value == "noop")
                skip_count = sum(1 for c in changes if c.kind.value == "skip")
                if not as_json:
                    click.echo(
                        "stage 5: "
                        f"{create_count} create, "
                        f"{update_count} update, "
                        f"{delete_count} delete-candidates, "
                        f"{conflict_count} conflicts, "
                        f"{noop_count} noop, "
                        f"{skip_count} skip"
                    )
                online_suffix = f"; online: {len(live_msp)} live managed_companies"

            if emit_canonical and not as_json:
                import yaml

                click.echo(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            if as_json:
                mpayload: dict[str, Any] = {
                    "ok": True,
                    "family": family,
                    "mode": "msp_online" if online else "msp_offline",
                    "manifest_name": msp_manifest.name,
                    "manifest_path": str(manifest_path.resolve()),
                    "stages_completed": [
                        "json_schema",
                        "semantic_rules",
                        "typed_model",
                        "managed_company_graph",
                    ],
                    "managed_company_count": len(order),
                    "online": online,
                }
                if online and live_msp is not None:
                    mpayload["stages_completed"].append("diff_smoke")
                    mpayload["live_managed_company_count"] = len(live_msp)
                    mpayload["stage5_summary"] = {
                        "create": create_count,
                        "update": update_count,
                        "delete": delete_count,
                        "conflict": conflict_count,
                        "noop": noop_count,
                        "skip": skip_count,
                    }
                if emit_canonical:
                    import yaml

                    mpayload["canonical_yaml"] = yaml.safe_dump(
                        document, sort_keys=False, allow_unicode=True
                    )
                click.echo(json.dumps(mpayload, indent=2))
            else:
                click.echo(f"ok: {MSP_FAMILY} ({len(order)} managed_companies){online_suffix}")
            return

        if family == SHARING_FAMILY:
            try:
                sharing_manifest = load_sharing_manifest(document)
                order = sharing_apply_order(sharing_manifest)
            except SchemaError as exc:
                click.echo(f"validation failed: {exc}", err=True)
                sys.exit(EXIT_SCHEMA)
            except RefError as exc:
                click.echo(f"reference error: {exc}", err=True)
                sys.exit(EXIT_REF)
            uid_n = len(order)
            if emit_canonical and not as_json:
                import yaml

                click.echo(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
            if as_json:
                spayload: dict[str, Any] = {
                    "ok": True,
                    "family": family,
                    "mode": "sharing_offline",
                    "manifest_path": str(manifest_path.resolve()),
                    "stages_completed": [
                        "json_schema",
                        "semantic_rules",
                        "typed_model",
                        "uid_ref_graph",
                    ],
                    "uid_ref_count": uid_n,
                    "online": False,
                }
                if emit_canonical:
                    import yaml

                    spayload["canonical_yaml"] = yaml.safe_dump(
                        document, sort_keys=False, allow_unicode=True
                    )
                click.echo(json.dumps(spayload, indent=2))
            else:
                click.echo(f"ok: {SHARING_FAMILY} ({uid_n} uid_refs); online stages skipped.")
            return

        if emit_canonical and not as_json:
            import yaml

            click.echo(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
        if as_json:
            payload: dict[str, Any] = {
                "ok": True,
                "family": family,
                "mode": "schema_only",
                "manifest_path": str(manifest_path.resolve()),
                "stages_completed": ["json_schema", "semantic_rules"],
            }
            if emit_canonical:
                import yaml

                payload["canonical_yaml"] = yaml.safe_dump(
                    document, sort_keys=False, allow_unicode=True
                )
            click.echo(json.dumps(payload, indent=2))
        else:
            click.echo(
                f"ok: schema-valid ({family}); uid_ref graph + online stages skipped "
                f"(PAM-only until docs/PAM_PARITY_PROGRAM.md provider slices land)."
            )
        return

    try:
        assert_preview_keys_allowed(document)
        manifest = Manifest.model_validate(document)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)

    # uid_ref graph sanity
    try:
        build_graph(manifest)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)

    online_suffix = ""
    pam_live: list[LiveRecord] | None = None
    if online:
        provider = _make_provider(ctx, manifest_path, pam=manifest, vault=None)
        try:
            pam_live = provider.discover()
        except CapabilityError as exc:
            click.echo(f"discovery failed: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)

        pam_gaps: list[str] = getattr(provider, "unsupported_capabilities", lambda _m: [])(manifest)
        stage4_failed = False
        if pam_gaps:
            if not as_json:
                click.echo("capability gaps (will appear as plan conflicts):", err=True)
                for reason in pam_gaps:
                    click.echo(f"  - {reason}", err=True)
            stage4_failed = True

        live_gateway_names = {
            record.title for record in pam_live if record.resource_type == "gateway"
        }
        for gateway in manifest.gateways:
            if gateway.mode != "reference_existing":
                continue
            if gateway.name in live_gateway_names:
                continue
            if not as_json:
                click.echo(f"stage 4: gateway '{gateway.name}' not found in tenant", err=True)
            stage4_failed = True

        try:
            changes = compute_diff(manifest, pam_live, adopt=False)
        except OwnershipError as exc:
            click.echo(f"ownership error: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)

        create_count = sum(1 for change in changes if change.kind.value == "create")
        update_count = sum(1 for change in changes if change.kind.value == "update")
        delete_count = sum(1 for change in changes if change.kind.value == "delete")
        conflict_count = sum(1 for change in changes if change.kind.value == "conflict")
        if not as_json:
            click.echo(
                "stage 5: "
                f"{create_count} create, "
                f"{update_count} update, "
                f"{delete_count} delete-candidates, "
                f"{conflict_count} conflicts"
            )

        pam_binding_issues: list[str] = getattr(provider, "check_tenant_bindings", lambda _m: [])(
            manifest
        )
        stage5_failed = False
        if pam_binding_issues:
            stage5_failed = True
            if not as_json:
                click.echo("stage 5: tenant binding failures:", err=True)
                for issue in pam_binding_issues:
                    click.echo(f"  - {issue}", err=True)

        online_suffix = f"; online: {len(pam_live)} live records"
        if stage4_failed or stage5_failed:
            sys.exit(EXIT_CAPABILITY)

    uid_n = len(manifest.iter_uid_refs())
    if as_json:
        payload = {
            "ok": True,
            "family": PAM_FAMILY,
            "mode": "pam_full",
            "manifest_name": manifest.name,
            "uid_ref_count": uid_n,
            "stages_completed": ["json_schema", "semantic_rules", "typed_model", "uid_ref_graph"],
        }
        if online:
            assert pam_live is not None
            payload["stages_completed"].extend(
                ["tenant_capability", "tenant_bindings", "diff_smoke"]
            )
            payload["online"] = True
            payload["live_record_count"] = len(pam_live)
            payload["stage5_summary"] = {
                "create": create_count,
                "update": update_count,
                "delete": delete_count,
                "conflict": conflict_count,
            }
        else:
            payload["online"] = False
        if emit_canonical:
            payload["canonical_yaml"] = dump_manifest(manifest, fmt="yaml")
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(f"ok: {manifest.name} ({uid_n} uid_refs){online_suffix}")
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
    """Lift a Commander-shaped PAM project JSON document into a manifest."""
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
@click.option(
    "--format",
    "output_format",
    metavar="FORMAT",
    default=None,
    help="Emit plan as table or json; other formats are reserved capability stubs",
)
@click.option(
    "--provider",
    "provider_override",
    type=click.Choice(["mock", "commander", "service"]),
    default=None,
    help="Override the configured provider",
)
@click.pass_context
def plan(
    ctx: click.Context,
    manifest_path: Path,
    allow_delete: bool,
    as_json: bool,
    output_format: str | None,
    provider_override: str | None,
) -> None:
    """Compute an execution plan against the configured provider.

    Exits 0 when the plan is clean, 2 when changes are present, 4 when conflicts exist.
    """
    if provider_override is not None:
        ctx.obj["provider"] = provider_override
    try:
        resolved_format = _resolve_plan_output_format(as_json, output_format)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    plan_obj = _build_plan(ctx, manifest_path, allow_delete=allow_delete)
    if resolved_format == "json":
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
    try:
        document = read_manifest_document(manifest_path)
        fam = validate_manifest(document)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except UnsupportedFamilyError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except ManifestError as exc:
        click.echo(f"manifest error: {exc}", err=True)
        sys.exit(EXIT_GENERIC)
    if fam != PAM_FAMILY:
        if fam == ENTERPRISE_FAMILY:
            if ctx.obj.get("provider") != "mock":
                click.echo(f"provider error: {_ENTERPRISE_IMPORT_UNSUPPORTED_REASON}", err=True)
                sys.exit(EXIT_CAPABILITY)
            try:
                enterprise_manifest = load_enterprise_manifest(document)
                build_enterprise_graph(enterprise_manifest)
                order = enterprise_apply_order(enterprise_manifest)
            except SchemaError as exc:
                click.echo(f"validation failed: {exc}", err=True)
                sys.exit(EXIT_SCHEMA)
            except RefError as exc:
                click.echo(f"reference error: {exc}", err=True)
                sys.exit(EXIT_REF)

            provider = _make_provider(ctx, manifest_path, enterprise=enterprise_manifest)
            try:
                live_enterprise = provider.discover_enterprise()
            except CapabilityError as exc:
                click.echo(f"discovery failed: {exc}", err=True)
                sys.exit(EXIT_CAPABILITY)

            changes = compute_enterprise_diff(
                enterprise_manifest,
                live_enterprise,
                manifest_name=manifest_path.stem,
                adopt=True,
            )
            import_changes = [
                change
                for change in changes
                if (change.kind is ChangeKind.UPDATE and "adoption" in (change.reason or ""))
                or change.kind is ChangeKind.CONFLICT
            ]
            plan_obj = build_plan(manifest_path.stem, import_changes, order)

            click.echo(ctx.obj["renderer"].render_plan(plan_obj))
            for change in plan_obj.updates:
                if change.reason:
                    click.echo(f"adoption: {change.uid_ref or change.title}: {change.reason}")
            if plan_obj.conflicts:
                for conflict in plan_obj.conflicts:
                    click.echo(
                        f"conflict: {conflict.uid_ref or conflict.title}: "
                        f"{conflict.reason or 'blocked'}",
                        err=True,
                    )
                sys.exit(EXIT_CONFLICT)
            if plan_obj.is_clean:
                click.echo("no records to adopt.")
                sys.exit(EXIT_OK)
            if dry_run:
                sys.exit(EXIT_OK)
            if not auto_approve:
                click.confirm("Proceed?", abort=True)

            try:
                outcomes = provider.adopt_enterprise_plan(plan_obj)
            except CapabilityError as exc:
                click.echo(f"provider error: {exc}", err=True)
                sys.exit(EXIT_CAPABILITY)

            click.echo(ctx.obj["renderer"].render_outcomes(outcomes))
            sys.exit(EXIT_OK)
        if fam == MSP_FAMILY:
            if ctx.obj.get("provider") == "commander":
                click.echo(f"provider error: {_MSP_COMMANDER_UNSUPPORTED_REASON}", err=True)
                sys.exit(EXIT_CAPABILITY)
            bundle = _load_plan_context(ctx, manifest_path)
            msp_manifest = bundle.msp
            assert msp_manifest is not None
            changes = compute_msp_diff(msp_manifest, bundle.live_msp, adopt=True)
            adopt_changes = [
                change
                for change in changes
                if change.kind is ChangeKind.UPDATE and "adoption" in (change.reason or "")
            ]
            plan_obj = build_plan(bundle.manifest_name, adopt_changes, bundle.order)

            click.echo(ctx.obj["renderer"].render_plan(plan_obj))
            if plan_obj.is_clean:
                click.echo("no records to adopt.")
                sys.exit(EXIT_OK)
            if dry_run:
                sys.exit(EXIT_OK)
            if not auto_approve:
                click.confirm("Proceed?", abort=True)

            try:
                outcomes = bundle.provider.adopt_managed_companies(plan_obj)
            except CapabilityError as exc:
                click.echo(f"provider error: {exc}", err=True)
                sys.exit(EXIT_CAPABILITY)

            click.echo(ctx.obj["renderer"].render_outcomes(outcomes))
            sys.exit(EXIT_OK)
        click.echo("capability error: dsk import applies to pam-environment.v1 only.", err=True)
        sys.exit(EXIT_CAPABILITY)

    bundle = _load_plan_context(ctx, manifest_path)
    pam_manifest = bundle.pam
    assert pam_manifest is not None
    order, live = bundle.order, bundle.live
    try:
        changes = compute_diff(pam_manifest, live, adopt=True)
    except OwnershipError as exc:
        click.echo(f"ownership error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    adopt_changes = [
        change
        for change in changes
        if change.kind is ChangeKind.UPDATE and "adoption" in (change.reason or "")
    ]
    plan_obj = build_plan(pam_manifest.name, adopt_changes, order)

    click.echo(ctx.obj["renderer"].render_plan(plan_obj))
    if plan_obj.is_clean:
        click.echo("no records to adopt.")
        sys.exit(EXIT_OK)
    if dry_run:
        sys.exit(EXIT_OK)
    if not auto_approve:
        click.confirm("Proceed?", abort=True)

    provider = bundle.provider
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
@click.option("--auto-approve", "--yes", is_flag=True)
@click.option("--dry-run", is_flag=True, help="Render what would run without mutating")
@click.option(
    "--provider",
    "provider_override",
    type=click.Choice(["mock", "commander", "service"]),
    default=None,
    help="Override the configured provider",
)
@click.pass_context
def apply(
    ctx: click.Context,
    manifest_path: Path,
    allow_delete: bool,
    auto_approve: bool,
    dry_run: bool,
    provider_override: str | None,
) -> None:
    """Apply a manifest via the selected provider."""
    if provider_override is not None:
        ctx.obj["provider"] = provider_override
    plan_obj = _build_plan(ctx, manifest_path, allow_delete=allow_delete)
    if dry_run:
        click.echo(ctx.obj["renderer"].render_plan(plan_obj))
        sys.exit(_exit_from_plan(plan_obj))

    click.echo(ctx.obj["renderer"].render_plan(plan_obj))
    if plan_obj.is_clean:
        click.echo("nothing to do.")
        sys.exit(EXIT_OK)
    if plan_obj.conflicts and not allow_delete:
        for conflict in plan_obj.conflicts:
            if conflict.reason:
                click.echo(f"conflict: {conflict.reason}", err=True)
        click.echo(f"{len(plan_obj.conflicts)} conflict(s) must be resolved first.", err=True)
        sys.exit(EXIT_CONFLICT)
    bundle = ctx.obj["_plan_bundle"]
    if bundle.pam_extended is not None:
        click.echo(
            (
                f"provider error: {PAM_EXTENDED_FAMILY} apply is upstream-gap "
                "(offline schema/model/diff and plan only; no Commander write/readback proof)"
            ),
            err=True,
        )
        sys.exit(EXIT_CAPABILITY)
    if not auto_approve and not dry_run:
        click.confirm("Proceed?", abort=True)
    provider = bundle.provider
    try:
        if bundle.msp is not None:
            outcomes = provider.apply_msp_plan(plan_obj, dry_run=dry_run)
        elif bundle.ksm is not None:
            if not hasattr(provider, "apply_ksm_plan"):
                raise CapabilityError(
                    reason=(
                        f"provider {ctx.obj.get('provider', 'mock')!r} has no KSM apply support"
                    ),
                    next_action=(
                        "use `--provider commander` for supported KSM app lifecycle rows "
                        "or `--provider mock` for full offline simulation"
                    ),
                )
            outcomes = provider.apply_ksm_plan(plan_obj, dry_run=dry_run)
        else:
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
    bundle = _load_plan_context(ctx, manifest_path)
    ctx.obj["_plan_bundle"] = bundle
    capability_subject: (
        Manifest
        | VaultManifestV1
        | SharingManifestV1
        | MspManifestV1
        | IdentityManifestV1
        | KsmManifestV1
        | EventsManifestV1
        | PamExtendedManifestV1
        | EpmManifestV1
        | TerraformIntegrationManifestV1
        | K8sEsoManifestV1
        | SiemManifestV1
    )
    try:
        if bundle.pam is not None:
            changes = compute_diff(
                bundle.pam,
                bundle.live,
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.pam
        elif bundle.vault is not None:
            changes = compute_vault_diff(
                bundle.vault,
                bundle.live,
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
                live_record_type_defs=bundle.live_record_type_defs,
            )
            capability_subject = bundle.vault
        elif bundle.msp is not None:
            changes = compute_msp_diff(
                bundle.msp,
                bundle.live_msp,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.msp
        elif bundle.sharing is not None:
            changes = _build_sharing_changes(
                bundle.provider,
                bundle.sharing,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.sharing
        elif bundle.identity is not None:
            changes = compute_identity_diff(
                bundle.identity,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise CapabilityError(
                reason=(
                    f"{IDENTITY_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Commander identity write verb confirmed)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a Commander "
                    "identity writer"
                ),
            )
        elif bundle.ksm is not None:
            changes = compute_ksm_diff(
                bundle.ksm,
                bundle.live_ksm,
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.ksm
        elif bundle.events is not None:
            changes = compute_events_diff(
                bundle.events,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise CapabilityError(
                reason=(
                    f"{EVENTS_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Commander events write verb confirmed)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a Commander events writer"
                ),
            )
        elif bundle.pam_extended is not None:
            changes = compute_pam_extended_diff(
                bundle.pam_extended,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.pam_extended
        elif bundle.epm is not None:
            changes = compute_epm_diff(
                bundle.epm,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise CapabilityError(
                reason=(
                    f"{EPM_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no PEDM tenant write/readback proof)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a PEDM tenant "
                    "writer proven through MSP managed-company lab context"
                ),
            )
        elif bundle.terraform is not None:
            raise CapabilityError(
                reason=(
                    f"{TERRAFORM_FAMILY} plan/apply is upstream-gap "
                    "(schema/model boundary metadata only; Terraform state remains the writer)"
                ),
                next_action=(
                    "use `dsk validate` for mapping checks; run Terraform for Terraform-owned "
                    "resources and DSK manifests for DSK-owned Keeper objects"
                ),
            )
        elif bundle.k8s_eso is not None:
            raise CapabilityError(
                reason=(
                    f"{K8S_ESO_FAMILY} plan/apply is upstream-gap "
                    "(schema/model/YAML generation only; Kubernetes remains the writer)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; render ESO YAML with "
                    "keeper_sdk.integrations.k8s and apply it through your Kubernetes "
                    "delivery path"
                ),
            )
        elif bundle.siem is not None:
            changes = compute_siem_diff(
                bundle.siem,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise CapabilityError(
                reason=(
                    f"{SIEM_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Keeper SIEM writer/discover hook)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a supported "
                    "SIEM configuration writer and readback surface"
                ),
            )
        else:
            raise CapabilityError(
                "plan is not supported for this manifest family; "
                "use `dsk validate` to check schema only",
                next_action="dsk validate <path>",
            )
    except OwnershipError as exc:
        click.echo(f"ownership error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except CapabilityError as exc:
        click.echo(f"discovery failed: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    # Surface provider capability gaps as CONFLICT rows so plan / dry-run /
    # apply are behaviourally identical (DELIVERY_PLAN.md: "plan == apply
    # --dry-run"). Without this, CommanderCliProvider.apply_plan would only
    # raise at real-apply time — operators would see green plans. See
    # REVIEW.md "Update — second pass / C3".
    try:
        capability_gaps = bundle.provider.unsupported_capabilities(capability_subject)
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

    plan_obj = build_plan(bundle.manifest_name, changes, bundle.order)
    setattr(plan_obj, "allow_delete", allow_delete)
    return plan_obj


def _load_plan_context(ctx: click.Context, manifest_path: Path) -> PlanLoadBundle:
    try:
        typed = load_declarative_manifest(manifest_path)
    except SchemaError as exc:
        click.echo(f"validation failed: {exc}", err=True)
        sys.exit(EXIT_SCHEMA)
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except UnsupportedFamilyError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except ManifestError as exc:
        click.echo(f"manifest error: {exc}", err=True)
        sys.exit(EXIT_GENERIC)

    pam: Manifest | None = typed if isinstance(typed, Manifest) else None
    vault: VaultManifestV1 | None = typed if isinstance(typed, VaultManifestV1) else None
    sharing: SharingManifestV1 | None = typed if isinstance(typed, SharingManifestV1) else None
    msp: MspManifestV1 | None = typed if isinstance(typed, MspManifestV1) else None
    identity: IdentityManifestV1 | None = typed if isinstance(typed, IdentityManifestV1) else None
    ksm: KsmManifestV1 | None = typed if isinstance(typed, KsmManifestV1) else None
    pam_extended: PamExtendedManifestV1 | None = (
        typed if isinstance(typed, PamExtendedManifestV1) else None
    )
    epm: EpmManifestV1 | None = typed if isinstance(typed, EpmManifestV1) else None
    terraform: TerraformIntegrationManifestV1 | None = (
        typed if isinstance(typed, TerraformIntegrationManifestV1) else None
    )
    k8s_eso: K8sEsoManifestV1 | None = typed if isinstance(typed, K8sEsoManifestV1) else None
    siem: SiemManifestV1 | None = typed if isinstance(typed, SiemManifestV1) else None
    events: EventsManifestV1 | None = typed if isinstance(typed, EventsManifestV1) else None
    if pam is not None:
        manifest_name = pam.name
    elif msp is not None:
        manifest_name = msp.name
    elif identity is not None:
        manifest_name = IDENTITY_FAMILY
    elif events is not None:
        manifest_name = events.name
    elif pam_extended is not None:
        manifest_name = PAM_EXTENDED_FAMILY
    elif epm is not None:
        manifest_name = EPM_FAMILY
    elif terraform is not None:
        manifest_name = TERRAFORM_FAMILY
    elif k8s_eso is not None:
        manifest_name = K8S_ESO_FAMILY
    elif siem is not None:
        manifest_name = siem.name or SIEM_FAMILY
    else:
        manifest_name = manifest_path.stem

    try:
        if pam is not None:
            graph = build_graph(pam)
            order = execution_order(graph)
        elif vault is not None:
            assert vault is not None
            order = vault_record_apply_order(vault)
        elif msp is not None:
            order = msp_apply_order(msp)
        elif sharing is not None:
            order = sharing_apply_order(sharing)
        elif identity is not None:
            raise CapabilityError(
                reason=(
                    f"{IDENTITY_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Commander identity write verb confirmed)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a Commander "
                    "identity writer"
                ),
            )
        elif ksm is not None:
            provider_name = ctx.obj.get("provider", "mock")
            if provider_name == "service":
                raise CapabilityError(
                    reason=(
                        f"{KSM_FAMILY} plan/apply is not implemented for {provider_name} provider"
                    ),
                    next_action=(
                        "use `--provider commander` for supported KSM app lifecycle rows "
                        "or `--provider mock` for full offline simulation"
                    ),
                )
            order = ksm_apply_order(ksm)
        elif events is not None:
            raise CapabilityError(
                reason=(
                    f"{EVENTS_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Commander events write verb confirmed)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a Commander events writer"
                ),
            )
        elif pam_extended is not None:
            order = [uid_ref for uid_ref, _kind in pam_extended.iter_object_refs()]
        elif epm is not None:
            raise CapabilityError(
                reason=(
                    f"{EPM_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no PEDM tenant write/readback proof)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a PEDM tenant "
                    "writer proven through MSP managed-company lab context"
                ),
            )
        elif terraform is not None:
            raise CapabilityError(
                reason=(
                    f"{TERRAFORM_FAMILY} plan/apply is upstream-gap "
                    "(schema/model boundary metadata only; Terraform state remains the writer)"
                ),
                next_action=(
                    "use `dsk validate` for mapping checks; run Terraform for Terraform-owned "
                    "resources and DSK manifests for DSK-owned Keeper objects"
                ),
            )
        elif k8s_eso is not None:
            raise CapabilityError(
                reason=(
                    f"{K8S_ESO_FAMILY} plan/apply is upstream-gap "
                    "(schema/model/YAML generation only; Kubernetes remains the writer)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; render ESO YAML with "
                    "keeper_sdk.integrations.k8s and apply it through your Kubernetes "
                    "delivery path"
                ),
            )
        elif siem is not None:
            raise CapabilityError(
                reason=(
                    f"{SIEM_FAMILY} plan/apply is upstream-gap "
                    "(offline schema/model/diff only; no Keeper SIEM writer/discover hook)"
                ),
                next_action=(
                    "use `dsk validate` for schema checks; apply waits on a supported "
                    "SIEM configuration writer and readback surface"
                ),
            )
        else:
            raise CapabilityError(
                "plan is not supported for this manifest family; "
                "use `dsk validate` to check schema only",
                next_action="dsk validate <path>",
            )
    except RefError as exc:
        click.echo(f"reference error: {exc}", err=True)
        sys.exit(EXIT_REF)
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    provider = _make_provider(
        ctx,
        manifest_path,
        pam=pam,
        vault=vault,
        sharing=sharing,
        msp=msp,
        ksm=ksm,
    )
    live_record_type_defs: list[dict[str, Any]] = []
    live: list[LiveRecord] = []
    live_msp: list[dict[str, Any]] = []
    live_ksm: dict[str, list[dict[str, Any]]] = {}
    if ksm is not None:
        try:
            discover_ksm_state = provider.discover_ksm_state
        except AttributeError:
            click.echo(
                f"discovery failed: provider {ctx.obj.get('provider', 'mock')!r} has no KSM discovery support",
                err=True,
            )
            sys.exit(EXIT_CAPABILITY)
        try:
            live_ksm = discover_ksm_state()
        except CapabilityError as exc:
            click.echo(f"discovery failed: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)
    elif msp is not None:
        try:
            live_msp = provider.discover_managed_companies()
        except CapabilityError as exc:
            click.echo(f"discovery failed: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)
    elif sharing is None and pam_extended is None:
        try:
            live = provider.discover()
        except CapabilityError as exc:
            click.echo(f"discovery failed: {exc}", err=True)
            sys.exit(EXIT_CAPABILITY)
        if vault is not None:
            live, live_record_type_defs = _vault_live_inputs(live)

    return PlanLoadBundle(
        pam=pam,
        vault=vault,
        sharing=sharing,
        msp=msp,
        identity=identity,
        ksm=ksm,
        pam_extended=pam_extended,
        epm=epm,
        terraform=terraform,
        k8s_eso=k8s_eso,
        siem=siem,
        manifest_name=manifest_name,
        order=order,
        live=live,
        live_msp=live_msp,
        live_ksm=live_ksm,
        live_record_type_defs=live_record_type_defs,
        provider=provider,
        events=events,
    )


def _vault_live_inputs(live: list[LiveRecord]) -> tuple[list[LiveRecord], list[dict[str, Any]]]:
    records: list[LiveRecord] = []
    record_type_defs: list[dict[str, Any]] = []
    for record in live:
        if record.resource_type == "record_type":
            record_type_defs.append(
                {
                    "keeper_uid": record.keeper_uid,
                    "title": record.title,
                    "resource_type": record.resource_type,
                    "payload": dict(record.payload),
                    "marker": dict(record.marker) if record.marker else None,
                }
            )
            continue
        records.append(record)
    return records, record_type_defs


def _build_sharing_changes(
    provider: Any,
    manifest: SharingManifestV1,
    *,
    allow_delete: bool,
) -> list[Change]:
    live_by_type = _sharing_live_rows_by_type(provider.discover())
    manifest_name = getattr(provider, "_manifest_name", None) or "vault-sharing"
    return compute_sharing_diff(
        manifest,
        live_folders=live_by_type["sharing_folder"],
        live_shared_folders=live_by_type["sharing_shared_folder"],
        live_share_records=live_by_type["sharing_record_share"],
        live_share_folders=live_by_type["sharing_share_folder"],
        manifest_name=manifest_name,
        allow_delete=allow_delete,
    )


def _sharing_live_rows_by_type(live: list[LiveRecord]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        "sharing_folder": [],
        "sharing_shared_folder": [],
        "sharing_record_share": [],
        "sharing_share_folder": [],
    }
    for record in live:
        if record.resource_type not in rows:
            continue
        rows[record.resource_type].append(
            {
                "keeper_uid": record.keeper_uid,
                "resource_type": record.resource_type,
                "title": record.title,
                "payload": dict(record.payload),
                "marker": dict(record.marker) if record.marker else None,
            }
        )
    return rows


def _make_provider(
    ctx: click.Context,
    manifest_path: Path,
    *,
    pam: Manifest | None = None,
    vault: VaultManifestV1 | None = None,
    sharing: SharingManifestV1 | None = None,
    msp: MspManifestV1 | None = None,
    ksm: KsmManifestV1 | None = None,
    enterprise: EnterpriseManifestV1 | None = None,
):
    provider_name = ctx.obj.get("provider", "mock")
    folder_uid = ctx.obj.get("folder_uid")
    if pam is not None:
        manifest_name = pam.name
    elif msp is not None:
        manifest_name = msp.name
    else:
        manifest_name = manifest_path.stem
    if provider_name == "mock" and ksm is not None:
        return ctx.obj.setdefault("_ksm_provider_instance", KsmMockProvider(manifest_name))
    if provider_name == "mock":
        return ctx.obj.setdefault("_provider_instance", MockProvider(manifest_name))
    if provider_name == "commander":
        manifest_source: dict[str, Any] = {}
        if pam is not None:
            manifest_source = pam.model_dump(mode="python", exclude_none=True)
        elif vault is not None:
            manifest_source = vault.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif sharing is not None:
            manifest_source = sharing.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif msp is not None:
            manifest_source = msp.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif ksm is not None:
            manifest_source = ksm.model_dump(mode="python", exclude_none=True, by_alias=True)
            manifest_source.setdefault("name", manifest_path.stem)
        elif enterprise is not None:
            manifest_source = enterprise.model_dump(mode="python", exclude_none=True, by_alias=True)
        return CommanderCliProvider(
            folder_uid=folder_uid or os.environ.get("KEEPER_DECLARATIVE_FOLDER"),
            manifest_source=manifest_source,
        )
    if provider_name == "service":
        manifest_source = {}
        if pam is not None:
            manifest_source = pam.model_dump(mode="python", exclude_none=True)
        elif vault is not None:
            manifest_source = vault.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif sharing is not None:
            manifest_source = sharing.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif msp is not None:
            manifest_source = msp.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif ksm is not None:
            manifest_source = ksm.model_dump(mode="python", exclude_none=True, by_alias=True)
        elif enterprise is not None:
            manifest_source = enterprise.model_dump(mode="python", exclude_none=True, by_alias=True)
        return CommanderServiceProvider(
            base_url=os.environ.get("KEEPER_SERVICE_URL", "http://localhost:4020"),
            api_key=os.environ.get("KEEPER_SERVICE_API_KEY"),
            timeout=int(os.environ.get("KEEPER_SERVICE_TIMEOUT", "300")),
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
            next_action="pip install keepercommander>=17.2.16,<18",
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


def _resolve_plan_output_format(as_json: bool, output_format: str | None) -> str:
    if output_format is None:
        return "json" if as_json else "table"

    normalized = output_format.strip().lower()
    if normalized in {"json", "table"}:
        return normalized

    raise CapabilityError(
        reason=(
            f"plan output format `{output_format}` is not implemented "
            "(supported formats: json, table)"
        ),
        next_action="use `--json`, `--format json`, or `--format table`",
    )


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
    from keeper_sdk.cli._report.common import (
        ReportOutputLeakError,
        serialize_report_payload,
    )

    try:
        click.echo(serialize_report_payload(payload))
    except ReportOutputLeakError as exc:
        click.echo(f"report refused: output failed leak check: {exc.warnings!r}", err=True)
        sys.exit(EXIT_GENERIC)
    sys.exit(EXIT_OK)


def _run_argv_from_command(command: tuple[str, ...]) -> list[str]:
    if not command:
        raise click.UsageError("missing Commander command")
    if len(command) == 1:
        return shlex.split(command[0])
    return list(command)


def _redact_run_output(text: str, *, sanitize_uids: bool) -> str:
    if not text:
        return ""
    from keeper_sdk.cli._live.transcript import _sanitize_value
    from keeper_sdk.core.redact import redact as redact_secrets

    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            redacted = str(redact_secrets(text))
        else:
            redacted = json.dumps(redact_secrets(parsed), indent=2)
            if text.endswith("\n"):
                redacted += "\n"
    else:
        redacted = str(redact_secrets(text))
    if sanitize_uids:
        redacted = str(_sanitize_value(redacted))
    return redacted


def _echo_preserving_newline(text: str, *, err: bool = False) -> None:
    if text:
        click.echo(text, nl=not text.endswith("\n"), err=err)


@main.command("run", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.option(
    "--sanitize-uids",
    is_flag=True,
    help="Fingerprint UID-like substrings in Commander output",
)
@click.option("--json", "as_json", is_flag=True, help="Append --json to the Commander command")
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def run_commander(
    ctx: click.Context,
    sanitize_uids: bool,
    as_json: bool,
    command: tuple[str, ...],
) -> None:
    """Run an arbitrary Commander command via the configured Commander session."""
    if ctx.obj.get("provider") != "commander":
        click.echo(
            "capability error: dsk run requires --provider commander; "
            "mock provider has no Commander session; "
            "next_action: dsk --provider commander run <commander-command>",
            err=True,
        )
        sys.exit(EXIT_CAPABILITY)

    try:
        argv = _run_argv_from_command(command)
        if as_json and "--json" not in argv:
            argv.append("--json")
        from keeper_sdk.cli._report import runner as keeper_runner

        result = keeper_runner.run_keeper_passthrough(
            argv,
            keeper_bin=os.environ.get("KEEPER_BIN"),
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    except CapabilityError as exc:
        click.echo(f"capability error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)

    _echo_preserving_newline(_redact_run_output(result.stdout or "", sanitize_uids=sanitize_uids))
    _echo_preserving_newline(
        _redact_run_output(result.stderr or "", sanitize_uids=sanitize_uids),
        err=True,
    )
    sys.exit(result.returncode)


@main.group("report", help=_REPORT_HELP)
def report_cli() -> None:
    """Run read-only Commander reports."""


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
    "--no-fail-on-empty/--fail-on-empty",
    default=True,
    show_default=True,
    help="Exit 0 with a warning envelope when the no-rebuild compliance cache is empty",
)
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
    no_fail_on_empty: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Default enterprise compliance table via ``keeper compliance report``."""
    from keeper_sdk.cli._report.compliance import (
        COMPLIANCE_CACHE_EMPTY_WARNING,
        run_compliance_report,
    )

    try:
        payload = run_compliance_report(
            node=node,
            username=username,
            team=team,
            rebuild=rebuild,
            no_cache=no_cache,
            no_fail_on_empty=no_fail_on_empty,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=keeper_bin,
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    except CapabilityError as exc:
        click.echo(f"report error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    if payload.get("warning") == "cache_empty":
        click.echo(COMPLIANCE_CACHE_EMPTY_WARNING, err=True)
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


@report_cli.command("vault-health")
@click.option(
    "--shared-threshold",
    "--shared-user-threshold",
    "shared_threshold",
    type=click.IntRange(min=0),
    default=10,
    show_default=True,
    help="Flag records shared to more than this many users",
)
@click.option(
    "--stale-days",
    type=click.IntRange(min=1),
    default=90,
    show_default=True,
    help="Flag records not modified for more than this many days",
)
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
def report_vault_health(
    shared_threshold: int,
    stale_days: int,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Vault posture findings from Commander ``list-records`` metadata."""
    from keeper_sdk.cli._report.vault_health import run_vault_health_report

    try:
        payload = run_vault_health_report(
            shared_threshold=shared_threshold,
            stale_days=stale_days,
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


@report_cli.command("team-report")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint team_uid values instead of printing raw UIDs",
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
def report_team_report(quiet: bool, sanitize_uids: bool, keeper_bin: str | None) -> None:
    """Enterprise team rows from ``keeper enterprise-info``."""
    from keeper_sdk.cli._report.team_roles import run_team_report

    try:
        payload = run_team_report(
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


@report_cli.command("team-roles")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON (default; kept for compatibility)")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint team_uid values instead of printing raw UIDs",
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
def report_team_roles(
    as_json: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """Enterprise team/role relationship rows from ``keeper enterprise-info``."""
    from keeper_sdk.cli._report.team_roles import run_team_roles_report

    try:
        payload = run_team_roles_report(
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


@report_cli.command("ksm-usage")
@click.option("--json", "as_json", is_flag=True, help="Emit KSM usage as JSON")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint app_uid values in JSON output; suppress table when --json is set",
)
@click.option(
    "--sanitize-uids",
    is_flag=True,
    help="Fingerprint UID-like substrings in output",
)
@click.option(
    "--keeper-bin",
    default=None,
    envvar="KEEPER_BIN",
    help="Path to keeper CLI (default: keeper on PATH)",
)
@click.pass_context
def report_ksm_usage(
    ctx: click.Context,
    as_json: bool,
    quiet: bool,
    sanitize_uids: bool,
    keeper_bin: str | None,
) -> None:
    """KSM app/share usage summary."""
    from keeper_sdk.cli._report.ksm_usage import (
        render_ksm_usage_table,
        run_ksm_usage_report,
    )

    try:
        if ctx.obj.get("provider") == "mock":
            provider = ctx.obj.get("_ksm_report_provider_instance")
            if provider is None:
                provider = KsmMockProvider("ksm-usage")
                ctx.obj["_ksm_report_provider_instance"] = provider
            payload = run_ksm_usage_report(
                provider=provider, sanitize_uids=sanitize_uids, quiet=quiet
            )
        elif ctx.obj.get("provider") == "commander":
            payload = run_ksm_usage_report(
                sanitize_uids=sanitize_uids,
                quiet=quiet,
                keeper_bin=keeper_bin,
                config_file=os.environ.get("KEEPER_CONFIG"),
                password=os.environ.get("KEEPER_PASSWORD"),
            )
        else:
            raise CapabilityError(
                reason="dsk report ksm-usage supports --provider mock or --provider commander",
                next_action="rerun with --provider mock for offline coverage",
            )
    except CapabilityError as exc:
        click.echo(f"report error: {exc}", err=True)
        sys.exit(EXIT_CAPABILITY)
    except Exception as exc:
        source = "Commander" if ctx.obj.get("provider") == "commander" else "KSM usage"
        click.echo(f"report error: unexpected {source} error: {exc}", err=True)
        sys.exit(EXIT_GENERIC)

    if as_json:
        _emit_report_json(payload)
    if not quiet:
        click.echo(render_ksm_usage_table(payload))
    sys.exit(EXIT_OK)


@report_cli.command("role-report")
@click.option(
    "--quiet",
    is_flag=True,
    help="Fingerprint role_id values when Commander emits string IDs",
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
def report_role_report(quiet: bool, sanitize_uids: bool, keeper_bin: str | None) -> None:
    """Enterprise role rows from ``keeper enterprise-info``."""
    from keeper_sdk.cli._report.team_roles import run_role_report

    try:
        payload = run_role_report(
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
        empty.write_text('version: "1"\nname: _smoke_placeholder\nschema: pam-environment.v1\n')

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
