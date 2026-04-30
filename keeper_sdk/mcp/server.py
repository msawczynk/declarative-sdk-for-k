"""DSK MCP server over stdio JSON-RPC."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin

import yaml

from keeper_sdk import __version__
from keeper_sdk.cli import main as cli_main
from keeper_sdk.cli.main import (
    _build_sharing_changes,
    _emit_report_json,
    _plan_to_dict,
    _vault_live_inputs,
)
from keeper_sdk.cli.renderer import RichRenderer
from keeper_sdk.core import (
    IDENTITY_FAMILY,
    CapabilityError,
    IdentityManifestV1,
    Manifest,
    MspManifestV1,
    OwnershipError,
    build_graph,
    build_plan,
    build_vault_graph,
    compute_diff,
    compute_identity_diff,
    compute_msp_diff,
    compute_vault_diff,
    dump_manifest,
    execution_order,
    from_pam_import_json,
    load_declarative_manifest,
    msp_apply_order,
    redact,
    sharing_apply_order,
    vault_record_apply_order,
)
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord
from keeper_sdk.core.manifest import load_manifest_string

try:
    from keeper_sdk.core.models_ai_agent import (  # stripped in public build
        AI_AGENT_FAMILY,
        AiAgentManifest,
    )
except ImportError:
    AI_AGENT_FAMILY = "ai-agent.v1"  # type: ignore[assignment]

    class AiAgentManifest:  # type: ignore[no-redef]  # stripped in public build
        """Stub for stripped private module."""


from keeper_sdk.core.models_integrations_events import EVENTS_FAMILY, EventsManifestV1
from keeper_sdk.core.models_ksm import KSM_FAMILY, KsmManifestV1

try:
    from keeper_sdk.core.models_nhi import NHI_FAMILY, NhiAgentManifest  # stripped in public build
except ImportError:
    NHI_FAMILY = "nhi-agent.v1"  # type: ignore[assignment]

    class NhiAgentManifest:  # type: ignore[no-redef]  # stripped in public build
        """Stub for stripped private module."""


try:
    from keeper_sdk.core.models_pam_extended import (  # stripped in public build
        PAM_EXTENDED_FAMILY,
        PamExtendedManifestV1,
    )
except ImportError:
    PAM_EXTENDED_FAMILY = "keeper-pam-extended.v1"  # type: ignore[assignment]

    class PamExtendedManifestV1:  # type: ignore[no-redef]  # stripped in public build
        """Stub for stripped private module."""


try:
    from keeper_sdk.core.pam_extended_diff import (
        compute_pam_extended_diff,  # stripped in public build
    )
except ImportError:
    compute_pam_extended_diff = None  # type: ignore[assignment]
from keeper_sdk.core.planner import Plan
from keeper_sdk.core.sharing_models import SharingManifestV1
from keeper_sdk.core.vault_models import VaultManifestV1
from keeper_sdk.mcp.manifest_helper import (
    capture_dsk_output,
    json_to_tempfile,
    remove_tempfile,
    yaml_to_tempfile,
)
from keeper_sdk.providers import MockProvider
from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import KsmBus

ToolHandler = Callable[..., Awaitable[str]]
CommanderServiceProvider: type[Any] | None = None

_MOCK_PROVIDERS: dict[str, MockProvider] = {}
_SERVER_NAME = "dsk-mcp"
_PROTOCOL_VERSION = "2024-11-05"
_SERVICE_URL_ENV = "KEEPER_SERVICE_URL"
_SERVICE_API_KEY_ENV = "KEEPER_SERVICE_API_KEY"


@dataclass
class PlanBundle:
    manifest_name: str
    order: list[str]
    provider: Any
    pam: Manifest | None = None
    vault: VaultManifestV1 | None = None
    sharing: SharingManifestV1 | None = None
    msp: MspManifestV1 | None = None
    identity: IdentityManifestV1 | None = None
    pam_extended: PamExtendedManifestV1 | None = None
    events: EventsManifestV1 | None = None
    nhi: NhiAgentManifest | None = None
    ai_agent: AiAgentManifest | None = None
    live: list[LiveRecord] | None = None
    live_msp: list[dict[str, Any]] | None = None
    live_record_type_defs: list[dict[str, Any]] | None = None


class JsonRpcMcpServer:
    """Tiny MCP-compatible JSON-RPC server for stdio clients."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._tools: dict[str, ToolHandler] = {}

    def tool(self, name: str) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(fn: ToolHandler) -> ToolHandler:
            self._tools[name] = fn
            return fn

        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        return [_tool_schema(name, fn) for name, fn in sorted(self._tools.items())]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        try:
            text = await self._tools[name](**(arguments or {}))
            return {"content": [{"type": "text", "text": str(text)}], "isError": False}
        except Exception as exc:
            return {"content": [{"type": "text", "text": str(redact(str(exc)))}], "isError": True}

    async def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in request:
            return None
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        try:
            result: dict[str, Any]
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion") or _PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": __version__},
                }
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                result = await self.call_tool(str(params["name"]), params.get("arguments") or {})
            elif method in {"ping", "health"}:
                result = {}
            else:
                return _rpc_error(req_id, -32601, f"method not found: {method}")
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except KeyError as exc:
            return _rpc_error(req_id, -32602, str(exc))
        except Exception as exc:
            return _rpc_error(req_id, -32603, str(redact(str(exc))))

    async def run_stdio(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if line == "":
                break
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = await self.handle(request)
            except json.JSONDecodeError as exc:
                response = _rpc_error(None, -32700, f"parse error: {exc}")
            if response is None:
                continue
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


server = JsonRpcMcpServer(_SERVER_NAME)


@server.tool("dsk_validate")
async def validate(manifest_yaml: str) -> str:
    """Validate a DSK manifest YAML string against packaged schemas.

    Includes nhi-agent.v1 and ai-agent.v1.
    """
    path = yaml_to_tempfile(manifest_yaml)
    try:
        output = capture_dsk_output(
            cli_main.main,
            args=["validate", str(path)],
            prog_name="dsk",
            standalone_mode=False,
        )
    finally:
        remove_tempfile(path)
    return "ok" if output.startswith("ok:") else output


@server.tool("dsk_plan")
async def plan(manifest_yaml: str, allow_delete: bool = False) -> str:
    """Compute plan for a manifest. Returns JSON plan (changes, summary, conflicts)."""
    path = yaml_to_tempfile(manifest_yaml)
    try:
        plan_obj, _bundle = _build_mcp_plan(path, allow_delete=allow_delete)
        return _redacted_json(_plan_to_dict(plan_obj))
    finally:
        remove_tempfile(path)


@server.tool("dsk_apply")
async def apply(manifest_yaml: str, auto_approve: bool = True, dry_run: bool = False) -> str:
    """Apply a manifest. Returns outcomes JSON. Requires explicit auto_approve=True."""
    if auto_approve is not True:
        raise ValueError("dsk_apply requires auto_approve=True")
    path = yaml_to_tempfile(manifest_yaml)
    try:
        plan_obj, bundle = _build_mcp_plan(path, allow_delete=False)
        if plan_obj.conflicts:
            return _redacted_json({"error": "plan has conflicts", "plan": _plan_to_dict(plan_obj)})
        if plan_obj.is_clean:
            return _redacted_json({"summary": _plan_to_dict(plan_obj)["summary"], "outcomes": []})
        if bundle.msp is not None:
            outcomes = bundle.provider.apply_msp_plan(plan_obj, dry_run=dry_run)
        else:
            outcomes = bundle.provider.apply_plan(plan_obj, dry_run=dry_run)
        return _redacted_json(
            {
                "summary": _plan_to_dict(plan_obj)["summary"],
                "dry_run": dry_run,
                "outcomes": [_outcome_to_dict(outcome) for outcome in outcomes],
            }
        )
    finally:
        remove_tempfile(path)


@server.tool("dsk_diff")
async def diff(manifest_yaml: str) -> str:
    """Field-level diff between manifest and live tenant."""
    path = yaml_to_tempfile(manifest_yaml)
    try:
        plan_obj, _bundle = _build_mcp_plan(path, allow_delete=False)
        return str(redact(RichRenderer().render_diff(plan_obj)))
    finally:
        remove_tempfile(path)


@server.tool("dsk_export")
async def export(project_json: str) -> str:
    """Convert pam project export JSON to a DSK manifest YAML string."""
    path = json_to_tempfile(project_json)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest_dict = redact(from_pam_import_json(data, name=path.stem))
        manifest = load_manifest_string(json.dumps(manifest_dict), suffix=".json")
        return dump_manifest(manifest, fmt="yaml")
    finally:
        remove_tempfile(path)


@server.tool("dsk_report")
async def report(report_type: str, sanitize_uids: bool = True) -> str:
    """Run a DSK report. report_type: password-report|compliance-report|security-audit-report."""
    allowed = {"password-report", "compliance-report", "security-audit-report"}
    if report_type not in allowed:
        raise ValueError(f"unsupported report_type: {report_type}")
    args = [report_type, "--quiet"]
    if sanitize_uids:
        args.append("--sanitize-uids")
    return _redact_structured_text(capture_dsk_output(_invoke_report_cli, args))


@server.tool("dsk_bus_publish")
async def bus_publish(channel: str, payload: dict[str, Any], record_uid: str) -> str:
    """Publish a message to the KSM inter-agent bus channel."""
    version = KsmBus(KsmSecretStore(), record_uid).publish(channel, payload)
    return _redacted_json({"channel": channel, "version": version})


@server.tool("dsk_bus_get")
async def bus_get(channel: str, record_uid: str) -> str:
    """Get latest message from a KSM bus channel."""
    value = KsmBus(KsmSecretStore(), record_uid).get(channel)
    if value is None:
        return _redacted_json({"channel": channel, "value": None, "version": 0})
    return _redacted_json({"channel": channel, "value": value.value, "version": value.version})


def main() -> None:
    """Run the stdio MCP server."""
    asyncio.run(server.run_stdio())


def _invoke_report_cli(args: list[str]) -> None:
    command = args[0]
    sanitize_uids = "--sanitize-uids" in args
    quiet = "--quiet" in args
    if command == "password-report":
        from keeper_sdk.cli._report.password import run_password_report

        payload = run_password_report(
            policy="12,2,2,2,0",
            folder=None,
            verbose=False,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=os.environ.get("KEEPER_BIN"),
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    elif command == "compliance-report":
        from keeper_sdk.cli._report.compliance import run_compliance_report

        payload = run_compliance_report(
            node=None,
            username=(),
            team=(),
            rebuild=False,
            no_cache=False,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=os.environ.get("KEEPER_BIN"),
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    elif command == "security-audit-report":
        from keeper_sdk.cli._report.security_audit import run_security_audit_report

        payload = run_security_audit_report(
            nodes=(),
            record_details=False,
            breachwatch=False,
            score_type="default",
            force=True,
            quiet=quiet,
            sanitize_uids=sanitize_uids,
            keeper_bin=os.environ.get("KEEPER_BIN"),
            config_file=os.environ.get("KEEPER_CONFIG"),
            password=os.environ.get("KEEPER_PASSWORD"),
        )
    else:
        raise ValueError(f"unsupported report_type: {command}")
    _emit_report_json(payload)


def _build_mcp_plan(path: Path, *, allow_delete: bool) -> tuple[Plan, PlanBundle]:
    bundle = _load_mcp_bundle(path)
    capability_subject: object
    try:
        if bundle.pam is not None:
            changes = compute_diff(
                bundle.pam,
                bundle.live or [],
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.pam
        elif bundle.vault is not None:
            changes = compute_vault_diff(
                bundle.vault,
                bundle.live or [],
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
                live_record_type_defs=bundle.live_record_type_defs or [],
            )
            capability_subject = bundle.vault
        elif bundle.msp is not None:
            changes = compute_msp_diff(bundle.msp, bundle.live_msp or [], allow_delete=allow_delete)
            capability_subject = bundle.msp
        elif bundle.sharing is not None:
            changes = _build_sharing_changes(
                bundle.provider,
                bundle.sharing,
                allow_delete=allow_delete,
            )
            capability_subject = bundle.sharing
        elif bundle.identity is not None:
            compute_identity_diff(
                bundle.identity,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise _unsupported_plan_apply(IDENTITY_FAMILY, "upstream-gap")
        elif bundle.events is not None:
            raise _unsupported_plan_apply(EVENTS_FAMILY, "upstream-gap")
        elif bundle.nhi is not None:
            raise _unsupported_plan_apply(NHI_FAMILY, "upstream-gap; pending NHI PAM API GA")
        elif bundle.ai_agent is not None:
            raise _unsupported_plan_apply(AI_AGENT_FAMILY, "upstream-gap; pending NHI PAM API GA")
        elif bundle.pam_extended is not None:
            compute_pam_extended_diff(
                bundle.pam_extended,
                {},
                manifest_name=bundle.manifest_name,
                allow_delete=allow_delete,
            )
            raise _unsupported_plan_apply(PAM_EXTENDED_FAMILY, "preview-gated")
        else:
            raise CapabilityError(
                reason="plan is not supported for this manifest family",
                next_action="use dsk_validate for schema checks",
            )
    except OwnershipError as exc:
        raise CapabilityError(reason=f"ownership error: {exc}") from exc

    for reason in getattr(bundle.provider, "unsupported_capabilities", lambda _m: [])(
        capability_subject
    ):
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
    return build_plan(bundle.manifest_name, changes, bundle.order), bundle


def _load_mcp_bundle(path: Path) -> PlanBundle:
    typed = load_declarative_manifest(path)
    pam = typed if isinstance(typed, Manifest) else None
    vault = typed if isinstance(typed, VaultManifestV1) else None
    sharing = typed if isinstance(typed, SharingManifestV1) else None
    msp = typed if isinstance(typed, MspManifestV1) else None
    identity = typed if isinstance(typed, IdentityManifestV1) else None
    pam_extended = typed if isinstance(typed, PamExtendedManifestV1) else None
    events = typed if isinstance(typed, EventsManifestV1) else None
    nhi = typed if isinstance(typed, NhiAgentManifest) else None
    ai_agent = typed if isinstance(typed, AiAgentManifest) else None
    ksm = typed if isinstance(typed, KsmManifestV1) else None
    manifest_name = _manifest_name(path, pam, msp, identity, pam_extended, events, nhi, ai_agent)

    if pam is not None:
        order = execution_order(build_graph(pam))
    elif vault is not None:
        build_vault_graph(vault)
        order = vault_record_apply_order(vault)
    elif msp is not None:
        order = msp_apply_order(msp)
    elif sharing is not None:
        order = sharing_apply_order(sharing)
    elif identity is not None:
        raise _unsupported_plan_apply(IDENTITY_FAMILY, "upstream-gap")
    elif events is not None:
        raise _unsupported_plan_apply(EVENTS_FAMILY, "upstream-gap")
    elif nhi is not None:
        raise _unsupported_plan_apply(NHI_FAMILY, "upstream-gap; pending NHI PAM API GA")
    elif ai_agent is not None:
        raise _unsupported_plan_apply(AI_AGENT_FAMILY, "upstream-gap; pending NHI PAM API GA")
    elif pam_extended is not None:
        raise _unsupported_plan_apply(PAM_EXTENDED_FAMILY, "preview-gated")
    elif ksm is not None:
        raise CapabilityError(
            reason=f"typed plan/load supports {KSM_FAMILY} for offline validation only",
            next_action=f"use dsk_validate for {KSM_FAMILY} schema checks",
        )
    else:
        raise CapabilityError(
            reason="plan is not supported for this manifest family",
            next_action="use dsk_validate for schema checks",
        )

    provider = _make_mcp_provider(manifest_name, typed)
    live: list[LiveRecord] = []
    live_msp: list[dict[str, Any]] = []
    live_record_type_defs: list[dict[str, Any]] = []
    if msp is not None:
        live_msp = provider.discover_managed_companies()
    elif sharing is None:
        live = provider.discover()
        if vault is not None:
            live, live_record_type_defs = _vault_live_inputs(live)

    return PlanBundle(
        manifest_name=manifest_name,
        order=order,
        provider=provider,
        pam=pam,
        vault=vault,
        sharing=sharing,
        msp=msp,
        identity=identity,
        pam_extended=pam_extended,
        events=events,
        nhi=nhi,
        ai_agent=ai_agent,
        live=live,
        live_msp=live_msp,
        live_record_type_defs=live_record_type_defs,
    )


def _make_mcp_provider(manifest_name: str, manifest: object) -> Any:
    service_url = os.environ.get(_SERVICE_URL_ENV)
    api_key = os.environ.get(_SERVICE_API_KEY_ENV)
    if service_url and api_key:
        provider_cls = CommanderServiceProvider or _import_service_provider()
        manifest_source = {}
        if hasattr(manifest, "model_dump"):
            manifest_source = manifest.model_dump(mode="python", exclude_none=True, by_alias=True)
        return provider_cls(
            service_url=service_url,
            api_key=api_key,
            manifest_source=manifest_source,
        )
    return _MOCK_PROVIDERS.setdefault(manifest_name, MockProvider(manifest_name))


def _import_service_provider() -> type[Any]:
    try:
        from keeper_sdk.providers.commander_service import CommanderServiceProvider as cls
    except ImportError as exc:
        raise CapabilityError(
            reason="CommanderServiceProvider is unavailable in this SDK build",
            next_action=(
                "unset KEEPER_SERVICE_URL/KEEPER_SERVICE_API_KEY for mock offline mode, "
                "or install the Commander service provider extension"
            ),
        ) from exc
    return cls


def _manifest_name(
    path: Path,
    pam: Manifest | None,
    msp: MspManifestV1 | None,
    identity: IdentityManifestV1 | None,
    pam_extended: PamExtendedManifestV1 | None,
    events: EventsManifestV1 | None,
    nhi: NhiAgentManifest | None,
    ai_agent: AiAgentManifest | None,
) -> str:
    if pam is not None:
        return pam.name
    if msp is not None:
        return msp.name
    if identity is not None:
        return IDENTITY_FAMILY
    if events is not None:
        return events.name
    if nhi is not None:
        return NHI_FAMILY
    if ai_agent is not None:
        return AI_AGENT_FAMILY
    if pam_extended is not None:
        return PAM_EXTENDED_FAMILY
    return path.stem


def _unsupported_plan_apply(family: str, status: str) -> CapabilityError:
    return CapabilityError(
        reason=f"{family} plan/apply is not supported ({status}; no live provider proof)",
        next_action="use dsk_validate for schema checks",
    )


def _outcome_to_dict(outcome: ApplyOutcome) -> dict[str, Any]:
    return asdict(outcome)


def _redacted_json(value: Any) -> str:
    return json.dumps(redact(value), indent=2, sort_keys=True)


def _redact_structured_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return _redacted_json(json.loads(stripped))
    except json.JSONDecodeError:
        pass
    try:
        loaded = yaml.safe_load(stripped)
    except yaml.YAMLError:
        return str(redact(text)).strip()
    if isinstance(loaded, (dict, list)):
        return yaml.safe_dump(redact(loaded), sort_keys=False)
    return str(redact(text)).strip()


def _tool_schema(name: str, fn: ToolHandler) -> dict[str, Any]:
    signature = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in signature.parameters.items():
        properties[param_name] = _json_schema_for_annotation(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {
        "name": name,
        "description": inspect.getdoc(fn) or "",
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def _json_schema_for_annotation(annotation: Any) -> dict[str, Any]:
    if isinstance(annotation, str):
        lowered = annotation.lower()
        if "bool" in lowered:
            return {"type": "boolean"}
        if "dict" in lowered:
            return {"type": "object"}
        if "list" in lowered:
            return {"type": "array"}
        if "int" in lowered:
            return {"type": "integer"}
        if "float" in lowered:
            return {"type": "number"}
        return {"type": "string"}
    origin = get_origin(annotation)
    if origin in (UnionType, getattr(__import__("typing"), "Union")):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        return _json_schema_for_annotation(args[0]) if args else {"type": "string"}
    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is dict or origin is dict:
        return {"type": "object"}
    if annotation is list or origin is list:
        return {"type": "array"}
    return {"type": "string"}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


__all__ = [
    "apply",
    "bus_get",
    "bus_publish",
    "diff",
    "export",
    "main",
    "plan",
    "report",
    "server",
    "validate",
]
