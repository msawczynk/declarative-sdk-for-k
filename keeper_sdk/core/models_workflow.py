"""Typed models for ``keeper-workflow.v1`` manifests."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from keeper_sdk.core.errors import SchemaError

WORKFLOW_FAMILY: Literal["keeper-workflow.v1"] = "keeper-workflow.v1"

UidRef: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
WorkflowRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-workflow:workflows:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
ApproverRef: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^keeper-workflow:approvers:[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
NonEmptyString: TypeAlias = Annotated[str, StringConstraints(min_length=1)]
WorkflowStatus: TypeAlias = Literal["pending", "approved", "denied", "started", "ended"]


class _WorkflowModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)


class WorkflowApprover(_WorkflowModel):
    """One PAM workflow approver identity."""

    uid_ref: UidRef
    name: NonEmptyString
    email: NonEmptyString | None = None


class WorkflowConfig(_WorkflowModel):
    """One PAM workflow definition."""

    uid_ref: UidRef
    name: NonEmptyString
    resource_uid_ref: str | None = None
    approver_uid_refs: list[ApproverRef] = Field(default_factory=list)
    enabled: bool = True


class WorkflowRequest(_WorkflowModel):
    """One desired workflow request seed."""

    uid_ref: UidRef
    workflow_uid_ref: WorkflowRef
    requester: NonEmptyString
    reason: str | None = None


class WorkflowState(_WorkflowModel):
    """Expected state metadata for a workflow request."""

    uid_ref: UidRef
    workflow_uid_ref: WorkflowRef
    status: WorkflowStatus = "pending"


class WorkflowManifestV1(_WorkflowModel):
    """Top-level ``keeper-workflow.v1`` manifest."""

    workflow_schema: Literal["keeper-workflow.v1"] = Field(
        default=WORKFLOW_FAMILY,
        alias="schema",
    )
    workflows: list[WorkflowConfig] = Field(default_factory=list)
    approvers: list[WorkflowApprover] = Field(default_factory=list)
    requests: list[WorkflowRequest] = Field(default_factory=list)
    states: list[WorkflowState] = Field(default_factory=list)

    @model_validator(mode="after")
    def _refs_are_consistent(self) -> WorkflowManifestV1:
        seen: dict[str, str] = {}
        duplicates: list[str] = []
        for uid_ref, kind in self.iter_uid_refs():
            if uid_ref in seen:
                duplicates.append(uid_ref)
            seen[uid_ref] = kind
        if duplicates:
            raise ValueError(f"duplicate uid_ref values: {sorted(set(duplicates))}")

        workflow_refs = {workflow.uid_ref for workflow in self.workflows}
        approver_refs = {approver.uid_ref for approver in self.approvers}
        missing_workflows = sorted(
            {
                _workflow_uid_ref(ref)
                for ref in [r.workflow_uid_ref for r in self.requests]
                + [s.workflow_uid_ref for s in self.states]
                if _workflow_uid_ref(ref) not in workflow_refs
            }
        )
        if missing_workflows:
            raise ValueError(f"unknown workflow refs: {missing_workflows}")

        missing_approvers = sorted(
            {
                _approver_uid_ref(ref)
                for workflow in self.workflows
                for ref in workflow.approver_uid_refs
                if _approver_uid_ref(ref) not in approver_refs
            }
        )
        if missing_approvers:
            raise ValueError(f"unknown workflow approver refs: {missing_approvers}")
        return self

    def iter_uid_refs(self) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        refs.extend((workflow.uid_ref, "workflow") for workflow in self.workflows)
        refs.extend((approver.uid_ref, "workflow_approver") for approver in self.approvers)
        refs.extend((request.uid_ref, "workflow_request") for request in self.requests)
        refs.extend((state.uid_ref, "workflow_state") for state in self.states)
        return refs


def _workflow_uid_ref(ref: str) -> str:
    return ref.rsplit(":", 1)[-1]


def _approver_uid_ref(ref: str) -> str:
    return ref.rsplit(":", 1)[-1]


def load_workflow_manifest(document: dict[str, Any]) -> WorkflowManifestV1:
    """Validate with JSON Schema, then parse as ``WorkflowManifestV1``."""
    from keeper_sdk.core.schema import validate_manifest

    family = validate_manifest(document)
    if family != WORKFLOW_FAMILY:
        raise SchemaError(
            reason=f"expected {WORKFLOW_FAMILY!r}, got {family!r}",
            next_action="set schema: keeper-workflow.v1 on the manifest",
        )
    try:
        return WorkflowManifestV1.model_validate(document)
    except ValidationError as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-workflow.v1 typed rules",
        ) from exc
    except (ValueError, TypeError) as exc:
        raise SchemaError(
            reason=str(exc),
            next_action="fix fields to match keeper-workflow.v1 typed rules",
        ) from exc


__all__ = [
    "WORKFLOW_FAMILY",
    "WorkflowApprover",
    "WorkflowConfig",
    "WorkflowManifestV1",
    "WorkflowRequest",
    "WorkflowState",
    "load_workflow_manifest",
]
