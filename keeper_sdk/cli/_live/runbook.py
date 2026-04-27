"""Live smoke runbook — bootstrap → login → apply → diff → cleanup.

Bundles the live-tenant smoke loop so the parent doesn't have to
remember the order or the per-phase verification. Each phase yields a
:class:`Phase` that the caller appends to a :class:`Transcript`.

The functions here DO NOT read any secret material directly. Credentials
flow in via env vars (or a path to a KSM config file); on failure they
are NOT included in the error message — only the phase name + a
truncated stderr summary.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

from .transcript import Phase

DEFAULT_PHASES = ("bootstrap", "login", "apply", "diff", "cleanup")


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Run a subprocess; return (rc, stdout, stderr).

    Stderr is truncated to 2 KB so a verbose tool can't blow up the
    transcript. Stdout is returned in full because phases that want to
    parse it (e.g. plan/diff JSON output) need the whole thing.
    """
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env if env is not None else os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    stderr = proc.stderr or ""
    if len(stderr) > 2048:
        stderr = stderr[:2048] + "...<truncated>"
    return proc.returncode, proc.stdout or "", stderr


def phase_bootstrap(
    *,
    ksm_record_uid: str,
    ksm_config_path: Path | None = None,
    workdir: Path,
    app_name: str | None = None,
    login_helper: str | None = None,
) -> Phase:
    """Run `dsk bootstrap-ksm`. Records app UID fingerprint."""
    started = time.monotonic()
    out = (ksm_config_path or (workdir / "ksm.config")).resolve()
    # Unique app name per workdir so parallel test tmp dirs never collide on KSM app title.
    name = (
        app_name
        or ("dsk-live-" + hashlib.sha256(str(workdir).encode("utf-8")).hexdigest()[:20])[:64]
    )
    helper = login_helper or os.environ.get("KEEPER_LIVE_BOOTSTRAP_LOGIN_HELPER") or "commander"
    cmd = [
        "dsk",
        "bootstrap-ksm",
        "--app-name",
        name,
        "--admin-record-uid",
        ksm_record_uid,
        "--config-out",
        str(out),
        "--overwrite",
        "--login-helper",
        helper,
    ]
    rc, stdout, stderr = _run(cmd, cwd=workdir, timeout=300)
    elapsed = int((time.monotonic() - started) * 1000)
    phase = Phase(name="bootstrap", elapsed_ms=elapsed)
    if rc != 0:
        phase.status = "failed"
        phase.error = (stderr or "") + (stdout or "")
        return phase
    phase.status = "ok"
    phase.details = {"stdout_len": len(stdout)}
    return phase


def phase_login(*, helper_path: Path, workdir: Path) -> Phase:
    """Verify the KSM-derived login helper resolves to a working session.

    Runs `dsk validate --online` against an empty manifest as a cheap
    "the session works" check — `validate --online` already exercises
    `pam config list` + `pam gateway list`.
    """
    started = time.monotonic()
    rc, stdout, stderr = _run(
        ["dsk", "validate", "--online", str(workdir / "_smoke_empty.yml")],
        cwd=workdir,
    )
    elapsed = int((time.monotonic() - started) * 1000)
    phase = Phase(name="login", elapsed_ms=elapsed)
    # rc 0 (clean), 4 (conflict), 5 (capability) all mean "session worked".
    # rc 1 (generic) or 2 (schema) mean we couldn't even reach the tenant.
    if rc in (0, 4, 5):
        phase.status = "ok"
        phase.details = {"validate_rc": rc, "stdout_chars": len(stdout)}
    else:
        phase.status = "failed"
        phase.error = stderr
    return phase


def phase_apply(*, manifest_path: Path, workdir: Path) -> Phase:
    """Run `dsk apply` on the smoke manifest."""
    started = time.monotonic()
    rc, stdout, stderr = _run(
        ["dsk", "apply", str(manifest_path), "--yes"],
        cwd=workdir,
        timeout=300,
    )
    elapsed = int((time.monotonic() - started) * 1000)
    phase = Phase(name="apply", elapsed_ms=elapsed)
    if rc == 0:
        phase.status = "ok"
        phase.details = {"stdout_chars": len(stdout)}
    else:
        phase.status = "failed"
        phase.error = stderr
    return phase


def phase_diff(*, manifest_path: Path, workdir: Path) -> Phase:
    """Re-plan the same manifest. Clean re-plan == 0 changes."""
    started = time.monotonic()
    rc, stdout, stderr = _run(
        ["dsk", "diff", str(manifest_path)],
        cwd=workdir,
    )
    elapsed = int((time.monotonic() - started) * 1000)
    phase = Phase(name="diff", elapsed_ms=elapsed)
    if rc == 0:
        phase.status = "ok"
        phase.details = {"clean_replan": True}
    elif rc == 2:
        phase.status = "failed"
        phase.error = "diff shows pending changes after apply (rc=2)"
        phase.details = {"clean_replan": False, "diff_chars": len(stdout)}
    else:
        phase.status = "failed"
        phase.error = stderr
    return phase


def phase_cleanup(*, cleanup_callable) -> Phase:
    """Run the test-supplied cleanup function. Failure here is loud."""
    started = time.monotonic()
    phase = Phase(name="cleanup")
    try:
        cleanup_callable()
        phase.status = "ok"
    except Exception as exc:
        phase.status = "failed"
        phase.error = str(exc)[:500]
    phase.elapsed_ms = int((time.monotonic() - started) * 1000)
    return phase


def iter_default_phases(
    *,
    ksm_record_uid: str,
    ksm_config_path: Path | None,
    manifest_path: Path,
    workdir: Path,
    cleanup_callable=None,
) -> Iterator[Phase]:
    """Yield phases in order; stop on first failure (later phases are
    appended as `skipped` so the transcript is still complete).

    The caller (CLI verb or pytest) is responsible for adding each
    yielded phase to the Transcript.
    """
    helper_path = workdir / "ksm.config"

    p = phase_bootstrap(
        ksm_record_uid=ksm_record_uid,
        ksm_config_path=ksm_config_path,
        workdir=workdir,
    )
    yield p
    if p.status != "ok":
        for name in ("login", "apply", "diff", "cleanup"):
            yield Phase(name=name, status="skipped")
        return

    p = phase_login(helper_path=helper_path, workdir=workdir)
    yield p
    if p.status != "ok":
        for name in ("apply", "diff", "cleanup"):
            yield Phase(name=name, status="skipped")
        return

    p = phase_apply(manifest_path=manifest_path, workdir=workdir)
    yield p
    if p.status != "ok":
        for name in ("diff", "cleanup"):
            yield Phase(name=name, status="skipped")
        if cleanup_callable is not None:
            yield phase_cleanup(cleanup_callable=cleanup_callable)
        return

    p = phase_diff(manifest_path=manifest_path, workdir=workdir)
    yield p

    if cleanup_callable is not None:
        yield phase_cleanup(cleanup_callable=cleanup_callable)
    else:
        yield Phase(
            name="cleanup",
            status="skipped",
            details={"reason": "no cleanup_callable supplied"},
        )
