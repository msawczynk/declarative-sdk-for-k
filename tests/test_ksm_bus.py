from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from keeper_sdk.secrets import KsmSecretStore
from keeper_sdk.secrets.bus import KsmBus
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "ksm-config.json"
    path.write_text("{}", encoding="utf-8")
    return path


def _store(tmp_path: Path) -> KsmSecretStore:
    return KsmSecretStore(config_path=_config_file(tmp_path))


def test_put_creates_custom_field_and_get_reads_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    record = FakeRecord(uid=uid, custom=[])
    fake_ksm = install_fake_ksm_core(monkeypatch, {uid: record})
    saved: list[str] = []

    def save(self: Any, saved_record: FakeRecord) -> bool:
        _ = self
        saved.append(saved_record.uid)
        return True

    monkeypatch.setattr(fake_ksm, "save", save, raising=False)
    bus = KsmBus(_store(tmp_path), uid)

    bus.put("phase7.status", "ready")

    assert bus.get("phase7.status") == "ready"
    assert record.dict["custom"] == [{"type": "text", "label": "phase7.status", "value": ["ready"]}]
    assert saved == [uid]


def test_put_updates_existing_custom_field_without_duplicate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    record = FakeRecord(
        uid=uid,
        custom=[
            {"type": "text", "label": "phase7.status", "value": ["starting"]},
            {"type": "text", "label": "other", "value": ["keep"]},
        ],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})
    bus = KsmBus(_store(tmp_path), uid)

    bus.put("phase7.status", "done")

    assert bus.get("phase7.status") == "done"
    assert record.dict["custom"] == [
        {"type": "text", "label": "phase7.status", "value": ["done"]},
        {"type": "text", "label": "other", "value": ["keep"]},
    ]


def test_get_missing_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "BUSUID123456"
    install_fake_ksm_core(
        monkeypatch,
        {uid: FakeRecord(uid=uid, custom=[{"type": "text", "label": "known", "value": ["v"]}])},
    )

    assert KsmBus(_store(tmp_path), uid).get("missing") is None


def test_missing_record_uid_keeps_not_implemented_fallback(tmp_path: Path) -> None:
    bus = KsmBus(_store(tmp_path), "")

    with pytest.raises(NotImplementedError, match="next_action"):
        bus.put("phase7.status", "ready")

    with pytest.raises(NotImplementedError, match="next_action"):
        bus.get("phase7.status")
