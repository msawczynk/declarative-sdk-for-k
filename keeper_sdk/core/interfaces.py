"""Protocols exchanged between the core, providers, and renderers.

The declarative core is I/O-free. Real providers (Commander, mock, Terraform,
service) implement these Protocols; the core consumes them to execute plans.
"""

# ruff: noqa: UP037

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

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
    """Result of applying a single planned change.

    Attributes:
        uid_ref: Manifest handle for the resource. Empty string if the
            change had no uid_ref (e.g. a synthetic conflict outcome).
        keeper_uid: Vault UID of the record after the action completed.
            Empty string for dry-run or failed creates.
        action: One of ``create``, ``update``, ``delete``, ``noop``,
            ``conflict``. Matches :class:`ChangeKind` values.
        details: Free-form provider-specific metadata. Well-known keys
            include ``dry_run`` (bool), ``marker_written`` (bool),
            ``verified`` (bool), ``field_drift`` (dict), ``reason`` (str),
            ``reused_existing`` (bool), ``removed`` (bool).
    """

    uid_ref: str
    keeper_uid: str
    action: str
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

    def unsupported_capabilities(self, manifest: Any) -> list[str]:  # noqa: ARG002
        """Return human-readable reasons the manifest exceeds this provider.

        Called by the CLI at plan/apply time BEFORE ``apply_plan``. Each
        returned string becomes a ``ChangeKind.CONFLICT`` row in the plan,
        guaranteeing ``plan`` / ``apply --dry-run`` / ``apply`` surface the
        same capability failures — no more green-plan + red-apply.

        Default for providers that implement everything the schema accepts:
        return ``[]``. See :class:`MockProvider` for the trivial case and
        :meth:`CommanderCliProvider.unsupported_capabilities` for the
        Commander-release-17.2.13 list (rotation, JIT, gateway mode:create,
        …).
        """
        ...


class MetadataStore(Protocol):
    """Reads/writes declarative-ownership metadata on live records."""

    def read(self, keeper_uid: str) -> dict[str, Any] | None: ...

    def write(self, keeper_uid: str, marker: dict[str, Any]) -> None: ...

    def clear(self, keeper_uid: str) -> None: ...


class Renderer(Protocol):
    """Formats plans / diffs / outcomes for humans or machines."""

    def render_plan(self, plan: "Plan") -> str: ...

    def render_diff(self, plan: "Plan") -> str: ...

    def render_outcomes(self, outcomes: list[ApplyOutcome]) -> str: ...
