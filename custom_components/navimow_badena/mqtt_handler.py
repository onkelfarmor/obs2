import asyncio
import json
import logging
import ssl
from collections import deque
from urllib.parse import urlparse

_LOGGER = logging.getLogger(__name__)

MAX_POINTS = 5000


class NavimowMQTTHandler:
    """Holder MQTT-forbindelse og opsamler positionspunkter per enhed."""

    def __init__(self, mqtt_info: dict, device_ids: list[str]) -> None:
        self._info = mqtt_info
        self._device_ids = device_ids
        self._paths: dict[str, deque] = {d: deque(maxlen=MAX_POINTS) for d in device_ids}
        self._attributes: dict[str, dict] = {d: {} for d in device_ids}
        self._listeners: dict[str, list] = {}
        self._task: asyncio.Task | None = None

    def get_path(self, device_id: str) -> list[tuple[float, float, float]]:
        return list(self._paths.get(device_id, []))

    def get_attributes(self, device_id: str) -> dict:
        return dict(self._attributes.get(device_id, {}))

    def reset_path(self, device_id: str) -> None:
        self._paths.setdefault(device_id, deque(maxlen=MAX_POINTS)).clear()
        self._notify(device_id)

    def add_listener(self, device_id: str, callback) -> None:
        self._listeners.setdefault(device_id, []).append(callback)

    async def async_start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _notify(self, device_id: str) -> None:
        for cb in self._listeners.get(device_id, []):
            try:
                cb()
            except Exception:
                pass

    def _connection_params(self) -> dict:
        mqtt_url = self._info.get("mqttUrl", "")
        host = self._info.get("mqttHost", "mqtt.navimow.com")
        username = self._info.get("userName", "")
        password = self._info.get("pwdInfo", "")

        params: dict = {"username": username, "password": password}

        if mqtt_url.startswith(("wss://", "ws://")):
            parsed = urlparse(mqtt_url)
            params["hostname"] = parsed.hostname or host
            params["port"] = parsed.port or (443 if mqtt_url.startswith("wss") else 80)
            params["websocket_path"] = parsed.path or "/mqtt"
            params["transport"] = "websockets"
            if mqtt_url.startswith("wss://"):
                params["tls_context"] = ssl.create_default_context()
        else:
            params["hostname"] = host
            params["port"] = 1883

        return params

    async def _run(self) -> None:
        import aiomqtt

        topics = []
        for dev in self._device_ids:
            topics.append(f"/downlink/vehicle/{dev}/realtimeDate/location")
            topics.append(f"/downlink/vehicle/{dev}/realtimeDate/state")
            topics.append(f"/downlink/vehicle/{dev}/realtimeDate/attributes")
            topics.append(f"/downlink/vehicle/{dev}/realtimeDate/event")

        params = self._connection_params()

        while True:
            try:
                async with aiomqtt.Client(**params) as client:
                    _LOGGER.info("Navimow MQTT forbundet til %s", params.get("hostname"))
                    for topic in topics:
                        await client.subscribe(topic)
                    async for msg in client.messages:
                        self._on_message(str(msg.topic), bytes(msg.payload))
            except asyncio.CancelledError:
                return
            except Exception as err:
                _LOGGER.warning("Navimow MQTT fejl, genforbinder om 30 sek.: %s", err)
                await asyncio.sleep(30)

    def _on_message(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            return

        parts = topic.split("/")
        if len(parts) < 5:
            return
        device_id = parts[3]
        channel = parts[-1]

        if channel == "location":
            self._handle_location(device_id, data)
        elif channel == "state":
            self._handle_state(device_id, data)
        elif channel == "attributes":
            self._handle_attributes(device_id, data)
        elif channel == "event":
            _LOGGER.debug("Navimow %s event: %s", device_id, data)

    def _handle_location(self, device_id: str, data: dict) -> None:
        pos_x = data.get("posX") or data.get("postureX") or data.get("x")
        pos_y = data.get("posY") or data.get("postureY") or data.get("y")
        theta = data.get("postureTheta") or data.get("theta") or 0.0
        if pos_x is None or pos_y is None:
            return
        self._paths.setdefault(device_id, deque(maxlen=MAX_POINTS)).append(
            (float(pos_x), float(pos_y), float(theta))
        )
        self._notify(device_id)

    def _handle_state(self, device_id: str, data: dict) -> None:
        state = str(data.get("vehicleState", "")).lower()
        if state in ("docked", "idle", "charging", "isdocked", "isidle", "ischarging"):
            if self._paths.get(device_id):
                _LOGGER.debug("Navimow %s returnerede til dok — nulstiller sti", device_id)
                self.reset_path(device_id)

    def _handle_attributes(self, device_id: str, data: dict) -> None:
        attrs = self._attributes.setdefault(device_id, {})
        for key in (
            "battery", "capacityRemaining", "descriptiveCapacityRemaining",
            "signal_strength", "signalStrength",
            "firmware_version", "firmwareVersion",
            "serial_number", "serialNumber",
            "online",
        ):
            if key in data:
                attrs[key] = data[key]
        self._notify(device_id)
