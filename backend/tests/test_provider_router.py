from app.services.action_registry import ActionName
from app.services.provider_router import ProviderRouter


class Provider:
    def __init__(self, name):
        self.name = name


def test_router_prefers_api_when_configured():
    router = ProviderRouter(
        api_provider=Provider("api"),
        cdp_provider=Provider("cdp"),
        api_configured=True,
        api_actions={ActionName.PAUSE_PLAN},
    )
    assert router.choose(ActionName.PAUSE_PLAN).name == "api"


def test_router_uses_cdp_when_api_missing_or_unsupported():
    router = ProviderRouter(
        api_provider=None,
        cdp_provider=Provider("cdp"),
        api_configured=False,
        api_actions={ActionName.PAUSE_PLAN},
    )
    assert router.choose(ActionName.PAUSE_PLAN).name == "cdp"
    assert router.choose(ActionName.DELETE_PLAN).name == "cdp"

def test_router_supports_all_registered_api_actions():
    from app.services.provider_router import API_SUPPORTED_ACTIONS

    assert ActionName.CREATE_PLAN in API_SUPPORTED_ACTIONS
    assert ActionName.DELETE_PLAN in API_SUPPORTED_ACTIONS
    assert ActionName.BIND_EXISTING_MATERIAL in API_SUPPORTED_ACTIONS
