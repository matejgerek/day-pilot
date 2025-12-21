---
id: task-003
title: User location normalization via OpenCage (init command)
status: Done
assignee: []
created_date: '2025-12-21 14:24'
updated_date: '2025-12-21 15:01'
labels:
  - location
  - integration
  - weather
  - cli
dependencies: []
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enable Day-Pilot CLI to accept free-form user location input (e.g. "svidnik") and normalize it to a canonical location with coordinates and timezone via OpenCage. Add a dedicated `init` command that gathers user details (starting with location), confirms the resolved result, and stores it locally in a dot folder/file that is ignored by git. This normalized location becomes the single source of truth for downstream features (weather/daylight/planning rules).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Add `cli init` command that prompts for free-form location when missing or on explicit init
- [ ] #2 Resolve user input via OpenCage geocoding to a canonical, human-readable place (city/region/country) plus lat/lon and timezone
- [ ] #3 Handle ambiguity by presenting best match and requiring explicit user confirmation before saving
- [ ] #4 Persist the normalized location in a local dot directory/file (e.g. `.daypilot/config.json`) and add it to `.gitignore`
- [ ] #5 On subsequent runs, reuse the stored location without prompting unless user runs `cli init` again
- [ ] #6 Provide clear error handling for network/API failures and invalid input (retry/cancel)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
OpenCage Python module docs (for implementation):

- Install: `pip install opencage` (we'll use `uv add opencage`).

- Usage: `from opencage.geocoder import OpenCageGeocode`; `geocoder = OpenCageGeocode(API_KEY)`; `results = geocoder.geocode(query)`; supports params like `no_annotations=1`, `language=...`, `proximity='lat,lng'`.

- Reverse: `geocoder.reverse_geocode(lat, lng)`.

- HTTP session reuse via `with OpenCageGeocode(key) as geocoder:`.

- Exceptions to handle: `InvalidInputError`, `NotAuthorizedError`, `ForbiddenError`, `RateLimitExceededError`, `UnknownError`.

- Async methods exist (`geocode_async`, `reverse_geocode_async`) if we need batching later.
<!-- SECTION:NOTES:END -->
