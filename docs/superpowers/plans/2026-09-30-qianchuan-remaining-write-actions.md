# Qianchuan Remaining Write Actions Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the persisted CDP execution framework to all remaining in-scope investment operations except material upload: plan create/copy/delete/edit, bid, targeting, schedule, and existing-material bind/unbind.

**Architecture:** Reuse the Plan 2 action registry, preflight planner, confirmation state machine, execution provider, read-after-write verification, and audit pipeline. Add action-specific schemas, selector-driven page workflows, richer frontend parameter forms, destructive-action safeguards, and live calibration extensions.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite, Playwright CDP, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Scope

This plan implements:

- `create_plan`
- `copy_plan`
- `delete_plan`
- `edit_plan`
- `update_plan_bid`
- `update_targeting`
- `update_schedule`
- `bind_existing_material`
- `unbind_existing_material`

This plan does not implement:

- material upload
- account recharge, transfer, or balance management
- multi-account or multi-user support
- automatic execution without confirmation
- model-generated selector strings
- learning-loop optimization and API migration

## Global Constraints

- Every action is registered, schema-validated, preflighted, confirmed, executed, verified, and audited.
- Delete and unbind actions require an explicit destructive-action confirmation.
- The LLM may propose parameters but may not generate selectors, click coordinates, or bypass confirmation.
- Batch operations are limited, serialized, and show a complete target list.
- Unknown state never retries automatically.
- Selector configuration is external and fail-closed.
- Page content is untrusted data.
- CDP binds only to `127.0.0.1`.
- Every preview shows the strategy profile version and hard constraints.
- UI remains Nordic minimal.

## Review Focus

- A delete preview must clearly show the target and require a second explicit destructive confirmation.
- A copy operation must reject an unknown source plan and an empty destination name.
- An edit must reject fields not in the allowlist before any page mutation.
- Material bind/unbind must reject a material that is not already available in the account.
- Batch operations must abort before starting when any target fails preflight.

## File Structure

```text
backend/
  app/
    services/
      action_registry.py
      action_planner.py
      execution.py
    execution/
      fake_page_adapter.py
      cdp/
        selector_config.py
        page_adapter.py
        provider.py
  tests/
    test_remaining_action_registry.py
    test_remaining_action_planner.py
    test_plan_lifecycle_actions.py
    test_optimization_actions.py
    test_material_binding_actions.py
    test_batch_action_guardrails.py
frontend/
  src/
    components/
      ActionParameterForm.tsx
      BatchConfirmationDialog.tsx
    lib/api.ts
    test/
      action-parameter-form.test.tsx
      batch-confirmation-dialog.test.tsx
docs/
  runbooks/live-remaining-actions.md
```

---

### Task 1: Extend Action Registry and Input Schemas

**Files:**
- Modify: `backend/app/services/action_registry.py`
- Create: `backend/tests/test_remaining_action_registry.py`

**Interfaces:**
- Consumes: existing `ActionName` and `ActionRegistry`.
- Produces: typed definitions for nine remaining actions.

- [ ] **Step 1: Write failing registry tests**

```python
from app.services.action_registry import ActionName, ActionRegistry


def test_registry_contains_all_remaining_actions():
    registry = ActionRegistry.default()
    expected = {
        ActionName.CREATE_PLAN,
        ActionName.COPY_PLAN,
        ActionName.DELETE_PLAN,
        ActionName.EDIT_PLAN,
        ActionName.UPDATE_PLAN_BID,
        ActionName.UPDATE_TARGETING,
        ActionName.UPDATE_SCHEDULE,
        ActionName.BIND_EXISTING_MATERIAL,
        ActionName.UNBIND_EXISTING_MATERIAL,
    }
    assert {registry.get(name).name for name in expected} == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_remaining_action_registry.py -v
```

Expected: FAIL because the enum values and definitions do not exist.

- [ ] **Step 3: Add action enums and input models**

