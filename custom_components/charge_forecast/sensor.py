"""Sensor platform for Charge Forecast."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_CHARGING_DURATION,
    DEFAULT_CHARGING_DURATION,
    EPEX_SENSOR_ENTITY_ID,
    SENSOR_WINDOWS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChargeForecastSensorEntityDescription(SensorEntityDescription):
    """Describes Charge Forecast sensor entity."""

    window_hours: int | None = None


def _parse_epex_timestamp(ts_str: str | None) -> datetime | None:
    """
    Parse EPEX timestamp (ISO string with Z suffix) to timezone-aware datetime.
    
    NED Energy Forecast returns timestamps as "2025-01-15T14:00:00Z" (UTC).
    """
    if not ts_str:
        return None
        
    try:
        # Handle "Z" suffix (UTC indicator)
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        
        # Ensure timezone-aware
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=dt_util.UTC)
        
        return dt
    except (ValueError, AttributeError, TypeError) as err:
        _LOGGER.debug("Failed to parse EPEX timestamp '%s': %s", ts_str, err)
        return None


def _get_epex_forecast_data(hass: HomeAssistant) -> list[dict[str, Any]] | None:
    """
    Get EPEX forecast data from NED Energy Forecast sensor.
    
    Returns list of {"timestamp": datetime, "price": float} or None on error.
    """
    epex_sensor = hass.states.get(EPEX_SENSOR_ENTITY_ID)
    
    # Check sensor existence
    if epex_sensor is None:
        _LOGGER.error(
            "EPEX sensor '%s' not found. Ensure NED Energy Forecast is installed.",
            EPEX_SENSOR_ENTITY_ID
        )
        return None
    
    # Check sensor availability
    if epex_sensor.state in ("unavailable", "unknown", None):
        _LOGGER.warning(
            "EPEX sensor unavailable (state=%s). Waiting for data...",
            epex_sensor.state
        )
        return None
    
    forecast_data = []
    
    # Add current price as first datapoint
    try:
        current_price = float(epex_sensor.state)
        now = dt_util.now()
        forecast_data.append({
            "timestamp": now,
            "price": current_price,
        })
    except (ValueError, TypeError) as err:
        _LOGGER.warning("Could not parse current EPEX price '%s': %s", epex_sensor.state, err)
    
    # Get forecast from attributes
    forecast_list = epex_sensor.attributes.get("forecast")
    
    if not forecast_list or not isinstance(forecast_list, list):
        _LOGGER.debug("EPEX sensor has no forecast data in attributes")
        # Return with just current price if available
        return forecast_data if forecast_data else None
    
    # Parse forecast entries
    for record in forecast_list:
        if not isinstance(record, dict):
            continue
            
        ts = _parse_epex_timestamp(record.get("datetime"))
        price = record.get("value")
        
        if ts and price is not None:
            try:
                forecast_data.append({
                    "timestamp": ts,
                    "price": float(price),
                })
            except (ValueError, TypeError):
                continue
    
    if not forecast_data:
        _LOGGER.warning("No valid forecast data found in EPEX sensor")
        return None
    
    # Sort by timestamp
    forecast_data.sort(key=lambda x: x["timestamp"])
    
    _LOGGER.debug("Retrieved %d EPEX forecast datapoints", len(forecast_data))
    return forecast_data


def _calculate_best_charging_block(
    forecast_data: list[dict[str, Any]],
    window_hours: int,
    charging_duration: int,
) -> tuple[datetime | None, dict[str, Any]]:
    """
    Find the best charging block (rolling window) within the forecast window.
    
    Uses rolling window approach: evaluates every possible N-hour block,
    calculates average price, and returns the cheapest one.
    On price tie, earliest block wins.
    
    Args:
        forecast_data: List of {"timestamp": datetime, "price": float}
        window_hours: Search window (24/36/72/96/144 hours)
        charging_duration: Duration of charging session (hours)
    
    Returns:
        (best_start_time, attributes_dict)
    """
    empty_result = {
        "block_start": None,
        "block_end": None,
        "average_price": None,
        "total_cost": None,
        "hours_from_now": None,
        "window_hours": window_hours,
        "charging_duration": charging_duration,
        "top_3_blocks": [],
        "data_coverage_pct": 0.0,
    }
    
    if not forecast_data:
        return None, empty_result
    
    now = dt_util.now()
    window_end = now + timedelta(hours=window_hours)
    
    # Filter data within search window
    window_data = [
        d for d in forecast_data
        if now <= d["timestamp"] <= window_end
    ]
    
    if len(window_data) < charging_duration:
        _LOGGER.debug(
            "Insufficient data for %dh block: only %d datapoints in %dh window",
            charging_duration,
            len(window_data),
            window_hours,
        )
        empty_result["data_coverage_pct"] = round(
            len(window_data) / window_hours * 100, 1
        ) if window_hours > 0 else 0.0
        return None, empty_result
    
    # Calculate all possible charging blocks (rolling window)
    blocks = []
    
    for i in range(len(window_data) - charging_duration + 1):
        block = window_data[i : i + charging_duration]
        
        # Calculate average price for this block
        avg_price = sum(d["price"] for d in block) / len(block)
        start_time = block[0]["timestamp"]
        end_time = block[-1]["timestamp"] + timedelta(hours=1)  # End of last hour
        
        blocks.append({
            "start": start_time,
            "end": end_time,
            "avg_price": avg_price,
            "total_cost": avg_price * charging_duration,
        })
    
    if not blocks:
        return None, empty_result
    
    # Sort by average price (cheapest first), then by start time (earliest first)
    blocks.sort(key=lambda b: (b["avg_price"], b["start"]))
    
    best = blocks[0]
    
    # Top 3 blocks for comparison
    top3 = [
        {
            "start": b["start"].isoformat(),
            "end": b["end"].isoformat(),
            "avg_price": round(b["avg_price"], 3),
            "hours_from_now": round(
                (b["start"] - now).total_seconds() / 3600, 1
            ),
        }
        for b in blocks[:3]
    ]
    
    # Data coverage percentage
    expected_datapoints = window_hours
    actual_datapoints = len(window_data)
    coverage_pct = min(100.0, round(actual_datapoints / expected_datapoints * 100, 1))
    
    return best["start"], {
        "block_start": best["start"].isoformat(),
        "block_end": best["end"].isoformat(),
        "average_price": round(best["avg_price"], 3),
        "total_cost": round(best["total_cost"], 3),
        "hours_from_now": round((best["start"] - now).total_seconds() / 3600, 1),
        "window_hours": window_hours,
        "charging_duration": charging_duration,
        "top_3_blocks": top3,
        "data_coverage_pct": coverage_pct,
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Charge Forecast sensors from a config entry."""
    charging_duration = entry.options.get(
        CONF_CHARGING_DURATION, DEFAULT_CHARGING_DURATION
    )
    
    entities = []
    
    for key, window_hours in SENSOR_WINDOWS.items():
        entities.append(
            ChargeForecastSensor(
                entry=entry,
                description=ChargeForecastSensorEntityDescription(
                    key=f"best_block_{key}",
                    name=f"Best Charge Block ({key})",
                    icon="mdi:battery-charging-clock",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    window_hours=window_hours,
                ),
                charging_duration=charging_duration,
            )
        )
    
    async_add_entities(entities)


