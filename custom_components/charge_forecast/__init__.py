"""The Charge Forecast integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
from .coordinator import ChargeforecastDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_FORCE_CALIBRATION = "force_calibration"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Charge Forecast from a config entry."""
    
    # Get config from entry
    nordpool_entity = entry.data.get(CONF_NORDPOOL_ENTITY)
    
    # Get options with defaults
    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    calibration_interval = entry.options.get(
        CONF_CALIBRATION_INTERVAL, DEFAULT_CALIBRATION_INTERVAL
    )
    lookback_days = entry.options.get(CONF_LOOKBACK_DAYS, DEFAULT_LOOKBACK_DAYS)
    
    # Get aiohttp session
    session = async_get_clientsession(hass)
    
    # Create coordinator with proper arguments
    coordinator = ChargeforecastDataUpdateCoordinator(
        hass=hass,
        session=session,
        nordpool_entity=nordpool_entity,
        update_interval=timedelta(seconds=update_interval),
        calibration_interval=timedelta(seconds=calibration_interval),
        lookback_days=lookback_days,
    )
    
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    # Register service
    async def handle_force_calibration(call: ServiceCall) -> None:
        """Handle the force_calibration service call."""
        _LOGGER.info("Forcing calibration via service call")
        await coordinator.async_force_calibration()
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORCE_CALIBRATION,
        handle_force_calibration,
        schema=cv.make_entity_service_schema({}),
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove service if no more instances
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_FORCE_CALIBRATION)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
