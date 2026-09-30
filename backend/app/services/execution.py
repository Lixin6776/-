import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execution.base import ExecutionProvider, UnknownExecutionState
from app.models import ExecutionJob, ExecutionLog
from app.services.action_registry import ActionEnvelope
from app.services.audit import AuditService
from app.services.confirmations import ConfirmationService


class ExecutionRecord(BaseModel):
    job_id: str
    status: str
    before: dict
    after: dict


class ExecutionService:
    TERMINAL_STATUSES: ClassVar[set[str]] = {"succeeded", "failed", "unknown", "cancelled"}

    def __init__(
        self,
        provider: ExecutionProvider,
        confirmations: ConfirmationService,
        session: Session,
        audit: AuditService | None = None,
    ) -> None:
        self.provider = provider
        self.confirmations = confirmations
        self.session = session
        self.audit = audit or AuditService(Path(".local/artifacts"))
        self._events: dict[str, asyncio.Event] = {}
        self._completed: dict[str, ExecutionRecord] = {}

    async def run_confirmation(self, confirmation_id: str) -> ExecutionRecord:
        completed = self._completed.get(confirmation_id)
        if completed is not None:
            return completed
        event = self._events.get(confirmation_id)
        if event is not None:
            await event.wait()
            return self._completed[confirmation_id]

        confirmation = self.confirmations.get(confirmation_id)
        if confirmation is None:
            raise ValueError("Confirmation not found")
        if not self.confirmations.claim(confirmation_id):
            return await self._wait_for_existing(confirmation_id)

        event = asyncio.Event()
        self._events[confirmation_id] = event
        try:
            record = await self._execute_claimed(confirmation)
            self._completed[confirmation_id] = record
            return record
        finally:
            event.set()

    async def _execute_claimed(self, confirmation) -> ExecutionRecord:
        action = self._action_from_confirmation(confirmation)
        job = ExecutionJob(
            id=str(uuid.uuid4()),
            confirmation_id=confirmation.id,
            action_name=confirmation.action_name,
            status="preflight",
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            result={},
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

        preflight = await self.provider.preflight(action)
        self._log(job.id, "preflight", {"ok": preflight.ok, "before": preflight.before})
        if not preflight.ok:
            return self._fail(job, preflight.message, preflight.before)

        job.status = "executing"
        self.session.commit()
        try:
            result = await self.provider.execute(action)
            self._log(job.id, "execute", {"before": result.before, "after": result.after})
            job.status = "verifying"
            self.session.commit()
            verification = await self.provider.verify(action, result)
        except UnknownExecutionState as exc:
            return self._unknown(job, str(exc))

        self._log(
            job.id,
            "verify",
            {
                "ok": verification.ok,
                "before": verification.before,
                "after": verification.after,
                "message": verification.message,
            },
        )
        if not verification.ok:
            return self._fail(job, verification.message, verification.after, result.before)

        job.status = "succeeded"
        job.finished_at = datetime.now(UTC)
        job.result = {"before": result.before, "after": verification.after}
        self.session.commit()
        artifact_dir = self.audit.record(job.id, result.before, verification.after, job.result)
        self._log(
            job.id,
            "audit",
            {
                "before": result.before,
                "after": verification.after,
                "artifact_dir": artifact_dir,
            },
            artifact_dir=artifact_dir,
        )
        self.confirmations.finish(confirmation.id, "succeeded")
        return ExecutionRecord(
            job_id=job.id,
            status="succeeded",
            before=result.before,
            after=verification.after,
        )

    async def _wait_for_existing(self, confirmation_id: str) -> ExecutionRecord:
        for _ in range(100):
            job = self.session.scalar(
                select(ExecutionJob).where(ExecutionJob.confirmation_id == confirmation_id)
            )
            if job is None:
                raise RuntimeError("Confirmation could not be claimed")
            if job.status in self.TERMINAL_STATUSES:
                return self._record(job)
            await asyncio.sleep(0.01)
        raise RuntimeError("Execution job did not reach a terminal state")

    def logs_for(self, job_id: str) -> list[ExecutionLog]:
        return list(
            self.session.scalars(
                select(ExecutionLog)
                .where(ExecutionLog.job_id == job_id)
                .order_by(ExecutionLog.created_at.asc())
            )
        )

    @staticmethod
    def _action_from_confirmation(confirmation) -> ActionEnvelope:
        params = dict(confirmation.action_params)
        target_id = str(params.pop("target_id"))
        params.pop("_diff", None)
        return ActionEnvelope(
            action_name=confirmation.action_name,
            target_id=target_id,
            params=params,
        )

    def _log(
        self,
        job_id: str,
        phase: str,
        payload: dict,
        artifact_dir: str | None = None,
    ) -> None:
        self.session.add(
            ExecutionLog(
                id=str(uuid.uuid4()),
                job_id=job_id,
                phase=phase,
                payload=json.loads(json.dumps(payload, ensure_ascii=False, default=str)),
                artifact_dir=artifact_dir,
                created_at=datetime.now(UTC),
            )
        )
        self.session.commit()

    def _fail(
        self,
        job: ExecutionJob,
        message: str,
        after: dict,
        before: dict | None = None,
    ) -> ExecutionRecord:
        job.status = "failed"
        job.error = message
        job.finished_at = datetime.now(UTC)
        job.result = {"before": before or {}, "after": after}
        self.session.commit()
        self.confirmations.finish(job.confirmation_id, "failed")
        return ExecutionRecord(
            job_id=job.id,
            status="failed",
            before=before or {},
            after=after,
        )

    def _unknown(self, job: ExecutionJob, message: str) -> ExecutionRecord:
        job.status = "unknown"
        job.error = message
        job.finished_at = datetime.now(UTC)
        job.result = {"before": {}, "after": {}}
        self.session.commit()
        self.confirmations.finish(job.confirmation_id, "failed")
        return ExecutionRecord(
            job_id=job.id,
            status="unknown",
            before={},
            after={},
        )

    @staticmethod
    def _record(job: ExecutionJob) -> ExecutionRecord:
        return ExecutionRecord(
            job_id=job.id,
            status=job.status,
            before=job.result.get("before", {}),
            after=job.result.get("after", {}),
        )