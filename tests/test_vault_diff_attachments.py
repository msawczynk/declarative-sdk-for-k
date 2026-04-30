"""keeper-vault.v1 attachment sibling-block diff tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core import compute_vault_diff
from keeper_sdk.core.diff import Change, ChangeKind
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.vault_models import VaultManifestV1


def _manifest(*attachments: dict, records: list[dict] | None = None) -> VaultManifestV1:
    return VaultManifestV1.model_validate(
        {
            "schema": "keeper-vault.v1",
            "records": records or [],
            "attachments": list(attachments),
        }
    )


def _attachment(**overrides: object) -> dict:
    data = {
        "uid_ref": "att.alpha",
        "record_uid_ref": "rec.alpha",
        "source_path": "./attachments/runbook.pdf",
        "name": "runbook.pdf",
        "size": 128,
        "mime_type": "application/pdf",
        "content_hash": "hash-a",
    }
    data.update(overrides)
    return data


def _live_attachment(
    *,
    managed: bool = True,
    marker: dict | None = None,
    **overrides: object,
) -> dict:
    data = {
        "keeper_uid": "file-1",
        "uid_ref": "att.alpha",
        "record_uid_ref": "rec.alpha",
        "name": "runbook.pdf",
        "size": 128,
        "mime_type": "application/pdf",
        "content_hash": "hash-a",
    }
    data.update(overrides)
    if managed:
        data["marker"] = marker or encode_marker(
            uid_ref=str(data["uid_ref"]),
            manifest="demo",
            resource_type="attachment",
            parent_uid_ref=str(data["record_uid_ref"]),
        )
    elif marker is not None:
        data["marker"] = marker
    return data


def _only(changes: list[Change]) -> Change:
    assert len(changes) == 1
    return changes[0]


def test_attachment_diff_empty_manifest_and_live_has_no_changes() -> None:
    changes = compute_vault_diff(_manifest(), [], live_attachments=[])

    assert changes == []


def test_attachment_diff_adds_manifest_attachment_missing_from_live() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(_attachment()),
            [],
            manifest_name="demo",
            live_attachments=[],
        )
    )

    assert row.kind is ChangeKind.ADD
    assert row.uid_ref == "att.alpha"
    assert row.resource_type == "attachment"
    assert row.after["manifest_name"] == "demo"
    assert row.after["marker"]["manifest"] == "demo"


def test_attachment_diff_deletes_managed_live_attachment_when_allowed() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(),
            [],
            manifest_name="demo",
            allow_delete=True,
            live_attachments=[_live_attachment()],
        )
    )

    assert row.kind is ChangeKind.DELETE
    assert row.uid_ref == "att.alpha"
    assert row.before["manifest_name"] == "demo"


def test_attachment_diff_ignores_managed_orphan_without_allow_delete() -> None:
    changes = compute_vault_diff(
        _manifest(),
        [],
        manifest_name="demo",
        allow_delete=False,
        live_attachments=[_live_attachment()],
    )

    assert changes == []


def test_attachment_diff_updates_when_size_differs() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(_attachment(size=256)),
            [],
            manifest_name="demo",
            live_attachments=[_live_attachment(size=128)],
        )
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before == {"size": 128, "manifest_name": "demo"}
    assert row.after == {"size": 256, "manifest_name": "demo"}


def test_attachment_diff_updates_when_content_hash_differs() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(_attachment(content_hash="b" * 64)),
            [],
            manifest_name="demo",
            live_attachments=[_live_attachment(content_hash="a" * 64)],
        )
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before["content_hash"] == "a" * 64
    assert row.after["content_hash"] == "b" * 64


def test_attachment_diff_updates_when_mime_type_differs() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(_attachment(mime_type="text/plain")),
            [],
            manifest_name="demo",
            live_attachments=[_live_attachment(mime_type="application/pdf")],
        )
    )

    assert row.kind is ChangeKind.UPDATE
    assert row.before["mime_type"] == "application/pdf"
    assert row.after["mime_type"] == "text/plain"


def test_attachment_diff_missing_record_uid_ref_raises_value_error() -> None:
    attachment = _attachment()
    attachment.pop("record_uid_ref")

    with pytest.raises(ValueError, match="record_uid_ref"):
        compute_vault_diff(_manifest(attachment), [], live_attachments=[])


def test_attachment_diff_duplicate_record_and_name_in_manifest_raises_value_error() -> None:
    with pytest.raises(ValueError, match="duplicate attachment"):
        compute_vault_diff(
            _manifest(
                _attachment(uid_ref="att.one"),
                _attachment(uid_ref="att.two"),
            ),
            [],
            live_attachments=[],
        )


def test_attachment_diff_unmanaged_live_attachment_is_skip() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(),
            [],
            manifest_name="demo",
            live_attachments=[_live_attachment(managed=False)],
        )
    )

    assert row.kind is ChangeKind.SKIP
    assert row.reason == "unmanaged attachment"


def test_attachment_diff_preserves_record_level_changes_alongside_attachments() -> None:
    changes = compute_vault_diff(
        _manifest(
            _attachment(),
            records=[{"uid_ref": "rec.alpha", "type": "login", "title": "Alpha"}],
        ),
        [],
        manifest_name="demo",
        live_attachments=[],
    )

    assert [(c.kind, c.resource_type, c.uid_ref) for c in changes] == [
        (ChangeKind.CREATE, "login", "rec.alpha"),
        (ChangeKind.ADD, "attachment", "att.alpha"),
    ]


def test_attachment_diff_change_rows_carry_manifest_name() -> None:
    row = _only(
        compute_vault_diff(
            _manifest(_attachment()),
            [],
            manifest_name="custom-manifest",
            live_attachments=[],
        )
    )

    assert row.after["manifest_name"] == "custom-manifest"
    assert row.after["marker"]["manifest"] == "custom-manifest"
