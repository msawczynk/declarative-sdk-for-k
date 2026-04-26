"""Keeper PAM Declarative — pure shared core.

Zero I/O. No subprocess. No Commander. Safe to import from any caller
(CLI, Commander adapter, tests, Terraform provider, etc.).

Stable public surface:
    - load_manifest, load_declarative_manifest, dump_manifest (core.manifest)
    - validate_manifest (core.schema)
    - Manifest models (core.models)
    - VaultManifestV1, load_vault_manifest (core.vault_models) — keeper-vault.v1 slice 1
    - build_vault_graph, vault_record_apply_order (core.vault_graph) — vault PR-V2
    - compute_vault_diff (core.vault_diff) — vault PR-V3
    - build_graph, execution_order (core.graph)
    - compute_diff, Change (core.diff)
    - build_plan, Plan (core.planner)
    - Provider, MetadataStore, Renderer (core.interfaces)
    - ManifestError taxonomy (core.errors)
    - encode_marker, decode_marker, MARKER_FIELD_LABEL (core.metadata)
    - redact (core.redact)
    - to_pam_import_json, from_pam_import_json (core.normalize)
"""

from keeper_sdk.core.diff import Change, ChangeKind, compute_diff
from keeper_sdk.core.errors import (
    CapabilityError,
    CollisionError,
    DeleteUnsupportedError,
    ManifestError,
    OwnershipError,
    RefError,
    SchemaError,
)
from keeper_sdk.core.graph import build_graph, execution_order
from keeper_sdk.core.interfaces import MetadataStore, Provider, Renderer
from keeper_sdk.core.manifest import (
    dump_manifest,
    load_declarative_manifest,
    load_manifest,
    read_manifest_document,
)
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, decode_marker, encode_marker
from keeper_sdk.core.models import (
    Gateway,
    LoginRecord,
    Manifest,
    PamConfiguration,
    PamDatabase,
    PamDirectory,
    PamMachine,
    PamRemoteBrowser,
    PamUser,
    Project,
    SharedFolderBlock,
    SharedFoldersBlock,
)
from keeper_sdk.core.normalize import from_pam_import_json, to_pam_import_json
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.core.redact import redact
from keeper_sdk.core.schema import (
    PAM_FAMILY,
    load_schema,
    load_schema_for_family,
    packaged_schema_families,
    resolve_manifest_family,
    validate_manifest,
)
from keeper_sdk.core.vault_diff import compute_vault_diff
from keeper_sdk.core.vault_graph import build_vault_graph, vault_record_apply_order
from keeper_sdk.core.vault_models import (
    VAULT_FAMILY as VAULT_MANIFEST_FAMILY,
)
from keeper_sdk.core.vault_models import (
    VaultManifestV1,
    VaultRecord,
    load_vault_manifest,
)

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
    "load_declarative_manifest",
    "dump_manifest",
    "read_manifest_document",
    "PAM_FAMILY",
    "load_schema",
    "load_schema_for_family",
    "packaged_schema_families",
    "resolve_manifest_family",
    "validate_manifest",
    "build_graph",
    "execution_order",
    "Change",
    "ChangeKind",
    "compute_diff",
    "compute_vault_diff",
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
    "VaultManifestV1",
    "VaultRecord",
    "load_vault_manifest",
    "VAULT_MANIFEST_FAMILY",
    "build_vault_graph",
    "vault_record_apply_order",
]
