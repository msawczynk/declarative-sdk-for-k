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
    - SharingManifestV1, load_sharing_manifest (core.sharing_models) — sharing typed slice
    - build_sharing_graph, sharing_apply_order (core.sharing_graph) — sharing dependency graph
    - compute_sharing_diff (core.sharing_diff) — sharing folders diff slice
    - MspManifestV1, load_msp_manifest (core.msp_models) — MSP slice 1
    - build_msp_graph, msp_apply_order (core.msp_graph) — MSP slice 1
    - compute_msp_diff (core.msp_diff) — MSP slice 1
    - IdentityManifestV1, load_identity_manifest, compute_identity_diff
      (core.models_integrations_identity / core.integrations_identity_diff) — W14 offline
    - PamExtendedManifestV1, load_pam_extended_manifest, compute_pam_extended_diff
      (core.models_pam_extended / core.pam_extended_diff) — W17 offline
    - TerraformIntegrationManifestV1, load_terraform_manifest
      (core.models_terraform) — Terraform integration boundary metadata
    - K8sEsoManifestV1, load_k8s_eso_manifest
      (core.models_k8s_eso) — Kubernetes ESO integration boundary metadata
    - SiemManifestV1, load_siem_manifest, compute_siem_diff
      (core.models_siem / core.siem_diff) — SIEM event streaming metadata
    - Workflow / privileged-access / tunnel / SaaS rotation typed scaffolds
      (core.models_workflow, core.models_privileged_access, core.models_tunnel,
      core.models_saas_rotation) — Commander 17.2.16 public-eligible families
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
    UnsupportedFamilyError,
)
from keeper_sdk.core.graph import build_graph, execution_order
from keeper_sdk.core.integrations_identity_diff import compute_identity_diff
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
from keeper_sdk.core.models_integrations_identity import (
    IDENTITY_FAMILY,
    IdentityDomain,
    IdentityManifestV1,
    IdentityOutboundEmail,
    IdentityScimProvisioning,
    IdentitySsoProvider,
    load_identity_manifest,
)
from keeper_sdk.core.models_k8s_eso import (
    K8S_ESO_FAMILY,
    EsoStore,
    ExternalSecret,
    ExternalSecretData,
    K8sEsoManifestV1,
    load_k8s_eso_manifest,
)

try:
    from keeper_sdk.core.models_pam_extended import (  # stripped in public build
        PAM_EXTENDED_FAMILY,
        PamExtendedDiscoveryRule,
        PamExtendedGatewayConfig,
        PamExtendedManifest,
        PamExtendedManifestV1,
        PamExtendedResource,
        PamExtendedRotationSchedule,
        PamExtendedServiceMapping,
        load_pam_extended_manifest,
    )
except ImportError:
    pass
from keeper_sdk.core.models_privileged_access import (
    PRIVILEGED_ACCESS_FAMILY,
    PrivilegedAccessManifestV1,
    PrivilegedGroup,
    PrivilegedGroupMembership,
    PrivilegedUser,
    load_privileged_access_manifest,
)
from keeper_sdk.core.models_saas_rotation import (
    SAAS_ROTATION_FAMILY,
    SaaSRotationBinding,
    SaaSRotationConfig,
    SaaSRotationManifestV1,
    load_saas_rotation_manifest,
)
from keeper_sdk.core.models_siem import (
    SIEM_FAMILY,
    SiemFilter,
    SiemManifestV1,
    SiemRoute,
    SiemSink,
    load_siem_manifest,
)
from keeper_sdk.core.models_terraform import (
    TERRAFORM_FAMILY,
    TerraformIntegrationManifestV1,
    TerraformResourceMapping,
    load_terraform_manifest,
)
from keeper_sdk.core.models_tunnel import (
    TUNNEL_FAMILY,
    TunnelConfig,
    TunnelGatewayBinding,
    TunnelHostMapping,
    TunnelManifestV1,
    load_tunnel_manifest,
)
from keeper_sdk.core.models_workflow import (
    WORKFLOW_FAMILY,
    WorkflowApprover,
    WorkflowConfig,
    WorkflowManifestV1,
    WorkflowRequest,
    WorkflowState,
    load_workflow_manifest,
)
from keeper_sdk.core.msp_diff import compute_msp_diff
from keeper_sdk.core.msp_graph import build_msp_graph, msp_apply_order
from keeper_sdk.core.msp_models import (
    MSP_FAMILY,
    Addon,
    ManagedCompany,
    MspManifestV1,
    load_msp_manifest,
)
from keeper_sdk.core.normalize import from_pam_import_json, to_pam_import_json

