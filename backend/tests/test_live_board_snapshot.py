from datetime import UTC, datetime

import pytest

from app.execution.cdp.live_snapshot import parse_live_board_text

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
