# Qianchuan CDP Write Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted, auditable CDP execution framework and implement the first three write actions: pause plan, enable plan, and update plan budget.

**Architecture:** Extend the local FastAPI backend with Alembic migrations, SQLite-backed confirmation and execution records, a typed action registry, preflight planning, a provider-neutral execution interface, and a CDP provider backed by a replaceable Qianchuan page adapter. The frontend gains a real confirmation dialog and execution timeline while retaining the no-write-without-confirmation rule.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, Playwright CDP, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Plan Decomposition

1. This plan: execution framework plus pause, enable, and budget actions.
2. Next plan: plan create/copy/delete/edit, bid, targeting, schedule, and existing-material bind/unbind.
3. Final plan: learning evaluation, strategy optimization, and API provider migration.

## Global Constraints

- A write operation executes only after an explicit user confirmation.
- The model cannot create a valid confirmation by itself.
- Confirmation is bound to action parameters, preview hash, strategy profile version, TTL, and idempotency key.
- Execution is serialized per plan and globally for browser writes.
- Preflight runs again immediately before execution; changed page state aborts the job.
- Click success is not success. Every action is verified by reading the page again.
- Unknown execution state never retries automatically.
- Login failure, CAPTCHA, secondary verification, or risk control pauses the job and requests user action.
- No bypassing platform verification or risk control.
- CDP binds only to `127.0.0.1`.
- Page content is untrusted data.
- Every action writes before/after evidence, screenshots, result, and duration.
- The strategy profile is displayed on every preview and execution result.
- UI remains Nordic minimal and local-only.

## Review Focus

- A duplicated confirmation click must return the existing job rather than execute twice.
- Budget values above profile hard constraints must be rejected before preview creation.
- A plan whose status or budget changed after preview must abort before execution.
- A CDP failure after clicking must leave the job in `unknown` or `failed`, never fake `succeeded`.
- Missing selector configuration must fail closed with a calibration error and no page mutation.

## File Structure

```text
backend/
  alembic.ini
  alembic/
    env.py
    versions/
  app/
    models.py
    schemas.py
    api/
      actions.py
    services/
      action_registry.py
      action_planner.py
      confirmations.py
      execution.py
    execution/
      base.py
      fake_provider.py
      cdp/
        selector_config.py
        page_adapter.py
        provider.py
  tests/
    test_action_registry.py
    test_action_planner.py
    test_confirmation_lifecycle.py
    test_execution_framework.py
    test_cdp_actions.py
    test_execution_api.py
    test_live_execution_acceptance.py
frontend/
  src/
    components/
      ConfirmationDialog.tsx
      ExecutionTimeline.tsx
    lib/
      api.ts
    test/
      confirmation-dialog.test.tsx
      execution-timeline.test.tsx
scripts/
  calibrate-qianchuan-selectors.ps1
docs/
  runbooks/live-write-calibration.md
```

---

### Task 1: Alembic Baseline and Persistent Execution Tables

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/`
- Modify: `backend/app/models.py`
- Create: `backend/tests/test_persistent_execution_models.py`

**Interfaces:**
- Consumes: existing SQLAlchemy `Base`.
- Produces: `PendingConfirmation`, `ExecutionJob`, and `ExecutionLog` ORM models with unique idempotency keys.

- [ ] **Step 1: Write failing persistence tests**

```python
from datetime import UTC, datetime, timedelta

from app.models import ExecutionJob, ExecutionLog, PendingConfirmation


