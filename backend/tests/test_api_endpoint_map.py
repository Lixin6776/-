from app.services.action_registry import ActionEnvelope, ActionName
from app.services.api_endpoint_map import EndpointMap


def test_pause_plan_maps_to_status_update():
    request = EndpointMap.default().build(
        ActionEnvelope(
            action_name=ActionName.PAUSE_PLAN,
            target_id="plan-1",
            params={},
        ),
        advertiser_id=123,
    )
    assert request.method == "POST"
    assert "/qianchuan/ad/status/update/" in request.path
    assert request.payload["ad_ids"] == ["plan-1"]