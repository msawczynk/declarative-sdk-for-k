from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SMOKE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "smoke"
sys.path.insert(0, str(_SMOKE_DIR))

import smoke  # noqa: E402


def test_parse_args_login_helper_default() -> None:
    args = smoke._parse_args([])
    assert args.login_helper == "profile"
    assert args.profile == "default"
    assert args.node_uid is None


def test_parse_args_login_helper_env() -> None:
    args = smoke._parse_args(["--login-helper", "env"])
    assert args.login_helper == "env"


def test_parse_args_profile_and_node() -> None:
    args = smoke._parse_args(["--profile", "p1", "--node", "NODE123"])
    assert args.profile == "p1"
    assert args.node_uid == "NODE123"


def test_auth_path_message_names_public_env_helper() -> None:
    message = smoke._auth_path_message("env")

    assert "public EnvLoginHelper env path" in message
    assert "KEEPER_SDK_LOGIN_HELPER unset" in message
    assert "KEEPER_EMAIL" in message
    assert "KEEPER_TOTP_SECRET" in message


def test_auth_path_message_names_profile_helper() -> None:
    message = smoke._auth_path_message("profile", helper_path="/tmp/profile-helper.py")

    assert "profile helper path" in message
    assert "KEEPER_SDK_LOGIN_HELPER" in message
    assert "/tmp/profile-helper.py" in message


def test_auth_path_message_names_profile_ksm() -> None:
    message = smoke._auth_path_message("profile")

    assert "profile KSM record" in message
    assert "KEEPER_SDK_LOGIN_HELPER=ksm" in message


def test_sdk_error_preserves_command_exit_and_output_tails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        stdout = "\n".join(f"stdout line {idx}" for idx in range(45))
        stderr = "\n".join(f"stderr line {idx}" for idx in range(43))
        return subprocess.CompletedProcess(cmd, 7, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    with pytest.raises(smoke.SdkCommandError) as raised:
        smoke._sdk_allow([0], ["plan", "manifest.yaml"], env={"KEEPER_CONFIG": "cfg.json"})

    error = raised.value
    message = str(error)
    assert error.returncode == 7
    assert error.args_list == ["plan", "manifest.yaml"]
    assert error.command[-2:] == ["plan", "manifest.yaml"]
    assert "sdk command failed: exit_code=7" in message
    assert "command:" in message
    assert "keeper_sdk.cli" in message
    assert "stdout_tail:" in message
    assert "stderr_tail:" in message
    assert "stdout line 44" in message
    assert "stderr line 42" in message
    assert "stdout line 0" not in error.stdout_tail
    assert "stderr line 0" not in error.stderr_tail
    assert "... (5 line(s) omitted)" in error.stdout_tail
    assert "... (3 line(s) omitted)" in error.stderr_tail

    _, kwargs = calls[0]
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_sdk_constraint_error_preserves_failure_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            5,
            stdout="provider stdout",
            stderr="next_action: fix tenant role",
        )

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)

    with pytest.raises(smoke.TenantConstraintError) as raised:
        smoke._sdk_allow([0], ["apply", "--auto-approve", "manifest.yaml"], env={})

    message = str(raised.value)
    assert "sdk command reported tenant/provider constraint: exit_code=5" in message
    assert "command:" in message
    assert "provider stdout" in message
    assert "next_action: fix tenant role" in message


def test_cleanup_falls_back_to_sandbox_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_teardown_records(
        _admin_params: object,
        folder_uid: str,
        *,
        manager: str,
        sandbox: object | None = None,
    ) -> list[str]:
        calls.append(folder_uid)
        assert manager == smoke.MANAGER_NAME
        assert sandbox is smoke.sandbox.DEFAULT_SANDBOX_CONFIG
        if folder_uid == "stale-managed-folder":
            raise RuntimeError("No such folder or record")
        return ["removed-record"]

    monkeypatch.setattr(smoke.sandbox, "teardown_records", fake_teardown_records)

    removed = smoke._teardown_records_with_fallback(
        {
            "admin_params": object(),
            "managed_folder_uid": "stale-managed-folder",
            "sf_uid": "sandbox-folder",
        }
    )

    assert removed == ["removed-record"]
    assert calls == ["stale-managed-folder", "sandbox-folder"]


def test_cleanup_deduplicates_candidate_folder_uids() -> None:
    assert smoke._candidate_cleanup_folder_uids(
        {"managed_folder_uid": "same-folder", "sf_uid": "same-folder"}
    ) == ["same-folder"]


def test_sandbox_teardown_records_forces_marker_guarded_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def record_command(_params: object, command: str) -> str:
        calls.append(command)
        return ""

    monkeypatch.setattr(
        smoke.sandbox,
        "_list_folder_entries",
        lambda _params, _folder_uid: [{"type": "record", "uid": "REC1"}],
    )
    monkeypatch.setattr(
        smoke.sandbox,
        "_record_marker",
        lambda _params, _record_uid: {"manager": smoke.MANAGER_NAME},
    )
    monkeypatch.setattr(
        smoke.sandbox,
        "_do",
        record_command,
    )

    removed = smoke.sandbox.teardown_records(
        object(),
        "folder-uid",
        manager=smoke.MANAGER_NAME,
    )

    assert removed == ["REC1"]
    assert calls == ["rm --force REC1"]
