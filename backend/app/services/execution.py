import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execution.base import ExecutionProvider
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

    async def run_confirmation(self, confirmation_id: str) -> ExecutionRecord:
        confirmation = self.confirmations.get(confirmation_id)
        if confirmation is None:
            raise ValueError("Confirmation not found")
        if not self.confirmations.claim(confirmation_id):
            existing = self.session.scalar(
                select(ExecutionJob).where(ExecutionJob.confirmation_id == confirmation_id)
            )
            if existing is None:
                raise RuntimeError("Confirmation could not be claimed")
            return self._record(existing)

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
        result = await self.provider.execute(action)
        self._log(job.id, "execute", {"before": result.before, "after": result.after})

        job.status = "verifying"
        self.session.commit()
        verification = await self.provider.verify(action, result)
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
        artifact_dir = self.audit.record(
            job.id,
            result.before,
            verification.after,
            job.result,
        )
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

    @staticmethod
    def _record(job: ExecutionJob) -> ExecutionRecord:
        return ExecutionRecord(
            job_id=job.id,
            status=job.status,
            before=job.result.get("before", {}),
            after=job.result.get("after", {}),
        )