import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_update_bid_verifies_new_value():
    adapter = FakePageAdapter(
        {"plan-1": {"status": "active", "budget": 1000, "bid": 2.5}}
    )
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BID,
        target_id="plan-1",
        params={"bid": 2.8},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert adapter.plans["plan-1"]["bid"] == 2.8


@pytest.mark.asyncio
async def test_update_targeting_and_schedule_verify_values():
    adapter = FakePageAdapter(
        {
            "plan-1": {
                "status": "active",
                "budget": 1000,
                "targeting": {},
                "schedule": {},
            }
        }
    )
    provider = CdpExecutionProvider(adapter)
    targeting = ActionEnvelope(
        action_name=ActionName.UPDATE_TARGETING,
        target_id="plan-1",
        params={"targeting": {"gender": "female"}},
    )
    schedule = ActionEnvelope(
        action_name=ActionName.UPDATE_SCHEDULE,
        target_id="plan-1",
        params={"schedule": {"days": ["mon", "tue"]}},
    )
    targeting_result = await provider.execute(targeting)
    schedule_result = await provider.execute(schedule)
    assert (await provider.verify(targeting, targeting_result)).ok is True
    assert (await provider.verify(schedule, schedule_result)).ok is True


@pytest.mark.asyncio
async def test_provider_preflight_rejects_invalid_bid():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.UPDATE_PLAN_BID,
        target_id="plan-1",
        params={"bid": 0},
    )
    result = await provider.preflight(action)
    assert result.ok is False