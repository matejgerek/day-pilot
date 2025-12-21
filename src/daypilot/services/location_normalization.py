from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencage.geocoder import (
    ForbiddenError,
    InvalidInputError,
    NotAuthorizedError,
    OpenCageGeocode,
    RateLimitExceededError,
    UnknownError,
)

from daypilot.settings import get_settings


@dataclass(frozen=True)
class NormalizedLocation:
    canonical_name: str
    city: str | None
    region: str | None
    country: str | None
    latitude: float
    longitude: float
    timezone: str | None


class LocationNormalizationError(RuntimeError):
    """Raised when a location cannot be normalized."""


class LocationNormalizer:
    """Resolve free-form locations into canonical locations via OpenCage."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.opencage_api_key
        if not self._api_key:
            raise LocationNormalizationError("OPENCAGE_API_KEY is not set")
        self._geocoder = OpenCageGeocode(self._api_key)

    def resolve(self, query: str) -> NormalizedLocation:
        if not query or not query.strip():
            raise LocationNormalizationError("Location query is empty")

        try:
            results = self._geocoder.geocode(query, no_annotations=0)
        except (
            InvalidInputError,
            NotAuthorizedError,
            ForbiddenError,
            RateLimitExceededError,
            UnknownError,
        ) as exc:
            raise LocationNormalizationError(str(exc)) from exc

        if not results:
            raise LocationNormalizationError("No matching locations found")

        best = results[0]
        components = best.get("components", {})
        geometry = best.get("geometry", {})
        annotations = best.get("annotations", {})
        timezone = _get_nested_str(annotations, "timezone", "name")

        latitude = geometry.get("lat")
        longitude = geometry.get("lng")
        if latitude is None or longitude is None:
            raise LocationNormalizationError("Location coordinates are missing")

        return NormalizedLocation(
            canonical_name=str(best.get("formatted", "")).strip(),
            city=_pick_component(
                components,
                "city",
                "town",
                "village",
                "hamlet",
                "locality",
            ),
            region=_pick_component(components, "state", "region", "county"),
            country=_get_optional_str(components, "country"),
            latitude=float(latitude),
            longitude=float(longitude),
            timezone=timezone,
        )


def _pick_component(components: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _get_optional_str(components, key)
        if value:
            return value
    return None


def _get_optional_str(components: dict[str, Any], key: str) -> str | None:
    value = components.get(key)
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _get_nested_str(data: dict[str, Any], *keys: str) -> str | None:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if current is None:
        return None
    value = str(current).strip()
    return value or None
