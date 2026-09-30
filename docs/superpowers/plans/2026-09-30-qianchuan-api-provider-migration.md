# Qianchuan Official API Provider Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an official Marketing API provider, API-first provider routing with CDP fallback, credential/token handling, and a controlled migration path from CDP.

**Architecture:** Add an HTTP API client, endpoint map, token service, read provider, write provider, and provider router behind the existing ExecutionProvider interface. API calls are disabled unless credentials are explicitly configured. MockTransport tests verify request shapes without touching a real account.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings, HTTPX, SQLAlchemy, Alembic, pytest, React TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Global Constraints

- No real API request runs without explicit local credentials.
- API secrets are never committed, logged, or sent to the model.
- API write actions use the same confirmation, preflight, verification, and audit pipeline as CDP.
- API provider is preferred only when configured and action support is known.
- CDP remains fallback and is never silently used after an API mutation attempt.
- Unknown API state never retries automatically.
- API migration does not activate or rewrite strategy profiles.
- Token refresh failure pauses execution and requests user action.

## Review Focus

- API credentials absent: routing must keep using CDP and never send unauthenticated requests.
- A refresh-token failure must not fall back to a mutating CDP action for the same confirmation.
- API response business errors must map to failed/unknown without retry loops.
- Payload mapping must preserve exact action parameters and advertiser/account IDs.
- Real API integration remains opt-in and mock-tested by default.

## File Structure

```text
backend/
  app/
    config.py
    models.py
    schemas.py
    services/
      token_service.py
      api_client.py
      api_endpoint_map.py
      provider_router.py
    execution/
      api_provider.py
      api_read_provider.py
  tests/
    test_api_config.py
    test_token_service.py
    test_api_client.py
    test_api_endpoint_map.py
    test_api_execution_provider.py
    test_provider_router.py
    test_api_migration_acceptance.py
frontend/
  src/components/ApiConnectionPanel.tsx
  src/test/api-connection-panel.test.tsx
docs/runbooks/api-migration.md
```

---

### Task 1: API Configuration and Credential Lifetime

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/token_service.py`
- Create: `backend/tests/test_api_config.py`
- Create: `backend/tests/test_token_service.py`

**Interfaces:**
- Consumes: environment or local settings.
- Produces: `ApiSettings` and `TokenService.is_configured()`, `should_refresh()`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_api_is_disabled_without_credentials(settings):
    assert settings.api_configured is False


def test_token_refresh_window_is_five_minutes(token_service):
    assert token_service.should_refresh(expires_in=299) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_config.py tests/test_token_service.py -v
```

Expected: FAIL because API settings and token service do not exist.

- [ ] **Step 3: Implement safe settings**

Add `api_base_url`, `api_app_id`, `api_app_secret`, `api_access_token`, `api_refresh_token`, and `api_token_expires_at`. `api_configured` is true only when required values are present. Secrets must not appear in `repr` or logs.

- [ ] **Step 4: Implement token lifetime logic**

`should_refresh()` returns true when the token is missing, expired, or has less than five minutes remaining. No network call occurs in this task.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/config.py backend/app/services/token_service.py backend/tests/test_api_config.py backend/tests/test_token_service.py
git commit -m "feat: add API credential configuration"
```

---

### Task 2: HTTP Client and Token Refresh

**Files:**
- Create: `backend/app/services/api_client.py`
- Create: `backend/tests/test_api_client.py`

**Interfaces:**
- Consumes: `TokenService` and HTTPX transport.
- Produces: `OceanEngineApiClient.request(method, path, params, json)` and `refresh_access_token()`.

- [ ] **Step 1: Write failing client tests**

```python
def test_client_sends_bearer_token(mock_transport, api_client):
    response = api_client.request("GET", "/open_api/v1.0/ad/get/", params={"advertiser_id": 1})
    assert response.status_code == 200
    assert mock_transport.last_request.headers["Authorization"] == "Bearer token-1"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_client.py -v
```

Expected: FAIL because the API client does not exist.

- [ ] **Step 3: Implement HTTP client**

Use `httpx.Client` with timeout, headers, redacted logging, and injectable transport for tests. Refresh tokens once before the request when `should_refresh()` is true. Raise `ApiAuthenticationError` if refresh fails.

- [ ] **Step 4: Implement response classification**

Map HTTP 401 and auth business codes to `ApiAuthenticationError`; map 429 to `ApiRateLimitError`; map other 4xx/5xx to `ApiRequestError`. Do not retry mutations automatically.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/api_client.py backend/tests/test_api_client.py
git commit -m "feat: add OceanEngine API client"
```
---

