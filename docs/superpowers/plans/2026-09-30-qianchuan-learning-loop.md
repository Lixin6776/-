# Qianchuan Strategy Learning Loop Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local strategy-learning loop that records decisions and outcomes, evaluates strategy effectiveness, retrieves similar cases, and proposes explainable strategy adjustments without automatically changing production rules.

**Architecture:** Extend the existing SQLite domain with learning cases, outcomes, evaluations, and suggestions. Deterministic services calculate metrics and confidence; the LLM explains evidence and proposes changes. Every learning result is versioned, traceable to a strategy profile and execution job, and requires user approval before becoming a new strategy profile.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Global Constraints

- Learning never modifies an active strategy without user approval.
- Every case links to profile version, recommendation, confirmation, execution job, and observed outcomes.
- Small samples never produce high-confidence recommendations.
- Correlation is not presented as causation.
- User feedback is stored separately from deterministic metrics.
- Production data remains local unless the user explicitly sends selected context to an LLM.
- UI follows Nordic minimal design.
- API migration is a separate later plan.

## Review Focus

- A case with insufficient samples must produce low confidence and no strategy update.
- A suggestion must show the evidence window, baseline, sample size, and counterexamples.
- Deleting or replaying a learning case must not modify historical execution records.
- Model explanations must not overwrite deterministic evaluation metrics.
- User rejection of a suggestion must be stored and reused in later retrieval.

## File Structure

```text
backend/
  alembic/versions/0002_learning_tables.py
  app/
    models.py
    schemas.py
    api/learning.py
    services/
      outcomes.py
      evaluation.py
      case_library.py
      suggestions.py
      learning.py
  tests/
    test_learning_models.py
    test_outcome_attribution.py
    test_strategy_evaluation.py
    test_case_retrieval.py
    test_learning_suggestions.py
    test_learning_api.py
    test_learning_guardrails.py
frontend/
  src/components/
    LearningCaseList.tsx
    StrategyEvaluationPanel.tsx
    StrategySuggestionCard.tsx
  src/test/
    learning-case-list.test.tsx
    strategy-evaluation-panel.test.tsx
```

---

### Task 1: Learning Tables and Migration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/0002_learning_tables.py`
- Create: `backend/tests/test_learning_models.py`

**Interfaces:**
- Consumes: existing execution and strategy tables.
- Produces: `LearningCase`, `DecisionOutcome`, `StrategyEvaluation`, `StrategySuggestion`.

- [ ] **Step 1: Write failing model tests**

```python
def test_learning_case_links_execution_history(db_session):
    case = LearningCase(
        id="case-1",
        strategy_profile_version=3,
        recommendation_id="rec-1",
        confirmation_id="conf-1",
        execution_job_id="job-1",
        action_name="pause_plan",
        context={"roi": 1.8, "spend": 500},
        status="observed",
    )
    db_session.add(case)
    db_session.commit()
    assert db_session.get(LearningCase, "case-1").strategy_profile_version == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_models.py -v
```

Expected: FAIL because learning models do not exist.

- [ ] **Step 3: Implement models and migration**

Required fields:

```text
LearningCase: id, strategy_profile_version, recommendation_id, confirmation_id,
  execution_job_id, action_name, context, status, created_at
DecisionOutcome: id, case_id, metric_window, metrics, observed_at
StrategyEvaluation: id, case_id, sample_size, effect_size, confidence,
  verdict, evidence, created_at
StrategySuggestion: id, strategy_profile_version, suggestion_type,
  proposed_change, evidence, confidence, status, created_at
```

`StrategySuggestion.status` supports `proposed`, `accepted`, `rejected`, `expired`.

- [ ] **Step 4: Run migration and tests**

Run:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m pytest tests/test_learning_models.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/models.py backend/alembic/versions/0002_learning_tables.py backend/tests/test_learning_models.py
git commit -m "feat: add learning loop persistence"
```

---

### Task 2: Outcome Attribution

**Files:**
- Create: `backend/app/services/outcomes.py`
- Create: `backend/tests/test_outcome_attribution.py`

**Interfaces:**
- Consumes: execution job, before/after states, monitor snapshots.
- Produces: `OutcomeAttributionService.record(case_id, before, after, windows) -> list[DecisionOutcome]`.

- [ ] **Step 1: Write failing attribution tests**

```python
def test_outcomes_include_short_and_long_windows(outcome_service, case):
    outcomes = outcome_service.record(
        case_id=case.id,
        before={"roi": 2.0, "spend": 400},
        after={"roi": 2.6, "spend": 450},
        windows=["5m", "30m"],
    )
    assert [outcome.metric_window for outcome in outcomes] == ["5m", "30m"]
    assert outcomes[0].metrics["roi_delta"] == 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_outcome_attribution.py -v
