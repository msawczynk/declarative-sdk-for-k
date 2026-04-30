from __future__ import annotations

from typing import Any, cast

import pytest

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.secrets.bus import BusClient


def _client() -> BusClient:
    """Bypass the sealed __init__ that raises on construction."""
    return object.__new__(BusClient)


def _assert_not_implemented(exc: CapabilityError) -> None:
    assert "not implemented" in str(exc).lower()


def test_init_seals_construction() -> None:
    with pytest.raises(CapabilityError) as excinfo:
        BusClient(store=cast(Any, object()), directory_uid="bus-directory")

    _assert_not_implemented(excinfo.value)


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("post", {"to": "*", "subject": "topic", "payload": {"ok": True}}),
        ("fetch", {"since_id": None, "consumer": "*"}),
        ("ack", {"last_id": "message-id", "consumer": "*"}),
        ("gc", {}),
    ],
)
def test_method_raises_capability_error(method_name: str, kwargs: dict[str, object]) -> None:
    method = getattr(_client(), method_name)

    with pytest.raises(CapabilityError) as excinfo:
        method(**kwargs)

    _assert_not_implemented(excinfo.value)
