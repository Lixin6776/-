import pytest

from app.execution.fake_provider import FakeExecutionProvider
from app.services.audit import AuditService
from app.services.confirmations import ConfirmationService
from app.services.execution import ExecutionService


@pytest.fixture
def confirmation_service(db_session):
    return ConfirmationService(db_session)


@pytest.fixture
def confirmation(confirmation_service, preview):
    return confirmation_service.create_from_preview(preview)


@pytest.fixture
def execution_service(db_session, confirmation_service, tmp_path):
    provider = FakeExecutionProvider(
        initial_plan={"id": "plan-1", "status": "active", "budget": 1000}
    )
    return ExecutionService(
        provider,
        confirmation_service,
        db_session,
        audit=AuditService(tmp_path),
    )


@pytest.mark.asyncio
async def test_successful_job_writes_before_after_and_screenshot(
    execution_service,
    confirmation,
):
    result = await execution_service.run_confirmation(confirmation.id)
    logs = execution_service.logs_for(result.job_id)
    phases = [item.phase for item in logs]
    assert phases == ["preflight", "execute", "verify", "audit"]
    assert logs[-1].payload["before"]["status"] == "active"
    assert logs[-1].payload["after"]["status"] == "paused"
    assert logs[-1].artifact_dir