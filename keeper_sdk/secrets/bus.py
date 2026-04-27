"""Phase B: KSM-backed inter-agent message bus (SKELETON, do not enable).

Status
------

This module is **not implemented**. It is a sealed scaffold so the next
agent can wire the API without re-deriving the design. Every public entry
point raises :class:`CapabilityError` with a precise next-action so
accidental imports fail loudly instead of silently no-oping.

The ``bootstrap_ksm_application(create_bus_directory=True, ...)`` flow
already provisions the on-tenant directory record this module will read
and write; that contract is frozen and covered by unit tests in
``tests/test_bootstrap_ksm.py::test_bootstrap_with_bus_creates_directory_record``
and ``...::test_bootstrap_with_bus_reuses_existing_directory``.

Why we picked KSM as the bus substrate
--------------------------------------

We considered three substrates before settling on KSM directory records:

1. **Standalone Keeper records (one per message)** — would explode the
   tenant's record count, blow past the 25k-records-per-app soft limit,
   and lose ordering. Rejected.

2. **External broker (Redis/SQS/etc.)** — adds a second auth surface,
   second secrets-rotation story, and a second outage axis. The whole
   point of the KSM bootstrap is that operators already trust the vault
   for credentials; reusing it for low-volume agent coordination is
   strictly less infrastructure. Selected.

3. **Local filesystem fallback** — works on a single workstation, falls
   apart for cross-host agents and CI runners. Human-readable notes stay
   separate; the bus stays machine-coordinated. Out of scope.

Wire format
-----------

A single KSM record (the *directory record*, created on demand by
``bootstrap_ksm_application(create_bus_directory=True)``) holds the bus
state. Its custom fields encode messages as JSON envelopes::

    {
      "v": 1,                       # envelope version, monotonic
      "id": "<uuid4>",              # message id, immutable
      "from": "<agent-id>",         # producer label, free-form
      "to": "<agent-id>|*",         # consumer label or broadcast
      "subject": "<topic>",         # short routing key
      "ts": "<ISO-8601 UTC>",       # producer wall clock
      "payload": <json-value>,      # caller-supplied body
      "ttl_s": <int>,               # optional, default 3600
      "trace_id": "<uuid4>"         # optional, propagates across agents
    }

A separate custom field, ``cursor`` (single value, integer), is the
high-watermark a consumer last acknowledged.

Compare-and-swap (CAS) semantics
--------------------------------

The directory record is single-writer-at-a-time by convention; concurrent
producers race in the open. We coordinate via the record's revision
number returned from ``KSMCommand.update_record``. Each ``post`` /
``ack`` operation:

1. Loads the directory record and snapshots its revision.
2. Applies the local mutation (append envelope, advance cursor).
3. Issues an update with ``If-Match: <snapshot revision>``.
4. On 409, reloads, re-applies, retries with bounded backoff (max 8
   tries, total ≤ 12s — same rationale as the bootstrap verify loop).

Producers MUST be idempotent on ``id`` so a retry after a partial
visible-but-not-acked write doesn't duplicate. Consumers MUST treat the
cursor as advisory and de-dup on ``id`` to absorb the same edge.

Public API (TO IMPLEMENT)
-------------------------

::

    class BusClient:
        def __init__(self, *, store: KsmSecretStore, directory_uid: str): ...
        def post(self, *, to: str, subject: str, payload: Any, ttl_s: int = 3600,
                 trace_id: str | None = None) -> str: ...
        def fetch(self, *, since_id: str | None = None,
                  consumer: str = "*") -> list[BusMessage]: ...
        def ack(self, *, last_id: str, consumer: str) -> None: ...
        def gc(self, *, now: datetime | None = None) -> int: ...

    @dataclass(frozen=True)
    class BusMessage: ...

Next-action checklist for the implementing agent
-------------------------------------------------

1. Add ``KSMCommand.update_record`` and ``KSMCommand.get_record`` probes
   under ``scripts/probe_commander.py`` to confirm the revision header is
   surfaced in this Commander pin (``.commander-pin``). If not, use the
   ``record_management.update_record_v3`` path instead — log the rev
   source choice in JOURNAL.md.
2. Wire CAS retries through the same exponential backoff helper used in
   ``keeper_sdk.secrets.bootstrap._verify_redeemed_config`` (extract to
   ``keeper_sdk.core.retry`` first; current bootstrap copy is fine to
   inline-replace).
3. Cap envelope size at 32 KB (KSM custom field practical ceiling).
   Reject larger payloads with :class:`CapabilityError` — operators
   should put bulk artefacts in regular records and pass the UID.
4. Add ``tests/test_bus_ksm.py`` with the same fake-KSM substrate from
   ``tests/_fakes/ksm.py``. Cover: post + fetch, CAS conflict + retry,
   TTL expiry sweep, broadcast vs. addressed delivery, idempotency on
   replayed ``id``.
5. Document the operator runbook in ``docs/KSM_BUS.md`` (model on
   ``docs/KSM_BOOTSTRAP.md``); link it from ``docs/KSM_INTEGRATION.md``.
6. Wire a ``dsk bus`` family of CLI subcommands in
   ``keeper_sdk/cli/main.py`` (``post``, ``tail``, ``ack``, ``gc``) so
   operators can debug without writing Python.

Until the steps above are done this module stays sealed: importing it is
fine, instantiating ``BusClient`` raises :class:`CapabilityError` so the
guardrail is structural, not aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from keeper_sdk.core.errors import CapabilityError

if TYPE_CHECKING:
    from keeper_sdk.secrets.ksm import KsmSecretStore


_NOT_IMPLEMENTED_NEXT_ACTION = (
    "Phase B (KSM bus) is not implemented yet; see "
    "keeper_sdk/secrets/bus.py module docstring for the next-action "
    "checklist before turning this on."
)


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

    All methods raise :class:`CapabilityError` so that any code path that
    accidentally activates the bus today fails with the canonical error
    shape — not a silent no-op, not a generic ``NotImplementedError``.
    """

    def __init__(
        self,
        *,
        store: KsmSecretStore,
        directory_uid: str,
    ) -> None:
        _ = store, directory_uid
        raise CapabilityError(
            reason="Phase B KSM bus client is not implemented",
            next_action=_NOT_IMPLEMENTED_NEXT_ACTION,
        )

    def post(
        self,
        *,
        to: str,
        subject: str,
        payload: Any,
        ttl_s: int = 3600,
        trace_id: str | None = None,
    ) -> str:
        _ = to, subject, payload, ttl_s, trace_id
        raise CapabilityError(
            reason="Phase B KSM bus 'post' is not implemented",
            next_action=_NOT_IMPLEMENTED_NEXT_ACTION,
        )

    def fetch(
        self,
        *,
        since_id: str | None = None,
        consumer: str = "*",
    ) -> list[BusMessage]:
        _ = since_id, consumer
        raise CapabilityError(
            reason="Phase B KSM bus 'fetch' is not implemented",
            next_action=_NOT_IMPLEMENTED_NEXT_ACTION,
        )

    def ack(self, *, last_id: str, consumer: str) -> None:
        _ = last_id, consumer
        raise CapabilityError(
            reason="Phase B KSM bus 'ack' is not implemented",
            next_action=_NOT_IMPLEMENTED_NEXT_ACTION,
        )

    def gc(self, *, now: datetime | None = None) -> int:
        _ = now
        raise CapabilityError(
            reason="Phase B KSM bus 'gc' is not implemented",
            next_action=_NOT_IMPLEMENTED_NEXT_ACTION,
        )


__all__ = ["BusClient", "BusMessage"]
