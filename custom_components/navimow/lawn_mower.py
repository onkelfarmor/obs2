import logging

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VEHICLE_STATE_MAP
from .coordinator import NavimowCoordinator

_LOGGER = logging.getLogger(__name__)

_ACTIVITY_MAP = {
    "mowing": LawnMowerActivity.MOWING,
    "paused": LawnMowerActivity.PAUSED,
    "docked": LawnMowerActivity.DOCKED,
    "error": LawnMowerActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: dict = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        NavimowMower(coord, device)
        for coord, device in coordinators.values()
    )


class NavimowMower(CoordinatorEntity[NavimowCoordinator], LawnMowerEntity):
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator: NavimowCoordinator, device: dict) -> None:
        super().__init__(coordinator)
        self._device_id = device["deviceId"]
        self._attr_unique_id = f"{self._device_id}_mower"
        self._attr_name = device.get("deviceName", "Navimow")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("deviceName", "Navimow"),
            manufacturer="Segway",
            model=device.get("deviceType", "Navimow"),
        )

    @property
    def activity(self) -> LawnMowerActivity | None:
        data = self.coordinator.data
        if not data:
            return None
        raw = str(data.get("vehicleState", "unknown")).lower()
        mapped = VEHICLE_STATE_MAP.get(raw, "error")
        return _ACTIVITY_MAP.get(mapped, LawnMowerActivity.ERROR)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        attrs = {}
        if (pct := data.get("mowingPercentage")) is not None:
            attrs["klippefremgang_pct"] = pct
        if (err := data.get("errorCode")) is not None:
            attrs["fejlkode"] = err
        if (msg := data.get("errorMessage")):
            attrs["fejlbesked"] = msg
        if (sig := data.get("signalStrength")) is not None:
            attrs["signalstyrke"] = sig
        return attrs

    async def async_start_mowing(self) -> None:
        await self.coordinator.api.async_start(self._device_id)
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        await self.coordinator.api.async_pause(self._device_id)
        await self.coordinator.async_request_refresh()

    async def async_dock(self) -> None:
        await self.coordinator.api.async_dock(self._device_id)
        await self.coordinator.async_request_refresh()
