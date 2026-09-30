from pathlib import Path

from app.services.monitor import MonitorService


def test_read_only_acceptance_flow(client, profile):
    profile = client.get("/api/profiles/active")
    assert profile.status_code == 200
    monitor_service = MonitorService(
        Path("tests/fixtures/plan_live_snapshot.json"),
        profile_version=profile.json()["version"],
    )
    event = monitor_service.tick()
    assert event.banner
    assert event.freshness in {"fresh", "stale"}


def test_local_runbook_and_launcher_are_safe():
    runbook = Path("../docs/runbooks/local-development.md")
    launcher = Path("../scripts/start-dev.ps1")
    assert runbook.is_file()
    assert launcher.is_file()
    text = runbook.read_text(encoding="utf-8") + launcher.read_text(encoding="utf-8")
    assert "127.0.0.1" in text
    assert "No write action" in text or "no write action" in text