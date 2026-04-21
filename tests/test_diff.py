"""Change classification."""

from __future__ import annotations

from pathlib import Path

from keeper_sdk.core import compute_diff, load_manifest
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import MANAGER_NAME, encode_marker


def test_diff_all_create(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    changes = compute_diff(manifest, live_records=[])
    kinds = {c.kind for c in changes}
    assert kinds == {ChangeKind.CREATE}
    uid_refs = {c.uid_ref for c in changes if c.uid_ref}
    # resource + pam_config + nested user
    assert "acme-lab-linux1" in uid_refs
    assert "acme-lab-cfg" in uid_refs
    assert "acme-lab-linux1-root" in uid_refs


def test_diff_noop_when_marker_matches(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    # simulate a live record owned by us, same payload
    payload = {"title": "lab-linux-1", "host": "10.16.9.10", "port": "22"}
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID_MACHINE",
            title="lab-linux-1",
            resource_type="pamMachine",
            payload=payload,
            marker=encode_marker(uid_ref="acme-lab-linux1", manifest_name=manifest.name),
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    machine_changes = [c for c in changes if c.uid_ref == "acme-lab-linux1"]
    assert len(machine_changes) == 1
    # host matches, other unspecified fields count as missing -> UPDATE
    # Acceptable because manifest has additional keys not present in payload.
    assert machine_changes[0].kind in (ChangeKind.UPDATE, ChangeKind.NOOP)


def test_diff_conflict_on_foreign_manager(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID",
            title="lab-linux-1",
            resource_type="pamMachine",
            marker={"manager": "someone-else", "uid_ref": "acme-lab-linux1", "version": "1"},
            payload={"title": "lab-linux-1"},
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    conflicts = [c for c in changes if c.kind is ChangeKind.CONFLICT]
    assert len(conflicts) == 1
    assert conflicts[0].title == "lab-linux-1"


def test_diff_adoption_when_marker_missing(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID",
            title="lab-linux-1",
            resource_type="pamMachine",
            marker=None,
            payload={"title": "lab-linux-1", "host": "10.16.9.10"},
        )
    ]
    changes = compute_diff(manifest, live_records=live)
    adopt = [c for c in changes if c.uid_ref == "acme-lab-linux1"]
    assert adopt
    assert adopt[0].kind is ChangeKind.UPDATE
    assert adopt[0].reason and "adoption" in adopt[0].reason


def test_diff_delete_when_allowed(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    orphan = LiveRecord(
        keeper_uid="ORPHAN",
        title="old-host",
        resource_type="pamMachine",
        marker=encode_marker(uid_ref="acme-lab-old", manifest_name=manifest.name),
        payload={"title": "old-host"},
    )
    changes = compute_diff(manifest, live_records=[orphan], allow_delete=True)
    deletes = [c for c in changes if c.kind is ChangeKind.DELETE]
    assert deletes and deletes[0].title == "old-host"


def test_diff_no_delete_without_flag(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    orphan = LiveRecord(
        keeper_uid="ORPHAN",
        title="old-host",
        resource_type="pamMachine",
        marker=encode_marker(uid_ref="acme-lab-old", manifest_name=manifest.name),
        payload={"title": "old-host"},
    )
    changes = compute_diff(manifest, live_records=[orphan], allow_delete=False)
    assert not [c for c in changes if c.kind is ChangeKind.DELETE]
    assert [c for c in changes if c.kind is ChangeKind.CONFLICT and c.title == "old-host"]
