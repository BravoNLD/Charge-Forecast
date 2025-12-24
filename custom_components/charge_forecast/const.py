"""Constants for Charge Forecast integration."""
from __future__ import annotations

DOMAIN = "charge_forecast"

# Config
CONF_NORDPOOL_ENTITY = "nordpool_entity"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CALIBRATION_INTERVAL = "calibration_interval"
CONF_LOOKBACK_DAYS = "lookback_days"

# Default values
DEFAULT_UPDATE_INTERVAL = 3600  # 1 uur
DEFAULT_CALIBRATION_INTERVAL = 86400  # 24 uur
DEFAULT_LOOKBACK_DAYS = 14  # 2 weken

# NED API Type IDs (van https://api.ned.nl/v1/types)
NED_TYPE_CONSUMPTION = 4  # "Consumption of Electricity"
NED_TYPE_WIND_ONSHORE = 6  # "Production of Electricity From Wind Onshore"
NED_TYPE_WIND_OFFSHORE = 7  # "Production of Electricity From Wind Offshore"
NED_TYPE_SOLAR = 8  # "Production of Electricity From Solar"

# Sensor types
SENSOR_TYPE_CONSUMPTION = "consumption"
SENSOR_TYPE_WIND_ONSHORE = "wind_onshore"
SENSOR_TYPE_WIND_OFFSHORE = "wind_offshore"
SENSOR_TYPE_SOLAR = "solar"
SENSOR_TYPE_RESTLAST = "restlast"
SENSOR_TYPE_CHARGE_ADVICE = "charge_advice"
SENSOR_TYPE_MODEL_ACCURACY = "model_accuracy"

# Advice states
ADVICE_CHARGE_SOON = "CHARGE_SOON"
ADVICE_WAIT_2_3_DAYS = "WAIT_2_3_DAYS"
ADVICE_WAIT_4_7_DAYS = "WAIT_4_7_DAYS"
ADVICE_NO_DATA = "NO_DATA"

# Model calibration parameters
MODEL_MIN_SAMPLES = 50  # Minimaal aantal datapunten voor calibratie
MODEL_MIN_R2 = 0.3  # Minimale R² score om model te accepteren
MODEL_MIN_MULTIPLIER = 0.5  # Minimale multiplier
MODEL_MAX_MULTIPLIER = 5.0  # Maximale multiplier
MODEL_MIN_OFFSET = -10.0  # Minimale offset (ct/kWh)
MODEL_MAX_OFFSET = 20.0  # Maximale offset (ct/kWh)

