"""KSM-backed inter-agent bus stub.

The bus is intended to let autonomous SDK workers publish and subscribe to
low-volume coordination messages through a Keeper Secrets Manager directory
record. ``bootstrap_ksm_application(create_bus_directory=True, ...)`` already
provisions that directory record; this module is the future client that will
read and write it.

This is not implemented yet because the bus protocol still needs design and
live proof for envelope shape, consumer cursors, compare-and-swap conflict
handling, retention, and operator debug commands. Until that design exists,
every public ``BusClient`` / ``KsmBus`` method raises ``NotImplementedError``
with a concrete ``next_action`` instead of pretending a bus exists.

Design placeholder: ``docs/KSM_BUS.md``.

Public API (design stub)
------------------------

::

    class BusClient:
        def __init__(self, *, store: KsmSecretStore, directory_uid: str): ...
        def publish(self, *, to: str, subject: str, payload: Any,
                    ttl_s: int = 3600, trace_id: str | None = None) -> str: ...
        def subscribe(self, *, since_id: str | None = None,
                      consumer: str = "*") -> list[BusMessage]: ...

    KsmBus = BusClient

Older ``post`` / ``fetch`` / ``ack`` / ``gc`` names remain as sealed
compatibility stubs until the publish/subscribe protocol is designed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, NoReturn

from keeper_sdk.core.errors import CapabilityError

if TYPE_CHECKING:
    from keeper_sdk.secrets.ksm import KsmSecretStore


_NOT_IMPLEMENTED_REASON = "KSM inter-agent bus is not implemented"
_NOT_IMPLEMENTED_NEXT_ACTION = "design bus protocol and implement publish/subscribe."
_NOT_IMPLEMENTED_MESSAGE = (
    "KSM inter-agent bus is not implemented. "
    "next_action: design bus protocol and implement publish/subscribe."
)


class _KsmBusNotImplementedError(NotImplementedError, CapabilityError):
    """NotImplementedError with legacy CapabilityError compatibility."""

    def __init__(self) -> None:
        NotImplementedError.__init__(self, _NOT_IMPLEMENTED_MESSAGE)
        self.reason = _NOT_IMPLEMENTED_REASON
        self.uid_ref = None
        self.resource_type = None
        self.live_identifier = None
        self.next_action = _NOT_IMPLEMENTED_NEXT_ACTION
        self.context: dict[str, Any] = {}

    def __str__(self) -> str:
        return _NOT_IMPLEMENTED_MESSAGE


def _raise_not_implemented() -> NoReturn:
    raise _KsmBusNotImplementedError()


@dataclass(frozen=True)
class BusMessage:
    """Frozen view of one envelope read from the bus directory record.

    Kept here (rather than left as a TODO comment) so callers that want
    to type-annotate consumer code today don't have to wait for the bus
    to ship; the wire format above is the contract.
    """

    id: str
    sender: str
    recipient: str
    subject: str
    timestamp: str
    payload: Any
    trace_id: str | None = None
    ttl_seconds: int = 3600


class BusClient:
    """Sealed entry point for the Phase B inter-agent bus.

    All methods raise ``NotImplementedError`` so that any code path that
    accidentally activates the bus today fails with the canonical next action.
    The concrete exception also subclasses ``CapabilityError`` for callers
    written against the earlier sealed scaffold.
    """

    def __init__(
        self,
        *,
        store: KsmSecretStore,
        directory_uid: str,
    ) -> None:
        _ = store, directory_uid
        _raise_not_implemented()

    def publish(self, *args: Any, **kwargs: Any) -> str:
        _ = args, kwargs
        _raise_not_implemented()

    def subscribe(self, *args: Any, **kwargs: Any) -> list[BusMessage]:
        _ = args, kwargs
        _raise_not_implemented()

    def post(
        self,
        *,
        to: str,
        subject: str,
        payload: Any,
        ttl_s: int = 3600,
        trace_id: str | None = None,
    ) -> str:
        return self.publish(
            to=to,
            subject=subject,
            payload=payload,
            ttl_s=ttl_s,
            trace_id=trace_id,
        )

    def fetch(
        self,
        *,
        since_id: str | None = None,
        consumer: str = "*",
    ) -> list[BusMessage]:
        return self.subscribe(since_id=since_id, consumer=consumer)

    def ack(self, *, last_id: str, consumer: str) -> None:
        _ = last_id, consumer
        _raise_not_implemented()

    def gc(self, *, now: datetime | None = None) -> int:
        _ = now
        _raise_not_implemented()


KsmBus = BusClient


__all__ = ["BusClient", "BusMessage", "KsmBus"]
