# handoff.md — StockScreener

## ⏯️ 目前做到哪

**抓取程式已完成（45 測試全過），資料抓取掛機中，UI 與自動接續腳本已上線。**

- **藍圖**：`agents.md`（階段路線圖、文件分工、陷阱、常用指令）
- 程式碼：`fetch.py` ＋ `src/` ＋ `monitor.py`（進度儀表板）＋ `run_all.py`（自動接續）
- 規格書：`docs/superpowers/specs/2026-10-06-stock-screener-spec.md`（14 節，現行實作依據）
- 詞彙表：`CONTEXT.md`
- 決策紀錄：`docs/superpowers/specs/2026-10-05-decision-log.md`
- **資料來源實測**：`docs/review/data-source-verification.md`（26 項測試）

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
- **抓取掛機中**（2026-10-06 晚，DESKTOP-5241OJK）
  - 進度看儀表板 **<http://127.0.0.1:8765/>**（`monitor.py`，每 5 秒刷新）
  - 或 `uv run python fetch.py --status`
  - 全部完成時會寫 `logs/ALL_DONE.txt` ＋ 彈 Windows 通知
- **Git**：`master` = `origin/master`（收工前已推）
- **Obsidian**：`OpenCode專區/StockScreener/2026-10-06.md`

## 📍 專案路徑（重要，2026-10-06 變更）

**專案已從雲端硬碟搬到本機硬碟。**

| 機器 | 路徑 | 說明 |
|---|---|---|
| **DESKTOP-5241OJK** | `E:\OpenCode\Stock Screener(股票篩選)` | **現行工作目錄、data 存這裡** |
| 雲端硬碟上的舊副本 | （不再使用）| 見下方「⚠️ 舊副本狀態」 |

### 資料存在哪裡

`data/`（sync_state.db ＋ parquet）**存在 DESKTOP-5241OJK 的本機硬碟 `E:`**，不在雲端硬碟。

搬移原因與教訓：

1. 舊位置在雲端硬碟，同步軟體會在**檔案還沒寫完時就同步**，造成
   `sync_state.db` 說「已完成」但 `data/raw/` 對應的 parquet 不見（或不完整）。
2. 續傳邏輯原本只讀 SQLite，看不到檔案遺失，會直接跳過 → **資料空洞，且不會報錯**。
3. 已修（commit `f5a488e`）：續傳改以 `writer.exists()` 實際檔案為準，
   檔案遺失就從頭重抓（`last_date` 在檔案不存在時不可信）。
4. 雲端硬碟上的 data 應視為**不可靠**，不要再把抓取產物放回雲端同步路徑。

### ⚠️ 舊副本狀態

雲端硬碟上的舊副本**仍存在**，且是**過時的**：缺本次的
`monitor.py`、`run_all.py`，git 也落後 2 個 commit（但工作區有同樣的未提交修改，
打開會看到「有未提交變動」的假象）。

- **一律以 git ＋ `E:\OpenCode\...` 為準，不要再開舊副本**
- 舊副本要不要刪除由使用者手動決定（本 agent 不刪）

## ▶️ 明天在另一台主機怎麼做

### 程式碼

```bash
cd <該機的專案路徑>          # 路徑由使用者提供，尚未確定
git pull
uv sync                       # 首次
uv run python -m unittest discover tests   # 應 45 passed
```

### ⚠️ 兩台不能同時抓

額度是**帳號層級** 600 次/小時。這台（DESKTOP-5241OJK）正在抓，
另一台**不要**跑 fetch，除非這台的抓取已結束（看 `logs/ALL_DONE.txt` 或儀表板）。

### 抓取（若要在那台執行）

```bash
uv run python run_all.py      # 依序抓 7 個 dataset，中斷可續傳
uv run python monitor.py      # 另開，看進度 UI（:8765）
```

### 下一階段（階段 2 財務指標計算）

待辦（詳見 `agents.md` 階段 2 區塊）：

1. 實算篩選剩幾檔（原未解問題 #2）⚠️ `align_score` 無資料來源，可用條件是三個不是四個
2. ROE 多年平均（3 年／5 年）＋ TTM ROE 參考顯示
3. 杜邦五項（`IncomeAfterTaxes`，不可用 `NetIncome`）
4. 營收 CAGR（`revenue_year`+`revenue_month`，**不是 `date`**）
5. 還原股價：`DividendResult` + `ParValueChange` + `SplitPrice`

**資料要不要複製到另一台：尚未決定**（使用者明日提供該機路徑後再決定搬運方式）。
建議不要在雲端硬碟上直接同步 `data/`（見上方教訓），用 zip 一次搬移較安全。

## 🛠️ 2026-10-06 晚 在 DESKTOP-5241OJK 遇到的問題與處理

### 1. 專案路徑從雲端硬碟搬到本機（使用者主導）

- 變更：工作目錄改 `E:\OpenCode\Stock Screener(股票篩選)`
- 處理：搬移後在新位置 `uv sync` 重建環境、重跑 45 測試與 ruff 全過
- 影響：data 與 sync_state.db 跟著到本機，雲端副本作廢

### 2. 雲端同步造成 parquet 遺失，續傳會靜默跳過

- 症狀：`sync_state.db` 記錄 5 個全域 dataset 全完成，但 `data/raw/` 檔案不見
- 根因：續傳只信 SQLite 狀態，不看檔案
- 修法：`fetch.py` 續傳改比對 `writer.exists()`；新增 `SyncState.ok_ids()`
  （與 `done_ids` 差在排除 `empty`——empty 本來就沒檔，不能當遺失重抓）
