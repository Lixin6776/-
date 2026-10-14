from datetime import UTC, datetime

import pytest

from app.execution.cdp.live_snapshot import (
    LiveBoardSnapshotReader,
    _room_name,
    parse_live_board_text,
)

SAMPLE_TEXT = """
直播大屏
正在直播
综合成本(元)

4,968.02

综合营销ROI

2.00

净成交金额(元)
乘方投放期间

9,948.00

整体成交订单数

66

GPM(元)

3,016.67

实时在线人数

128

直播间整体观看人数

1,683

直播间整体曝光次数
43,972

观看成交转化率

3.92

曝光观看率(次数)

5.37

直播间观看次数

2,369

商品点击次数

961
"""


def test_parse_live_board_text_extracts_core_metrics():
    captured_at = datetime(2026, 9, 30, 20, 15, tzinfo=UTC)
    snapshot = parse_live_board_text(SAMPLE_TEXT, captured_at=captured_at)

    assert snapshot.captured_at == captured_at
    assert snapshot.freshness == "fresh"
    assert snapshot.plan_status == "active"
    assert snapshot.spend == 4968.02
    assert snapshot.gmv == 9948.0
    assert snapshot.orders == 66
    assert snapshot.roi == 2.0
    assert snapshot.gpm == 3016.67
    assert snapshot.online_viewers == 128
    assert snapshot.views == 1683
    assert snapshot.exposure_count == 43972
    assert snapshot.view_count == 2369
    assert snapshot.product_clicks == 961
    assert snapshot.view_conversion_rate == 3.92
    assert snapshot.exposure_view_rate == 5.37


def test_parse_live_board_text_rejects_missing_required_metric():
    with pytest.raises(ValueError, match="综合成本"):
        parse_live_board_text("直播大屏\n正在直播")


def test_parse_live_board_text_extracts_live_started_at():
    captured_at = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    text = SAMPLE_TEXT + "\n开播时间：2026-09-30 06:00:51"
    snapshot = parse_live_board_text(text, captured_at=captured_at)

    assert snapshot.live_started_at is not None
    assert snapshot.live_started_at.isoformat() == "2026-09-30T06:00:51+08:00"


# --- 直播间名解析（大屏页面顺序会变，不能抓到工具条/指标标签）----------------

def test_room_name_from_header():
    text = "质润官方旗舰店\n直播中5小时39分钟\n开播时间：2026-10-09 06:00:17\n刷新数据\n综合成本(元)\n1,000"
    assert _room_name(text) == "质润官方旗舰店"


def test_room_name_ignores_toolbar_when_title_missing():
    """标题没渲染出来时（页面以工具条开头）宁可不给名字，也不能抓成「刷新数据」。"""
    text = (
        "刷新数据\n全屏\n公告\n查看详情\n我知道了\n1 / 2\n"
        "综合成本(元)\n38,055.52\n综合营销ROI\n1.86\n"
        "整体趋势\n素材表现\n综合成本\n净成交金额\n消耗\n"
        "成交渠道构成\n短视频及图文引流46.99%\n"
    )
    name = _room_name(text)
    assert name is None, f"不该把工具条/标签当成直播间名，实际拿到 {name!r}"


def test_room_name_ignores_metric_labels_and_symbols():
    for junk in ("综合营销ROI", "GPM(元)", "直播间整体观看人数", "%", "38,055.52", "1 / 2"):
        assert _room_name(f"{junk}\n综合成本(元)\n1") is None


# --- 选页面：不能抱着「上一场已结束」的大屏读 ---------------------------------

def test_score_prefers_live_over_ended():
    reader = LiveBoardSnapshotReader("http://127.0.0.1:9222")
    live_target = {"url": "https://qianchuan.jinritemai.com/board-next?live_room_id=222&aavid=1"}
    ended_target = {"url": "https://qianchuan.jinritemai.com/board-next?live_room_id=111&aavid=1"}
    live_text = "质润官方旗舰店\n直播中9小时18分钟\n开播时间：2026-10-10 06:00:03"
    ended_text = "质润官方旗舰店\n已结束19小时59分钟\n开播时间：2026-10-09 06:00:17"

    live_score, _ = reader._score(live_target, live_text)
    ended_score, _ = reader._score(ended_target, ended_text)

    assert live_score > ended_score
    # 已结束的页必须被重罚，否则同名直播间会一直读到冻结的上一场
    assert ended_score < 0


def test_room_id_of_url():
    reader = LiveBoardSnapshotReader("http://127.0.0.1:9222")
    url = "https://qianchuan.jinritemai.com/board-next?live_room_id=7694791024207481600&aavid=1"
    assert reader._room_id_of_url(url) == "7694791024207481600"
    assert reader._room_id_of_url(None) == ""
