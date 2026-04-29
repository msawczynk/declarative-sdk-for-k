from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.secrets import KsmSecretStore, load_keeper_login_from_ksm
from keeper_sdk.secrets import ksm as ksm_module
from keeper_sdk.secrets.ksm import _coerce_totp_secret
from tests._fakes.ksm import FakeRecord, install_fake_ksm_core


def _config_file(tmp_path: Path) -> Path:
    path = tmp_path / "ksm-config.json"
    path.write_text("{}", encoding="utf-8")
    return path


def test_config_path_explicit_path_returned_and_missing_raises(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)

    assert KsmSecretStore(config_path=config_path).config_path == config_path

    missing = tmp_path / "missing.json"
    with pytest.raises(CapabilityError) as exc_info:
        _ = KsmSecretStore(config_path=missing).config_path

    assert str(missing) in exc_info.value.reason
    assert exc_info.value.next_action is not None
    assert "KEEPER_SDK_KSM_CONFIG" in exc_info.value.next_action


def test_config_path_discovers_keeper_sdk_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    primary = _config_file(tmp_path)
    fallback = tmp_path / "ksm-fallback.json"
    fallback.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("KEEPER_SDK_KSM_CONFIG", str(primary))
    monkeypatch.setenv("KSM_CONFIG", str(fallback))

    assert KsmSecretStore().config_path == primary


def test_config_path_discovers_ksm_config_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _config_file(tmp_path)
    monkeypatch.delenv("KEEPER_SDK_KSM_CONFIG", raising=False)
    monkeypatch.setenv("KSM_CONFIG", str(config_path))

    assert KsmSecretStore().config_path == config_path


def test_config_path_discovers_default_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe = _config_file(tmp_path)
    monkeypatch.delenv("KEEPER_SDK_KSM_CONFIG", raising=False)
    monkeypatch.delenv("KSM_CONFIG", raising=False)
    monkeypatch.setattr(ksm_module, "DEFAULT_CONFIG_PROBES", (probe,))

    assert KsmSecretStore().config_path == probe


def test_field_reads_typed_and_labelled_custom_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "UID123456789"
    config_path = _config_file(tmp_path)
    record = FakeRecord(
        uid=uid,
        fields=[{"type": "login", "label": "", "value": ["operator@example.invalid"]}],
        custom=[
            {"type": "secret", "label": "database-password", "value": ["db-password"]},
            {"type": "secret", "label": "api-token", "value": ["api-token"]},
        ],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})
    store = KsmSecretStore(config_path=config_path)

    assert store.field(uid, "login") == "operator@example.invalid"
    assert store.field(uid, "secret", label="database-password") == "db-password"


def test_field_missing_field_and_record_raise_capability_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "UID123456789"
    config_path = _config_file(tmp_path)
    install_fake_ksm_core(monkeypatch, {uid: FakeRecord(uid=uid)})
    store = KsmSecretStore(config_path=config_path)

    with pytest.raises(CapabilityError):
        store.field(uid, "login")

    with pytest.raises(CapabilityError) as exc_info:
        store.field("MISSING123456", "login")

    assert "shared-folder grant" in exc_info.value.reason
    assert exc_info.value.next_action is not None


def test_describe_returns_shape_without_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "UID123456789"
    config_path = _config_file(tmp_path)
    record = FakeRecord(
        uid=uid,
        title="Login Record",
        fields=[
            {"type": "login", "label": "", "value": ["operator@example.invalid"]},
            {"type": "password", "label": "", "value": ["password-value"]},
        ],
        custom=[{"type": "secret", "label": "database-password", "value": ["db-password"]}],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})

    described = KsmSecretStore(config_path=config_path).describe(uid)

    assert described["uid_prefix"] == "UID123..."
    assert described["fields"][0] == {"type": "login", "label": "", "has_value": True}
    encoded = json.dumps(described)
    assert "operator@example.invalid" not in encoded
    assert "password-value" not in encoded
    assert "db-password" not in encoded


def test_lazy_import_does_not_crash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setitem(sys.modules, "keeper_secrets_manager_core", None)
    monkeypatch.setitem(sys.modules, "keeper_secrets_manager_core.storage", None)

    store = KsmSecretStore(config_path=_config_file(tmp_path))

    with pytest.raises(CapabilityError) as exc_info:
        store.client()

    assert exc_info.value.next_action is not None
    assert "pip install 'declarative-sdk-for-k[ksm]'" in exc_info.value.next_action


def test_coerce_totp_secret_base32_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH", raising=False)

    assert _coerce_totp_secret("JBSWY3DPEHPK3PXP") == "JBSWY3DPEHPK3PXP"


def test_coerce_totp_secret_extracts_otpauth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH", raising=False)

    assert (
        _coerce_totp_secret("otpauth://totp/SDK?secret=JBSWY3DPEHPK3PXP&issuer=Keeper")
        == "JBSWY3DPEHPK3PXP"
    )


def test_coerce_totp_secret_missing_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH", raising=False)

    with pytest.raises(CapabilityError):
        _coerce_totp_secret("otpauth://totp/SDK?issuer=Keeper")


def test_coerce_totp_secret_allows_otpauth_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uri = "otpauth://totp/SDK?secret=JBSWY3DPEHPK3PXP&issuer=Keeper"
    monkeypatch.setenv("KEEPER_SDK_KSM_ALLOW_OTPAUTH_PASSTHROUGH", "1")

    assert _coerce_totp_secret(uri) == uri


def test_load_keeper_login_from_ksm_returns_credential_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "UID123456789"
    config_path = _config_file(tmp_path)
    record = FakeRecord(
        uid=uid,
        fields=[
            {"type": "login", "label": "", "value": ["operator@example.invalid"]},
            {"type": "password", "label": "", "value": ["password-value"]},
            {
                "type": "oneTimeCode",
                "label": "",
                "value": ["otpauth://totp/SDK?secret=JBSWY3DPEHPK3PXP&issuer=Keeper"],
            },
        ],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})

    creds = load_keeper_login_from_ksm(
        uid,
        config_path=config_path,
        config_path_for_login="/tmp/keeper.json",
        server="keepersecurity.eu",
    )

    assert creds.email == "operator@example.invalid"
    assert creds.password == "password-value"
    assert creds.totp_secret == "JBSWY3DPEHPK3PXP"
    assert creds.config_path == "/tmp/keeper.json"
    assert creds.server == "keepersecurity.eu"


def test_load_keeper_login_from_ksm_missing_field_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    uid = "UID123456789"
    config_path = _config_file(tmp_path)
    record = FakeRecord(
        uid=uid,
        fields=[
            {"type": "login", "label": "", "value": ["operator@example.invalid"]},
            {"type": "password", "label": "", "value": ["password-value"]},
            {"type": "oneTimeCode", "label": "", "value": []},
        ],
    )
    install_fake_ksm_core(monkeypatch, {uid: record})

    with pytest.raises(CapabilityError):
        load_keeper_login_from_ksm(uid, config_path=config_path)
