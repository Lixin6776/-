from app.execution.cdp.plan_reader import parse_plan_detail_text

SAMPLE_TEXT = """
推直播间
抖音号：质润官方旗舰店
投放中
计划ID：1876023119718580
抖音号ID：32058940192
预算(元)：
每日9,999,999.00
综合营销ROI目标：
2.60
综合营销ROI
重要
1.87
净成交金额(元)
重要
113,586.29
整体成交订单数
747
综合成本(元)
重要
60,778.54
数据
素材
调控
"""


def test_parse_plan_detail_text_reads_new_overall_live_layout():
    snapshot = parse_plan_detail_text(SAMPLE_TEXT, "1876023119718580")

    assert snapshot.id == "1876023119718580"
    assert snapshot.name == "计划 1876023119718580"
    assert snapshot.status == "active"
    assert snapshot.budget == 9_999_999.0
    assert snapshot.roi_goal == 2.6
    assert snapshot.roi == 1.87
    assert snapshot.spend == 60_778.54
    assert snapshot.gmv == 113_586.29
    assert snapshot.orders == 747
