"""DataUpdateCoordinator for MinForsyning."""
from __future__ import annotations

import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ConsumptionData, MinForsyningAPI
from .auth import AuthenticationError, MinForsyningAuth
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class MinForsyningCoordinator(DataUpdateCoordinator[ConsumptionData]):
    """Fetches consumption data and keeps sensors up to date."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        auth: MinForsyningAuth,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._auth = auth
        self._api = MinForsyningAPI(session, auth)

    async def _async_update_data(self) -> ConsumptionData:
        try:
            return await self._api.fetch_consumption()
        except AuthenticationError:
            _LOGGER.warning("Token expired or invalid – re-authenticating")
            try:
                await self._auth.authenticate()
                return await self._api.fetch_consumption()
            except AuthenticationError as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching MinForsyning data: {err}") from err
