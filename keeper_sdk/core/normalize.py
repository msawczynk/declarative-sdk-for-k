"""Alias normalization + manifest<->Commander PAM JSON round-trip.

The declarative manifest is richer than Commander's native PAM import/export
format. ``to_pam_import_json`` projects that richer manifest onto the JSON
shape Commander 17.x actually consumes:

    {
      "project": "...",
      "shared_folder_resources": {...},
      "shared_folder_users": {...},
      "pam_configuration": {...},
      "pam_data": {"resources": [...], "users": [...]},
    }

``from_pam_import_json`` performs the inverse lift, accepting both the native
Commander shape and the older SDK-internal shape used by early offline tests.
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
            if key == "jit_settings" and isinstance(value, dict):
                rewritten[key] = _rewrite_jit_settings_refs(value, lookup)
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


def _rewrite_jit_settings_refs(
    settings: dict[str, Any],
    lookup: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    rewritten: dict[str, Any] = {}
    for key, value in settings.items():
        if key in _DECLARATIVE_ONLY_KEYS:
            continue
        if key == "pam_directory_uid_ref" and isinstance(value, str):
            rewritten["pam_directory_record"] = lookup.get(value, (value,))[0] or value
            continue
        rewritten[key] = _rewrite_refs(value, lookup)
    return rewritten


def to_pam_import_json(manifest: dict[str, Any]) -> dict[str, Any]:
    """Render a manifest dict as Commander's native PAM project JSON."""
    canonical = canonicalize(manifest)
    lookup = _build_lookup(canonical)

    out: dict[str, Any] = {"project": canonical.get("name")}

    shared_folders = canonical.get("shared_folders")
    if isinstance(shared_folders, dict):
        resources_folder = shared_folders.get("resources")
        users_folder = shared_folders.get("users")
        if isinstance(resources_folder, dict):
            out["shared_folder_resources"] = _rewrite_refs(resources_folder, lookup)
        if isinstance(users_folder, dict):
            out["shared_folder_users"] = _rewrite_refs(users_folder, lookup)

    pam_configurations = canonical.get("pam_configurations")
    if isinstance(pam_configurations, list) and pam_configurations:
        pam_configuration = _rewrite_refs(pam_configurations[0], lookup)
        gateway_name = pam_configuration.pop("gateway", None)
        if isinstance(gateway_name, str) and gateway_name.strip():
            pam_configuration["gateway_name"] = gateway_name
        out["pam_configuration"] = pam_configuration

    pam_data: dict[str, Any] = {}
    if "resources" in canonical:
        pam_data["resources"] = _rewrite_refs(canonical["resources"], lookup)
    if "users" in canonical:
        pam_data["users"] = _rewrite_refs(canonical["users"], lookup)
    if pam_data:
        out["pam_data"] = pam_data
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
    else:
        shared_folders: dict[str, Any] = {}
        if isinstance(doc.get("shared_folder_resources"), dict):
            item = dict(doc["shared_folder_resources"])
            item.setdefault("uid_ref", assign_ref("resources", "sf"))
            shared_folders["resources"] = item
        if isinstance(doc.get("shared_folder_users"), dict):
            item = dict(doc["shared_folder_users"])
            item.setdefault("uid_ref", assign_ref("users", "sf"))
            shared_folders["users"] = item
        if shared_folders:
            out["shared_folders"] = shared_folders

    if "gateways" in doc:
        out["gateways"] = []
        for gateway in doc["gateways"]:
            item = dict(gateway)
            item.setdefault("uid_ref", assign_ref(item.get("name", "gateway"), "gw"))
            item.setdefault("mode", "reference_existing")
            out["gateways"].append(item)
    elif isinstance(doc.get("pam_configuration"), dict):
        gateway_name = str(doc["pam_configuration"].get("gateway_name", "")).strip()
        if gateway_name:
            out["gateways"] = [
                {
                    "uid_ref": assign_ref(gateway_name, "gw"),
                    "name": gateway_name,
                    "mode": "reference_existing",
                }
            ]

    if "pam_configurations" in doc:
        out["pam_configurations"] = []
        for cfg in doc["pam_configurations"]:
            item = dict(cfg)
            seed = item.get("title") or item.get("environment") or "pamcfg"
            item.setdefault("uid_ref", assign_ref(seed, "pc"))
            out["pam_configurations"].append(item)
    elif isinstance(doc.get("pam_configuration"), dict):
        item = dict(doc["pam_configuration"])
        gateway_name = item.pop("gateway_name", None)
        seed = item.get("title") or item.get("environment") or "pamcfg"
        item.setdefault("uid_ref", assign_ref(seed, "pc"))
        if gateway_name and out.get("gateways"):
            item["gateway_uid_ref"] = out["gateways"][0]["uid_ref"]
        out["pam_configurations"] = [item]

    raw_pam = doc.get("pam_data")
    pam_data: dict[str, Any] = raw_pam if isinstance(raw_pam, dict) else {}

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
    elif isinstance(pam_data.get("resources"), list):
        out["resources"] = []
        for res in pam_data["resources"]:
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
    elif isinstance(pam_data.get("users"), list):
        out["users"] = []
        for user in pam_data["users"]:
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
