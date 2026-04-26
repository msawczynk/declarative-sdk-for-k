"""CLI smoke tests."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from keeper_sdk.cli import main
from keeper_sdk.cli.main import (
    EXIT_CAPABILITY,
    EXIT_CHANGES,
    EXIT_CONFLICT,
    EXIT_GENERIC,
    EXIT_REF,
    EXIT_SCHEMA,
)
from keeper_sdk.core import build_graph, build_plan, compute_diff, execution_order, load_manifest
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.providers import MockProvider

cli_main_module = importlib.import_module("keeper_sdk.cli.main")


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False)


def test_validate_ok(minimal_manifest_path: Path) -> None:
    result = _run(["validate", str(minimal_manifest_path)])
    assert result.exit_code == 0, result.output
    assert "ok:" in result.output


def test_validate_rejects_missing_ref(invalid_manifest) -> None:
    path = invalid_manifest("missing-ref.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_REF


def test_validate_rejects_schema(invalid_manifest) -> None:
    path = invalid_manifest("rbi-rotation-on.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_SCHEMA


def test_validate_rejects_capability(invalid_manifest) -> None:
    path = invalid_manifest("gateway-create-in-unsupported-env.yaml")
    result = _run(["validate", str(path)])
    assert result.exit_code == EXIT_CAPABILITY


def test_validate_online_passes_with_mock_provider(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)
    provider.seed(
        [
            LiveRecord(
                keeper_uid="LIVE_GW_UID",
                title="Acme Lab Gateway",
                resource_type="gateway",
                payload={"name": "Acme Lab Gateway"},
                marker=None,
            )
        ]
    )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["validate", str(minimal_manifest_path), "--online"])
    assert result.exit_code == 0, result.output
    assert "online:" in result.output


def test_validate_online_warns_on_missing_gateway(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["validate", str(minimal_manifest_path), "--online"])
    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "stage 4" in result.output


def test_validate_online_fails_on_provider_capability_gap(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)

    class GapProvider(MockProvider):
        def unsupported_capabilities(self, manifest=None) -> list[str]:
            return ["rotation_settings requires pam rotation edit"]

    provider = GapProvider(manifest.name)
    provider.seed(
        [
            LiveRecord(
                keeper_uid="LIVE_GW_UID",
                title="Acme Lab Gateway",
                resource_type="gateway",
                payload={"name": "Acme Lab Gateway"},
                marker=None,
            )
        ]
    )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["validate", str(minimal_manifest_path), "--online"])
    assert result.exit_code == EXIT_CAPABILITY, result.output
    assert "capability gaps" in result.output
    assert "rotation_settings requires pam rotation edit" in result.output


def test_validate_without_online_unchanged(minimal_manifest_path: Path) -> None:
    result = _run(["validate", str(minimal_manifest_path)])
    assert result.exit_code == 0, result.output
    assert "online" not in result.output
    assert "stage" not in result.output


@pytest.mark.parametrize(
    ("scenario", "expected_exit"),
    [
        ("clean", 0),
        ("changes", EXIT_CHANGES),
        ("conflict", EXIT_CONFLICT),
    ],
)
def test_plan_emits_json_exit_codes(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_exit: int,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)

    if scenario == "clean":
        graph = build_graph(manifest)
        order = execution_order(graph)
        provider.apply_plan(
            build_plan(manifest.name, compute_diff(manifest, provider.discover()), order)
        )
    elif scenario == "conflict":
        provider.seed(
            [
                LiveRecord(
                    keeper_uid="LIVE_UID",
                    title="lab-linux-1",
                    resource_type="pamMachine",
                    marker={
                        **encode_marker(
                            uid_ref="acme-lab-linux1",
                            manifest=manifest.name,
                            resource_type="pamMachine",
                        ),
                        "manager": "someone-else",
                    },
                    payload={"title": "lab-linux-1"},
                )
            ]
        )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["plan", str(minimal_manifest_path), "--json"])
    assert result.exit_code == expected_exit, result.output
    doc = json.loads(result.output)
    assert doc["manifest_name"] == "acme-lab-minimal"
    if scenario == "clean":
        assert doc["summary"] == {"create": 0, "update": 0, "delete": 0, "conflict": 0, "noop": 3}
    elif scenario == "changes":
        assert doc["summary"]["create"] >= 1
        assert doc["summary"]["conflict"] == 0
    else:
        assert doc["summary"]["conflict"] >= 1


def test_apply_auto_approve(minimal_manifest_path: Path) -> None:
    result = _run(["apply", str(minimal_manifest_path), "--auto-approve"])
    assert result.exit_code == 0, result.output
    assert "create" in result.output.lower()


@pytest.mark.parametrize(
    ("seed_clean", "expected_exit"),
    [
        (False, EXIT_CHANGES),
        (True, 0),
    ],
)
def test_apply_dry_run_equivalent_to_plan(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seed_clean: bool,
    expected_exit: int,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)

    if seed_clean:
        graph = build_graph(manifest)
        order = execution_order(graph)
        provider.apply_plan(
            build_plan(manifest.name, compute_diff(manifest, provider.discover()), order)
        )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result_plan = _run(["plan", str(minimal_manifest_path)])
    assert result_plan.exit_code == expected_exit, result_plan.output

    result_apply = _run(["apply", str(minimal_manifest_path), "--dry-run"])
    assert result_apply.exit_code == expected_exit, result_apply.output
    assert result_plan.output == result_apply.output


def test_import_adopts_unmanaged_title_match(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)
    provider.seed(
        [
            LiveRecord(
                keeper_uid="LIVE_UID",
                title="lab-linux-1",
                resource_type="pamMachine",
                payload={"title": "lab-linux-1", "host": "10.16.9.10"},
                marker=None,
            )
        ]
    )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["import", str(minimal_manifest_path), "--auto-approve"])
    assert result.exit_code == 0, result.output

    adopted = next(record for record in provider.discover() if record.keeper_uid == "LIVE_UID")
    assert adopted.marker is not None
    assert adopted.marker["uid_ref"] == "acme-lab-linux1"
    assert adopted.marker["manifest"] == manifest.name


def test_import_noop_when_nothing_to_adopt(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)
    graph = build_graph(manifest)
    order = execution_order(graph)
    provider.apply_plan(
        build_plan(manifest.name, compute_diff(manifest, provider.discover()), order)
    )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["import", str(minimal_manifest_path), "--auto-approve"])
    assert result.exit_code == 0, result.output
    assert "no records to adopt." in result.output


def test_import_dry_run_does_not_mutate(
    minimal_manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_manifest(minimal_manifest_path)
    provider = MockProvider(manifest.name)
    provider.seed(
        [
            LiveRecord(
                keeper_uid="LIVE_UID",
                title="lab-linux-1",
                resource_type="pamMachine",
                payload={"title": "lab-linux-1", "host": "10.16.9.10"},
                marker=None,
            )
        ]
    )

    monkeypatch.setattr(cli_main_module, "MockProvider", lambda manifest_name: provider)

    result = _run(["import", str(minimal_manifest_path), "--dry-run"])
    assert result.exit_code == 0, result.output

    live = next(record for record in provider.discover() if record.keeper_uid == "LIVE_UID")
    assert live.marker is None


def test_report_password_report_emits_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [{"record_uid": "AbCdEfGhIjKlMnOpQrSt", "title": "svc", "length": 8}]

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps(sample)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "password-report", "--policy", "8,0,0,0,0"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "password-report"
    assert payload["dsk_report_version"] == 1
    assert payload["rows"] == sample


def test_report_password_report_quiet_fingerprints_uid(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = "AbCdEfGhIjKlMnOpQrSt"
    sample = [{"record_uid": uid, "title": "svc", "length": 8}]

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps(sample)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "password-report", "--policy", "8,0,0,0,0", "--quiet"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["rows"][0]["record_uid"] != uid
    assert payload["rows"][0]["record_uid"].startswith("<uid:")


def test_report_compliance_report_emits_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [{"record_uid": "ZzYyXxWwVvUuTtSsRrQq", "title": "row1"}]

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps(sample)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "compliance-report", "--quiet"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "compliance-report"
    assert payload["rows"][0]["record_uid"] != sample[0]["record_uid"]


def test_report_security_audit_report_emits_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [{"email": "a@example.com", "weak": 1}]

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps(sample)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "security-audit-report", "--node", "n1", "--force"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "security-audit-report"
    assert payload["meta"]["nodes"] == ["n1"]
    assert payload["rows"] == sample


def test_report_password_report_scrubs_secret_dict_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    sample = [{"record_uid": "ab", "title": "svc", "token": "should-not-appear"}]

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps(sample)

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "password-report", "--policy", "8,0,0,0,0"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    row = payload["rows"][0]
    assert row.get("token") == "<redacted>"
    assert row.get("title") == "svc"


def test_report_password_report_refuses_when_output_echoes_env_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "UniqueKeeperPassPhraseForLeakTest99"
    monkeypatch.setenv("KEEPER_PASSWORD", secret)

    def _fake_batch(*_a: object, **_k: object) -> str:
        return json.dumps([{"record_uid": "ab", "title": secret}])

    monkeypatch.setattr("keeper_sdk.cli._report.runner.run_keeper_batch", _fake_batch)

    result = _run(["report", "password-report", "--policy", "8,0,0,0,0"])
    assert result.exit_code == EXIT_GENERIC, result.output
    assert "refused" in result.output.lower() or "leak" in result.output.lower()
