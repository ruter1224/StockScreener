"""抓取進度儀表板（純標準庫）。

資料來源只有兩樣，都不影響抓取：
- `data/sync_state.db`（唯讀，每檔 commit 一次）
- `data/raw/` 下的 parquet 檔數與容量

啟動：uv run python monitor.py        → http://127.0.0.1:8765

⚠️ 唯讀 SQLite 連線：抓取端持續寫入，這邊只 SELECT。
用 `file:...?mode=ro` 開啟，抓取端中止時儀表板不會卡住或鎖住資料庫。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from fetch import (  # noqa: E402
    FINANCIAL_DATASETS,
    GLOBAL_DATASETS,
    MARKET_DATASETS,
    PER_STOCK_DATASETS,
)

DATA_DIR = Path("data")
STATE_DB = DATA_DIR / "sync_state.db"
PARQUET_ROOT = DATA_DIR / "raw"
UNIVERSE_JSON = PARQUET_ROOT / "universe.json"
LOG_DIR = Path("logs")

# 股票池大小讀 fetch.py 存的那份，不要自己重推（見 fetch.save_universe 說明）
_pool_cache: tuple[int, int] | None = None


def pool_sizes() -> tuple[int, int]:
    """回傳 (全部證券數, 有財報數)。讀不到回傳 (0, 0)。"""
    global _pool_cache
    if _pool_cache is not None:
        return _pool_cache
    try:
        d = json.loads(UNIVERSE_JSON.read_text(encoding="utf-8"))
        _pool_cache = (len(d["all_securities"]), len(d["with_financials"]))
    except (OSError, KeyError, ValueError):
        _pool_cache = (0, 0)
    return _pool_cache


def dataset_total(dataset: str) -> int | None:
    """該 dataset 的應抓檔案總數（分母）。"""
    if dataset in GLOBAL_DATASETS:
        return 1
    all_sec, with_fin = pool_sizes()
    if dataset in FINANCIAL_DATASETS:
        return with_fin or None
    if dataset in MARKET_DATASETS:
        return all_sec or None
    return None


def read_state() -> list[dict]:
    """唯讀抓取狀態。每個 dataset 一列，含各 status 計數與最近更新時間。"""
    if not STATE_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True, timeout=3)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT dataset, status, COUNT(*) AS n, MAX(updated_at) AS latest "
            "FROM sync_state GROUP BY dataset, status"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    merged: dict[str, dict] = {}
    for r in rows:
        ds = merged.setdefault(
            r["dataset"],
            {"dataset": r["dataset"], "ok": 0, "empty": 0, "error": 0,
             "skipped": 0, "latest": ""},
        )
        ds[r["status"]] = r["n"]
        if r["latest"] and r["latest"] > ds["latest"]:
            ds["latest"] = r["latest"]
    return list(merged.values())


def recent_error_sample(limit: int = 8) -> list[dict]:
    if not STATE_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True, timeout=3)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT dataset, stock_id, error_msg, updated_at FROM sync_state "
            "WHERE status = 'error' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [dict(r) for r in rows]


def log_tail(lines: int = 25) -> list[str]:
    """最新一份抓取 log 的尾端。抓取中看錯誤訊息最快。

    run_all.py 會寫 `run_all-*.log`（utf-8），優先取那份；
    沒有才退回 fetch-*.out.log（可能是 cp950）。
    """
    if not LOG_DIR.exists():
        return []
    for pattern, encoding in (
        ("run_all-*.log", "utf-8"),
        ("fetch-*.out.log", "utf-8"),
    ):
        logs = sorted(LOG_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
        if not logs:
            continue
        try:
            text = logs[-1].read_text(encoding=encoding, errors="replace")
        except OSError:
            continue
        return text.splitlines()[-lines:]
    return []


def parquet_stats() -> dict[str, int]:
    """各 dataset 的 parquet 檔數。用來對帳狀態有沒有說謊。"""
    out: dict[str, int] = {}
    if not PARQUET_ROOT.exists():
        return out
    for d in PARQUET_ROOT.iterdir():
        if d.is_dir():
            out[d.name] = sum(1 for _ in d.glob("*.parquet"))
    return out


def build_snapshot() -> dict:
    pcounts = parquet_stats()
    rows = read_state()
    by_ds = {r["dataset"]: r for r in rows}

    items = []
    for ds in GLOBAL_DATASETS + PER_STOCK_DATASETS:
        s = by_ds.get(ds, {"dataset": ds, "ok": 0, "empty": 0, "error": 0,
                           "skipped": 0, "latest": ""})
        total = dataset_total(ds)
        done = s["ok"] + s["empty"] + s["skipped"]
        pct = (done / total * 100) if total else None
        items.append(
            {
                "dataset": ds,
                "kind": "global" if ds in GLOBAL_DATASETS else (
                    "financial" if ds in FINANCIAL_DATASETS else "market"
                ),
                "done": done,
                "total": total,
                "ok": s["ok"],
                "empty": s["empty"],
                "error": s["error"],
                "pct": pct,
                "complete": bool(total and done >= total),
                "parquet": pcounts.get(ds, 0),
                "latest": s["latest"],
            }
        )

    # 正在跑哪一個：最近有更新的、還沒完成的 dataset
    active = None
    for it in items:
        if it["kind"] != "global" and not it["complete"] and it["latest"]:
            if active is None or it["latest"] > active["latest"]:
                active = it

    done_files = sum(i["parquet"] for i in items)
    total_files = sum((i["total"] or 0) for i in items)
    size_mb = 0.0
    if PARQUET_ROOT.exists():
        size_mb = sum(f.stat().st_size for f in PARQUET_ROOT.rglob("*.parquet")) / 1024 / 1024

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
        "active": active,
        "all_complete": bool(total_files) and all(i["complete"] for i in items),
        "total_done": sum(i["done"] for i in items),
        "total_target": total_files,
        "overall_pct": (done_files / total_files * 100) if total_files else 0.0,
        "parquet_files": done_files,
        "size_mb": round(size_mb, 1),
        "errors": recent_error_sample(),
        "log": log_tail(),
    }


HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Stock Screener 抓取進度</title>
<style>
  :root { color-scheme: dark; }
  body { background:#12151a; color:#e6e9ef; font-family:"Microsoft JhengHei",
         "Segoe UI", system-ui, sans-serif; margin:0; padding:24px 28px; }
  h1 { font-size:20px; margin:0 0 4px; font-weight:600; }
  .sub { color:#8b93a3; font-size:13px; margin-bottom:20px; }
  .overall { background:#1c2029; border:1px solid #2a2f3a; border-radius:10px;
             padding:18px 20px; margin-bottom:22px; }
  .overall .big { font-size:34px; font-weight:700; letter-spacing:-1px; }
  .overall .meta { color:#8b93a3; font-size:13px; margin-top:4px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:left; color:#8b93a3; font-weight:500; font-size:12px;
       padding:6px 8px; border-bottom:1px solid #2a2f3a; }
  td { padding:7px 8px; border-bottom:1px solid #1e232b; vertical-align:middle; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .bar { background:#262b35; height:8px; border-radius:4px; overflow:hidden; min-width:120px; }
  .bar > i { display:block; height:100%; background:#4c8dff; }
  .bar.done > i { background:#35c26a; }
  .tag { font-size:11px; padding:2px 7px; border-radius:4px; background:#262b35;
         color:#9aa3b2; margin-right:4px; }
  .tag.err { background:#4a1f24; color:#ff8a8a; }
  .tag.ok  { background:#17351f; color:#6fdc96; }
  .tag.act { background:#3a2f10; color:#ffce6a; }
  pre { background:#161a21; border:1px solid #2a2f3a; border-radius:8px;
        padding:12px 14px; font-size:12px; line-height:1.55; overflow-x:auto;
        color:#b9c1cf; max-height:340px; }
  h2 { font-size:14px; color:#8b93a3; font-weight:500; margin:26px 0 10px;
       text-transform:uppercase; letter-spacing:1px; }
  .flash { animation: none; }
</style>
</head>
<body>
<h1>Stock Screener — 抓取進度</h1>
<div class="sub">每 5 秒自動重新整理 ｜ 資料來源 data/sync_state.db（唯讀）</div>
<div id="root"></div>
<script>
const KIND = {global:"全域", financial:"財務", market:"行情"};

function bar(item) {
  const pct = item.pct === null ? 0 : item.pct;
  return '<div class="bar' + (item.complete ? ' done' : '') + '">' +
         '<i style="width:' + Math.min(100, pct).toFixed(1) + '%"></i></div>';
}

function render(d) {
  const pct = d.overall_pct.toFixed(1);
  let h = '<div class="overall">';
  h += '<div class="big">' + pct + '%</div>';
  h += '<div class="meta">' + d.total_done + ' / ' + d.total_target +
       ' 檔 ｜ parquet ' + d.parquet_files + ' 個檔案 ｜ ' + d.size_mb + ' MB ｜ 更新於 ' +
       d.generated_at + '</div>';
  if (d.all_complete) {
    h += '<div class="meta" style="color:#6fdc96;font-weight:600">' +
         '全部 dataset 完成，可以進行下一階段</div>';
  } else if (d.active) {
    h += '<div class="meta" style="color:#ffce6a">進行中：' + d.active.dataset +
         '（' + d.active.done + (d.active.total ? " / " + d.active.total : "") + '）</div>';
  }
  h += '</div>';

  h += '<table><tr><th>dataset</th><th>類別</th><th>進度</th>' +
       '<th style="text-align:right">完成</th><th style="text-align:right">ok</th>' +
       '<th style="text-align:right">empty</th><th style="text-align:right">error</th>' +
       '<th style="text-align:right">parquet</th><th>狀態</th></tr>';
  for (const it of d.items) {
    let tag = '<span class="tag">未開始</span>';
    if (it.complete) tag = '<span class="tag ok">完成</span>';
    else if (d.active && it.dataset === d.active.dataset) {
      tag = '<span class="tag act">進行中</span>';
    }
    else if (it.done > 0) tag = '<span class="tag">部分</span>';
    if (it.error > 0) tag += '<span class="tag err">錯誤 ' + it.error + '</span>';
    h += '<tr><td>' + it.dataset + '</td><td>' + KIND[it.kind] + '</td><td>' + bar(it) + '</td>' +
         '<td class="num">' + it.done + (it.total ? " / " + it.total : "") + '</td>' +
         '<td class="num">' + it.ok + '</td><td class="num">' + it.empty + '</td>' +
         '<td class="num">' + it.error + '</td><td class="num">' + it.parquet + '</td>' +
         '<td>' + tag + '</td></tr>';
  }
  h += '</table>';

  if (d.errors.length) {
    h += '<h2>最近錯誤</h2><table><tr><th>dataset</th><th>stock_id</th>' +
         '<th>訊息</th><th>時間</th></tr>';
    for (const e of d.errors) {
      h += '<tr><td>' + e.dataset + '</td><td>' + e.stock_id + '</td><td>' +
           (e.error_msg || "") + '</td><td>' + e.updated_at + '</td></tr>';
    }
    h += '</table>';
  }

  const logText = (d.log.length ? d.log.join('\\n') : '（尚無 log）')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;');
  h += '<h2>抓取 log（尾端）</h2><pre>' + logText + '</pre>';
  document.getElementById('root').innerHTML = h;
}

fetch('api/state').then(r => r.json()).then(render).catch(e => {
  document.getElementById('root').innerHTML = '<pre>讀取失敗：' + e + '</pre>';
});
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ScreenerMonitor/1.0"

    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/state":
            self._send(
                json.dumps(build_snapshot(), ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )
        elif path in ("/", "/index.html"):
            self._send(HTML.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # 不要把每次輪詢噴到 console


def main() -> None:
    ap = argparse.ArgumentParser(description="抓取進度儀表板")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="不要自動開瀏覽器")
    args = ap.parse_args()

    if not STATE_DB.exists():
        raise SystemExit(f"找不到 {STATE_DB}，請先跑過 fetch.py")

    pool_sizes()  # 預熱股票池
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"抓取進度儀表板：{url}（Ctrl+C 結束）", flush=True)

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n關閉儀表板")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
