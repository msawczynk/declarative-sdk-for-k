"""Direct tests for Commander CLI helper edge cases."""

from __future__ import annotations

import pytest

from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.core.metadata import MARKER_FIELD_LABEL, encode_marker, serialize_marker
from keeper_sdk.providers._commander_cli_helpers import (
    _canonical_payload_from_field,
    _entry_uid_by_name,
    _extract_marker_field,
    _kind_from_collection,
    _load_json,
    _merge_pam_remote_browser_from_get_payload,
    _pam_configuration_uid_ref,
    _parse_pam_project_args,
    _payload_for_extend,
    _payload_from_get,
    _record_from_get,
    _resource_type_from_get,
    _type_from_listing_details,
)


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        (
            [
                "--dry-run",
                "--name=Lab",
                "--file",
                "pam.json",
                "--config=/tmp/keeper.json",
            ],
            {
                "dry_run": True,
                "name": "Lab",
                "file": "pam.json",
                "config": "/tmp/keeper.json",
            },
        ),
        (
            ["-d", "-n", "Lab", "-f", "pam.json", "-c", "/tmp/keeper.json"],
            {
                "dry_run": True,
                "name": "Lab",
                "file": "pam.json",
                "config": "/tmp/keeper.json",
            },
        ),
    ],
)
def test_parse_pam_project_args_accepts_flag_forms(
    tail: list[str], expected: dict[str, object]
) -> None:
    assert _parse_pam_project_args(tail) == expected


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"pam_configurations": []},
        {"pam_configurations": "not-a-list"},
        {"pam_configurations": ["not-a-dict"]},
        {"pam_configurations": [{"uid_ref": "  "}]},
    ],
)
def test_pam_configuration_uid_ref_returns_none_for_unusable_shapes(
    manifest: dict[str, object],
) -> None:
    assert _pam_configuration_uid_ref(manifest) is None


def test_payload_for_extend_skips_non_dict_resources_and_sets_user_folders() -> None:
    payload = {
        "pam_data": {
            "resources": [
                "not-a-resource",
                {"title": "db", "users": [{"username": "admin"}, "not-a-user"]},
            ],
            "users": [{"username": "standalone"}, "not-a-user"],
        }
    }

    out = _payload_for_extend(
        payload,
        resources_folder_name="Resources",
        users_folder_name="Users",
    )

    resource = out["pam_data"]["resources"][1]
    assert resource["folder_path"] == "Resources"
    assert resource["users"][0]["folder_path"] == "Users"
    assert out["pam_data"]["users"][0]["folder_path"] == "Users"
    assert "folder_path" not in payload["pam_data"]["resources"][1]


def test_load_json_empty_payload_is_empty_list() -> None:
    assert _load_json(" \n\t", command="ls --format json") == []


def test_load_json_rejects_malformed_json() -> None:
    with pytest.raises(CapabilityError) as exc_info:
        _load_json("{", command="ls --format json")

    assert "non-JSON" in exc_info.value.reason


def test_entry_uid_by_name_rejects_non_array_json() -> None:
    with pytest.raises(CapabilityError) as exc_info:
        _entry_uid_by_name({"name": "Resources"}, "Resources")

    assert "non-array JSON" in exc_info.value.reason


def test_entry_uid_by_name_skips_non_dict_entries_and_accepts_uid_aliases() -> None:
    entries = [
        "not-an-entry",
        {"title": "Resources", "shared_folder_uid": "sf-uid"},
    ]

    assert _entry_uid_by_name(entries, "Resources") == "sf-uid"


def test_payload_from_get_skips_non_dict_field_blocks() -> None:
    payload = _payload_from_get(
        {
            "record_uid": "record-uid",
            "fields": [
                "not-a-field",
                {"type": "text", "label": "providerGroup", "value": ["admins"]},
            ],
            "custom": [
                "not-a-field",
                {"type": "text", "label": "instanceId", "value": ["i-123"]},
            ],
        }
    )

    assert "record_uid" not in payload
    assert payload["provider_group"] == "admins"
    assert payload["instance_id"] == "i-123"


@pytest.mark.parametrize(
    "field",
    [
        {},
        {"type": "text", "value": "not-a-list"},
        {"type": "text", "label": "empty", "value": []},
        {"type": "pamRemoteBrowserSettings", "value": ["not-a-dict"]},
        {"type": "text", "label": "nested", "value": [{"not": "scalar"}]},
        {"type": "host", "value": ["not-a-host-object"]},
    ],
)
def test_canonical_payload_from_field_returns_empty_for_unsupported_shapes(
    field: dict[str, object],
) -> None:
    assert _canonical_payload_from_field(field) == {}


def test_merge_pam_remote_browser_settings_ignores_bad_connection_shape() -> None:
    payload = {"pamRemoteBrowserSettings": {"connection": []}}

    _merge_pam_remote_browser_from_get_payload(payload)

    assert "pam_settings" not in payload


def test_merge_pam_remote_browser_settings_skips_empty_connection_values() -> None:
    payload = {
        "pamRemoteBrowserSettings": {
            "connection": {
                "protocol": "",
                "ignoreInitialSslCert": None,
                "disableCopy": False,
            }
        }
    }

    _merge_pam_remote_browser_from_get_payload(payload)

    assert payload["pam_settings"]["connection"] == {"disable_copy": False}


def test_record_from_get_returns_none_without_keeper_uid() -> None:
    assert _record_from_get({}, listing_entry={}) is None


def test_record_from_get_returns_none_without_resource_type() -> None:
    item = {"record_uid": "record-uid", "title": "orphan"}

    assert _record_from_get(item, listing_entry={"details": "Name: orphan"}) is None


def test_record_from_get_marks_empty_title_and_collection_fallback() -> None:
    marker = encode_marker(uid_ref="user.admin", manifest="lab", resource_type="pamUser")
    raw_marker = serialize_marker(marker)
    item = {
        "uid": "record-uid",
        "collection": "users",
        "custom_fields": {MARKER_FIELD_LABEL: [raw_marker]},
    }

    record = _record_from_get(item, listing_entry={"folder_uid": "folder-uid"})

    assert record is not None
    assert record.title == ""
    assert record.resource_type == "pamUser"
    assert record.payload["_note"] == "empty title"
    assert record.payload["_legacy_type_fallback"] is True
    assert record.marker == marker


def test_resource_type_helpers_cover_listing_and_collection_fallbacks() -> None:
    assert _type_from_listing_details(None) is None
    assert _type_from_listing_details("Type: ") is None
    assert _kind_from_collection("missing") is None
    assert _resource_type_from_get(
        {},
        listing_entry={"details": "Type: pamMachine, shared folder"},
    ) == ("pamMachine", False)

    item = {"collection": "gateways"}

    assert _resource_type_from_get(item, listing_entry={"details": "Name: Gateway"}) == (
        "gateway",
        True,
    )
    assert item["type"] == "gateway"


def test_extract_marker_field_handles_dict_and_list_shapes() -> None:
    raw_marker = serialize_marker(
        encode_marker(uid_ref="res.db", manifest="lab", resource_type="pamDatabase")
    )

    assert _extract_marker_field({"custom_fields": {MARKER_FIELD_LABEL: raw_marker}}) == raw_marker
    assert (
        _extract_marker_field({"custom_fields": {MARKER_FIELD_LABEL: [raw_marker]}}) == raw_marker
    )
    assert (
        _extract_marker_field(
            {
                "custom": [
                    "not-a-field",
                    {"name": MARKER_FIELD_LABEL, "value": raw_marker},
                ]
            }
        )
        == raw_marker
    )
