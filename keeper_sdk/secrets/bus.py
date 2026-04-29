"""KSM-backed inter-agent bus helpers.

The basic ``KsmBus`` lets autonomous SDK workers share low-volume key/value
messages through custom fields on one Keeper Secrets Manager record.
``bootstrap_ksm_application(create_bus_directory=True, ...)`` provisions that
record and shares it into the KSM application.

The richer publish/subscribe ``BusClient`` remains sealed until the protocol
has design and live proof for envelope shape, consumer cursors, compare-and-swap
conflict handling, retention, and operator debug commands.

Design placeholder: ``docs/KSM_BUS.md``.

Public API (design stub)
------------------------

::

    bus = KsmBus(store, record_uid)
    bus.put("phase7.status", "ready")
    value = bus.get("phase7.status")

Publish/subscribe design stub::

    class BusClient:
        def __init__(self, *, store: KsmSecretStore, directory_uid: str): ...
        def publish(self, *, to: str, subject: str, payload: Any,
                    ttl_s: int = 3600, trace_id: str | None = None) -> str: ...
        def subscribe(self, *, since_id: str | None = None,
                      consumer: str = "*") -> list[BusMessage]: ...

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


_BUS_FIELD_TYPE = "text"
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


def _matching_custom_field(record: Any, key: str) -> dict[str, Any] | None:
    for entry in record.dict.get("custom", []) or []:
        if isinstance(entry, dict) and (entry.get("label") or "") == key:
            return entry
    return None


def _sync_record(record: Any) -> None:
    update = getattr(record, "_update", None)
    if callable(update):
        update()


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


class KsmBus:
    """Basic KSM-backed key/value bus using custom fields on one record."""

    def __init__(self, store: KsmSecretStore, record_uid: str) -> None:
        self._store = store
        self._record_uid = record_uid

    def _record(self) -> Any:
        if not self._record_uid:
            _raise_not_implemented()
        return self._store.get_record(self._record_uid)

    def put(self, key: str, value: str) -> None:
        """Write ``value`` to a custom text field labelled ``key``."""
        if not key:
            raise ValueError("KSM bus key must not be empty")
        record = self._record()
        custom = record.dict.setdefault("custom", [])
        field = _matching_custom_field(record, key)
        if field is None:
            custom.append({"type": _BUS_FIELD_TYPE, "label": key, "value": [value]})
        else:
            field["type"] = field.get("type") or _BUS_FIELD_TYPE
            field["value"] = [value]
        _sync_record(record)
        save = getattr(self._store.client(), "save", None)
        if callable(save):
            save(record)

    def get(self, key: str) -> str | None:
        """Read a custom field labelled ``key`` from the bus record."""
        if not key:
            raise ValueError("KSM bus key must not be empty")
        field = _matching_custom_field(self._record(), key)
        if field is None:
            return None
        values = field.get("value") or []
        if not values:
            return None
        return str(values[0])


__all__ = ["BusClient", "BusMessage", "KsmBus"]
