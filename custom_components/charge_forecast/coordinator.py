"""DataUpdateCoordinator for Charge Forecast."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    NED_TYPE_CONSUMPTION,
    NED_TYPE_SOLAR,
    NED_TYPE_WIND_OFFSHORE,
    NED_TYPE_WIND_ONSHORE,
    MODEL_MAX_MULTIPLIER,
    MODEL_MAX_OFFSET,
    MODEL_MIN_MULTIPLIER,
    MODEL_MIN_OFFSET,
    MODEL_MIN_R2,
    MODEL_MIN_SAMPLES,
)

_LOGGER = logging.getLogger(__name__)

NED_API_BASE = "https://api.ned.nl/v1"
NED_POINT_NL = 247  # Nederland identifier


class ChargeforecastDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching NED data and calibrating pricing model."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        nordpool_entity: str,
        update_interval: timedelta,
        calibration_interval: timedelta,
        lookback_days: int,
    ) -> None:
        """Initialize coordinator."""
        self.session = session
        self.nordpool_entity = nordpool_entity
        self.calibration_interval = calibration_interval
        self.lookback_days = lookback_days

        # Model parameters
        self.multiplier = 1.27  # Start waarde
        self.offset = 1.5
        self.last_calibration: datetime | None = None
        self.calibration_r2: float | None = None
        self.calibration_mae: float | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from NED API."""
        try:
            # 1. Haal NED data op
            ned_data = await self._fetch_ned_data()

            # 2. Calibreer model indien nodig
            if (
                self.last_calibration is None
                or dt_util.now() - self.last_calibration > self.calibration_interval
            ):
                await self._calibrate_pricing_model()

            # 3. Bereken prijsvoorspelling
            price_forecast = self._calculate_price_forecast(ned_data)

            # 4. Bepaal laadadvies
            charge_advice = self._calculate_charge_advice(price_forecast)

            return {
                "ned_data": ned_data,
                "price_forecast": price_forecast,
                "charge_advice": charge_advice,
                "calibration": {
                    "multiplier": self.multiplier,
                    "offset": self.offset,
                    "last_update": self.last_calibration,
                    "r2_score": self.calibration_r2,
                    "mae": self.calibration_mae,
                },
            }

        except Exception as err:
            raise UpdateFailed(f"Error fetching NED data: {err}") from err

    async def _fetch_ned_data(self) -> dict[str, Any]:
        """Fetch utilization data from NED API."""
        now = dt_util.now()
        
        # NED API parameters voor forecast data (7 dagen vooruit)
        params = {
            "point": NED_POINT_NL,
            "granularity": 4,  # Hourly
            "classification": 2,  # Forecast
            "activity": 1,  # Providing
            "validfrom[after]": now.isoformat(),
            "validfrom[before]": (now + timedelta(days=7)).isoformat(),
            "itemsPerPage": 200,
        }

        results = {
            "consumption": [],
            "wind_onshore": [],
            "wind_offshore": [],
            "solar": [],
        }

        # Haal data op per type
        for data_type, type_id in [
            ("consumption", NED_TYPE_CONSUMPTION),
            ("wind_onshore", NED_TYPE_WIND_ONSHORE),
            ("wind_offshore", NED_TYPE_WIND_OFFSHORE),
            ("solar", NED_TYPE_SOLAR),
        ]:
            type_params = {**params, "type": type_id}
            
            try:
                async with self.session.get(
                    f"{NED_API_BASE}/utilizations",
                    params=type_params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        _LOGGER.warning(
                            f"NED API returned {response.status} for type {data_type}"
                        )
                        continue

                    data = await response.json()
                    
                    # Parse hydra response
                    if "hydra:member" in data:
                        for item in data["hydra:member"]:
                            results[data_type].append({
                                "timestamp": datetime.fromisoformat(
                                    item["validfrom"].replace("Z", "+00:00")
                                ),
                                "volume": float(item.get("volume", 0)) / 1000,  # MW -> GW
                                "capacity": float(item.get("capacity", 0)) / 1000,
                            })

            except Exception as err:
                _LOGGER.error(f"Error fetching {data_type}: {err}")
                continue

        # Bereken restlast per timestamp
        forecast = []
        timestamps = set(item["timestamp"] for item in results["consumption"])
        
        for ts in sorted(timestamps):
            consumption = next(
                (i["volume"] for i in results["consumption"] if i["timestamp"] == ts),
                0,
            )
            wind_onshore = next(
                (i["volume"] for i in results["wind_onshore"] if i["timestamp"] == ts),
                0,
            )
            wind_offshore = next(
                (i["volume"] for i in results["wind_offshore"] if i["timestamp"] == ts),
                0,
            )
            solar = next(
                (i["volume"] for i in results["solar"] if i["timestamp"] == ts), 0
            )

            restlast = consumption - (wind_onshore + wind_offshore + solar)

            forecast.append({
                "timestamp": ts,
                "consumption": consumption,
                "wind_onshore": wind_onshore,
                "wind_offshore": wind_offshore,
                "solar": solar,
                "restlast": restlast,
            })

        return {"forecast": forecast, "raw": results}

    async def _calibrate_pricing_model(self) -> None:
        """Calibrate pricing model based on historical data."""
        _LOGGER.info("Starting pricing model calibration...")

        try:
            # 1. Haal historische Nordpool prijzen op
            nordpool_state = self.hass.states.get(self.nordpool_entity)

            if not nordpool_state:
                _LOGGER.warning(f"Nordpool sensor {self.nordpool_entity} not found")
                return

            # 2. Haal historische data via recorder
            historical_prices = await self._get_historical_nordpool_prices(
                self.nordpool_entity, self.lookback_days
            )

            if not historical_prices or len(historical_prices) < MODEL_MIN_SAMPLES:
                _LOGGER.warning(
                    f"Insufficient data for calibration: {len(historical_prices)} samples"
                )
                return

            # 3. Haal bijbehorende NED restlast op
            historical_restlast = await self._get_historical_ned_restlast(
                [h["timestamp"] for h in historical_prices]
            )

            # 4. Match data
            matched_data = []
            for price_point in historical_prices:
                ts = price_point["timestamp"]
                restlast = historical_restlast.get(ts)

                if restlast is not None and price_point["price"] is not None:
                    matched_data.append({"restlast": restlast, "price": price_point["price"]})

            if len(matched_data) < MODEL_MIN_SAMPLES:
                _LOGGER.warning(f"Insufficient matched data: {len(matched_data)} points")
                return

            # 5. Linear regression
            xs = [d["restlast"] for d in matched_data]
            ys = [d["price"] for d in matched_data]

            new_mult, new_offset = self._fit_linear(xs, ys)

            # 6. Bereken accuracy
            predictions = [new_mult * x + new_offset for x in xs]
            r2 = self._calculate_r2(ys, predictions)
            mae = sum(abs(y - p) for y, p in zip(ys, predictions)) / len(ys)

            # 7. Update parameters (met sanity checks)
            if (
                MODEL_MIN_MULTIPLIER < new_mult < MODEL_MAX_MULTIPLIER
                and MODEL_MIN_OFFSET < new_offset < MODEL_MAX_OFFSET
                and r2 > MODEL_MIN_R2
            ):
                _LOGGER.info(
                    f"Calibration success: mult {self.multiplier:.3f} → {new_mult:.3f}, "
                    f"offset {self.offset:.2f} → {new_offset:.2f} "
                    f"(R²={r2:.3f}, MAE={mae:.2f}ct)"
                )
                self.multiplier = new_mult
                self.offset = new_offset
                self.calibration_r2 = r2
                self.calibration_mae = mae
                self.last_calibration = dt_util.now()
            else:
                _LOGGER.warning(
                    f"Calibration rejected: mult={new_mult:.3f}, "
                    f"offset={new_offset:.2f}, R²={r2:.3f}"
                )

        except Exception as err:
            _LOGGER.error(f"Calibration failed: {err}")

    def _fit_linear(self, xs: list[float], ys: list[float]) -> tuple[float, float]:
        """Simple linear regression without numpy."""
        n = len(xs)
        if n < 2:
            return self.multiplier, self.offset

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        s_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        s_xx = sum((x - mean_x) ** 2 for x in xs)

        if s_xx < 0.01:
            return self.multiplier, self.offset

        a = s_xy / s_xx
        b = mean_y - a * mean_x

        return a, b

    def _calculate_r2(self, actuals: list[float], predictions: list[float]) -> float:
        """Calculate R² score."""
        n = len(actuals)
        if n == 0:
            return 0.0

        mean_actual = sum(actuals) / n
        ss_tot = sum((y - mean_actual) ** 2 for y in actuals)
        ss_res = sum((y - p) ** 2 for y, p in zip(actuals, predictions))

        if ss_tot < 0.0001:
            return 0.0

        return max(0.0, 1.0 - (ss_res / ss_tot))

    async def _get_historical_nordpool_prices(
        self, entity_id: str, days: int
    ) -> list[dict]:
        """Get historical Nordpool prices from recorder."""
        from homeassistant.components.recorder import history

        end_time = dt_util.now()
        start_time = end_time - timedelta(days=days)

        prices = []

        try:
            # Haal states op via recorder
            states = await self.hass.async_add_executor_job(
                history.state_changes_during_period,
                self.hass,
                start_time,
                end_time,
                entity_id,
            )

            if entity_id in states:
                for state in states[entity_id]:
                    # Nordpool raw_today heeft timestamps
                    raw_data = state.attributes.get("raw_today", [])
                    for entry in raw_data:
                        if "start" in entry and "value" in entry:
                            prices.append({
                                "timestamp": datetime.fromisoformat(entry["start"]),
                                "price": entry["value"] * 100,  # €/kWh → ct/kWh
                            })

        except Exception as err:
            _LOGGER.error(f"Error getting Nordpool history: {err}")

        return prices

    async def _get_historical_ned_restlast(
        self, timestamps: list[datetime]
    ) -> dict[datetime, float]:
        """Get historical NED restlast data."""
        # Voor historische NED data moeten we de realtime classification gebruiken
        result = {}
        
        if not timestamps:
            return result

        start_time = min(timestamps)
        end_time = max(timestamps)

        params = {
            "point": NED_POINT_NL,
            "granularity": 4,  # Hourly
            "classification": 1,  # Near-realtime (niet forecast!)
            "activity": 1,  # Providing
            "validfrom[after]": start_time.isoformat(),
            "validfrom[before]": end_time.isoformat(),
            "itemsPerPage": 200,
        }

        try:
            # Haal consumption data op
            consumption_data = {}
            renewable_data = {}

            # Fetch alle types
            for data_type, type_id in [
                ("consumption", NED_TYPE_CONSUMPTION),
                ("wind_onshore", NED_TYPE_WIND_ONSHORE),
                ("wind_offshore", NED_TYPE_WIND_OFFSHORE),
                ("solar", NED_TYPE_SOLAR),
            ]:
                type_params = {**params, "type": type_id}
                
                async with self.session.get(
                    f"{NED_API_BASE}/utilizations",
                    params=type_params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if "hydra:member" in data:
                            for item in data["hydra:member"]:
                                ts = datetime.fromisoformat(
                                    item["validfrom"].replace("Z", "+00:00")
                                )
                                volume = float(item.get("volume", 0)) / 1000  # MW -> GW

                                if data_type == "consumption":
                                    consumption_data[ts] = volume
                                else:
                                    renewable_data.setdefault(ts, 0)
                                    renewable_data[ts] += volume

            # Bereken restlast
            for ts in consumption_data:
                if ts in renewable_data:
                    result[ts] = consumption_data[ts] - renewable_data[ts]

        except Exception as err:
            _LOGGER.error(f"Error fetching historical NED data: {err}")

        return result

    def _calculate_price_forecast(self, ned_data: dict) -> list[dict]:
        """Calculate price forecast based on restlast."""
        forecast = []

        for hour_data in ned_data.get("forecast", []):
            restlast_gw = hour_data.get("restlast", 0)
            timestamp = hour_data["timestamp"]

            # Prijsformule: prijs = multiplier * restlast + offset
            price = (self.multiplier * restlast_gw) + self.offset

            # Confidence interval (wordt groter verder in de toekomst)
            hours_ahead = (timestamp - dt_util.now()).total_seconds() / 3600
            confidence_std = 0.5 + (hours_ahead / 48) * 1.5  # 0.5→2.0 ct

            forecast.append({
                "timestamp": timestamp,
                "price": round(price, 2),
                "price_low": round(price - confidence_std, 2),
                "price_high": round(price + confidence_std, 2),
                "confidence_std": round(confidence_std, 2),
                "restlast_gw": round(restlast_gw, 2),
            })

        return forecast

    def _calculate_charge_advice(self, price_forecast: list[dict]) -> dict:
        """Calculate charging advice based on price forecast."""
        if not price_forecast:
            return {"advice": "NO_DATA"}

        now = dt_util.now()

        # Splits in tijdvensters
        window_0_48h = [
            p for p in price_forecast if 0 <= self._hours_from_now(p["timestamp"]) < 48
        ]
        window_48_96h = [
            p
            for p in price_forecast
            if 48 <= self._hours_from_now(p["timestamp"]) < 96
        ]
        window_96_168h = [
            p
            for p in price_forecast
            if 96 <= self._hours_from_now(p["timestamp"]) < 168
        ]

        # Vind beste 4-uur blok per venster
        best_now = self._find_best_block(window_0_48h, hours=4)
        best_later = self._find_best_block(window_48_96h, hours=4)
        best_much_later = self._find_best_block(window_96_168h, hours=4)

        # Bepaal advies
        if not best_now:
            return {"advice": "NO_DATA"}

        if best_later and best_later["avg_price"] < best_now["avg_price"] * 0.90:
            advice = "WAIT_2_3_DAYS"
            best_option = best_later
            savings = best_now["avg_price"] - best_later["avg_price"]
        elif (
            best_much_later
            and best_much_later["avg_price"] < best_now["avg_price"] * 0.85
        ):
            advice = "WAIT_4_7_DAYS"
            best_option = best_much_later
            savings = best_now["avg_price"] - best_much_later["avg_price"]
        else:
            advice = "CHARGE_SOON"
            best_option = best_now
            savings = 0

        return {
            "advice": advice,
            "best_window": best_option,
            "savings_vs_now": round(savings, 2) if savings else 0,
            "best_now": best_now,
            "best_later": best_later,
            "best_much_later": best_much_later,
        }

    def _find_best_block(
        self, prices: list[dict], hours: int = 4
    ) -> dict[str, Any] | None:
        """Find cheapest consecutive block."""
        if not prices or len(prices) < hours:
            return None

        best = None
        for i in range(len(prices) - hours + 1):
            block = prices[i : i + hours]
            avg_price = sum(p["price"] for p in block) / hours

            if best is None or avg_price < best["avg_price"]:
                best = {
                    "start": block[0]["timestamp"],
                    "end": block[-1]["timestamp"],
                    "avg_price": round(avg_price, 2),
                    "prices": [p["price"] for p in block],
                }

        return best

    def _hours_from_now(self, timestamp: datetime) -> float:
        """Calculate hours from now."""
        delta = timestamp - dt_util.now()
        return delta.total_seconds() / 3600
