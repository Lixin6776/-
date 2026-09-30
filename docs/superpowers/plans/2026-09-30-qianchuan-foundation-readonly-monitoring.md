# Qianchuan Local CDP Assistant Foundation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working local Qianchuan assistant slice: Chatbot, persistent strategy profiles, CDP diagnostics, read-only plan/live-room metrics, 5-10 minute monitoring, change detection, recommendations, and human confirmation records.

**Architecture:** A local FastAPI backend owns domain state in SQLite and exposes chat, profile, monitor, and recommendation APIs. A provider-neutral LLM adapter turns natural language into schema-validated read-only tool calls. A CDP gateway and fixture-backed page adapter provide replaceable data acquisition. A React/Vite frontend consumes the APIs with the Nordic minimal design system.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, SQLite, APScheduler, Playwright CDP, HTTPX, pytest, React 19, TypeScript, Vite, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-30-qianchuan-local-cdp-assistant-design.md`

## Plan Decomposition

This project is split into three independently testable plans:

1. This plan: foundation, Chatbot, strategy profile, read-only data, monitoring, recommendations, confirmation records.
2. Next plan: CDP write actions, execution provider, preflight, confirmation execution, read-after-write verification, audit.
3. Final plan: learning evaluation, case retrieval, strategy optimization, API provider migration, hardening.

Write actions are intentionally absent from this plan. The only write-like object produced here is a `pending_confirmation`; it cannot execute because no execution provider is registered.

## Global Constraints

- Local service binds only to `127.0.0.1`.
- Single local user and single Qianchuan account.
- The LLM never directly controls the browser.
- Every Chatbot, monitor, and confirmation output includes strategy profile version, direction, objective, constraints, data time, and freshness.
- CDP debug port binds only to `127.0.0.1`.
- Page content is untrusted data and cannot be treated as instructions.
- No CAPTCHA, secondary-verification, or platform-risk-control bypass.
- No write action may execute in this plan.
- Default monitor interval is 5 minutes; 10 minutes is supported.
- Core monitored metrics are ROI, spend, GMV, orders, GPM, online viewers, plan status, and plan budget.
- UI follows the Nordic minimal tokens in the spec.
- Tests use fixtures and mocks; real account writes are forbidden.
- Every task ends with a commit.

## Review Focus

- Stale or unchanged page data must produce `freshness=stale` and must not emit an action recommendation.
- Missing page selectors or malformed pages must fail closed, preserve diagnostics, and never fabricate metrics.
- Malformed LLM output must be rejected by schema validation and return a safe user-facing error.
- A pending confirmation must be invalid after TTL, profile-version change, or parameter-hash change.
- Nordic UI tests must prove the strategy banner and data-freshness label remain visible in Chat and monitor views.

## File Structure

```text
backend/
  pyproject.toml
  alembic.ini
  app/
    __init__.py
    main.py
    config.py
    db.py
    models.py
    schemas.py
    dependencies.py
    api/
      chat.py
      profiles.py
      monitor.py
      recommendations.py
    services/
      profiles.py
      analytics.py
      changes.py
      monitor.py
      recommendations.py
      confirmations.py
      orchestrator.py
      llm/
        base.py
        fake.py
        openai_compatible.py
    execution/
      base.py
      cdp/
        browser.py
        page_probe.py
        fixture_adapter.py
  tests/
    conftest.py
    test_health.py
    test_profiles.py
    test_orchestrator.py
    test_analytics.py
    test_changes.py
    test_monitor.py
    test_recommendations.py
    test_confirmations.py
    fixtures/
      plan_live_snapshot.json
frontend/
  package.json
  index.html
  vite.config.ts
  src/
    main.tsx
    App.tsx
    styles/tokens.css
    lib/api.ts
    components/
      StrategyBanner.tsx
      ChatPanel.tsx
      LiveMonitorPanel.tsx
      DecisionPanel.tsx
    test/
      setup.ts
      strategy-banner.test.tsx
      decision-panel.test.tsx
scripts/
  start-chrome-cdp.ps1
  start-dev.ps1
docs/
  runbooks/local-development.md
```

---

### Task 1: Backend Scaffold and Health Contract

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: none.
- Produces: FastAPI ASGI object `app` in `app.main`; `GET /health -> {"status":"ok"}`.

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from app.main import app


def test_health_contract() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
py -3.11 -m pytest backend/tests/test_health.py -v
```

Expected: FAIL because `app.main` or `app` does not exist.

- [ ] **Step 3: Create project metadata and minimal app**

`backend/pyproject.toml`:

```toml
[project]
name = "qianchuan-assistant"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.34,<1",
  "pydantic-settings>=2.7,<3",
  "sqlalchemy>=2.0,<3",
  "alembic>=1.14,<2",
  "apscheduler>=3.11,<4",
  "playwright>=1.50,<2",
  "httpx>=0.28,<1",
  "sse-starlette>=2.2,<3",
  "structlog>=24.4,<26"
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
  "pytest-asyncio>=0.25,<1",
  "ruff>=0.9,<1",
  "mypy>=1.14,<2"
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
markers = ["cdp: requires a locally running Chrome/Edge with CDP"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

`backend/app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Qianchuan Local Assistant", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Install, run, and verify**

