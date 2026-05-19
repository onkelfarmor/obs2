"""Config flow for MinForsyning integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import AuthenticationError, MinForsyningAuth
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_UTILITY, DEFAULT_UTILITY, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_UTILITY, default=DEFAULT_UTILITY): str,
    }
)


class MinForsyningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of MinForsyning."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            utility = user_input[CONF_UTILITY].strip()

            await self.async_set_unique_id(f"{DOMAIN}_{email}_{utility}")
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            auth = MinForsyningAuth(session, email, password, utility)

            try:
                await auth.authenticate()
            except AuthenticationError as err:
                _LOGGER.warning("MinForsyning auth error: %s", err)
                error_str = str(err).lower()
                if "invalid" in error_str or "password" in error_str or "forkert" in error_str:
                    errors["base"] = "invalid_auth"
                elif "csrf" in error_str or "structure" in error_str:
                    errors["base"] = "login_page_changed"
                else:
                    errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during MinForsyning setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"MinForsyning ({utility})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_UTILITY: utility,
                        **auth.to_dict(),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "utility_hint": "Forsyningsnummer fra URL-parametret 'utility' (standard: 0654000)"
            },
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "MinForsyningOptionsFlow":
        return MinForsyningOptionsFlow(config_entry)


class MinForsyningOptionsFlow(config_entries.OptionsFlow):
    """Allow updating credentials without re-adding the integration."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            utility = user_input[CONF_UTILITY].strip()

            session = async_get_clientsession(self.hass)
            auth = MinForsyningAuth(session, email, password, utility)
            try:
                await auth.authenticate()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_UTILITY: utility,
                        **auth.to_dict(),
                    },
                )
                return self.async_create_entry(title="", data={})

        current = self._entry.data
        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL, default=current.get(CONF_EMAIL, "")): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_UTILITY, default=current.get(CONF_UTILITY, DEFAULT_UTILITY)): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