```

Expected: FAIL because outcome attribution does not exist.

- [ ] **Step 3: Implement deterministic deltas**

Calculate deltas for ROI, spend, GMV, orders, GPM, online viewers, and budget change. Store the observation window and whether data was stale or incomplete.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_outcome_attribution.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/outcomes.py backend/tests/test_outcome_attribution.py
git commit -m "feat: add decision outcome attribution"
```
---

### Task 3: Strategy Evaluation Engine

**Files:**
- Create: `backend/app/services/evaluation.py`
- Create: `backend/tests/test_strategy_evaluation.py`

**Interfaces:**
- Consumes: outcomes and strategy profile version.
- Produces: `StrategyEvaluationService.evaluate(case_ids) -> StrategyEvaluation`.

- [ ] **Step 1: Write failing evaluation tests**

```python
def test_small_sample_never_has_high_confidence(evaluation_service, low_sample_cases):
    evaluation = evaluation_service.evaluate([case.id for case in low_sample_cases])
    assert evaluation.sample_size < 5
    assert evaluation.confidence == "low"
    assert evaluation.verdict == "insufficient_data"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_strategy_evaluation.py -v
```

Expected: FAIL because evaluation service does not exist.

- [ ] **Step 3: Implement deterministic evaluation**

Calculate:

- sample size
- mean and median metric change
- success rate
- variance
- confidence level
- counterexample count
- verdict: `beneficial`, `harmful`, `neutral`, `insufficient_data`

Thresholds:

```text
sample < 5 -> low confidence
5-19 -> medium confidence
20+ -> high confidence
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_strategy_evaluation.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/evaluation.py backend/tests/test_strategy_evaluation.py
git commit -m "feat: add strategy evaluation engine"
```

---

### Task 4: Case Library and Similarity Retrieval

**Files:**
- Create: `backend/app/services/case_library.py`
- Create: `backend/tests/test_case_retrieval.py`

**Interfaces:**
- Consumes: strategy direction, objective, context, action, and outcomes.
- Produces: `CaseLibrary.find_similar(query, limit) -> list[CaseMatch]`.

- [ ] **Step 1: Write failing retrieval tests**

```python
def test_similar_cases_rank_same_direction_and_action_first(case_library, query):
    matches = case_library.find_similar(query, limit=3)
    assert matches[0].case.business_direction == query.business_direction
    assert matches[0].case.action_name == query.action_name
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_case_retrieval.py -v
```

Expected: FAIL because case retrieval does not exist.

- [ ] **Step 3: Implement deterministic similarity**

Score these fields:

```text
business direction
primary objective
action name
plan stage
product category hash
hour of day
spend range
ROI range
```

Return the score, matched reasons, successful cases, and counterexamples. Do not use embeddings in the first version.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_case_retrieval.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/case_library.py backend/tests/test_case_retrieval.py
git commit -m "feat: add strategy case retrieval"
```

---

### Task 5: Strategy Suggestion Engine

**Files:**
- Create: `backend/app/services/suggestions.py`
- Create: `backend/tests/test_learning_suggestions.py`

**Interfaces:**
- Consumes: evaluations and similar cases.
- Produces: `SuggestionEngine.propose(evaluation, matches, profile) -> StrategySuggestion | None`.

- [ ] **Step 1: Write failing suggestion tests**

```python
def test_low_confidence_does_not_create_suggestion(suggestion_engine, low_confidence_evaluation, profile):
    suggestion = suggestion_engine.propose(low_confidence_evaluation, [], profile)
    assert suggestion is None


def test_strong_evidence_creates_proposed_change(suggestion_engine, strong_evaluation, matches, profile):
    suggestion = suggestion_engine.propose(strong_evaluation, matches, profile)
    assert suggestion is not None
    assert suggestion.status == "proposed"
    assert suggestion.proposed_change
    assert suggestion.evidence["sample_size"] >= 20
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_suggestions.py -v
```

Expected: FAIL because suggestion engine does not exist.

- [ ] **Step 3: Implement suggestion rules**

Generate only:

- threshold adjustment suggestions
- observation-window adjustment suggestions
- action-priority suggestions
- strategy-profile change proposals

Never apply the suggested change. Store evidence, counterexamples, confidence, and a human-readable rationale.

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_suggestions.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/suggestions.py backend/tests/test_learning_suggestions.py
git commit -m "feat: add explainable strategy suggestions"
```
---

### Task 6: Learning API and Chat Context

**Files:**
- Create: `backend/app/api/learning.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/orchestrator.py`
- Create: `backend/tests/test_learning_api.py`

**Interfaces:**
- Consumes: learning services.
- Produces: case, evaluation, suggestion APIs and optional Chatbot learning context.

- [ ] **Step 1: Write failing API tests**

```python
def test_learning_suggestion_api_returns_proposed_only(client, profile, strong_evaluation):
    response = client.get("/api/learning/suggestions")
    assert response.status_code == 200
    assert all(item["status"] == "proposed" for item in response.json())
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_api.py -v
```

