"""JSON envelope + UID fingerprinting for ``dsk report`` outputs."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from keeper_sdk.cli._live.transcript import secret_leak_check
from keeper_sdk.core.errors import CapabilityError


class ReportOutputLeakError(Exception):
    """Raised when serialized report JSON fails ``secret_leak_check``."""

    def __init__(self, warnings: list[str]) -> None:
        self.warnings = warnings
        super().__init__(", ".join(warnings))


def serialize_report_payload(payload: dict[str, Any]) -> str:
    """``json.dumps`` envelope + belt-and-brangles leak grep (P17 / live-smoke parity).

    Monkeypatch note: callers should invoke ``keeper_runner.run_keeper_batch`` so
    tests can patch ``keeper_sdk.cli._report.runner.run_keeper_batch``.
    """
    text = json.dumps(payload, indent=2)
    leaks = secret_leak_check(
        text,
        env_keys=tuple(
            k for k in ("KEEPER_PASSWORD", "KEEPER_TOTP_SECRET") if (os.environ.get(k) or "")
        ),
    )
    if leaks:
        raise ReportOutputLeakError(leaks)
    return text


def _fingerprint_uid(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<uid:{digest}>"


def fingerprint_uid_fields(
    rows: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Copy rows, replacing string values for selected keys with fingerprints."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append(row)
            continue
        copy = dict(row)
        for key in keys:
            uid = copy.get(key)
            if isinstance(uid, str) and uid:
                copy[key] = _fingerprint_uid(uid)
        out.append(copy)
    return out


def parse_report_json_array(raw: str, *, command: str) -> list[dict[str, Any]]:
    """Parse Commander ``dump_report_data`` JSON array stdout."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CapabilityError(
            reason=f"{command} returned non-JSON stdout: {exc}",
            context={"head": raw[:400]},
            next_action=f"run `keeper {command} --format json` manually and inspect output",
        ) from exc
    if not isinstance(parsed, list):
        raise CapabilityError(
            reason=f"{command} JSON was not an array",
            context={"sample": str(parsed)[:200]},
            next_action="upgrade Keeper Commander to a compatible version",
        )
    rows: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"value": item})
    return rows


def build_envelope(
    *,
    command: str,
    rows: list[Any],
    meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dsk_report_version": 1,
        "command": command,
        "meta": meta,
        "rows": rows,
    }
