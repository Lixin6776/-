from app.services.llm.base import LLMResponse


def test_llm_status_never_returns_api_key(client, monkeypatch):
    import app.api.llm_connection as module

    monkeypatch.setattr(module.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(module.settings, "llm_model", "test-model")
    monkeypatch.setattr(module.settings, "llm_api_key", "secret-key")

    response = client.get("/api/llm-connection/status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["api_key_configured"] is True
    assert "secret-key" not in response.text


def test_save_llm_connection_uses_local_configurator(client, monkeypatch):
    import app.api.llm_connection as module

    captured = {}

    def fake_save(settings, *, base_url, model, api_key="", path=None):
        captured.update(
            {
                "base_url": base_url,
                "model": model,
                "api_key": api_key,
            }
        )
        settings.llm_base_url = base_url
        settings.llm_model = model
        settings.llm_api_key = api_key or settings.llm_api_key

    monkeypatch.setattr(module, "save_llm_config", fake_save)
    response = client.post(
        "/api/llm-connection/config",
        json={
            "base_url": "https://llm.example/v1 ",
            "model": " test-model ",
            "api_key": " secret-key ",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "base_url": "https://llm.example/v1",
        "model": "test-model",
        "api_key": "secret-key",
    }
    assert "secret-key" not in response.text


def test_test_llm_connection_uses_provider(client, monkeypatch):
    import app.api.llm_connection as module

    class FakeProvider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def complete(self, messages, tools):
            return LLMResponse(content="OK")

    monkeypatch.setattr(module.settings, "llm_api_key", "secret-key")
    monkeypatch.setattr(module.settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(module.settings, "llm_model", "test-model")
    monkeypatch.setattr(module, "OpenAICompatibleProvider", FakeProvider)

    response = client.post("/api/llm-connection/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True
