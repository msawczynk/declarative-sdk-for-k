"""Tests for WorkflowSettings, SaasPluginConfig, and resource/user wiring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from keeper_sdk.core.models import PamMachine, PamUser, SaasPluginConfig, WorkflowSettings


def test_workflow_settings_parses_all_optional_fields_when_present() -> None:
    payload = {
        "approvals_needed": 2,
        "checkout_needed": True,
        "start_access_on_approval": True,
        "require_reason": True,
        "require_ticket": False,
        "require_mfa": True,
        "access_length": 90,
        "allowed_days": ["Mon", "Wed", "Fri", "Sun"],
        "allowed_from_time": "09:00",
        "allowed_to_time": "17:30",
        "allowed_timezone": "Europe/Berlin",
        "approver_uid_refs": ["appr1_uid_ref", "appr2_uid_ref"],
    }
    ws = WorkflowSettings.model_validate(payload)

    assert ws.approvals_needed == 2
    assert ws.checkout_needed is True
    assert ws.start_access_on_approval is True
    assert ws.require_reason is True
    assert ws.require_ticket is False
    assert ws.require_mfa is True
    assert ws.access_length == 90
    assert ws.allowed_days == ["Mon", "Wed", "Fri", "Sun"]
    assert ws.allowed_from_time == "09:00"
    assert ws.allowed_to_time == "17:30"
    assert ws.allowed_timezone == "Europe/Berlin"
    assert ws.approver_uid_refs == ["appr1_uid_ref", "appr2_uid_ref"]


def test_workflow_settings_minimal_empty_dict_and_constructors_accepted() -> None:
    empty = WorkflowSettings.model_validate({})
    assert WorkflowSettings.model_validate(empty.model_dump()) == empty

    default_ctor = WorkflowSettings()
    assert default_ctor.model_dump() == WorkflowSettings.model_validate({}).model_dump()


@pytest.mark.parametrize("bad_day", ["Monday", "mon", "", "FUN"])
def test_workflow_settings_allowed_days_rejects_invalid_literals(bad_day: str) -> None:
    with pytest.raises(ValidationError):
        WorkflowSettings.model_validate({"allowed_days": ["Mon", bad_day]})


@pytest.mark.parametrize("day", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
def test_workflow_settings_allowed_days_each_literal_accepted(day: str) -> None:
    ws = WorkflowSettings.model_validate({"allowed_days": [day]})
    assert ws.allowed_days == [day]


def test_pam_machine_workflow_settings_round_trips_via_model_dump_then_validate() -> None:
    machine = PamMachine.model_validate(
        {
            "uid_ref": "res.linux01",
            "type": "pamMachine",
            "title": "prod-web",
            "workflow_settings": {
                "approvals_needed": 1,
                "checkout_needed": True,
                "allowed_days": ["Tue", "Thu"],
                "allowed_from_time": "08:00",
                "allowed_to_time": "18:00",
                "allowed_timezone": "UTC",
                "approver_uid_refs": ["leader_uid"],
            },
        }
    )

    dumped = PamMachine.model_validate(machine.model_dump())
    assert dumped.workflow_settings == machine.workflow_settings
    assert dumped.model_dump() == machine.model_dump()


def test_pam_user_saas_plugins_happy_path_opaque_config() -> None:
    user = PamUser.model_validate(
        {
            "type": "pamUser",
            "title": "rotation-svc",
            "saas_plugins": [
                {
                    "plugin_name": "custom_saas",
                    "config": {"api_url": "https://x.example", "depth": {"n": 1}},
                }
            ],
        }
    )

    assert len(user.saas_plugins) == 1
    plug = user.saas_plugins[0]
    assert isinstance(plug, SaasPluginConfig)
    assert plug.plugin_name == "custom_saas"
    assert plug.config == {"api_url": "https://x.example", "depth": {"n": 1}}


def test_pam_user_saas_plugins_defaults_to_empty_list_when_omitted() -> None:
    user = PamUser.model_validate({"type": "pamUser", "title": "plain-user"})
    assert user.saas_plugins == []


def test_saas_plugin_config_config_defaults_to_empty_dict_when_omitted() -> None:
    plug = SaasPluginConfig.model_validate({"plugin_name": "minimal"})
    assert plug.config == {}
