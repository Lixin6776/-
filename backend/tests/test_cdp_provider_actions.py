import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_pause_plan_verifies_new_status():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.PAUSE_PLAN,
        target_id="plan-1",
        params={},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert adapter.plans["plan-1"]["status"] == "paused"