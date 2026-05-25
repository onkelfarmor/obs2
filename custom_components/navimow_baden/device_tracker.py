import math

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DOCK_LAT, CONF_DOCK_LNG, DOMAIN
from .coordinator import NavimowCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: dict = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    dock_lat: float = entry.data[CONF_DOCK_LAT]
    dock_lng: float = entry.data[CONF_DOCK_LNG]
    async_add_entities(
        NavimowTracker(coord, device, dock_lat, dock_lng)
        for coord, device in coordinators.values()
    )


def _relative_to_gps(
    dock_lat: float, dock_lng: float, pos_x: float, pos_y: float
) -> tuple[float, float]:
    """Convert relative meter offset (X east, Y north) to GPS coordinates."""
    lat = dock_lat + (pos_y / 111_320)
    lng = dock_lng + (pos_x / (111_320 * math.cos(math.radians(dock_lat))))
    return lat, lng


class NavimowTracker(CoordinatorEntity[NavimowCoordinator], TrackerEntity):
    _attr_source_type = SourceType.GPS
    _attr_icon = "mdi:robot-mower"

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        device: dict,
        dock_lat: float,
        dock_lng: float,
    ) -> None:
        super().__init__(coordinator)
        self._dock_lat = dock_lat
        self._dock_lng = dock_lng
        device_id = device["deviceId"]
        device_name = device.get("deviceName", "Navimow Baden")
        self._attr_unique_id = f"{device_id}_tracker"
        self._attr_name = f"{device_name} position"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _resolve_gps(self) -> tuple[float | None, float | None]:
        data = self.coordinator.data or {}
        pos = data.get("position")

        if isinstance(pos, dict):
            raw_lat = pos.get("lat")
            raw_lng = pos.get("lng")
            if raw_lat is not None and raw_lng is not None:
                # Afgør om koordinaterne er relative (meter) eller rigtige GPS.
                # Rigtige GPS-grader ligger altid i intervallet ±90/±180.
                # Relative meter-offset kan let overstige dette for store haver.
                if abs(float(raw_lat)) <= 90 and abs(float(raw_lng)) <= 180:
                    return float(raw_lat), float(raw_lng)
                # Relative meter-koordinater — konverter via dokke-position
                return _relative_to_gps(self._dock_lat, self._dock_lng, float(raw_lng), float(raw_lat))

        # Fallback: posX/posY (ioBroker-format)
        pos_x = data.get("posX") or data.get("postureX")
        pos_y = data.get("posY") or data.get("postureY")
        if pos_x is not None and pos_y is not None:
            return _relative_to_gps(self._dock_lat, self._dock_lng, float(pos_x), float(pos_y))

        return None, None

    @property
    def latitude(self) -> float | None:
        lat, _ = self._resolve_gps()
        return lat

    @property
    def longitude(self) -> float | None:
        _, lng = self._resolve_gps()
        return lng

    @property
    def location_accuracy(self) -> int:
        return 5

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "dok_breddegrad": self._dock_lat,
            "dok_længdegrad": self._dock_lng,
        }
