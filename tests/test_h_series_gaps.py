"""H-series coverage gaps (2026-04-24 devil's-advocate audit).

Every production code path in this file was traced to a live branch with
no corresponding test. One test per branch, no fixtures shared across
targets so each failure mode points at one call site.

H1  ``_run_cmd`` non-zero exit  -> CapabilityError with rc / stdout / stderr
H1b ``_run_cmd`` silent-fail detector (stdout empty + stderr carries a
    known marker for one of _SILENT_FAIL_COMMANDS)
H2  post-apply collision: ``discover`` after write finds two records
    with the same (type, title) -> CollisionError
H3  CLI ``apply`` without ``--allow-delete`` when plan has conflicts
    -> EXIT_CONFLICT (exit code 4), never prompts
H4  ``compute_diff`` marker version mismatch -> OwnershipError
H5  ``_get_keeper_params`` failure branches: no env var, bad path,
    prior attempt already failed
H6  C3 contract: provider.unsupported_capabilities() results appear as
    CONFLICT rows in the CLI plan (so plan == apply --dry-run == apply)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli.main import main as cli_main
from keeper_sdk.core.diff import compute_diff
from keeper_sdk.core.errors import (
    CapabilityError,
    CollisionError,
    OwnershipError,
)
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.manifest import load_manifest_string
from keeper_sdk.providers.commander_cli import CommanderCliProvider

# ---------------------------------------------------------------------------
# H1: _run_cmd error paths


def _make_provider(monkeypatch: pytest.MonkeyPatch, **extra: Any) -> CommanderCliProvider:
    monkeypatch.setattr(
        "keeper_sdk.providers.commander_cli.shutil.which",
        lambda _bin: "/usr/local/bin/keeper",
    )
    kwargs: dict[str, Any] = {"manifest_source": {"version": "1", "name": "t"}}
    kwargs.update(extra)
    return CommanderCliProvider(**kwargs)


class _CompletedStub:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_cmd_nonzero_exit_raises_capability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """keeper_sdk/providers/commander_cli.py L713-718."""
    provider = _make_provider(monkeypatch)

    def fake_run(_argv: list[str], **_kwargs: Any) -> _CompletedStub:
        return _CompletedStub(returncode=9, stdout="partial\n", stderr="boom: totp required\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CapabilityError) as exc:
        provider._run_cmd(["ls", "folder-uid", "--format", "json"])
    assert "rc=9" in exc.value.reason
    assert exc.value.context["stderr"].endswith("totp required\n")


def test_run_cmd_silent_failure_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    """L720-726. rc=0, no stdout, stderr carries a known silent-fail marker."""
    provider = _make_provider(monkeypatch)

    def fake_run(_argv: list[str], **_kwargs: Any) -> _CompletedStub:
        return _CompletedStub(
            returncode=0,
            stdout="",
            stderr="uid-xxx cannot be resolved\n",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CapabilityError) as exc:
        provider._run_cmd(["record-update", "uid-xxx", "--field", "x=y"])
    assert "silent-fail" in exc.value.reason


# ---------------------------------------------------------------------------
# H2: post-apply collision


def test_apply_plan_post_apply_collision_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """keeper_sdk/providers/commander_cli.py L281-289 — after a successful
    pam project import, discover() returns two records with the same
    (resource_type, title); CommanderCliProvider must refuse to label
    either with a marker and raise CollisionError instead of silently
    claiming the first match.
    """
    from keeper_sdk.core.diff import Change, ChangeKind
    from keeper_sdk.core.planner import Plan

    provider = _make_provider(
        monkeypatch,
        manifest_source={
            "version": "1",
            "name": "proj",
            "resources": [
                {"uid_ref": "res.m", "type": "pamMachine", "title": "machine-1"},
            ],
        },
        folder_uid="folder-xyz",
    )

    dup_live = [
        LiveRecord(
            keeper_uid="uid-a",
            title="machine-1",
            resource_type="pamMachine",
            folder_uid="folder-xyz",
            payload={},
            marker=None,
        ),
        LiveRecord(
            keeper_uid="uid-b",
            title="machine-1",
            resource_type="pamMachine",
            folder_uid="folder-xyz",
            payload={},
            marker=None,
        ),
    ]
    monkeypatch.setattr(provider, "discover", lambda: dup_live)
    monkeypatch.setattr(
        provider,
        "_run_cmd",
        lambda _argv: "Access token: 00000000-0000-0000-0000-000000000000\n",
    )
    monkeypatch.setattr(provider, "_resolve_project_resources_folder", lambda _n: None)

    plan = Plan(
        manifest_name="proj",
        order=["res.m"],
        changes=[
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.m",
                resource_type="pamMachine",
                title="machine-1",
                after={"type": "pamMachine", "title": "machine-1"},
            ),
        ],
    )

    with pytest.raises(CollisionError) as exc:
        provider.apply_plan(plan, dry_run=False)
    assert "2 pamMachine" in exc.value.reason


# ---------------------------------------------------------------------------
# H3: CLI apply exits 4 when conflicts exist and --allow-delete not passed


def test_cli_apply_exits_conflict_when_conflicts_and_no_allow_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """keeper_sdk/cli/main.py L302-304 — ``apply`` refuses to proceed
    past a conflict-bearing plan without ``--allow-delete``, and exits
    EXIT_CONFLICT (4) rather than prompting / aborting."""
    manifest_yaml = """
version: "1"
name: proj-h3
resources:
  - uid_ref: res.m
    type: pamMachine
    title: mach