### Task 3: Endpoint Map and Payload Builders

**Files:**
- Create: `backend/app/services/api_endpoint_map.py`
- Create: `backend/tests/test_api_endpoint_map.py`

**Interfaces:**
- Consumes: `ActionEnvelope`.
- Produces: `ApiActionRequest(method, path, payload)` and `EndpointMap.build(action, advertiser_id)`.

- [ ] **Step 1: Write failing endpoint tests**

```python
def test_pause_plan_maps_to_status_update():
    request = EndpointMap.default().build(
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        ),
        advertiser_id=123,
    )
    assert request.method == "POST"
    assert "/qianchuan/ad/status/update/" in request.path
    assert request.payload["ad_ids"] == ["plan-1"]
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_endpoint_map.py -v
```

Expected: FAIL because endpoint map does not exist.

- [ ] **Step 3: Implement endpoint map**

Map all registered actions to API method, path, and payload. Keep paths centralized so official endpoint changes do not scatter across providers.

- [ ] **Step 4: Include read endpoints**

Add methods for account info, plan list, plan report, and live-room report.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/api_endpoint_map.py backend/tests/test_api_endpoint_map.py
git commit -m "feat: add OceanEngine endpoint mapping"
```

---

### Task 4: API Read Provider

**Files:**
- Create: `backend/app/execution/api_read_provider.py`
- Create: `backend/tests/test_api_read_provider.py`

**Interfaces:**
- Consumes: API client and endpoint map.
- Produces: `ApiReadProvider.get_plan()`, `get_account()`, `get_reports()`.

- [ ] **Step 1: Write failing read tests**

```python
def test_read_provider_normalizes_plan_snapshot(api_read_provider, mock_api):
    snapshot = api_read_provider.get_plan("plan-1")
    assert snapshot.id == "plan-1"
    assert snapshot.status == "active"
    assert snapshot.budget == 1000
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_read_provider.py -v
```

Expected: FAIL because read provider does not exist.

- [ ] **Step 3: Normalize API responses**

Map official fields into the local `PlanPageSnapshot` and report schemas. Missing fields fail closed instead of producing guessed values.

- [ ] **Step 4: Commit**

```powershell
git add backend/app/execution/api_read_provider.py backend/tests/test_api_read_provider.py
git commit -m "feat: add API read provider"
```

---

### Task 5: API Execution Provider

**Files:**
- Create: `backend/app/execution/api_provider.py`
- Create: `backend/tests/test_api_execution_provider.py`

**Interfaces:**
- Consumes: API client, endpoint map.
- Produces: `ApiExecutionProvider` implementing all ExecutionProvider methods.

- [ ] **Step 1: Write failing write tests**

```python
def test_api_provider_pause_verifies_readback(api_provider, mock_api):
    result = api_provider.execute(
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        )
    )
    verification = api_provider.verify(action, result)
    assert verification.ok is True
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_execution_provider.py -v
```

Expected: FAIL because API execution provider does not exist.

- [ ] **Step 3: Implement mutation and verification**

Before mutation, read the current state. After mutation, read again and compare exact requested changes. Authentication errors raise `UnknownExecutionState` only when the mutation may have been submitted; preflight auth errors fail before mutation.

- [ ] **Step 4: Disable automatic retries for mutation**

Retries are allowed only for idempotent reads. Write requests require the existing confirmation job and are never retried automatically by the HTTP client.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/execution/api_provider.py backend/tests/test_api_execution_provider.py
git commit -m "feat: add API execution provider"
```

---

### Task 6: API-first Provider Router with CDP Fallback

**Files:**
- Create: `backend/app/services/provider_router.py`
- Create: `backend/tests/test_provider_router.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: API provider, CDP provider factory, action support map.
- Produces: `ProviderRouter.choose(action)` and execution-provider factory.

- [ ] **Step 1: Write failing routing tests**

```python
def test_router_prefers_api_when_configured(router):
    selected = router.choose(ActionName.PAUSE_PLAN)
    assert selected.name == "api"


def test_router_uses_cdp_when_api_missing(cdp_only_router):
    selected = cdp_only_router.choose(ActionName.PAUSE_PLAN)
    assert selected.name == "cdp"
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_provider_router.py -v
```

Expected: FAIL because provider router does not exist.

- [ ] **Step 3: Implement routing rules**

Rules:

```text
API configured + action supported -> API
API missing or action unsupported -> CDP
API mutation started and fails -> no automatic CDP retry
```

- [ ] **Step 4: Wire local app factory**

Main chooses provider based on settings at request time. Credentials never enter the browser.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/provider_router.py backend/app/main.py backend/tests/test_provider_router.py
git commit -m "feat: route between API and CDP providers"
```
---

