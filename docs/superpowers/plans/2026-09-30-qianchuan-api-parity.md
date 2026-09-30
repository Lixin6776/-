# Qianchuan Official API Parity Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Extend official API execution and read support from pause/enable/budget to every remaining in-scope action except material upload, while preserving CDP fallback and confirmation safety.

**Architecture:** Reuse the existing API client, endpoint map, read provider, execution provider, and provider router. Expand request payload builders, read normalization, verification, routing support, and mock acceptance.

**Tech Stack:** Python 3.11+, Pydantic, HTTPX, pytest, React TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Global Constraints

- Real API calls remain disabled without credentials.
- All mutations still require persisted user confirmation.
- API writes are verified by read-back.
- API mutation failure never retries through CDP automatically.
- Material upload remains out of scope.
- Endpoint paths remain centralized and configurable.
- Full test suite must pass after parity expansion.

## Review Focus

- Every remaining action maps to a non-empty method/path/payload.
- Read normalization preserves optional bid, targeting, schedule, and material fields.
- API verification checks the exact requested change.
- Router selects API for every registered API-supported action.
- Missing response fields fail closed.

## Tasks

### Task 1: Payload Builders for Remaining Actions

**Files:** `backend/app/services/api_endpoint_map.py`, `backend/tests/test_api_endpoint_map.py`

- [x] Add payload assertions for create, copy, delete, edit, bid, targeting, schedule, bind, and unbind.
- [x] Implement action-specific payload fields while keeping advertiser_id centralized.
- [x] Run `pytest tests/test_api_endpoint_map.py -v`.
- [x] Commit `feat: add remaining API payload builders`.

### Task 2: Read Snapshot Expansion

**Files:** `backend/app/execution/api_read_provider.py`, `backend/app/execution/cdp/page_adapter.py`, `backend/tests/test_api_read_provider.py`

- [x] Write failing tests for bid, targeting, schedule, and materials normalization.
- [x] Normalize optional API fields into `PlanPageSnapshot`.
- [x] Missing required fields fail closed; optional fields default safely.
- [x] Run focused tests and commit `feat: expand API plan snapshots`.

### Task 3: API Verification for All Actions

**Files:** `backend/app/execution/api_provider.py`, `backend/tests/test_api_execution_provider.py`

- [x] Write failing verification tests for edit, bid, targeting, schedule, bind, and unbind.
- [x] Implement exact expected-state comparisons using result.before plus requested changes.
- [x] Keep create/copy verification name-based and delete verification absence-based.
- [x] Run focused tests and commit `feat: verify all API mutations`.

### Task 4: Router API Action Expansion

**Files:** `backend/app/main.py`, `backend/app/services/provider_router.py`, `backend/tests/test_provider_router.py`

- [x] Add a canonical `API_SUPPORTED_ACTIONS` set.
- [x] Route every supported action to API when credentials are configured.
- [x] Keep CDP fallback only for unsupported actions or missing API configuration.
- [x] Run focused tests and commit `feat: expand API-first action routing`.

### Task 5: Provider Indicator UI

**Files:** `frontend/src/components/ApiConnectionPanel.tsx`, `frontend/src/test/api-connection-panel.test.tsx`

- [x] Add a test showing API actions are routed first when configured.
- [x] Display configured provider and fallback behavior without secrets.
- [x] Run frontend tests/build and commit `feat: show API-first provider status`.

### Task 6: Full Mock Parity Acceptance and Bug Sweep

**Files:** `backend/tests/test_api_migration_acceptance.py`

- [x] Add a mock round trip covering create, copy, edit, bid, targeting, schedule, bind, unbind, delete.
- [x] Run backend tests, Ruff, mypy, frontend tests, and production build.
- [x] Fix any Critical or Important finding with a failing test first.
- [x] Commit `test: add API parity acceptance coverage`.

## Self-Review

- Payload mapping: Task 1.
- Read normalization: Task 2.
- Write verification: Task 3.
- Router parity: Task 4.
- User-visible provider state: Task 5.
- End-to-end mock parity and bug sweep: Task 6.