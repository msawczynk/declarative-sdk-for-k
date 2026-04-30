from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest
from click.testing import CliRunner

from keeper_sdk.cli.main import main
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker
from keeper_sdk.core.planner import Plan
from keeper_sdk.providers.commander_service import CommanderServiceProvider
from keeper_sdk.providers.service_client import CommanderServiceClient


class FakeClient:
    def __init__(
        self,
        *,
        statuses: list[dict[str, Any]] | None = None,
        results: list[dict[str, Any]] | None = None,
    ) -> None:
        self.submits: list[tuple[str, dict[str, Any] | None]] = []
        self.statuses = statuses or [{"status": "completed"}]
        self.results = results or [{"status": "success"}]

    def _post_async(self, command: str, filedata: dict[str, Any] | None = None) -> str:
        self.submits.append((command, filedata))
        return f"req-{len(self.submits)}"

    def _poll_status(self, request_id: str, timeout: int | None = None) -> dict[str, Any]:
        assert request_id.startswith("req-")
        assert timeout == 300
        return self.statuses.pop(0)

    def _get_result(self, request_id: str) -> dict[str, Any]:
        assert request_id.startswith("req-")
        return self.results.pop(0)


def test_execute_submits_async_polls_and_returns_result() -> None:
    client = FakeClient(results=[{"status": "success", "stdout": '{"ok": true}'}])
    provider = CommanderServiceProvider(api_key="token", client=client)

    result = provider._execute("pam project list --format=json")

    assert result["stdout"] == '{"ok": true}'
    assert client.submits == [("pam project list --format=json", None)]


@pytest.mark.parametrize("status", ["failed", "expired"])
def test_execute_raises_capability_error_on_failed_or_expired(status: str) -> None:
    client = FakeClient(statuses=[{"status": status, "message": "boom"}])
    provider = CommanderServiceProvider(api_key="token", client=client)

    with pytest.raises(CapabilityError, match="boom"):
        provider._execute("pam project list --format=json")


def test_discover_parses_pam_project_list_stdout() -> None:
    marker = serialize_marker(
        encode_marker(uid_ref="res.db", manifest="m", resource_type="pamDatabase")
    )
    stdout = json.dumps(
        {
            "records": [
                {
                    "uid": "UID1",
                    "title": "prod-db",
                    "resource_type": "pamDatabase",
                    "host": "db.example.com",
                    "custom_fields": {MARKER_FIELD_LABEL: marker},
                }
            ]
        }
    )
    client = FakeClient(results=[{"status": "success", "stdout": stdout}])
    provider = CommanderServiceProvider(api_key="token", client=client)

    records = provider.discover()

    assert len(records) == 1
    assert records[0].keeper_uid == "UID1"
    assert records[0].title == "prod-db"
    assert records[0].resource_type == "pamDatabase"
    assert records[0].marker and records[0].marker["uid_ref"] == "res.db"


