"""Config flow for Charge Forecast integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_CHARGING_DURATION,
    DEFAULT_CHARGING_DURATION,
    EPEX_SENSOR_ENTITY_ID,
)

_LOGGER = logging.getLogger(__name__)


class ChargeForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Charge Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        # Check if NED Energy Forecast integration is loaded
        if "ned_energy_forecast" not in self.hass.config.components:
            errors["base"] = "ned_forecast_not_loaded"
            _LOGGER.warning("NED Energy Forecast integration not loaded")

        # Check if EPEX sensor exists
        epex_state = self.hass.states.get(EPEX_SENSOR_ENTITY_ID)
        if epex_state is None:
            errors["base"] = "epex_sensor_not_found"
            _LOGGER.warning(f"EPEX sensor {EPEX_SENSOR_ENTITY_ID} not found")

        if user_input is not None and not errors:
            # Create entry
            return self.async_create_entry(
                title="Charge Forecast",
                data={},
                options={
                    CONF_CHARGING_DURATION: user_input.get(
                        CONF_CHARGING_DURATION, DEFAULT_CHARGING_DURATION
                    ),
                },
            )

        # Show configuration form
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CHARGING_DURATION,
                    default=DEFAULT_CHARGING_DURATION,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=12,
                        step=1,
                        unit_of_measurement="hours",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return ChargeForecastOptionsFlow(config_entry)


class ChargeForecastOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Charge Forecast."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CHARGING_DURATION,
                        default=self.config_entry.options.get(
                            CONF_CHARGING_DURATION, DEFAULT_CHARGING_DURATION
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=12,
                            step=1,
                            unit_of_measurement="hours",
                            mode=selector.NumberSelectorMode.BOX,
                        ),
                    ),
                }
            ),
        )
