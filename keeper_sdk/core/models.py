"""Typed models for the Keeper PAM declarative manifest v1.

Mirrors manifests/pam-environment.v1.schema.json from the keeper-pam-declarative
package. Canonical field names match Commander's pam_import README so the
model is a superset-compatible wrapper that round-trips without renames.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

OnOff = Literal["on", "off"]
Environment = Literal["local", "aws", "azure", "domain", "gcp", "oci"]
ResourceKind = Literal["pamMachine", "pamDatabase", "pamDirectory", "pamRemoteBrowser"]
UserKind = Literal["pamUser", "login"]
SharedFolderSection = Literal["users", "resources"]
RotationMode = Literal["general", "iam_user", "scripts_only"]


class _Model(BaseModel):
    """Shared model config. Permissive so unknown canonical fields survive."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, str_strip_whitespace=True)


# ----------------------------------------------------------------------------
# leaf blocks


class RotationScheduleOnDemand(_Model):
    type: Literal["on-demand"]


class RotationScheduleCron(_Model):
    type: Literal["CRON"]
    cron: str


RotationSchedule = Union[RotationScheduleOnDemand, RotationScheduleCron]


class RotationSettings(_Model):
    rotation: RotationMode
    enabled: OnOff = "on"
    schedule: RotationSchedule | None = None
    password_complexity: str | None = None


class Script(_Model):
    file: str
    script_command: str | None = None
    additional_credentials_uid_refs: list[str] = Field(default_factory=list)


class SftpBlock(_Model):
    enable_sftp: bool | None = None
    sftp_resource_uid_ref: str | None = None
    sftp_user_credentials_uid_ref: str | None = None
    sftp_root_directory: str | None = None
    sftp_upload_directory: str | None = None
    sftp_keepalive_interval: int | None = None


class PortForward(_Model):
    port: str | int | None = None
    reuse_port: bool | None = None


class JitSettings(_Model):
    create_ephemeral: bool | None = None
    elevate: bool | None = None
    elevation_method: Literal["group", "role"] | None = None
    elevation_string: str | None = None
    base_distinguished_name: str | None = None
    ephemeral_account_type: Literal["linux", "mac", "windows", "domain"] | None = None
    pam_directory_uid_ref: str | None = None


class AiSettings(_Model):
    risk_levels: dict[str, Any] | None = None


# ----------------------------------------------------------------------------
# options


class CommonOptions(_Model):
    connections: OnOff | None = None
    rotation: OnOff | None = None
    tunneling: OnOff | None = None
    remote_browser_isolation: OnOff | None = None
    graphical_session_recording: OnOff | None = None
    text_session_recording: OnOff | None = None
    ai_threat_detection: OnOff | None = None
    ai_terminate_session_on_detection: OnOff | None = None


class ResourceOptions(CommonOptions):
    jit_settings: JitSettings | None = None
    ai_settings: AiSettings | None = None


class RbiOptions(_Model):
    remote_browser_isolation: OnOff | None = None
    graphical_session_recording: OnOff | None = None


# ----------------------------------------------------------------------------
# connection blocks


class ConnectionBase(_Model):
    protocol: str | None = None
    port: str | int | None = None
    allow_supply_user: bool | None = None
    administrative_credentials_uid_ref: str | None = None
    launch_credentials_uid_ref: str | None = None
    autofill_credentials_uid_ref: str | None = None
    recording_include_keys: bool | None = None
    disable_copy: bool | None = None
    disable_paste: bool | None = None
    sftp: SftpBlock | None = None


class RbiConnection(_Model):
    protocol: Literal["http"] = "http"
    autofill_credentials_uid_ref: str | None = None
    autofill_targets: str | None = None
    allow_url_manipulation: bool | None = None
    allowed_url_patterns: str | None = None
    allowed_resource_url_patterns: str | None = None
    recording_include_keys: bool | None = None
    disable_copy: bool | None = None
    disable_paste: bool | None = None
    ignore_server_cert: bool | None = None


class PamSettings(_Model):
    options: ResourceOptions | None = None
    allow_supply_host: bool | None = None
    port_forward: PortForward | None = None
    connection: ConnectionBase | None = None


class RbiPamSettings(_Model):
    options: RbiOptions | None = None
    connection: RbiConnection | None = None


# ----------------------------------------------------------------------------
# shared folders


class SharedFolderPermission(_Model):
    name: str
    manage_users: bool | None = None
    manage_records: bool | None = None
    can_edit: bool | None = None
    can_share: bool | None = None


