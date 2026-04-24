"""Manifest loading + dumping."""

from __future__ import annotations

from pathlib import Path

from keeper_sdk.core import dump_manifest, load_manifest


def test_load_minimal(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    assert manifest.name == "acme-lab-minimal"
    assert len(manifest.gateways) == 1
    assert manifest.gateways[0].uid_ref == "acme-lab-gw"
    assert len(manifest.pam_configurations) == 1
    assert manifest.pam_configurations[0].environment == "local"
    assert len(manifest.resources) == 1


def test_load_full_local(full_local_manifest_path: Path) -> None:
    manifest = load_manifest(full_local_manifest_path)
    assert manifest.name == "acme-prod-full-local"
    kinds = {resource.type for resource in manifest.resources}
    assert kinds == {"pamMachine", "pamDatabase", "pamDirectory", "pamRemoteBrowser"}


def test_load_aws(aws_manifest_path: Path) -> None:
    manifest = load_manifest(aws_manifest_path)
    config = manifest.pam_configurations[0]
    assert config.environment == "aws"


def test_load_domain(domain_manifest_path: Path) -> None:
    manifest = load_manifest(domain_manifest_path)
    config = manifest.pam_configurations[0]
    assert config.environment == "domain"


def test_dump_roundtrip(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    dumped = dump_manifest(manifest, fmt="yaml")
    assert "acme-lab-minimal" in dumped
    assert "pamMachine" in dumped


def test_iter_uid_refs_unique(minimal_manifest_path: Path) -> None:
    manifest = load_manifest(minimal_manifest_path)
    uid_refs = [uid_ref for uid_ref, _ in manifest.iter_uid_refs()]
    assert len(uid_refs) == len(set(uid_refs))