try:
    from keeper_sdk.core.pam_extended_diff import (
        compute_pam_extended_diff,  # stripped in public build
    )
except ImportError:
    compute_pam_extended_diff = None  # type: ignore[assignment]
from keeper_sdk.core.planner import Plan, build_plan
from keeper_sdk.core.redact import redact
from keeper_sdk.core.schema import (
    PAM_FAMILY,
    SHARING_FAMILY,
    load_schema,
    load_schema_for_family,
    packaged_schema_families,
    resolve_manifest_family,
    validate_manifest,
)
from keeper_sdk.core.sharing_diff import compute_sharing_diff
from keeper_sdk.core.sharing_graph import build_sharing_graph, sharing_apply_order
from keeper_sdk.core.sharing_models import SHARING_FAMILY as SHARING_MANIFEST_FAMILY
from keeper_sdk.core.sharing_models import (
    FolderGranteePermissions,
    Grantee,
    RecordPermissions,
    SharingFolder,
    SharingManifestV1,
    SharingRecordShare,
    SharingSharedFolder,
    SharingShareFolder,
    load_sharing_manifest,
)
from keeper_sdk.core.siem_diff import compute_siem_diff
from keeper_sdk.core.vault_diff import compute_vault_diff
from keeper_sdk.core.vault_graph import build_vault_graph, vault_record_apply_order
from keeper_sdk.core.vault_models import VAULT_FAMILY as VAULT_MANIFEST_FAMILY
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
    "UnsupportedFamilyError",
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
    "MSP_FAMILY",
    "IDENTITY_FAMILY",
    "PAM_EXTENDED_FAMILY",
    "TERRAFORM_FAMILY",
    "K8S_ESO_FAMILY",
    "SIEM_FAMILY",
    "WORKFLOW_FAMILY",
    "PRIVILEGED_ACCESS_FAMILY",
    "TUNNEL_FAMILY",
    "SAAS_ROTATION_FAMILY",
    "MspManifestV1",
    "IdentityDomain",
    "IdentityManifestV1",
    "IdentityOutboundEmail",
    "IdentityScimProvisioning",
    "IdentitySsoProvider",
    "PamExtendedDiscoveryRule",
    "PamExtendedGatewayConfig",
    "PamExtendedManifest",
    "PamExtendedManifestV1",
    "PamExtendedResource",
    "TerraformIntegrationManifestV1",
    "TerraformResourceMapping",
    "K8sEsoManifestV1",
    "SiemFilter",
    "SiemManifestV1",
    "SiemRoute",
    "SiemSink",
    "WorkflowApprover",
    "WorkflowConfig",
    "WorkflowManifestV1",
    "WorkflowRequest",
    "WorkflowState",
    "PrivilegedAccessManifestV1",
    "PrivilegedGroup",
    "PrivilegedGroupMembership",
    "PrivilegedUser",
    "TunnelConfig",
    "TunnelGatewayBinding",
    "TunnelHostMapping",
    "TunnelManifestV1",
    "SaaSRotationBinding",
    "SaaSRotationConfig",
    "SaaSRotationManifestV1",
    "EsoStore",
    "ExternalSecret",
    "ExternalSecretData",
    "PamExtendedRotationSchedule",
    "PamExtendedServiceMapping",
    "ManagedCompany",
    "Addon",
    "load_identity_manifest",
    "load_pam_extended_manifest",
    "load_terraform_manifest",
    "load_k8s_eso_manifest",
    "load_siem_manifest",
    "load_workflow_manifest",
    "load_privileged_access_manifest",
    "load_tunnel_manifest",
    "load_saas_rotation_manifest",
    "load_msp_manifest",
    "load_manifest",
    "load_declarative_manifest",
    "dump_manifest",
    "read_manifest_document",
    "PAM_FAMILY",
    "SHARING_FAMILY",
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
    "compute_msp_diff",
    "compute_identity_diff",
    "compute_pam_extended_diff",
    "compute_vault_diff",
    "build_sharing_graph",
    "sharing_apply_order",
    "compute_sharing_diff",
    "compute_siem_diff",
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
    "build_msp_graph",
    "msp_apply_order",
    "SharingManifestV1",
    "SharingFolder",
    "SharingSharedFolder",
    "SharingRecordShare",
    "SharingShareFolder",
    "Grantee",
    "RecordPermissions",
    "FolderGranteePermissions",
    "load_sharing_manifest",
    "SHARING_MANIFEST_FAMILY",
]