Define Pydantic input models for all nine actions. Required minimum fields:

```text
create_plan: source_product_id, name, budget, roi_goal
copy_plan: source_plan_id, name
delete_plan: target_id, reason
edit_plan: target_id, fields
update_plan_bid: target_id, bid
update_targeting: target_id, targeting
update_schedule: target_id, schedule
bind_existing_material: target_id, material_id
unbind_existing_material: target_id, material_id
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_remaining_action_registry.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/action_registry.py backend/tests/test_remaining_action_registry.py
git commit -m "feat: register remaining write actions"
```

---

### Task 2: Preflight Rules and Destructive Guardrails

**Files:**
- Modify: `backend/app/services/action_planner.py`
- Create: `backend/tests/test_remaining_action_planner.py`

**Interfaces:**
- Consumes: new action envelopes and current plan/material snapshots.
- Produces: action previews with field allowlists, destructive flags, blockers, and target lists.

- [ ] **Step 1: Write failing preflight tests**

```python
import pytest

from app.services.action_planner import ActionPlanner
from app.services.action_registry import ActionEnvelope, ActionName


def test_delete_requires_destructive_confirmation(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id="plan-1",
        params={"reason": "长期亏损"},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is True
    assert preview.destructive is True


def test_edit_rejects_non_allowlisted_field(profile, plan_snapshot):
    action = ActionEnvelope(
        action_name=ActionName.EDIT_PLAN,
        target_id="plan-1",
        params={"fields": {"unknown_field": "value"}},
    )
    preview = ActionPlanner().preflight(action, profile, plan_snapshot)
    assert preview.allowed is False
    assert "allowlist" in preview.blockers[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_remaining_action_planner.py -v
```

Expected: FAIL because the planner does not know the new action rules.

- [ ] **Step 3: Implement action-specific rules**

Add:

- edit field allowlist with budget, bid, targeting, schedule, name.
- delete destructive flag.
- unbind destructive flag.
- copy source existence check.
- bind material existence check.
- schedule validation against allowed time ranges.
- targeting validation against supported keys.
- batch preflight-all-or-abort behavior.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_remaining_action_planner.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/action_planner.py backend/tests/test_remaining_action_planner.py
git commit -m "feat: add remaining action preflight rules"
```
---

### Task 3: Extend Selector Config and Page Adapter Contract

**Files:**
- Modify: `backend/app/execution/cdp/selector_config.py`
- Modify: `backend/app/execution/cdp/page_adapter.py`
- Modify: `backend/app/execution/fake_page_adapter.py`
- Create: `backend/tests/test_plan_lifecycle_actions.py`

**Interfaces:**
- Consumes: existing selector-driven page adapter.
- Produces: methods for plan create, copy, delete, edit, bid, targeting, schedule, material bind, and material unbind.

- [ ] **Step 1: Write failing adapter tests**

```python
import pytest

