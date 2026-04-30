"""Crossplane provider scaffold for Keeper resources managed by DSK.

Usage pattern:
    Kubernetes operators install the preview XRDs from ``crossplane/xrds/``
    and bind them to the stub Compositions in ``crossplane/compositions/``.
    A future Crossplane Function or provider controller will translate each
    composite resource into a small DSK manifest, run ``dsk plan`` during
    observe, and run ``dsk apply`` for create/update/delete. The generated
    manifests map ``KeeperRecord`` resources to ``keeper-vault.v1`` login
    records and ``KeeperSharedFolder`` resources to
    ``keeper-vault-sharing.v1`` shared folders.

This module is only the offline Python foundation. It does not start a
Crossplane gRPC function server, call Kubernetes, call Commander, or run the
``dsk`` CLI. All lifecycle methods raise :class:`CapabilityError` with a
documentation pointer so callers get an explicit preview-gate failure rather
than an accidental partial reconcile.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.interfaces import ApplyOutcome, LiveRecord, Provider
from keeper_sdk.core.planner import Plan

DOCS_NEXT_ACTION = (
    "Read docs/CROSSPLANE_INTEGRATION.md; Crossplane support is preview-gated "
    "until a packaged function/controller, credential model, and live proof exist."
)


class CrossplaneProvider(Provider):
    """Preview-gated Crossplane lifecycle adapter.

    The intended controller lifecycle is:

    1. ``observe`` receives a Crossplane managed/composite resource and builds
       a DSK manifest fragment from ``spec.parameters``.
    2. ``plan`` runs the same deterministic DSK planner used by the CLI.
    3. ``create`` and ``update`` execute ``dsk apply`` for an approved plan.
    4. ``delete`` executes a marker-scoped DSK delete path with explicit
       deletion enabled.

    None of those steps are implemented yet. This class exists so importers,
    documentation, and offline tests have a stable module boundary while the
    Crossplane integration remains preview-gated.
    """

    docs_next_action = DOCS_NEXT_ACTION

    def plan(self, resource: Mapping[str, Any] | None = None) -> Plan:
        """Plan a Crossplane resource reconciliation.

        ``resource`` is expected to be a Kubernetes object dict in a future
        implementation. The preview stub always raises ``CapabilityError``.
        """

        _raise_preview_gate("plan")

    def apply(
        self,
        resource: Mapping[str, Any] | None = None,
        *,
        dry_run: bool = False,
    ) -> list[ApplyOutcome]:
        """Apply a planned Crossplane resource reconciliation.

        ``dry_run`` is reserved for parity with DSK ``apply --dry-run``.
        The preview stub always raises ``CapabilityError``.
        """

        _raise_preview_gate("apply")

    def observe(self, resource: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Observe live Keeper state for a Crossplane resource GET."""

        _raise_preview_gate("observe")

    def create(self, resource: Mapping[str, Any] | None = None) -> ApplyOutcome:
        """Create the Keeper object represented by a Crossplane resource."""

        _raise_preview_gate("create")

    def update(self, resource: Mapping[str, Any] | None = None) -> ApplyOutcome:
        """Update the Keeper object represented by a Crossplane resource."""

        _raise_preview_gate("update")

    def delete(self, resource: Mapping[str, Any] | None = None) -> ApplyOutcome:
        """Delete the Keeper object represented by a Crossplane resource."""

        _raise_preview_gate("delete")

    def discover(self) -> list[LiveRecord]:
        """Provider protocol hook; blocked until Crossplane runtime exists."""

        _raise_preview_gate("discover")

    def apply_plan(self, plan: Plan, *, dry_run: bool = False) -> list[ApplyOutcome]:
        """Provider protocol hook; blocked until Crossplane runtime exists."""

        _raise_preview_gate("apply_plan")

    def unsupported_capabilities(self, manifest: Any = None) -> list[str]:
        """Provider protocol hook; blocked until Crossplane runtime exists."""

        _raise_preview_gate("unsupported_capabilities")

    def check_tenant_bindings(self, manifest: Any = None) -> list[str]:
        """Provider protocol hook; blocked until Crossplane runtime exists."""

        _raise_preview_gate("check_tenant_bindings")


def _raise_preview_gate(operation: str) -> NoReturn:
    raise CapabilityError(
        reason=f"Crossplane provider {operation} is not implemented",
        resource_type="crossplane",
        next_action=DOCS_NEXT_ACTION,
    )
