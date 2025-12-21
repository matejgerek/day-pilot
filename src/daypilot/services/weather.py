from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry

from daypilot.services.config import LocationConfig


@dataclass(frozen=True)
class HourlyForecast:
    time: datetime
    temperature_c: float
    precipitation_probability: float | None
    wind_speed_kph: float | None
    condition: str | None


@dataclass(frozen=True)
class DailyOverview:
    summary: str
    temperature_min_c: float | None
    temperature_max_c: float | None
    precipitation_probability_max: float | None
    wind_speed_max_kph: float | None


@dataclass(frozen=True)
class WeatherReport:
    overview: DailyOverview
    hourly: list[HourlyForecast]
    timezone: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WeatherReport":
        overview_data = data.get("overview", {})
        hourly_data = data.get("hourly", [])
        timezone_name = data.get("timezone", "UTC")
        tz = ZoneInfo(timezone_name)

        overview = DailyOverview(
            summary=str(overview_data.get("summary", "Unknown")),
            temperature_min_c=_optional_number(overview_data.get("temperature_min_c")),
            temperature_max_c=_optional_number(overview_data.get("temperature_max_c")),
            precipitation_probability_max=_optional_number(
                overview_data.get("precipitation_probability_max")
            ),
            wind_speed_max_kph=_optional_number(overview_data.get("wind_speed_max_kph")),
        )

        hourly: list[HourlyForecast] = []
        for entry in hourly_data:
            if not isinstance(entry, dict):
                continue
            time_str = entry.get("time")
            if not time_str:
                continue
            time_value = datetime.fromisoformat(time_str)
            if time_value.tzinfo is None:
                time_value = time_value.replace(tzinfo=tz)

            hourly.append(
                HourlyForecast(
                    time=time_value,
                    temperature_c=float(entry.get("temperature_c")),
                    precipitation_probability=_optional_number(
                        entry.get("precipitation_probability")
                    ),
                    wind_speed_kph=_optional_number(entry.get("wind_speed_kph")),
                    condition=_optional_str(entry.get("condition")),
                )
            )

        return WeatherReport(overview=overview, hourly=hourly, timezone=timezone_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overview": {
                "summary": self.overview.summary,
                "temperature_min_c": self.overview.temperature_min_c,
                "temperature_max_c": self.overview.temperature_max_c,
                "precipitation_probability_max": self.overview.precipitation_probability_max,
                "wind_speed_max_kph": self.overview.wind_speed_max_kph,
            },
            "hourly": [
                {
                    "time": entry.time.isoformat(),
                    "temperature_c": entry.temperature_c,
                    "precipitation_probability": entry.precipitation_probability,
                    "wind_speed_kph": entry.wind_speed_kph,
                    "condition": entry.condition,
                }
                for entry in self.hourly
            ],
            "timezone": self.timezone,
        }


class WeatherServiceError(RuntimeError):
    """Raised when weather data cannot be fetched or parsed."""


