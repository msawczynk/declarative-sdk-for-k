import sys
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


def _peak_rss_mib() -> float:
    if sys.platform.startswith("win"):
        pytest.skip("resource.getrusage().ru_maxrss is not available on Windows")
    import resource

    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_per_unit = 1 if sys.platform == "darwin" else 1024
    return peak_rss * bytes_per_unit / (1024 * 1024)


@pytest.mark.slow
def test_lifecycle_under_budget_500_resources() -> None:
    if sys.platform.startswith("win"):
        pytest.skip("resource.getrusage().ru_maxrss is not reliable on Windows")

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
    peak_rss_mib = _peak_rss_mib()

    machine_creates = [change for change in plan.creates if change.resource_type == "pamMachine"]

    assert len(machine_creates) == 500
    assert elapsed < 5.0, f"lifecycle too slow: {elapsed:.2f}s"
    # Observed on 2026-04-25 macOS (darwin, Python 3.14.4): 55.98 MiB peak RSS.
    # Ceiling set to ~3x observed, rounded to a greppable 192 MiB to catch 10x regressions.
    assert peak_rss_mib < 192.0, f"lifecycle used too much memory: {peak_rss_mib:.2f} MiB"