- 驗證：新增 10 個測試（`TestParquetLossRecovery`），共 45 passed

### 3. 抓取 log 中文變亂碼

- 症狀：`run_all` 的 log 出現 `略??235` 這類問號
- 根因：Windows 主控台預設 cp950，Python 寫檔時用 cp950 編碼
- 修法：`run_all.py` 明確設 `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`
  （在 `os.environ.setdefault`，子行程繼承）
- 補充：先前用 PowerShell 看到的「??」部分是**顯示層**問題，
  逐位元組驗證 log 本身乾淨（0 個 U+FFFD、0 個 `?`）。看中文 log 請用
  `Get-Content -Encoding UTF8` 或直接開儀表板

### 4. 進度儀表板算出的分母不對

- 症狀：UI 算 2154 檔，fetch.py 實抓 2037 檔 → 進度條永遠到不了 100%
- 根因：UI 從本地 parquet 推股票池（含已下市股），fetch.py 用當期 API 結果
- 修法：`fetch.py` 抓取時寫 `data/raw/universe.json`（權威股票池），
  `monitor.py` 讀它當分母，**兩邊不再各算各的**

### 5. PowerShell 5.1 不支援 `Start-Process -Environment`

- 症狀：參數驗證錯誤，行程沒啟動
- 修法：改在父層先 `$env:PYTHONIOENCODING="utf-8"`，或由腳本內部 `os.environ` 設定

### 6. 抓取進度與排程工具（新增）

| 檔 | 用途 |
|---|---|
| `monitor.py` | 進度 UI，<http://127.0.0.1:8765/>，只讀 DB 不干擾抓取 |
| `run_all.py` | 依序抓 7 個 dataset，可 Ctrl+C 中斷續傳，完成彈通知 |
| `logs/` | 抓取 log（git 忽略）|

掛機指令（DESKTOP-5241OJK，2026-10-06 19:38 起）：

```bash
# 背景執行（無視窗）
.venv\Scripts\python.exe run_all.py     → logs\runner.out.log / run_all-YYYYMMDD-HHMM.log
.venv\Scripts\python.exe monitor.py --no-browser  → logs\monitor.out.log
```

## ✅ 已完成（10-06 晚）

1. 專案搬至本機 E:，環境重建、45 測試 + ruff 全過
2. `monitor.py` 進度儀表板（純標準庫，無新依賴）
3. `run_all.py` 自動接續腳本 ＋ Windows 完成通知
4. parquet 遺失恢復（含 10 個新測試）
5. `universe.json` 統一進度分母
6. 兩個 commit 已推（`f5a488e` 續傳修正、`0e0d038` UI 與腳本）

## ⚠️ 注意事項

### 掛機行程不會活過重開機

`run_all.py` / `monitor.py` 是背景行程，**重開機後不會自己恢復**。
開機後要重跑：

```bash
cd "E:\OpenCode\Stock Screener(股票篩選)"
uv run python monitor.py --no-browser   # 先開 UI
uv run python run_all.py                # 續傳抓取
```

### 抓取中不能關機／休眠

斷網會讓抓取失敗（續傳可救回，但該輪會停）。暫停請 `Ctrl+C` 或停行程。

### Token 不是必需的

免 token 即可取用多數 dataset；`.env` 已建但非抓取必要。

### ETF 保留但不抓財務

- stock master 保留全部 2507 檔（ETF 保留）
- 財務類只抓 2037 檔有財報的個股，行情類抓全部 2507 檔

### 還原股價需要三個來源

`DividendResult` + `ParValueChange` + `SplitPrice`（`CapitalReductionReferencePrice` 實測回空，不可用）

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
4. `TaiwanStockInfo` 是**變更事件流**，需取 `date` 最新一列（`latest_by_stock`）
5. `origin_name` 中文名大量重複，**必須用英文 key 硬編碼對應**
6. 普通股判斷**不能只看 4 碼數字**，要結合 `industry_category` ＋ 字母後綴（`classify_universe`）
7. 進度分母**只能用 `universe.json`**，不要從本地 parquet 重推（會含下市股）

### 安全機制（已內建，不要移除）

- 4xx 連續 3 次 → **熔斷停止**
- `403 ip banned` → 立即停止
- `402` 額度用盡 → 立即停止
- 5xx／網路錯誤 → 才重試（最多 3 次）

## 🕐 最後更新

- 時間：2026-10-06（收工，第二次）
- 更新者：OpenCode @ **DESKTOP-5241OJK**
- HEAD：見 `git log -1`
- Git push：✅ 已推（`f5a488e` + `0e0d038`）
- Chezmoi push：—（`chezmoi status` 於 2026-10-06 確認乾淨）
- 目標驗證：✅ 45 個單元測試通過（`uv run python -m unittest discover tests`）
- 目標驗證：✅ ruff 全過（`uv run ruff check src fetch.py monitor.py run_all.py tests`）
- 目標驗證：✅ 儀表板可讀（HTTP 200，12 個 dataset 進度正確，分母與 fetch.py 一致）
- 目標驗證：✅ 抓取實際進行中（`TaiwanStockFinancialStatements` 持續增加，0 錯誤）
- ⚠️ **抓取掛機中，重開機會停**（重啟方式見「掛機行程不會活過重開機」）
- 目標驗證：⚠️ 舊雲端副本未清理（由使用者決定，見「舊副本狀態」）
