"""Keeper PAM Declarative — pure shared core.

Zero I/O. No subprocess. No Commander. Safe to import from any caller
(CLI, Commander adapter, tests, Terraform provider, etc.).

Stable public surface:
    - load_manifest, dump_manifest (core.manifest)
    - validate_manifest (core.schema)
    - Manifest models (core.models)
    - build_graph, execution_order (core.graph)
    - compute_diff, Change (core.diff)
    - build_plan, Plan (core.planner)
    - Provider, MetadataStore, Renderer (core.interfaces)
    - ManifestError taxonomy (core.errors)
    - encode_marker, decode_marker, MARKER_FIELD_LABEL (core.metadata)
    - redact (core.redact)
    - to_pam_import_json, from_pam_import_json (core.normalize)
"""

from keeper_sdk.core.errors import (
    CapabilityError,
    CollisionError,
    DeleteUnsupportedError,
    ManifestError,
    OwnershipError,
    RefError,
    SchemaError,
)
from keeper_sdk.core.manifest import dump_manifest, load_manifest
from keeper_sdk.core.schema import load_schema, validate_manifest
from keeper_sdk.core.models import (
    Gateway,
    Manifest,
    PamConfiguration,
    PamDatabase,
    PamDirectory,
    PamMachine,
    PamRemoteBrowser,
    PamUser,
    LoginRecord,
    Project,
    SharedFolderBlock,
    SharedFoldersBlock,
)
from keeper_sdk.core.graph import build_graph, execution_order
from keeper_sdk.core.diff import Change, ChangeKind, compute_diff
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.core.interfaces import MetadataStore, Provider, Renderer
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker, encode_marker
from keeper_sdk.core.redact import redact
from keeper_sdk.core.normalize import from_pam_import_json, to_pam_import_json

__all__ = [
    "CapabilityError",
    "CollisionError",
    "DeleteUnsupportedError",
    "ManifestError",
    "OwnershipError",
    "RefError",
    "SchemaError",
    "Manifest",
    "Gateway",
    "PamConfiguration",
    "PamDatabase",
    "PamDirectory",
    "PamMachine",
    "PamRemoteBrowser",
    "PamUser",
    "LoginRecord",
    "Project",
    "SharedFolderBlock",
    "SharedFoldersBlock",
    "load_manifest",
    "dump_manifest",
    "load_schema",
    "validate_manifest",
    "build_graph",
    "execution_order",
    "Change",
    "ChangeKind",
    "compute_diff",
    "Plan",
    "build_plan",
    "Provider",
    "MetadataStore",
    "Renderer",
    "MARKER_FIELD_LABEL",
    "encode_marker",
    "decode_marker",
    "redact",
    "from_pam_import_json",
    "to_pam_import_json",
]
