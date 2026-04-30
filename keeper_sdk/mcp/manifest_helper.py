"""Helpers for MCP tool calls that reuse DSK in process."""

from __future__ import annotations

import contextlib
import io
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from keeper_sdk.core.redact import redact


def yaml_to_tempfile(yaml_str: str) -> Path:
    """Write manifest YAML to a temp file. Caller removes it."""
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yaml",
        prefix="dsk-mcp-",
        delete=False,
    )
    with handle:
        handle.write(yaml_str)
        if yaml_str and not yaml_str.endswith("\n"):
            handle.write("\n")
    return Path(handle.name)


def json_to_tempfile(json_str: str) -> Path:
    """Write JSON to a temp file. Caller removes it."""
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="dsk-mcp-",
        delete=False,
    )
    with handle:
        handle.write(json_str)
        if json_str and not json_str.endswith("\n"):
            handle.write("\n")
    return Path(handle.name)


def capture_dsk_output(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Capture redacted stdout/stderr from an in-process DSK call."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    code: int | str | None = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            fn(*args, **kwargs)
        except SystemExit as exc:
            code = exc.code

    out = stdout.getvalue()
    err = stderr.getvalue()
    text = out if out else err
    if out and err:
        text = f"{out}{err}"
    if not text and code not in (None, 0):
        text = f"exit {code}"
    return str(redact(text)).strip()


def remove_tempfile(path: Path) -> None:
    """Best-effort temp cleanup."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
