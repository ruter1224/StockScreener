"""Parquet 分區寫入。raw 層不可變：只追加，不 UPDATE，不轉型。

分區策略：dataset=xxx/stock_id=2330.parquet
一檔一檔存，中斷時已完成的檔案不會受影響。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class ParquetWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, dataset: str, stock_id: str) -> Path:
        d = self.root / dataset
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{stock_id}.parquet"

    def write(self, dataset: str, stock_id: str, rows: list[dict[str, Any]]) -> Path | None:
        """寫入一檔的資料。空資料不寫檔（回傳 None）。"""
        if not rows:
            return None
        p = self.path_for(dataset, stock_id)
        df = pd.DataFrame(rows)
        df.to_parquet(p, index=False, compression="snappy")
        return p

    def exists(self, dataset: str, stock_id: str) -> bool:
        return self.path_for(dataset, stock_id).exists()

    def read(self, dataset: str, stock_id: str) -> pd.DataFrame:
        p = self.path_for(dataset, stock_id)
        if not p.exists():
            return pd.DataFrame()
        return pd.read_parquet(p)

    def count_files(self, dataset: str) -> int:
        d = self.root / dataset
        if not d.exists():
            return 0
        return len(list(d.glob("*.parquet")))

    def total_size_mb(self, dataset: str | None = None) -> float:
        base = self.root / dataset if dataset else self.root
        if not base.exists():
            return 0.0
        return sum(f.stat().st_size for f in base.rglob("*.parquet")) / 1024 / 1024