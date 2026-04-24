"""Semantic rule validation tests."""

from __future__ import annotations

import pytest

from keeper_sdk.core.errors import SchemaError
from keeper_sdk.core.rules import apply_semantic_rules


def test_rule_resource_requires_pam_configuration_uid_ref_when_configs_exist() -> None:
    document = {
        "version": "1",
        "name": "t",
        "pam_configurations": [{"uid_ref": "cfg1"}],
        "resources": [{"uid_ref": "res1", "type": "pamMachine"}],
    }

    with pytest.raises(SchemaError) as exc_info:
        apply_semantic_rules(document)

    exc = exc_info.value
    assert (
        exc.reason
        == "resource 'res1' must set pam_configuration_uid_ref because "
        "pam_configurations are declared"
    )
    assert exc.uid_ref == "res1"
    assert exc.resource_type == "pamMachine"
    assert (
        exc.next_action
        == "set pam_configuration_uid_ref on the resource or remove all pam_configurations"
    )


def test_rule_resource_without_pam_configuration_allowed_when_no_configs() -> None:
    document = {
        "version": "1",
        "name": "t",
        "resources": [{"uid_ref": "res1", "type": "pamMachine"}],
    }

    apply_semantic_rules(document)


def test_rule_pam_remote_browser_cannot_have_jit_settings() -> None:
    document = {
        "version": "1",
        "name": "t",
        "resources": [
            {
                "uid_ref": "res1",
                "type": "pamRemoteBrowser",
                "pam_settings": {"options": {"jit_settings": {"enabled": True}}},
            }
        ],
    }

    with pytest.raises(SchemaError) as exc_info:
        apply_semantic_rules(document)

    exc = exc_info.value
    assert exc.reason == "pamRemoteBrowser does not support jit_settings"
    assert exc.uid_ref == "res1"
    assert exc.resource_type == "pamRemoteBrowser"
    assert exc.next_action == "remove jit_settings from pam_settings.options"


def test_rule_non_rotatable_cannot_have_rotation() -> None:
    document = {
        "version": "1",
        "name": "t",
        "resources": [
            {
                "uid_ref": "res1",
                "type": "pamUser",
                "pam_settings": {"options": {"rotation": "on"}},
            }
        ],
    }

    with pytest.raises(SchemaError) as exc_info:
        apply_semantic_rules(document)

    exc = exc_info.value
    assert exc.reason == "rotation is not supported for pamUser"
    assert exc.uid_ref == "res1"
    assert exc.resource_type == "pamUser"
    assert exc.next_action == "remove rotation from pam_settings.options"


def test_rule_pam_machine_can_have_rotation() -> None:
    document = {
        "version": "1",
        "name": "t",
        "resources": [
            {
                "uid_ref": "res1",
                "type": "pamMachine",
                "pam_settings": {"options": {"rotation": "on"}},
            }
        ],
    }

    apply_semantic_rules(document)