### Task 7: API Connection Panel and Migration Runbook

**Files:**
- Create: `frontend/src/components/ApiConnectionPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/test/api-connection-panel.test.tsx`
- Create: `docs/runbooks/api-migration.md`

**Interfaces:**
- Consumes: API configuration status endpoint.
- Produces: local connection status UI and migration instructions.

- [ ] **Step 1: Write failing UI test**

```tsx
test("API panel explains that secrets remain local", () => {
  render(<ApiConnectionPanel configured={false} />);
  expect(screen.getByText(/仅保存在本地/)).toBeInTheDocument();
  expect(screen.getByText(/CDP 回退/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
```

Expected: FAIL because connection panel does not exist.

- [ ] **Step 3: Implement connection status UI**

Show configured/not configured, provider preference, last successful API check, and a warning that credentials are local-only. Do not render secret values.

- [ ] **Step 4: Write migration runbook**

Document:

```text
1. Create developer app and request Qianchuan scopes.
2. Configure callback and OAuth.
3. Test read-only account and report calls.
4. Enable API-first routing.
5. Verify pause/enable/budget via API.
6. Keep CDP fallback for unsupported actions.
7. Do not retry a failed mutation through CDP automatically.
```

- [ ] **Step 5: Run tests, build, and commit**

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add frontend docs/runbooks/api-migration.md
git commit -m "feat: add API connection status and migration runbook"
```

---

### Task 8: API Migration Acceptance and Bug Sweep

**Files:**
- Create: `backend/tests/test_api_migration_acceptance.py`
- Modify: `backend/app/services/provider_router.py`

**Interfaces:**
- Consumes: all API provider components.
- Produces: mock end-to-end acceptance and migration guardrails.

- [ ] **Step 1: Write failing acceptance test**

```python
def test_api_migration_acceptance_uses_mock_transport(api_provider, mock_api):
    snapshot = api_provider.adapter.get_plan("plan-1")
    assert snapshot.id == "plan-1"
    result = api_provider.execute(PAUSE_ACTION)
    assert api_provider.verify(PAUSE_ACTION, result).ok is True
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api_migration_acceptance.py -v
```

Expected: FAIL until routing and mock integration are complete.

- [ ] **Step 3: Implement migration-safe fallback policy**

If a mutation has not started, CDP fallback is allowed. If a mutation has started, failures become `failed` or `unknown`; CDP must not retry the same confirmation automatically.

- [ ] **Step 4: Run full bug sweep**

Run:

```powershell
.\.venv\Scripts\python -m pytest -v
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m mypy app
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Inspect failures, flaky tests, stale state, and red warnings. Fix all Critical and Important findings with a failing test first.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/provider_router.py backend/tests/test_api_migration_acceptance.py
git commit -m "test: add API migration acceptance coverage"
```

---

## Plan Self-Review

### Spec Coverage

- API credentials and token storage: Tasks 1 and 2.
- API request abstraction: Task 2.
- Endpoint mapping: Task 3.
- Read provider: Task 4.
- Write provider: Task 5.
- API-first/CDP fallback routing: Task 6.
- Local connection visibility: Task 7.
- Migration instructions: Task 7.
- Mock acceptance and bug sweep: Task 8.

### Placeholder Scan

No `TBD`, `TODO`, deferred implementation language, or unspecified test behavior is present. Real credentials and real API calls remain opt-in and are not needed for the default test suite.

### Type Consistency

- `ApiSettings` is defined in Task 1 and consumed by Tasks 2, 6, and 7.
- `OceanEngineApiClient` is defined in Task 2 and consumed by Tasks 4, 5, and 8.
- `EndpointMap` is defined in Task 3 and consumed by Tasks 4, 5, and 8.
- `ApiReadProvider` and `ApiExecutionProvider` are consumed by the router in Task 6.
- Routing decisions use the existing `ActionName` enum and `ExecutionProvider` protocol.

### Review Focus Mapping

- Missing credentials: Tasks 1 and 6.
- Refresh failure: Tasks 2 and 6.
- API business errors: Tasks 2 and 5.
- Exact payload mapping: Task 3.
- No automatic CDP retry after mutation: Tasks 6 and 8.