class SharedFolderBlock(_Model):
    uid_ref: str | None = None
    manage_users: bool | None = None
    manage_records: bool | None = None
    can_edit: bool | None = None
    can_share: bool | None = None
    permissions: list[SharedFolderPermission] = Field(default_factory=list)


class SharedFoldersBlock(_Model):
    users: SharedFolderBlock | None = None
    resources: SharedFolderBlock | None = None


# ----------------------------------------------------------------------------
# gateway + project


class Gateway(_Model):
    uid_ref: str
    name: str
    mode: Literal["reference_existing", "create"] = "reference_existing"
    ksm_application_name: str | None = None


class Project(_Model):
    uid_ref: str | None = None
    project: str


# ----------------------------------------------------------------------------
# PAM configurations


class _PamConfigBase(_Model):
    uid_ref: str
    environment: Environment
    title: str | None = None
    gateway_uid_ref: str | None = None
    options: CommonOptions | None = None
    port_mapping: list[str] | None = None
    default_rotation_schedule: RotationSchedule | None = None
    scripts: list[dict[str, Any]] | None = None
    attachments: list[str] | None = None


class PamConfigurationLocal(_PamConfigBase):
    environment: Literal["local"] = "local"
    network_id: str | None = None
    network_cidr: str | None = None


class PamConfigurationAws(_PamConfigBase):
    environment: Literal["aws"] = "aws"
    aws_id: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region_names: list[str] | None = None


class PamConfigurationAzure(_PamConfigBase):
    environment: Literal["azure"] = "azure"
    az_entra_id: str | None = None
    az_client_id: str | None = None
    az_client_secret: str | None = None
    az_subscription_id: str | None = None
    az_tenant_id: str | None = None
    az_resource_groups: list[str] | None = None


class PamConfigurationDomain(_PamConfigBase):
    environment: Literal["domain"] = "domain"
    dom_domain_id: str | None = None
    dom_hostname: str | None = None
    dom_port: str | int | None = None
    dom_use_ssl: bool | None = None
    dom_scan_dc_cidr: bool | None = None
    dom_network_cidr: str | None = None
    dom_administrative_credential_uid_ref: str | None = None


class PamConfigurationGcp(_PamConfigBase):
    environment: Literal["gcp"] = "gcp"
    gcp_id: str | None = None
    gcp_service_account_key: str | None = None
    gcp_google_admin_email: str | None = None
    gcp_region_names: list[str] | None = None


class PamConfigurationOci(_PamConfigBase):
    environment: Literal["oci"] = "oci"
    oci_id: str | None = None
    oci_admin_id: str | None = None
    oci_admin_public_key: str | None = None
    oci_admin_private_key: str | None = None
    oci_tenancy: str | None = None
    oci_region: str | None = None


PamConfiguration = Annotated[
    Union[
        PamConfigurationLocal,
        PamConfigurationAws,
        PamConfigurationAzure,
        PamConfigurationDomain,
        PamConfigurationGcp,
        PamConfigurationOci,
    ],
    Field(discriminator="environment"),
]


# ----------------------------------------------------------------------------
# users


class PamUser(_Model):
    uid_ref: str | None = None
    type: Literal["pamUser"]
    title: str
    notes: str | None = None
    login: str | None = None
    password: str | None = None
    private_pem_key: str | None = None
    distinguished_name: str | None = None
    connect_database: str | None = None
    managed: bool | None = None
    otp: str | None = None
    attachments: list[str] | None = None
    scripts: list[dict[str, Any]] | None = None
    rotation_settings: RotationSettings | None = None


class LoginRecord(_Model):
    uid_ref: str | None = None
    type: Literal["login"]
    title: str
    notes: str | None = None
    login: str | None = None
    password: str | None = None
    otp: str | None = None


User = Annotated[Union[PamUser, LoginRecord], Field(discriminator="type")]


# ----------------------------------------------------------------------------
# resources


class _ResourceBase(_Model):
    uid_ref: str
    title: str
    notes: str | None = None
    pam_configuration_uid_ref: str | None = None
    shared_folder: SharedFolderSection | None = None
    otp: str | None = None
    attachments: list[str] | None = None
    scripts: list[dict[str, Any]] | None = None
    pam_settings: PamSettings | None = None
    users: list[PamUser] = Field(default_factory=list)