from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_copy_plan_creates_new_plan():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    result = await adapter.copy_plan(
        ActionEnvelope(
            action_name=ActionName.COPY_PLAN,
            target_id="plan-1",
            params={"name": "计划 B"},
        )
    )
    assert result.ok is True
    assert "计划 B" in result.after["name"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_plan_lifecycle_actions.py -v
```

Expected: FAIL because the adapter methods do not exist.

- [ ] **Step 3: Extend selector config**

Add required keys for:

```text
create_plan_button
plan_form_name
plan_form_budget
plan_form_roi_goal
plan_form_submit
copy_plan_button
delete_plan_button
delete_confirm_input
delete_confirm_submit
edit_plan_button
edit_field_container
bid_input
targeting_editor
schedule_editor
material_picker
material_bind_button
material_unbind_button
```

The loader must continue to fail closed when any required key is missing.

- [ ] **Step 4: Implement adapter methods**

Add to the adapter contract:

```text
create_plan(action) -> ActionAttempt
copy_plan(action) -> ActionAttempt
delete_plan(action) -> ActionAttempt
edit_plan(action) -> ActionAttempt
update_bid(action) -> ActionAttempt
update_targeting(action) -> ActionAttempt
update_schedule(action) -> ActionAttempt
bind_material(action) -> ActionAttempt
unbind_material(action) -> ActionAttempt
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_plan_lifecycle_actions.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/selector_config.py backend/app/execution/cdp/page_adapter.py backend/app/execution/fake_page_adapter.py backend/tests/test_plan_lifecycle_actions.py
git commit -m "feat: extend page adapter for remaining actions"
```

---

### Task 4: Plan Lifecycle CDP Provider Workflows

**Files:**
- Modify: `backend/app/execution/cdp/provider.py`
- Create: `backend/tests/test_plan_lifecycle_provider.py`

**Interfaces:**
- Consumes: adapter methods for create, copy, delete, and edit.
- Produces: verified provider workflows for plan lifecycle operations.

- [ ] **Step 1: Write failing provider tests**

```python
import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_delete_plan_verifies_plan_is_gone():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id="plan-1",
        params={"reason": "长期亏损"},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert "plan-1" not in adapter.plans
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_plan_lifecycle_provider.py -v
```

Expected: FAIL because provider dispatch does not include plan lifecycle actions.

- [ ] **Step 3: Implement provider dispatch and verification**

For each action define expected post-state:

```text
create_plan -> new plan exists with expected name/budget
copy_plan -> new plan exists and source remains unchanged
delete_plan -> target is absent from plan list
edit_plan -> allowlisted fields match requested values
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_plan_lifecycle_provider.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/provider.py backend/tests/test_plan_lifecycle_provider.py
git commit -m "feat: add plan lifecycle execution workflows"
```

---

### Task 5: Bid, Targeting, and Schedule Workflows

**Files:**
- Modify: `backend/app/execution/cdp/provider.py`
- Create: `backend/tests/test_optimization_actions.py`

**Interfaces:**
- Consumes: adapter methods for bid, targeting, and schedule.
- Produces: verified provider workflows for optimization actions.

- [ ] **Step 1: Write failing optimization tests**

```python
import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_update_bid_verifies_new_value():
    adapter = FakePageAdapter(
        {"plan-1": {"status": "active", "budget": 1000, "bid": 2.5}}
    )
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BID,
        target_id="plan-1",
        params={"bid": 2.8},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert adapter.plans["plan-1"]["bid"] == 2.8
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_optimization_actions.py -v
```

Expected: FAIL because provider dispatch does not include these actions.

- [ ] **Step 3: Implement provider verification**

Verify:

```text
bid equals requested value
targeting equals normalized requested object
schedule equals normalized requested object
```

The provider must use normalized values from the preview, not raw model text.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_optimization_actions.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/provider.py backend/tests/test_optimization_actions.py
git commit -m "feat: add bid targeting and schedule workflows"
```
---

### Task 6: Existing-Material Bind and Unbind Workflows

**Files:**
- Modify: `backend/app/execution/cdp/provider.py`
- Create: `backend/tests/test_material_binding_actions.py`

**Interfaces:**
- Consumes: existing material ID and target plan.
- Produces: bind/unbind previews and verified provider workflows.

- [ ] **Step 1: Write failing material tests**

```python
import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_bind_existing_material_verifies_association():
    adapter = FakePageAdapter(
        {
            "plan-1": {
                "status": "active",
                "budget": 1000,
                "materials": [],
            },
            "material-1": {"available": True},
        }
    )
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.BIND_EXISTING_MATERIAL,
        target_id="plan-1",
        params={"material_id": "material-1"},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert "material-1" in adapter.plans["plan-1"]["materials"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_material_binding_actions.py -v
```

Expected: FAIL because bind/unbind workflows do not exist.

- [ ] **Step 3: Implement bind/unbind rules**

Bind requires:

- target plan exists
- material exists in the account library
- material is not already bound

Unbind requires:

- target plan exists
- material is bound
- destructive confirmation is present

- [ ] **Step 4: Implement provider verification**

Verify exact association after bind and absence after unbind. Never upload or create a new material.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_material_binding_actions.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution/cdp/provider.py backend/tests/test_material_binding_actions.py
git commit -m "feat: add existing material bind and unbind workflows"
```

---

### Task 7: Batch Action Guardrails and API Support

**Files:**
- Modify: `backend/app/services/action_planner.py`
- Modify: `backend/app/api/actions.py`
- Create: `backend/tests/test_batch_action_guardrails.py`

**Interfaces:**
- Consumes: multiple action envelopes and one strategy profile version.
- Produces: batch previews and all-or-abort confirmation creation.

- [ ] **Step 1: Write failing batch tests**

```python
from app.services.action_planner import ActionPlanner
from app.services.action_registry import ActionEnvelope, ActionName


def test_batch_preview_aborts_when_any_target_is_invalid(profile, plan_snapshot):
    actions = [
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        ),
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="missing-plan",
            params={},
        ),
    ]
    previews = ActionPlanner().preflight_batch(actions, profile, {"plan-1": plan_snapshot})
    assert all(not preview.allowed for preview in previews)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_batch_action_guardrails.py -v