Run:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest tests/test_health.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/pyproject.toml backend/app backend/tests/test_health.py
git commit -m "feat: scaffold backend health service"
```
---

### Task 2: Persistent Strategy Profiles and Versioning

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/services/profiles.py`
- Create: `backend/app/api/profiles.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_profiles.py`

**Interfaces:**
- Consumes: FastAPI `app`.
- Produces: `StrategyProfileService.create_version(payload) -> StrategyProfile`; `StrategyProfileService.get_active() -> StrategyProfile`; profile API `/api/profiles/active` and `/api/profiles/versions`.

- [ ] **Step 1: Write failing profile tests**

```python
def test_profile_versions_are_immutable(client):
    payload = {
        "name": "稳定放量",
        "business_direction": "稳定放量",
        "primary_objective": "ROI >= 2.5 且提升成交额",
        "secondary_objectives": ["保持在线人数"],
        "hard_constraints": {"daily_budget_max": 5000},
        "monitoring_config": {"interval_minutes": 5},
        "allowed_actions": ["pause_plan", "update_plan_budget"],
        "notification_policy": {"dedupe_minutes": 10},
    }
    first = client.post("/api/profiles/versions", json=payload)
    assert first.status_code == 201
    assert first.json()["version"] == 1

    payload["hard_constraints"] = {"daily_budget_max": 4500}
    second = client.post("/api/profiles/versions", json=payload)
    assert second.status_code == 201
    assert second.json()["version"] == 2

    active = client.get("/api/profiles/active").json()
    assert active["version"] == 2
    assert active["hard_constraints"]["daily_budget_max"] == 4500
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests/test_profiles.py -v
```

Expected: FAIL because profile endpoints and models do not exist.

- [ ] **Step 3: Implement database and profile models**

`backend/app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QCA_")
    database_url: str = "sqlite:///./qianchuan.db"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000


settings = Settings()
```

`backend/app/db.py`:

```python
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
```

`backend/app/models.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrategyProfile(Base):
    __tablename__ = "strategy_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    business_direction: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_objective: Mapped[str] = mapped_column(String(500), nullable=False)
    secondary_objectives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    hard_constraints: Mapped[dict] = mapped_column(JSON, nullable=False)
    monitoring_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    allowed_actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    notification_policy: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

`backend/app/schemas.py`:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class StrategyProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    business_direction: str = Field(min_length=1, max_length=120)
    primary_objective: str = Field(min_length=1, max_length=500)
    secondary_objectives: list[str] = []
    hard_constraints: dict = {}
    monitoring_config: dict = {"interval_minutes": 5}
    allowed_actions: list[str] = []
    notification_policy: dict = {"dedupe_minutes": 10}


class StrategyProfileRead(StrategyProfileCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    active: bool
    created_at: datetime
    effective_at: datetime
```

- [ ] **Step 4: Implement service and API**

`backend/app/services/profiles.py`:

```python
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import StrategyProfile
from app.schemas import StrategyProfileCreate


class StrategyProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_version(self, payload: StrategyProfileCreate) -> StrategyProfile:
        latest = self.session.scalar(
            select(StrategyProfile).order_by(StrategyProfile.version.desc()).limit(1)
        )
        next_version = 1 if latest is None else latest.version + 1
        self.session.execute(update(StrategyProfile).values(active=False))
        profile = StrategyProfile(version=next_version, active=True, **payload.model_dump())
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_active(self) -> StrategyProfile:
        profile = self.session.scalar(
            select(StrategyProfile).where(StrategyProfile.active.is_(True)).limit(1)
        )
        if profile is None:
            raise LookupError("No active strategy profile")
        return profile
```

