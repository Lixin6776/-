import pytest

from app.services.action_registry import ActionName, ActionRegistry


def test_registry_contains_phase_two_actions():
    registry = ActionRegistry.default()
    assert registry.get(ActionName.PAUSE_PLAN).name == ActionName.PAUSE_PLAN
    assert registry.get(ActionName.ENABLE_PLAN).name == ActionName.ENABLE_PLAN
    assert registry.get(ActionName.UPDATE_PLAN_BUDGET).name == ActionName.UPDATE_PLAN_BUDGET


def test_registry_rejects_unknown_action():
    with pytest.raises(KeyError):
        ActionRegistry.default().get("delete_everything")