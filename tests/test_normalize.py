"""Alias canonicalization + pam_import round-trip."""

from __future__ import annotations

from pathlib import Path

from keeper_sdk.core import from_pam_import_json, load_manifest, to_pam_import_json
from keeper_sdk.core.normalize import canonicalize


def test_alias_rewrite() -> None:
    doc = {
        "resources": [
            {
                "hostname": "x",
                "pam_config": "cfg-a",
                "pam_settings": {
                    "connection": {
                        "administrative_credentials": "admin",
                    }
                },
            }
        ]
    }
    out = canonicalize(doc)
    resource = out["resources"][0]
    assert resource["host"] == "x"
    assert resource["pam_configuration_uid_ref"] == "cfg-a"
    assert resource["pam_settings"]["connection"]["administrative_credentials_uid_ref"] == "admin"


def test_canonicalize_is_idempotent_for_nested_aliases_and_extensions() -> None:
    doc = {
        "resources": [
            {
                "hostname": "db.internal",
                "pam_config_uid": "cfg.prod",
                "vendor_extension": {
                    "kept": True,
                    "items": [{"custom_key": "gw.prod"}],
                },
                "pam_settings": {
                    "connection": {
                        "launch_credentials": "usr.launch",
                        "sftp_resource": "res.sftp",
                    }
                },
            }
        ]
    }

    once = canonicalize(doc)
    twice = canonicalize(once)

    assert twice == once
    assert doc["resources"][0]["hostname"] == "db.internal"
    resource = once["resources"][0]
    assert "hostname" not in resource
    assert resource["host"] == "db.internal"
    assert resource["pam_configuration_uid_ref"] == "cfg.prod"
    assert resource["vendor_extension"] == {
        "kept": True,
        "items": [{"custom_key": "gw.prod"}],
    }
    connection = resource["pam_settings"]["connection"]
    assert connection["launch_credentials_uid_ref"] == "usr.launch"
    assert connection["sftp_resource_uid_ref"] == "res.sftp"


def test_to_pam_import_rewrites_refs_to_titles(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    doc = manifest.model_dump(mode="python", exclude_none=True)
    converted = to_pam_import_json(doc)

    resource = converted["pam_data"]["resources"][0]
    assert "uid_ref" not in resource
    assert resource["pam_configuration"] == "Acme Lab Local PAM Configuration"
    connection = resource["pam_settings"]["connection"]
    assert connection["administrative_credentials"] == "lab-linux-1-root"


def test_to_pam_import_rewrites_top_level_user_refs_and_additional_credentials() -> None:
    converted = to_pam_import_json(
        {
            "version": "1",
            "name": "top-level-users",
            "users": [
                {
                    "uid_ref": "usr.admin",
                    "type": "pamUser",
                    "title": "admin-user",
                    "login": "admin",
                },
                {
                    "uid_ref": "usr.blank-title",
                    "type": "pamUser",
                    "title": "",
                },
            ],
            "resources": [
                {
                    "uid_ref": "res.db",
                    "type": "pamDatabase",
                    "title": "database",
                    "additional_credentials_uid_refs": [
                        "usr.admin",
                        "usr.blank-title",
                        "usr.missing",
                        {"not": "a-ref"},
                    ],
                    "pam_settings": {
                        "connection": {
                            "launch_credentials_uid_ref": "usr.admin",
                        }
                    },
                }
            ],
        }
    )

    resource = converted["pam_data"]["resources"][0]
    assert "uid_ref" not in resource
    assert resource["additional_credentials"] == [
        "admin-user",
        "usr.blank-title",
        "usr.missing",
    ]
    assert resource["pam_settings"]["connection"]["launch_credentials"] == "admin-user"
    assert converted["pam_data"]["users"] == [
        {"type": "pamUser", "title": "admin-user", "login": "admin"},
        {"type": "pamUser", "title": ""},
    ]


def test_to_pam_import_preserves_top_metadata(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    doc = manifest.model_dump(mode="python", exclude_none=True)
    converted = to_pam_import_json(doc)
    assert converted["project"] == manifest.name
    assert "name" not in converted
    assert "pam_configuration" in converted
    assert "pam_data" in converted


def test_to_pam_import_preserves_nested_pam_users() -> None:
    doc = {
        "version": "1",
        "name": "nested-user-smoke",
        "resources": [
            {
                "uid_ref": "res.host",
                "type": "pamMachine",
                "title": "linux-host",
                "users": [
                    {
                        "uid_ref": "usr.local",
                        "type": "pamUser",
                        "title": "linux-local-user",
                        "login": "local-user",
                    }
                ],
            }
        ],
    }
    converted = to_pam_import_json(doc)

    resource = converted["pam_data"]["resources"][0]
    user = resource["users"][0]
    assert "uid_ref" not in resource
    assert "uid_ref" not in user
    assert user == {
        "type": "pamUser",
        "title": "linux-local-user",
        "login": "local-user",
    }


def test_from_pam_import_preserves_manifest_sections_and_assigns_missing_refs() -> None:
    lifted = from_pam_import_json(
        {
            "version": "1",
            "project": "native-shape",
            "projects": [{"name": "legacy-project"}],
            "shared_folders": {"resources": {"uid_ref": "sf.resources", "name": "Resource SF"}},
            "gateways": [
                {"name": "shared gateway"},
                {"name": "shared gateway", "mode": "create"},
            ],
            "pam_configurations": [
                {"title": "Primary PAM"},
                {"environment": "AWS"},
            ],
            "resources": [
                {
                    "type": "pamDatabase",
                    "title": "Primary DB",
                    "users": [{"type": "pamUser", "login": "root"}],
                }
            ],
            "users": [{"type": "pamUser", "title": "Global Admin"}],
        },
        name="lifted-native",
    )

    assert lifted["name"] == "lifted-native"
    assert lifted["projects"] == [{"name": "legacy-project"}]
    assert lifted["shared_folders"] == {
        "resources": {"uid_ref": "sf.resources", "name": "Resource SF"}
    }
    assert lifted["gateways"] == [
        {
            "name": "shared gateway",
            "uid_ref": "gw.shared-gateway",
            "mode": "reference_existing",
        },
        {
            "name": "shared gateway",
            "mode": "create",
            "uid_ref": "gw.shared-gateway-2",
        },
    ]
    assert [cfg["uid_ref"] for cfg in lifted["pam_configurations"]] == [
        "pc.primary-pam",
        "pc.aws",
    ]
    assert lifted["resources"][0]["uid_ref"] == "res.primary-db"
    assert lifted["resources"][0]["users"][0]["uid_ref"] == "usr.root"
    assert lifted["users"][0]["uid_ref"] == "usr.global-admin"


def test_from_pam_import_assigns_refs_to_pam_data_resource_users() -> None:
    lifted = from_pam_import_json(
        {
            "project": "commander-shape",
            "pam_data": {
                "resources": [
                    {
                        "type": "pamMachine",
                        "title": "Linux Host",
                        "users": [{"type": "pamUser", "login": "ec2-user"}],
                    }
                ]
            },
        }
    )

    assert lifted["resources"][0]["uid_ref"] == "res.linux-host"
    assert lifted["resources"][0]["users"][0]["uid_ref"] == "usr.ec2-user"
