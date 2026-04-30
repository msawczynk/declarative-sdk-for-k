"""Typed models for ``keeper-vault.v1`` manifests (PAM parity program PR-V1).

Slice 1 per ``docs/VAULT_L1_DESIGN.md``: ``records[]`` with ``type == "login"``
only. Graph over ``uid_ref`` / ``folder_ref`` lives in :mod:`keeper_sdk.core.vault_graph`.

Load via :func:`~keeper_sdk.core.manifest.load_declarative_manifest` (or
:func:`load_vault_manifest` after :func:`~keeper_sdk.core.schema.validate_manifest`).
:func:`~keeper_sdk.core.manifest.load_manifest` is **PAM-only** and refuses this family.
CLI + providers ship in ``keeper_sdk/cli`` and ``keeper_sdk.providers`` — see
``docs/VAULT_L1_DESIGN.md`` §8.
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import SchemaError

VAULT_FAMILY: Literal["keeper-vault.v1"] = "keeper-vault.v1"


class _VaultModel(BaseModel):
    """Permissive leaf blocks so schema growth does not break reads."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, str_strip_whitespace=True)


class _StrictVaultModel(BaseModel):
    """Strict typed leaf blocks for manifest-owned Keeper field values."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


VaultJsonScalar: TypeAlias = str | int | float | bool | None
VaultCustomValue: TypeAlias = (
    VaultJsonScalar
    | list[VaultJsonScalar]
    | dict[str, VaultJsonScalar]
    | list[dict[str, VaultJsonScalar]]
)


class VaultSecurityQuestionValue(_StrictVaultModel):
    question: str
    answer: str | None = None


class VaultNameValue(_StrictVaultModel):
    first: str | None = None
    middle: str | None = None
    last: str | None = None


class VaultAddressValue(_StrictVaultModel):
    street1: str | None = None
    street2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


class VaultPhoneValue(_StrictVaultModel):
    region: str | None = None
    number: str | None = None
    ext: str | None = None
    type: str | None = None


class VaultPaymentCardValue(_StrictVaultModel):
    cardNumber: str | None = None
    cardExpirationDate: str | None = None
    cardSecurityCode: str | None = None


class VaultBankAccountValue(_StrictVaultModel):
    accountType: str | None = None
    routingNumber: str | None = None
    accountNumber: str | None = None
    otherType: str | None = None


class VaultKeyPairValue(_StrictVaultModel):
    publicKey: str | None = None
    privateKey: str | None = None


class VaultHostValue(_StrictVaultModel):
    hostName: str | None = None
    port: int | str | None = None


class VaultFileRefValue(_StrictVaultModel):
    uid_ref: str | None = None
    keeper_uid: str | None = None
    name: str | None = None
    title: str | None = None
    mime_type: str | None = None
    size: int | None = None
    content_sha256: str | None = None


VaultFieldValue: TypeAlias = (
    VaultJsonScalar
    | VaultSecurityQuestionValue
    | VaultNameValue
    | VaultAddressValue
    | VaultPhoneValue
    | VaultPaymentCardValue
    | VaultBankAccountValue
    | VaultKeyPairValue
    | VaultHostValue
    | VaultFileRefValue
)


class VaultTypedField(_StrictVaultModel):
    """Manifest-owned Keeper typed field entry.

    ``fields`` and ``custom`` still store plain dictionaries on ``VaultRecord``
    for backwards compatibility, but both lists validate through this model.
    """

    type: Literal[
        "login",
        "password",
        "url",
        "email",
        "phone",
        "address",
        "secret_question",
        "securityQuestion",
        "multiline",
        "text",
        "secret",
        "pinCode",
        "name",
        "paymentCard",
        "bankAccount",
        "keyPair",
        "host",
        "file_ref",
        "fileRef",
    ]
    value: list[VaultFieldValue]
    label: str | None = None


class VaultCustomKeyValue(_StrictVaultModel):
    """Free-form custom key/value row accepted in ``records[].custom[]``."""

    key: str
    value: VaultCustomValue


def _validate_typed_fields(fields: list[dict[str, Any]], *, allow_custom_kv: bool) -> None:
    for field in fields:
        try:
            VaultTypedField.model_validate(field)
            continue
        except ValidationError:
            if not allow_custom_kv:
                raise
        VaultCustomKeyValue.model_validate(field)


class VaultRecord(_VaultModel):
    """One ``records[]`` entry (see ``keeper-vault.v1`` schema ``$defs.record``)."""

    uid_ref: str
    type: str
    title: str
    folder_ref: str | None = None
    notes: str | None = None
    fields: list[dict[str, Any]] = Field(default_factory=list)
    custom: list[dict[str, Any]] = Field(default_factory=list)
    keeper_uid: str | None = None

    @field_validator("fields")
    @classmethod
    def _validate_fields(cls, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _validate_typed_fields(fields, allow_custom_kv=False)
        return fields

    @field_validator("custom")
    @classmethod
    def _validate_custom(cls, custom: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _validate_typed_fields(custom, allow_custom_kv=True)
        return custom


class VaultSharedFolder(_VaultModel):
    """Offline model for a future Commander shared-folder write surface."""

    title: str
    uid_ref: str
    manager: str
    members: list[dict[str, Any]] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(
        default_factory=lambda: {"manage_records": False, "manage_users": False}
    )

    @field_validator("members")
    @classmethod
    def _validate_members(cls, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed_roles = {"read", "edit", "manage"}
        out: list[dict[str, Any]] = []
        for member in members:
            if not isinstance(member, dict):
                raise ValueError("shared-folder member must be an object")
            email = member.get("email")
            role = member.get("role")
            if not isinstance(email, str) or not email:
                raise ValueError("shared-folder member requires email")
            if role not in allowed_roles:
                raise ValueError("shared-folder member role must be read, edit, or manage")
            out.append({"email": email, "role": role})
        return out

    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, permissions: dict[str, bool]) -> dict[str, bool]:
        required = {"manage_records", "manage_users"}
        missing = required - set(permissions)
        if missing:
            raise ValueError("shared-folder permissions require manage_records and manage_users")
        out: dict[str, bool] = {}
        for key, value in permissions.items():
            if key not in required:
                raise ValueError(
                    "shared-folder permissions only support manage_records and manage_users"
                )
            if not isinstance(value, bool):
                raise ValueError("shared-folder permission flags must be booleans")
            out[key] = value
        return out


class VaultManifestV1(_VaultModel):
    """Top-level ``keeper-vault.v1`` manifest (slice 1).

    JSON key remains ``schema`` (alias). Python attribute is ``vault_schema`` so
    we do not shadow :meth:`pydantic.BaseModel.schema`.
    """

    vault_schema: Literal["keeper-vault.v1"] = Field(default=VAULT_FAMILY, alias="schema")
    records: list[VaultRecord] = Field(default_factory=list)
    shared_folders: list[VaultSharedFolder] = Field(default_factory=list)
    record_types: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    keeper_fill: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _l1_login_slice(self) -> VaultManifestV1:
        """``docs/VAULT_L1_DESIGN.md`` §1 — L1 allows ``login`` records only."""
        bad = [r.type for r in self.records if r.type != "login"]
        if bad:
            raise ValueError(
                "keeper-vault L1 slice allows only records with type='login'; "
                f"found other type(s): {sorted(set(bad))[:8]}"
            )
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        """Return ``(uid_ref, record_type)`` for each record (graph prelude)."""
        return [(r.uid_ref, r.type) for r in self.records]


def _shared_folder_diff_payload(folder: VaultSharedFolder) -> dict[str, Any]:
    payload = folder.model_dump(mode="python")
    payload["members"] = sorted(
        payload["members"],
        key=lambda member: str(member.get("email") or "").casefold(),
    )
    return payload


def diff_shared_folder(before: VaultSharedFolder, after: VaultSharedFolder) -> Change:
    """Diff two shared-folder models as one offline planner row."""
    before_payload = _shared_folder_diff_payload(before)
    after_payload = _shared_folder_diff_payload(after)
    diff_fields = [
        key
        for key in ("title", "manager", "members", "permissions")
        if before_payload.get(key) != after_payload.get(key)
    ]
    if not diff_fields:
        return Change(
            kind=ChangeKind.NOOP,
            uid_ref=after.uid_ref,
            resource_type="shared_folder",
            title=after.title,
        )
    return Change(
        kind=ChangeKind.UPDATE,
        uid_ref=after.uid_ref,
        resource_type="shared_folder",
        title=after.title,
        before={key: before_payload.get(key) for key in diff_fields},
        after={key: after_payload.get(key) for key in diff_fields},
    )


SharedFolder = VaultSharedFolder


def diff_shared_folders(before: VaultSharedFolder, after: VaultSharedFolder) -> list[Change]:
    """List-shaped wrapper for callers expecting planner rows."""
    return [diff_shared_folder(before, after)]


def load_vault_manifest(document: dict[str, Any]) -> VaultManifestV1:
    """Validate with JSON Schema + semantic rules, then parse as :class:`VaultManifestV1`.

    Raises :class:`SchemaError` if the document is not ``keeper-vault.v1`` or
    fails validation / L1 slice rules.
    """
    from keeper_sdk.core.schema import PAM_FAMILY, validate_manifest

    family = validate_manifest(document)
    if family == PAM_FAMILY:
        raise SchemaError(
            reason="document is a pam-environment manifest, not keeper-vault.v1",
            next_action="use load_manifest() for PAM or fix top-level schema:",
        )
    if family != VAULT_FAMILY:
        raise SchemaError(
            reason=f"expected {VAULT_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-vault.v1 on the manifest",
        )
    try:
        return VaultManifestV1.model_validate(document)
    except ValueError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix records to match L1 rules in docs/VAULT_L1_DESIGN.md",
        ) from exc
