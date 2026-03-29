"""
Seam Connect API client (server-side only).

Auth: API key in Authorization: Bearer <key> — not a username/password.
Official reference: https://docs.seam.co/latest/api/
Test connectivity: POST https://connect.getseam.com/workspaces/get with body {}
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SEAM_BASE_URL = "https://connect.getseam.com"


def _iso_utc_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    s = dt.isoformat()
    return s.replace("+00:00", "Z")


class SeamAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SeamService:
    """
    Thin wrapper around Seam's HTTP API. Use from the backend only; never send the API key to browsers.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_SEAM_BASE_URL,
        timeout: float = 30.0,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("Seam API key is required")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _post(self, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path if path.startswith('/') else '/' + path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=headers, json=json_body or {})
        except httpx.RequestError as e:
            raise SeamAPIError(f"Seam request failed: {e}") from e

        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text}

        if response.status_code >= 400:
            raise SeamAPIError(
                f"Seam API error ({response.status_code})",
                status_code=response.status_code,
                body=data,
            )

        if isinstance(data, dict) and data.get("ok") is False:
            raise SeamAPIError("Seam API returned ok=false", status_code=response.status_code, body=data)

        return data if isinstance(data, dict) else {"result": data}

    def get_workspace(self) -> dict[str, Any]:
        """Verify credentials and reachability; returns parsed JSON including `workspace`."""
        return self._post("/workspaces/get", {})

    def verify_connection(self) -> dict[str, Any]:
        """Alias for a clear name when checking deploy / env configuration."""
        return self.get_workspace()

    def list_devices(self, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """POST /devices/list — https://docs.seam.co/latest/api/devices/list"""
        data = self._post("/devices/list", body or {})
        devices = data.get("devices")
        return devices if isinstance(devices, list) else []

    def _device_name_candidates(self, device: dict[str, Any]) -> list[str]:
        """Lowercased labels to match against SEAM_DEVICE_NAME (display name, nickname, etc.)."""
        out: list[str] = []
        for key in ("display_name", "nickname"):
            v = device.get(key)
            if isinstance(v, str) and v.strip():
                out.append(v.strip().lower())
        props = device.get("properties")
        if isinstance(props, dict):
            app = props.get("appearance")
            if isinstance(app, dict):
                n = app.get("name")
                if isinstance(n, str) and n.strip():
                    out.append(n.strip().lower())
        return out

    def find_device_id_by_display_name(self, name: str) -> str | None:
        """
        Resolve Seam ``device_id`` by human-readable device name (e.g. UI label "Grape").
        Match is case-insensitive on display_name / nickname / properties.appearance.name.
        If multiple devices match equally, the first listed device wins and a warning is logged.
        """
        want = (name or "").strip().lower()
        if not want:
            return None
        matches: list[str] = []
        for device in self.list_devices():
            did = device.get("device_id")
            if not isinstance(did, str) or not did.strip():
                continue
            for label in self._device_name_candidates(device):
                if label == want:
                    matches.append(did.strip())
                    break
        if not matches:
            logger.warning("No Seam device found with display name matching %r", name)
            return None
        if len(matches) > 1:
            logger.warning(
                "Multiple Seam devices matched name %r; using first device_id=%s",
                name,
                matches[0],
            )
        return matches[0]

    def get_access_code(self, access_code_id: str) -> dict[str, Any]:
        """POST /access_codes/get — https://docs.seam.co/latest/api/access_codes/get"""
        data = self._post("/access_codes/get", {"access_code_id": access_code_id})
        ac = data.get("access_code")
        return ac if isinstance(ac, dict) else {}

    def wait_until_access_code_set_on_device(
        self,
        access_code_id: str,
        *,
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        """
        Poll until Seam reports ``status`` ``set`` (PIN actually on the lock), or errors/time out.

        ``create`` returning HTTP 200 only means the job was accepted; the lock may still be
        ``setting`` until this returns.
        """
        deadline = time.monotonic() + max(5.0, float(timeout_seconds))
        interval = max(0.5, float(poll_interval_seconds))
        last: dict[str, Any] = {}
        last_status: str | None = None
        while time.monotonic() < deadline:
            last = self.get_access_code(access_code_id)
            status = (last.get("status") or "").strip().lower()
            last_status = status
            errors = last.get("errors")
            if isinstance(errors, list) and len(errors) > 0:
                raise SeamAPIError(
                    f"Access code reported device errors before status=set: {errors!r}",
                    body=last,
                )
            if status == "set":
                return last
            if status == "unknown":
                raise SeamAPIError(
                    "Access code status is unknown (check device connectivity in Seam).",
                    body=last,
                )
            time.sleep(interval)
        raise SeamAPIError(
            f"Timed out after {timeout_seconds}s waiting for PIN on physical lock "
            f"(last status={last_status!r}).",
            body=last,
        )

    def delete_access_code(self, device_id: str, access_code_id: str) -> None:
        """POST /access_codes/delete — remove a failed or obsolete access code in Seam."""
        self._post(
            "/access_codes/delete",
            {"device_id": device_id, "access_code_id": access_code_id},
        )

    def create_access_code(
        self,
        device_id: str,
        code: str,
        *,
        name: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> dict[str, Any]:
        """
        Program a PIN on the lock via Seam (time-bound window).
        https://docs.seam.co/latest/api/access_codes/create
        """
        body: dict[str, Any] = {
            "device_id": device_id,
            "code": code,
            "name": name,
            "starts_at": _iso_utc_z(starts_at),
            "ends_at": _iso_utc_z(ends_at),
        }
        return self._post("/access_codes/create", body)
