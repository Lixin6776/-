import os
from pathlib import Path

import pytest

from app.execution.cdp.selector_config import SelectorConfig


@pytest.mark.live
def test_live_selector_config_is_valid_when_enabled():
    if os.getenv("QCA_RUN_LIVE_TESTS") != "1":
        pytest.skip("live Qianchuan tests disabled")
    config = SelectorConfig.load(Path(".local/selectors/qianchuan.json"))
    assert config.plan_status_toggle
    assert config.budget_save_button