import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NavimowAPI
from .const import UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class NavimowCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, api: NavimowAPI, device_id: str, device_name: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Navimow {device_name}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api
        self.device_id = device_id

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.async_get_device_status(self.device_id)
        except Exception as err:
            raise UpdateFailed(f"Fejl ved opdatering af Navimow: {err}") from err