"""
    manifest_path = tmp_path / "m.yaml"
    manifest_path.write_text(manifest_yaml, encoding="utf-8")

    # Force the mock provider to surface a pre-existing unmanaged record
    # with the same title -> compute_diff produces a CONFLICT row.
    from keeper_sdk.providers.mock import MockProvider

    def preload_discover(self: MockProvider) -> list[LiveRecord]:
        return [
            LiveRecord(
                keeper_uid="uid-pre",
                title="mach",
                resource_type="pamMachine",
                folder_uid=None,
                payload={},
                marker=None,
            ),
        ]

    monkeypatch.setattr(MockProvider, "discover", preload_discover)

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["apply", str(manifest_path), "--auto-approve"],
        catch_exceptions=False,
    )
    assert result.exit_code == 4, result.output
    assert "conflict" in result.output.lower()


# ---------------------------------------------------------------------------
# H4: OwnershipError on unsupported marker version


def test_compute_diff_unsupported_marker_version_raises(tmp_path: Path) -> None:
    """keeper_sdk/core/diff.py L210-216 — marker with a version string
    the core can't cope with must raise OwnershipError, not silently
    overwrite the record."""
    manifest = load_manifest_string(
        """
version: "1"
name: proj-h4
resources:
  - uid_ref: res.m
    type: pamMachine
    title: mach
""",
        suffix=".yaml",
    )
    live = [
        LiveRecord(
            keeper_uid="uid-future",
            title="mach",
            resource_type="pamMachine",
            folder_uid=None,
            payload={},
            marker={"manager": "keeper-pam-declarative", "version": "9999"},
        ),
    ]
    with pytest.raises(OwnershipError) as exc:
        compute_diff(manifest, live)
    assert "9999" in exc.value.reason


# ---------------------------------------------------------------------------
# H5: _get_keeper_params failure branches


def test_get_keeper_params_no_helper_falls_back_to_env_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When KEEPER_SDK_LOGIN_HELPER is unset the provider falls back to
    :class:`EnvLoginHelper`, which raises a specific `missing env vars`
    message listing KEEPER_EMAIL / KEEPER_PASSWORD / KEEPER_TOTP_SECRET.
    Previously this path required the helper env var unconditionally
    (v0.x behaviour) — breaking every adopter who wasn't the author.
    """
    provider = _make_provider(monkeypatch)
    monkeypatch.delenv("KEEPER_SDK_LOGIN_HELPER", raising=False)
    for var in ("KEEPER_EMAIL", "KEEPER_PASSWORD", "KEEPER_TOTP_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(CapabilityError) as exc:
        provider._get_keeper_params()
    assert "EnvLoginHelper" in exc.value.reason
    assert "KEEPER_EMAIL" in exc.value.reason


def test_get_keeper_params_helper_path_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An explicit but missing helper path is loud: we do NOT fall back
    to ``EnvLoginHelper`` in that case — the operator clearly intended
    to override the default."""
    provider = _make_provider(monkeypatch)
    monkeypatch.setenv("KEEPER_SDK_LOGIN_HELPER", str(tmp_path / "nope.py"))
    with pytest.raises(CapabilityError) as exc:
        provider._get_keeper_params()
    assert "login helper path not found" in exc.value.reason


def test_get_keeper_params_after_prior_failure_refuses_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """L793-797 — setting ``_keeper_login_attempted`` short-circuits
    so a half-broken workstation can't silently re-try a 30s login
    per subcommand."""
    provider = _make_provider(monkeypatch)
    provider._keeper_login_attempted = True
    with pytest.raises(CapabilityError) as exc:
        provider._get_keeper_params()
    assert "previously failed" in exc.value.reason


# ---------------------------------------------------------------------------
# H6: C3 contract — provider capability gaps appear in the plan


def test_cli_plan_surfaces_provider_capability_gaps_as_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C3 contract test: when a provider declares capability gaps (e.g.
    rotation_settings on Commander), ``plan`` / ``apply --dry-run`` /
    ``apply`` must all surface identical CONFLICT rows. Previously only
    ``apply_plan`` raised, producing green plans + red applies.
    """
    manifest_yaml = """
version: "1"
name: proj-h6
resources:
  - uid_ref: res.m
    type: pamMachine
    title: mach
"""
    manifest_path = tmp_path / "m.yaml"
    manifest_path.write_text(manifest_yaml, encoding="utf-8")

    # Patch MockProvider.unsupported_capabilities to emulate the
    # commander provider's real behaviour without requiring a keeper
    # binary on $PATH.
    from keeper_sdk.providers.mock import MockProvider

    monkeypatch.setattr(
        MockProvider,
        "unsupported_capabilities",
        lambda self, _m=None: [
            "rotation_settings is not implemented (Commander hook: `keeper pam rotation set`)"
        ],
    )

    import json as _json

    runner = CliRunner()
    plan_result = runner.invoke(
        cli_main,
        ["plan", str(manifest_path), "--json"],
        catch_exceptions=False,
    )
    dry_result = runner.invoke(
        cli_main,
        ["apply", str(manifest_path), "--dry-run", "--auto-approve"],
        catch_exceptions=False,
    )
    # Both paths must report exit 4 (EXIT_CONFLICT).
    assert plan_result.exit_code == 4, plan_result.output
    assert dry_result.exit_code == 4, dry_result.output

    # --json mode exposes the full reason without table truncation.
    doc = _json.loads(plan_result.output)
    capability_conflicts = [
        c for c in doc["changes"] if c["kind"] == "conflict" and c["resource_type"] == "capability"
    ]
    assert len(capability_conflicts) == 1
    assert "rotation_settings" in capability_conflicts[0]["reason"]
