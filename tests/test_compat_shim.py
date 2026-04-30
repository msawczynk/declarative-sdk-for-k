from __future__ import annotations

import importlib
import json
import subprocess
import sys
import warnings
from pathlib import Path

import keeper_sdk

REPO_ROOT = Path(__file__).resolve().parents[1]


def _drop_declarative_sdk_k(*, reset_warning: bool) -> None:
    for name in list(sys.modules):
        if name == "declarative_sdk_k" or name.startswith("declarative_sdk_k."):
            sys.modules.pop(name, None)
    if reset_warning and hasattr(sys, "_declarative_sdk_k_shim_warning_emitted"):
        delattr(sys, "_declarative_sdk_k_shim_warning_emitted")


def test_declarative_sdk_k_imports() -> None:
    _drop_declarative_sdk_k(reset_warning=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        declarative_sdk_k = importlib.import_module("declarative_sdk_k")
    assert declarative_sdk_k is not None


def test_declarative_sdk_k_version_matches_keeper_sdk() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        declarative_sdk_k = importlib.import_module("declarative_sdk_k")
    assert declarative_sdk_k.__version__ == keeper_sdk.__version__


def test_keeper_sdk_import_still_works() -> None:
    assert keeper_sdk is not None


def test_declarative_sdk_k_core_import_path_works() -> None:
    _drop_declarative_sdk_k(reset_warning=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        module = importlib.import_module("declarative_sdk_k.core")
    assert module.load_manifest is keeper_sdk.core.load_manifest


def test_declarative_sdk_k_shim_warns_once_per_process() -> None:
    _drop_declarative_sdk_k(reset_warning=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module("declarative_sdk_k")
    assert [w.category for w in caught] == [DeprecationWarning]

    _drop_declarative_sdk_k(reset_warning=False)
    with warnings.catch_warnings(record=True) as caught_again:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module("declarative_sdk_k")
    assert caught_again == []


def test_pam_schema_marks_legacy_version_deprecated() -> None:
    schema = json.loads(
        (REPO_ROOT / "keeper_sdk/core/schemas/pam-environment.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    marker = schema["$defs"]["manifest_version"]["x-keeper-deprecated"]
    assert marker["remove-after-pin"] == "v2.0.0"
    assert "schema: pam-environment.v1" in marker["reason"]


def test_sync_upstream_baseline_check_exits_zero_with_current_pin(tmp_path: Path) -> None:
    baseline = tmp_path / ".sync_baseline"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/sync_upstream.py",
            "--baseline-check",
            "--baseline-file",
            str(baseline),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "NEW_COMMANDS: []" in proc.stdout
    assert "CHANGED_APIS: []" in proc.stdout
    assert "DRIFT_DETECTED: false" in proc.stdout
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data["pinned_version"] == data["installed_version"]
