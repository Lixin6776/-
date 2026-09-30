from dataclasses import dataclass

from app.services.action_registry import ActionName


@dataclass(frozen=True)
class ProviderSelection:
    name: str
    provider: object


class ProviderRouter:
    def __init__(
        self,
        api_provider,
        cdp_provider,
        api_configured: bool,
        api_actions: set[ActionName],
    ) -> None:
        self.api_provider = api_provider
        self.cdp_provider = cdp_provider
        self.api_configured = api_configured
        self.api_actions = api_actions

    def choose(self, action_name: ActionName | str) -> ProviderSelection:
        action = ActionName(action_name)
        if self.api_configured and self.api_provider is not None and action in self.api_actions:
            return ProviderSelection(name="api", provider=self.api_provider)
        if self.cdp_provider is None:
            raise RuntimeError("No execution provider is available")
        return ProviderSelection(name="cdp", provider=self.cdp_provider)