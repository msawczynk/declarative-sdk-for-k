"""Alias normalization + manifest<->pam_import JSON round-trip.

The declarative manifest is a superset-compatible wrapper around the JSON
consumed by Commander's ``pam project import``. `to_pam_import_json` emits a
document Commander can accept; `from_pam_import_json` ingests a Commander
export and returns a canonical manifest dict.

Alias handling here is intentionally minimal — the manifest schema already
uses the canonical Commander field names for anything that ships in
production. The alias table covers common human-friendly synonyms so that
hand-written manifests don't trip on trivia.
"""

from __future__ import annotations

import copy
from typing import Any

# ----------------------------------------------------------------------------
# alias table (input-only; canonical output always uses the value)

_FIELD_ALIASES: dict[str, str] = {
    "hostname": "host",
    "pam_config": "pam_configuration_uid_ref",
    "pam_config_uid_ref": "pam_configuration_uid_ref",
    "pam_config_uid": "pam_configuration_uid_ref",
    "pam_configuration_uid": "pam_configuration_uid_ref",
    "gateway_uid": "gateway_uid_ref",
    "gateway": "gateway_uid_ref",
    "administrative_credentials": "administrative_credentials_uid_ref",
    "admin_credentials_uid_ref": "administrative_credentials_uid_ref",
    "launch_credentials": "launch_credentials_uid_ref",
    "autofill_credentials": "autofill_credentials_uid_ref",
    "sftp_user_credentials": "sftp_user_credentials_uid_ref",
    "sftp_resource": "sftp_resource_uid_ref",
    "pam_directory": "pam_directory_uid_ref",
    "dom_administrative_credential": "dom_administrative_credential_uid_ref",
    "dom_administrative_credentials_uid_ref": "dom_administrative_credential_uid_ref",
}

_REMOVE_SECTIONS: tuple[str, ...] = ()


