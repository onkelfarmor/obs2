import logging
from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_entry_oauth2_flow

from .const import CLIENT_ID, CLIENT_SECRET, CONF_DOCK_LAT, CONF_DOCK_LNG, DOMAIN, OAUTH2_AUTHORIZE, OAUTH2_TOKEN

_LOGGER = logging.getLogger(__name__)

DOCK_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOCK_LAT): vol.Coerce(float),
        vol.Required(CONF_DOCK_LNG): vol.Coerce(float),
    }
)


class NavimowConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    DOMAIN = DOMAIN
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._oauth_data: dict = {}

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_step_user(self, user_input=None):
        """Registrer OAuth2-implementation før flow starter (nødvendig ved første installation)."""
        config_entry_oauth2_flow.async_register_implementation(
            self.hass,
            DOMAIN,
            config_entry_oauth2_flow.LocalOAuth2Implementation(
                self.hass,
                DOMAIN,
                CLIENT_ID,
                CLIENT_SECRET,
                OAUTH2_AUTHORIZE,
                OAUTH2_TOKEN,
            ),
        )
        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict) -> dict:
        self._oauth_data = data
        return await self.async_step_dock()

    async def async_step_dock(self, user_input: dict[str, Any] | None = None) -> dict:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                DOCK_SCHEMA(user_input)
            except vol.Invalid:
                errors["base"] = "ugyldig_koordinat"
            else:
                return self.async_create_entry(
                    title="Navimow Baden",
                    data={**self._oauth_data, **user_input},
                )

        return self.async_show_form(
            step_id="dock",
            data_schema=DOCK_SCHEMA,
            errors=errors,
            description_placeholders={},
        )
