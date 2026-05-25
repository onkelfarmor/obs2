import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client, config_entry_oauth2_flow

from .api import NavimowAPI
from .const import CLIENT_ID, CLIENT_SECRET, DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN
from .coordinator import NavimowCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["lawn_mower", "sensor", "device_tracker"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        config_entry_oauth2_flow.LocalOAuth2Implementation(
            hass,
            DOMAIN,
            CLIENT_ID,
            CLIENT_SECRET,
            OAUTH2_AUTHORIZE,
            OAUTH2_TOKEN,
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    oauth_session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    websession = aiohttp_client.async_get_clientsession(hass)
    api = NavimowAPI(websession, oauth_session)

    devices = await api.async_get_devices()

    coordinators: dict[str, tuple[NavimowCoordinator, dict]] = {}
    for device in devices:
        device_id = device["deviceId"]
        device_name = device.get("deviceName", "Navimow")
        coord = NavimowCoordinator(hass, api, device_id, device_name)
        await coord.async_config_entry_first_refresh()
        coordinators[device_id] = (coord, device)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
