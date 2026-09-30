from app.services.analytics import ComputedMetrics
from app.services.changes import ChangeDetector, ChangeLevel


def metrics(roi: float, spend: float, gmv: float) -> ComputedMetrics:
    return ComputedMetrics(roi=roi, gpm=1000, spend=spend, gmv=gmv, orders=20, online_viewers=120)


def test_stale_data_never_recommends_action():
    signal = ChangeDetector().evaluate(metrics(1.5, 600, 900), metrics(3.0, 400, 1200), stale=True)
    assert signal.level == ChangeLevel.NORMAL
    assert signal.reason == "数据未刷新"


def test_two_bad_roi_windows_trigger_action():
    detector = ChangeDetector()
    first = detector.evaluate(metrics(2.2, 400, 880), metrics(3.0, 350, 1050), stale=False)
    second = detector.evaluate(metrics(1.9, 500, 950), metrics(2.2, 400, 880), stale=False)
    assert first.level in {ChangeLevel.WATCH, ChangeLevel.ACTION}
    assert second.level == ChangeLevel.ACTION