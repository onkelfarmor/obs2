from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NavimowCoordinator


@dataclass(frozen=True, kw_only=True)
class NavimowSensorDescription(SensorEntityDescription):
    value_key: str


SENSORS: tuple[NavimowSensorDescription, ...] = (
    NavimowSensorDescription(
        key="battery",
        name="Batteri",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="batteryLevel",
    ),
    NavimowSensorDescription(
        key="mowing_progress",
        name="Klippefremgang",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_key="mowingPercentage",
        icon="mdi:grass",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinators: dict = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    async_add_entities(
        NavimowSensor(coord, device, desc)
        for coord, device in coordinators.values()
        for desc in SENSORS
    )


class NavimowSensor(CoordinatorEntity[NavimowCoordinator], SensorEntity):
    entity_description: NavimowSensorDescription

    def __init__(
        self,
        coordinator: NavimowCoordinator,
        device: dict,
        description: NavimowSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = device["deviceId"]
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    @property
    def native_value(self) -> int | float | None:
        return (self.coordinator.data or {}).get(self.entity_description.value_key)
