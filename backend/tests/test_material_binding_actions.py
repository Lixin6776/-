import pytest

from app.execution.cdp.provider import CdpExecutionProvider
from app.execution.fake_page_adapter import FakePageAdapter
from app.services.action_registry import ActionEnvelope, ActionName


@pytest.mark.asyncio
async def test_bind_existing_material_verifies_association():
    adapter = FakePageAdapter(
        {
            "plan-1": {
                "status": "active",
                "budget": 1000,
                "materials": [],
                "available_materials": ["material-1"],
            }
        }
    )
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.BIND_EXISTING_MATERIAL,
        target_id="plan-1",
        params={"material_id": "material-1"},
    )
    result = await provider.execute(action)
    verification = await provider.verify(action, result)
    assert verification.ok is True
    assert "material-1" in adapter.plans["plan-1"]["materials"]


@pytest.mark.asyncio
async def test_preflight_rejects_unavailable_material():
    adapter = FakePageAdapter(
        {
            "plan-1": {
                "status": "active",
                "budget": 1000,
                "materials": [],
                "available_materials": [],
            }
        }
    )
    provider = CdpExecutionProvider(adapter)
    action = ActionEnvelope(
        action_name=ActionName.BIND_EXISTING_MATERIAL,
        target_id="plan-1",
        params={"material_id": "missing-material"},
    )
    result = await provider.preflight(action)
    assert result.ok is False