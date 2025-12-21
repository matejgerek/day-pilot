from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from daypilot.services.config import ConfigError, WhoopConfig, update_config
from daypilot.services.whoop_oauth import WHOOP_TOKEN_URL
from daypilot.settings import get_settings

WHOOP_API_BASE_URL = "https://api.prod.whoop.com/developer"
DEFAULT_TIMEOUT_SECONDS = 30

T = TypeVar("T")


class WhoopServiceError(RuntimeError):
    """Raised when WHOOP data cannot be fetched or parsed."""


@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    records: list[T]
    next_token: str | None


@dataclass(frozen=True)
class WhoopCycle:
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime | None
    timezone_offset: str
    score_state: str
    score: dict[str, Any] | None


@dataclass(frozen=True)
class WhoopSleep:
    id: str
    cycle_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    nap: bool
    score_state: str
    score: dict[str, Any] | None


@dataclass(frozen=True)
class WhoopRecovery:
    cycle_id: int
    sleep_id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: str
    score: dict[str, Any] | None


@dataclass(frozen=True)
class WhoopWorkout:
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    start: datetime
    end: datetime
    timezone_offset: str
    sport_name: str
    score_state: str
    sport_id: int | None
    score: dict[str, Any] | None


@dataclass(frozen=True)
class WhoopProfile:
    user_id: int
    email: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class WhoopBodyMeasurement:
    height_meter: float
    weight_kilogram: float
    max_heart_rate: int


@dataclass(frozen=True)
class WhoopSnapshot:
    cycle: WhoopCycle | None
    recovery: WhoopRecovery | None
    sleep: WhoopSleep | None
    workouts: list[WhoopWorkout]
    profile: WhoopProfile | None
    body: WhoopBodyMeasurement | None


