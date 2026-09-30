from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import StrategyProfile
from app.schemas import StrategyProfileCreate


class StrategyProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_version(self, payload: StrategyProfileCreate) -> StrategyProfile:
        latest = self.session.scalar(
            select(StrategyProfile).order_by(StrategyProfile.version.desc()).limit(1)
        )
        next_version = 1 if latest is None else latest.version + 1
        self.session.execute(update(StrategyProfile).values(active=False))
        profile = StrategyProfile(version=next_version, active=True, **payload.model_dump())
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_active(self) -> StrategyProfile:
        profile = self.session.scalar(
            select(StrategyProfile).where(StrategyProfile.active.is_(True)).limit(1)
        )
        if profile is None:
            raise LookupError("No active strategy profile")
        return profile