class PamMachine(_ResourceBase):
    type: Literal["pamMachine"]
    host: str | None = None
    port: str | int | None = None
    ssl_verification: bool | None = None
    operating_system: Literal["Windows", "Linux", "macOS"] | None = None
    instance_name: str | None = None
    instance_id: str | None = None
    provider_group: str | None = None
    provider_region: str | None = None


class PamDatabase(_ResourceBase):
    type: Literal["pamDatabase"]
    database_type: Literal[
        "postgresql", "postgresql-flexible",
        "mysql", "mysql-flexible",
        "mariadb", "mariadb-flexible",
        "mssql", "oracle", "mongodb",
    ]
    host: str | None = None
    port: str | int | None = None
    use_ssl: bool | None = None
    database_id: str | None = None
    provider_group: str | None = None
    provider_region: str | None = None


class PamDirectory(_ResourceBase):
    type: Literal["pamDirectory"]
    directory_type: Literal["active_directory", "openldap", "ldap"]
    host: str | None = None
    port: str | int | None = None
    use_ssl: bool | None = None
    domain_name: str | None = None
    alternative_ips: list[str] | None = None
    directory_id: str | None = None
    user_match: str | None = None
    provider_group: str | None = None
    provider_region: str | None = None


class PamRemoteBrowser(_Model):
    uid_ref: str
    type: Literal["pamRemoteBrowser"]
    title: str
    notes: str | None = None
    url: str
    otp: str | None = None
    pam_configuration_uid_ref: str | None = None
    shared_folder: SharedFolderSection | None = None
    attachments: list[str] | None = None
    pam_settings: RbiPamSettings | None = None

    @model_validator(mode="after")
    def _no_rotation(self) -> "PamRemoteBrowser":
        opts = (self.pam_settings.options if self.pam_settings else None)
        if opts is not None:
            extras = getattr(opts, "__pydantic_extra__", {}) or {}
            if "rotation" in extras:
                raise ValueError("pamRemoteBrowser cannot set rotation")
        return self


Resource = Annotated[
    Union[PamMachine, PamDatabase, PamDirectory, PamRemoteBrowser],
    Field(discriminator="type"),
]


# ----------------------------------------------------------------------------
# manifest


class Manifest(_Model):
    version: Literal["1"]
    name: str
    projects: list[Project] = Field(default_factory=list)
    shared_folders: SharedFoldersBlock | None = None
    gateways: list[Gateway] = Field(default_factory=list)
    pam_configurations: list[PamConfiguration] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    users: list[User] = Field(default_factory=list)

    # --- accessor helpers -----------------------------------------------

    def iter_all_users(self) -> list[PamUser | LoginRecord]:
        """Yield global users plus nested users under every resource."""
        acc: list[PamUser | LoginRecord] = list(self.users)
        for resource in self.resources:
            acc.extend(getattr(resource, "users", []) or [])
        return acc

    def find_uid_ref(self, uid_ref: str) -> Any:
        for collection in (
            self.projects,
            self.gateways,
            self.pam_configurations,
            self.resources,
            self.users,
        ):
            for item in collection:
                if getattr(item, "uid_ref", None) == uid_ref:
                    return item
        # nested users
        for resource in self.resources:
            for user in getattr(resource, "users", []) or []:
                if getattr(user, "uid_ref", None) == uid_ref:
                    return user
        # shared folder blocks
        if self.shared_folders is not None:
            for block in (self.shared_folders.users, self.shared_folders.resources):
                if block is not None and getattr(block, "uid_ref", None) == uid_ref:
                    return block
        return None

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return list of (uid_ref, kind) for every object that carries one."""
        out: list[tuple[str, str]] = []
        if self.shared_folders is not None:
            for section_name in ("users", "resources"):
                block = getattr(self.shared_folders, section_name)
                if block is not None and block.uid_ref:
                    out.append((block.uid_ref, f"shared_folder_{section_name}"))
        for project in self.projects:
            if project.uid_ref:
                out.append((project.uid_ref, "project"))
        for gateway in self.gateways:
            out.append((gateway.uid_ref, "gateway"))
        for config in self.pam_configurations:
            out.append((config.uid_ref, "pam_configuration"))
        for resource in self.resources:
            out.append((resource.uid_ref, resource.type))
            for user in getattr(resource, "users", []) or []:
                if user.uid_ref:
                    out.append((user.uid_ref, user.type))
        for user in self.users:
            if user.uid_ref:
                out.append((user.uid_ref, user.type))
        return out
