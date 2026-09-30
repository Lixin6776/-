from app.services.action_registry import ActionName, ActionRegistry


def test_registry_contains_all_remaining_actions():
    registry = ActionRegistry.default()
    expected = {
        ActionName.CREATE_PLAN,
        ActionName.COPY_PLAN,
        ActionName.DELETE_PLAN,
        ActionName.EDIT_PLAN,
        ActionName.UPDATE_PLAN_BID,
        ActionName.UPDATE_TARGETING,
        ActionName.UPDATE_SCHEDULE,
        ActionName.BIND_EXISTING_MATERIAL,
        ActionName.UNBIND_EXISTING_MATERIAL,
    }
    assert {registry.get(name).name for name in expected} == expected