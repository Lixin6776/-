from datetime import UTC, datetime, timedelta

import pytest

from app.services.action_planner import ActionPreview
from app.services.action_registry import ActionName
from app.services.confirmations import ConfirmationService


@pytest.fixture
def preview():
    return ActionPreview(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        target_name="计划 A",
        normalized_params={"target_id": "plan-1"},
        diff={"status": {"before": "active", "after": "paused"}},
        blockers=[],
        warnings=[],
        allowed=True,
        strategy_profile_version=1,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        preview_hash="hash-1",
        idempotency_key="idem-1",
    )


@pytest.fixture
def confirmation_service(db_session):
    return ConfirmationService(db_session)


def test_confirmation_cannot_be_executed_twice(confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview)
    assert confirmation_service.claim(confirmation.id) is True
    assert confirmation_service.claim(confirmation.id) is False


def test_confirmation_expiry_is_enforced(confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview, ttl_minutes=-1)
    assert confirmation_service.validate(confirmation.id) is False