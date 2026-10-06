"""抓取主程式。

用法：
    uv run python fetch.py                          # 抓所有 PER_STOCK_DATASETS
    uv run python fetch.py --dataset TaiwanStockPrice   # 只抓一個
    uv run python fetch.py --limit 20               # 只抓 20 檔（測試用）
    uv run python fetch.py --include-etf            # 連 ETF 一起抓
    uv run python fetch.py --retry-errors           # 只重試失敗項目
    uv run python fetch.py --status                 # 看進度

設計要點：
- 每檔完成即寫 Parquet + commit SQLite，中斷後 rerun 自動續傳
- 額度用盡（402）自動暫停一小時，不會死掉
- 支援兩台電腦同時跑不同 dataset（各自獨立的 sync_state）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.finmind_client import (  # noqa: E402
    CircuitBreaker,
    CircuitOpen,
    FetchError,
    FinMindClient,
    RateLimiter,
    Response,
    load_token,
)
from storage.sync_state import SyncState  # noqa: E402
from storage.writer import ParquetWriter  # noqa: E402

DATA_DIR = Path("data")
STATE_DB = DATA_DIR / "sync_state.db"
PARQUET_ROOT = DATA_DIR / "raw"
# fetch.py 實際使用的股票池。monitor.py 靠它算進度分母，
# 不用自己重推（本地 parquet 含已下市股，會算出比實際更大的分母）。
UNIVERSE_JSON = PARQUET_ROOT / "universe.json"

# 實測確認：12 個 dataset 逐檔查詢免費層全部可用（測試 27）
#
# 依「是否有財報」分成兩類：
# - FINANCIAL：只有個股有資料，ETF/權證回 rows=0 → 只抓有財報的
# - 行情類：ETF 也有（使用者要看 ETF 技術線圖）→ 抓全部證券
FINANCIAL_DATASETS = [
    "TaiwanStockFinancialStatements",
    "TaiwanStockBalanceSheet",
    "TaiwanStockCashFlowsStatement",
    "TaiwanStockPER",
    "TaiwanStockMonthRevenue",
]
MARKET_DATASETS = [
    "TaiwanStockPrice",
    "TaiwanStockDividendResult",
]
PER_STOCK_DATASETS = FINANCIAL_DATASETS + MARKET_DATASETS

# 全域型：1 次就抓完，不需要逐檔
GLOBAL_DATASETS = [
    "TaiwanStockInfo",
    "TaiwanStockTradingDate",
    "TaiwanStockParValueChange",
    "TaiwanStockSplitPrice",
    "TaiwanStockDelisting",
]

START_DATE = "2015-01-01"


class Fetcher(Protocol):
    """抓取函式只依賴 fetch() 介面，不綁死 FinMindClient 整個類別。

    測試要注入 fake（不送真實請求）時才需要這個寬度。
    """

    def fetch(
        self,
        dataset: str,
        data_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Response: ...


def log(msg: str) -> None:
    # Windows 主控台預設 cp950 無法輸出 emoji，中文可但符號不行。
    # 統一降級替換，避免 UnicodeEncodeError 中斷長時間抓取。
    safe = msg.replace("⏱", "[時間]").replace("🔴", "[停止]").replace("⚠", "[注意]")
    print(f"[{time.strftime('%H:%M:%S')}] {safe}", flush=True)


def latest_by_stock(rows: list[dict]) -> dict[str, dict]:
    """TaiwanStockInfo 是變更事件流，同一 stock_id 有多列，取 date 最新。"""
    latest: dict[str, dict] = {}
    for row in rows:
        sid = row.get("stock_id")
        if not sid:
            continue
        dt = str(row.get("date") or "")
        if sid not in latest or dt > str(latest[sid].get("date") or ""):
            latest[sid] = row
    return latest


def classify_universe(
    latest: dict[str, dict],
) -> tuple[list[str], list[str]]:
    """把 TaiwanStockInfo 去重後的結果分成 (全部證券, 財務篩選用股票)。

    ⚠️ **ETF 保留在全部證券中**（2026-10-06 使用者決定）。
    使用者可能要看 ETF 的技術線圖等資料，所以不能從主檔排除。
    但 ETF 沒有財報（FinancialStatements / BalanceSheet / PER /
    MonthRevenue 全回 rows=0），**財務指標計算時要排除**。

    排除依據：
    - v1 不啟用興櫃（emerging，官方無資料、無財報）
    - 非 4 碼數字的代號（特別股等，見 test 11.2）
    """
    by_type: dict[str, set[str]] = {}
    by_cat: dict[str, set[str]] = {}
    for sid, row in latest.items():
        by_type.setdefault(row.get("type", ""), set()).add(sid)
        by_cat.setdefault(row.get("industry_category", ""), set()).add(sid)

    twse_tpex = by_type.get("twse", set()) | by_type.get("tpex", set())

    def has_financials(sid: str, row: dict) -> bool:
        cat = str(row.get("industry_category", ""))
        if "ETF" in cat or "期貨" in cat or "權證" in cat:
            return False
        # 帶字母後綴的是 ETF／特別股（00411A、00679B 等）
        if not (sid.isdigit() and len(sid) == 4):
            return False
        return True

    with_fin = sorted(
        s
        for s in twse_tpex
        if s.isdigit() and len(s) == 4 and has_financials(s, latest[s])
    )
    return sorted(twse_tpex), with_fin


def build_universe(client: Fetcher, include_etf: bool) -> tuple[list[str], list[str]]:
    """從 TaiwanStockInfo 取股票池，並回報規模。

    篩選規則在 classify_universe，monitor.py 也複用同一份，
    避免兩邊的 ETF 判定各自漂移。
    """
    r = client.fetch("TaiwanStockInfo", start_date="2026-01-01")
    if not r.ok:
        raise SystemExit(f"無法取得股票池：{r.kind.value} / {r.msg}")

    latest = latest_by_stock(r.data)
    all_securities, with_fin = classify_universe(latest)

    by_type: dict[str, set[str]] = {}
    by_cat: dict[str, int] = {}
    for sid, row in latest.items():
        by_type.setdefault(row.get("type", ""), set()).add(sid)
        cat = row.get("industry_category", "")
        by_cat[cat] = by_cat.get(cat, 0) + 1
    cats = sorted(by_cat.items(), key=lambda x: -x[1])[:6]
    log(f"  產業別 top6：{cats}")
    log(f"股票池：twse={len(by_type.get('twse', set()))} "
        f"tpex={len(by_type.get('tpex', set()))} → "
        f"全部證券 {len(all_securities)} 檔（ETF 保留）｜ "
        f"有財報 {len(with_fin)} 檔")
    save_universe(all_securities, with_fin)
    return all_securities, with_fin


def save_universe(all_securities: list[str], with_fin: list[str]) -> None:
    """記錄實際使用的股票池，供 monitor.py 當進度分母。

    一定要用當次 API 回應推導的結果，不要用本地 parquet 重推：
    本地 parquet 是全歷史事件流，含已下市證券，會算出偏大的分母，
    導致進度條永遠到不了 100%。
    """
    UNIVERSE_JSON.write_text(
        json.dumps(
            {
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "all_securities": all_securities,
                "with_financials": with_fin,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def fetch_global(client: Fetcher, writer: ParquetWriter, state: SyncState) -> None:
    """全域型 dataset：一次抓完存成單一檔案。"""
    log("=== 抓取全域型 dataset ===")
    for ds in GLOBAL_DATASETS:
        # 續傳以 parquet 實際存在為準。`data/` 若被雲端同步，狀態可能跟檔案分離。
        if "ALL" in state.done_ids(ds) and writer.exists(ds, "ALL"):
            log(f"  {ds}: 已完成，略過")
            continue
        r = client.fetch(ds, start_date=START_DATE)
        if r.ok:
            writer.write(ds, "ALL", r.data)
            last = max((str(x.get("date", "")) for x in r.data), default=None)
            state.record(ds, "ALL", "ok", rows=r.rows, last_date=last)
            log(f"  {ds}: OK {r.rows} 筆")
        else:
            state.record(ds, "ALL", "error", error_msg=f"{r.kind.value}: {r.msg}")
            log(f"  {ds}: 失敗 {r.kind.value} — {r.msg[:70]}")


def fetch_per_stock(
    client: Fetcher,
    writer: ParquetWriter,
    state: SyncState,
    dataset: str,
    pool: list[str],
    limit: int | None,
    retry_errors: bool,
    max_seconds: int | None,
) -> None:
    """逐檔抓取。支援續傳、熔斷、時間上限。

    安全設計（依官方 https://finmind.github.io/BanIPPolicy/）：
    - 4xx 累積 3 次即熔斷停止，避免被列入黑名單
    - IP 被封鎖（403 ip banned）立即停止，不重試
    - 額度用盡（402）停止，等下個計費週期
    """
    done = state.done_ids(dataset)
    # 狀態說完成、但 parquet 不在 → 視為遺失重抓。
    # 原因：`data/` 被雲端同步時，sync_state.db 與 data/raw/ 會分離，
    # 只看狀態會靜默跳過（2026-10-06 實際發生過）。
    lost = {s for s in state.ok_ids(dataset) if not writer.exists(dataset, s)}
    log(f"=== {dataset} ===")

    if retry_errors:
        targets = [sid for sid, _ in state.errors(dataset)]
        log(f"  重試失敗項目 {len(targets)} 個")
    else:
        targets = [s for s in pool if s not in done or s in lost]
        skipped = len(pool) - len(targets)
        if skipped:
            log(f"  續傳：略過 {skipped} 檔已完成")
        if lost:
            log(f"  資料檔遺失重抓 {len(lost)} 檔")

    if limit is not None:
        targets = targets[:limit]

    if not targets:
        log("  無需抓取")
        return

    run_id = state.start_run(dataset, len(targets))
    stats = {"ok": 0, "empty": 0, "error": 0}
    t0 = time.time()

    for i, sid in enumerate(targets, 1):
        # 時間上限：到點就正常結束，資料已落盤，rerun 可續
        if max_seconds is not None and (time.time() - t0) > max_seconds:
            log(f"  ⏱ 達到時間上限 {max_seconds}s，已完成 {i - 1}/{len(targets)}")
            state.finish_run(run_id, i - 1, f"time limit {max_seconds}s")
            return

        # 增量：已有資料則從最新日期之後抓。
        # 檔案不在 → last_date 不可信，從頭抓，否則會缺前段資料。
        last = state.last_date(dataset, sid) if writer.exists(dataset, sid) else None
        start = last if last else START_DATE

        try:
            r = client.fetch(dataset, data_id=sid, start_date=start)
        except CircuitOpen as e:
            # 4xx 熔斷：立即停止，不繼續累積 4xx
            log(f"\n  🔴 熔斷停止：{e}")
            log("  已完成的資料都已落盤，修正問題後 rerun 會自動續傳。")
            state.finish_run(run_id, i - 1, "circuit breaker: 4xx")
            return

        if r.kind is FetchError.IP_BANNED:
            # 官方：IP 被封鎖 30 分鐘自動解除，不要繼續打
            log("\n  🔴 IP 被封鎖（403 ip banned）")
            log("  官方政策：30 分鐘自動解除。停止抓取，請 30 分後再執行。")
            state.finish_run(run_id, i - 1, "ip banned")
            return

        if r.ok:
            last_date = max((str(x.get("date", "")) for x in r.data), default=last)
            if r.rows == 0:
                state.record(dataset, sid, "empty", rows=0, last_date=last)
                stats["empty"] += 1
            else:
                writer.write(dataset, sid, r.data)
                state.record(dataset, sid, "ok", rows=r.rows, last_date=last_date)
                stats["ok"] += 1
        elif r.kind is FetchError.QUOTA_EXCEEDED:
            log(f"\n  ⚠ 額度用盡（{i}/{len(targets)}）")
            log("  官方：402 表示額度用盡，等下個計費週期。停止抓取。")
            state.finish_run(run_id, i - 1, "quota exhausted (402)")
            return
        else:
            state.record(dataset, sid, "error", error_msg=f"{r.kind.value}: {r.msg}")

        if i % 25 == 0 or i == len(targets):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 0
            eta = (len(targets) - i) / rate / 3600 if rate else 0
            log(f"  {i}/{len(targets)}  ok={stats['ok']} empty={stats['empty']} "
                f"err={stats['error']}  {rate:.2f} 檔/秒  ETA {eta:.1f}h")

    state.finish_run(run_id, len(targets))
    log(f"完成：ok={stats['ok']} empty={stats['empty']} error={stats['error']}")
    if stats["error"]:
        log(f"錯誤樣例：{state.errors(dataset)[:3]}")


def show_status(state: SyncState) -> None:
    log("=== 抓取進度 ===")
    all_ds = PER_STOCK_DATASETS + GLOBAL_DATASETS
    for ds in all_ds:
        s = state.stats(ds)
        if not s:
            continue
        total = sum(s.values())
        ok_n = s.get("ok", 0)
        pct = ok_n / total * 100 if total else 0
        log(f"  {ds:40s} {ok_n:5d}/{total:<5d} ({pct:5.1f}%)  {s}")
    log("")
    log(f"Parquet 檔案數：{sum(ParquetWriter(PARQUET_ROOT).count_files(d) for d in all_ds)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="FinMind 資料抓取")
    ap.add_argument("--dataset", help="只抓指定 dataset")
    ap.add_argument("--limit", type=int, help="只抓前 N 檔（測試用）")
    ap.add_argument("--include-etf", action="store_true", help="連 ETF/權證一起抓")
    ap.add_argument("--retry-errors", action="store_true", help="只重試失敗項目")
    ap.add_argument("--status", action="store_true", help="顯示進度後結束")
    ap.add_argument("--global-only", action="store_true", help="只抓全域型 dataset")
    ap.add_argument(
        "--max-seconds",
        type=int,
        help="執行時間上限（秒）。到點正常結束，rerun 可續傳",
    )
    ap.add_argument(
        "--per-hour",
        type=int,
        default=540,
        help="每小時請求數上限（預設 540，額度 600 留緩衝）",
    )
    args = ap.parse_args()

    token = load_token()
    limiter = RateLimiter(per_hour=args.per_hour)
    client = FinMindClient(token=token, limiter=limiter, breaker=CircuitBreaker())
    writer = ParquetWriter(PARQUET_ROOT)
    state = SyncState(STATE_DB)

    if args.status:
        show_status(state)
        return

    log(f"速率：{args.per_hour} 次/小時 ｜ token {'有' if token else '無（僅查額度需用）'}")
    log("安全：4xx 連續 3 次熔斷 ｜ 403 ip banned 立即停 ｜ 402 額度用盡立即停")
    if args.max_seconds:
        log(f"時間上限：{args.max_seconds} 秒")

    if not args.global_only:
        all_securities, with_financials = build_universe(client, args.include_etf)
        datasets = [args.dataset] if args.dataset else PER_STOCK_DATASETS
        for ds in datasets:
            if ds in GLOBAL_DATASETS:
                continue
            # 財務類 dataset 只需要有財報的股票；行情類要全部證券
            pool = (
                with_financials
                if ds in FINANCIAL_DATASETS
                else all_securities
            )
            fetch_per_stock(
                client, writer, state, ds, pool,
                args.limit, args.retry_errors, args.max_seconds,
            )
    else:
        fetch_global(client, writer, state)

    show_status(state)
    state.close()


if __name__ == "__main__":
    main()