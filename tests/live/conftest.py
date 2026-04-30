"""Skip-by-default gate for live-tenant tests.

A test in `tests/live/` runs only if **all** of:

  1. `KEEPER_LIVE_TENANT=1` in env.
  2. The credential env vars the test declares via `@pytest.mark.live(requires=...)`
     are all present (each requires a non-empty string).

Otherwise the test is skipped at collection time so plain
`pytest tests/` (offline default) never touches a tenant.

A test that opts in must additionally pass the parent's pre-flight
checklist in `docs/LIVE_TEST_RUNBOOK.md`. The conftest does NOT
validate the credentials — it only checks they exist.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live(requires=()): live-tenant test; skipped unless "
        "KEEPER_LIVE_TENANT=1 and listed env vars are all set",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_enabled = os.environ.get("KEEPER_LIVE_TENANT") == "1"
    skip_disabled = pytest.mark.skip(
        reason="live-tenant tests skipped (set KEEPER_LIVE_TENANT=1 to run)"
    )

    for item in items:
        marker = item.get_closest_marker("live")
        if marker is None:
            continue
        if not live_enabled:
            item.add_marker(skip_disabled)
            continue
        requires = marker.kwargs.get("requires", ())
        missing = [name for name in requires if not os.environ.get(name)]
        if missing:
            item.add_marker(
                pytest.mark.skip(reason=f"live-tenant test missing env vars: {', '.join(missing)}")
            )