def test_discover_parses_nested_project_resources() -> None:
    client = FakeClient(
        results=[
            {
                "status": "success",
                "result": {
                    "projects": [
                        {
                            "name": "acme",
                            "pam_data": {
                                "resources": [
                                    {
                                        "record_uid": "UID2",
                                        "title": "machine",
                                        "type": "pamMachine",
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        ]
    )
    provider = CommanderServiceProvider(api_key="token", client=client)

    records = provider.discover()

    assert [(r.keeper_uid, r.resource_type, r.title) for r in records] == [
        ("UID2", "pamMachine", "machine")
    ]


def test_apply_plan_dry_run_skips_http_calls() -> None:
    client = FakeClient()
    provider = CommanderServiceProvider(api_key="token", client=client)
    plan = Plan(
        "m",
        [
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.machine",
                resource_type="pamMachine",
                title="machine",
                after={"title": "machine", "type": "pamMachine"},
            ),
            Change(
                kind=ChangeKind.UPDATE,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db",
                keeper_uid="UID3",
                after={"host": "db.example.com"},
            ),
            Change(
                kind=ChangeKind.DELETE,
                uid_ref="res.old",
                resource_type="pamDirectory",
                title="old",
                keeper_uid="UID4",
            ),
        ],
        ["res.machine", "res.db", "res.old"],
    )

    outcomes = provider.apply_plan(plan, dry_run=True)

    assert client.submits == []
    assert [o.action for o in outcomes] == ["create", "update", "delete"]
    assert all(o.details["dry_run"] for o in outcomes)


def test_apply_plan_create_uses_filedata_import() -> None:
    client = FakeClient(results=[{"status": "success", "uid": "NEWUID"}])
    provider = CommanderServiceProvider(api_key="token", client=client)
    plan = Plan(
        "acme",
        [
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db",
                after={"title": "db", "type": "pamDatabase", "host": "db.example.com"},
            )
        ],
        ["res.db"],
    )

    outcomes = provider.apply_plan(plan)

    assert outcomes[0].keeper_uid == "NEWUID"
    assert client.submits[0][0] == "pam project import --filename=FILEDATA"
    assert client.submits[0][1] == {
        "project": "acme",
        "pam_data": {
            "resources": [{"title": "db", "type": "pamDatabase", "host": "db.example.com"}]
        },
    }


def test_apply_plan_create_with_manifest_source_serializes_commander_project() -> None:
    source = {
        "name": "acme",
        "resources": [
            {
                "uid_ref": "res.db",
                "type": "pamDatabase",
                "title": "db",
                "host": "db.example.com",
            }
        ],
    }
    client = FakeClient(results=[{"status": "success"}])
    provider = CommanderServiceProvider(api_key="token", client=client, manifest_source=source)
    plan = Plan(
        "acme",
        [
            Change(
                kind=ChangeKind.CREATE,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db",
                after=source["resources"][0],
            )
        ],
        ["res.db"],
    )

    provider.apply_plan(plan)

    assert client.submits[0][1] == {
        "project": "acme",
        "pam_data": {
            "resources": [{"type": "pamDatabase", "title": "db", "host": "db.example.com"}]
        },
    }


def test_apply_plan_update_builds_edit_command() -> None:
    client = FakeClient(results=[{"status": "success"}])
    provider = CommanderServiceProvider(api_key="token", client=client)
    plan = Plan(
        "m",
        [
            Change(
                kind=ChangeKind.UPDATE,
                uid_ref="res.db",
                resource_type="pamDatabase",
                title="db",
                keeper_uid="UID3",
                after={"host": "db.example.com", "port": 3306, "title": "db"},
            )
        ],
        ["res.db"],
    )

    provider.apply_plan(plan)

    assert client.submits[0][0] == "pam database edit UID3 --host=db.example.com --port=3306"
    assert client.submits[0][1] is None


def test_apply_plan_delete_builds_delete_command() -> None:
    client = FakeClient(results=[{"status": "success"}])
    provider = CommanderServiceProvider(api_key="token", client=client)
    plan = Plan(
        "m",
        [
            Change(
                kind=ChangeKind.DELETE,
                uid_ref="res.old",
                resource_type="pamDirectory",
                title="old",
                keeper_uid="UID4",
            )
        ],
        ["res.old"],
    )

    provider.apply_plan(plan)

    assert client.submits[0][0] == "pam directory delete UID4"


def test_unsupported_capabilities_match_cli_detector() -> None:
    provider = CommanderServiceProvider(
        api_key="token",
        manifest_source={"gateways": [{"uid_ref": "gw.new", "name": "new", "mode": "create"}]},
    )

    gaps = provider.unsupported_capabilities()

    assert "mode: create is not implemented" in gaps[0]


def test_service_client_post_async_serializes_filedata(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str, dict[str, str]]] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"request_id":"REQ1"}'

    def fake_urlopen(request: Any, timeout: int) -> Response:
        seen.append((request.full_url, request.data.decode("utf-8"), dict(request.headers)))
        assert timeout == 300
        return Response()

    monkeypatch.setattr("keeper_sdk.providers.service_client.urllib.request.urlopen", fake_urlopen)

    client = CommanderServiceClient("http://svc", "token")
    request_id = client._post_async("pam project import --filename=FILEDATA", {"x": 1})

    assert request_id == "REQ1"
    assert seen[0][0] == "http://svc/api/v2/executecommand-async"
    assert json.loads(seen[0][1]) == {
        "command": "pam project import --filename=FILEDATA",
        "filedata": {"x": 1},
    }
    assert seen[0][2]["Api-key"] == "token"


def test_service_client_429_backs_off_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    sleeps: list[float] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"request_id":"REQ2"}'

    def fake_urlopen(_request: Any, timeout: int) -> Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError(
                url="http://svc/api/v2/executecommand-async",
                code=429,
                msg="rate limited",
                hdrs={"Retry-After": "0.25"},
                fp=None,
            )
        return Response()

    monkeypatch.setattr("keeper_sdk.providers.service_client.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("keeper_sdk.providers.service_client.time.sleep", sleeps.append)

    client = CommanderServiceClient("http://svc", "token")
    assert client._post_async("pam project list --format=json") == "REQ2"
    assert calls == 2
    assert sleeps == [0.25]


def test_service_client_poll_status_until_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = [{"status": "running"}, {"status": "completed"}]
    sleeps: list[float] = []
    client = CommanderServiceClient("http://svc", "token", poll_interval=0.1)

    def fake_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        assert method == "GET"
        assert path == "/api/v2/status/REQ3"
        return statuses.pop(0)

    monkeypatch.setattr(client, "_request_json", fake_request)
    monkeypatch.setattr("keeper_sdk.providers.service_client.time.sleep", sleeps.append)

    assert client._poll_status("REQ3") == {"status": "completed"}
    assert sleeps == [0.1]


def test_provider_wired_via_cli_provider_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    path = tmp_path / "env.yaml"
    path.write_text(
        """
version: "1"
name: svc-test
shared_folders:
  resources:
    uid_ref: sf.resources
    manage_users: true
    manage_records: true
    can_edit: true
    can_share: true
gateways:
  - uid_ref: gw.existing
    name: Existing Gateway
    mode: reference_existing
pam_configurations:
  - uid_ref: cfg.existing
    title: Existing Config
    environment: local
    gateway_uid_ref: gw.existing
resources:
  - uid_ref: res.db
    type: pamDatabase
    title: prod-db
    pam_configuration_uid_ref: cfg.existing
    shared_folder: resources
    database_type: mysql
    database_id: prod
    host: db.example.com
    port: "3306"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("KEEPER_SERVICE_API_KEY", "token")
    monkeypatch.setattr(
        CommanderServiceProvider,
        "discover",
        lambda self: [],
    )

    result = CliRunner().invoke(
        main,
        ["--provider", "service", "plan", str(path), "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["summary"]["create"] == 2