def _rename(mapping: dict[str, Any]) -> dict[str, Any]:
    renamed: dict[str, Any] = {}
    for key, value in mapping.items():
        canonical = _FIELD_ALIASES.get(key, key)
        if isinstance(value, dict):
            renamed[canonical] = _rename(value)
        elif isinstance(value, list):
            renamed[canonical] = [
                _rename(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            renamed[canonical] = value
    return renamed


def canonicalize(document: dict[str, Any]) -> dict[str, Any]:
    """Apply alias rewrites on a manifest dict, returning a new dict."""
    return _rename(copy.deepcopy(document))


# ----------------------------------------------------------------------------
# manifest -> pam_import JSON

# Declarative-only keys that must not leak into Commander's pam_import payload.
_DECLARATIVE_ONLY_KEYS = {"uid_ref"}

# Fields whose value is a uid_ref pointer. Commander's pam_import accepts
# by-title strings for the same fields under a slightly different name (the
# trailing ``_uid_ref`` is dropped). We rewrite each one to the target's
# human-readable identity (title for records, name for gateways, etc.).
_REF_FIELD_MAP = {
    "pam_configuration_uid_ref": ("pam_configuration", "title"),
    "gateway_uid_ref": ("gateway", "name"),
    "administrative_credentials_uid_ref": ("administrative_credentials", "title"),
    "launch_credentials_uid_ref": ("launch_credentials", "title"),
    "autofill_credentials_uid_ref": ("autofill_credentials", "title"),
    "sftp_user_credentials_uid_ref": ("sftp_user_credentials", "title"),
    "sftp_resource_uid_ref": ("sftp_resource", "title"),
    "pam_directory_uid_ref": ("pam_directory", "title"),
    "dom_administrative_credential_uid_ref": ("dom_administrative_credential", "title"),
}


def _build_lookup(manifest: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map each uid_ref to (title_or_name, kind)."""
    lookup: dict[str, tuple[str, str]] = {}
    for gateway in manifest.get("gateways") or []:
        if gateway.get("uid_ref"):
            lookup[gateway["uid_ref"]] = (gateway.get("name", ""), "gateway")
    for cfg in manifest.get("pam_configurations") or []:
        if cfg.get("uid_ref"):
            lookup[cfg["uid_ref"]] = (cfg.get("title", ""), "pam_configuration")
    for res in manifest.get("resources") or []:
        if res.get("uid_ref"):
            lookup[res["uid_ref"]] = (res.get("title", ""), res.get("type", "resource"))
        for user in res.get("users") or []:
            if user.get("uid_ref"):
                lookup[user["uid_ref"]] = (user.get("title", ""), user.get("type", "pamUser"))
    for user in manifest.get("users") or []:
        if user.get("uid_ref"):
            lookup[user["uid_ref"]] = (user.get("title", ""), user.get("type", "pamUser"))
    return lookup


def _rewrite_refs(node: Any, lookup: dict[str, tuple[str, str]]) -> Any:
    if isinstance(node, dict):
        rewritten: dict[str, Any] = {}
        for key, value in node.items():
            if key in _DECLARATIVE_ONLY_KEYS:
                continue
            if key in _REF_FIELD_MAP and isinstance(value, str):
                new_key = _REF_FIELD_MAP[key][0]
                title = lookup.get(value, (value,))[0] or value
                rewritten[new_key] = title
                continue
            if key == "additional_credentials_uid_refs" and isinstance(value, list):
                rewritten["additional_credentials"] = [
                    lookup.get(ref, (ref,))[0] or ref for ref in value if isinstance(ref, str)
                ]
                continue
            rewritten[key] = _rewrite_refs(value, lookup)
        return rewritten
    if isinstance(node, list):
        return [_rewrite_refs(item, lookup) for item in node]
    return node


def to_pam_import_json(manifest: dict[str, Any]) -> dict[str, Any]:
    """Render a manifest dict as a Commander ``pam project import`` document.

    Rewrites ``*_uid_ref`` pointers into Commander's by-title string
    references and strips declarative-only keys.
    """
    canonical = canonicalize(manifest)
    lookup = _build_lookup(canonical)

    out: dict[str, Any] = {"version": canonical.get("version"), "project": canonical.get("name")}
    for key in (
        "projects",
        "shared_folders",
        "gateways",
        "pam_configurations",
        "resources",
        "users",
    ):
        if key in canonical:
            out[key] = _rewrite_refs(canonical[key], lookup)
    return out


# ----------------------------------------------------------------------------
# pam_import JSON -> manifest

def from_pam_import_json(document: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
    """Lift a Commander export into a declarative manifest.

    ``uid_ref`` values are synthesised from titles so the lifted manifest can
    be fed back into validate/plan without further editing. Callers are
    expected to refine the slugs.
    """
    doc = canonicalize(document)
    out: dict[str, Any] = {
        "version": doc.get("version", "1"),
        "name": name or doc.get("project") or doc.get("name") or "exported",
    }

    used: set[str] = set()

    def assign_ref(seed: str, prefix: str) -> str:
        base = _slugify(seed) or prefix
        candidate = f"{prefix}.{base}"
        idx = 1
        while candidate in used:
            idx += 1
            candidate = f"{prefix}.{base}-{idx}"
        used.add(candidate)
        return candidate

    if "projects" in doc:
        out["projects"] = doc["projects"]
    if "shared_folders" in doc:
        out["shared_folders"] = doc["shared_folders"]

    if "gateways" in doc:
        out["gateways"] = []
        for gateway in doc["gateways"]:
            item = dict(gateway)
            item.setdefault("uid_ref", assign_ref(item.get("name", "gateway"), "gw"))
            item.setdefault("mode", "reference_existing")
            out["gateways"].append(item)

    if "pam_configurations" in doc:
        out["pam_configurations"] = []
        for cfg in doc["pam_configurations"]:
            item = dict(cfg)
            seed = item.get("title") or item.get("environment") or "pamcfg"
            item.setdefault("uid_ref", assign_ref(seed, "pc"))
            out["pam_configurations"].append(item)

    if "resources" in doc:
        out["resources"] = []
        for res in doc["resources"]:
            item = dict(res)
            item.setdefault("uid_ref", assign_ref(item.get("title", "resource"), "res"))
            if "users" in item:
                users = []
                for user in item["users"]:
                    uitem = dict(user)
                    seed = uitem.get("title") or uitem.get("login") or "user"
                    uitem.setdefault("uid_ref", assign_ref(seed, "usr"))
                    users.append(uitem)
                item["users"] = users
            out["resources"].append(item)

    if "users" in doc:
        out["users"] = []
        for user in doc["users"]:
            item = dict(user)
            seed = item.get("title") or item.get("login") or "user"
            item.setdefault("uid_ref", assign_ref(seed, "usr"))
            out["users"].append(item)

    return out


def _slugify(value: str) -> str:
    import re

    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "item"
