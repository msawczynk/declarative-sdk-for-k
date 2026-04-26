from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

from keeper_sdk.core.errors import CapabilityError


class FakeRecord:
    """Small stand-in for a KSM record object used by unit tests."""

    def __init__(
        self,
        *,
        uid: str = "UID123456789",
        title: str = "Unit Test Record",
        fields: list[dict[str, Any]] | None = None,
        custom: list[dict[str, Any]] | None = None,
    ) -> None:
        self.uid = uid
        self.title = title
        self.dict = {
            "fields": fields or [],
            "custom": custom or [],
        }

    def field(self, field_type: str, *, single: bool = True) -> Any:
        """Return the first matching typed or custom field value."""
        for source in (self.dict["fields"], self.dict["custom"]):
            for entry in source:
                if entry.get("type") != field_type:
                    continue
                values = entry.get("value") or []
                return (values[0] if values else None) if single else values
        raise CapabilityError(
            reason=f"fake KSM record {self.uid[:6]}... has no field type={field_type!r}",
            next_action="verify the field exists on the record",
        )


class FakeFileKeyValueStorage:
    """Captures the config path passed to the KSM storage wrapper."""

    def __init__(self, path: str) -> None:
        self.path = path


class FakeSecretsManager:
    """Fake ``SecretsManager`` with class-level records for easy patching.

    ``get_secrets_calls`` lets tests assert how many fetch attempts the
    bootstrap verify loop made; ``visibility_delay`` simulates the
    add_app_share → KSM-client propagation race by hiding the records
    for the first N ``get_secrets`` calls.
    """

    records: dict[str, FakeRecord] = {}
    init_calls: list[Any] = []
    get_secrets_calls: int = 0
    visibility_delay: int = 0

    def __init__(self, *, config: Any, token: str | None = None, **kwargs: Any) -> None:
        _ = kwargs
        self.config = config
        self.__class__.init_calls.append({"config": config, "token_supplied": token is not None})
        if token is not None and getattr(config, "path", None):
            Path(config.path).write_text('{"fake":"ksm-config"}', encoding="utf-8")

    def get_secrets(self, uids: list[str]) -> list[FakeRecord]:
        cls = self.__class__
        cls.get_secrets_calls += 1
        if cls.get_secrets_calls <= cls.visibility_delay:
            return []
        return [self.records[uid] for uid in uids if uid in self.records]


def install_fake_ksm_core(
    monkeypatch: Any,
    records: dict[str, FakeRecord],
    *,
    visibility_delay: int = 0,
) -> type[FakeSecretsManager]:
    """Install fake KSM modules into ``sys.modules`` for one test."""
    FakeSecretsManager.records = dict(records)
    FakeSecretsManager.init_calls = []
    FakeSecretsManager.get_secrets_calls = 0
    FakeSecretsManager.visibility_delay = visibility_delay

    core = types.ModuleType("keeper_secrets_manager_core")
    core.SecretsManager = FakeSecretsManager
    storage = types.ModuleType("keeper_secrets_manager_core.storage")
    storage.FileKeyValueStorage = FakeFileKeyValueStorage

    monkeypatch.setitem(sys.modules, "keeper_secrets_manager_core", core)
    monkeypatch.setitem(sys.modules, "keeper_secrets_manager_core.storage", storage)
    return FakeSecretsManager