```

Expected: FAIL because batch preflight does not exist.

- [ ] **Step 3: Implement batch planning**

`preflight_batch` must:

- preflight every action before returning.
- mark all previews blocked if any target fails.
- include the complete target list.
- refuse mixed strategy profile versions.
- enforce a configurable maximum batch size, default 20.

- [ ] **Step 4: Add batch API**

Implement:

```text
POST /api/actions/batch-preview
POST /api/actions/batch-confirmations
```

Batch confirmation creation succeeds only when every preview is allowed.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_batch_action_guardrails.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/action_planner.py backend/app/api/actions.py backend/tests/test_batch_action_guardrails.py
git commit -m "feat: add all-or-abort batch action guardrails"
```

---

### Task 8: Nordic Action Parameter Forms and Destructive Confirmation

**Files:**
- Create: `frontend/src/components/ActionParameterForm.tsx`
- Create: `frontend/src/components/BatchConfirmationDialog.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/test/action-parameter-form.test.tsx`
- Create: `frontend/src/test/batch-confirmation-dialog.test.tsx`

**Interfaces:**
- Consumes: action definitions and previews.
- Produces: typed forms for remaining actions and destructive/batch confirmation UI.

- [ ] **Step 1: Write failing form tests**

```tsx
import { render, screen } from "@testing-library/react";

import { ActionParameterForm } from "../components/ActionParameterForm";


test("copy plan form requires a destination name", () => {
  render(
    <ActionParameterForm
      actionName="copy_plan"
      onSubmit={() => undefined}
    />
  );
  expect(screen.getByLabelText("目标计划名称")).toBeRequired();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
```

Expected: FAIL because the form and batch dialog do not exist.

- [ ] **Step 3: Implement action forms**

Fields must be generated from an explicit action-to-field map. Do not render arbitrary JSON inputs for production actions.

- [ ] **Step 4: Implement destructive and batch confirmation UI**

Delete and unbind dialogs require the user to check an explicit destructive-action checkbox. Batch dialogs show every target and block confirmation if any preview is blocked.

