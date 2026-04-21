"""Shared error taxonomy.

Each subclass carries enough context for an operator-facing remediation message:
resource type, uid_ref, reason, and concrete next action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ManifestError(Exception):
    """Base class for all declarative-engine errors."""

    reason: str
    uid_ref: str | None = None
    resource_type: str | None = None
    live_identifier: str | None = None
    next_action: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        parts: list[str] = []
        if self.resource_type:
            parts.append(self.resource_type)
        if self.uid_ref:
            parts.append(f"uid_ref={self.uid_ref}")
        if self.live_identifier:
            parts.append(f"live={self.live_identifier}")
        header = "[" + " ".join(parts) + "] " if parts else ""
        tail = f" Next: {self.next_action}" if self.next_action else ""
        return f"{header}{self.reason}.{tail}"


class SchemaError(ManifestError):
    """Manifest failed JSON Schema or typed-model validation."""


class RefError(ManifestError):
    """A *_uid_ref target is missing, duplicate, cyclic, or by-title unresolved."""


class OwnershipError(ManifestError):
    """Ownership metadata conflict, wrong manager, wrong version, or ambiguity."""


class CollisionError(ManifestError):
    """An unmanaged live record blocks a declarative create."""


class CapabilityError(ManifestError):
    """Missing role enforcement, license, KSM app, or environment support."""


class DeleteUnsupportedError(ManifestError):
    """Delete rejected because provider cannot prove safe ownership or has dependents."""
