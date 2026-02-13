"""The Charge Forecast integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, EPEX_SENSOR_ENTITY_ID

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Charge Forecast from a config entry."""
    
    # Verify EPEX sensor exists before setting up
    epex_state = hass.states.get(EPEX_SENSOR_ENTITY_ID)
    if epex_state is None:
        _LOGGER.error(
            "EPEX forecast sensor '%s' not found. "
            "Please install and configure the NED Energy Forecast integration first: "
            "https://github.com/BravoNLD/NED-forecast",
            EPEX_SENSOR_ENTITY_ID
        )
        
        # Create persistent notification
        hass.components.persistent_notification.async_create(
            f"De EPEX prijsprognose sensor ({EPEX_SENSOR_ENTITY_ID}) is niet gevonden. "
            f"Installeer eerst de NED Energy Forecast integratie.",
            title="Charge Forecast - Configuratiefout",
            notification_id="charge_forecast_missing_epex",
        )
        return False
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
