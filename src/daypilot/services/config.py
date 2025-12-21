from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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
    whoop: "WhoopConfig | None" = None


@dataclass(frozen=True)
class WhoopConfig:
    access_token: str
    refresh_token: str | None
    scope: str | None
    token_type: str | None
    expires_at: datetime | None
    connected_at: datetime
    last_sync_at: datetime | None


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

    whoop_data = data.get("whoop")
    return AppConfig(
        location=_parse_location(location_data),
        whoop=_parse_whoop(whoop_data),
    )


def write_config(config: AppConfig, base_dir: Path | None = None) -> None:
    path = ensure_config_dir(base_dir)
    payload: dict[str, Any] = {
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
    if config.whoop:
        payload["whoop"] = _serialize_whoop(config.whoop)
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

    config = AppConfig(
        location=_parse_location(location_data),
        whoop=_parse_whoop(merged.get("whoop")),
    )
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


def _parse_whoop(data: Any) -> WhoopConfig | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigError("WHOOP payload is invalid")

    access_token = _required_str(data, "access_token")
    connected_at = _required_datetime(data, "connected_at")

    return WhoopConfig(
        access_token=access_token,
        refresh_token=_optional_str(data, "refresh_token"),
        scope=_optional_str(data, "scope"),
        token_type=_optional_str(data, "token_type"),
        expires_at=_optional_datetime(data, "expires_at"),
        connected_at=connected_at,
        last_sync_at=_optional_datetime(data, "last_sync_at"),
    )


def _serialize_whoop(config: WhoopConfig) -> dict[str, Any]:
    return {
        "access_token": config.access_token,
        "refresh_token": config.refresh_token,
        "scope": config.scope,
        "token_type": config.token_type,
        "expires_at": _format_datetime(config.expires_at),
        "connected_at": _format_datetime(config.connected_at),
        "last_sync_at": _format_datetime(config.last_sync_at),
    }


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


def _required_datetime(data: dict[str, Any], key: str) -> datetime:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigMissingError(f"WHOOP is missing `{key}`.")
    return _parse_datetime(value, key)


def _optional_datetime(data: dict[str, Any], key: str) -> datetime | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return _parse_datetime(value, key)


def _parse_datetime(value: str, key: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid datetime for `{key}`.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


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
