import pytest

from app.execution.fake_provider import FakeExecutionProvider
from app.services.confirmations import ConfirmationService
from app.services.execution import ExecutionService


@pytest.fixture
def confirmation_service(db_session):
    return ConfirmationService(db_session)


@pytest.mark.asyncio
async def test_fake_provider_executes_and_verifies(db_session, confirmation_service, preview):
    confirmation = confirmation_service.create_from_preview(preview)
    provider = FakeExecutionProvider(
        initial_plan={"id": "plan-1", "status": "active", "budget": 1000}
    )
    service = ExecutionService(provider, confirmation_service, db_session)
    result = await service.run_confirmation(confirmation.id)
    assert result.status == "succeeded"
    assert result.after["status"] == "paused"