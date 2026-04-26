"""Live KSM bootstrap smoke (G3).

This test exercises the *real* `dsk bootstrap-ksm` flow against a real
Keeper tenant. It is the first live-proof test for the
`pam-environment.v1` schema family — when it produces a green
transcript, the schema's `x-keeper-live-proof.evidence` field gets
pointed at the transcript and the family graduates from
`preview-gated` to `supported` for the bootstrap phase.

Skipped unless:

  - KEEPER_LIVE_TENANT=1
  - KEEPER_LIVE_KSM_RECORD_UID set (UID of the bootstrap config record)
  - KEEPER_CONFIG set (path to commander config the bootstrap reads from)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from keeper_sdk.cli._live.runbook import phase_bootstrap, phase_login
from keeper_sdk.cli._live.transcript import Transcript, secret_leak_check


@pytest.mark.live(
    requires=("KEEPER_LIVE_KSM_RECORD_UID", "KEEPER_CONFIG"),
)
def test_ksm_bootstrap_then_session(tmp_path: Path) -> None:
    """Bootstrap a fresh KSM application then prove the session works."""
    record_uid = os.environ["KEEPER_LIVE_KSM_RECORD_UID"]
    transcript = Transcript(
        schema_family="pam-environment",
        schema_version="v1",
        commander_pin=_read_pin(),
    )

    bootstrap = phase_bootstrap(
        ksm_record_uid=record_uid,
        ksm_config_path=None,
        workdir=tmp_path,
    )
    transcript.add_phase(bootstrap)
    assert bootstrap.status == "ok", bootstrap.error or "bootstrap failed"

    # Empty manifest just to drive `validate --online` against a live tenant.
    (tmp_path / "_smoke_empty.yml").write_text("schema: pam-environment.v1\n")
    login = phase_login(helper_path=tmp_path / "ksm.config", workdir=tmp_path)
    transcript.add_phase(login)
    assert login.status == "ok", login.error or "login probe failed"

    transcript.finalize()
    out = tmp_path / "evidence.json"
    transcript.write(out)
    leaks = secret_leak_check(
        out.read_text(),
        env_keys=("KEEPER_CONFIG", "KEEPER_LIVE_KSM_RECORD_UID"),
    )
    assert leaks == [], f"sanitization leak: {leaks}"


def _read_pin() -> str:
    pin = Path(__file__).resolve().parents[2] / ".commander-pin"
    return pin.read_text().strip() if pin.exists() else "unknown"
