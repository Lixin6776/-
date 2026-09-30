import pytest

from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_copy_plan_creates_new_plan():
    adapter = FakePageAdapter({"plan-1": {"status": "active", "budget": 1000}})
    result = await adapter.copy_plan(
        ActionEnvelope(
            action_name=ActionName.COPY_PLAN,
            target_id="plan-1",
            params={"name": "计划 B"},
        )
    )
    assert result.ok is True
    assert "计划 B" in result.after["name"]