"""Commander runtime-version feature gates."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from keeper_sdk.providers import commander_version


@pytest.fixture(autouse=True)
def _clear_version_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DSK_COMMANDER_V18", raising=False)
    commander_version.get_commander_version.cache_clear()
    yield
    commander_version.get_commander_version.cache_clear()


def test_v17_version_tuple_and_gate_false() -> None:
    with patch("importlib.metadata.version", return_value="17.2.16"):
        assert commander_version.get_commander_version() == (17, 2, 16)
        assert commander_version.v18_or_later() is False


def test_v18_version_tuple_and_gate_true() -> None:
    with patch("importlib.metadata.version", return_value="18.0.0"):
        assert commander_version.get_commander_version() == (18, 0, 0)
        assert commander_version.v18_or_later() is True


def test_version_parse_failure_returns_zero_tuple_and_gate_false() -> None:
    with patch("importlib.metadata.version", side_effect=ValueError("bad version")):
        assert commander_version.get_commander_version() == (0, 0, 0)
        assert commander_version.v18_or_later() is False


def test_env_override_enables_v18_with_v17_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSK_COMMANDER_V18", "1")
    with patch("importlib.metadata.version", return_value="17.2.16"):
        assert commander_version.v18_or_later() is True


def test_rotation_info_json_predicate() -> None:
    with patch("importlib.metadata.version", return_value="18.0.0"):
        assert commander_version.v18_rotation_info_json() is True


def test_sm_token_add_predicate() -> None:
    with patch("importlib.metadata.version", return_value="18.0.0"):
        assert commander_version.v18_sm_token_add() is True


def test_project_import_server_dedup_predicate() -> None:
    with patch("importlib.metadata.version", return_value="18.0.0"):
        assert commander_version.v18_project_import_server_dedup() is True


def test_project_export_native_predicate() -> None:
    with patch("importlib.metadata.version", return_value="18.0.0"):
        assert commander_version.v18_project_export_native() is True
