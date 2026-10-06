# handoff.md — StockScreener

## ⏯️ 目前做到哪

**抓取程式已完成並測試通過，資料尚未全量抓取。**

- 程式碼：`fetch.py` ＋ `src/core/` ＋ `src/storage/`（**7 個檔案，35 個單元測試全過**）
- 規格書：`docs/superpowers/specs/2026-10-06-stock-screener-spec.md`（14 節，現行實作依據）
- 詞彙表：`CONTEXT.md`
- 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`
- **資料來源實測**：`docs/review/data-source-verification.md`（26 項測試）
- **抓取說明**：`README.md`（**晚上要看這份**）

已確認的決策（細節與依據在 decision-log）：

| 項目 | 決策 |
|---|---|
| 定位 | **研究輔助系統**（非全自動篩選器）|
| 資料來源 | FinMind REST API ＋ TWSE/TPEx 官方 open data |
| 技術棧 | Python 3.12 + DuckDB + Streamlit，依賴用 `uv` |
| 財務報表 | **已轉單季值**，TTM = 最近 4 季相加，不需相減 |
| ROE 篩選 | **講義的多年平均**（推翻原 D9 的 TTM），TTM 另留參考顯示 |
| 目標 PER | **只由 Tier 決定**，CAGR 不當獨立上限 |
| 風險折扣 | 講義第 5 維 20 分，**階梯跳級**（14 分差距 → PER 差近 10 倍）|
| 維度 2 | 手動輸入產業 CAGR ＋ 系統換算建議分數 |
| 維度 4 | 維持人工評分，杜邦僅作參考面板 |
| 估值 | 安全邊際（5 年）與追價安全圈（2 年）**兩套並存** |
| 安全圈 EPS | **全手動輸入**，不做自動預測 |
| ETF | **保留在資料庫**（使用者要看技術線圖），但財務類 dataset 不抓 |
| 否決過濾 | 兩個機制 v1 不做，只記錄 |
| align_score | **無資料來源，v1 不實作** |

## 🚦 目前狀態

- 可運行：**抓取器可運行**；財務指標計算、介面尚未開始
- 資料：**尚未全量抓取**（本機測試過 62 檔，之後已清空）
- Git：`master` = `origin/master`（已同步）
- Obsidian：`OpenCode專區/StockScreener/2026-10-06.md`
- **資料面驗證完成**：26 項測試，額度與可用性全部有實測依據

## ▶️ 晚上在另一台電腦怎麼做

### ⚠️ 兩台電腦不能同時抓

額度是**帳號層級**的 600 次/小時，兩台合計會超標。
建議：**這台只做 `--limit` 小量測試，家裡那台抓全量。**

### 步驟

```bash
# 1. 拉程式碼
git pull

# 2. 建環境（首次）
uv sync

# 3. 先抓全域型（5 個 request，幾秒完成，建議先做）
uv run python fetch.py --global-only

# 4. 抓主要 dataset（單一約 4 小時，中斷可續傳）
uv run python fetch.py --dataset TaiwanStockFinancialStatements

# 5. 看進度
uv run python fetch.py --status
```

**中斷了就再跑同一指令**，會自動跳過已完成的檔案續傳。

想限時（例如掛機一小時就停）：
```bash
uv run python fetch.py --dataset TaiwanStockBalanceSheet --max-seconds 3600
```

### 預計耗時（額度 540/小時）

| dataset | 檔數 | 耗時 |
|---|---|---|
| FinancialStatements | 2037 | 3.8 h |
| BalanceSheet | 2037 | 3.8 h |
| Price | 2507 | 4.6 h |
| CashFlowsStatement | 2037 | 3.8 h |
| PER | 2037 | 3.8 h |
| MonthRevenue | 2037 | 3.8 h |
| DividendResult | 2507 | 4.6 h |
| 全域型（5 個） | — | 秒 |

**單一 dataset 約 4 小時，建議分天抓。全抓完約 28 小時。**

### 安全機制（已內建，不要移除）

依官方 <https://finmind.github.io/BanIPPolicy/>：
- **4xx 連續 3 次熔斷停止**（累積 4xx 會被封鎖 IP 30 分鐘）
- `403 ip banned` 立即停止
- `402` 額度用盡立即停止
- 5xx／網路錯誤才重試（最多 3 次）

## ✅ 已完成（10-06）

1. 資料來源 26 項實測（額度、可用性、靜默錯誤陷阱全部有依據）
2. grill 設計 8 題（產品契約、五維評分不可砍、略過篩選入口、ROE 多年平均、PE 只提示、維度 2／4 定位、安全圈 EPS 全手動、長期價值 CAGR 獨立）
3. 規格書（14 節）＋ CONTEXT.md 詞彙表
4. 五項未解問題實測（**3 項已解決**：PER 21 年、額度確認、創新板只標註）
5. 官方文件查證（**發現文件本身有 5 個錯誤**，修正 4 處錯誤歸因）
6. **抓取程式**（client／sync_state／writer ＋ 35 個測試）

## ⚠️ 注意事項

### Token 不是必需的

實測確認**免 token 即可取用多數 dataset**。token 唯一用途是查額度。
`.env` 已建立但非抓取必要。

### ETF 保留但不抓財務

- stock master 保留全部 2507 檔證券
- 財務類 dataset 只抓個股 2037 檔（ETF 沒財報會回空浪費額度）
- 行情類（Price／DividendResult）抓全部

### 還原股價需要三個來源

先前只用 `TaiwanStockDividendResult`（除權息），**漏了面額變更**。
還原因子需合併 `DividendResult` + `ParValueChange` + `SplitPrice`。
（`CapitalReductionReferencePrice` 實測回空，不可用）

### 三種錯誤性質要分清

| 回應 | 性質 |
|---|---|
| `422` enum 錯誤 | 名稱不存在（含大小寫）|
| `400 "Your level is free"` | 需登入或付費 |
| `400 "parameter data_id don't provide"` | 用法錯誤 |
| `200` + `rows: 0` | 期間無資料（**不是錯誤**）|

### 靜默錯誤陷阱（寫錯不會報錯）

1. 損益表 `EquityAttributableToOwnersOfParent` 是「**淨利**歸屬母公司」，**不是權益**
2. `NetIncome` 只有 20 期（止於 2019），**用 `IncomeAfterTaxes`**（46 期）
3. `_per` 後綴是「占總資產百分比」，**整組忽略**
4. `TaiwanStockInfo` 是**變更事件流**（4,329 列／300+ 個 date／32 列 date=null），需 upsert
5. `origin_name` 中文名大量重複，**必須用英文 key 硬編碼對應**

## ⚠️ 本機 Chezmoi 待處理

`chezmoi status` 已於 2026-10-06 確認乾淨，無待處理變動。

## 🕐 最後更新

- 時間：2026-10-06（第五次更新）
- 更新者：OpenCode @ LAP2021-T153
- HEAD：`44b8413`（建立抓取程式）
- Git 狀態：**工作區乾淨，已與 `origin/master` 同步**
- 驗證：35 個單元測試通過、ruff 全過、端到端實測（台泥單季營收 331.7/381.2 億元證明單季值判斷正確）