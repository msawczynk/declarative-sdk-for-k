"""Unit tests for Commander → SDK managed-company row mapping."""

from __future__ import annotations

import pytest

from keeper_sdk.providers.commander_cli import _commander_mc_dict_to_sdk_row


def test_commander_row_maps_product_id_and_file_plan() -> None:
    row = {
        "mc_enterprise_name": "Acme Corp",
        "mc_enterprise_id": 42,
        "number_of_seats": 5,
        "product_id": 1,
        "file_plan_type": "STORAGE_100GB",
        "add_ons": [{"name": "chat", "seats": 0}],
    }
    out = _commander_mc_dict_to_sdk_row(row)
    assert out["name"] == "Acme Corp"
    assert out["plan"] == "business"
    assert out["seats"] == 5
    assert out["mc_enterprise_id"] == 42
    assert out["file_plan"] == "100GB"
    assert out["addons"] == [{"name": "chat", "seats": 0}]


def test_commander_row_unlimited_seats() -> None:
    row = {
        "mc_enterprise_name": "BigCo",
        "mc_enterprise_id": 1,
        "number_of_seats": 2147483647,
        "product_id": "enterprise",
        "file_plan_type": None,
        "add_ons": [],
    }
    out = _commander_mc_dict_to_sdk_row(row)
    assert out["seats"] == -1
    assert out["plan"] == "enterprise"


def test_commander_row_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        _commander_mc_dict_to_sdk_row(
            {
                "mc_enterprise_name": "  ",
                "product_id": 1,
                "number_of_seats": 1,
            }
        )
