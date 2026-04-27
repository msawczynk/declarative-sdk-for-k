"""keeper-vault.v1 KeeperFill sibling-block diff."""

from __future__ import annotations

from typing import Any

import pytest

from keeper_sdk.core import compute_vault_diff
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker
from keeper_sdk.core.vault_models import VaultManifestV1, VaultRecord


def _manifest(keeper_fill: dict[str, Any] | None = None) -> VaultManifestV1:
    return VaultManifestV1(keeper_fill=keeper_fill)


def _record_manifest(keeper_fill: dict[str, Any] | None = None) -> VaultManifestV1:
    return VaultManifestV1(
        records=[
            VaultRecord(
                uid_ref="vault.login.alpha",
                type="login",
                title="Alpha",
                fields=[{"type": "login", "label": "Login", "value": ["u"]}],
            )
        ],
        keeper_fill=keeper_fill,
    )


def _setting(
    record_uid_ref: str = "rec.web-admin",
    *,
    auto_fill: str = "on",
    auto_submit: str = "off",
) -> dict[str, Any]:
    return {
        "record_uid_ref": record_uid_ref,
        "auto_fill": auto_fill,
        "auto_submit": auto_submit,
    }


def _domain_setting(
    domain: str = "example.com",
    *,
    scope: str = "enterprise",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "scope": scope,
        "policy": policy or {"auto_fill": "on", "auto_submit": "off"},
    }


def _keeper_fill(*settings: dict[str, Any]) -> dict[str, Any]:
    return {"settings": list(settings)}


def _marker(manifest_name: str = "demo") -> dict[str, Any]:
    return encode_marker(
        uid_ref="keeper_fill:tenant",
        manifest=manifest_name,
        resource_type="keeper_fill",
    )


def _live(
    *settings: dict[str, Any],
    marker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"keeper_uid": "kf-uid", "settings": list(settings)}
    if marker is not None:
        out["marker"] = marker
    return out


def _live_custom_marker(*settings: dict[str, Any]) -> dict[str, Any]:
    marker = _marker()
    return {
        "keeper_uid": "kf-uid",
        "settings": list(settings),
        "custom": [
            {
                "type": "text",
                "label": MARKER_FIELD_LABEL,
                "value": [serialize_marker(marker)],
            }
        ],
    }


def test_keeper_fill_both_none_no_changes() -> None:
    changes = compute_vault_diff(_manifest(), [], live_keeper_fill={})

    assert changes == []


def test_keeper_fill_manifest_set_live_none_adds_whole_block() -> None:
    manifest = _manifest(_keeper_fill(_setting()))

    changes = compute_vault_diff(manifest, [], manifest_name="demo")

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].uid_ref == "keeper_fill:tenant"
    assert changes[0].resource_type == "keeper_fill"


def test_keeper_fill_live_marked_manifest_none_deletes_with_allow_delete() -> None:
    live = _live(_setting(), marker=_marker())

    changes = compute_vault_diff(
        _manifest(),
        [],
        manifest_name="demo",
        allow_delete=True,
        live_keeper_fill=live,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE
    assert changes[0].uid_ref == "keeper_fill:tenant"


def test_keeper_fill_same_settings_no_changes_with_custom_marker() -> None:
    setting = _setting()

    changes = compute_vault_diff(
        _manifest(_keeper_fill(setting)),
        [],
        manifest_name="demo",
        live_keeper_fill=_live_custom_marker(setting),
    )

    assert changes == []


def test_keeper_fill_policy_drift_updates_setting() -> None:
    manifest = _manifest(
        _keeper_fill(_domain_setting(policy={"auto_fill": "on", "auto_submit": "off"}))
    )
    live = _live(
        _domain_setting(policy={"auto_fill": "off", "auto_submit": "off"}),
        marker=_marker(),
    )

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_keeper_fill=live)

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].resource_type == "keeper_fill_setting"
    assert changes[0].title == "example.com"
    assert changes[0].after == {"policy": {"auto_fill": "on", "auto_submit": "off"}}


def test_keeper_fill_scope_drift_updates_setting() -> None:
    manifest = _manifest(_keeper_fill(_domain_setting(scope="enterprise")))
    live = _live(_domain_setting(scope="team"), marker=_marker())

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_keeper_fill=live)

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.UPDATE
    assert changes[0].after == {"scope": "enterprise"}


def test_keeper_fill_new_manifest_setting_adds_setting_row() -> None:
    manifest = _manifest(_keeper_fill(_setting("rec.a"), _setting("rec.b")))
    live = _live(_setting("rec.a"), marker=_marker())

    changes = compute_vault_diff(manifest, [], manifest_name="demo", live_keeper_fill=live)

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.ADD
    assert changes[0].uid_ref == "keeper_fill:tenant:rec.b"
    assert changes[0].after == _setting("rec.b")


def test_keeper_fill_removed_live_setting_deletes_with_allow_delete() -> None:
    manifest = _manifest(_keeper_fill(_setting("rec.a")))
    live = _live(_setting("rec.a"), _setting("rec.b"), marker=_marker())

    changes = compute_vault_diff(
        manifest,
        [],
        manifest_name="demo",
        allow_delete=True,
        live_keeper_fill=live,
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DELETE
    assert changes[0].uid_ref == "keeper_fill:tenant:rec.b"
    assert changes[0].before == _setting("rec.b")


def test_keeper_fill_live_unmanaged_skips() -> None:
    changes = compute_vault_diff(
        _manifest(_keeper_fill(_setting())),
        [],
        manifest_name="demo",
        live_keeper_fill=_live(_setting()),
    )

    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.SKIP
    assert changes[0].reason == "unmanaged keeper_fill"


def test_keeper_fill_rows_include_manifest_name() -> None:
    changes = compute_vault_diff(
        _manifest(_keeper_fill(_setting())),
        [],
        manifest_name="tenant-demo",
    )

    assert len(changes) == 1
    assert changes[0].manifest_name == "tenant-demo"


def test_keeper_fill_preserves_record_level_changes_alongside() -> None:
    manifest = _record_manifest(_keeper_fill(_setting()))
    live_record = LiveRecord(
        keeper_uid="uid-1",
        title="Alpha",
        resource_type="login",
        payload={"type": "login", "title": "Alpha", "Login": "other-user"},
        marker=encode_marker(
            uid_ref="vault.login.alpha",
            manifest="demo",
            resource_type="login",
        ),
    )

    changes = compute_vault_diff(manifest, [live_record], manifest_name="demo")

    assert [change.kind for change in changes] == [ChangeKind.UPDATE, ChangeKind.ADD]
    assert [change.uid_ref for change in changes] == ["vault.login.alpha", "keeper_fill:tenant"]


def test_keeper_fill_duplicate_manifest_domain_raises_value_error() -> None:
    manifest = _manifest(
        _keeper_fill(_domain_setting("example.com"), _domain_setting("example.com"))
    )

    with pytest.raises(ValueError, match="example.com"):
        compute_vault_diff(
            manifest,
            [],
            manifest_name="demo",
            live_keeper_fill=_live(_domain_setting("example.com"), marker=_marker()),
        )
