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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "start": _format_datetime(self.start),
            "end": _format_datetime(self.end),
            "timezone_offset": self.timezone_offset,
            "score_state": self.score_state,
            "score": self.score,
        }


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cycle_id": self.cycle_id,
            "user_id": self.user_id,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "start": _format_datetime(self.start),
            "end": _format_datetime(self.end),
            "timezone_offset": self.timezone_offset,
            "nap": self.nap,
            "score_state": self.score_state,
            "score": self.score,
        }


@dataclass(frozen=True)
class WhoopRecovery:
    cycle_id: int
    sleep_id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    score_state: str
    score: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "sleep_id": self.sleep_id,
            "user_id": self.user_id,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "score_state": self.score_state,
            "score": self.score,
        }


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "created_at": _format_datetime(self.created_at),
            "updated_at": _format_datetime(self.updated_at),
            "start": _format_datetime(self.start),
            "end": _format_datetime(self.end),
            "timezone_offset": self.timezone_offset,
            "sport_name": self.sport_name,
            "score_state": self.score_state,
            "sport_id": self.sport_id,
            "score": self.score,
        }


@dataclass(frozen=True)
class WhoopProfile:
    user_id: int
    email: str
    first_name: str
    last_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
        }


@dataclass(frozen=True)
class WhoopBodyMeasurement:
    height_meter: float
    weight_kilogram: float
    max_heart_rate: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "height_meter": self.height_meter,
            "weight_kilogram": self.weight_kilogram,
            "max_heart_rate": self.max_heart_rate,
        }


@dataclass(frozen=True)
class WhoopSnapshot:
    cycle: WhoopCycle | None
    recovery: WhoopRecovery | None
    sleep: WhoopSleep | None
    workouts: list[WhoopWorkout]
    profile: WhoopProfile | None
    body: WhoopBodyMeasurement | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle.to_dict() if self.cycle else None,
            "recovery": self.recovery.to_dict() if self.recovery else None,
            "sleep": self.sleep.to_dict() if self.sleep else None,
            "workouts": [workout.to_dict() for workout in self.workouts],
            "profile": self.profile.to_dict() if self.profile else None,
            "body": self.body.to_dict() if self.body else None,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WhoopSnapshot":
        cycle = _parse_cycle_dict(data.get("cycle"))
        recovery = _parse_recovery_dict(data.get("recovery"))
        sleep = _parse_sleep_dict(data.get("sleep"))
        workouts_raw = data.get("workouts", [])
        workouts: list[WhoopWorkout] = []
        if isinstance(workouts_raw, list):
            for entry in workouts_raw:
                parsed = _parse_workout_dict(entry)
                if parsed:
                    workouts.append(parsed)
        profile = _parse_profile_dict(data.get("profile"))
        body = _parse_body_measurement_dict(data.get("body"))
        return WhoopSnapshot(
            cycle=cycle,
            recovery=recovery,
            sleep=sleep,
            workouts=workouts,
            profile=profile,
            body=body,
        )

    def format_for_prompt(self) -> str:
        if not any([self.cycle, self.recovery, self.sleep, self.workouts]):
            return "WHOOP: No data available."

        local_tz = datetime.now().astimezone().tzinfo
        today = datetime.now().astimezone().date()
        lines = ["WHOOP snapshot (most recent data):"]

        if self.recovery:
            if self.recovery.score_state != "SCORED":
                lines.append(f"Recovery: {self.recovery.score_state} (not yet available)")
            else:
                score = _score_value(self.recovery.score, "recovery_score", suffix="%")
                hrv = _score_value(self.recovery.score, "hrv_rmssd_milli", suffix=" ms")
                rhr = _score_value(self.recovery.score, "resting_heart_rate", suffix=" bpm")
                details = _join_parts(
                    [
                        score and f"score {score}",
                        hrv and f"HRV (RMSSD) {hrv}",
                        rhr and f"RHR {rhr}",
                    ]
                )
                lines.append(f"Recovery (from last sleep): {details}")

        if self.sleep:
            sleep_start = _format_dt(self.sleep.start, local_tz)
            sleep_end = _format_dt(self.sleep.end, local_tz)
            duration_hours = _duration_hours(self.sleep.start, self.sleep.end)
            duration = f"{duration_hours:.1f}h" if duration_hours else "Unknown duration"
            nap = "nap" if self.sleep.nap else "overnight"
            if self.sleep.score_state != "SCORED":
                lines.append(f"Sleep ({nap}): {sleep_start} → {sleep_end} | {duration}")
            else:
                performance = _score_value(
                    self.sleep.score,
                    "sleep_performance_percentage",
                    suffix="%",
                )
                efficiency = _score_value(
                    self.sleep.score,
                    "sleep_efficiency_percentage",
                    suffix="%",
                )
                details = _join_parts(
                    [
                        f"{sleep_start} → {sleep_end}",
                        duration,
                        performance and f"performance {performance}",
                        efficiency and f"efficiency {efficiency}",
                    ]
                )
                lines.append(f"Sleep ({nap}): {details}")

        if self.cycle:
            cycle_start = _format_dt(self.cycle.start, local_tz)
            cycle_end = _format_dt(self.cycle.end, local_tz) if self.cycle.end else "ongoing"
            if self.cycle.score_state != "SCORED":
                lines.append(f"Cycle: {cycle_start} → {cycle_end}")
            else:
                strain = _score_value(self.cycle.score, "strain")
                strain_part = f"strain {strain}" if strain else None
                lines.append(f"Cycle: {cycle_start} → {cycle_end} | {_join_parts([strain_part])}")

        if self.workouts:
            workouts_lines: list[str] = []
            for workout in self.workouts[:3]:
                start_local = workout.start.astimezone(local_tz) if local_tz else workout.start
                day_label = _relative_day_label(start_local.date(), today)
                time_label = start_local.strftime("%H:%M")
                duration = _duration_hours(workout.start, workout.end)
                duration_label = f"{duration:.1f}h" if duration else None
                strain = _score_value(workout.score, "strain")
                details = _join_parts(
                    [
                        duration_label and f"duration {duration_label}",
                        strain and f"strain {strain}",
                    ]
                )
                label = f"- {day_label} {time_label} — {workout.sport_name}"
                if details:
                    label = f"{label} ({details})"
                workouts_lines.append(label)

            lines.append("Recent workouts (most recent first; may include yesterday):")
            lines.extend(workouts_lines)

        return "\n".join(lines)


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


