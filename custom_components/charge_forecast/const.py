"""Constants for the Charge Forecast integration."""
from datetime import timedelta

DOMAIN = "charge_forecast"
NAME = "Charge Forecast"

# Configuration
CONF_CHARGING_DURATION = "charging_duration"
DEFAULT_CHARGING_DURATION = 3  # hours

# Update interval
DEFAULT_SCAN_INTERVAL = timedelta(minutes=15)

# EPEX sensor from NED-forecast integration
EPEX_SENSOR_ENTITY_ID = "sensor.forecast_epex_price"

# Sensor types (windows in hours)
SENSOR_WINDOWS = {
    "24h": 24,
    "36h": 36,
    "72h": 72,
    "96h": 96,
    "144h": 144,
}
