"""Home Assistant sensor entities for MinForsyning water consumption."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import MinForsyningCoordinator

_LOGGER = logging.getLogger(__name__)

STATISTIC_ID_DAILY = f"{DOMAIN}:water_consumption_daily"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MinForsyningCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        MinForsyningSensor(coordinator, entry, "yesterday", "Vandforbrug i går", "yesterday"),
        MinForsyningSensor(coordinator, entry, "today", "Vandforbrug i dag", "today"),
        MinForsyningSensor(coordinator, entry, "month", "Vandforbrug denne måned", "month_total"),
        MinForsyningSensor(coordinator, entry, "year", "Vandforbrug i år", "year_total"),
    ]
    async_add_entities(entities)

    # Register a listener to push historical data into HA statistics
    # so the Energy Dashboard can display long-term water usage.
    @callback
    def _push_statistics(_now=None) -> None:
        coordinator.hass.async_create_task(_async_insert_statistics(hass, coordinator))

    entry.async_on_unload(coordinator.async_add_listener(_push_statistics))


async def _async_insert_statistics(
    hass: HomeAssistant, coordinator: MinForsyningCoordinator
) -> None:
    """Insert daily consumption values into HA long-term statistics."""
    if not coordinator.data or not coordinator.data.daily_values:
        return

    unit = _ha_unit(coordinator.data.unit)
    meta = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="MinForsyning vandforbrug",
        source=DOMAIN,
        statistic_id=STATISTIC_ID_DAILY,
        unit_of_measurement=unit,
    )

    # Find the last known sum so we can continue from there
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, STATISTIC_ID_DAILY, True, {"sum"}
    )
    last_sum: float = 0.0
    if last_stats and STATISTIC_ID_DAILY in last_stats:
        last_sum = last_stats[STATISTIC_ID_DAILY][0].get("sum") or 0.0

    stats: list[StatisticData] = []
    running_sum = last_sum

    for iso_date in sorted(coordinator.data.daily_values):
        value = coordinator.data.daily_values[iso_date]
        start = dt_util.as_utc(datetime.fromisoformat(iso_date))
        running_sum += value
        stats.append(
            StatisticData(start=start, sum=round(running_sum, 3), state=value)
        )

    if stats:
        async_add_external_statistics(hass, meta, stats)
        _LOGGER.debug("Inserted %d daily statistics for MinForsyning", len(stats))


def _ha_unit(raw: str) -> str:
    if raw.upper() in ("L", "LITER", "LITERS"):
        return UnitOfVolume.LITERS
    return UnitOfVolume.CUBIC_METERS


class MinForsyningSensor(CoordinatorEntity[MinForsyningCoordinator], SensorEntity):
    """A sensor representing one water-consumption metric."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MinForsyningCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        data_field: str,
    ) -> None:
        super().__init__(coordinator)
        self._data_field = data_field
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="MinForsyning",
            manufacturer="KMD Easy Energy",
            model="Vandforbrug",
            entry_type=None,
        )

    @property
    def native_unit_of_measurement(self) -> str:
        if self.coordinator.data:
            return _ha_unit(self.coordinator.data.unit)
        return UnitOfVolume.CUBIC_METERS

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return getattr(self.coordinator.data, self._data_field, None)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        attrs: dict = {}
        if self._data_field == "yesterday":
            # Include last 7 days for convenience
            daily = self.coordinator.data.daily_values
            recent = {k: v for k, v in sorted(daily.items())[-7:]}
            attrs["last_7_days"] = recent
        return attrs
