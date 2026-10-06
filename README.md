# 抓取程式使用說明

## 快速開始

```bash
uv sync                      # 安裝依賴（首次執行）
uv run python fetch.py --status          # 看目前進度
```

## 常用指令

```bash
# 只抓一個 dataset（續傳，rerun 會跳過已完成的）
uv run python fetch.py --dataset TaiwanStockFinancialStatements

# 測試：只抓 5 檔
uv run python fetch.py --dataset TaiwanStockFinancialStatements --limit 5

# 限制執行時間（到點正常結束，rerun 續傳）
uv run python fetch.py --dataset TaiwanStockBalanceSheet --max-seconds 3600

# 只重試失敗項目
uv run python fetch.py --retry-errors

# 只抓全域型 dataset（1 次就完，約 5 個 request）
uv run python fetch.py --global-only
```

## 兩台電腦分工

兩台電腦抓**不同的 dataset**，可以同時跑（各用各的額度是錯的，額度是帳號層級的，
所以**不要同時跑，否則合計會超過 600/小時**）。

建議順序：
1. 這台（測試）：`--limit 5` 驗證流程
2. 家裡那台（實跑）：先 `--global-only`（5 秒完成），再逐個 dataset 抓

## 額度與安全

| 項目 | 值 |
|---|---|
| 免費額度 | 600 次/小時（`/v2/user_info` 實測確認）|
| 程式預設速率 | 540 次/小時（留 60 次緩衝）|
| token | **非必需**，多數 dataset 免 token 即可取用 |

程式內建的安全機制（依官方 <https://finmind.github.io/BanIPPolicy/>）：

| 情況 | 行為 |
|---|---|
| 連續 3 次 4xx | **熔斷停止**，不重試不繼續 |
| `403 ip banned` | 立即停止，等 30 分鐘（官方自動解除）|
| `402` 額度用盡 | 立即停止，等下個計費週期 |
| 5xx / 網路錯誤 | exponential backoff，最多重試 3 次 |

⚠️ **不要移除 4xx 熔斷。** 官方明載累積 4xx 會觸發 IP 封鎖 30 分鐘。

## 檔案結構

```
data/
├── sync_state.db          SQLite 續傳狀態（不要進 git）
└── raw/
    └── <dataset>/
        └── <stock_id>.parquet    每檔一個檔案
```

raw 層**不可變**：只追加、不修改。所有資料修正都在後續 transform 層做。

## 預計耗時

| dataset | 檔數 | requests | 540/小時 |
|---|---|---|---|
| FinancialStatements | 2037 | 2037 | 3.8 h |
| BalanceSheet | 2037 | 2037 | 3.8 h |
| Price | 2507 | 2507 | 4.6 h |
| CashFlowsStatement | 2037 | 2037 | 3.8 h |
| PER | 2037 | 2037 | 3.8 h |
| MonthRevenue | 2037 | 2037 | 3.8 h |
| DividendResult | 2507 | 2507 | 4.6 h |
| 全域型（5 個） | — | 5 | 秒 |

**單一 dataset 約 4 小時，建議分天抓。** 全抓完約 28 小時。

## ETF 處理

- **ETF 保留在資料庫中**（使用者要看 ETF 技術線圖）
- 但財務類 dataset（FinancialStatements／BalanceSheet／PER／MonthRevenue／
  CashFlowsStatement）**只抓個股**，因為 ETF 沒有財報會回空
- 行情類（Price／DividendResult）**抓全部證券**

程式會自動分配股票池，不需要手動指定。

## 疑難排解

| 現象 | 處理 |
|---|---|
| `CircuitOpen` 熔斷 | 連續 3 次 4xx。檢查參數或方案權限，修正後 `--retry-errors` |
| 大量 `empty` | 正常（ETF／新上市／已下市），不是錯誤 |
| `UnicodeEncodeError` | 已修（log 會過濾 emoji）|
| 抓取很慢 | 檢查 `--per-hour` 設定；預設 540 為安全值 |

## 驗證指令

```bash
uv run python -m unittest discover tests -v   # 35 個測試
uv run ruff check src fetch.py tests           # lint
```