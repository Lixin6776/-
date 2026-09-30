from typing import Protocol

from pydantic import BaseModel


class UnknownExecutionState(RuntimeError):
    pass

from app.services.action_registry import ActionEnvelope


class PreflightResult(BaseModel):
    ok: bool
    before: dict
    message: str = ""


class ExecutionResult(BaseModel):
    action: dict
    before: dict
    after: dict
    message: str = ""


class VerificationResult(BaseModel):
    ok: bool
    before: dict
    after: dict
    message: str = ""


class CancelResult(BaseModel):
    cancelled: bool
    message: str = ""


class ExecutionProvider(Protocol):
    async def preflight(self, action: ActionEnvelope) -> PreflightResult:
        ...

    async def execute(self, action: ActionEnvelope) -> ExecutionResult:
        ...

    async def verify(self, action: ActionEnvelope, result: ExecutionResult) -> VerificationResult:
        ...

    async def cancel(self, job_id: str) -> CancelResult:
        ...