Expected: FAIL because learning endpoints do not exist.

- [ ] **Step 3: Implement endpoints**

```text
GET /api/learning/cases
GET /api/learning/cases/{case_id}
GET /api/learning/evaluations
GET /api/learning/suggestions
POST /api/learning/suggestions/{suggestion_id}/accept
POST /api/learning/suggestions/{suggestion_id}/reject
```

`accept` creates a new inactive strategy-profile draft; it never activates it automatically.

- [ ] **Step 4: Add Chatbot context**

When asked to explain a strategy result, load the relevant evaluation and case evidence. The model may summarize; deterministic metrics remain authoritative.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_api.py -v
```

Expected: PASS.

```powershell
git add backend/app/api/learning.py backend/app/main.py backend/app/services/orchestrator.py backend/tests/test_learning_api.py
git commit -m "feat: add learning APIs and chat context"
```

---

### Task 7: Learning Dashboard

**Files:**
- Create: `frontend/src/components/LearningCaseList.tsx`
- Create: `frontend/src/components/StrategyEvaluationPanel.tsx`
- Create: `frontend/src/components/StrategySuggestionCard.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/test/learning-case-list.test.tsx`
- Create: `frontend/src/test/strategy-evaluation-panel.test.tsx`

**Interfaces:**
- Consumes: learning APIs.
- Produces: case history, evaluation evidence, and suggestion review UI.

- [ ] **Step 1: Write failing UI tests**

```tsx
test("evaluation panel shows sample size and confidence", () => {
  render(
    <StrategyEvaluationPanel
      evaluation={{
        sample_size: 24,
        confidence: "high",
        verdict: "beneficial",
        evidence: { mean_roi_delta: 0.4 }
      }}
    />
  );
  expect(screen.getByText(/样本 24/)).toBeInTheDocument();
  expect(screen.getByText(/高置信度/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
```

Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement Nordic learning views**

Show case history, evidence windows, counterexamples, confidence, suggested change, and user actions. Accept/reject actions stay explicit.

- [ ] **Step 4: Run tests, build, and commit**

Run:

```powershell
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add frontend
git commit -m "feat: add strategy learning dashboard"
```

---

### Task 8: Learning Guardrails and Replay Acceptance

**Files:**
- Modify: `backend/app/services/learning.py`
- Create: `backend/tests/test_learning_guardrails.py`

**Interfaces:**
- Consumes: historical cases and suggestions.
- Produces: replayable evaluation, rejection memory, and safe learning boundaries.

- [ ] **Step 1: Write failing guardrail tests**

```python
def test_rejected_suggestion_is_remembered(learning_service, suggestion):
    learning_service.reject(suggestion.id, reason="样本不足")
    assert learning_service.was_rejected(suggestion.proposed_change) is True


def test_replay_does_not_mutate_execution_history(learning_service, execution_job):
    before = execution_job.result.copy()
    learning_service.replay(execution_job.id)
    assert execution_job.result == before
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_learning_guardrails.py -v
```

Expected: FAIL because replay and rejection memory do not exist.

- [ ] **Step 3: Implement replay and memory**

Replay evaluation without writing to execution logs or strategy profiles. Store rejected suggestions and their reasons. Reuse rejection memory in future retrieval and ranking.

- [ ] **Step 4: Run full verification and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest -v
pnpm --dir frontend exec vitest run --no-file-parallelism
pnpm --dir frontend build
```

Expected: PASS and build success.

```powershell
git add backend/app/services/learning.py backend/tests/test_learning_guardrails.py
git commit -m "feat: add learning guardrails and replay"
```

---

## Plan Self-Review

### Spec Coverage

- Outcome attribution: Task 2.
- Case library and retrieval: Task 4.
- Strategy evaluation and confidence: Task 3.
- Suggestion generation without auto-apply: Task 5.
- User acceptance and rejection: Tasks 6 and 8.
- Replay without mutation: Task 8.
- API and Chatbot explanation: Task 6.
- Learning dashboard: Task 7.
- Small-sample guardrails: Tasks 3 and 5.

### Placeholder Scan

No `TBD`, `TODO`, deferred implementation language, or unspecified test behavior is present. API migration remains outside this plan.

### Type Consistency

- `LearningCase` is defined in Task 1 and consumed by Tasks 2-4 and 6-8.
- `DecisionOutcome` is defined in Task 1 and consumed by Tasks 2, 3, and 8.
- `StrategyEvaluation` is defined in Task 1 and consumed by Tasks 3, 5, 6, and 7.
- `StrategySuggestion` is defined in Task 1 and consumed by Tasks 5-8.
- Case retrieval results are consumed by suggestions and Chatbot explanation.

### Review Focus Mapping

- Small samples: Task 3 and Task 5.
- Evidence and counterexamples: Tasks 3-7.
- Historical execution immutability: Task 8.
- Model versus deterministic authority: Task 6.
- Rejection memory: Task 8.