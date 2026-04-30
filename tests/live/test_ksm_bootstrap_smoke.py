"""Live KSM bootstrap smoke (G3).

This test exercises the *real* `dsk bootstrap-ksm` flow against a real
Keeper tenant. It is the first live-proof test for the
`pam-environment.v1` schema family — when it produces a green
transcript, the schema's `x-keeper-live-proof.evidence` field gets
pointed at the transcript and the family graduates from
`preview-gated` to `supported` for the bootstrap phase.

Skipped unless:

  - ``KEEPER_LIVE_TENANT=1``
  - ``KEEPER_LIVE_KSM_RECORD_UID`` — existing admin **login** record UID passed to
    ``dsk bootstrap-ksm --admin-record-uid``

**Auth (pick one):**

- **Recommended (CI / headless):** set ``KEEPER_LIVE_KSM_CONFIG`` to a
  ``ksm-config.json`` the SDK can read; the test runs
  ``bootstrap-ksm --login-helper ksm`` and exports ``KEEPER_SDK_KSM_CONFIG`` for
  the subprocess.
- **Local Commander session:** leave ``KEEPER_LIVE_KSM_CONFIG`` unset; the test
  uses ``--login-helper commander``, which needs an authenticated
  ``~/.keeper/config.json`` (a bare ``KEEPER_CONFIG`` in the **test** env is
  *not* wired into ``bootstrap-ksm`` for commander mode today).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from keeper_sdk.cli._live.runbook import phase_bootstrap, phase_login
from keeper_sdk.cli._live.transcript import Transcript, secret_leak_check


@pytest.mark.live(
    requires=("KEEPER_LIVE_KSM_RECORD_UID",),
)
def test_ksm_bootstrap_then_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bootstrap a fresh KSM application then prove the session works."""
    record_uid = os.environ["KEEPER_LIVE_KSM_RECORD_UID"]
    ksm_in = (os.environ.get("KEEPER_LIVE_KSM_CONFIG") or "").strip()
    if ksm_in:
        monkeypatch.setenv("KEEPER_SDK_KSM_CONFIG", ksm_in)
        # KsmLoginHelper (bootstrap --login-helper ksm) needs a creds record UID.
        monkeypatch.setenv(
            "KEEPER_SDK_KSM_CREDS_RECORD_UID",
            os.environ.get("KEEPER_LIVE_KSM_CREDS_RECORD_UID", record_uid),
        )
    bootstrap_kw: dict = {}
    if ksm_in:
        bootstrap_kw["login_helper"] = "ksm"
    else:
        bootstrap_kw["login_helper"] = "commander"

    transcript = Transcript(
        schema_family="pam-environment",
        schema_version="v1",
        commander_pin=_read_pin(),
    )

    bootstrap = phase_bootstrap(
        ksm_record_uid=record_uid,
        ksm_config_path=None,
        workdir=tmp_path,
        **bootstrap_kw,
    )
    transcript.add_phase(bootstrap)
    assert bootstrap.status == "ok", bootstrap.error or "bootstrap failed"

    # Minimal PAM manifest (version + name required) for `validate --online`.
    (tmp_path / "_smoke_empty.yml").write_text(
        "schema: pam-environment.v1\nversion: '1'\nname: live-ksm-bootstrap-probe\n"
    )
    login = phase_login(helper_path=tmp_path / "ksm.config", workdir=tmp_path)
    transcript.add_phase(login)
    assert login.status == "ok", login.error or "login probe failed"

    transcript.finalize()
    out = tmp_path / "evidence.json"
    transcript.write(out)
    leaks = secret_leak_check(
        out.read_text(),
        env_keys=(
            "KEEPER_CONFIG",
            "KEEPER_LIVE_KSM_RECORD_UID",
            "KEEPER_LIVE_KSM_CONFIG",
            "KEEPER_SDK_KSM_CONFIG",
        ),
    )
    assert leaks == [], f"sanitization leak: {leaks}"


def _read_pin() -> str:
    pin = Path(__file__).resolve().parents[2] / ".commander-pin"
    return pin.read_text().strip() if pin.exists() else "unknown"