`backend/app/api/profiles.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import StrategyProfileCreate, StrategyProfileRead
from app.services.profiles import StrategyProfileService

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("/versions", response_model=StrategyProfileRead, status_code=201)
def create_profile(payload: StrategyProfileCreate, db: Session = Depends(get_db)):
    return StrategyProfileService(db).create_version(payload)


@router.get("/active", response_model=StrategyProfileRead)
def active_profile(db: Session = Depends(get_db)):
    try:
        return StrategyProfileService(db).get_active()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

Modify `backend/app/main.py` to call `Base.metadata.create_all(bind=engine)` during startup and include the profiles router.

`backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import StrategyProfile


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def profile(db_session):
    item = StrategyProfile(
        version=1,
        name="稳定放量",
        business_direction="稳定放量",
        primary_objective="ROI >= 2.5 且提升成交额",
        secondary_objectives=["保持在线人数"],
        hard_constraints={"daily_budget_max": 5000},
        monitoring_config={"interval_minutes": 5},
        allowed_actions=["pause_plan", "update_plan_budget"],
        notification_policy={"dedupe_minutes": 10},
        active=True,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_profiles.py tests/test_health.py -v
```

Expected: PASS.

```powershell
git add backend/app backend/tests
git commit -m "feat: persist versioned strategy profiles"
```

---

### Task 3: Provider-Neutral LLM Orchestrator

**Files:**
- Create: `backend/app/services/llm/base.py`
- Create: `backend/app/services/llm/fake.py`
- Create: `backend/app/services/llm/openai_compatible.py`
- Create: `backend/app/services/orchestrator.py`
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: active strategy profile service.
- Produces: `LLMProvider.complete(messages, tools) -> LLMResponse`; `Orchestrator.handle(message, profile) -> ChatResult`; `POST /api/chat`.

- [ ] **Step 1: Write failing safe-output tests**

```python
import pytest
from app.services.llm.fake import FakeLLMProvider
from app.services.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_rejects_malformed_model_data(profile):
    llm = FakeLLMProvider(content="not-json")
    result = await Orchestrator(llm).handle("看看今天的ROI", profile)
    assert result.kind == "error"
    assert result.message == "模型返回格式无效，请重试。"


@pytest.mark.asyncio
async def test_orchestrator_returns_readonly_analysis(profile):
    llm = FakeLLMProvider(
        content='{"kind":"analysis","message":"当前策略要求在 ROI >= 2.5 下放量。"}'
    )
    result = await Orchestrator(llm).handle("当前策略是什么", profile)
    assert result.kind == "analysis"
    assert "ROI >= 2.5" in result.message
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_orchestrator.py -v
```

Expected: FAIL because orchestrator and LLM adapter do not exist.

- [ ] **Step 3: Implement LLM contracts and adapters**

`backend/app/services/llm/base.py`:

```python
from typing import Protocol
from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str


class LLMProvider(Protocol):
    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        ...
```

`backend/app/services/llm/fake.py`:

```python
from app.services.llm.base import LLMMessage, LLMResponse


class FakeLLMProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        return LLMResponse(content=self.content)
```

`backend/app/services/llm/openai_compatible.py`:

```python
import httpx
from app.services.llm.base import LLMMessage, LLMResponse


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def complete(self, messages: list[LLMMessage], tools: list[dict]) -> LLMResponse:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [m.model_dump() for m in messages],
                    "tools": tools,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return LLMResponse(content=data["choices"][0]["message"]["content"])
```

- [ ] **Step 4: Implement validated orchestrator**

`backend/app/services/orchestrator.py`:

```python
import json
from pydantic import BaseModel, ValidationError

from app.models import StrategyProfile
from app.services.llm.base import LLMMessage, LLMProvider


class ChatResult(BaseModel):
    kind: str
    message: str


class Orchestrator:
    ALLOWED_KINDS = {"analysis", "recommendation", "question", "error"}

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def handle(self, message: str, profile: StrategyProfile) -> ChatResult:
        context = (
            f"当前策略画像 v{profile.version}: {profile.business_direction}; "
            f"{profile.primary_objective}; 约束={profile.hard_constraints}"
        )
        response = await self.llm.complete(
            [LLMMessage(role="system", content=context), LLMMessage(role="user", content=message)],
            tools=[],
        )
        try:
            payload = json.loads(response.content)
            result = ChatResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError):
            return ChatResult(kind="error", message="模型返回格式无效，请重试。")
        if result.kind not in self.ALLOWED_KINDS:
            return ChatResult(kind="error", message="模型返回了不支持的操作类型。")
        return result
```

- [ ] **Step 5: Add chat API, run tests, and commit**

`POST /api/chat` loads the active profile, builds the configured provider, calls `Orchestrator.handle`, and returns `ChatResult`.

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_orchestrator.py -v
```

Expected: PASS.

```powershell
git add backend/app backend/tests/test_orchestrator.py
git commit -m "feat: add schema-validated chat orchestrator"
```
---

### Task 4: CDP Browser Gateway and Diagnostics Probe

**Files:**
- Create: `backend/app/execution/cdp/browser.py`
- Create: `backend/app/execution/cdp/page_probe.py`
- Create: `scripts/start-chrome-cdp.ps1`
- Create: `backend/tests/test_cdp_probe.py`

**Interfaces:**
- Consumes: local CDP endpoint `http://127.0.0.1:9222`.
- Produces: `CdpBrowserGateway.connect()`; `PageProbe.capture(page_url, output_dir) -> ProbeArtifact`.

- [ ] **Step 1: Write failing probe tests**

```python
import pytest
from app.execution.cdp.page_probe import validate_cdp_endpoint


def test_cdp_endpoint_must_be_loopback():
    with pytest.raises(ValueError):
        validate_cdp_endpoint("http://0.0.0.0:9222")


def test_cdp_endpoint_accepts_loopback():
    assert validate_cdp_endpoint("http://127.0.0.1:9222") == "http://127.0.0.1:9222"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_probe.py -v
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement gateway and probe**

`backend/app/execution/cdp/browser.py`:

```python
from playwright.async_api import Browser, Playwright, async_playwright


class CdpBrowserGateway:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None

    async def connect(self) -> Browser:
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.connect_over_cdp(self.endpoint)
        return self.browser
```

`backend/app/execution/cdp/page_probe.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.execution.cdp.browser import CdpBrowserGateway


