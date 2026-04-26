"""JSON Schema + semantic-rule validation."""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

import keeper_sdk.core.schema as schema_module
from keeper_sdk.core import (
    CapabilityError,
    RefError,
    SchemaError,
    load_manifest,
    validate_manifest,
)

_INVALID_DIR = (
    Path(__file__).resolve().parents[1].parent / "keeper-pam-declarative" / "examples" / "invalid"
)
_INVALID_FILES = sorted(p.name for p in _INVALID_DIR.glob("*.yaml"))


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    schema_module.load_schema_for_family.cache_clear()
    yield
    schema_module.load_schema_for_family.cache_clear()


def _raise_file_not_found(_name: str):
    raise FileNotFoundError(_name)


def _without_jsonschema(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.mark.parametrize("bad_file", _INVALID_FILES)
def test_schema_rejects_invalid(invalid_manifest, bad_file: str) -> None:
    from keeper_sdk.core import build_graph

    path = invalid_manifest(bad_file)
    try:
        manifest = load_manifest(path)
    except (SchemaError, CapabilityError):
        return

    with pytest.raises(RefError):
        build_graph(manifest)


@pytest.mark.parametrize(
    ("schema_parent_parts", "title"),
    [
        (("keeper-pam-declarative",), "sibling-parent"),
        (("pkg", "keeper-pam-declarative"), "sibling-child"),
    ],
)
def test_schema_load_schema_uses_workspace_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    schema_parent_parts: tuple[str, ...],
    title: str,
) -> None:
    package_file = tmp_path / "workspace" / "pkg" / "schema.py"
    package_file.parent.mkdir(parents=True)
    schema_file = (
        tmp_path / "workspace" / Path(*schema_parent_parts) / "manifests" / schema_module.SCHEMA_ID
    )
    schema_file.parent.mkdir(parents=True)
    schema_file.write_text(json.dumps({"type": "object", "title": title}), encoding="utf-8")
    monkeypatch.setattr(schema_module.resources, "files", _raise_file_not_found)
    monkeypatch.setattr(schema_module, "__file__", str(package_file))

    assert schema_module.load_schema()["title"] == title


def test_schema_load_schema_uses_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_file = tmp_path / schema_module.SCHEMA_ID
    schema_file.write_text(json.dumps({"type": "object", "title": "override"}), encoding="utf-8")
    monkeypatch.setattr(schema_module.resources, "files", _raise_file_not_found)
    monkeypatch.setattr(schema_module, "__file__", str(tmp_path / "pkg" / "schema.py"))
    monkeypatch.setenv("KEEPER_DECLARATIVE_SCHEMA", str(schema_file))

    assert schema_module.load_schema()["title"] == "override"


def test_schema_load_schema_raises_when_no_source_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(schema_module.resources, "files", _raise_file_not_found)
    monkeypatch.setattr(schema_module, "__file__", str(tmp_path / "pkg" / "schema.py"))
    monkeypatch.delenv("KEEPER_DECLARATIVE_SCHEMA", raising=False)

    with pytest.raises(SchemaError) as exc:
        schema_module.load_schema()

    assert exc.value.reason == "manifest schema not found"


def test_schema_pydantic_fallback_accepts_valid_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    _without_jsonschema(monkeypatch)

    validate_manifest({"version": "1", "name": "lab"})


def test_schema_pydantic_fallback_raises_schema_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _without_jsonschema(monkeypatch)

    with pytest.raises(SchemaError) as exc:
        validate_manifest({"version": "1", "name": "lab", "resources": "not-a-list"})

    assert exc.value.context["error_count"] >= 1


def test_schema_rejects_unknown_top_level_key_with_field_name_in_message() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest({"version": "1", "name": "lab", "unexpected": True})

    assert "unexpected" in exc.value.reason


def test_schema_rejects_missing_required_field_with_field_name_in_message() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest({"version": "1"})

    assert "name" in exc.value.reason


def test_schema_rejects_type_mismatch_with_field_location() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest({"version": "1", "name": "lab", "gateways": {}})

    assert exc.value.context["location"] == "gateways"


def test_schema_rejects_one_of_failure_with_item_location() -> None:
    with pytest.raises(SchemaError) as exc:
        validate_manifest(
            {
                "version": "1",
                "name": "lab",
                "resources": [{"uid_ref": "res.bad", "type": "notReal", "title": "bad"}],
            }
        )

    assert exc.value.context["location"] == "resources/0"
