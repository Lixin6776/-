import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from app.models import StrategyProfile


class PendingConfirmation(BaseModel):
    id: str
    recommendation_id: str
    action: dict
    preview_hash: str
    strategy_profile_version: int
    expires_at: datetime
    status: str = "pending"


class ConfirmationService:
    def __init__(self, ttl_minutes: int = 10) -> None:
        self.ttl_minutes = ttl_minutes
        self._records: dict[str, PendingConfirmation] = {}

    @staticmethod
    def _hash(action: dict) -> str:
        payload = json.dumps(action, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def create(
        self,
        recommendation_id: str,
        action: dict,
        profile: StrategyProfile,
    ) -> PendingConfirmation:
        confirmation = PendingConfirmation(
            id=str(uuid.uuid4()),
            recommendation_id=recommendation_id,
            action=action,
            preview_hash=self._hash(action),
            strategy_profile_version=profile.version,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self.ttl_minutes),
        )
        self._records[confirmation.id] = confirmation
        return confirmation

    def validate(
        self,
        confirmation_id: str,
        profile_version: int,
        preview_hash: str,
    ) -> bool:
        confirmation = self._records.get(confirmation_id)
        if confirmation is None or confirmation.status != "pending":
            return False
        if confirmation.expires_at <= datetime.now(timezone.utc):
            return False
        if confirmation.strategy_profile_version != profile_version:
            return False
        return confirmation.preview_hash == preview_hash