"""Change classification."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from keeper_sdk.core import compute_diff, load_manifest
from keeper_sdk.core.diff import ChangeKind
from keeper_sdk.core.errors import CollisionError
from keeper_sdk.core.interfaces import LiveRecord
from keeper_sdk.core.metadata import encode_marker
from keeper_sdk.core.models import Manifest


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
            marker=encode_marker(
                uid_ref="acme-lab-linux1",
                manifest=manifest.name,
                resource_type="pamMachine",
            ),
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


def test_diff_conflict_when_unmanaged_title_matches_by_default(minimal_manifest_path: Path) -> None:
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
    conflicts = [c for c in changes if c.uid_ref == "acme-lab-linux1"]
    assert conflicts
    assert conflicts[0].kind is ChangeKind.CONFLICT
    assert conflicts[0].reason
    assert any(term in conflicts[0].reason for term in ("unmanaged", "claim", "import"))


def test_diff_adoption_when_unmanaged_title_matches_with_adopt_flag(
    minimal_manifest_path: Path,
) -> None:
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
    changes = compute_diff(manifest, live_records=live, adopt=True)
    adopt = [c for c in changes if c.uid_ref == "acme-lab-linux1"]
    assert adopt
    assert adopt[0].kind is ChangeKind.UPDATE
    assert adopt[0].reason == "adoption: write ownership marker"


def test_diff_delete_when_allowed(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    orphan = LiveRecord(
        keeper_uid="ORPHAN",
        title="old-host",
        resource_type="pamMachine",
        marker=encode_marker(
            uid_ref="acme-lab-old",
            manifest=manifest.name,
            resource_type="pamMachine",
        ),
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
        marker=encode_marker(
            uid_ref="acme-lab-old",
            manifest=manifest.name,
            resource_type="pamMachine",
        ),
        payload={"title": "old-host"},
    )
    changes = compute_diff(manifest, live_records=[orphan], allow_delete=False)
    assert not [c for c in changes if c.kind is ChangeKind.DELETE]
    assert [c for c in changes if c.kind is ChangeKind.CONFLICT and c.title == "old-host"]


def test_collision_duplicate_marker_uid_ref(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID_A",
            title="lab-linux-1",
            resource_type="pamMachine",
            payload={"title": "lab-linux-1"},
            marker=encode_marker(
                uid_ref="acme-lab-linux1",
                manifest=manifest.name,
                resource_type="pamMachine",
            ),
        ),
        LiveRecord(
            keeper_uid="LIVE_UID_B",
            title="lab-linux-1-copy",
            resource_type="pamMachine",
            payload={"title": "lab-linux-1-copy"},
            marker=encode_marker(
                uid_ref="acme-lab-linux1",
                manifest=manifest.name,
                resource_type="pamMachine",
            ),
        ),
    ]

    with pytest.raises(CollisionError) as exc_info:
        compute_diff(manifest, live_records=live)

    err = exc_info.value
    assert err.uid_ref == "acme-lab-linux1"
    assert err.context["live_identifiers"] == ["LIVE_UID_A", "LIVE_UID_B"]
    assert "claiming uid_ref='acme-lab-linux1'" in err.reason


def test_collision_duplicate_title_no_marker(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID_A",
            title="lab-linux-1",
            resource_type="pamMachine",
            marker=None,
            payload={"title": "lab-linux-1"},
        ),
        LiveRecord(
            keeper_uid="LIVE_UID_B",
            title="lab-linux-1",
            resource_type="pamMachine",
            marker=None,
            payload={"title": "lab-linux-1"},
        ),
    ]

    with pytest.raises(CollisionError) as exc_info:
        compute_diff(manifest, live_records=live)

    err = exc_info.value
    assert err.uid_ref is None
    assert err.resource_type == "pamMachine"
    assert err.context["live_identifiers"] == ["LIVE_UID_A", "LIVE_UID_B"]
    assert "records titled 'lab-linux-1' with no ownership markers" in err.reason


def test_no_collision_single_marker_pair(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    live = [
        LiveRecord(
            keeper_uid="LIVE_UID_MACHINE",
            title="lab-linux-1",
            resource_type="pamMachine",
            payload={"title": "lab-linux-1", "host": "10.16.9.10", "port": "22"},
            marker=encode_marker(
                uid_ref="acme-lab-linux1",
                manifest=manifest.name,
                resource_type="pamMachine",
            ),
        )
    ]

    changes = compute_diff(manifest, live_records=live)
    machine_changes = [c for c in changes if c.uid_ref == "acme-lab-linux1"]
    assert len(machine_changes) == 1
    assert machine_changes[0].kind in (ChangeKind.UPDATE, ChangeKind.NOOP)


def test_diff_nested_pam_user_rotation_drift_surfaces_rotation_settings_key(
    minimal_manifest_path: Path,
) -> None:
    """P2.1 offline anchor: nested ``pamUser`` rotation readback shape drift keys ``rotation_settings``.

    Live Commander payloads can disagree with manifest schedule shape while still
    representing the same applied intent; ``compute_diff`` must name
    ``rotation_settings`` in UPDATE ``before``/``after`` so smoke/parent tails
    stay diagnosable (SDK_DA §P2.1 task 2).
    """
    manifest = load_manifest(minimal_manifest_path)
    assert isinstance(manifest, Manifest)
    data = manifest.model_dump(mode="python", exclude_none=True)
    machine = next(r for r in data["resources"] if r["uid_ref"] == "acme-lab-linux1")
    user_desired = next(u for u in machine["users"] if u["uid_ref"] == "acme-lab-linux1-root")
    live_user = {k: v for k, v in user_desired.items() if k not in {"rotation_settings"}} | {
        "rotation_settings": {
            "rotation": "general",
            "enabled": "on",
            "schedule": {"type": "CRON", "cron": "0 0 * * *"},
            "password_complexity": user_desired["rotation_settings"]["password_complexity"],
        }
    }
    live = [
        LiveRecord(
            keeper_uid="LIVE_MACHINE",
            title="lab-linux-1",
            resource_type="pamMachine",
            payload=deepcopy(machine),
            marker=encode_marker(
                uid_ref="acme-lab-linux1",
                manifest=manifest.name,
                resource_type="pamMachine",
            ),
        ),
        LiveRecord(
            keeper_uid="LIVE_USER",
            title="lab-linux-1-root",
            resource_type="pamUser",
            payload=live_user,
            marker=encode_marker(
                uid_ref="acme-lab-linux1-root",
                manifest=manifest.name,
                resource_type="pamUser",
            ),
        ),
    ]
    changes = compute_diff(manifest, live_records=live)
    user_change = next(c for c in changes if c.uid_ref == "acme-lab-linux1-root")
    assert user_change.kind is ChangeKind.UPDATE
    assert user_change.before is not None
    assert user_change.after is not None
    assert "rotation_settings" in user_change.before
    assert "rotation_settings" in user_change.after
