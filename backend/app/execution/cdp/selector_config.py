import json
from pathlib import Path

from pydantic import BaseModel, ValidationError


class SelectorConfig(BaseModel):
    plan_rows: str
    plan_id: str
    plan_name: str
    plan_status: str
    plan_status_toggle: str
    budget_value: str
    budget_edit_button: str
    budget_input: str
    budget_save_button: str
    confirmation_dialog: str
    confirmation_submit: str

    @classmethod
    def load(cls, path: Path) -> "SelectorConfig":
        if not path.exists():
            raise ValueError(f"Missing selector calibration: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return cls.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            required = set(cls.model_fields)
            supplied = set(payload) if "payload" in locals() and isinstance(payload, dict) else set()
            missing = sorted(required - supplied)
            detail = ", ".join(missing) if missing else str(exc)
            raise ValueError(f"Invalid selector calibration: {detail}") from exc