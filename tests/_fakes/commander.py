from __future__ import annotations

import json
from typing import Any


def fake_record_cache_entry(
    *,
    uid: str,
    title: str,
    record_type: str = "login",
    fields: list[dict[str, Any]] | None = None,
    custom: list[dict[str, Any]] | None = None,
    version: int = 3,
) -> dict[str, Any]:
    """Return the Commander record-cache shape used by bootstrap tests."""
    return {
        "record_uid": uid,
        "version": version,
        "record_key_unencrypted": b"fake-record-key",
        "data_unencrypted": json.dumps(
            {
                "type": record_type,
                "title": title,
                "fields": fields or [],
                "custom": custom or [],
            }
        ).encode("utf-8"),
    }


class FakeKeeperParams:
    """Minimal authenticated ``KeeperParams`` stand-in for bootstrap tests."""

    def __init__(self) -> None:
        self.record_cache: dict[str, dict[str, Any]] = {}
        self.session_token = "fake-session-token"
        self.server = "keepersecurity.com"
        self.sync_calls = 0

    def add_record(
        self,
        *,
        uid: str,
        title: str,
        record_type: str = "login",
        fields: list[dict[str, Any]] | None = None,
        custom: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add a normal vault record to the fake Commander cache."""
        self.record_cache[uid] = fake_record_cache_entry(
            uid=uid,
            title=title,
            record_type=record_type,
            fields=fields,
            custom=custom,
        )

    def add_app(self, *, uid: str, title: str) -> None:
        """Add a KSM application record to the fake Commander cache."""
        self.record_cache[uid] = fake_record_cache_entry(
            uid=uid,
            title=title,
            record_type="app",
            version=5,
        )


class FakeCommanderApi:
    """Small API object exposing only ``sync_down``."""

    @staticmethod
    def sync_down(params: FakeKeeperParams, record_types: bool = False) -> None:
        """Count sync calls without contacting Keeper."""
        _ = record_types
        params.sync_calls += 1


class FakeKsmCommand:
    """Commander KSM command fake with deterministic app and token creation."""

    add_app_calls: list[str] = []
    share_calls: list[dict[str, Any]] = []
    add_client_calls: list[dict[str, Any]] = []
    _app_counter = 0

    @classmethod
    def reset(cls) -> None:
        """Clear fake call history between tests."""
        cls.add_app_calls = []
        cls.share_calls = []
        cls.add_client_calls = []
        cls._app_counter = 0

    @staticmethod
    def get_app_record(params: FakeKeeperParams, app_name_or_uid: str) -> dict[str, Any] | None:
        """Find an application by title or UID in the fake cache."""
        for entry in params.record_cache.values():
            if entry.get("version") != 5:
                continue
            data = json.loads(entry["data_unencrypted"].decode("utf-8"))
            if entry.get("record_uid") == app_name_or_uid or data.get("title") == app_name_or_uid:
                return entry
        return None

    @classmethod
    def add_new_v5_app(
        cls,
        params: FakeKeeperParams,
        app_name: str,
        force_to_add: bool = False,
        format_type: str = "table",
    ) -> str | None:
        """Create a deterministic fake KSM application record."""
        _ = force_to_add
        cls.add_app_calls.append(app_name)
        if cls.get_app_record(params, app_name):
            if format_type == "json":
                return json.dumps(
                    {"error": f'Application with the same name "{app_name}" already exists.'}
                )
            return None
        cls._app_counter += 1
        app_uid = f"APP{cls._app_counter:09d}"
        params.add_app(uid=app_uid, title=app_name)
        if format_type == "json":
            return json.dumps({"app_name": app_name, "app_uid": app_uid})
        return None

    @classmethod
    def add_app_share(
        cls,
        params: FakeKeeperParams,
        secret_uids: list[str],
        app_name_or_uid: str,
        is_editable: bool,
    ) -> bool:
        """Record a fake app share operation."""
        if not cls.get_app_record(params, app_name_or_uid):
            raise ValueError("fake app not found")
        cls.share_calls.append(
            {
                "secret_uids": list(secret_uids),
                "app_name_or_uid": app_name_or_uid,
                "is_editable": is_editable,
            }
        )
        return True

    @classmethod
    def add_client(
        cls,
        params: FakeKeeperParams,
        app_name_or_uid: str,
        count: int,
        unlock_ip: bool,
        first_access_expire_on: int,
        access_expire_in_min: int | None,
        client_name: str | None = None,
        config_init: str | None = None,
        silent: bool = False,
        client_type: int = 1,
    ) -> list[dict[str, str]]:
        """Return a fake one-time token without printing it."""
        if not cls.get_app_record(params, app_name_or_uid):
            raise ValueError("fake app not found")
        cls.add_client_calls.append(
            {
                "app_name_or_uid": app_name_or_uid,
                "count": count,
                "unlock_ip": unlock_ip,
                "first_access_expire_on": first_access_expire_on,
                "access_expire_in_min": access_expire_in_min,
                "client_name": client_name,
                "config_init": config_init,
                "silent": silent,
                "client_type": client_type,
            }
        )
        return [{"oneTimeToken": "US:fake-bootstrap-token", "deviceToken": "fake-device"}]


class FakeRecordAddCommand:
    """Commander record-add fake with deterministic record UIDs."""

    calls: list[dict[str, Any]] = []
    _record_counter = 0

    @classmethod
    def reset(cls) -> None:
        """Clear fake record-add history between tests."""
        cls.calls = []
        cls._record_counter = 0

    def execute(self, params: FakeKeeperParams, **kwargs: Any) -> str:
        """Create a fake vault record from the JSON ``data`` argument."""
        data = json.loads(kwargs["data"])
        self.__class__.calls.append(data)
        self.__class__._record_counter += 1
        uid = f"REC{self.__class__._record_counter:09d}"
        params.add_record(
            uid=uid,
            title=data["title"],
            record_type=data["type"],
            fields=data.get("fields") or [],
            custom=data.get("custom") or [],
        )
        return uid
