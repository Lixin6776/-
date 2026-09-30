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