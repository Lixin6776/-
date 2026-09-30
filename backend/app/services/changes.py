from enum import StrEnum

from pydantic import BaseModel

from app.services.analytics import ComputedMetrics


class ChangeLevel(StrEnum):
    NORMAL = "normal"
    WATCH = "watch"
    ACTION = "action"


class ChangeSignal(BaseModel):
    level: ChangeLevel
    reason: str
    roi_change: float | None
    spend_change: float | None


class ChangeDetector:
    def __init__(self) -> None:
        self._consecutive_non_normal = 0

    def evaluate(
        self,
        current: ComputedMetrics,
        previous: ComputedMetrics,
        stale: bool,
    ) -> ChangeSignal:
        if stale:
            self._consecutive_non_normal = 0
            return ChangeSignal(
                level=ChangeLevel.NORMAL,
                reason="数据未刷新",
                roi_change=None,
                spend_change=None,
            )

        roi_change = None
        if previous.roi and current.roi is not None:
            roi_change = (current.roi - previous.roi) / previous.roi

        spend_change = None
        if previous.spend > 0:
            spend_change = (current.spend - previous.spend) / previous.spend

        level = ChangeLevel.NORMAL
        reason = "指标正常"
        if roi_change is not None and roi_change <= -0.20:
            level = ChangeLevel.ACTION
            reason = "ROI 显著下降"
        elif roi_change is not None and roi_change <= -0.10:
            level = ChangeLevel.WATCH
            reason = "ROI 连续观察"

        if level != ChangeLevel.NORMAL:
            self._consecutive_non_normal += 1
        else:
            self._consecutive_non_normal = 0

        if level != ChangeLevel.NORMAL and self._consecutive_non_normal >= 2:
            level = ChangeLevel.ACTION
            reason = "连续两个周期 ROI 下降"
        elif level == ChangeLevel.ACTION:
            level = ChangeLevel.WATCH
            reason = "等待第二个确认窗口"

        return ChangeSignal(
            level=level,
            reason=reason,
            roi_change=roi_change,
            spend_change=spend_change,
        )