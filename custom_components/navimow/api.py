import uuid
import logging
from .const import API_BASE, CMD_START_STOP, CMD_PAUSE_UNPAUSE, CMD_DOCK

_LOGGER = logging.getLogger(__name__)


class NavimowAPI:
    def __init__(self, websession, oauth_session):
        self._session = websession
        self._oauth = oauth_session

    async def _headers(self):
        await self._oauth.async_ensure_token_valid()
        return {
            "Authorization": f"Bearer {self._oauth.token['access_token']}",
            "Content-Type": "application/json",
            "x-request-id": str(uuid.uuid4()),
        }

    async def async_get_devices(self):
        headers = await self._headers()
        async with self._session.get(
            f"{API_BASE}/openapi/smarthome/authList",
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", []) if isinstance(data, dict) else data

    async def async_get_device_status(self, device_id: str) -> dict:
        headers = await self._headers()
        async with self._session.post(
            f"{API_BASE}/openapi/smarthome/getVehicleStatus",
            headers=headers,
            json={"deviceId": device_id},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", {}) if isinstance(data, dict) else {}

    async def _send_command(self, device_id: str, command: str, params: dict | None = None):
        headers = await self._headers()
        async with self._session.post(
            f"{API_BASE}/openapi/smarthome/sendCommands",
            headers=headers,
            json={"deviceId": device_id, "command": command, "params": params or {}},
        ) as resp:
            resp.raise_for_status()

    async def async_start(self, device_id: str):
        await self._send_command(device_id, CMD_START_STOP, {"on": True})

    async def async_pause(self, device_id: str):
        await self._send_command(device_id, CMD_PAUSE_UNPAUSE, {"on": False})

    async def async_dock(self, device_id: str):
        await self._send_command(device_id, CMD_DOCK)
