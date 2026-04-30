from __future__ import annotations

import pytest

from keeper_sdk.secrets.bus import BusClient


def _bus() -> BusClient:
    """Bypass sealed construction so method stubs can be tested directly."""
    return object.__new__(BusClient)


def test_bus_client_imports() -> None:
    assert BusClient.__name__ == "BusClient"


def test_publish_raises_not_implemented_with_next_action() -> None:
    with pytest.raises(NotImplementedError, match="next_action"):
        _bus().publish(to="*", subject="topic", payload={"ok": True})


def test_subscribe_raises_not_implemented_with_next_action() -> None:
    with pytest.raises(NotImplementedError, match="next_action"):
        _bus().subscribe(consumer="*")
