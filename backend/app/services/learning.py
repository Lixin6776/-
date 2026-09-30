import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExecutionJob, LearningCase, StrategySuggestion
from app.services.outcomes import OutcomeAttributionService


class LearningService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def reject(self, suggestion_id: str, reason: str) -> StrategySuggestion:
        suggestion = self.session.get(StrategySuggestion, suggestion_id)
        if suggestion is None:
            raise LookupError("Suggestion not found")
        suggestion.status = "rejected"
        suggestion.evidence = {**suggestion.evidence, "rejection_reason": reason}
        self.session.commit()
        self.session.refresh(suggestion)
        return suggestion

    def was_rejected(self, proposed_change: dict) -> bool:
        suggestions = self.session.scalars(
            select(StrategySuggestion).where(StrategySuggestion.status == "rejected")
        )
        target = json.dumps(proposed_change, sort_keys=True, ensure_ascii=False)
        return any(
            json.dumps(item.proposed_change, sort_keys=True, ensure_ascii=False) == target
            for item in suggestions
        )

    def replay(self, execution_job_id: str) -> dict:
        job = self.session.get(ExecutionJob, execution_job_id)
        if job is None:
            raise LookupError("Execution job not found")
        return json.loads(json.dumps(job.result, ensure_ascii=False, default=str))
    def record_execution_case(self, job: ExecutionJob, profile_version: int) -> LearningCase:
        case = LearningCase(
            strategy_profile_version=profile_version,
            confirmation_id=job.confirmation_id,
            execution_job_id=job.id,
            action_name=job.action_name,
            context={
                "status": job.status,
                "before": job.result.get("before", {}),
                "after": job.result.get("after", {}),
            },
            status="observed",
        )
        self.session.add(case)
        self.session.commit()
        self.session.refresh(case)
        OutcomeAttributionService(self.session).record(
            case_id=case.id,
            before=job.result.get("before", {}),
            after=job.result.get("after", {}),
            windows=["5m", "30m"],
        )
        return case
