# -*- coding: utf-8 -*-
"""盯盘日志存储（SQLite）：接口要和老的 JSON 版一致，且能导入老数据。"""

import json

from app.services.watch_log_store import SqliteWatchLogStore


def _report(i: int, day: str = "2026-10-10T08:00:00+00:00") -> dict:
    return {"id": f"r{i}", "created_at": f"2026-10-10T08:{i:02d}:00+00:00", "room_name": "质润官方旗舰店", "spend": i}


def test_append_and_list_newest_first(tmp_path):
    store = SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json")
    store.append(_report(1))
    store.append(_report(3))
    store.append(_report(2))

    items = store.list_logs(limit=10)
    assert [i["id"] for i in items] == ["r3", "r2", "r1"]     # 时间倒序
    assert store.latest()["id"] == "r3"
    assert store.count() == 3


def test_append_same_id_replaces(tmp_path):
    store = SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json")
    store.append({"id": "same", "created_at": "2026-10-10T08:00:00+00:00", "spend": 1})
    store.append({"id": "same", "created_at": "2026-10-10T08:00:00+00:00", "spend": 2})
    assert store.count() == 1
    assert store.latest()["spend"] == 2


def test_keeps_only_latest_rows(tmp_path):
    store = SqliteWatchLogStore(tmp_path / "w.sqlite3", tmp_path / "none.json", keep=5)
    for i in range(12):
        store.append(_report(i))
    assert store.count() == 5
    assert store.latest()["id"] == "r11"       # 保留最新的


def test_imports_legacy_json_once(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps([_report(1), _report(2)], ensure_ascii=False), encoding="utf-8"
    )
    store = SqliteWatchLogStore(tmp_path / "w.sqlite3", legacy, keep=100)
    assert store.count() == 2
    # 再建一个（同库）不会重复导入
    again = SqliteWatchLogStore(tmp_path / "w.sqlite3", legacy, keep=100)
    assert again.count() == 2
    # 老文件保留，当备份
    assert legacy.exists()


def test_survives_broken_payload(tmp_path):
    import sqlite3

    path = tmp_path / "w.sqlite3"
    store = SqliteWatchLogStore(path, tmp_path / "none.json")
    store.append(_report(1))
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO watch_reports (id, created_at, payload) VALUES ('bad','2026-10-10T09:00:00+00:00','{not json')")
        conn.commit()
    items = store.list_logs(limit=5)
    assert items[0] == {}          # 坏数据不炸，返回空 dict
    assert items[1]["id"] == "r1"