class WeatherService:
    """Fetch weather context from Open-Meteo."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        cache_root = cache_dir or Path(".daypilot") / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_session = requests_cache.CachedSession(
            cache_root / "openmeteo",
            expire_after=3600,
        )
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        self._client = openmeteo_requests.Client(session=retry_session)

    def fetch(self, location: LocationConfig, now: datetime) -> WeatherReport:
        if now.tzinfo is None:
            raise WeatherServiceError("`now` must be timezone-aware")

        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": [
                "temperature_2m",
                "precipitation_probability",
                "weathercode",
                "windspeed_10m",
            ],
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "weathercode",
                "windspeed_10m_max",
            ],
            "timezone": "auto",
        }

        responses = self._client.weather_api(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
        )
        response = responses[0]

        tz_name = response.Timezone()
        if isinstance(tz_name, bytes):
            tz_name = tz_name.decode()
        tz = ZoneInfo(str(tz_name))
        now_local = now.astimezone(tz)
        midnight = (now_local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        hourly = response.Hourly()
        times = _build_time_range(hourly.Time(), hourly.TimeEnd(), hourly.Interval(), tz)
        temperature = hourly.Variables(0).ValuesAsNumpy()
        precipitation = hourly.Variables(1).ValuesAsNumpy()
        weather_code = hourly.Variables(2).ValuesAsNumpy()
        wind = hourly.Variables(3).ValuesAsNumpy()

        hourly_forecast: list[HourlyForecast] = []
        for idx, timestamp in enumerate(times):
            if timestamp < now_local or timestamp >= midnight:
                continue

            hourly_forecast.append(
                HourlyForecast(
                    time=timestamp,
                    temperature_c=float(temperature[idx]),
                    precipitation_probability=_optional_float(precipitation, idx),
                    wind_speed_kph=_optional_float(wind, idx),
                    condition=_weather_code_label(weather_code, idx),
                )
            )

        daily = response.Daily()
        overview = DailyOverview(
            summary=_daily_summary(daily),
            temperature_min_c=_optional_float(daily.Variables(1).ValuesAsNumpy(), 0),
            temperature_max_c=_optional_float(daily.Variables(0).ValuesAsNumpy(), 0),
            precipitation_probability_max=_optional_float(daily.Variables(2).ValuesAsNumpy(), 0),
            wind_speed_max_kph=_optional_float(daily.Variables(4).ValuesAsNumpy(), 0),
        )

        return WeatherReport(
            overview=overview,
            hourly=hourly_forecast,
            timezone=str(tz),
        )

    def format_for_prompt(self, report: WeatherReport) -> str:
        overview = report.overview
        overview_line = (
            f"Today: {overview.summary} | "
            f"{_format_range(overview.temperature_min_c, overview.temperature_max_c)}C "
            f"| Precip max {overview.precipitation_probability_max or 0:.0f}% "
            f"| Wind max {overview.wind_speed_max_kph or 0:.0f} km/h"
        )

        lines = [
            "Weather overview:",
            overview_line,
            "",
            "Hourly forecast (local time, now -> midnight):",
            "Hour | Temp | Precip | Wind | Condition",
        ]
        for entry in report.hourly:
            lines.append(
                f"{entry.time.strftime('%H:%M')} | "
                f"{entry.temperature_c:.0f}C | "
                f"{_format_optional_pct(entry.precipitation_probability)} | "
                f"{_format_optional_kph(entry.wind_speed_kph)} | "
                f"{entry.condition or 'Unknown'}"
            )

        return "\n".join(lines)

    def format_from_dict(self, data: dict[str, Any]) -> str:
        return self.format_for_prompt(WeatherReport.from_dict(data))


def _build_time_range(
    start_timestamp: int,
    end_timestamp: int,
    interval_seconds: int,
    tz: ZoneInfo,
) -> list[datetime]:
    start = datetime.fromtimestamp(start_timestamp, tz=timezone.utc).astimezone(tz)
    end = datetime.fromtimestamp(end_timestamp, tz=timezone.utc).astimezone(tz)

    times: list[datetime] = []
    current = start
    while current < end:
        times.append(current)
        current += timedelta(seconds=interval_seconds)
    return times


def _optional_float(values: np.ndarray, index: int) -> float | None:
    value = values[index]
    if value is None or np.isnan(value):
        return None
    return float(value)


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _format_range(min_val: float | None, max_val: float | None) -> str:
    if min_val is None and max_val is None:
        return "--"
    if min_val is None:
        return f"--/{max_val:.0f}"
    if max_val is None:
        return f"{min_val:.0f}/--"
    return f"{min_val:.0f}/{max_val:.0f}"


def _format_optional_pct(value: float | None) -> str:
    return "--" if value is None else f"{value:.0f}%"


def _format_optional_kph(value: float | None) -> str:
    return "--" if value is None else f"{value:.0f} km/h"


def _daily_summary(daily: Any) -> str:
    weather_code = daily.Variables(3).ValuesAsNumpy()
    return _weather_code_label(weather_code, 0) or "Unknown"


def _weather_code_label(values: np.ndarray, index: int) -> str | None:
    code_raw = values[index]
    if code_raw is None or np.isnan(code_raw):
        return None
    code = int(code_raw)
    return _WEATHER_CODE_LABELS.get(code, "Unknown")


_WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