def _parse_cycle_dict(value: Any) -> WhoopCycle | None:
    if not isinstance(value, dict):
        return None
    return WhoopCycle(
        id=_required_int(value, "id"),
        user_id=_required_int(value, "user_id"),
        created_at=_required_datetime(value, "created_at"),
        updated_at=_required_datetime(value, "updated_at"),
        start=_required_datetime(value, "start"),
        end=_optional_datetime(value.get("end")),
        timezone_offset=_required_str(value, "timezone_offset"),
        score_state=_required_str(value, "score_state"),
        score=_optional_dict(value.get("score")),
    )


def _parse_sleep_dict(value: Any) -> WhoopSleep | None:
    if not isinstance(value, dict):
        return None
    return WhoopSleep(
        id=_required_str(value, "id"),
        cycle_id=_required_int(value, "cycle_id"),
        user_id=_required_int(value, "user_id"),
        created_at=_required_datetime(value, "created_at"),
        updated_at=_required_datetime(value, "updated_at"),
        start=_required_datetime(value, "start"),
        end=_required_datetime(value, "end"),
        timezone_offset=_required_str(value, "timezone_offset"),
        nap=_required_bool(value, "nap"),
        score_state=_required_str(value, "score_state"),
        score=_optional_dict(value.get("score")),
    )


def _parse_recovery_dict(value: Any) -> WhoopRecovery | None:
    if not isinstance(value, dict):
        return None
    return WhoopRecovery(
        cycle_id=_required_int(value, "cycle_id"),
        sleep_id=_required_str(value, "sleep_id"),
        user_id=_required_int(value, "user_id"),
        created_at=_required_datetime(value, "created_at"),
        updated_at=_required_datetime(value, "updated_at"),
        score_state=_required_str(value, "score_state"),
        score=_optional_dict(value.get("score")),
    )


def _parse_workout_dict(value: Any) -> WhoopWorkout | None:
    if not isinstance(value, dict):
        return None
    return WhoopWorkout(
        id=_required_str(value, "id"),
        user_id=_required_int(value, "user_id"),
        created_at=_required_datetime(value, "created_at"),
        updated_at=_required_datetime(value, "updated_at"),
        start=_required_datetime(value, "start"),
        end=_required_datetime(value, "end"),
        timezone_offset=_required_str(value, "timezone_offset"),
        sport_name=_required_str(value, "sport_name"),
        score_state=_required_str(value, "score_state"),
        sport_id=_optional_int(value.get("sport_id")),
        score=_optional_dict(value.get("score")),
    )


def _parse_profile_dict(value: Any) -> WhoopProfile | None:
    if not isinstance(value, dict):
        return None
    return WhoopProfile(
        user_id=_required_int(value, "user_id"),
        email=_required_str(value, "email"),
        first_name=_required_str(value, "first_name"),
        last_name=_required_str(value, "last_name"),
    )


def _parse_body_measurement_dict(value: Any) -> WhoopBodyMeasurement | None:
    if not isinstance(value, dict):
        return None
    return WhoopBodyMeasurement(
        height_meter=_required_float(value, "height_meter"),
        weight_kilogram=_required_float(value, "weight_kilogram"),
        max_heart_rate=_required_int(value, "max_heart_rate"),
    )


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


def _score_value(score: dict[str, Any] | None, key: str, suffix: str = "") -> str | None:
    if not score:
        return None
    value = score.get(key)
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            value_str = str(value).lower()
        elif isinstance(value, int):
            value_str = str(value)
        elif isinstance(value, float):
            value_str = f"{value:.1f}"
        else:
            value_str = str(value)
    except (TypeError, ValueError):
        value_str = str(value)
    return f"{value_str}{suffix}"


def _join_parts(parts: list[str | None]) -> str:
    return " | ".join(part for part in parts if part)


def _duration_hours(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    delta = end - start
    hours = delta.total_seconds() / 3600
    return hours if hours >= 0 else None


def _format_dt(value: datetime, tz: Any) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        localized = value.astimezone(tz) if tz else value
    except Exception:
        localized = value
    return localized.strftime("%Y-%m-%d %H:%M")


def _relative_day_label(day: Any, today: Any) -> str:
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return str(day)


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
