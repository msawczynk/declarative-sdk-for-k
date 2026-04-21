"""Protocols exchanged between the core, providers, and renderers.

The declarative core is I/O-free. Real providers (Commander, mock, Terraform,
service) implement these Protocols; the core consumes them to execute plans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from keeper_sdk.core.planner import Plan


@dataclass(frozen=True)
class LiveRecord:
    """A Keeper-side record as seen by a provider.

    ``marker`` holds the decoded declarative-ownership payload if present.
    ``payload`` is the provider-normalised field bag (lookup by canonical key
    only — providers must translate their native structures).
    """

    keeper_uid: str
    title: str
    resource_type: str
    folder_uid: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    marker: dict[str, Any] | None = None


@dataclass(frozen=True)
class ApplyOutcome:
    uid_ref: str
    keeper_uid: str
    action: str  # create | update | delete | noop
    details: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    """Backend that can introspect and mutate a Keeper PAM environment."""

    def discover(self) -> list[LiveRecord]:
        """Return every record visible to this provider.

        The core filters and matches against the manifest; providers should
        not pre-filter unless a scope is configured externally.
        """
        ...

    def apply_plan(self, plan: "Plan", *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Execute a plan. Must respect ``dry_run`` and fail fast on errors."""
        ...


class MetadataStore(Protocol):
    """Reads/writes declarative-ownership metadata on live records."""

    def read(self, keeper_uid: str) -> dict[str, Any] | None:
        ...

    def write(self, keeper_uid: str, marker: dict[str, Any]) -> None:
        ...

    def clear(self, keeper_uid: str) -> None:
        ...


class Renderer(Protocol):
    """Formats plans / diffs / outcomes for humans or machines."""

    def render_plan(self, plan: "Plan") -> str:
        ...

    def render_outcomes(self, outcomes: list[ApplyOutcome]) -> str:
        ...
