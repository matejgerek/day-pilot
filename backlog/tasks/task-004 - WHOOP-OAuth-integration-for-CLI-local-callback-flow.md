---
id: task-004
title: WHOOP OAuth integration for CLI (local callback flow)
status: In Progress
assignee:
  - Codex
created_date: '2025-12-21 16:28'
updated_date: '2025-12-21 16:43'
labels:
  - whoop
  - cli
  - oauth
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enable users to connect WHOOP via a local OAuth callback from the CLI, store tokens locally, and manage connection status for future energy-aware planning.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CLI provides commands to connect, check status, and disconnect WHOOP.
- [ ] #2 OAuth flow opens a browser and uses a temporary local callback server with clear success/failure feedback.
- [ ] #3 Successful connections persist tokens locally and survive app restarts.
- [ ] #4 Status command reports connected state and last sync info when available.
- [ ] #5 Disconnect command removes stored WHOOP credentials cleanly.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
- Extend config model to include optional WhoopConfig (tokens, scope, expires_at, connected_at, last_sync_at) and read/write/update helpers.
- Implement whoop_oauth service: build auth URL, start temporary local HTTP server for callback, validate state, exchange code for tokens, and compute expires_at.
- Add CLI commands whoop-connect/whoop-status/whoop-disconnect with clear console messaging and confirmation on overwrite.
- Persist tokens in .daypilot/config.json and remove on disconnect; status reports connected state and timestamps.
- Keep integration isolated to WHOOP; no changes to planning logic yet.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented WHOOP OAuth local callback flow with temporary HTTP server, browser launch, and token exchange. Added WHOOP config persistence in .daypilot/config.json, CLI commands whoop-connect/status/disconnect, and optional WHOOP env settings.

User reported WHOOP token exchange failing with "error code: 1010". Updated token exchange to try JSON, form, and form+Basic auth payload styles; improved error reporting with HTTP status and hints for redirect/credentials. Awaiting user confirmation that connect succeeds.
<!-- SECTION:NOTES:END -->
