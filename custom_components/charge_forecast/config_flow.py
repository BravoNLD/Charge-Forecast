"""Config flow for Charge Forecast integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_CALIBRATION_INTERVAL,
    CONF_LOOKBACK_DAYS,
    CONF_NORDPOOL_ENTITY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CALIBRATION_INTERVAL,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _validate_nordpool_entity(hass: HomeAssistant, entity_id: str) -> bool:
    """Validate that the nordpool entity exists."""
    return hass.states.get(entity_id) is not None


class ChargeforecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Charge Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate nordpool entity
            nordpool_entity = user_input[CONF_NORDPOOL_ENTITY]
            
            if not _validate_nordpool_entity(self.hass, nordpool_entity):
                errors["base"] = "entity_not_found"
            else:
                # Check if already configured
                await self.async_set_unique_id(nordpool_entity)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Charge Forecast",
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NORDPOOL_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargeforecastOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ChargeforecastOptionsFlowHandler(config_entry)


class ChargeforecastOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Charge Forecast."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(cv.positive_int, vol.Range(min=600, max=86400)),
                vol.Optional(
                    CONF_CALIBRATION_INTERVAL,
                    default=options.get(
                        CONF_CALIBRATION_INTERVAL, DEFAULT_CALIBRATION_INTERVAL
                    ),
                ): vol.All(cv.positive_int, vol.Range(min=3600, max=604800)),
                vol.Optional(
                    CONF_LOOKBACK_DAYS,
                    default=options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS),
                ): vol.All(cv.positive_int, vol.Range(min=7, max=30)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)

