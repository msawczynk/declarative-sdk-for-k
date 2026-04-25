from __future__ import annotations

import sys
from pathlib import Path

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import smoke  # noqa: E402


def test_parse_args_login_helper_default() -> None:
    args = smoke._parse_args([])
    assert args.login_helper == "deploy_watcher"


def test_parse_args_login_helper_env() -> None:
    args = smoke._parse_args(["--login-helper", "env"])
    assert args.login_helper == "env"
