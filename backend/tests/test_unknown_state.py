import pytest

from app.execution.base import UnknownExecutionState
from app.services.audit import AuditService
from app.services.confirmations import ConfirmationService
from app.services.execution import ExecutionService


class UnknownProvider:
    def __init__(self):
        self.execute_calls = 0

    async def preflight(self, action):
        from app.execution.base import PreflightResult

        return PreflightResult(
            ok=True,
            before={"id": "plan-1", "status": "active", "budget": 1000},
        )

    async def execute(self, action):
        from app.execution.base import ExecutionResult

        self.execute_calls += 1
        return ExecutionResult(
            action={"action_name": action.action_name.value, "target_id": action.target_id},
            before={"id": "plan-1", "status": "active", "budget": 1000},
            after={"id": "plan-1", "status": "paused", "budget": 1000},
        )

    async def verify(self, action, result):
        raise UnknownExecutionState("page unreadable")

    async def cancel(self, job_id):
        from app.execution.base import CancelResult

        return CancelResult(cancelled=False)


@pytest.fixture
def unknown_provider():
    return UnknownProvider()


@pytest.fixture
def confirmation_service(db_session):
    return ConfirmationService(db_session)


@pytest.fixture
def confirmation(confirmation_service, preview):
    return confirmation_service.create_from_preview(preview)


@pytest.mark.asyncio
async def test_unreadable_page_sets_unknown_and_does_not_retry(
    unknown_provider,
    execution_service,
    confirmation,
):
    result = await execution_service.run_confirmation(confirmation.id)
    assert result.status == "unknown"
    assert unknown_provider.execute_calls == 1
    repeated = await execution_service.run_confirmation(confirmation.id)
    assert repeated.status == "unknown"
    assert unknown_provider.execute_calls == 1

@pytest.fixture
def execution_service(db_session, confirmation_service, unknown_provider, tmp_path):
    return ExecutionService(
        unknown_provider,
        confirmation_service,
        db_session,
        audit=AuditService(tmp_path),
    )