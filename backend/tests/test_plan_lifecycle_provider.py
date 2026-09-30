import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_delete_plan_verifies_plan_is_gone():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.DELETE_PLAN,
        target_id="plan-1",
        params={"reason": "长期亏损"},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert "plan-1" not in adapter.plans