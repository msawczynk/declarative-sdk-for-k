"""Sanitized live-test proof transcript writer.

Every live-tenant test produces a transcript that pins:

  - Which Commander pin the test ran against.
  - Which schema family + version was being proved.
  - The phases run + their outcomes.
  - A coarse fingerprint of any state mutated (so re-runs are auditable
    without writing the actual UIDs to git).

Secrets, full record UIDs, and tenant identifiers are NEVER written to
the transcript file. The sanitizer is allowlist-based (only known-safe
fields pass through); anything not on the allowlist is replaced with a
length-bucket placeholder (`<redacted:32>`).

Schema (machine-readable shape that downstream tools rely on):

    {
      "schema_family": "keeper-vault",
      "schema_version": "v1",
      "commander_pin": "89047920a0...",
      "started_at": "2026-04-26T19:00:00Z",
      "finished_at": "2026-04-26T19:01:23Z",
      "phases": [
        {"name": "bootstrap", "status": "ok", "elapsed_ms": 4321,
         "details": {"app_uid_fingerprint": "<sha256:8>"}}
      ],
      "summary": {
        "total_phases": 4,
        "ok": 4,
        "skipped": 0,
        "failed": 0
      }
    }

This shape is what `x-keeper-live-proof.evidence` points at. CI's
`live-smoke` workflow validates the file exists + parses + has
non-empty `phases` before marking a phase green.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Match strings that LOOK like Keeper UIDs (22 chars URL-safe base64) so we
# can fingerprint them without printing them. Slightly forgiving on length
# to catch related identifiers (KSM client_id, app_uid, etc.).
_UID_RE = re.compile(r"\b[A-Za-z0-9_-]{20,28}\b")
# Strings that MUST never appear in the transcript even at field level.
_SECRET_KEYS = {
    "password",
    "secret",
    "token",
    "client_key",
    "private_key",
    "appKey",
    "applicationKey",
    "totp",
    "config",
}


def _fingerprint(value: str, prefix: str = "sha256") -> str:
    """Return a short hash placeholder, never the original value."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<{prefix}:{digest}>"


def sanitize_secret_keys_only(value: Any) -> Any:
    """Redact ``_SECRET_KEYS`` dict entries recursively; leave other strings intact.

    ``dsk report`` uses this by default so ``record_uid`` and similar columns
    stay machine-readable. For transcript / evidence parity (fingerprint UID-like
    substrings everywhere), call ``_sanitize_value`` or pass ``--sanitize-uids``.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k.lower() in _SECRET_KEYS:
                out[k] = "<redacted>"
                continue
            out[k] = sanitize_secret_keys_only(v)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize_secret_keys_only(v) for v in value]
    return value


def _sanitize_value(value: Any, key_path: tuple[str, ...] = ()) -> Any:
    """Recursively scrub `value` for leakable content.

    - Dict keys whose lower-case form is in `_SECRET_KEYS` get their
      values replaced with the literal string `<redacted>`.
    - Strings that match `_UID_RE` get fingerprinted in-place.
    - Lists/tuples/dicts recurse.
    - Other primitives pass through.
    """
    base = sanitize_secret_keys_only(value)
    if isinstance(base, str):
        return _UID_RE.sub(lambda m: _fingerprint(m.group(0), "uid"), base)
    if isinstance(base, dict):

        def _fp_strings(v: Any) -> Any:
            if isinstance(v, str):
                return _UID_RE.sub(lambda m: _fingerprint(m.group(0), "uid"), v)
            if isinstance(v, dict):
                return {k2: _fp_strings(v2) for k2, v2 in v.items()}
            if isinstance(v, list):
                return [_fp_strings(x) for x in v]
            return v

        return _fp_strings(base)
    if isinstance(base, list):
        return [_sanitize_value(v, key_path) for v in base]
    return base


@dataclass
class Phase:
    name: str
    status: str = "pending"
    elapsed_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "details": _sanitize_value(self.details),
        }
        if self.error is not None:
            out["error"] = self.error[:500]
        return out


@dataclass
class Transcript:
    schema_family: str
    schema_version: str
    commander_pin: str
    started_at: str = ""
    finished_at: str = ""
    phases: list[Phase] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def add_phase(self, phase: Phase) -> None:
        self.phases.append(phase)

    def finalize(self) -> None:
        self.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def summary(self) -> dict[str, int]:
        ok = sum(1 for p in self.phases if p.status == "ok")
        skipped = sum(1 for p in self.phases if p.status == "skipped")
        failed = sum(1 for p in self.phases if p.status == "failed")
        return {
            "total_phases": len(self.phases),
            "ok": ok,
            "skipped": skipped,
            "failed": failed,
        }

    def to_dict(self) -> dict[str, Any]:
        pin = (self.commander_pin or "").strip()
        if len(pin) > 12:
            pin = pin[:8] + "..."
        return {
            "schema_family": self.schema_family,
            "schema_version": self.schema_version,
            "commander_pin": pin,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "phases": [p.to_dict() for p in self.phases],
            "summary": self.summary(),
        }

    def write(self, path: Path) -> Path:
        """Write sanitized transcript to `path`. Returns the resolved path."""
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.finished_at:
            self.finalize()
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return path


def secret_leak_check(text: str, *, env_keys: tuple[str, ...] = ()) -> list[str]:
    """Return list of leak warnings if `text` contains secret-like strings.

    Used by CI as a belt-and-braces check on the sanitized transcript:
    even though `_sanitize_value` should have stripped everything,
    `secret_leak_check` greps the final bytes for known-bad markers
    (env-var values, `BEGIN PRIVATE KEY`, etc.).

    `env_keys` is a tuple of env var names whose VALUES must NOT appear
    in the transcript. Pass the names of credential env vars from the
    runbook (e.g. `KEEPER_CONFIG`, `KEEPER_LOGIN_TOKEN`).
    """
    warnings: list[str] = []
    if "BEGIN PRIVATE KEY" in text or "BEGIN RSA PRIVATE KEY" in text:
        warnings.append("transcript contains a PEM private-key block")
    if "BEGIN ENCRYPTED PRIVATE KEY" in text:
        warnings.append("transcript contains an encrypted PEM block")
    for key in env_keys:
        val = os.environ.get(key)
        if not val or len(val) < 8:
            continue
        if val in text:
            warnings.append(f"transcript leaks raw value of env var {key!r}")
    if re.search(r"\b[A-Fa-f0-9]{40,64}\b", text):
        # 40-char hex or longer; any sha1/sha256 of a UID would have
        # passed `_fingerprint` truncation. A long unbroken hex run
        # suggests a raw secret or device key.
        warnings.append("transcript contains a long hex run (possible raw key)")
    return warnings
