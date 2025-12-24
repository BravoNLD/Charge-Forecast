"""Sensor platform for Charge Forecast."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SENSOR_TYPE_CHARGE_ADVICE,
    SENSOR_TYPE_CONSUMPTION,
    SENSOR_TYPE_MODEL_ACCURACY,
    SENSOR_TYPE_RESTLAST,
    SENSOR_TYPE_SOLAR,
    SENSOR_TYPE_WIND_OFFSHORE,
    SENSOR_TYPE_WIND_ONSHORE,
    ADVICE_CHARGE_SOON,
    ADVICE_WAIT_2_3_DAYS,
    ADVICE_WAIT_4_7_DAYS,
    ADVICE_NO_DATA,
)
from .coordinator import ChargeforecastDataUpdateCoordinator


@dataclass
class ChargeforecastSensorEntityDescription(SensorEntityDescription):
    """Describes Charge Forecast sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_TYPES: tuple[ChargeforecastSensorEntityDescription, ...] = (
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_CONSUMPTION,
        name="NED Consumption",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="GW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_latest_ned_value(data, "consumption"),
        attributes_fn=lambda data: _get_ned_forecast_attributes(data, "consumption"),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_WIND_ONSHORE,
        name="NED Wind Onshore",
        icon="mdi:wind-turbine",
        native_unit_of_measurement="GW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_latest_ned_value(data, "wind_onshore"),
        attributes_fn=lambda data: _get_ned_forecast_attributes(data, "wind_onshore"),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_WIND_OFFSHORE,
        name="NED Wind Offshore",
        icon="mdi:wind-turbine",
        native_unit_of_measurement="GW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_latest_ned_value(data, "wind_offshore"),
        attributes_fn=lambda data: _get_ned_forecast_attributes(data, "wind_offshore"),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_SOLAR,
        name="NED Solar",
        icon="mdi:solar-power",
        native_unit_of_measurement="GW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_latest_ned_value(data, "solar"),
        attributes_fn=lambda data: _get_ned_forecast_attributes(data, "solar"),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_RESTLAST,
        name="NED Restlast",
        icon="mdi:transmission-tower",
        native_unit_of_measurement="GW",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_latest_ned_value(data, "restlast"),
        attributes_fn=lambda data: _get_restlast_attributes(data),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_CHARGE_ADVICE,
        name="Charge Advice",
        icon="mdi:ev-station",
        value_fn=lambda data: data.get("charge_advice", {}).get("advice", ADVICE_NO_DATA),
        attributes_fn=lambda data: _get_charge_advice_attributes(data),
    ),
    ChargeforecastSensorEntityDescription(
        key=SENSOR_TYPE_MODEL_ACCURACY,
        name="Model Accuracy",
        icon="mdi:chart-line",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _get_model_accuracy(data),
        attributes_fn=lambda data: _get_model_attributes(data),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Charge Forecast sensors from a config entry."""
    coordinator: ChargeforecastDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ChargeforecastSensor(coordinator, description)
        for description in SENSOR_TYPES
    ]

    async_add_entities(entities)


class ChargeforecastSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Charge Forecast sensor."""

    entity_description: ChargeforecastSensorEntityDescription

    def __init__(
        self,
        coordinator: ChargeforecastDataUpdateCoordinator,
        description: ChargeforecastSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_has_entity_name = True

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.data is None:
            return {}

        if self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)

        return {}

    @property
    def icon(self) -> str | None:
        """Return icon based on state."""
        # Special handling for charge advice sensor
        if self.entity_description.key == SENSOR_TYPE_CHARGE_ADVICE:
            state = self.native_value
            if state == ADVICE_CHARGE_SOON:
                return "mdi:battery-charging-100"
            elif state == ADVICE_WAIT_2_3_DAYS:
                return "mdi:clock-time-four-outline"
            elif state == ADVICE_WAIT_4_7_DAYS:
                return "mdi:calendar-clock"
            else:
                return "mdi:help-circle-outline"

        return self.entity_description.icon


# Helper functions for extracting data


def _get_latest_ned_value(data: dict[str, Any], field: str) -> float | None:
    """Get latest NED value for a field."""
    ned_data = data.get("ned_data", {})
    forecast = ned_data.get("forecast", [])

    if not forecast:
        return None

    # Find closest to now
    now = dt_util.now()
    closest = min(forecast, key=lambda x: abs((x["timestamp"] - now).total_seconds()))

    return round(closest.get(field, 0), 2)


def _get_ned_forecast_attributes(data: dict[str, Any], field: str) -> dict[str, Any]:
    """Get forecast attributes for a NED field."""
    ned_data = data.get("ned_data", {})
    forecast = ned_data.get("forecast", [])

    if not forecast:
        return {}

    # Get next 24 hours
    now = dt_util.now()
    next_24h = [
        {
            "time": f["timestamp"].isoformat(),
            "value": round(f.get(field, 0), 2),
        }
        for f in forecast
        if 0 <= (f["timestamp"] - now).total_seconds() / 3600 <= 24
    ]

    # Calculate stats
    values = [f.get(field, 0) for f in forecast[:24]]
    
    return {
        "forecast_24h": next_24h[:24],
        "min_24h": round(min(values), 2) if values else None,
        "max_24h": round(max(values), 2) if values else None,
        "avg_24h": round(sum(values) / len(values), 2) if values else None,
        "unit_of_measurement": "GW",
    }


def _get_restlast_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Get restlast specific attributes."""
    ned_data = data.get("ned_data", {})
    forecast = ned_data.get("forecast", [])
    calibration = data.get("calibration", {})

    if not forecast:
        return {}

    now = dt_util.now()
    next_24h = [
        {
            "time": f["timestamp"].isoformat(),
            "restlast": round(f.get("restlast", 0), 2),
            "consumption": round(f.get("consumption", 0), 2),
            "renewables": round(
                f.get("wind_onshore", 0)
                + f.get("wind_offshore", 0)
                + f.get("solar", 0),
                2,
            ),
        }
        for f in forecast
        if 0 <= (f["timestamp"] - now).total_seconds() / 3600 <= 24
    ]

    values = [f.get("restlast", 0) for f in forecast[:24]]

    return {
        "forecast_24h": next_24h[:24],
        "min_24h": round(min(values), 2) if values else None,
        "max_24h": round(max(values), 2) if values else None,
        "avg_24h": round(sum(values) / len(values), 2) if values else None,
        "model_multiplier": calibration.get("multiplier"),
        "model_offset": calibration.get("offset"),
        "unit_of_measurement": "GW",
    }


def _get_charge_advice_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Get charge advice attributes."""
    advice_data = data.get("charge_advice", {})
    calibration = data.get("calibration", {})
    price_forecast = data.get("price_forecast", [])

    if not advice_data:
        return {}

    best_window = advice_data.get("best_window", {})
    best_now = advice_data.get("best_now", {})
    
    attrs = {
        "advice": advice_data.get("advice"),
        "savings_ct_per_kwh": advice_data.get("savings_vs_now", 0),
    }

    # Best charging window
    if best_window:
        attrs.update({
            "best_start_time": best_window.get("start").isoformat() if best_window.get("start") else None,
            "best_end_time": best_window.get("end").isoformat() if best_window.get("end") else None,
            "best_avg_price": best_window.get("avg_price"),
            "best_prices": best_window.get("prices", []),
        })

    # Current window for comparison
    if best_now:
        attrs.update({
            "current_best_start": best_now.get("start").isoformat() if best_now.get("start") else None,
            "current_best_price": best_now.get("avg_price"),
        })

    # Model info
    attrs.update({
        "model_multiplier": calibration.get("multiplier"),
        "model_offset": calibration.get("offset"),
        "model_r2_score": calibration.get("r2_score"),
        "model_mae": calibration.get("mae"),
        "last_calibration": calibration.get("last_update").isoformat()
        if calibration.get("last_update")
        else None,
    })

    # Price forecast next 24h
    now = dt_util.now()
    next_24h_prices = [
        {
            "time": p["timestamp"].isoformat(),
            "price": p["price"],
            "price_low": p.get("price_low"),
            "price_high": p.get("price_high"),
        }
        for p in price_forecast
        if 0 <= (p["timestamp"] - now).total_seconds() / 3600 <= 24
    ]
    attrs["price_forecast_24h"] = next_24h_prices[:24]

    return attrs


def _get_model_accuracy(data: dict[str, Any]) -> float | None:
    """Get model R² score as percentage."""
    calibration = data.get("calibration", {})
    r2 = calibration.get("r2_score")

    if r2 is None:
        return None

    return round(r2 * 100, 1)  # Convert to percentage


def _get_model_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Get model accuracy attributes."""
    calibration = data.get("calibration", {})

    return {
        "r2_score": calibration.get("r2_score"),
        "mae_ct_per_kwh": calibration.get("mae"),
        "multiplier": calibration.get("multiplier"),
        "offset": calibration.get("offset"),
        "last_calibration": calibration.get("last_update").isoformat()
        if calibration.get("last_update")
        else None,
        "interpretation": _interpret_r2(calibration.get("r2_score")),
    }


def _interpret_r2(r2: float | None) -> str:
    """Interpret R² score."""
    if r2 is None:
        return "No calibration yet"
    elif r2 >= 0.8:
        return "Excellent - model explains >80% of price variation"
    elif r2 >= 0.7:
        return "Good - model explains >70% of price variation"
    elif r2 >= 0.5:
        return "Fair - model explains >50% of price variation"
    elif r2 >= 0.3:
        return "Poor - limited predictive power"
    else:
        return "Very poor - model not reliable"

