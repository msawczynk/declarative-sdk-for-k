import time

import pytest

from keeper_sdk.core import (
    Manifest,
    build_graph,
    build_plan,
    compute_diff,
    execution_order,
    validate_manifest,
)
from keeper_sdk.providers import MockProvider


@pytest.mark.slow
def test_lifecycle_under_budget_500_resources() -> None:
    resources = [
        {
            "uid_ref": f"r{i}",
            "type": "pamMachine",
            "title": f"host-{i}",
            "host": f"10.0.{i // 256}.{i % 256}",
            "pam_configuration_uid_ref": "cfg-main",
        }
        for i in range(500)
    ]
    document = {
        "version": "1",
        "name": "perf",
        "gateways": [{"uid_ref": "gw-main", "name": "gw", "mode": "reference_existing"}],
        "pam_configurations": [
            {
                "uid_ref": "cfg-main",
                "environment": "local",
                "gateway_uid_ref": "gw-main",
            }
        ],
        "resources": resources,
    }

    t0 = time.perf_counter()
    validate_manifest(document)
    manifest = Manifest.model_validate(document)
    graph = build_graph(manifest)
    order = execution_order(graph)
    provider = MockProvider(manifest.name)
    changes = compute_diff(manifest, provider.discover())
    plan = build_plan(manifest.name, changes, order)
    elapsed = time.perf_counter() - t0

    machine_creates = [change for change in plan.creates if change.resource_type == "pamMachine"]

    assert len(machine_creates) == 500
    assert elapsed < 5.0, f"lifecycle too slow: {elapsed:.2f}s"
