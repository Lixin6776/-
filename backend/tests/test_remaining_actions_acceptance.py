import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_create_copy_edit_delete_round_trip():
    adapter = FakePageAdapter({"seed": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)

    create = ActionEnvelope(
        action_name=ActionName.CREATE_PLAN,
        target_id="new",
        params={
            "source_product_id": "product-1",
            "name": "新计划",
            "budget": 500,
            "roi_goal": 2.5,
        },
    )
    create_result = await provider.execute(create)
    created_id = str(create_result.after["id"])
    assert create_result.after["name"] == "新计划"

    copy = ActionEnvelope(
        action_name=ActionName.COPY_PLAN,
        target_id=created_id,
        params={"name": "复制计划"},
    )
    copy_result = await provider.execute(copy)
    copied_id = str(copy_result.after["id"])
    assert copy_result.after["name"] == "复制计划"

    edit = ActionEnvelope(
        action_name=ActionName.EDIT_PLAN,
        target_id=copied_id,
        params={"fields": {"name": "编辑后的计划", "bid": 2.8}},
    )
    edit_result = await provider.execute(edit)
    assert (await provider.verify(edit, edit_result)).ok is True

    bid = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BID,
        target_id=copied_id,
        params={"bid": 3.1},
    )
    targeting = ActionEnvelope(
        action_name=ActionName.UPDATE_TARGETING,
        target_id=copied_id,
        params={"targeting": {"gender": "female"}},
    )
    schedule = ActionEnvelope(
        action_name=ActionName.UPDATE_SCHEDULE,
        target_id=copied_id,
        params={"schedule": {"days": ["mon", "tue"]}},
    )
    for action in (bid, targeting, schedule):
        result = await provider.execute(action)
        assert (await provider.verify(action, result)).ok is True

    adapter.plans[copied_id]["available_materials"] = ["material-1"]
    bind = ActionEnvelope(
        action_name=ActionName.BIND_EXISTING_MATERIAL,
        target_id=copied_id,
        params={"material_id": "material-1"},
    )
    bind_result = await provider.execute(bind)
    assert (await provider.verify(bind, bind_result)).ok is True

    unbind = ActionEnvelope(
        action_name=ActionName.UNBIND_EXISTING_MATERIAL,
        target_id=copied_id,
        params={"material_id": "material-1"},
    )
    unbind_result = await provider.execute(unbind)
    assert (await provider.verify(unbind, unbind_result)).ok is True

    delete = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id=copied_id,
        params={"reason": "验收清理"},
    )
    delete_result = await provider.execute(delete)
    assert (await provider.verify(delete, delete_result)).ok is True
    assert copied_id not in adapter.plans