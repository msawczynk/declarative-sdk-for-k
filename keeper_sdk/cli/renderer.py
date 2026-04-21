"""Rich-based renderer for plans, diffs, and apply outcomes."""

from __future__ import annotations

import io

from rich.console import Console
from rich.table import Table
from rich.text import Text

from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import ApplyOutcome
from keeper_sdk.core.planner import Plan
from keeper_sdk.core.redact import redact

_STYLES = {
    ChangeKind.CREATE: "green",
    ChangeKind.UPDATE: "yellow",
    ChangeKind.DELETE: "red",
    ChangeKind.CONFLICT: "bold red",
    ChangeKind.NOOP: "dim",
}


class RichRenderer:
    def render_plan(self, plan: Plan) -> str:
        console = _console()
        table = Table(title=f"Plan: {plan.manifest_name}")
        table.add_column("Action")
        table.add_column("Type")
        table.add_column("uid_ref")
        table.add_column("Title")
        table.add_column("Keeper UID")
        table.add_column("Note")

        for change in plan.ordered():
            style = _STYLES[change.kind]
            table.add_row(
                Text(change.kind.value, style=style),
                change.resource_type,
                change.uid_ref or "-",
                change.title,
                change.keeper_uid or "-",
                change.reason or "",
            )
        console.print(table)
        console.print(
            f"[green]+{len(plan.creates)}[/] create, "
            f"[yellow]~{len(plan.updates)}[/] update, "
            f"[red]-{len(plan.deletes)}[/] delete, "
            f"[bold red]!{len(plan.conflicts)}[/] conflict, "
            f"[dim]·{len(plan.noops)}[/] noop"
        )
        return _flush(console)

    def render_diff(self, plan: Plan) -> str:
        console = _console()
        console.print(f"[bold]Diff for {plan.manifest_name}[/]")
        for change in plan.changes:
            if change.kind is ChangeKind.NOOP:
                continue
            console.rule(f"{change.kind.value} · {change.resource_type} · {change.title}")
            if change.before:
                console.print("[dim]before:[/]")
                console.print(redact(change.before))
            if change.after:
                console.print("[dim]after:[/]")
                console.print(redact(change.after))
            if change.reason:
                console.print(f"[yellow]{change.reason}[/]")
        return _flush(console)

    def render_outcomes(self, outcomes: list[ApplyOutcome]) -> str:
        console = _console()
        table = Table(title="Apply results")
        table.add_column("Action")
        table.add_column("uid_ref")
        table.add_column("Keeper UID")
        table.add_column("Details")
        for outcome in outcomes:
            table.add_row(
                outcome.action,
                outcome.uid_ref,
                outcome.keeper_uid or "-",
                ", ".join(f"{k}={v}" for k, v in outcome.details.items()),
            )
        console.print(table)
        return _flush(console)


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, record=True)


def _flush(console: Console) -> str:
    return console.export_text()
