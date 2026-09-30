import pytest

from app.services.action_registry import ActionEnvelope, ActionName
from app.services.api_endpoint_map import EndpointMap


def test_pause_plan_maps_to_status_update():
    request = EndpointMap.default().build(
        ActionEnvelope(action_name=ActionName.PAUSE_PLAN, target_id="plan-1", params={}),
        advertiser_id=123,
    )
    assert request.method == "POST"
    assert "/qianchuan/ad/status/update/" in request.path
    assert request.payload["ad_ids"] == ["plan-1"]


@pytest.mark.parametrize(
    ("name", "params", "required_key"),
    [
        (ActionName.CREATE_PLAN, {"source_product_id": "p1", "name": "n", "budget": 1, "roi_goal": 2}, "source_product_id"),
        (ActionName.COPY_PLAN, {"name": "copy"}, "source_ad_id"),
        (ActionName.DELETE_PLAN, {"reason": "loss"}, "ad_id"),
        (ActionName.EDIT_PLAN, {"fields": {"name": "new"}}, "ad_id"),
        (ActionName.UPDATE_PLAN_BID, {"bid": 2.5}, "ad_id"),
        (ActionName.UPDATE_TARGETING, {"targeting": {"gender": "female"}}, "ad_id"),
        (ActionName.UPDATE_SCHEDULE, {"schedule": {"days": ["mon"]}}, "ad_id"),
        (ActionName.BIND_EXISTING_MATERIAL, {"material_id": "m1"}, "ad_id"),
        (ActionName.UNBIND_EXISTING_MATERIAL, {"material_id": "m1"}, "ad_id"),
    ],
)
def test_remaining_actions_have_required_payload(name, params, required_key):
    request = EndpointMap.default().build(
        ActionEnvelope(action_name=name, target_id="plan-1", params=params),
        advertiser_id=123,
    )
    assert request.path
    assert request.payload["advertiser_id"] == 123
    assert required_key in request.payload