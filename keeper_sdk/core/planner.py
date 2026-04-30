"""Ordered execution plan.

Consumes changes from :mod:`diff` and the execution order from :mod:`graph`
and produces a deterministic list of steps. Creates run in topological order;
deletes run in reverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from keeper_sdk.core.diff import Change, ChangeKind


@dataclass
class Plan:
    """Deterministic, ordered set of changes for a single manifest.

    A Plan is built from the output of :func:`compute_diff` (unordered
    changes) plus :func:`execution_order` (topological uid_ref order).
    It is the unit of work the CLI and Provider hand to each other:

    * :meth:`ordered` returns creates/updates in dependency order,
      followed by deletes in reverse dependency order.
    * :meth:`is_clean` is the "no actionable changes" predicate used to
      drive the ``plan`` / ``diff`` exit code (2 when non-clean).
    * The ``creates`` / ``updates`` / ``deletes`` / ``conflicts`` /
      ``noops`` properties expose per-kind slices without mutating the
      underlying list.
    """

    manifest_name: str
    changes: list[Change] = field(default_factory=list)
    order: list[str] = field(default_factory=list)

    @property
    def creates(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.CREATE]

    @property
    def updates(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.UPDATE]

    @property
    def deletes(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.DELETE]

    @property
    def conflicts(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.CONFLICT]

    @property
    def noops(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.NOOP]

    @property
    def is_clean(self) -> bool:
        return not (self.creates or self.updates or self.deletes or self.conflicts)

    def ordered(self) -> list[Change]:
        """Return changes in a safe execution order."""
        index = {uid_ref: idx for idx, uid_ref in enumerate(self.order)}

        def key_forward(change: Change) -> tuple[int, int, str]:
            rank = index.get(change.uid_ref or "", 10_000)
            return (0, rank, change.title)

        def key_reverse(change: Change) -> tuple[int, int, str]:
            rank = index.get(change.uid_ref or "", 10_000)
            return (0, -rank, change.title)

        forward_kinds = (ChangeKind.CREATE, ChangeKind.UPDATE)
        forward = sorted([c for c in self.changes if c.kind in forward_kinds], key=key_forward)
        deletes = sorted(self.deletes, key=key_reverse)
        return forward + deletes


def build_plan(
    manifest_name: str,
    changes: list[Change],
    order: list[str],
) -> Plan:
    """Construct a Plan, defensively copying its inputs.

    The copies keep the Plan independent of any mutation the caller
    applies to ``changes`` / ``order`` afterwards — important because
    downstream code (renderers, providers) inspects the Plan across
    multiple call sites.
    """
    return Plan(manifest_name=manifest_name, changes=list(changes), order=list(order))