def validate_cdp_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("CDP endpoint must use loopback host")
    return endpoint.rstrip("/")


@dataclass(frozen=True)
class ProbeArtifact:
    page_url: str
    html_path: Path
    screenshot_path: Path


class PageProbe:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = validate_cdp_endpoint(endpoint)

    async def capture(self, page_url: str, output_dir: Path) -> ProbeArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        browser = await CdpBrowserGateway(self.endpoint).connect()
        context = browser.contexts[0]
        page = next((p for p in context.pages if page_url in p.url), context.pages[0])
        html_path = output_dir / "page.html"
        screenshot_path = output_dir / "page.png"
        html_path.write_text(await page.content(), encoding="utf-8")
        await page.screenshot(path=str(screenshot_path), full_page=True)
        return ProbeArtifact(page.url, html_path, screenshot_path)
```

- [ ] **Step 4: Add explicit local browser launcher**

`scripts/start-chrome-cdp.ps1` starts a dedicated profile with a loopback-only debug address. The equivalent command shape is:

```powershell
& $chrome --remote-debugging-address=127.0.0.1 `
  --remote-debugging-port=9222 `
  "--user-data-dir=$profile" `
  https://qianchuan.jinritemai.com/
```

- [ ] **Step 5: Run unit tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_cdp_probe.py -v
```

Expected: PASS.

```powershell
git add backend/app/execution backend/tests/test_cdp_probe.py scripts/start-chrome-cdp.ps1
git commit -m "feat: add loopback-only CDP diagnostics"
```
---

### Task 5: Fixture Page Adapter, Metrics, and Analytics

**Files:**
- Create: `backend/app/execution/cdp/fixture_adapter.py`
- Create: `backend/app/services/analytics.py`
- Create: `backend/tests/fixtures/plan_live_snapshot.json`
- Create: `backend/tests/test_analytics.py`

**Interfaces:**
- Consumes: fixture JSON.
- Produces: `MetricSnapshot`; `FixturePageAdapter.read_snapshot(path) -> MetricSnapshot`; `AnalyticsService.compute(snapshot) -> ComputedMetrics`.

- [ ] **Step 1: Write failing metric tests**

```python
import pytest
from pathlib import Path
from app.execution.cdp.fixture_adapter import FixturePageAdapter
from app.services.analytics import AnalyticsService


def test_fixture_metrics_are_computed():
    snapshot = FixturePageAdapter().read_snapshot(Path("tests/fixtures/plan_live_snapshot.json"))
    metrics = AnalyticsService().compute(snapshot)
    assert metrics.roi == 2.5
    assert metrics.gpm == 1000
    assert metrics.spend == 400


