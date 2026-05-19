"""MinForsyning integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import MinForsyningAuth
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRES,
    CONF_UTILITY,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MinForsyningCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    stored_tokens = {
        "access_token": entry.data.get(CONF_ACCESS_TOKEN),
        "refresh_token": entry.data.get(CONF_REFRESH_TOKEN),
        "token_expires": entry.data.get(CONF_TOKEN_EXPIRES),
    }

    auth = MinForsyningAuth.from_dict(
        session=session,
        stored=stored_tokens,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        utility=entry.data[CONF_UTILITY],
    )

    # Authenticate if we have no stored token
    if not auth.access_token:
        await auth.authenticate()
        # Persist the fresh tokens
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **auth.to_dict()},
        )

    coordinator = MinForsyningCoordinator(hass, session, auth)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
