"""Opt-in live proof check for ``keeper-vault-sharing.v1``.

This offline worker must not run Keeper or Commander. The parent live harness
can set ``KEEPER_LIVE_VAULT_SHARING_TRANSCRIPT`` to the sanitized transcript
captured from the second-account sharing proof, then this test validates that
artifact without printing secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from keeper_sdk.cli._live.transcript import secret_leak_check


@pytest.mark.live(requires=("KEEPER_LIVE_VAULT_SHARING_TRANSCRIPT",))
def test_vault_sharing_live_transcript_is_sanitized_and_complete() -> None:
    transcript = Path(os.environ["KEEPER_LIVE_VAULT_SHARING_TRANSCRIPT"]).expanduser()
    text = transcript.read_text(encoding="utf-8")

    leaks = secret_leak_check(
        text,
        env_keys=(
            "KEEPER_LIVE_ADMIN_KSM_RECORD_UID",
            "KEEPER_LIVE_LABSHARE_KSM_RECORD_UID",
            "KEEPER_LIVE_KSM_CONFIG",
            "KEEPER_LIVE_VAULT_SHARING_TRANSCRIPT",
        ),
    )

    lowered = text.lower()
    assert leaks == []
    assert "keeper-vault-sharing" in lowered
    assert "labshare" in lowered
    for phase in ("plan", "apply", "noop", "cleanup"):
        assert phase in lowered
