"""續傳狀態：記錄每個 (dataset, stock_id) 的抓取結果，中斷後可繼續。

用 SQLite 而非 DuckDB：這是寫入密集的狀態表，需要單寫者保證。
DuckDB 留給查詢層（唯讀）。

⚠️ 每完成一個 stock_id 就 commit，這是 2765 檔能中斷續傳的關鍵。
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_state (
    dataset     TEXT NOT NULL,
    stock_id    TEXT NOT NULL,
    status      TEXT NOT NULL,          -- ok / empty / error / skipped
    rows        INTEGER DEFAULT 0,
    last_date   TEXT,
    error_msg   TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (dataset, stock_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_state(dataset, status);

CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    dataset     TEXT,
    total       INTEGER,
    done        INTEGER,
    note        TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SyncState:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def done_ids(self, dataset: str) -> set[str]:
        """已成功或已確認為空（無資料）的 stock_id。中斷後跳過這些。"""
        cur = self.conn.execute(
            "SELECT stock_id FROM sync_state "
            "WHERE dataset = ? AND status IN ('ok', 'empty', 'skipped')",
            (dataset,),
        )
        return {r[0] for r in cur.fetchall()}

    def ok_ids(self, dataset: str) -> set[str]:
        """只有 status='ok' 的 stock_id。

        與 done_ids 的差別在於 empty 項目**本來就沒有**資料檔，
        不能拿來跟「檔案遺失」比對（見 fetch.py 的續傳邏輯）。
        """
        cur = self.conn.execute(
            "SELECT stock_id FROM sync_state WHERE dataset = ? AND status = 'ok'",
            (dataset,),
        )
        return {r[0] for r in cur.fetchall()}

    def record(
        self,
        dataset: str,
        stock_id: str,
        status: str,
        rows: int = 0,
        last_date: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO sync_state "
            "(dataset, stock_id, status, rows, last_date, error_msg, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(dataset, stock_id) DO UPDATE SET "
            "status=excluded.status, rows=excluded.rows, "
            "last_date=excluded.last_date, error_msg=excluded.error_msg, "
            "updated_at=excluded.updated_at",
            (dataset, stock_id, status, rows, last_date, error_msg, _now()),
        )
        self.conn.commit()

    def last_date(self, dataset: str, stock_id: str) -> str | None:
        """該 stock_id 已有資料的最新日期，增量抓取時作為 start_date。"""
        cur = self.conn.execute(
            "SELECT last_date FROM sync_state "
            "WHERE dataset = ? AND stock_id = ? AND status = 'ok'",
            (dataset, stock_id),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def stats(self, dataset: str) -> dict[str, int]:
        cur = self.conn.execute(
            "SELECT status, COUNT(*) FROM sync_state WHERE dataset = ? GROUP BY status",
            (dataset,),
        )
        return {r[0]: r[1] for r in cur.fetchall()}

    def errors(self, dataset: str) -> list[tuple[str, str]]:
        """取出失敗項目，可單獨重試。"""
        cur = self.conn.execute(
            "SELECT stock_id, error_msg FROM sync_state "
            "WHERE dataset = ? AND status = 'error'",
            (dataset,),
        )
        return cur.fetchall()

    def start_run(self, dataset: str, total: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO run_log (started_at, dataset, total, done) VALUES (?, ?, ?, 0)",
            (_now(), dataset, total),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def finish_run(self, run_id: int, done: int, note: str | None = None) -> None:
        self.conn.execute(
            "UPDATE run_log SET ended_at = ?, done = ?, note = ? WHERE id = ?",
            (_now(), done, note, run_id),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()