def test_malformed_snapshot_fails_closed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"freshness":"fresh"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed page snapshot"):
        FixturePageAdapter().read_snapshot(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_analytics.py -v
```

Expected: FAIL because adapter and analytics service do not exist.

- [ ] **Step 3: Add fixture and implement adapter**

`backend/tests/fixtures/plan_live_snapshot.json`:

```json
{
  "captured_at": "2026-09-30T20:15:00+08:00",
  "freshness": "fresh",
  "plan": {"status": "active", "budget": 1200},
  "metrics": {
    "spend": 400,
    "gmv": 1000,
    "orders": 20,
    "views": 1000,
    "online_viewers": 120,
    "roi": null,
    "gpm": null
  }
}
```

`backend/app/execution/cdp/fixture_adapter.py`:

```python
import json
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel


class MetricSnapshot(BaseModel):
    captured_at: datetime
    freshness: str
    plan_status: str
    plan_budget: float
    spend: float
    gmv: float
    orders: int
    views: int
    online_viewers: int


class FixturePageAdapter:
    def read_snapshot(self, path: Path) -> MetricSnapshot:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return MetricSnapshot(
                captured_at=raw["captured_at"],
                freshness=raw["freshness"],
                plan_status=raw["plan"]["status"],
                plan_budget=raw["plan"]["budget"],
                **raw["metrics"],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Malformed page snapshot") from exc
```

- [ ] **Step 4: Implement analytics with explicit undefined behavior**

`backend/app/services/analytics.py`:

```python
from pydantic import BaseModel
from app.execution.cdp.fixture_adapter import MetricSnapshot


class ComputedMetrics(BaseModel):
    roi: float | None
    gpm: float | None
    spend: float
    gmv: float
    orders: int
    online_viewers: int


class AnalyticsService:
    def compute(self, snapshot: MetricSnapshot) -> ComputedMetrics:
        roi = snapshot.gmv / snapshot.spend if snapshot.spend > 0 else None
        gpm = snapshot.gmv / (snapshot.views / 1000) if snapshot.views > 0 else None
        return ComputedMetrics(
            roi=roi,
            gpm=gpm,
            spend=snapshot.spend,
            gmv=snapshot.gmv,
            orders=snapshot.orders,
            online_viewers=snapshot.online_viewers,
        )
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_analytics.py -v
```

Expected: PASS with `roi=2.5`, `gpm=1000.0`, `spend=400.0`.

```powershell
git add backend/app backend/tests
git commit -m "feat: add fixture-backed metrics and analytics"
```
---

### Task 6: Change Detector with Stale-Data Fail-Closed Behavior

**Files:**
- Create: `backend/app/services/changes.py`
- Create: `backend/tests/test_changes.py`

**Interfaces:**
- Consumes: `ComputedMetrics`.
- Produces: `ChangeDetector.evaluate(current, previous, stale) -> ChangeSignal`; `ChangeLevel` values `normal`, `watch`, `action`.

- [ ] **Step 1: Write failing tests**

```python
from app.services.analytics import ComputedMetrics
from app.services.changes import ChangeDetector, ChangeLevel


def metrics(roi: float, spend: float, gmv: float) -> ComputedMetrics:
    return ComputedMetrics(roi=roi, gpm=1000, spend=spend, gmv=gmv, orders=20, online_viewers=120)


def test_stale_data_never_recommends_action():
    signal = ChangeDetector().evaluate(metrics(1.5, 600, 900), metrics(3.0, 400, 1200), stale=True)
    assert signal.level == ChangeLevel.NORMAL
    assert signal.reason == "数据未刷新"


def test_two_bad_roi_windows_trigger_action():
    detector = ChangeDetector()
    first = detector.evaluate(metrics(2.2, 400, 880), metrics(3.0, 350, 1050), stale=False)
    second = detector.evaluate(metrics(1.9, 500, 950), metrics(2.2, 400, 880), stale=False)
    assert first.level in {ChangeLevel.WATCH, ChangeLevel.ACTION}
    assert second.level == ChangeLevel.ACTION
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_changes.py -v
```

Expected: FAIL because `changes.py` does not exist.

- [ ] **Step 3: Implement detector**

Use relative ROI change `<= -0.10` as watch, `<= -0.20` as action, require two consecutive non-normal windows for action, and return `NORMAL` for stale data.

```python
from enum import StrEnum
from pydantic import BaseModel
from app.services.analytics import ComputedMetrics


class ChangeLevel(StrEnum):
    NORMAL = "normal"
    WATCH = "watch"
    ACTION = "action"


class ChangeSignal(BaseModel):
    level: ChangeLevel
    reason: str
    roi_change: float | None
    spend_change: float | None


class ChangeDetector:
    def __init__(self) -> None:
        self._consecutive_non_normal = 0

    def evaluate(
        self,
        current: ComputedMetrics,
        previous: ComputedMetrics,
        stale: bool,
    ) -> ChangeSignal:
        if stale:
            self._consecutive_non_normal = 0
            return ChangeSignal(
                level=ChangeLevel.NORMAL,
                reason="数据未刷新",
                roi_change=None,
                spend_change=None,
            )
        roi_change = None
        if previous.roi and current.roi is not None:
            roi_change = (current.roi - previous.roi) / previous.roi
        spend_change = None
        if previous.spend > 0:
            spend_change = (current.spend - previous.spend) / previous.spend
        level = ChangeLevel.NORMAL
        reason = "指标正常"
        if roi_change is not None and roi_change <= -0.20:
            level = ChangeLevel.ACTION
            reason = "ROI 显著下降"
        elif roi_change is not None and roi_change <= -0.10:
            level = ChangeLevel.WATCH
            reason = "ROI 连续观察"
        if level != ChangeLevel.NORMAL:
            self._consecutive_non_normal += 1
        else:
            self._consecutive_non_normal = 0
        if self._consecutive_non_normal < 2 and level == ChangeLevel.ACTION:
            level = ChangeLevel.WATCH
            reason = "等待第二个确认窗口"
        return ChangeSignal(
            level=level,
            reason=reason,
            roi_change=roi_change,
            spend_change=spend_change,
        )
```

- [ ] **Step 4: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_changes.py -v
```

Expected: PASS.

```powershell
git add backend/app/services/changes.py backend/tests/test_changes.py
git commit -m "feat: add fail-closed change detector"
```
---

### Task 7: Monitor Service and Server-Sent Events

**Files:**
- Create: `backend/app/services/monitor.py`
- Create: `backend/app/api/monitor.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_monitor.py`

**Interfaces:**
- Consumes: fixture adapter, analytics service, change detector.
- Produces: `MonitorService.tick() -> MonitorEvent`; `GET /api/monitor/events` as SSE.

- [ ] **Step 1: Write failing monitor test**

```python
from pathlib import Path
import pytest
from app.services.monitor import MonitorService


@pytest.fixture
def monitor_service():
    return MonitorService(Path("tests/fixtures/plan_live_snapshot.json"), profile_version=1)


def test_monitor_emits_profile_and_freshness(monitor_service):
    event = monitor_service.tick()
    assert event.profile_version >= 1
    assert event.freshness in {"fresh", "stale"}
    assert "策略画像" in event.banner
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_monitor.py -v
```

Expected: FAIL because monitor service does not exist.

- [ ] **Step 3: Implement monitor event and service**

`backend/app/services/monitor.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel
from app.services.changes import ChangeDetector
from app.services.analytics import AnalyticsService
from app.execution.cdp.fixture_adapter import FixturePageAdapter


class MonitorEvent(BaseModel):
    captured_at: datetime
    freshness: str
    banner: str
    level: str
    reason: str
    profile_version: int


class MonitorService:
    def __init__(self, fixture_path: Path, profile_version: int = 1, interval_seconds: int = 300) -> None:
        self.fixture_path = fixture_path
        self.profile_version = profile_version
        self.interval_seconds = interval_seconds
        self.detector = ChangeDetector()

    def tick(self) -> MonitorEvent:
        snapshot = FixturePageAdapter().read_snapshot(self.fixture_path)
        metrics = AnalyticsService().compute(snapshot)
        signal = self.detector.evaluate(metrics, metrics, stale=snapshot.freshness != "fresh")
        return MonitorEvent(
            captured_at=datetime.now(timezone.utc),
            freshness=snapshot.freshness,
            banner=f"当前策略画像 v{self.profile_version}；大方向=稳定放量；ROI >= 2.5",
            level=signal.level,
            reason=signal.reason,
            profile_version=self.profile_version,
        )
```

- [ ] **Step 4: Add SSE endpoint and scheduler**

`backend/app/api/monitor.py`:

```python
import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/events")
async def monitor_events(request: Request):
    service = request.app.state.monitor_service

    async def stream():
        while True:
            event = service.tick()
            yield {"event": "monitor", "data": event.model_dump_json()}
            await asyncio.sleep(service.interval_seconds)

    return EventSourceResponse(stream())
```

`backend/app/services/monitor.py` must accept `interval_seconds: int = 300` and expose it as an attribute. `backend/app/main.py` creates the service during lifespan startup and assigns it to `app.state.monitor_service`.

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_monitor.py -v
```

Expected: PASS.

```powershell
git add backend/app backend/tests/test_monitor.py
git commit -m "feat: add monitor events and profile banner"
```

---

### Task 8: Recommendations and Confirmation Records Without Execution

**Files:**
- Create: `backend/app/services/recommendations.py`
- Create: `backend/app/services/confirmations.py`
- Create: `backend/app/api/recommendations.py`
- Create: `backend/tests/test_recommendations.py`
- Create: `backend/tests/test_confirmations.py`

**Interfaces:**
- Consumes: `ChangeSignal`, active `StrategyProfile`.
- Produces: `RecommendationEngine.recommend(signal, profile) -> Recommendation`; `ConfirmationService.create(recommendation, action, profile) -> PendingConfirmation`; `ConfirmationService.validate(confirmation_id, profile_version, preview_hash) -> bool`.

- [ ] **Step 1: Write failing tests**

```python
from app.services.changes import ChangeLevel, ChangeSignal
from app.services.confirmations import ConfirmationService
from app.services.recommendations import RecommendationEngine


def test_action_change_creates_recommendation(profile):
    signal = ChangeSignal(
        level=ChangeLevel.ACTION,
        reason="ROI 显著下降",
        roi_change=-0.25,
        spend_change=0.30,
    )
    recommendation = RecommendationEngine().recommend(signal, profile)
    assert recommendation is not None
    assert recommendation.action == "update_plan_budget"
    assert "人工确认" in recommendation.reason


def test_confirmation_invalid_after_profile_version_change(profile):
    confirmation_service = ConfirmationService()
    confirmation = confirmation_service.create(
        recommendation_id="rec-1",
        action={"action_name": "update_plan_budget", "target_id": "plan-1", "budget": 800},
        profile=profile,
    )
    assert confirmation_service.validate(confirmation.id, profile.version, confirmation.preview_hash)
    assert not confirmation_service.validate(confirmation.id, profile.version + 1, confirmation.preview_hash)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_recommendations.py tests/test_confirmations.py -v
```

Expected: FAIL because recommendation and confirmation services do not exist.

- [ ] **Step 3: Implement recommendation contract**

`backend/app/services/recommendations.py`:

```python
from pydantic import BaseModel
from app.models import StrategyProfile
from app.services.changes import ChangeLevel, ChangeSignal


class Recommendation(BaseModel):
    reason: str
    action: str
    confidence: str
    strategy_profile_version: int
    requires_confirmation: bool = True


class RecommendationEngine:
    def recommend(self, signal: ChangeSignal, profile: StrategyProfile) -> Recommendation | None:
        if signal.level != ChangeLevel.ACTION:
            return None
        if "update_plan_budget" not in profile.allowed_actions:
            return None
        return Recommendation(
            reason=f"{signal.reason}；必须人工确认后执行。",
            action="update_plan_budget",
            confidence="medium",
            strategy_profile_version=profile.version,
        )
```

- [ ] **Step 4: Implement confirmation records and validation**

`backend/app/services/confirmations.py`:

```python
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel


class PendingConfirmation(BaseModel):
    id: str
    recommendation_id: str
    action: dict
    preview_hash: str
    strategy_profile_version: int
    expires_at: datetime
    status: str = "pending"


class ConfirmationService:
    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._records: dict[str, PendingConfirmation] = {}

    @staticmethod
    def _hash(action: dict) -> str:
        payload = json.dumps(action, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def create(
        self,
        recommendation_id: str,
        action: dict,
        profile,
    ) -> PendingConfirmation:
        confirmation = PendingConfirmation(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            action=action,
            preview_hash=self._hash(action),
            strategy_profile_version=profile.version,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.ttl_minutes),
        )
        self._records[confirmation.id] = confirmation
        return confirmation

    def validate(
        self,
        confirmation_id: str,
        profile_version: int,
        preview_hash: str,
    ) -> bool:
        confirmation = self._records.get(confirmation_id)
        if confirmation is None or confirmation.status != "pending":
            return False
        if confirmation.expires_at <= datetime.now(timezone.utc):
            return False
        if confirmation.strategy_profile_version != profile_version:
            return False
        return confirmation.preview_hash == preview_hash
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_recommendations.py tests/test_confirmations.py -v
```

Expected: PASS.

```powershell
git add backend/app backend/tests
git commit -m "feat: add recommendations and pending confirmations"
```
---

### Task 9: Nordic Minimal Frontend Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/StrategyBanner.tsx`
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/components/LiveMonitorPanel.tsx`
- Create: `frontend/src/components/DecisionPanel.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/strategy-banner.test.tsx`
- Create: `frontend/src/test/decision-panel.test.tsx`

**Interfaces:**
- Consumes: backend `/api/profiles/active`, `/api/chat`, `/api/monitor/events`.
- Produces: local single-page UI with sticky strategy banner and visible freshness labels.

- [ ] **Step 1: Write failing UI tests**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { StrategyBanner } from "../components/StrategyBanner";
import { DecisionPanel } from "../components/DecisionPanel";

test("strategy banner is always visible with profile data", () => {
  render(<StrategyBanner profile={{
    version: 3,
    business_direction: "稳定放量",
    primary_objective: "ROI >= 2.5 且提升成交额",
    hard_constraints: { daily_budget_max: 5000 },
    data_time: "2026-09-30T20:15:00+08:00",
    freshness: "fresh"
  }} />);
  expect(screen.getByText(/策略画像 v3/)).toBeInTheDocument();
  expect(screen.getByText(/ROI >= 2.5/)).toBeInTheDocument();
  expect(screen.getByText(/数据最新/)).toBeInTheDocument();
});

test("decision panel requires an explicit confirmation click", () => {
  const confirmed: string[] = [];
  render(
    <DecisionPanel
      decisions={[{ id: "d1", title: "计划 A 降预算", reason: "ROI 连续下降", confidence: "medium" }]}
      onConfirm={(id) => confirmed.push(id)}
      onReject={() => undefined}
    />
  );
  expect(confirmed).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "确认执行建议" }));
  expect(confirmed).toEqual(["d1"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd frontend
npm install
npm run test -- --run strategy-banner
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement Nordic tokens**

`frontend/src/styles/tokens.css`:

```css
:root {
  --color-background: #F6F6F3;
  --color-surface: #FFFFFF;
  --color-surface-muted: #ECECE7;
  --color-text-primary: #1C1F1D;
  --color-text-secondary: #66706B;
  --color-border: #D9DCD7;
  --color-accent: #4F6F64;
  --color-accent-hover: #405B52;
  --color-success: #5E7F65;
  --color-warning: #B08A55;
  --color-danger: #A45D5D;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --radius-card: 12px;
  --radius-button: 8px;
  --font-sans: Inter, system-ui, "Noto Sans SC", "Microsoft YaHei", sans-serif;
}

body {
  margin: 0;
  background: var(--color-background);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.6;
}
```

- [ ] **Step 4: Implement layout and decision UI**

`frontend/src/components/StrategyBanner.tsx`:

```tsx
export type StrategyBannerProfile = {
  version: number;
  business_direction: string;
  primary_objective: string;
  hard_constraints: Record<string, unknown>;
  data_time: string;
  freshness: "fresh" | "stale";
};

export function StrategyBanner({ profile }: { profile: StrategyBannerProfile }) {
  return (
    <header className="strategy-banner">
      <strong>策略画像 v{profile.version}</strong>
      <span>{profile.business_direction}</span>
      <span>{profile.primary_objective}</span>
      <span>约束：{JSON.stringify(profile.hard_constraints)}</span>
      <span>{profile.freshness === "fresh" ? "数据最新" : "数据未刷新"}</span>
      <time dateTime={profile.data_time}>{profile.data_time}</time>
    </header>
  );
}
```

`frontend/src/components/DecisionPanel.tsx`:

```tsx
type Decision = {
  id: string;
  title: string;
  reason: string;
  confidence: string;
};

export function DecisionPanel({
  decisions,
  onConfirm,
  onReject,
}: {
  decisions: Decision[];
  onConfirm: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <section className="decision-panel">
      <h2>待确认建议</h2>
      {decisions.map((decision) => (
        <article key={decision.id} className="decision-card">
          <h3>{decision.title}</h3>
          <p>{decision.reason}</p>
          <small>置信度：{decision.confidence}</small>
          <div className="decision-actions">
            <button className="button-outline" onClick={() => onReject(decision.id)}>
              暂不执行
            </button>
            <button className="button-primary" onClick={() => onConfirm(decision.id)}>
              确认执行建议
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
```

`App.tsx` places StrategyBanner above a two-column CSS grid: ChatPanel on the left and LiveMonitorPanel plus DecisionPanel on the right. The stylesheet uses the tokens from Step 3 and no gradients or box-shadow larger than `0 1px 2px rgba(0,0,0,0.06)`.

- [ ] **Step 5: Run frontend tests and commit**

Run:

```powershell
npm run test -- --run
npm run build
```

Expected: PASS and production build succeeds.

```powershell
git add frontend
git commit -m "feat: add Nordic minimal local UI shell"
```

---

### Task 10: Local Runbook and Acceptance Test

**Files:**
- Create: `scripts/start-dev.ps1`
- Create: `docs/runbooks/local-development.md`
- Create: `backend/tests/test_acceptance_readonly.py`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: one command to start the local stack and an acceptance test proving read-only monitoring works.

- [ ] **Step 1: Write failing acceptance test**

```python
from pathlib import Path
from app.services.monitor import MonitorService


def test_read_only_acceptance_flow(client):
    profile = client.get("/api/profiles/active")
    assert profile.status_code == 200
    monitor_service = MonitorService(
        Path("tests/fixtures/plan_live_snapshot.json"),
        profile_version=profile.json()["version"],
    )
    event = monitor_service.tick()
    assert event.banner
    assert event.freshness in {"fresh", "stale"}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests/test_acceptance_readonly.py -v
```

Expected: FAIL until the runbook fixture setup and monitor service are complete.

- [ ] **Step 3: Add runbook and launcher**

`scripts/start-dev.ps1`:

```powershell
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root ".local\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$backend = Start-Job -ScriptBlock {
  Set-Location (Join-Path $using:root "backend")
  & .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
}

$frontend = Start-Job -ScriptBlock {
  Set-Location (Join-Path $using:root "frontend")
  npm run dev -- --host 127.0.0.1
}

Write-Output "Backend job: $($backend.Id)"
Write-Output "Frontend job: $($frontend.Id)"
Write-Output "Open http://127.0.0.1:5173"
```

`docs/runbooks/local-development.md`:

```markdown
# Local Development Runbook

1. Install backend dependencies with `pip install -e ".[dev]"`.
2. Install frontend dependencies with `npm install`.
3. Start the stack with `scripts/start-dev.ps1`.
4. Start the dedicated browser with `scripts/start-chrome-cdp.ps1`.
5. Log in to Qianchuan manually in that browser.
6. Run the CDP page probe and inspect `page.html` and `page.png`.
7. Use fixture mode until the selectors are calibrated against the captured page.
8. Open `http://127.0.0.1:5173`.
9. Confirm the strategy banner is visible before reviewing monitor events.
10. No write action is available in this phase.
```

- [ ] **Step 4: Run complete verification**

Run:

```powershell
cd backend
.\.venv\Scripts\python -m pytest -v
cd ..\frontend
npm run test -- --run
npm run build
```

Expected: all tests pass and the frontend build succeeds.

- [ ] **Step 5: Commit**

```powershell
git add scripts docs backend/tests/test_acceptance_readonly.py
git commit -m "docs: add local runbook and read-only acceptance"
```

---

## Plan Self-Review

### Spec Coverage

- Chatbot: Tasks 3 and 9.
- Persistent strategy profile and versioning: Task 2.
- Every-output strategy reminder: Tasks 7 and 9.
- 5-10 minute monitoring: Task 7.
- ROI, spend, GMV, orders, GPM, online viewers: Tasks 5, 6, and 7.
- Change detection and recommendations: Tasks 6 and 8.
- Human confirmation records: Task 8.
- CDP loopback and diagnostics: Task 4.
- No writes in Phase 1: Global Constraints and Task 8.
- Nordic minimal UI: Task 9.
- Security and local-only operation: Task 4, Task 9, and Task 10.
- Tests and acceptance: Tasks 1-10.

Write operations, real selectors, learning, and API provider migration are explicitly assigned to later plans.

### Placeholder Scan

The plan contains no `TBD`, `TODO`, deferred implementation language, or unspecified test behavior. The only external integration that requires a live environment is selector calibration; it uses diagnostics and fixture mode until selectors are captured.

### Type Consistency

- `MetricSnapshot` is defined in Task 5 and consumed in Tasks 5-7.
- `ComputedMetrics` is defined in Task 5 and consumed in Task 6.
- `ChangeSignal` and `ChangeLevel` are defined in Task 6 and consumed in Tasks 7-8.
- `StrategyProfile.version` is defined in Task 2 and used by confirmation validation in Task 8.
- `LLMProvider.complete` is defined in Task 3 and consumed by `Orchestrator`.
- `validate_cdp_endpoint` is defined in Task 4 and used by the probe.

### Review Focus Mapping

- Stale data: Task 6 test.
- Missing or malformed page: Task 4 diagnostics and Task 5 fixture adapter validation.
- Malformed LLM output: Task 3 test.
- Confirmation invalidation: Task 8 test.
- Nordic banner and freshness visibility: Task 9 test.