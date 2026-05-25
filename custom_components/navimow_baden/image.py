from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .mqtt_handler import NavimowMQTTHandler

_LOGGER = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw
    _PIL = True
except ImportError:
    _PIL = False

_SIZE = 800
_PAD = 50


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    mqtt: NavimowMQTTHandler | None = data.get("mqtt")
    if mqtt is None:
        return
    async_add_entities(
        NavimowPathImage(hass, coord, device, mqtt)
        for _id, (coord, device) in data["coordinators"].items()
    )


class NavimowPathImage(ImageEntity):
    _attr_content_type = "image/png"

    def __init__(self, hass, coordinator, device: dict, mqtt: NavimowMQTTHandler) -> None:
        super().__init__(hass)
        self._coordinator = coordinator
        self._mqtt = mqtt
        self._device_id: str = device["deviceId"]
        device_name: str = device.get("deviceName", "Navimow Baden")
        self._attr_unique_id = f"{self._device_id}_path_image"
        self._attr_name = f"{device_name} klippesti"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, self._device_id)})
        self._cached: bytes | None = None
        self._attr_image_last_updated = datetime.now(timezone.utc)
        mqtt.add_listener(self._device_id, self._on_new_point)

    def _on_new_point(self) -> None:
        self._cached = None
        self._attr_image_last_updated = datetime.now(timezone.utc)
        self.schedule_update_ha_state()

    async def async_image(self) -> bytes | None:
        if self._cached is None:
            self._cached = self._render()
        return self._cached

    def _render(self) -> bytes | None:
        points = self._mqtt.get_path(self._device_id)
        if not _PIL:
            return None
        if not points:
            return self._placeholder()
        return self._draw_path(points)

    def _draw_path(self, points):
        xs, ys = zip(*points)
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y) or 1
        scale = (_SIZE - 2 * _PAD) / span

        def px(x, y):
            return (int(_PAD + (x - min_x) * scale), int(_SIZE - _PAD - (y - min_y) * scale))

        img = Image.new("RGB", (_SIZE, _SIZE), (28, 28, 28))
        draw = ImageDraw.Draw(img)
        for i in range(0, _SIZE, 50):
            draw.line([(i, 0), (i, _SIZE)], fill=(48, 48, 48))
            draw.line([(0, i), (_SIZE, i)], fill=(48, 48, 48))
        n = len(points)
        for i in range(1, n):
            t = i / n
            color = (0, int(80 + 120 * t), int(200 * (1 - t)))
            draw.line([px(*points[i - 1]), px(*points[i])], fill=color, width=2)
        sx, sy = px(*points[0])
        draw.ellipse([(sx - 7, sy - 7), (sx + 7, sy + 7)], fill=(30, 100, 255), outline=(255, 255, 255))
        ex, ey = px(*points[-1])
        draw.ellipse([(ex - 7, ey - 7), (ex + 7, ey + 7)], fill=(220, 50, 50), outline=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _placeholder(self):
        img = Image.new("RGB", (400, 80), (28, 28, 28))
        draw = ImageDraw.Draw(img)
        draw.text((12, 28), "Afventer klipning…", fill=(140, 140, 140))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
