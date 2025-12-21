from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR_NAME = ".daypilot"
CONFIG_FILE_NAME = "config.json"


class ConfigError(RuntimeError):
    """Raised when config cannot be loaded or parsed."""


class ConfigMissingError(ConfigError):
    """Raised when required config is missing."""


@dataclass(frozen=True)
class LocationConfig:
    canonical_name: str
    city: str | None
    region: str | None
    country: str | None
    latitude: float
    longitude: float
    timezone: str | None


@dataclass(frozen=True)
class AppConfig:
    location: LocationConfig


def config_path(base_dir: Path | None = None) -> Path:
    base = base_dir or Path.cwd()
    return base / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def config_exists(base_dir: Path | None = None) -> bool:
    return config_path(base_dir).exists()


def ensure_config_dir(base_dir: Path | None = None) -> Path:
    path = config_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_config(base_dir: Path | None = None) -> AppConfig:
    path = config_path(base_dir)
    if not path.exists():
        raise ConfigMissingError("Config not found. Run `cli init` to set up your location.")

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError("Config file is not valid JSON") from exc

    location_data = data.get("location")
    if not isinstance(location_data, dict):
        raise ConfigMissingError("Location not configured. Run `cli init` to set up your location.")

    return AppConfig(location=_parse_location(location_data))


def write_config(config: AppConfig, base_dir: Path | None = None) -> None:
    path = ensure_config_dir(base_dir)
    payload = {
        "location": {
            "canonical_name": config.location.canonical_name,
            "city": config.location.city,
            "region": config.location.region,
            "country": config.location.country,
            "latitude": config.location.latitude,
            "longitude": config.location.longitude,
            "timezone": config.location.timezone,
        }
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def update_config(update: dict[str, Any], base_dir: Path | None = None) -> AppConfig:
    path = config_path(base_dir)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text())
        except json.JSONDecodeError:
            current = {}

    merged = _merge_dicts(current, update)
    location_data = merged.get("location")
    if not isinstance(location_data, dict):
        raise ConfigError("Location payload is invalid")

    config = AppConfig(location=_parse_location(location_data))
    write_config(config, base_dir)
    return config


def _parse_location(data: dict[str, Any]) -> LocationConfig:
    canonical_name = _required_str(data, "canonical_name")
    latitude = _required_float(data, "latitude")
    longitude = _required_float(data, "longitude")

    return LocationConfig(
        canonical_name=canonical_name,
        city=_optional_str(data, "city"),
        region=_optional_str(data, "region"),
        country=_optional_str(data, "country"),
        latitude=latitude,
        longitude=longitude,
        timezone=_optional_str(data, "timezone"),
    )


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigMissingError(
            f"Location is missing `{key}`. Run `cli init` to set up your location."
        )
    return value.strip()


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _required_float(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigMissingError(
            f"Location is missing `{key}`. Run `cli init` to set up your location."
        ) from exc


def _merge_dicts(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged
