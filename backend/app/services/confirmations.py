import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import PendingConfirmation, StrategyProfile
from app.services.action_planner import ActionPreview
from app.services.action_registry import ActionName


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ConfirmationService:
    def __init__(self, session: Session | None = None, ttl_minutes: int = 10) -> None:
        self.session = session
        self.ttl_minutes = ttl_minutes
        self._records: dict[str, PendingConfirmation] = {}

    @staticmethod
    def _hash(action: dict) -> str:
        payload = json.dumps(action, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def create_from_preview(
        self,
        preview: ActionPreview,
        ttl_minutes: int | None = None,
    ) -> PendingConfirmation:
        if not preview.allowed:
            raise ValueError("Cannot create confirmation from a blocked preview")
        if self.session is not None:
            existing = self.session.scalar(
                select(PendingConfirmation).where(
                    PendingConfirmation.idempotency_key == preview.idempotency_key
                )
            )
            if existing is not None:
                return existing
        ttl = self.ttl_minutes if ttl_minutes is None else ttl_minutes
        confirmation = PendingConfirmation(
            id=str(uuid.uuid4()),
            recommendation_id=None,
            status="pending",
            action_name=preview.action_name.value,
            action_params={
                "target_id": preview.target_id,
                **preview.normalized_params,
                "_diff": preview.diff,
            },
            preview_hash=preview.preview_hash,
            strategy_profile_version=preview.strategy_profile_version,
            idempotency_key=preview.idempotency_key,
            expires_at=datetime.now(UTC) + timedelta(minutes=ttl),
        )
        if self.session is not None:
            self.session.add(confirmation)
            self.session.commit()
            self.session.refresh(confirmation)
        else:
            self._records[confirmation.id] = confirmation
        return confirmation

    def create(
        self,
        recommendation_id: str,
        action: dict,
        profile: StrategyProfile,
    ) -> PendingConfirmation:
        action_name = str(action.get("action_name", "unknown"))
        params = {key: value for key, value in action.items() if key != "action_name"}
        preview = ActionPreview(
            action_name=ActionName(action_name),
            target_id=str(params.get("target_id", "")),
            target_name=str(params.get("target_id", "")),
            normalized_params=params,
            diff={},
            blockers=[],
            warnings=[],
            allowed=True,
            strategy_profile_version=profile.version,
            expires_at=datetime.now(UTC) + timedelta(minutes=self.ttl_minutes),
            preview_hash=self._hash(action),
            idempotency_key=f"idem:{self._hash(action)}",
        )
        confirmation = self.create_from_preview(preview)
        confirmation.recommendation_id = recommendation_id
        if self.session is not None:
            self.session.commit()
            self.session.refresh(confirmation)
        return confirmation

    def get(self, confirmation_id: str) -> PendingConfirmation | None:
        if self.session is not None:
            return self.session.get(PendingConfirmation, confirmation_id)
        return self._records.get(confirmation_id)

    def validate(
        self,
        confirmation_id: str,
        profile_version: int | None = None,
        preview_hash: str | None = None,
    ) -> bool:
        confirmation = self.get(confirmation_id)
        if confirmation is None or confirmation.status != "pending":
            return False
        if _as_utc(confirmation.expires_at) <= datetime.now(UTC):
            return False
        return not (
            (
                profile_version is not None
                and confirmation.strategy_profile_version != profile_version
            )
            or (preview_hash is not None and confirmation.preview_hash != preview_hash)
        )

    def claim(self, confirmation_id: str) -> bool:
        now = datetime.now(UTC)
        if self.session is not None:
            result = self.session.execute(
                update(PendingConfirmation)
                .where(
                    PendingConfirmation.id == confirmation_id,
                    PendingConfirmation.status == "pending",
                    PendingConfirmation.expires_at > now,
                )
                .values(status="executing", claimed_at=now).execution_options(synchronize_session=False))
            self.session.commit()
            return getattr(result, "rowcount", 0) == 1
        confirmation = self._records.get(confirmation_id)
        if confirmation is None or confirmation.status != "pending":
            return False
        if _as_utc(confirmation.expires_at) <= now:
            return False
        confirmation.status = "executing"
        confirmation.claimed_at = now
        return True

    def finish(self, confirmation_id: str, status: str) -> None:
        confirmation = self.get(confirmation_id)
        if confirmation is None:
            return
        confirmation.status = status
        confirmation.executed_at = datetime.now(UTC)
        if self.session is not None:
            self.session.commit()