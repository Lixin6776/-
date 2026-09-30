import pytest

from app.execution.cdp.selector_config import SelectorConfig


def test_missing_selector_config_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="selector calibration"):
        SelectorConfig.load(tmp_path / "missing.json")


def test_selector_config_requires_all_write_targets(tmp_path):
    path = tmp_path / "qianchuan.json"
    path.write_text('{"plan_rows": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="plan_status_toggle"):
        SelectorConfig.load(path)