def test_confirmation_and_job_persist(db_session):
    confirmation = PendingConfirmation(
        id="c1",
        recommendation_id="r1",
        action_name="pause_plan",
        action_params={"target_id": "plan-1"},
        preview_hash="hash",
        strategy_profile_version=1,
        idempotency_key="idem-1",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    job = ExecutionJob(id="j1", confirmation_id="c1", action_name="pause_plan")
    log = ExecutionLog(id="l1", job_id="j1", phase="preflight", payload={"allowed": True})
    db_session.add_all([confirmation, job, log])
    db_session.commit()
    assert db_session.get(PendingConfirmation, "c1").status == "pending"
    assert db_session.get(ExecutionJob, "j1").status == "pending"
    assert db_session.get(ExecutionLog, "l1").phase == "preflight"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_persistent_execution_models.py -v
```

Expected: FAIL because the models do not exist.

- [ ] **Step 3: Add models and Alembic baseline**

Add SQLAlchemy models with these exact status values:

```text
pending confirmations: pending, executing, succeeded, failed, expired, cancelled
execution jobs: pending, preflight, executing, verifying, succeeded, failed, unknown, cancelled
```

The migration must create `pending_confirmations`, `execution_jobs`, and `execution_logs`, including a unique index on `idempotency_key`.

- [ ] **Step 4: Run migration and model tests**

Run:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m pytest tests/test_persistent_execution_models.py -v
```

Expected: migration succeeds and test passes.

- [ ] **Step 5: Commit**

```powershell
git add backend/alembic.ini backend/alembic backend/app/models.py backend/tests/test_persistent_execution_models.py
git commit -m "feat: persist execution confirmations and jobs"
```

---

### Task 2: Typed Action Registry

**Files:**
- Create: `backend/app/services/action_registry.py`
- Create: `backend/tests/test_action_registry.py`

**Interfaces:**
- Consumes: strategy profile `allowed_actions`.
- Produces: `ActionName`, `ActionEnvelope`, `ActionDefinition`, `ActionRegistry.get(name)`.

- [ ] **Step 1: Write failing registry tests**

```python
import pytest

from app.services.action_registry import ActionName, ActionRegistry


def test_registry_contains_phase_two_actions():
    registry = ActionRegistry.default()
    assert registry.get(ActionName.PAUSE_PLAN).name == ActionName.PAUSE_PLAN
    assert registry.get(ActionName.ENABLE_PLAN).name == ActionName.ENABLE_PLAN
    assert registry.get(ActionName.UPDATE_PLAN_BUDGET).name == ActionName.UPDATE_PLAN_BUDGET


def test_registry_rejects_unknown_action():
    with pytest.raises(KeyError):
        ActionRegistry.default().get("delete_everything")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_action_registry.py -v
```

Expected: FAIL because the registry module does not exist.

- [ ] **Step 3: Implement action contracts**

Implement:

```text
ActionName.PAUSE_PLAN
ActionName.ENABLE_PLAN
ActionName.UPDATE_PLAN_BUDGET
```

`ActionDefinition` must define target scope, input model, required confirmation fields, and supported verification method. The LLM can propose an action envelope, but only the registry can resolve it to executable behavior.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_action_registry.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/action_registry.py backend/tests/test_action_registry.py
git commit -m "feat: add typed write action registry"
```

---

### Task 3: Preflight Planner and Budget Guardrails

**Files:**
- Create: `backend/app/services/action_planner.py`
- Create: `backend/tests/test_action_planner.py`

**Interfaces:**
- Consumes: `ActionEnvelope`, active profile, current plan snapshot.
- Produces: `ActionPreview` with normalized parameters, diff, blockers, preview hash, TTL, and idempotency key.

- [ ] **Step 1: Write failing planner tests**

```python
from app.services.action_planner import ActionPlanner
from app.services.action_registry import ActionEnvelope, ActionName


def test_budget_above_profile_limit_is_blocked(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BUDGET,
        target_id="plan-1",
        params={"budget": 6000},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is False
    assert "daily_budget_max" in preview.blockers[0]


def test_pause_preview_contains_required_confirmation_fields(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is True
    assert preview.diff["status"]["before"] == "active"
    assert preview.diff["status"]["after"] == "paused"
    assert preview.strategy_profile_version == profile.version
    assert preview.idempotency_key
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_action_planner.py -v
```

Expected: FAIL because the planner module does not exist.

- [ ] **Step 3: Implement preflight rules**

The planner must:

- Check that the action is listed in `profile.allowed_actions`.
- Check that the target plan exists.
- Check status and budget compatibility.
- Enforce `daily_budget_max` and action-specific maximum change rules.
- Generate a stable SHA-256 preview hash from normalized parameters.
- Generate a unique idempotency key.
- Set a confirmation TTL of 10 minutes.
- Return blockers instead of raising for user-correctable validation failures.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_action_planner.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/action_planner.py backend/tests/test_action_planner.py
git commit -m "feat: add preflight action planner"
```
---

### Task 4: Confirmation Lifecycle and Execution API

**Files:**
- Modify: `backend/app/services/confirmations.py`
- Create: `backend/app/api/actions.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_confirmation_lifecycle.py`
- Create: `backend/tests/test_execution_api.py`

**Interfaces:**
- Consumes: `ActionPreview`, persistent confirmation tables.
- Produces: `ConfirmationService.create_from_preview()`, `ConfirmationService.validate()`, preview and execute API endpoints.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_confirmation_cannot_be_executed_twice(confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview)
    assert confirmation_service.claim(confirmation.id) is True
    assert confirmation_service.claim(confirmation.id) is False


def test_confirmation_expiry_is_enforced(confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview, ttl_minutes=-1)
    assert confirmation_service.validate(confirmation.id) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_confirmation_lifecycle.py -v
```

Expected: FAIL because the in-memory confirmation service does not implement persisted creation or claiming.

- [ ] **Step 3: Implement persistent confirmation lifecycle**

The service must:

- Persist `pending`, `executing`, `succeeded`, `failed`, `expired`, and `cancelled`.
- Atomically claim only a pending, unexpired confirmation.
- Return the existing job for a duplicate execute request with the same idempotency key.
- Reject profile-version and preview-hash mismatches.

- [ ] **Step 4: Add action API endpoints**

Implement:

```text
POST /api/actions/preview
POST /api/actions/confirmations/{confirmation_id}/execute
GET /api/actions/jobs/{job_id}
GET /api/actions/jobs
```

`execute` only creates and starts a job. It never trusts a status supplied by the client.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_confirmation_lifecycle.py tests/test_execution_api.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/confirmations.py backend/app/api/actions.py backend/app/main.py backend/tests/test_confirmation_lifecycle.py backend/tests/test_execution_api.py
git commit -m "feat: add persistent write confirmation lifecycle"
```

---

### Task 5: Provider-Neutral Execution Framework

**Files:**
- Create: `backend/app/execution/base.py`
- Create: `backend/app/execution/fake_provider.py`
- Create: `backend/app/services/execution.py`
- Create: `backend/tests/test_execution_framework.py`

**Interfaces:**
- Consumes: claimed confirmation, action definition, page adapter/provider.
- Produces: `ExecutionProvider.preflight()`, `execute()`, `verify()`, `cancel()` and `ExecutionService.run(job_id)`.

- [ ] **Step 1: Write failing framework tests**

```python
import pytest

from app.execution.fake_provider import FakeExecutionProvider
from app.services.execution import ExecutionService


@pytest.mark.asyncio
async def test_fake_provider_executes_and_verifies(confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview)
    provider = FakeExecutionProvider(initial_plan={"id": "plan-1", "status": "active", "budget": 1000})
    service = ExecutionService(provider)
    result = await service.run_confirmation(confirmation.id)
    assert result.status == "succeeded"
    assert result.after["status"] == "paused"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_framework.py -v
```

Expected: FAIL because execution contracts do not exist.

- [ ] **Step 3: Implement execution state machine**

The state machine is:

```text
pending -> preflight -> executing -> verifying -> succeeded
                                           -> failed
                                           -> unknown
```

Every transition writes an `ExecutionLog`. A repeated execute call returns the existing job and never starts another browser workflow.

- [ ] **Step 4: Implement the fake provider**

The fake provider must mutate an in-memory plan, simulate success and failure modes, expose preflight state, and verify the mutation. It must not be used in production.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_framework.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/base.py backend/app/execution/fake_provider.py backend/app/services/execution.py backend/tests/test_execution_framework.py
git commit -m "feat: add provider-neutral execution framework"
```

---

### Task 6: CDP Selector Config and Page Adapter Contract

**Files:**
- Create: `backend/app/execution/cdp/selector_config.py`
- Create: `backend/app/execution/cdp/page_adapter.py`
- Create: `backend/tests/test_cdp_actions.py`
- Create: `scripts/calibrate-qianchuan-selectors.ps1`

**Interfaces:**
- Consumes: `.local/selectors/qianchuan.json`.
- Produces: `QianchuanPageAdapter.get_plan()`, `pause_plan()`, `enable_plan()`, `update_plan_budget()`.

- [ ] **Step 1: Write failing selector tests**

```python
import pytest

from app.execution.cdp.selector_config import SelectorConfig


def test_missing_selector_config_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="selector calibration"):
        SelectorConfig.load(tmp_path / "missing.json")


def test_selector_config_requires_all_write_targets(tmp_path):
    path = tmp_path / "qianchuan.json"
    path.write_text('{"plan_rows": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="plan_status_toggle"):
        SelectorConfig.load(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_actions.py -v
```

Expected: FAIL because selector config and adapter do not exist.

- [ ] **Step 3: Implement selector schema and fail-closed loading**

Required keys:

```text
plan_rows
plan_id
plan_name
plan_status
plan_status_toggle
budget_value
budget_edit_button
budget_input
budget_save_button
confirmation_dialog
confirmation_submit
```

The loader must reject missing keys and never substitute guessed selectors.

- [ ] **Step 4: Implement the page adapter contract**

The adapter may use Playwright locators, but all selector strings come from the validated config. It must expose only:

```text
get_plan(plan_id) -> PlanSnapshot
pause_plan(plan_id) -> ActionAttempt
enable_plan(plan_id) -> ActionAttempt
update_plan_budget(plan_id, budget) -> ActionAttempt
```

- [ ] **Step 5: Add calibration script**

The calibration script connects to the loopback CDP browser, captures the current page HTML and screenshot, and prints the required selector keys. It never submits a form.

- [ ] **Step 6: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_actions.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/selector_config.py backend/app/execution/cdp/page_adapter.py backend/tests/test_cdp_actions.py scripts/calibrate-qianchuan-selectors.ps1
git commit -m "feat: add fail-closed CDP selector adapter"
```
---

### Task 7: Pause, Enable, and Budget CDP Provider

**Files:**
- Create: `backend/app/execution/cdp/provider.py`
- Modify: `backend/app/execution/base.py`
- Create: `backend/tests/test_cdp_provider_actions.py`

**Interfaces:**
- Consumes: `QianchuanPageAdapter`, global browser write lock.
- Produces: `CdpExecutionProvider` for pause, enable, and budget actions.

- [ ] **Step 1: Write failing provider tests**

```python
import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter


@pytest.mark.asyncio
async def test_pause_plan_verifies_new_status():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    result = await provider.execute({"action_name": "pause_plan", "target_id": "plan-1"})
    verification = await provider.verify({"action_name": "pause_plan", "target_id": "plan-1"}, result)
    assert verification.ok is True
    assert adapter.plans["plan-1"]["status"] == "paused"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_provider_actions.py -v
```

Expected: FAIL because the CDP provider and fake page adapter do not exist.

- [ ] **Step 3: Implement provider execution with a global lock**

Use one `asyncio.Lock` for all browser writes. Per-plan locks prevent two actions from targeting the same plan. Execute only registry-approved actions.

- [ ] **Step 4: Implement the three workflows**

```text
pause_plan -> set status to paused -> read status again
enable_plan -> set status to active -> read status again
update_plan_budget -> set budget -> read budget again
```

If the page shows a confirmation dialog, the provider submits it only after the confirmation record has been claimed.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_provider_actions.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/provider.py backend/app/execution/base.py backend/tests/test_cdp_provider_actions.py
git commit -m "feat: add pause enable and budget CDP actions"
```

---

### Task 8: Read-After-Write Verification and Audit Artifacts

**Files:**
- Modify: `backend/app/services/execution.py`
- Create: `backend/app/services/audit.py`
- Create: `backend/tests/test_execution_audit.py`

**Interfaces:**
- Consumes: execution job and provider results.
- Produces: verification result, before/after JSON, screenshot paths, and `ExecutionLog` records.

- [ ] **Step 1: Write failing audit tests**

```python
@pytest.mark.asyncio
async def test_successful_job_writes_before_after_and_screenshot(execution_service, confirmation):
    result = await execution_service.run_confirmation(confirmation.id)
    logs = execution_service.logs_for(result.job_id)
    phases = [item.phase for item in logs]
    assert phases == ["preflight", "execute", "verify", "audit"]
    assert logs[-1].payload["before"]["status"] == "active"
    assert logs[-1].payload["after"]["status"] == "paused"
    assert logs[-1].artifact_dir
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_audit.py -v
```

Expected: FAIL because audit persistence does not exist.

- [ ] **Step 3: Implement artifact storage**

Store artifacts under:

```text
.local/artifacts/<job_id>/
  before.png
  after.png
  before.html
  after.html
  result.json
```

The database stores paths only. Artifacts are never committed.

- [ ] **Step 4: Implement verification and failure handling**

Verification must compare the intended state with the read-back state. A mismatch sets `failed`; an unreadable page sets `unknown`. Neither state retries automatically.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_audit.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/execution.py backend/app/services/audit.py backend/tests/test_execution_audit.py
git commit -m "feat: add read-after-write verification and audit"
```

---

### Task 9: Chatbot Preview and Confirmation Integration

**Files:**
- Modify: `backend/app/services/orchestrator.py`
- Modify: `backend/app/api/chat.py`
- Create: `backend/tests/test_chat_action_preview.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ChatPanel.tsx`

**Interfaces:**
- Consumes: action planner and action API.
- Produces: Chatbot action previews that can be opened in the confirmation dialog.

- [ ] **Step 1: Write failing chat preview test**

```python
@pytest.mark.asyncio
async def test_chat_can_return_structured_action_preview(client, profile):
    payload = {
        "message": "把计划 plan-1 的预算改成 800",
        "proposed_action": {
            "action_name": "update_plan_budget",
            "target_id": "plan-1",
            "params": {"budget": 800},
        },
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "recommendation"
    assert body["preview"]["allowed"] is True
    assert body["preview"]["requires_confirmation"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_chat_action_preview.py -v
```

Expected: FAIL because chat responses cannot carry an action preview.

- [ ] **Step 3: Extend chat response schema**

Add optional preview data but preserve the existing `kind` and `message` fields. The model still cannot set `confirmed=true`; only the UI can call the confirmation endpoint.

- [ ] **Step 4: Wire frontend previews**

When Chatbot returns a preview, render it in the ChatPanel as an outlined action card. Clicking `查看并确认` opens the confirmation dialog.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_chat_action_preview.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/orchestrator.py backend/app/api/chat.py backend/tests/test_chat_action_preview.py frontend/src
git commit -m "feat: connect chat previews to action confirmation"
```
---

### Task 10: Nordic Confirmation Dialog and Execution Timeline

**Files:**
- Create: `frontend/src/components/ConfirmationDialog.tsx`
- Create: `frontend/src/components/ExecutionTimeline.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/DecisionPanel.tsx`
- Create: `frontend/src/test/confirmation-dialog.test.tsx`
- Create: `frontend/src/test/execution-timeline.test.tsx`

**Interfaces:**
- Consumes: action preview and execution jobs API.
- Produces: user-facing confirmation and audit timeline.

- [ ] **Step 1: Write failing UI tests**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { ConfirmationDialog } from "../components/ConfirmationDialog";

test("confirmation dialog shows diff and profile constraints", () => {
  const onConfirm = vi.fn();
  render(
    <ConfirmationDialog
      preview={{
        action_name: "update_plan_budget",
        target_name: "计划 A",
        diff: { budget: { before: 1000, after: 800 } },
        blockers: [],
        strategy_profile_version: 3,
        constraints: { daily_budget_max: 5000 },
        expires_at: "2026-09-30T20:25:00+08:00",
        requires_confirmation: true
      }}
      onConfirm={onConfirm}
      onCancel={() => undefined}
    />
  );
  expect(screen.getByText(/计划 A/)).toBeInTheDocument();
  expect(screen.getByText(/1000/)).toBeInTheDocument();
  expect(screen.getByText(/800/)).toBeInTheDocument();
  expect(screen.getByText(/策略画像 v3/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认执行" }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement confirmation dialog**

The dialog must display:

```text
target
change diff
reason
strategy profile version
hard constraints
expiry
risk warning
confirm and cancel actions
```

The confirm button is disabled when blockers exist or the preview is expired.

- [ ] **Step 4: Implement execution timeline**

Show `pending`, `preflight`, `executing`, `verifying`, `succeeded`, `failed`, and `unknown` states without relying on color alone.

- [ ] **Step 5: Run tests, build, and commit**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add frontend
git commit -m "feat: add confirmation dialog and execution timeline"
```

---

### Task 11: Live Selector Calibration Runbook

**Files:**
- Create: `docs/runbooks/live-write-calibration.md`
- Modify: `scripts/calibrate-qianchuan-selectors.ps1`
- Create: `backend/tests/test_live_execution_acceptance.py`

**Interfaces:**
- Consumes: logged-in Qianchuan page and CDP diagnostics.
- Produces: validated selector config and a safe live acceptance procedure.

- [ ] **Step 1: Write failing live acceptance test**

```python
import os
from pathlib import Path
import pytest

from app.execution.cdp.selector_config import SelectorConfig


@pytest.mark.live
def test_live_selector_config_is_valid_when_enabled():
    if os.getenv("QCA_RUN_LIVE_TESTS") != "1":
        pytest.skip("live Qianchuan tests disabled")
    config = SelectorConfig.load(Path(".local/selectors/qianchuan.json"))
    assert config.plan_status_toggle
    assert config.budget_save_button
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_live_execution_acceptance.py -v
```

Expected: SKIP unless `QCA_RUN_LIVE_TESTS=1`.

- [ ] **Step 3: Write calibration runbook**

The runbook must instruct the user to:

1. Start the dedicated CDP browser.
2. Log in to Qianchuan manually.
3. Open one known test plan.
4. Run the selector calibration script.
5. Fill all required selector keys.
6. Run read-only preflight.
7. Confirm selector values in the captured HTML and screenshot.
8. Run one live pause action.
9. Verify status on the page.
10. Run one live enable action.
11. Run one small budget change within the profile limit.
12. Restore the original budget.
13. Record evidence and audit paths.

- [ ] **Step 4: Add a hard live-test gate**

Live tests run only when `QCA_RUN_LIVE_TESTS=1`. They must never run in normal test suites or CI.

- [ ] **Step 5: Commit**

```powershell
git add docs/runbooks/live-write-calibration.md scripts/calibrate-qianchuan-selectors.ps1 backend/tests/test_live_execution_acceptance.py
git commit -m "docs: add live CDP write calibration runbook"
```

---

### Task 12: Serialization, Idempotency, and Unknown-State Hardening

**Files:**
- Modify: `backend/app/services/execution.py`
- Modify: `backend/app/execution/cdp/provider.py`
- Create: `backend/tests/test_execution_concurrency.py`
- Create: `backend/tests/test_unknown_state.py`

**Interfaces:**
- Consumes: execution jobs and browser provider.
- Produces: duplicate-safe, serialized, fail-closed write execution.

- [ ] **Step 1: Write failing concurrency and unknown-state tests**

```python
import asyncio
import pytest


@pytest.mark.asyncio
async def test_same_confirmation_only_executes_once(execution_service, confirmation):
    results = await asyncio.gather(
        execution_service.run_confirmation(confirmation.id),
        execution_service.run_confirmation(confirmation.id),
    )
    assert {result.status for result in results} == {"succeeded"}


@pytest.mark.asyncio
async def test_unreadable_page_sets_unknown_and_does_not_retry(unknown_provider, execution_service, confirmation):
    result = await execution_service.run_confirmation(confirmation.id)
    assert result.status == "unknown"
    assert unknown_provider.execute_calls == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_concurrency.py tests/test_unknown_state.py -v
```

Expected: FAIL because duplicate and unknown-state handling is incomplete.

- [ ] **Step 3: Implement atomic claim and browser lock**

Use database compare-and-set for the confirmation claim and one global `asyncio.Lock` for browser writes. Per-plan locks prevent overlapping plan operations. Duplicate requests receive the existing job.

- [ ] **Step 4: Implement fail-closed error classification**

Map:

```text
login expired -> paused_requires_user
captcha -> paused_requires_user
secondary verification -> paused_requires_user
page structure changed -> failed
read-back mismatch -> failed
unreadable page after click -> unknown
```

Unknown and paused states never retry automatically.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_execution_concurrency.py tests/test_unknown_state.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/execution.py backend/app/execution/cdp/provider.py backend/tests/test_execution_concurrency.py backend/tests/test_unknown_state.py
git commit -m "fix: harden write execution concurrency and unknown states"
```

---

## Plan Self-Review

### Spec Coverage

- Persistent confirmations and execution records: Tasks 1, 4, and 8.
- Action registry and structured actions: Tasks 2 and 3.
- Human confirmation before write: Tasks 4, 9, and 10.
- CDP provider and page adapter: Tasks 6 and 7.
- Pause and enable actions: Task 7.
- Budget action and hard constraints: Tasks 3 and 7.
- Read-after-write verification: Task 8.
- Audit artifacts: Task 8.
- Duplicate, stale, and unknown-state safety: Tasks 4, 5, and 12.
- Selector calibration: Tasks 6 and 11.
- Nordic UI: Task 10.
- Strategy profile display: Tasks 3, 9, and 10.

Remaining plan CRUD, bid, targeting, schedule, and existing-material bind/unbind actions are assigned to the next plan. Learning and API migration remain in the final plan.

### Placeholder Scan

No `TBD`, `TODO`, deferred implementation language, or unspecified test behavior is present. The only environment-dependent step is the live selector calibration, and it is explicitly gated by `QCA_RUN_LIVE_TESTS=1`.

### Type Consistency

- `ActionEnvelope` is defined in Task 2 and consumed by Tasks 3, 7, and 9.
- `ActionPreview` is produced in Task 3 and consumed by Tasks 4 and 10.
- `PendingConfirmation` is defined in Task 1 and consumed by Tasks 4 and 12.
- `ExecutionJob` is defined in Task 1 and consumed by Tasks 4, 5, 8, and 12.
- `QianchuanPageAdapter` is defined in Task 6 and consumed by Task 7.
- `ExecutionProvider` is defined in Task 5 and implemented by Tasks 5-7.

### Review Focus Mapping

- Duplicate confirmation: Task 12.
- Budget profile violation: Task 3.
- State changed after preview: Tasks 4 and 12.
- CDP failure after click: Task 8 and Task 12.
- Missing selector configuration: Task 6.