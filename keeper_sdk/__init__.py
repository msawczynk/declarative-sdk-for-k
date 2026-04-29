"""Keeper PAM Declarative SDK.

Pure-Python reference implementation of the declarative design shipped in
``keeper-pam-declarative/``. Public surface lives in :mod:`keeper_sdk.core`.

Typical use:

    from keeper_sdk.core import load_manifest, build_graph, build_plan, compute_diff
    from keeper_sdk.providers import MockProvider

    manifest = load_manifest("env.yaml")
    provider = MockProvider(manifest.name)
    changes = compute_diff(manifest, provider.discover())
    plan = build_plan(manifest.name, changes, [])
    provider.apply_plan(plan)
"""

__version__ = "2.0.0"

from keeper_sdk import core, providers
from keeper_sdk.core import (
    Manifest,
    Plan,
    build_graph,
    build_plan,
    compute_diff,
    dump_manifest,
    execution_order,
    load_manifest,
    validate_manifest,
)

__all__ = [
    "__version__",
    "core",
    "providers",
    "Manifest",
    "Plan",
    "build_graph",
    "build_plan",
    "compute_diff",
    "dump_manifest",
    "execution_order",
    "load_manifest",
    "validate_manifest",
]