- [ ] **Step 5: Run tests, build, and commit**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add frontend
git commit -m "feat: add remaining action forms and batch confirmation"
```
---

### Task 9: Live Calibration Extension

**Files:**
- Modify: `scripts/calibrate-qianchuan-selectors.ps1`
- Create: `docs/runbooks/live-remaining-actions.md`
- Modify: `backend/tests/test_live_execution_acceptance.py`

**Interfaces:**
- Consumes: real Qianchuan page and calibrated selectors.
- Produces: safe live validation for plan lifecycle, bid, targeting, schedule, and material bind/unbind.

- [ ] **Step 1: Extend the live test**

Add a live-gated test that validates all new selector keys when `QCA_RUN_LIVE_TESTS=1`.

- [ ] **Step 2: Write the runbook**

The runbook must require the user to:

1. Use a dedicated test plan or test account.
2. Verify read-only preflight for every new action.
3. Create a temporary plan.
4. Copy that plan.
5. Edit name, bid, targeting, and schedule one field at a time.
6. Bind one existing material.
7. Unbind that material.
8. Delete the copied plan.
9. Verify every before/after result in the execution timeline.
10. Stop on `failed` or `unknown`.

- [ ] **Step 3: Commit**

```powershell
git add scripts/calibrate-qianchuan-selectors.ps1 docs/runbooks/live-remaining-actions.md backend/tests/test_live_execution_acceptance.py
git commit -m "docs: add remaining live action calibration runbook"
```

---

### Task 10: End-to-End Acceptance for Remaining Actions

**Files:**
- Create: `backend/tests/test_remaining_actions_acceptance.py`
- Modify: `frontend/src/test/app-api-integration.test.tsx`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: automated acceptance on fake provider and UI flows.

- [ ] **Step 1: Write failing acceptance tests**

```python
import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_create_copy_edit_delete_round_trip():
    adapter = FakePageAdapter({"seed": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    create = ActionEnvelope(
        action_name=ActionName.CREATE_PLAN,
        target_id="new",
        params={"source_product_id": "product-1", "name": "新计划", "budget": 500, "roi_goal": 2.5},
    )
    result = await provider.execute(create)
    assert result.after["name"] == "新计划"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_remaining_actions_acceptance.py -v
```

Expected: FAIL until all action workflows and UI integration are complete.

- [ ] **Step 3: Implement the full fake-provider round trip**

Cover create, copy, edit, bid, targeting, schedule, bind, unbind, and delete.

- [ ] **Step 4: Add UI acceptance test**

Verify a copy-plan preview can be rendered, edited, confirmed, and appears in the execution timeline.

- [ ] **Step 5: Run full verification and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest -v
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add backend/tests/test_remaining_actions_acceptance.py frontend/src/test/app-api-integration.test.tsx
git commit -m "test: add remaining action acceptance coverage"
```

---

## Plan Self-Review

### Spec Coverage

- Plan create/copy/delete/edit: Tasks 1-4 and 10.
- Bid, targeting, schedule: Tasks 1, 2, 5, and 10.
- Existing material bind/unbind: Tasks 1, 2, 6, and 10.
- Confirmation and audit reuse: Tasks 2-6 and 10.
- Selector fail-closed behavior: Task 3.
- Batch safety: Task 7.
- Nordic forms and destructive confirmation: Task 8.
- Live calibration: Task 9.
- Material upload excluded: Scope and Global Constraints.

### Placeholder Scan

No `TBD`, `TODO`, deferred implementation language, or unspecified test behavior is present. Live execution remains explicitly gated by `QCA_RUN_LIVE_TESTS=1`.

### Type Consistency

- Action enums are defined in Task 1 and consumed by Tasks 2-6, 10.
- Action-specific input models are defined in Task 1 and validated by Task 2.
- Adapter methods are defined in Task 3 and consumed by Tasks 4-6.
- Batch preflight is defined in Task 7 and consumed by Task 8 and Task 10.
- UI action names match backend enum string values.
- Live selector keys are extended in Task 3 and validated in Task 9.

### Review Focus Mapping

- Destructive delete/unbind: Tasks 2, 6, and 8.
- Unknown copy source or empty destination: Tasks 2 and 4.
- Non-allowlisted edit field: Task 2.
- Material not available in account: Task 6.
- Batch failure before execution: Task 7.