class WhoopDataService:
    """Fetch WHOOP data using stored OAuth credentials."""

    def __init__(
        self,
        config: WhoopConfig,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str = WHOOP_API_BASE_URL,
        config_base_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self._config = config
        self._client_id = client_id or settings.whoop_client_id
        self._client_secret = client_secret or settings.whoop_client_secret
        self._base_url = base_url.rstrip("/")
        self._config_base_dir = config_base_dir

    @property
    def config(self) -> WhoopConfig:
        return self._config

    def get_latest_cycle(self) -> WhoopCycle | None:
        response = self._get_paginated("/v2/cycle", limit=1, parser=_parse_cycle)
        return response.records[0] if response.records else None

    def get_latest_recovery(self) -> WhoopRecovery | None:
        response = self._get_paginated("/v2/recovery", limit=1, parser=_parse_recovery)
        return response.records[0] if response.records else None

    def get_recovery_for_cycle(self, cycle_id: int) -> WhoopRecovery | None:
        try:
            data = self._get(f"/v2/cycle/{cycle_id}/recovery")
        except WhoopServiceError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return _parse_recovery(data)

    def get_latest_sleep(self) -> WhoopSleep | None:
        response = self._get_paginated("/v2/activity/sleep", limit=1, parser=_parse_sleep)
        return response.records[0] if response.records else None

    def get_sleep_for_cycle(self, cycle_id: int) -> WhoopSleep | None:
        try:
            data = self._get(f"/v2/cycle/{cycle_id}/sleep")
        except WhoopServiceError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return _parse_sleep(data)

    def get_latest_workouts(self, limit: int = 3) -> list[WhoopWorkout]:
        response = self._get_paginated("/v2/activity/workout", limit=limit, parser=_parse_workout)
        return response.records

    def get_profile(self) -> WhoopProfile:
        data = self._get("/v2/user/profile/basic")
        return _parse_profile(data)

    def get_body_measurement(self) -> WhoopBodyMeasurement:
        data = self._get("/v2/user/measurement/body")
        return _parse_body_measurement(data)

    def get_snapshot(self) -> WhoopSnapshot:
        cycle = self.get_latest_cycle()
        recovery = self.get_recovery_for_cycle(cycle.id) if cycle else self.get_latest_recovery()
        sleep = self.get_sleep_for_cycle(cycle.id) if cycle else self.get_latest_sleep()
        workouts = self.get_latest_workouts()
        profile = self.get_profile()
        body = self.get_body_measurement()
        return WhoopSnapshot(
            cycle=cycle,
            recovery=recovery,
            sleep=sleep,
            workouts=workouts,
            profile=profile,
            body=body,
        )

    def _get_paginated(
        self,
        path: str,
        limit: int,
        parser: Callable[[dict[str, Any]], T],
    ) -> PaginatedResponse[T]:
        data = self._get(path, params={"limit": str(limit)})
        records_raw = data.get("records")
        if not isinstance(records_raw, list):
            raise WhoopServiceError(f"Unexpected records payload from {path}: {data}")

        records: list[T] = []
        for entry in records_raw:
            if isinstance(entry, dict):
                records.append(parser(entry))
        next_token = _optional_str(data.get("next_token"))
        return PaginatedResponse(records=records, next_token=next_token)

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        self._refresh_if_expiring()
        return self._request("GET", path, params=params, retry_on_unauthorized=True)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None,
        retry_on_unauthorized: bool,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        request = urllib.request.Request(
            url,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": _auth_header(self._config),
                "User-Agent": "daypilot/0.1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            if exc.code == 401 and retry_on_unauthorized and self._refresh_tokens():
                return self._request(method, path, params, retry_on_unauthorized=False)
            raise WhoopServiceError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WhoopServiceError("Network error while calling WHOOP API.") from exc

        payload = _parse_json(raw)
        self._touch_last_sync()
        return payload

    def _refresh_if_expiring(self) -> None:
        if self._config.expires_at is None:
            return
        now = datetime.now(timezone.utc)
        if self._config.expires_at <= now + timedelta(seconds=60):
            self._refresh_tokens()

    def _refresh_tokens(self) -> bool:
        if not self._config.refresh_token:
            return False
        if not self._client_id or not self._client_secret:
            return False

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._config.refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "offline",
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            WHOOP_TOKEN_URL,
            data=data,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "daypilot/0.1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise WhoopServiceError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WhoopServiceError("Network error while refreshing WHOOP token.") from exc

        payload_data = _parse_json(raw)
        access_token = _required_str(payload_data, "access_token")
        refresh_token = (
            _optional_str(payload_data.get("refresh_token")) or self._config.refresh_token
        )
        expires_in = _optional_int(payload_data.get("expires_in"))
        token_type = _optional_str(payload_data.get("token_type")) or self._config.token_type
        scope = _optional_str(payload_data.get("scope")) or self._config.scope

        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        self._config = WhoopConfig(
            access_token=access_token,
            refresh_token=refresh_token,
            scope=scope,
            token_type=token_type,
            expires_at=expires_at,
            connected_at=self._config.connected_at,
            last_sync_at=self._config.last_sync_at,
        )
        self._persist_tokens()
        return True

    def _persist_tokens(self) -> None:
        payload = {"whoop": _serialize_whoop(self._config)}
        try:
            update_config(payload, base_dir=self._config_base_dir)
        except ConfigError as exc:
            raise WhoopServiceError("Failed to persist WHOOP tokens.") from exc

    def _touch_last_sync(self) -> None:
        now = datetime.now(timezone.utc)
        self._config = WhoopConfig(
            access_token=self._config.access_token,
            refresh_token=self._config.refresh_token,
            scope=self._config.scope,
            token_type=self._config.token_type,
            expires_at=self._config.expires_at,
            connected_at=self._config.connected_at,
            last_sync_at=now,
        )
        payload = {"whoop": _serialize_whoop(self._config)}
        try:
            update_config(payload, base_dir=self._config_base_dir)
        except ConfigError as exc:
            raise WhoopServiceError("Failed to persist WHOOP last_sync_at.") from exc


def _parse_cycle(data: dict[str, Any]) -> WhoopCycle:
    return WhoopCycle(
        id=_required_int(data, "id"),
        user_id=_required_int(data, "user_id"),
        created_at=_required_datetime(data, "created_at"),
        updated_at=_required_datetime(data, "updated_at"),
        start=_required_datetime(data, "start"),
        end=_optional_datetime(data.get("end")),
        timezone_offset=_required_str(data, "timezone_offset"),
        score_state=_required_str(data, "score_state"),
        score=_optional_dict(data.get("score")),
    )


def _parse_sleep(data: dict[str, Any]) -> WhoopSleep:
    return WhoopSleep(
        id=_required_str(data, "id"),
        cycle_id=_required_int(data, "cycle_id"),
        user_id=_required_int(data, "user_id"),
        created_at=_required_datetime(data, "created_at"),
        updated_at=_required_datetime(data, "updated_at"),
        start=_required_datetime(data, "start"),
        end=_required_datetime(data, "end"),
        timezone_offset=_required_str(data, "timezone_offset"),
        nap=_required_bool(data, "nap"),
        score_state=_required_str(data, "score_state"),
        score=_optional_dict(data.get("score")),
    )


def _parse_recovery(data: dict[str, Any]) -> WhoopRecovery:
    return WhoopRecovery(
        cycle_id=_required_int(data, "cycle_id"),
        sleep_id=_required_str(data, "sleep_id"),
        user_id=_required_int(data, "user_id"),
        created_at=_required_datetime(data, "created_at"),
        updated_at=_required_datetime(data, "updated_at"),
        score_state=_required_str(data, "score_state"),
        score=_optional_dict(data.get("score")),
    )


def _parse_workout(data: dict[str, Any]) -> WhoopWorkout:
    return WhoopWorkout(
        id=_required_str(data, "id"),
        user_id=_required_int(data, "user_id"),
        created_at=_required_datetime(data, "created_at"),
        updated_at=_required_datetime(data, "updated_at"),
        start=_required_datetime(data, "start"),
        end=_required_datetime(data, "end"),
        timezone_offset=_required_str(data, "timezone_offset"),
        sport_name=_required_str(data, "sport_name"),
        score_state=_required_str(data, "score_state"),
        sport_id=_optional_int(data.get("sport_id")),
        score=_optional_dict(data.get("score")),
    )


def _parse_profile(data: dict[str, Any]) -> WhoopProfile:
    return WhoopProfile(
        user_id=_required_int(data, "user_id"),
        email=_required_str(data, "email"),
        first_name=_required_str(data, "first_name"),
        last_name=_required_str(data, "last_name"),
    )


def _parse_body_measurement(data: dict[str, Any]) -> WhoopBodyMeasurement:
    return WhoopBodyMeasurement(
        height_meter=_required_float(data, "height_meter"),
        weight_kilogram=_required_float(data, "weight_kilogram"),
        max_heart_rate=_required_int(data, "max_heart_rate"),
    )


def _parse_json(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise WhoopServiceError(
            "WHOOP API returned invalid JSON: " + raw.decode("utf-8", errors="replace")
        ) from exc
    if not isinstance(payload, dict):
        raise WhoopServiceError(f"Unexpected WHOOP response payload: {payload}")
    return payload


def _auth_header(config: WhoopConfig) -> str:
    token_type = (config.token_type or "bearer").strip()
    return f"{token_type.title()} {config.access_token}"


def _parse_datetime(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WhoopServiceError(f"Invalid datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WhoopServiceError(f"Missing or invalid `{key}`.")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str or None


def _required_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise WhoopServiceError(f"Missing or invalid `{key}`.") from exc


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_float(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise WhoopServiceError(f"Missing or invalid `{key}`.") from exc


def _required_bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise WhoopServiceError(f"Missing or invalid `{key}`.")


def _required_datetime(data: dict[str, Any], key: str) -> datetime:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WhoopServiceError(f"Missing or invalid `{key}`.")
    return _parse_datetime(value)


def _optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _parse_datetime(value)


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    return value


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


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
