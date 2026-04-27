"""Unit tests for keeper batch report runner (subprocess + session retry)."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch  # noqa: F401 — audit F4 required import

import pytest

from keeper_sdk.core.errors import CapabilityError

_REPO = Path(__file__).resolve().parents[1]


def _load_runner_without_eager_cli() -> None:
    """Register lightweight ``keeper_sdk.cli*`` shims so ``runner`` import skips ``main``."""
    if "keeper_sdk.cli" in sys.modules and hasattr(sys.modules["keeper_sdk.cli"], "main"):
        return
    import keeper_sdk  # noqa: F401

    m_cli = types.ModuleType("keeper_sdk.cli")
    m_cli.__path__ = [str(_REPO / "keeper_sdk" / "cli")]
    m_cli.__package__ = "keeper_sdk.cli"
    sys.modules["keeper_sdk.cli"] = m_cli
    m_r = types.ModuleType("keeper_sdk.cli._report")
    m_r.__path__ = [str(_REPO / "keeper_sdk" / "cli" / "_report")]
    m_r.__package__ = "keeper_sdk.cli._report"
    sys.modules["keeper_sdk.cli._report"] = m_r


_load_runner_without_eager_cli()

from keeper_sdk.cli._report.runner import (  # noqa: E402
    _is_retryable_keeper_session_text,
    run_keeper_batch,
)


def test_run_keeper_batch_raises_when_keeper_not_on_path() -> None:
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value=None):
        with pytest.raises(CapabilityError, match="keeper CLI not found on PATH"):
            run_keeper_batch(["foo"], keeper_bin=None, config_file=None, password=None)


def test_run_keeper_batch_happy_path_returns_stripped_stdout() -> None:
    cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="  out  \n", stderr="")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/bin/keeper"):
        with patch("keeper_sdk.cli._report.runner.subprocess.run", return_value=cp) as m_run:
            out = run_keeper_batch(["x"], keeper_bin=None, config_file=None, password=None)
    assert out == "out"
    assert m_run.call_count == 1


def test_run_keeper_batch_adds_config_flag_when_config_file_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KEEPER_CONFIG", raising=False)
    cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/usr/bin/keeper"):
        with patch("keeper_sdk.cli._report.runner.subprocess.run", return_value=cp) as m:
            run_keeper_batch(
                ["p"],
                keeper_bin=None,
                config_file="/path/cfg.json",
                password=None,
            )
    cmd = m.call_args[0][0]
    assert cmd[:4] == ["keeper", "--batch-mode", "--config", "/path/cfg.json"]


def test_run_keeper_batch_adds_config_from_keeper_config_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEEPER_CONFIG", "/env/keeper.json")
    cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/k/keeper"):
        with patch("keeper_sdk.cli._report.runner.subprocess.run", return_value=cp) as m:
            run_keeper_batch(["p"], keeper_bin=None, config_file=None, password=None)
    cmd = m.call_args[0][0]
    assert "--config" in cmd
    assert "/env/keeper.json" in cmd


@pytest.mark.parametrize(
    ("password_kw", "env_pwd", "expected"),
    [
        ("direct", None, "direct"),
        (None, "fromenv", "fromenv"),
    ],
)
def test_run_keeper_batch_injects_keeper_password_into_subprocess_env(
    monkeypatch: pytest.MonkeyPatch,
    password_kw: str | None,
    env_pwd: str | None,
    expected: str,
) -> None:
    monkeypatch.delenv("KEEPER_PASSWORD", raising=False)
    if env_pwd:
        monkeypatch.setenv("KEEPER_PASSWORD", env_pwd)
    cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/k/keeper"):
        with patch("keeper_sdk.cli._report.runner.subprocess.run", return_value=cp) as m:
            run_keeper_batch(
                ["p"],
                keeper_bin=None,
                config_file=None,
                password=password_kw,
            )
    env_passed = m.call_args[1]["env"]
    assert env_passed["KEEPER_PASSWORD"] == expected


def test_run_keeper_batch_session_expired_retry_then_success() -> None:
    first = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="session_token_expired"
    )
    second = subprocess.CompletedProcess(args=[], returncode=0, stdout="  ok  \n", stderr="")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/k/keeper"):
        with patch(
            "keeper_sdk.cli._report.runner.subprocess.run",
            side_effect=[first, second],
        ) as m:
            out = run_keeper_batch(["r"], keeper_bin=None, config_file=None, password=None)
    assert out == "ok"
    assert m.call_count == 2


def test_run_keeper_batch_session_expired_retry_exhausted_raises() -> None:
    fail1 = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="session_token_expired"
    )
    fail2 = subprocess.CompletedProcess(args=[], returncode=1, stdout="out2", stderr="err2")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/k/keeper"):
        with patch(
            "keeper_sdk.cli._report.runner.subprocess.run",
            side_effect=[fail1, fail2],
        ) as m:
            with pytest.raises(CapabilityError) as ei:
                run_keeper_batch(["r"], keeper_bin=None, config_file=None, password=None)
    assert m.call_count == 2
    assert ei.value.context["stdout"] == "out2"
    assert ei.value.context["stderr"] == "err2"


def test_run_keeper_batch_non_retryable_rc_fails_without_second_attempt() -> None:
    bad = subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="some other failure")
    with patch("keeper_sdk.cli._report.runner.shutil.which", return_value="/k/keeper"):
        with patch("keeper_sdk.cli._report.runner.subprocess.run", return_value=bad) as m:
            with pytest.raises(CapabilityError, match=r"failed \(rc=2\)"):
                run_keeper_batch(["r"], keeper_bin=None, config_file=None, password=None)
    assert m.call_count == 1


def test_is_retryable_keeper_session_text_true_code() -> None:
    assert _is_retryable_keeper_session_text(None, "session_token_expired")


def test_is_retryable_keeper_session_text_true_phrase() -> None:
    assert _is_retryable_keeper_session_text("Session Token has expired", None)


def test_is_retryable_keeper_session_text_false() -> None:
    assert not _is_retryable_keeper_session_text("ok", "connection reset")
