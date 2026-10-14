"""人货场变更记录。

用户框架：如果直播间人货场没有变动，盯盘只看消耗变量；
一旦人货场变了（画面/主播/话术/货品/机制），就必须在复盘里单独分析影响。
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

SITE_CHANGE_PATH = Path(__file__).resolve().parents[3] / ".local" / "site_changes.json"

CHANGE_TYPES = ("画面", "主播", "话术", "货品", "机制", "场景", "其他")


class SiteChangeStore:
    def __init__(self, path: Path = SITE_CHANGE_PATH) -> None:
        self.path = path

    def list(self, day: str | None = None) -> list[dict]:
        items = self._read()
        if day:
            items = [i for i in items if str(i.get("changed_at", "")).startswith(day)]
        return sorted(items, key=lambda i: i.get("changed_at") or "", reverse=True)

    def add(self, change_type: str, note: str, changed_at: str | None = None) -> dict:
        item = {
            "id": str(uuid.uuid4()),
            "type": change_type,
            "note": note,
            "changed_at": changed_at or datetime.now(UTC).isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
        }
        items = self._read()
        items.append(item)
        self._write(items)
        return item

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
