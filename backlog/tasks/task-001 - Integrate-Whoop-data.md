---
id: task-001
title: Integrate Whoop data
status: To Do
assignee: []
created_date: '2025-12-21 14:09'
labels:
  - integration
  - whoop
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add initial integration plumbing for Whoop data so Day Pilot can factor recovery/sleep/strain into planning. For now: define data model, config/env vars, and a stub fetch step with a clear interface for later implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define a Whoop data interface/model (e.g., recovery/sleep/strain) in codebase
- [ ] #2 Add configuration hooks (env vars) without committing secrets
- [ ] #3 Stub a fetch function/service with clear TODOs and error handling path
- [ ] #4 Document how/where the data will be used in planning prompts
<!-- AC:END -->