class ChargeForecastSensor(SensorEntity):
    """Representation of a Charge Forecast sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        description: ChargeForecastSensorEntityDescription,
        charging_duration: int,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self._entry = entry
        self._charging_duration = charging_duration
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}
        self._attr_available = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        # Listen to EPEX sensor state changes for real-time updates
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [EPEX_SENSOR_ENTITY_ID],
                self._handle_epex_update,
            )
        )
        
        # Initial update
        await self._async_update()

    @callback
    def _handle_epex_update(self, event: Any) -> None:
        """Handle EPEX sensor state changes."""
        self.hass.async_create_task(self._async_update())

    async def _async_update(self) -> None:
        """Update sensor state and attributes."""
        try:
            # Get EPEX forecast data
            forecast_data = _get_epex_forecast_data(self.hass)
            
            if forecast_data is None:
                self._attr_available = False
                self._attr_native_value = None
                self._attr_extra_state_attributes = {
                    "error": "EPEX forecast data not available",
                    "charging_duration": self._charging_duration,
                }
                self.async_write_ha_state()
                return
            
            # Calculate best charging block
            best_start, attributes = _calculate_best_charging_block(
                forecast_data=forecast_data,
                window_hours=self.entity_description.window_hours,
                charging_duration=self._charging_duration,
            )
            
            # Update state
            if best_start is None:
                self._attr_available = False
                _LOGGER.debug(
                    "No optimal block found for %s (insufficient data)",
                    self.entity_id
                )
            else:
                self._attr_available = True
            
            self._attr_native_value = best_start
            self._attr_extra_state_attributes = attributes
            
            self.async_write_ha_state()
            
        except Exception as err:
            _LOGGER.error("Error updating %s: %s", self.entity_id, err, exc_info=True)
            self._attr_available = False
            self._attr_extra_state_attributes = {
                "error": str(err),
                "charging_duration": self._charging_duration,
            }
            self.async_write_ha_state()
