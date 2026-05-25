from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NavimowCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: dict = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        NavimowTracker(coord, device)
        for coord, device in coordinators.values()
    )


class NavimowTracker(CoordinatorEntity[NavimowCoordinator], TrackerEntity):
    _attr_source_type = SourceType.GPS
    _attr_icon = "mdi:robot-mower"

    def __init__(self, coordinator: NavimowCoordinator, device: dict) -> None:
        super().__init__(coordinator)
        device_id = device["deviceId"]
        device_name = device.get("deviceName", "Navimow")
        self._attr_unique_id = f"{device_id}_tracker"
        self._attr_name = f"{device_name} position"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    def _parse_position(self) -> tuple[float | None, float | None]:
        data = self.coordinator.data or {}
        pos = data.get("position")
        if isinstance(pos, dict):
            return pos.get("lat"), pos.get("lng")
        # Fallback: direkte felter i API-svaret
        lat = data.get("lat") or data.get("latitude")
        lng = data.get("lng") or data.get("longitude")
        return lat, lng

    @property
    def latitude(self) -> float | None:
        lat, _ = self._parse_position()
        return float(lat) if lat is not None else None

    @property
    def longitude(self) -> float | None:
        _, lng = self._parse_position()
        return float(lng) if lng is not None else None

    @property
    def location_accuracy(self) -> int:
        return 5
