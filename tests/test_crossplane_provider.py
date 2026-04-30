from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

import keeper_sdk.crossplane as crossplane
from keeper_sdk.core.errors import CapabilityError
from keeper_sdk.crossplane import CrossplaneProvider
from keeper_sdk.crossplane import provider as provider_module

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: str) -> dict[str, Any]:
    document = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_crossplane_provider_import_and_instantiate() -> None:
    provider = CrossplaneProvider()

    assert crossplane.__all__ == ["CrossplaneProvider"]
    assert crossplane.CrossplaneProvider is CrossplaneProvider
    assert provider.docs_next_action == provider_module.DOCS_NEXT_ACTION
    assert "docs/CROSSPLANE_INTEGRATION.md" in provider.docs_next_action


def test_plan_raises_capability_error_with_docs_next_action() -> None:
    provider = CrossplaneProvider()

    with pytest.raises(CapabilityError) as exc_info:
        provider.plan({"kind": "KeeperRecord"})

    assert "Crossplane provider plan is not implemented" in str(exc_info.value)
    assert exc_info.value.resource_type == "crossplane"
    assert exc_info.value.next_action == provider_module.DOCS_NEXT_ACTION


@pytest.mark.parametrize("method_name", ["apply", "observe", "create", "update", "delete"])
def test_crossplane_lifecycle_methods_are_preview_gated(method_name: str) -> None:
    provider = CrossplaneProvider()
    method = getattr(provider, method_name)

    with pytest.raises(CapabilityError) as exc_info:
        method({"kind": "KeeperRecord"})

    assert f"Crossplane provider {method_name} is not implemented" in str(exc_info.value)
    assert "CROSSPLANE_INTEGRATION.md" in (exc_info.value.next_action or "")


@pytest.mark.parametrize(
    ("path", "kind", "family"),
    [
        (
            "crossplane/xrds/keeperrecord.xrd.yaml",
            "KeeperRecord",
            "keeper-vault.v1",
        ),
        (
            "crossplane/xrds/keepersharedfolder.xrd.yaml",
            "KeeperSharedFolder",
            "keeper-vault-sharing.v1",
        ),
    ],
)
def test_xrd_stubs_define_expected_version_and_mapping(
    path: str,
    kind: str,
    family: str,
) -> None:
    xrd = _load_yaml(path)

    assert xrd["apiVersion"] == "apiextensions.crossplane.io/v1"
    assert xrd["kind"] == "CompositeResourceDefinition"
    assert xrd["metadata"]["annotations"]["dsk.keeper.io/status"] == "preview-gated"
    assert family in xrd["metadata"]["annotations"]["dsk.keeper.io/maps-to"]
    assert xrd["spec"]["group"] == "keeper.dsk.io"
    assert xrd["spec"]["names"]["kind"] == kind

    version = xrd["spec"]["versions"][0]
    assert version["name"] == "v1alpha1"
    assert version["served"] is True
    assert version["referenceable"] is True
    assert "parameters" in version["schema"]["openAPIV3Schema"]["properties"]["spec"]["properties"]


@pytest.mark.parametrize(
    ("path", "kind", "family", "block"),
    [
        (
            "crossplane/compositions/keeperrecord.composition.yaml",
            "KeeperRecord",
            "keeper-vault.v1",
            "records",
        ),
        (
            "crossplane/compositions/keepersharedfolder.composition.yaml",
            "KeeperSharedFolder",
            "keeper-vault-sharing.v1",
            "shared_folders",
        ),
    ],
)
def test_compositions_reference_dsk_cli_function(
    path: str,
    kind: str,
    family: str,
    block: str,
) -> None:
    composition = _load_yaml(path)

    assert composition["apiVersion"] == "apiextensions.crossplane.io/v1"
    assert composition["kind"] == "Composition"
    assert composition["metadata"]["annotations"]["dsk.keeper.io/status"] == "preview-gated"
    assert composition["metadata"]["annotations"]["dsk.keeper.io/reconciler"] == "dsk-cli"
    assert composition["spec"]["compositeTypeRef"] == {
        "apiVersion": "keeper.dsk.io/v1alpha1",
        "kind": kind,
    }
    assert composition["spec"]["mode"] == "Pipeline"

    step = composition["spec"]["pipeline"][0]
    assert step["functionRef"]["name"] == "function-dsk-cli"
    template = step["input"]["spec"]["manifestTemplate"]
    assert template["schema"] == family
    assert block in template


def test_provider_docstrings_describe_crossplane_usage() -> None:
    module_doc = inspect.getdoc(provider_module)
    class_doc = inspect.getdoc(CrossplaneProvider)

    assert module_doc is not None
    assert class_doc is not None
    assert "Crossplane" in module_doc
    assert "keeper-vault.v1" in module_doc
    assert "keeper-vault-sharing.v1" in module_doc
    assert "CapabilityError" in module_doc
    assert "observe" in class_doc
    assert "delete" in class_doc


def test_crossplane_integration_doc_declares_preview_gate_and_references() -> None:
    text = (ROOT / "docs/CROSSPLANE_INTEGRATION.md").read_text(encoding="utf-8")

    assert "preview-gated" in text
    assert "function-dsk-cli" in text
    assert "https://docs.crossplane.io/latest/composition/compositions/" in text
    assert "https://github.com/crossplane/upjet" in text
