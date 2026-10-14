# -*- coding: utf-8 -*-
"""盯盘日志存储（SQLite）。

原来用 JSON：每 5 分钟把整个文件读进来、改完再整个写回去。跑到 5MB 之后
每次都读+写 5MB，基线还要再解析 400 条，越来越慢。

换成 SQLite：追加是插入一条，读取按时间倒序取 N 条。老 JSON 会在首次使用时
自动导入一次（原文件保留，当备份）。
"""

import json
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[3] / ".local" / "live_watch_logs.sqlite3"
)
LEGACY_JSON_PATH = Path(__file__).resolve().parents[3] / ".local" / "live_watch_logs.json"
KEEP_ROWS = 1500


class SqliteWatchLogStore:
    """和原来的 LiveWatchLogStore 保持一样的对外接口。"""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        legacy_json_path: Path = LEGACY_JSON_PATH,
        keep: int = KEEP_ROWS,
    ) -> None:
        self.path = Path(db_path)
        self.legacy_json_path = Path(legacy_json_path)
        self.keep = keep
        self._init_db()
        self._import_legacy_once()

    # --- 对外接口 ---------------------------------------------------------
    def list_logs(self, limit: int = 50) -> list[dict]:
        """按时间倒序（最新的在前）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM watch_reports ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._decode(row[0]) for row in rows]

    def latest(self) -> dict | None:
        items = self.list_logs(limit=1)
        return items[0] if items else None

    def append(self, report: dict) -> dict:
        payload = json.dumps(report, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO watch_reports "
                "(id, created_at, room_name, live_room_id, live_started_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(report.get("id") or ""),
                    str(report.get("created_at") or ""),
                    str(report.get("room_name") or ""),
                    str(report.get("live_room_id") or ""),
                    str(report.get("live_started_at") or ""),
                    payload,
                ),
            )
            conn.execute(
                "DELETE FROM watch_reports WHERE id NOT IN "
                "(SELECT id FROM watch_reports ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                (self.keep,),
            )
            conn.commit()
        return report

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM watch_reports").fetchone()[0])

    # --- 内部 -------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS watch_reports (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    room_name TEXT,
                    live_room_id TEXT,
                    live_started_at TEXT,
                    payload TEXT NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_reports_created "
                "ON watch_reports(created_at DESC)"
            )
            conn.commit()

    def _import_legacy_once(self) -> None:
        """首次运行：把老的 JSON 导进来（文件保留，不删）。"""
        if self.count() > 0:
            return
        if not self.legacy_json_path.exists():
            return
        try:
            items = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(items, list) or not items:
            return
        for report in items[-self.keep :]:
            if isinstance(report, dict):
                try:
                    self.append(report)
                except sqlite3.Error:
                    continue

    @staticmethod
    def _decode(payload: str) -> dict:
        try:
            value = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
