---
id: task-002
title: Integrate weather data
status: In Progress
assignee: []
created_date: '2025-12-21 14:09'
updated_date: '2025-12-21 15:14'
labels:
  - integration
  - weather
dependencies:
  - task-003
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a basic weather integration scaffold using Open-Meteo so Day Pilot can include weather context in planning. For the first iteration, do not implement scheduling rules or task classification; only fetch and include (1) a high-level overview for today and (2) an hourly forecast from current time (state["now"]) until midnight in the user’s local timezone. This weather context should be easy to render to the user and to pass into planning prompts later.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Use Open-Meteo API via `openmeteo-requests` with caching + retry (`requests-cache`, `retry-requests`)
- [ ] #2 Fetch a compact high-level overview for today (summary + notable conditions/alerts if available)
- [ ] #3 Fetch an hourly forecast from `state["now"]` until local midnight (include hour, condition, temp, precip %, wind at minimum)
- [ ] #4 Keep payload compact and prompt-friendly (avoid huge raw arrays)

- [ ] #5 Document the intended prompt format (overview + hourly table) for later integration into planning prompts
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Open-Meteo Python sample (reference):

- Install: `pip install openmeteo-requests requests-cache retry-requests numpy pandas` (we'll use `uv add ...`).

- Client setup with caching + retry: `requests_cache.CachedSession('.cache', expire_after=3600)`; `retry(cache_session, retries=5, backoff_factor=0.2)`; `openmeteo_requests.Client(session=retry_session)`.

- API: `openmeteo.weather_api(url, params={latitude, longitude, hourly: 'temperature_2m', ...})` and map hourly variables by index order.
<!-- SECTION:NOTES:END -->
