"""HTTP client for Keeper Commander Service Mode REST API v2."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import Any

from keeper_sdk.core.errors import CapabilityError

_DONE_STATUSES = {"completed", "complete", "success", "succeeded", "done"}
_FAIL_STATUSES = {"failed", "failure", "error", "expired", "cancelled", "canceled"}


class CommanderServiceClient:
    """Thin client for Commander's async service-mode queue."""

    def __init__(
        self,
        base_url: str = "http://localhost:4020",
        api_key: str | None = None,
        *,
        timeout: int = 300,
        poll_interval: float = 1.0,
        rate_limit_per_minute: int = 60,
        encrypted: bool = False,
        encryption_key: bytes | str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.rate_limit_per_minute = rate_limit_per_minute
        self.encrypted = encrypted
        self.encryption_key = encryption_key

    def _post_async(self, command: str, filedata: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {"command": command}
        if filedata is not None:
            body["filedata"] = filedata
        payload = self._request_json("POST", "/api/v2/executecommand-async", body)
        request_id = _first_str(payload, "request_id", "requestId", "id")
        if not request_id:
            raise CapabilityError(
                reason="Commander Service Mode response did not include request_id",
                next_action="check service-mode API v2 compatibility",
                context={"response": payload},
            )
        return request_id

    def _poll_status(self, request_id: str, timeout: int | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        last_payload: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            payload = self._request_json("GET", f"/api/v2/status/{request_id}")
            last_payload = payload
            status = _status(payload)
            if status in _DONE_STATUSES or status in _FAIL_STATUSES:
                return payload
            time.sleep(self.poll_interval)
        return {
            "status": "expired",
            "request_id": request_id,
            "last_status": last_payload,
            "message": f"timed out after {timeout if timeout is not None else self.timeout}s",
        }

    def _get_result(self, request_id: str) -> dict[str, Any]:
        payload = self._request_json("GET", f"/api/v2/result/{request_id}")
        if self.encrypted:
            return self._decrypt_response(payload)
        return payload

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                if not raw.strip():
                    return {}
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    return {"result": parsed}
                return parsed
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < 2:
                    retry_after = exc.headers.get("Retry-After")
                    delay = _retry_delay(retry_after, attempt=attempt)
                    time.sleep(delay)
                    continue
                raise CapabilityError(
                    reason=f"Commander Service Mode HTTP {exc.code} for {method} {path}",
                    next_action="check service-mode logs, API key, and rate limits",
                    context={"http_status": exc.code, "path": path},
                ) from exc
            except urllib.error.URLError as exc:
                raise CapabilityError(
                    reason=f"Commander Service Mode request failed for {method} {path}: {exc}",
                    next_action="start `keeper server --service-mode` and verify KEEPER_SERVICE_URL",
                    context={"path": path},
                ) from exc
            except json.JSONDecodeError as exc:
                raise CapabilityError(
                    reason=f"Commander Service Mode returned non-JSON for {method} {path}",
                    next_action="check service-mode API v2 compatibility",
                ) from exc
        raise CapabilityError(
            reason=f"Commander Service Mode rate limit retry exhausted for {method} {path}",
            next_action="reduce request rate or raise service-mode limits",
            context={"rate_limit_per_minute": self.rate_limit_per_minute},
        )

    def _decrypt_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        ciphertext_b64 = _first_str(payload, "ciphertext", "encrypted_data", "data")
        nonce_b64 = _first_str(payload, "nonce", "iv")
        tag_b64 = _first_str(payload, "tag")
        if not ciphertext_b64 or not nonce_b64:
            return payload
        if self.encryption_key is None:
            raise CapabilityError(
                reason="encrypted Commander Service Mode response needs encryption_key",
                next_action="configure AES-256 GCM key or disable encrypted response mode",
            )
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
        except ImportError as exc:
            raise CapabilityError(
                reason="AES-GCM response decryption needs cryptography installed",
                next_action="pip install cryptography or disable encrypted response mode",
            ) from exc

        key = _decode_key(self.encryption_key)
        ciphertext = base64.b64decode(ciphertext_b64)
        if tag_b64:
            ciphertext += base64.b64decode(tag_b64)
        nonce = base64.b64decode(nonce_b64)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
        parsed = json.loads(plaintext.decode("utf-8"))
        if not isinstance(parsed, dict):
            return {"result": parsed}
        return parsed


def _first_str(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _status(payload: dict[str, Any]) -> str:
    value = payload.get("status") or payload.get("state") or payload.get("request_status")
    return str(value or "").strip().lower()


def _retry_delay(retry_after: str | None, *, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return min(2.0, 0.5 * (2**attempt))


def _decode_key(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return value
    try:
        return base64.b64decode(value)
    except ValueError:
        return value.encode("utf-8")


__all__ = ["CommanderServiceClient"]
