import json
from pathlib import Path

from app.config import Settings

CONFIG_PATH = Path(__file__).resolve().parents[3] / ".local" / "llm_config.json"


def load_llm_config(settings: Settings, path: Path = CONFIG_PATH) -> None:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    for key in ("base_url", "model", "api_key"):
        value = payload.get(key)
        if isinstance(value, str):
            target = {
                "base_url": "llm_base_url",
                "model": "llm_model",
                "api_key": "llm_api_key",
            }[key]
            setattr(settings, target, value)


def save_llm_config(
    settings: Settings,
    *,
    base_url: str,
    model: str,
    api_key: str = "",
    path: Path = CONFIG_PATH,
) -> None:
    stored_key = api_key or settings.llm_api_key
    settings.llm_base_url = base_url
    settings.llm_model = model
    settings.llm_api_key = stored_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "base_url": settings.llm_base_url,
                "model": settings.llm_model,
                "api_key": stored_key,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
